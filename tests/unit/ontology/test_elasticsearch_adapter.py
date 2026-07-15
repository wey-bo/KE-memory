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
    fields: ElasticsearchFields = FIELDS,
) -> ElasticsearchConnection:
    return ElasticsearchConnection(
        endpoint=endpoint,
        index=index,
        api_key=SecretStr(api_key),
        timeout_seconds=2.5,
        fields=fields,
        roles=ROLES,
    )


def _mapping(
    *,
    canonical_type: str = "keyword",
    aliases_type: str = "keyword",
    keyword_multifields: bool = False,
) -> JsonObject:
    canonical_mapping: JsonObject = {"type": canonical_type}
    aliases_mapping: JsonObject = {"type": aliases_type}
    if keyword_multifields:
        canonical_mapping["fields"] = {"raw": {"type": "keyword"}}
        aliases_mapping["fields"] = {"raw": {"type": "keyword"}}
    return {
        "vocab": {
            "mappings": {
                "properties": {
                    "term": canonical_mapping,
                    "type": {"type": "keyword"},
                    "aliases": aliases_mapping,
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


DOTTED_FIELDS = ElasticsearchFields(
    canonical="ontology.labels.term",
    type="ontology.kind",
    aliases="ontology.labels.aliases",
    relations="ontology.links",
    relation_type="meta.kind",
    relation_target_id="target.id",
)


def _dotted_mapping() -> JsonObject:
    return {
        "vocab": {
            "mappings": {
                "properties": {
                    "ontology": {
                        "type": "object",
                        "properties": {
                            "labels": {
                                "type": "object",
                                "properties": {
                                    "term": {
                                        "type": "text",
                                        "fields": {"raw": {"type": "keyword"}},
                                    },
                                    "aliases": {"type": "keyword"},
                                },
                            },
                            "kind": {"type": "keyword"},
                            "links": {
                                "type": "nested",
                                "properties": {
                                    "meta": {
                                        "type": "object",
                                        "properties": {"kind": {"type": "keyword"}},
                                    },
                                    "target": {
                                        "type": "object",
                                        "properties": {"id": {"type": "keyword"}},
                                    },
                                },
                            },
                        },
                    }
                }
            }
        }
    }


def _dotted_source() -> JsonObject:
    return {
        "ontology": {
            "labels": {"term": "Triangle", "aliases": ["Tri"]},
            "kind": "concept",
            "links": [
                {
                    "meta": {"kind": "broader"},
                    "target": {"id": "shape"},
                }
            ],
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
        self.cat_identities: list[tuple[str, str]] | None = None
        self.statuses: dict[tuple[str, str], int] = {}
        self.invalid_json_paths: set[str] = set()
        self.failure: Exception | None = None
        self._cat_call = 0
        self._mapping_call = 0
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
            if self.cat_identities is None:
                index_name, index_uuid, _ = self.identity_versions[
                    min(self._mapping_call, len(self.identity_versions) - 1)
                ]
            else:
                index_name, index_uuid = self.cat_identities[
                    min(self._cat_call, len(self.cat_identities) - 1)
                ]
            self._cat_call += 1
            payload = [{"index": index_name, "uuid": index_uuid}]
        elif request.method == "GET" and path == "/vocab/_mapping":
            _, _, payload = self.identity_versions[
                min(self._mapping_call, len(self.identity_versions) - 1)
            ]
            self._mapping_call += 1
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

    def adapter(
        self,
        connection: ElasticsearchConnection | None = None,
    ) -> ElasticsearchVocabulary:
        return ElasticsearchVocabulary(connection or _connection(), client=self.client)


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
        ("GET", "/_cat/indices/vocab"),
        ("POST", "/vocab/_search"),
        ("POST", "/vocab/_search"),
        ("POST", "/vocab/_search"),
    ]
    assert es.requests[0].url.query == b"format=json"
    exact_body = json.loads(es.requests[3].content)
    assert exact_body == {
        "_source": ["term", "type", "aliases", "relations"],
        "query": {
            "bool": {
                "minimum_should_match": 1,
                "should": [
                    {"term": {"term": {"value": "triangle", "case_insensitive": True}}},
                    {"term": {"aliases": {"value": "triangle", "case_insensitive": True}}},
                ],
            }
        },
        "size": 100,
        "sort": [{"_score": {"order": "desc"}}],
        "track_total_hits": False,
    }
    second_exact_body = json.loads(es.requests[4].content)
    assert "unknown phrase" in json.dumps(second_exact_body)
    assert "triangle" not in json.dumps(second_exact_body)
    lexical_body = json.loads(es.requests[5].content)
    assert lexical_body["query"]["bool"]["should"] == [
        {
            "wildcard": {
                "term": {
                    "value": "*unknown*phrase*",
                    "case_insensitive": True,
                }
            }
        },
        {
            "wildcard": {
                "aliases": {
                    "value": "*unknown*phrase*",
                    "case_insensitive": True,
                }
            }
        },
    ]
    assert all(
        request.headers["authorization"] == "ApiKey unit-secret-value" for request in es.requests
    )


@pytest.mark.asyncio
async def test_keyword_exact_queries_retrieve_case_insensitive_canonical_and_alias(
    es: EsHarness,
) -> None:
    es.search_responses = [
        _search_response([_hit("canonical", _source("TRIANGLE"), score=1.0)]),
        _search_response(
            [
                _hit(
                    "alias",
                    _source("three-sided polygon", aliases=["THREE SIDE"]),
                    score=1.0,
                )
            ]
        ),
    ]

    bindings = await es.adapter().resolve_terms(["TriAngle", "Three Side"])

    assert [binding.document_id for binding in bindings] == ["canonical", "alias"]
    search_requests = [request for request in es.requests if request.url.path == "/vocab/_search"]
    assert len(search_requests) == 2
    first_body = json.loads(search_requests[0].content)
    first_terms = first_body["query"]["bool"]["should"]
    assert {next(iter(clause["term"].values()))["value"] for clause in first_terms} == {
        "TriAngle",
        "triangle",
    }
    assert all(
        next(iter(clause["term"].values()))["case_insensitive"] is True for clause in first_terms
    )
    assert "Three Side" not in json.dumps(first_body)


@pytest.mark.asyncio
async def test_text_exact_query_uses_phrase_and_concrete_keyword_multifield(
    es: EsHarness,
) -> None:
    es.identity_versions = [
        (
            "vocab",
            "uuid-1",
            _mapping(
                canonical_type="text",
                aliases_type="text",
                keyword_multifields=True,
            ),
        )
    ]
    es.search_responses = [_search_response([_hit("new-york", _source("New York"), score=1.0)])]

    binding = (await es.adapter().resolve_terms(["new york"]))[0]

    assert binding.document_id == "new-york"
    body = json.loads(es.requests[-1].content)
    should = body["query"]["bool"]["should"]
    assert {
        next(iter(clause["match_phrase"])) for clause in should if "match_phrase" in clause
    } == {
        "term",
        "aliases",
    }
    assert {next(iter(clause["term"])) for clause in should if "term" in clause} == {
        "term.raw",
        "aliases.raw",
    }


@pytest.mark.asyncio
async def test_keyword_lexical_fallback_uses_case_insensitive_wildcards(
    es: EsHarness,
) -> None:
    es.search_responses = [
        _search_response([]),
        _search_response([_hit("triangular", _source("Triangular Shape"), score=2.0)]),
    ]

    binding = (await es.adapter().resolve_terms(["triang"]))[0]

    assert binding.document_id == "triangular"
    lexical = json.loads(es.requests[-1].content)
    clauses = lexical["query"]["bool"]["should"]
    assert {next(iter(clause["wildcard"])) for clause in clauses} == {"term", "aliases"}
    assert all(
        next(iter(clause["wildcard"].values()))
        == {
            "value": "*triang*",
            "case_insensitive": True,
        }
        for clause in clauses
    )


@pytest.mark.asyncio
async def test_each_surface_has_independent_scores_and_exact_ambiguity(
    es: EsHarness,
) -> None:
    es.search_responses = [
        _search_response([_hit("alpha", _source("alpha"), score=0.1)]),
        _search_response(
            [
                _hit("beta-b", _source("beta"), score=3.0),
                _hit("beta-a", _source("beta"), score=3.0),
            ]
        ),
    ]

    bindings = await es.adapter().resolve_terms(["alpha", "beta"])

    assert bindings[0].document_id == "alpha"
    assert bindings[1].status is OntologyBindingStatus.UNRESOLVED
    assert [request.url.path for request in es.requests].count("/vocab/_search") == 2
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
    assert len(body["query"]["bool"]["should"]) <= 100


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
async def test_dotted_mapping_and_source_paths_resolve_terms_and_relations(
    es: EsHarness,
) -> None:
    es.identity_versions = [("vocab", "uuid-1", _dotted_mapping())]
    es.search_responses = [_search_response([_hit("triangle", _dotted_source())])]
    connection = _connection(fields=DOTTED_FIELDS)

    binding = (await es.adapter(connection).resolve_terms(["triangle"]))[0]

    assert binding.document_id == "triangle"
    assert binding.canonical_term == "Triangle"
    assert binding.aliases == ("Tri",)
    assert binding.relations == (OntologyRelationRef(relation_type="broader", target_id="shape"),)
    body = json.loads(es.requests[-1].content)
    assert body["_source"] == [
        "ontology.labels.term",
        "ontology.kind",
        "ontology.labels.aliases",
        "ontology.links",
    ]
    should = body["query"]["bool"]["should"]
    assert any("ontology.labels.term" in clause.get("match_phrase", {}) for clause in should)
    assert any("ontology.labels.term.raw" in clause.get("term", {}) for clause in should)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source",
    [
        {"ontology": {"kind": "concept", "links": []}},
        {"ontology": "not-an-object"},
        {
            "ontology": {
                "labels": {"term": "Triangle", "aliases": "Tri"},
                "kind": "concept",
                "links": [],
            }
        },
        {
            "ontology": {
                "labels": {"term": "Triangle", "aliases": []},
                "kind": "concept",
                "links": [{"meta": "not-an-object", "target": {"id": "shape"}}],
            }
        },
    ],
)
async def test_dotted_source_missing_intermediate_and_type_errors_are_schema_failures(
    es: EsHarness,
    source: JsonObject,
) -> None:
    es.identity_versions = [("vocab", "uuid-1", _dotted_mapping())]
    es.search_responses = [_search_response([_hit("triangle", source)])]

    with pytest.raises(OntologySchemaError):
        await es.adapter(_connection(fields=DOTTED_FIELDS)).resolve_terms(["triangle"])


@pytest.mark.asyncio
async def test_dotted_mapping_missing_intermediate_is_a_schema_failure(es: EsHarness) -> None:
    mapping = _dotted_mapping()
    ontology = mapping["vocab"]["mappings"]["properties"]["ontology"]
    del ontology["properties"]["labels"]
    es.identity_versions = [("vocab", "uuid-1", mapping)]

    with pytest.raises(OntologySchemaError, match="ontology.labels.term"):
        await es.adapter(_connection(fields=DOTTED_FIELDS)).index_identity()


@pytest.mark.asyncio
async def test_multiple_surfaces_use_separate_capped_exact_and_lexical_searches(
    es: EsHarness,
) -> None:
    surfaces = ["first term", "second term", "third term"]
    es.search_responses = [_search_response([]) for _ in range(6)]

    bindings = await es.adapter().resolve_terms(surfaces)

    assert len(bindings) == 3
    search_bodies = [
        json.loads(request.content)
        for request in es.requests
        if request.url.path == "/vocab/_search"
    ]
    assert len(search_bodies) == 6
    assert all(1 <= body["size"] <= 100 for body in search_bodies)
    assert all(len(body["query"]["bool"]["should"]) <= 100 for body in search_bodies)
    for index, surface in enumerate(surfaces):
        matching_bodies = search_bodies[index * 2 : index * 2 + 2]
        assert surface in json.dumps(matching_bodies[0])
        assert f"*{surface.replace(' ', '*')}*" in json.dumps(matching_bodies[1])
        assert all(
            other not in json.dumps(body)
            for body in matching_bodies
            for other in surfaces
            if other != surface
        )


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
    second_name, second_uuid, _ = second_identity
    es.cat_identities = [
        ("vocab", "uuid-1"),
        ("vocab", "uuid-1"),
        (second_name, second_uuid),
        (second_name, second_uuid),
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
    es.cat_identities = [
        ("vocab", "uuid-1"),
        ("vocab", "uuid-1"),
        ("vocab", "uuid-2"),
        ("vocab", "uuid-2"),
    ]
    adapter = es.adapter()
    await adapter.index_identity()

    with pytest.raises(OntologyDriftError):
        await adapter.resolve_terms(["triangle"])

    assert not any(request.url.path == "/vocab/_search" for request in es.requests)


@pytest.mark.asyncio
async def test_first_identity_rejects_mapping_root_for_another_index(es: EsHarness) -> None:
    mapping = _mapping()
    mapping["other-index"] = mapping.pop("vocab")
    es.identity_versions = [("vocab", "uuid-1", mapping)]

    with pytest.raises(OntologySchemaError, match="mapping index name"):
        await es.adapter().index_identity()


@pytest.mark.asyncio
async def test_first_identity_rejects_cat_name_that_is_not_configured(es: EsHarness) -> None:
    es.cat_identities = [("other-index", "uuid-1")]

    with pytest.raises(OntologySchemaError, match="CAT index name"):
        await es.adapter().index_identity()


@pytest.mark.asyncio
async def test_identity_detects_cat_rollover_around_mapping_read(es: EsHarness) -> None:
    es.cat_identities = [
        ("vocab", "uuid-before"),
        ("vocab", "uuid-after"),
    ]

    with pytest.raises(OntologyDriftError, match="changed during mapping read"):
        await es.adapter().index_identity()

    assert [request.url.path for request in es.requests] == [
        "/_cat/indices/vocab",
        "/vocab/_mapping",
        "/_cat/indices/vocab",
    ]


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
async def test_redirect_is_not_followed_or_forwarded_authorization() -> None:
    requests: list[httpx.Request] = []
    secret = "redirect-secret-value"

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            302,
            headers={"location": "https://redirect.test.invalid/capture"},
            content=f"body contains {secret}".encode(),
            request=request,
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    )
    adapter = ElasticsearchVocabulary(_connection(api_key=secret), client=client)

    async with adapter:
        with pytest.raises(OntologyError) as exc_info:
            await adapter.health()

    assert type(exc_info.value) is OntologyError
    assert len(requests) == 1
    assert requests[0].url.host == "es.test.invalid"
    assert requests[0].headers["authorization"] == f"ApiKey {secret}"
    assert all(request.url.host != "redirect.test.invalid" for request in requests)
    assert secret not in str(exc_info.value)
    assert "body contains" not in str(exc_info.value)


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
    invalid_search_response = _search_response([])
    invalid_search_response["hits"]["hits"] = "not-a-list"
    invalid_search.search_responses = [invalid_search_response]
    with pytest.raises(OntologySchemaError, match="hits"):
        await invalid_search.adapter().resolve_terms(["triangle"])


@pytest.mark.asyncio
async def test_failed_search_shards_are_unavailable_without_detail_leak(es: EsHarness) -> None:
    secret_detail = "sensitive-shard-detail"
    response = _search_response([])
    response["_shards"]["failed"] = 1
    response["_shards"]["failures"] = [{"reason": secret_detail}]
    es.search_responses = [response]

    with pytest.raises(OntologyUnavailableError) as exc_info:
        await es.adapter().resolve_terms(["triangle"])

    assert secret_detail not in str(exc_info.value)
    assert "failure" not in str(exc_info.value).casefold()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "shards",
    [
        None,
        {"total": 1, "successful": 1, "skipped": 0},
        {"total": 1, "successful": 1, "skipped": 0, "failed": "0"},
    ],
)
async def test_malformed_search_shards_are_schema_failures(
    es: EsHarness,
    shards: object,
) -> None:
    response = _search_response([])
    response["_shards"] = shards
    es.search_responses = [response]

    with pytest.raises(OntologySchemaError, match="shards"):
        await es.adapter().resolve_terms(["triangle"])


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
