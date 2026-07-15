from __future__ import annotations

import json
from typing import Any, cast

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from ke_memory_demo.domain import (
    OntologyBinding,
    OntologyBindingStatus,
    OntologyRelationRef,
    OntologyRole,
)
from ke_memory_demo.ontology import (
    ElasticsearchConnection,
    ElasticsearchVocabulary,
    OntologyError,
    OntologyHealth,
    OntologyRelation,
    OntologyTerm,
    OntologyVocabulary,
)
from ke_memory_demo.settings import ElasticsearchFields, ElasticsearchRoles


JsonObject = dict[str, Any]


def _connection() -> ElasticsearchConnection:
    return ElasticsearchConnection(
        endpoint="https://es.test.invalid",
        index="vocab",
        api_key=SecretStr("contract-secret-value"),
        timeout_seconds=1,
        fields=ElasticsearchFields(
            canonical="term",
            type="type",
            aliases="aliases",
            relations="relations",
            relation_type="type",
            relation_target_id="target_id",
        ),
        roles=ElasticsearchRoles(
            concept=("concept",),
            individual=("individual",),
            operator=("operator",),
        ),
    )


def _mapping() -> JsonObject:
    return {
        "vocab": {
            "mappings": {
                "properties": {
                    "term": {"type": "keyword"},
                    "type": {"type": "keyword"},
                    "aliases": {"type": "keyword"},
                    "relations": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "keyword"},
                            "target_id": {"type": "keyword"},
                        },
                    },
                }
            }
        }
    }


@pytest.mark.asyncio
async def test_protocol_conformance_and_only_five_allowlisted_request_shapes() -> None:
    observed: list[tuple[str, str, bytes]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        observed.append((request.method, request.url.path, request.url.query))
        payload: object
        if request.url.path == "/_cluster/health":
            payload = {
                "cluster_name": "contract-cluster",
                "status": "yellow",
                "timed_out": False,
            }
        elif request.url.path == "/_cat/indices/vocab":
            payload = [{"index": "vocab", "uuid": "contract-uuid"}]
        elif request.url.path == "/vocab/_mapping":
            payload = _mapping()
        elif request.url.path == "/vocab/_search":
            payload = {
                "took": 1,
                "timed_out": False,
                "_shards": {"total": 1, "successful": 1, "skipped": 0, "failed": 0},
                "hits": {"total": {"value": 0, "relation": "eq"}, "hits": []},
            }
        elif request.url.path == "/vocab/_mget":
            raw_ids = cast(JsonObject, json.loads(request.content))["ids"]
            assert isinstance(raw_ids, list)
            ids = cast(list[str], raw_ids)
            payload = cast(
                object,
                {
                    "docs": [
                        {
                            "_index": "vocab",
                            "_id": document_id,
                            "found": True,
                            "_source": {
                                "term": document_id,
                                "type": "concept",
                                "aliases": [],
                                "relations": [],
                            },
                        }
                        for document_id in ids
                    ]
                },
            )
        else:
            raise AssertionError(f"non-allowlisted request reached transport: {request.url}")
        return httpx.Response(200, json=payload, request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = ElasticsearchVocabulary(_connection(), client=client)

    assert isinstance(adapter, OntologyVocabulary)
    assert (await adapter.health()).status == "yellow"
    await adapter.index_identity()
    await adapter.resolve_terms(["missing"])
    await adapter.fetch_terms(["one"])
    await adapter.fetch_relations(["two"])

    assert {(method, path) for method, path, _ in observed} == {
        ("GET", "/_cluster/health"),
        ("GET", "/_cat/indices/vocab"),
        ("GET", "/vocab/_mapping"),
        ("POST", "/vocab/_search"),
        ("POST", "/vocab/_mget"),
    }
    assert all(
        forbidden not in path
        for _, path, _ in observed
        for forbidden in ("_bulk", "_doc", "_update", "_delete_by_query")
    )
    assert not any(
        hasattr(adapter, name)
        for name in ("bulk", "create", "delete", "index", "update", "delete_by_query")
    )


@pytest.mark.asyncio
async def test_central_allowlist_rejects_write_before_transport() -> None:
    reached_transport = False

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal reached_transport
        reached_transport = True
        return httpx.Response(200, json={}, request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = ElasticsearchVocabulary(_connection(), client=client)
    request = getattr(adapter, "_request")

    with pytest.raises(OntologyError, match="not allowlisted"):
        await request("DELETE", "/vocab/_doc/anything")

    assert not reached_transport


def test_public_models_are_frozen_extra_forbidding_and_sequences_are_immutable() -> None:
    health = OntologyHealth(cluster_name="cluster", status="green", timed_out=False)
    relation = OntologyRelation(
        source_document_id="child",
        relation_type="parent",
        target_id="root",
    )
    term = OntologyTerm.model_validate(
        {
            "document_id": "child",
            "canonical_term": "Child",
            "source_type": "concept",
            "role": "concept",
            "aliases": ["kid"],
            "relations": [relation],
        }
    )

    assert health.status == "green"
    assert term.aliases == ("kid",)
    assert term.relations == (relation,)
    with pytest.raises(ValidationError):
        OntologyHealth.model_validate(
            {"cluster_name": "cluster", "status": "green", "timed_out": False, "extra": True}
        )
    with pytest.raises(ValidationError):
        term.canonical_term = "Changed"


def test_task_two_binding_schema_is_reused_without_competition() -> None:
    binding = OntologyBinding(
        surface_form="child",
        normalized_surface="child",
        status=OntologyBindingStatus.RESOLVED,
        document_id="child",
        canonical_term="Child",
        role=OntologyRole.CONCEPT,
        source_type="concept",
        relations=(OntologyRelationRef(relation_type="parent", target_id="root"),),
    )

    assert isinstance(binding, OntologyBinding)
    assert isinstance(binding.relations[0], OntologyRelationRef)
