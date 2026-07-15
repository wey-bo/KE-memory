from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from ke_memory_demo.domain import OntologyBindingStatus, OntologyRelationRef, OntologyRole
from ke_memory_demo.ontology import (
    ElasticsearchConnection,
    ElasticsearchVocabulary,
    OntologyAuthenticationError,
    OntologyDriftError,
    OntologyError,
    OntologyNotFoundError,
    OntologySchemaError,
    OntologyUnavailableError,
)
from ke_memory_demo.settings import ElasticsearchFields, ElasticsearchRoles, load_settings


JsonObject = dict[str, Any]
FIELDS = ElasticsearchFields(
    canonical="term",
    type="type",
    aliases="aliases",
    relations="relations",
    relation_type="type",
    relation_target_id="target_id",
)
ROLES = ElasticsearchRoles(
    concept=("concept", "class"),
    individual=("individual", "instance"),
    operator=("operator", "predicate"),
)


def _connection(
    *,
    endpoint: str = "https://es.test.invalid",
    index: str = "vocab",
    api_key: str = "unit-secret-value",
) -> ElasticsearchConnection:
    return ElasticsearchConnection(
        endpoint=endpoint,
        index=index,
        api_key=SecretStr(api_key),
        timeout_seconds=2.5,
        fields=FIELDS,
        roles=ROLES,
    )


def _mapping(*, canonical_type: str = "keyword") -> JsonObject:
    return {
        "vocab": {
            "mappings": {
                "properties": {
                    "term": {"type": canonical_type},
                    "type": {"type": "keyword"},
                    "aliases": {"type": "keyword"},
                    "relations": {
                        "type": "nested",
                        "properties": {
                            "type": {"type": "keyword"},
                            "target_id": {"type": "keyword"},
                        },
                    },
                }
            }
        }
    }


def _source(
    term: str,
    *,
    source_type: str = "concept",
    aliases: list[object] | None = None,
    relations: list[JsonObject] | None = None,
) -> JsonObject:
    return {
        "term": term,
        "type": source_type,
        "aliases": [] if aliases is None else aliases,
        "relations": [] if relations is None else relations,
    }


def _hit(
    document_id: str,
    source: JsonObject,
    *,
    score: float = 1.0,
    matched_queries: list[str] | None = None,
) -> JsonObject:
    hit: JsonObject = {
        "_index": "vocab",
        "_id": document_id,
        "_score": score,
        "_source": source,
    }
    if matched_queries is not None:
        hit["matched_queries"] = matched_queries
    return hit


def _search_response(hits: list[JsonObject], *, timed_out: bool = False) -> JsonObject:
    scores = [float(hit["_score"]) for hit in hits]
    return {
        "took": 1,
        "timed_out": timed_out,
        "_shards": {"total": 1, "successful": 1, "skipped": 0, "failed": 0},
        "hits": {
            "total": {"value": len(hits), "relation": "eq"},
            "max_score": max(scores, default=None),
            "hits": hits,
        },
    }


class EsHarness:
    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.search_responses: list[JsonObject] = []
        self.mget_response: JsonObject = {"docs": []}
        self.health_response: JsonObject = {
            "cluster_name": "unit-cluster",
            "status": "green",
            "timed_out": False,
        }
        self.identity_versions: list[tuple[str, str, JsonObject]] = [
            ("vocab", "uuid-1", _mapping())
        ]
        self.statuses: dict[tuple[str, str], int] = {}
        self.invalid_json_paths: set[str] = set()
        self.failure: Exception | None = None
        self._identity_call = -1
        self.client = httpx.AsyncClient(transport=httpx.MockTransport(self.handle))

    async def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.failure is not None:
            raise self.failure

        path = request.url.path
        status = self.statuses.get((request.method, path), 200)
        if path in self.invalid_json_paths:
            return httpx.Response(status, content=b"{not-json", request=request)

        if request.method == "GET" and path == "/_cluster/health":
            payload = self.health_response
        elif request.method == "GET" and path == "/_cat/indices/vocab":
            self._identity_call += 1
            index_name, index_uuid, _ = self.identity_versions[
                min(self._identity_call, len(self.identity_versions) - 1)
            ]
            payload = [{"index": index_name, "uuid": index_uuid}]
        elif request.method == "GET" and path == "/vocab/_mapping":
            _, _, payload = self.identity_versions[
                min(max(self._identity_call, 0), len(self.identity_versions) - 1)
            ]
        elif request.method == "POST" and path == "/vocab/_search":
            payload = (
                self.search_responses.pop(0) if self.search_responses else _search_response([])
            )
        elif request.method == "POST" and path == "/vocab/_mget":
            payload = self.mget_response
        else:
            raise AssertionError(f"unexpected request: {request.method} {path}")
        return httpx.Response(
            status,
            content=json.dumps(payload).encode(),
            headers={"content-type": "application/json"},
            request=request,
        )

    def adapter(self) -> ElasticsearchVocabulary:
        return ElasticsearchVocabulary(_connection(), client=self.client)


@pytest.fixture
def es() -> EsHarness:
    return EsHarness()


@pytest.mark.asyncio
async def test_resolve_terms_sends_exact_read_only_shapes_and_preserves_misses(
    es: EsHarness,
) -> None:
    es.search_responses = [
        _search_response([_hit("concept:triangle", _source("triangle"), score=7.0)]),
        _search_response([]),
    ]

    bindings = await es.adapter().resolve_terms(["triangle", "unknown phrase"])

    assert bindings[0].model_dump(mode="json") == {
        "surface_form": "triangle",
        "normalized_surface": "triangle",
        "status": "resolved",
        "document_id": "concept:triangle",
        "canonical_term": "triangle",
        "role": "concept",
        "source_type": "concept",
        "matched_alias": None,
        "aliases": [],
        "relations": [],
    }
    assert bindings[1].status is OntologyBindingStatus.UNRESOLVED
    assert [(request.method, request.url.path) for request in es.requests] == [
        ("GET", "/_cat/indices/vocab"),
        ("GET", "/vocab/_mapping"),
        ("POST", "/vocab/_search"),
        ("POST", "/vocab/_search"),
    ]
    assert es.requests[0].url.query == b"format=json"
    exact_body = json.loads(es.requests[2].content)
    assert exact_body == {
        "_source": ["term", "type", "aliases", "relations"],
        "query": {
            "bool": {
                "minimum_should_match": 1,
                "should": [
                    {"term": {"term": {"value": "triangle", "_name": "canonical_0"}}},
                    {"term": {"aliases": {"value": "triangle", "_name": "alias_0"}}},
                    {"term": {"term": {"value": "unknown phrase", "_name": "canonical_1"}}},
                    {"term": {"aliases": {"value": "unknown phrase", "_name": "alias_1"}}},
                ],
            }
        },
        "size": 20,
        "sort": [{"_score": {"order": "desc"}}],
        "track_total_hits": False,
    }
    lexical_body = json.loads(es.requests[3].content)
    assert lexical_body["query"]["bool"]["should"] == [
        {
            "multi_match": {
                "query": "unknown phrase",
                "fields": ["term", "aliases"],
                "type": "best_fields",
                "operator": "and",
                "_name": "lexical_0",
            }
        }
    ]
    assert all(
        request.headers["authorization"] == "ApiKey unit-secret-value" for request in es.requests
    )
    assert all(
        forbidden not in request.url.path
        for request in es.requests
        for forbidden in ("_bulk", "_doc", "_update", "_delete_by_query")
    )


@pytest.mark.asyncio
async def test_normalization_alias_ranking_and_duplicate_mapping(es: EsHarness) -> None:
    original = "  ＴＲＩＡＮＧＬＥ\t shape  "
    es.search_responses = [
        _search_response(
            [
                _hit(
                    "alias-high-score",
                    _source("three-sided polygon", aliases=["triangle shape"]),
                    score=100.0,
                ),
                _hit("canonical-low-score", _source("triangle shape"), score=1.0),
            ]
        )
    ]

    bindings = await es.adapter().resolve_terms([original, "triangle shape", original])

    assert [binding.document_id for binding in bindings] == [
        "canonical-low-score",
        "canonical-low-score",
        "canonical-low-score",
    ]
    assert [binding.surface_form for binding in bindings] == [original, "triangle shape", original]
    assert all(binding.normalized_surface == "triangle shape" for binding in bindings)
    body = json.loads(es.requests[-1].content)
    assert len(body["query"]["bool"]["should"]) == 2


@pytest.mark.asyncio
async def test_alias_match_is_recorded(es: EsHarness) -> None:
    es.search_responses = [
        _search_response(
            [_hit("shape", _source("three-sided polygon", aliases=["Triangle", "tri"]))]
        )
    ]

    binding = (await es.adapter().resolve_terms([" triangle "]))[0]

    assert binding.document_id == "shape"
    assert binding.matched_alias == "Triangle"


@pytest.mark.asyncio
async def test_exact_top_score_tie_is_ambiguous_and_skips_lexical_fallback(
    es: EsHarness,
) -> None:
    es.search_responses = [
        _search_response(
            [
                _hit("doc-b", _source("triangle"), score=3.0),
                _hit("doc-a", _source("triangle"), score=3.0),
            ]
        )
    ]

    binding = (await es.adapter().resolve_terms(["triangle"]))[0]

    assert binding.status is OntologyBindingStatus.UNRESOLVED
    assert [request.url.path for request in es.requests].count("/vocab/_search") == 1


@pytest.mark.asyncio
async def test_lexical_fallback_uses_matched_query_and_document_id_tiebreak(
    es: EsHarness,
) -> None:
    es.search_responses = [
        _search_response([]),
        _search_response(
            [
                _hit("doc-z", _source("triangular item"), score=2.0, matched_queries=["lexical_0"]),
                _hit("doc-a", _source("triangular form"), score=2.0, matched_queries=["lexical_0"]),
            ]
        ),
    ]

    binding = (await es.adapter().resolve_terms(["triangular shape"]))[0]

    assert binding.document_id == "doc-a"


@pytest.mark.asyncio
async def test_unknown_source_type_retains_identity_as_unresolved_role(es: EsHarness) -> None:
    es.search_responses = [
        _search_response(
            [
                _hit(
                    "unknown-role",
                    _source(
                        "triangle",
                        source_type="geometry_kind",
                        aliases=["tri"],
                        relations=[{"type": "broader", "target_id": "shape"}],
                    ),
                )
            ]
        )
    ]

    binding = (await es.adapter().resolve_terms(["triangle"]))[0]

    assert binding.status is OntologyBindingStatus.UNRESOLVED_ROLE
    assert binding.document_id == "unknown-role"
    assert binding.canonical_term == "triangle"
    assert binding.source_type == "geometry_kind"
    assert binding.role is None
    assert binding.relations == (OntologyRelationRef(relation_type="broader", target_id="shape"),)


@pytest.mark.asyncio
async def test_search_batches_keep_size_and_clause_count_bounded(es: EsHarness) -> None:
    surfaces = [f"term {index}" for index in range(120)]
    es.search_responses = [_search_response([]) for _ in range(5)]

    bindings = await es.adapter().resolve_terms(surfaces)

    assert len(bindings) == 120
    search_bodies = [
        json.loads(request.content)
        for request in es.requests
        if request.url.path == "/vocab/_search"
    ]
    assert len(search_bodies) == 5
    assert all(1 <= body["size"] <= 100 for body in search_bodies)
    assert all(len(body["query"]["bool"]["should"]) <= 100 for body in search_bodies)


@pytest.mark.asyncio
async def test_fetch_terms_uses_one_ordered_mget_and_parses_relations(es: EsHarness) -> None:
    es.mget_response = {
        "docs": [
            {
                "_index": "vocab",
                "_id": "second",
                "_version": 1,
                "_seq_no": 2,
                "_primary_term": 1,
                "found": True,
                "_source": _source("Second", source_type="mystery"),
            },
            {
                "_index": "vocab",
                "_id": "first",
                "_version": 1,
                "_seq_no": 1,
                "_primary_term": 1,
                "found": True,
                "_source": _source(
                    "First",
                    source_type="operator",
                    aliases=["one"],
                    relations=[
                        {"type": "parent", "target_id": "root"},
                        {"type": "inverse", "target_id": "second"},
                    ],
                ),
            },
        ]
    }

    terms = await es.adapter().fetch_terms(["first", "second"])

    assert [term.document_id for term in terms] == ["first", "second"]
    assert terms[0].role is OntologyRole.OPERATOR
    assert terms[1].role is None
    assert [relation.target_id for relation in terms[0].relations] == ["root", "second"]
    request = es.requests[-1]
    assert request.method == "POST"
    assert request.url.path == "/vocab/_mget"
    assert json.loads(request.content) == {"ids": ["first", "second"]}


@pytest.mark.asyncio
async def test_fetch_relations_preserves_document_and_source_order(es: EsHarness) -> None:
    es.mget_response = {
        "docs": [
            {
                "_index": "vocab",
                "_id": "a",
                "found": True,
                "_source": _source(
                    "A",
                    relations=[
                        {"type": "first", "target_id": "x"},
                        {"type": "second", "target_id": "y"},
                    ],
                ),
            },
            {
                "_index": "vocab",
                "_id": "b",
                "found": True,
                "_source": _source("B", relations=[{"type": "third", "target_id": "z"}]),
            },
        ]
    }

    relations = await es.adapter().fetch_relations(["b", "a"])

    assert [
        (relation.source_document_id, relation.relation_type, relation.target_id)
        for relation in relations
    ] == [("b", "third", "z"), ("a", "first", "x"), ("a", "second", "y")]
    assert [request.url.path for request in es.requests].count("/vocab/_mget") == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "second_identity",
    [
        ("renamed-vocab", "uuid-1", _mapping()),
        ("vocab", "uuid-2", _mapping()),
        ("vocab", "uuid-1", _mapping(canonical_type="text")),
    ],
)
async def test_index_identity_pins_then_detects_each_drift_dimension(
    es: EsHarness,
    second_identity: tuple[str, str, JsonObject],
) -> None:
    es.identity_versions = [
        ("vocab", "uuid-1", _mapping()),
        second_identity,
    ]
    adapter = es.adapter()

    identity = await adapter.index_identity()
    with pytest.raises(OntologyDriftError, match="identity changed"):
        await adapter.index_identity()

    assert identity.index_name == "vocab"
    assert identity.index_uuid == "uuid-1"
    assert len(identity.mapping_sha256) == 64


@pytest.mark.asyncio
async def test_data_method_checks_pinned_identity_before_search(es: EsHarness) -> None:
    es.identity_versions = [
        ("vocab", "uuid-1", _mapping()),
        ("vocab", "uuid-2", _mapping()),
    ]
    adapter = es.adapter()
    await adapter.index_identity()

    with pytest.raises(OntologyDriftError):
        await adapter.resolve_terms(["triangle"])

    assert not any(request.url.path == "/vocab/_search" for request in es.requests)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("health", "message"),
    [
        ({"cluster_name": "cluster", "status": "red", "timed_out": False}, "red"),
        ({"cluster_name": "cluster", "status": "yellow", "timed_out": True}, "timed out"),
    ],
)
async def test_red_or_timed_out_health_is_unavailable(
    es: EsHarness,
    health: JsonObject,
    message: str,
) -> None:
    es.health_response = health

    with pytest.raises(OntologyUnavailableError, match=message):
        await es.adapter().health()


@pytest.mark.asyncio
async def test_health_projects_a_real_elasticsearch_response(es: EsHarness) -> None:
    es.health_response = {
        "cluster_name": "unit-cluster",
        "status": "green",
        "timed_out": False,
        "number_of_nodes": 3,
        "number_of_data_nodes": 2,
        "active_primary_shards": 5,
        "active_shards": 10,
        "relocating_shards": 0,
        "initializing_shards": 0,
        "unassigned_shards": 0,
        "delayed_unassigned_shards": 0,
        "number_of_pending_tasks": 0,
        "number_of_in_flight_fetch": 0,
        "task_max_waiting_in_queue_millis": 0,
        "active_shards_percent_as_number": 100.0,
    }

    health = await es.adapter().health()

    assert health.model_dump() == {
        "cluster_name": "unit-cluster",
        "status": "green",
        "timed_out": False,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 403])
async def test_authentication_http_status_is_typed(es: EsHarness, status: int) -> None:
    es.statuses[("GET", "/_cat/indices/vocab")] = status

    with pytest.raises(OntologyAuthenticationError) as exc_info:
        await es.adapter().index_identity()

    assert "unit-secret-value" not in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [429, 500, 503])
async def test_transient_http_status_is_unavailable(es: EsHarness, status: int) -> None:
    es.statuses[("GET", "/_cat/indices/vocab")] = status

    with pytest.raises(OntologyUnavailableError):
        await es.adapter().index_identity()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    [
        httpx.ConnectError("simulated connection failure"),
        httpx.ReadTimeout("simulated timeout"),
    ],
)
async def test_transport_failure_is_not_a_term_miss(
    es: EsHarness,
    failure: httpx.TransportError,
) -> None:
    es.failure = failure

    with pytest.raises(OntologyUnavailableError):
        await es.adapter().resolve_terms(["triangle"])


@pytest.mark.asyncio
async def test_missing_index_and_document_are_not_found(es: EsHarness) -> None:
    es.statuses[("GET", "/_cat/indices/vocab")] = 404
    with pytest.raises(OntologyNotFoundError):
        await es.adapter().index_identity()

    other = EsHarness()
    other.mget_response = {"docs": [{"_index": "vocab", "_id": "missing", "found": False}]}
    with pytest.raises(OntologyNotFoundError, match="missing"):
        await other.adapter().fetch_terms(["missing"])


@pytest.mark.asyncio
async def test_invalid_json_mapping_and_search_shapes_are_schema_failures(es: EsHarness) -> None:
    es.invalid_json_paths.add("/vocab/_mapping")
    with pytest.raises(OntologySchemaError, match="JSON"):
        await es.adapter().index_identity()

    invalid_mapping = EsHarness()
    invalid_mapping.identity_versions = [("vocab", "uuid-1", _mapping(canonical_type="object"))]
    with pytest.raises(OntologySchemaError, match="term"):
        await invalid_mapping.adapter().index_identity()

    invalid_search = EsHarness()
    invalid_search.search_responses = [{"hits": {"hits": "not-a-list"}}]
    with pytest.raises(OntologySchemaError, match="hits"):
        await invalid_search.adapter().resolve_terms(["triangle"])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "hit",
    [
        _hit("missing-field", {"term": "triangle", "type": "concept", "aliases": []}),
        _hit("bad-alias", _source("triangle", aliases=["ok", 7])),
        _hit("bad-relation", _source("triangle", relations=[{"type": "parent"}])),
        _hit("nan-score", _source("triangle"), score=float("nan")),
    ],
)
async def test_malformed_hits_are_schema_failures(es: EsHarness, hit: JsonObject) -> None:
    es.search_responses = [_search_response([hit])]

    with pytest.raises(OntologySchemaError):
        await es.adapter().resolve_terms(["triangle"])


@pytest.mark.asyncio
async def test_duplicate_search_document_ids_are_schema_failure(es: EsHarness) -> None:
    es.search_responses = [
        _search_response(
            [
                _hit("duplicate", _source("triangle")),
                _hit("duplicate", _source("different")),
            ]
        )
    ]

    with pytest.raises(OntologySchemaError, match="duplicate"):
        await es.adapter().resolve_terms(["triangle"])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "surface_terms",
    [[""], [" \t "], ["valid", 3]],
)
async def test_invalid_surface_inputs_fail_before_http(
    es: EsHarness,
    surface_terms: list[Any],
) -> None:
    with pytest.raises(OntologyError):
        await es.adapter().resolve_terms(surface_terms)

    assert es.requests == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "document_ids",
    [[""], [" \t"], ["duplicate", "duplicate"], ["valid", 3]],
)
async def test_invalid_mget_ids_fail_before_http(es: EsHarness, document_ids: list[Any]) -> None:
    with pytest.raises(OntologyError):
        await es.adapter().fetch_terms(document_ids)

    assert es.requests == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("endpoint", "ftp://es.test.invalid"),
        ("endpoint", "not-a-url"),
        ("index", "two,indices"),
        ("index", "wild*card"),
        ("index", "wild?card"),
        ("index", "_all"),
        ("index", "path/segment"),
        ("index", ".."),
    ],
)
def test_connection_rejects_non_concrete_http_contract(field: str, value: str) -> None:
    values: JsonObject = {
        "endpoint": "https://es.test.invalid",
        "index": "vocab",
        "api_key": "unit-secret-value",
        "timeout_seconds": 1,
        "fields": FIELDS,
        "roles": ROLES,
    }
    values[field] = value

    with pytest.raises(ValidationError):
        ElasticsearchConnection.model_validate(values)


def test_connection_redacts_secret_and_builds_from_settings(
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KE_MEMORY_ES_URL", "https://es.test.invalid/")
    monkeypatch.setenv("KE_MEMORY_ES_INDEX", "vocab")
    monkeypatch.setenv("KE_MEMORY_ES_API_KEY", "settings-secret-value")

    connection = ElasticsearchConnection.from_app_settings(load_settings(project_root))

    assert connection.endpoint == "https://es.test.invalid"
    assert connection.api_key.get_secret_value() == "settings-secret-value"
    assert "settings-secret-value" not in repr(connection)
    assert "settings-secret-value" not in connection.model_dump_json()
    assert "api_key" not in connection.model_dump()


@pytest.mark.parametrize("api_key", ["", "header-secret\nInjected: value", "header-secret\rvalue"])
def test_adapter_rejects_invalid_api_key_without_echoing_it(api_key: str) -> None:
    connection = _connection(api_key=api_key)

    with pytest.raises(OntologyError, match="API key") as exc_info:
        ElasticsearchVocabulary(connection)

    if api_key:
        assert api_key not in str(exc_info.value)


@pytest.mark.asyncio
async def test_adapter_url_encodes_index_as_one_segment() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/_cat/indices/vocab name":
            return httpx.Response(200, json=[{"index": "vocab name", "uuid": "uuid"}])
        return httpx.Response(200, json={"vocab name": _mapping()["vocab"]})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = ElasticsearchVocabulary(_connection(index="vocab name"), client=client)

    await adapter.index_identity()

    assert requests[0].url.raw_path.startswith(b"/_cat/indices/vocab%20name")
    assert requests[1].url.raw_path == b"/vocab%20name/_mapping"


@pytest.mark.asyncio
async def test_context_manager_closes_injected_client_idempotently(es: EsHarness) -> None:
    adapter = es.adapter()

    async with adapter as entered:
        assert entered is adapter
        assert not es.client.is_closed

    assert es.client.is_closed
    await adapter.aclose()
    assert es.client.is_closed
    with pytest.raises(OntologyError, match="closed"):
        await adapter.health()
