from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import math
from types import TracebackType
from typing import NoReturn, cast
import unicodedata
from urllib.parse import quote

import httpx
from pydantic import ValidationError

from ke_memory_demo.core.json import JsonValue, canonical_json
from ke_memory_demo.domain import (
    OntologyBinding,
    OntologyBindingStatus,
    OntologyRelationRef,
    OntologyRole,
)
from ke_memory_demo.settings import AppSettings

from .models import (
    ElasticsearchConnection,
    IndexIdentity,
    OntologyAuthenticationError,
    OntologyDriftError,
    OntologyError,
    OntologyHealth,
    OntologyNotFoundError,
    OntologyRelation,
    OntologySchemaError,
    OntologyTerm,
    OntologyUnavailableError,
)


_KEYWORD_MAPPING_TYPES = frozenset({"keyword", "constant_keyword", "wildcard"})
_ANALYZED_MAPPING_TYPES = frozenset({"text", "match_only_text", "search_as_you_type"})
_SCALAR_MAPPING_TYPES = _KEYWORD_MAPPING_TYPES | _ANALYZED_MAPPING_TYPES
_MAX_CANDIDATE_FORMS = 16
_MAX_QUERY_CLAUSES = 100
_MAX_RESPONSE_SIZE = 100


@dataclass(frozen=True)
class _MappedField:
    source_path: str
    keyword_paths: tuple[str, ...]
    analyzed_paths: tuple[str, ...]


@dataclass(frozen=True)
class _LookupPlan:
    canonical: _MappedField
    aliases: _MappedField

    @property
    def fields(self) -> tuple[_MappedField, _MappedField]:
        return (self.canonical, self.aliases)


_MISSING = object()


@dataclass(frozen=True)
class _Candidate:
    term: OntologyTerm
    score: float
    matched_queries: tuple[str, ...] | None


@dataclass(frozen=True)
class _Match:
    candidate: _Candidate
    match_kind: int
    matched_alias: str | None


class ElasticsearchVocabulary:
    normalization_mode = "bounded-best-effort"

    def __init__(
        self,
        connection: ElasticsearchConnection,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        api_key = connection.api_key.get_secret_value()
        if not api_key.strip() or "\r" in api_key or "\n" in api_key:
            raise OntologyError("Elasticsearch API key must be a non-empty single-line value")
        self._connection = connection
        self._encoded_index = quote(connection.index, safe="")
        self._client = client or httpx.AsyncClient(timeout=connection.timeout_seconds)
        self._closed = False
        self._pinned_identity: IndexIdentity | None = None
        self._lookup_plan: _LookupPlan | None = None
        self._role_by_source_type = self._build_role_map(connection)

    @classmethod
    def from_app_settings(
        cls,
        settings: AppSettings,
        client: httpx.AsyncClient | None = None,
    ) -> ElasticsearchVocabulary:
        return cls(ElasticsearchConnection.from_app_settings(settings), client=client)

    async def __aenter__(self) -> ElasticsearchVocabulary:
        self._ensure_open()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc_value, traceback
        await self.aclose()

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._client.aclose()

    async def health(self) -> OntologyHealth:
        payload = await self._request("GET", "/_cluster/health")
        root = self._require_object(payload, "cluster health response")
        try:
            health = OntologyHealth.model_validate(
                {
                    "cluster_name": root.get("cluster_name"),
                    "status": root.get("status"),
                    "timed_out": root.get("timed_out"),
                }
            )
        except ValidationError as exc:
            raise OntologySchemaError("cluster health response has an invalid shape") from exc
        if health.status == "red":
            raise OntologyUnavailableError("Elasticsearch cluster health is red")
        if health.timed_out:
            raise OntologyUnavailableError("Elasticsearch cluster health request timed out")
        return health

    async def index_identity(self) -> IndexIdentity:
        cat_path = f"/_cat/indices/{self._encoded_index}"
        mapping_path = f"/{self._encoded_index}/_mapping"
        cat_before_payload = await self._request("GET", cat_path, params={"format": "json"})
        mapping_payload = await self._request("GET", mapping_path)
        cat_after_payload = await self._request("GET", cat_path, params={"format": "json"})
        before = self._parse_cat_identity(cat_before_payload)
        after = self._parse_cat_identity(cat_after_payload)
        if before != after:
            raise OntologyDriftError("Elasticsearch index identity changed during mapping read")
        index_name, index_uuid = before
        self._validate_cat_name(index_name)
        mapping_hash = hashlib.sha256(canonical_json(cast(JsonValue, mapping_payload))).hexdigest()
        identity = IndexIdentity(
            index_name=index_name,
            index_uuid=index_uuid,
            mapping_sha256=mapping_hash,
        )
        if self._pinned_identity is not None and identity != self._pinned_identity:
            raise OntologyDriftError("Elasticsearch index identity changed after it was pinned")
        lookup_plan = self._validate_mapping(mapping_payload, index_name)
        if self._pinned_identity is None:
            self._pinned_identity = identity
        self._lookup_plan = lookup_plan
        return identity

    async def resolve_terms(self, surface_terms: Sequence[str]) -> list[OntologyBinding]:
        originals, normalized = self._validate_surfaces(surface_terms)
        if not originals:
            return []
        await self.index_identity()

        unique_surfaces = list(dict.fromkeys(normalized))
        matches: dict[str, _Match | None] = {surface: None for surface in unique_surfaces}
        candidate_forms: dict[str, list[str]] = {surface: [] for surface in unique_surfaces}
        for original, normalized_surface in zip(originals, normalized, strict=True):
            forms = candidate_forms[normalized_surface]
            for form in self._candidate_forms(original, normalized_surface):
                if form not in forms and len(forms) < _MAX_CANDIDATE_FORMS:
                    forms.append(form)

        lookup_plan = self._require_lookup_plan()
        for surface in unique_surfaces:
            exact_payload = await self._request(
                "POST",
                f"/{self._encoded_index}/_search",
                json_body=self._exact_query(candidate_forms[surface], lookup_plan),
            )
            candidates = self._parse_search_hits(exact_payload)
            exact_matches = self._exact_matches(surface, candidates)
            primary_selected, primary_is_ambiguous = self._select_exact(exact_matches)
            if any(match.match_kind == 0 for match in exact_matches):
                if not primary_is_ambiguous:
                    matches[surface] = primary_selected
                continue

            lexical_payload = await self._request(
                "POST",
                f"/{self._encoded_index}/_search",
                json_body=self._lexical_query(surface, lookup_plan),
            )
            lexical_candidates = self._parse_search_hits(lexical_payload)
            if exact_matches:
                candidates_by_id: dict[str, _Candidate] = {}
                for candidate in (*candidates, *lexical_candidates):
                    candidates_by_id.setdefault(candidate.term.document_id, candidate)
                combined_exact = self._exact_matches(surface, list(candidates_by_id.values()))
                if any(match.match_kind == 0 for match in combined_exact):
                    combined_selected, combined_is_ambiguous = self._select_exact(combined_exact)
                    if not combined_is_ambiguous:
                        matches[surface] = combined_selected
                elif not primary_is_ambiguous:
                    matches[surface] = primary_selected
                continue

            recovered_exact = self._exact_matches(surface, lexical_candidates)
            recovered, is_ambiguous = self._select_exact(recovered_exact)
            if is_ambiguous:
                continue
            if recovered is not None:
                matches[surface] = recovered
                continue
            if not lexical_candidates:
                continue
            candidate = min(
                lexical_candidates,
                key=lambda item: (-item.score, item.term.document_id),
            )
            matches[surface] = _Match(
                candidate=candidate,
                match_kind=2,
                matched_alias=None,
            )

        return [
            self._binding_for(surface, normalized_surface, matches[normalized_surface])
            for surface, normalized_surface in zip(originals, normalized, strict=True)
        ]

    async def fetch_terms(self, document_ids: Sequence[str]) -> list[OntologyTerm]:
        ids = self._validate_document_ids(document_ids)
        if not ids:
            return []
        await self.index_identity()
        return await self._fetch_terms(ids)

    async def fetch_relations(self, document_ids: Sequence[str]) -> list[OntologyRelation]:
        ids = self._validate_document_ids(document_ids)
        if not ids:
            return []
        await self.index_identity()
        terms = await self._fetch_terms(ids)
        return [relation for term in terms for relation in term.relations]

    async def _fetch_terms(self, document_ids: tuple[str, ...]) -> list[OntologyTerm]:
        payload = await self._request(
            "POST",
            f"/{self._encoded_index}/_mget",
            json_body={"ids": list(document_ids)},
        )
        root = self._require_object(payload, "multi-get response")
        raw_docs = root.get("docs")
        if not isinstance(raw_docs, list):
            raise OntologySchemaError("multi-get response docs must be a list")
        docs = cast(list[object], raw_docs)

        requested = set(document_ids)
        by_id: dict[str, OntologyTerm] = {}
        missing: set[str] = set()
        for raw_doc in docs:
            doc = self._require_object(raw_doc, "multi-get document")
            document_id = self._require_non_empty_string(doc.get("_id"), "multi-get _id")
            if document_id in by_id or document_id in missing:
                raise OntologySchemaError(
                    f"multi-get response contains duplicate document ID {document_id!r}"
                )
            if document_id not in requested:
                raise OntologySchemaError(
                    f"multi-get response contains unrequested document ID {document_id!r}"
                )
            found = doc.get("found")
            if not isinstance(found, bool):
                raise OntologySchemaError("multi-get document found flag must be a boolean")
            if not found:
                missing.add(document_id)
                continue
            by_id[document_id] = self._parse_source(document_id, doc.get("_source"))

        missing.update(requested.difference(by_id))
        if missing:
            missing_list = ", ".join(sorted(missing))
            raise OntologyNotFoundError(f"required ontology documents not found: {missing_list}")
        return [by_id[document_id] for document_id in document_ids]

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
        json_body: Mapping[str, object] | None = None,
    ) -> object:
        self._ensure_open()
        allowed = {
            ("GET", "/_cluster/health"),
            ("GET", f"/_cat/indices/{self._encoded_index}"),
            ("GET", f"/{self._encoded_index}/_mapping"),
            ("POST", f"/{self._encoded_index}/_search"),
            ("POST", f"/{self._encoded_index}/_mget"),
        }
        if (method, path) not in allowed:
            raise OntologyError(f"Elasticsearch request is not allowlisted: {method} {path}")

        url = f"{self._connection.endpoint}{path}"
        headers = {"Authorization": f"ApiKey {self._connection.api_key.get_secret_value()}"}
        try:
            response = await self._client.request(
                method,
                url,
                params=params,
                json=json_body,
                headers=headers,
                timeout=self._connection.timeout_seconds,
                follow_redirects=False,
            )
        except httpx.TransportError:
            raise OntologyUnavailableError(
                f"Elasticsearch transport failed for {method} {path}"
            ) from None

        if response.status_code in {401, 403}:
            raise OntologyAuthenticationError(
                f"Elasticsearch authentication failed with HTTP {response.status_code}"
            )
        if response.status_code == 404:
            raise OntologyNotFoundError(f"Elasticsearch resource not found for {method} {path}")
        if response.status_code == 400:
            raise OntologySchemaError(
                f"Elasticsearch rejected the schema or query for {method} {path}"
            )
        if response.status_code in {408, 429} or response.status_code >= 500:
            raise OntologyUnavailableError(
                f"Elasticsearch unavailable with HTTP {response.status_code}"
            )
        if not 200 <= response.status_code < 300:
            raise OntologyError(
                f"Elasticsearch rejected {method} {path} with HTTP {response.status_code}"
            )
        try:
            return cast(object, response.json())
        except ValueError:
            raise OntologySchemaError(
                f"Elasticsearch returned invalid JSON for {method} {path}"
            ) from None

    def _parse_cat_identity(self, payload: object) -> tuple[str, str]:
        if not isinstance(payload, list):
            raise OntologySchemaError("index identity response must contain exactly one index")
        items = cast(list[object], payload)
        if len(items) != 1:
            raise OntologySchemaError("index identity response must contain exactly one index")
        item = self._require_object(items[0], "index identity entry")
        return (
            self._require_non_empty_string(item.get("index"), "index identity name"),
            self._require_non_empty_string(item.get("uuid"), "index identity UUID"),
        )

    def _validate_cat_name(self, index_name: str) -> None:
        if index_name != self._connection.index:
            self._raise_identity_name_mismatch("CAT index name does not match the configured index")

    def _raise_identity_name_mismatch(self, message: str) -> NoReturn:
        if self._pinned_identity is not None:
            raise OntologyDriftError("Elasticsearch index identity changed after it was pinned")
        raise OntologySchemaError(message)

    def _validate_mapping(
        self,
        payload: object,
        cat_index_name: str,
    ) -> _LookupPlan:
        root = self._require_object(payload, "mapping response")
        if len(root) != 1:
            raise OntologySchemaError("mapping response must contain exactly one index")
        mapping_index_name, raw_index_mapping = next(iter(root.items()))
        if mapping_index_name != self._connection.index or mapping_index_name != cat_index_name:
            self._raise_identity_name_mismatch(
                "mapping index name does not match the configured and CAT index"
            )
        index_mapping = self._require_object(raw_index_mapping, "index mapping")
        mappings = self._require_object(index_mapping.get("mappings"), "mappings")
        properties = self._require_object(mappings.get("properties"), "mapping properties")

        fields = self._connection.fields
        canonical = self._mapped_field(properties, fields.canonical)
        self._require_scalar_mapping(properties, fields.type)
        aliases = self._mapped_field(properties, fields.aliases)

        relation_mapping = self._find_mapping(properties, fields.relations)
        relation_type = relation_mapping.get("type", "object")
        if relation_type not in {"object", "nested"}:
            raise OntologySchemaError(
                f"mapping field {fields.relations!r} must be object or nested"
            )
        relation_properties = self._require_object(
            relation_mapping.get("properties"),
            f"mapping field {fields.relations!r} properties",
        )
        self._require_scalar_mapping(relation_properties, fields.relation_type)
        self._require_scalar_mapping(relation_properties, fields.relation_target_id)
        return _LookupPlan(canonical=canonical, aliases=aliases)

    def _require_scalar_mapping(
        self,
        properties: Mapping[str, object],
        path: str,
    ) -> dict[str, object]:
        mapping = self._find_mapping(properties, path)
        mapping_type = mapping.get("type")
        if mapping_type not in _SCALAR_MAPPING_TYPES:
            raise OntologySchemaError(f"mapping field {path!r} must have a scalar text type")
        self._require_searchable_mapping(mapping, path)
        return mapping

    @staticmethod
    def _require_searchable_mapping(
        mapping: Mapping[str, object],
        path: str,
    ) -> None:
        indexed = mapping.get("index", True)
        if not isinstance(indexed, bool):
            raise OntologySchemaError(f"mapping field {path!r} index must be a boolean")
        if not indexed:
            raise OntologySchemaError(f"mapping field {path!r} must be searchable")

    def _mapped_field(
        self,
        properties: Mapping[str, object],
        path: str,
    ) -> _MappedField:
        mapping = self._require_scalar_mapping(properties, path)
        mapping_type = cast(str, mapping["type"])
        keyword_paths: list[str] = []
        analyzed_paths: list[str] = []
        if mapping_type in _KEYWORD_MAPPING_TYPES:
            keyword_paths.append(path)
        else:
            index_options = mapping.get("index_options", "positions")
            if index_options not in {"positions", "offsets"}:
                raise OntologySchemaError(
                    f"mapping field {path!r} index_options must support phrase positions"
                )
            analyzed_paths.append(path)
            raw_multifields = mapping.get("fields")
            if raw_multifields is not None:
                multifields = self._require_object(
                    raw_multifields,
                    f"mapping field {path!r} multifields",
                )
                for name in sorted(multifields):
                    multifield = self._require_object(
                        multifields[name],
                        f"mapping field {path!r}.{name}",
                    )
                    if multifield.get("type") in _KEYWORD_MAPPING_TYPES:
                        self._require_searchable_mapping(
                            multifield,
                            f"{path}.{name}",
                        )
                        keyword_paths.append(f"{path}.{name}")
                        break
        return _MappedField(
            source_path=path,
            keyword_paths=tuple(keyword_paths),
            analyzed_paths=tuple(analyzed_paths),
        )

    def _find_mapping(
        self,
        properties: Mapping[str, object],
        path: str,
    ) -> dict[str, object]:
        direct = properties.get(path)
        if direct is not None:
            return self._require_object(direct, f"mapping field {path!r}")

        current = properties
        for index, segment in enumerate(path.split(".")):
            node = self._require_object(current.get(segment), f"mapping field {path!r}")
            if index == len(path.split(".")) - 1:
                return node
            current = self._require_object(
                node.get("properties"), f"mapping field {path!r} properties"
            )
        raise OntologySchemaError(f"mapping field {path!r} is missing")

    def _parse_search_hits(self, payload: object) -> list[_Candidate]:
        root = self._require_object(payload, "search response")
        timed_out = root.get("timed_out", False)
        if not isinstance(timed_out, bool):
            raise OntologySchemaError("search timed_out must be a boolean")
        if timed_out:
            raise OntologyUnavailableError("Elasticsearch search timed out")
        shards = self._require_object(root.get("_shards"), "search _shards")
        shard_counts: dict[str, int] = {}
        for name in ("total", "successful", "skipped", "failed"):
            value = shards.get(name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise OntologySchemaError(f"search _shards.{name} must be a non-negative integer")
            shard_counts[name] = value
        if shard_counts["failed"] != 0:
            raise OntologyUnavailableError("Elasticsearch search did not complete on all shards")
        hits_wrapper = self._require_object(root.get("hits"), "search hits")
        raw_hits_value = hits_wrapper.get("hits")
        if not isinstance(raw_hits_value, list):
            raise OntologySchemaError("search hits.hits must be a list")
        raw_hits = cast(list[object], raw_hits_value)

        seen_ids: set[str] = set()
        candidates: list[_Candidate] = []
        for raw_hit in raw_hits:
            hit = self._require_object(raw_hit, "search hit")
            document_id = self._require_non_empty_string(hit.get("_id"), "search hit _id")
            if document_id in seen_ids:
                raise OntologySchemaError(
                    f"search response contains duplicate document ID {document_id!r}"
                )
            seen_ids.add(document_id)
            raw_score = hit.get("_score")
            if isinstance(raw_score, bool) or not isinstance(raw_score, (int, float)):
                raise OntologySchemaError("search hit _score must be a finite number")
            score = float(raw_score)
            if not math.isfinite(score):
                raise OntologySchemaError("search hit _score must be a finite number")

            raw_matched = hit.get("matched_queries")
            matched_queries: tuple[str, ...] | None
            if raw_matched is None:
                matched_queries = None
            elif isinstance(raw_matched, list):
                matched_items = cast(list[object], raw_matched)
                if not all(isinstance(item, str) and item for item in matched_items):
                    raise OntologySchemaError("search hit matched_queries must be a string list")
                matched_queries = tuple(cast(list[str], matched_items))
            else:
                raise OntologySchemaError("search hit matched_queries must be a string list")
            candidates.append(
                _Candidate(
                    term=self._parse_source(document_id, hit.get("_source")),
                    score=score,
                    matched_queries=matched_queries,
                )
            )
        return candidates

    def _parse_source(self, document_id: str, raw_source: object) -> OntologyTerm:
        source = self._require_object(raw_source, f"document {document_id!r} _source")
        fields = self._connection.fields
        canonical = self._require_non_empty_string(
            self._path_value(
                source,
                fields.canonical,
                f"document {document_id!r} canonical term",
            ),
            f"document {document_id!r} canonical term",
        )
        source_type = self._require_non_empty_string(
            self._path_value(
                source,
                fields.type,
                f"document {document_id!r} source type",
            ),
            f"document {document_id!r} source type",
        )
        raw_aliases_value = self._path_value(
            source,
            fields.aliases,
            f"document {document_id!r} aliases",
        )
        if not isinstance(raw_aliases_value, list):
            raise OntologySchemaError(
                f"document {document_id!r} aliases must be a list of non-empty strings"
            )
        raw_aliases = cast(list[object], raw_aliases_value)
        if not all(isinstance(alias, str) and alias for alias in raw_aliases):
            raise OntologySchemaError(
                f"document {document_id!r} aliases must be a list of non-empty strings"
            )
        aliases = tuple(cast(list[str], raw_aliases))
        raw_relations_value = self._path_value(
            source,
            fields.relations,
            f"document {document_id!r} relations",
        )
        if not isinstance(raw_relations_value, list):
            raise OntologySchemaError(f"document {document_id!r} relations must be a list")
        raw_relations = cast(list[object], raw_relations_value)

        relations: list[OntologyRelation] = []
        for raw_relation in raw_relations:
            relation = self._require_object(raw_relation, f"document {document_id!r} relation")
            relation_type = self._require_non_empty_string(
                self._path_value(
                    relation,
                    fields.relation_type,
                    f"document {document_id!r} relation type",
                ),
                f"document {document_id!r} relation type",
            )
            target_id = self._require_non_empty_string(
                self._path_value(
                    relation,
                    fields.relation_target_id,
                    f"document {document_id!r} relation target",
                ),
                f"document {document_id!r} relation target",
            )
            relations.append(
                OntologyRelation(
                    source_document_id=document_id,
                    relation_type=relation_type,
                    target_id=target_id,
                )
            )
        try:
            return OntologyTerm(
                document_id=document_id,
                canonical_term=canonical,
                source_type=source_type,
                role=self._role_by_source_type.get(source_type),
                aliases=aliases,
                relations=tuple(relations),
            )
        except ValidationError as exc:
            raise OntologySchemaError(f"document {document_id!r} is malformed") from exc

    def _exact_matches(
        self,
        surface: str,
        candidates: Sequence[_Candidate],
    ) -> list[_Match]:
        matches: list[_Match] = []
        for candidate in candidates:
            term = candidate.term
            if self._normalize(term.canonical_term) == surface:
                matches.append(_Match(candidate, 0, None))
                continue
            for alias in term.aliases:
                if self._normalize(alias) == surface:
                    matches.append(_Match(candidate, 1, alias))
                    break
        return matches

    @staticmethod
    def _select_exact(matches: Sequence[_Match]) -> tuple[_Match | None, bool]:
        if not matches:
            return None, False
        ranked = sorted(
            matches,
            key=lambda match: (
                match.match_kind,
                -match.candidate.score,
                match.candidate.term.document_id,
            ),
        )
        best = ranked[0]
        tied_documents = {
            match.candidate.term.document_id
            for match in ranked
            if match.match_kind == best.match_kind and match.candidate.score == best.candidate.score
        }
        if len(tied_documents) > 1:
            return None, True
        return best, False

    @staticmethod
    def _binding_for(
        surface: str,
        normalized_surface: str,
        match: _Match | None,
    ) -> OntologyBinding:
        if match is None:
            return OntologyBinding(
                surface_form=surface,
                normalized_surface=normalized_surface,
                status=OntologyBindingStatus.UNRESOLVED,
            )
        term = match.candidate.term
        status = (
            OntologyBindingStatus.RESOLVED
            if term.role is not None
            else OntologyBindingStatus.UNRESOLVED_ROLE
        )
        return OntologyBinding(
            surface_form=surface,
            normalized_surface=normalized_surface,
            status=status,
            document_id=term.document_id,
            canonical_term=term.canonical_term,
            role=term.role,
            source_type=term.source_type,
            matched_alias=match.matched_alias,
            aliases=term.aliases,
            relations=tuple(
                OntologyRelationRef(
                    relation_type=relation.relation_type,
                    target_id=relation.target_id,
                )
                for relation in term.relations
            ),
        )

    def _exact_query(
        self,
        forms: Sequence[str],
        plan: _LookupPlan,
    ) -> dict[str, object]:
        should: list[object] = []
        for mapped_field in plan.fields:
            for path in mapped_field.keyword_paths:
                for form in forms:
                    should.append(
                        {
                            "term": {
                                path: {
                                    "value": form,
                                    "case_insensitive": True,
                                }
                            }
                        }
                    )
            for path in mapped_field.analyzed_paths:
                for form in forms:
                    should.append({"match_phrase": {path: {"query": form}}})
        return self._search_body(should[:_MAX_QUERY_CLAUSES])

    def _lexical_query(
        self,
        surface: str,
        plan: _LookupPlan,
    ) -> dict[str, object]:
        should: list[object] = []
        keyword_paths: list[str] = []
        analyzed_paths: list[str] = []
        for mapped_field in plan.fields:
            keyword_paths.extend(mapped_field.keyword_paths)
            analyzed_paths.extend(mapped_field.analyzed_paths)
        pattern = self._wildcard_pattern(surface)
        for path in dict.fromkeys(keyword_paths):
            should.append(
                {
                    "wildcard": {
                        path: {
                            "value": pattern,
                            "case_insensitive": True,
                        }
                    }
                }
            )
        unique_analyzed_paths = list(dict.fromkeys(analyzed_paths))
        if unique_analyzed_paths:
            should.append(
                {
                    "multi_match": {
                        "query": surface,
                        "fields": unique_analyzed_paths,
                        "type": "best_fields",
                        "operator": "and",
                    }
                }
            )
        return self._search_body(should[:_MAX_QUERY_CLAUSES])

    def _search_body(self, should: list[object]) -> dict[str, object]:
        if not should:
            raise OntologyError("validated mapping produced no usable search clauses")
        fields = self._connection.fields
        source_fields = list(
            dict.fromkeys((fields.canonical, fields.type, fields.aliases, fields.relations))
        )
        return {
            "_source": source_fields,
            "query": {"bool": {"minimum_should_match": 1, "should": should}},
            "size": _MAX_RESPONSE_SIZE,
            "sort": [{"_score": {"order": "desc"}}],
            "track_total_hits": False,
        }

    @staticmethod
    def _candidate_forms(surface: str, normalized_surface: str) -> tuple[str, ...]:
        raw_collapsed = " ".join(surface.strip().split())
        nfkc_collapsed = " ".join(unicodedata.normalize("NFKC", surface).strip().split())
        candidates = [raw_collapsed, nfkc_collapsed, normalized_surface]
        for canonical_form in (
            unicodedata.normalize("NFC", normalized_surface),
            unicodedata.normalize("NFD", normalized_surface),
        ):
            for case_form in (
                canonical_form,
                canonical_form.upper(),
                canonical_form.title(),
            ):
                candidates.append(case_form)
                candidates.append(ElasticsearchVocabulary._fullwidth_ascii_compatibility(case_form))
        return tuple(dict.fromkeys(candidates))[:_MAX_CANDIDATE_FORMS]

    @staticmethod
    def _fullwidth_ascii_compatibility(value: str) -> str:
        characters: list[str] = []
        for character in value:
            if character == " ":
                characters.append("\u3000")
            elif "!" <= character <= "~":
                characters.append(chr(ord(character) + 0xFEE0))
            else:
                characters.append(character)
        return "".join(characters)

    @staticmethod
    def _wildcard_pattern(surface: str) -> str:
        escaped = surface.replace("\\", "\\\\").replace("*", "\\*").replace("?", "\\?")
        return f"*{escaped.replace(' ', '*')}*"

    @classmethod
    def _validate_surfaces(
        cls,
        surface_terms: Sequence[str],
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        if isinstance(surface_terms, (str, bytes)):
            raise OntologyError("surface_terms must be a sequence of strings")
        originals = cast(tuple[object, ...], tuple(surface_terms))
        normalized: list[str] = []
        for surface in originals:
            if not isinstance(surface, str):
                raise OntologyError("surface_terms must contain only strings")
            normalized_surface = cls._normalize(surface)
            if not normalized_surface:
                raise OntologyError("surface terms must not be empty after normalization")
            normalized.append(normalized_surface)
        return cast(tuple[str, ...], originals), tuple(normalized)

    @staticmethod
    def _validate_document_ids(document_ids: Sequence[str]) -> tuple[str, ...]:
        if isinstance(document_ids, (str, bytes)):
            raise OntologyError("document_ids must be a sequence of strings")
        ids = cast(tuple[object, ...], tuple(document_ids))
        for document_id in ids:
            if not isinstance(document_id, str) or not document_id.strip():
                raise OntologyError("document IDs must be non-empty strings")
        if len(ids) != len(set(ids)):
            raise OntologyError("document IDs must not contain duplicates")
        return cast(tuple[str, ...], ids)

    @staticmethod
    def _normalize(surface: str) -> str:
        normalized = unicodedata.normalize("NFKC", surface)
        return " ".join(normalized.strip().split()).casefold()

    def _path_value(
        self,
        root: Mapping[str, object],
        path: str,
        label: str,
    ) -> object:
        direct = root.get(path, _MISSING)
        if direct is not _MISSING:
            return direct
        current: object = root
        for segment in path.split("."):
            current_mapping = self._require_object(current, f"{label} intermediate")
            if segment not in current_mapping:
                raise OntologySchemaError(f"{label} path {path!r} is missing")
            current = current_mapping[segment]
        return current

    def _require_lookup_plan(self) -> _LookupPlan:
        if self._lookup_plan is None:
            raise OntologyError("Elasticsearch mapping has not been validated")
        return self._lookup_plan

    @staticmethod
    def _require_object(value: object, label: str) -> dict[str, object]:
        if not isinstance(value, dict):
            raise OntologySchemaError(f"{label} must be an object")
        mapping = cast(dict[object, object], value)
        if not all(isinstance(key, str) for key in mapping):
            raise OntologySchemaError(f"{label} must be an object")
        return cast(dict[str, object], mapping)

    @staticmethod
    def _require_non_empty_string(value: object, label: str) -> str:
        if not isinstance(value, str) or not value:
            raise OntologySchemaError(f"{label} must be a non-empty string")
        return value

    @staticmethod
    def _build_role_map(connection: ElasticsearchConnection) -> dict[str, OntologyRole]:
        return {
            **{source_type: OntologyRole.CONCEPT for source_type in connection.roles.concept},
            **{source_type: OntologyRole.INDIVIDUAL for source_type in connection.roles.individual},
            **{source_type: OntologyRole.OPERATOR for source_type in connection.roles.operator},
        }

    def _ensure_open(self) -> None:
        if self._closed:
            raise OntologyError("Elasticsearch vocabulary adapter is closed")
