from __future__ import annotations

import importlib
import json
from typing import Any

import pytest

from tools.natural_memory_benchmark.query_compiler_v2 import (
    CompilerRegistryV1,
    PredicateRegistryEntryV1,
    QueryDraftRequestV1,
)


API_KEY = "unit-test-secret-key"


def _module() -> Any:
    try:
        return importlib.import_module(
            "tools.natural_memory_benchmark.query_compiler_v2_openai_producer"
        )
    except ModuleNotFoundError:
        pytest.fail("query_compiler_v2_openai_producer module is missing")


def _registry() -> CompilerRegistryV1:
    return CompilerRegistryV1(
        ontology_revision="ontology-v1",
        identity_revision="identity-v1",
        registry_revision="registry-v1",
        identity_snapshot_id="identity-snapshot-v1",
        identity_input_fingerprint="a" * 64,
        entity_aliases={"user": ["entity-user"]},
        entity_types={"entity-user": ["Person"]},
        identity_status={"entity-user": "resolved"},
        predicate_aliases={
            "led": [
                PredicateRegistryEntryV1(
                    sense="lead/manage",
                    canonical_operator="led_by",
                    role_types={"ARG0": "Person", "ARG1": "Project"},
                )
            ]
        },
    )


def _request() -> QueryDraftRequestV1:
    return QueryDraftRequestV1(
        raw_query="Which projects has user led?",
        query_id="query-1",
        query_time="2026-07-30T00:00:00Z",
        current_user_surface="I",
        compiler_policy_revision="query-policy-v2",
    )


def _draft_payload() -> dict[str, object]:
    return {
        "schema_version": "natural-query-draft-v1",
        "query_id": "query-1",
        "intent": "fact_lookup",
        "target_level": "L1",
        "answer": {
            "schema_version": "query-answer-draft-v1",
            "kind": "fact",
            "variable": "?project",
            "distinct_by": None,
        },
        "pattern_groups": [
            {
                "schema_version": "query-pattern-group-draft-v1",
                "group_id": "group-1",
                "atoms": [
                    {
                        "schema_version": "query-atom-draft-v1",
                        "atom_id": "atom-1",
                        "predicate_surface": "led",
                        "roles": [
                            {
                                "schema_version": "query-role-draft-v1",
                                "role": "ARG0",
                                "role_name": "leader",
                                "term": {
                                    "schema_version": "query-term-draft-v1",
                                    "kind": "entity_surface",
                                    "value": "user",
                                    "expected_type": "Person",
                                },
                            },
                            {
                                "schema_version": "query-role-draft-v1",
                                "role": "ARG1",
                                "role_name": "project",
                                "term": {
                                    "schema_version": "query-term-draft-v1",
                                    "kind": "variable",
                                    "value": "?project",
                                    "expected_type": "Project",
                                },
                            },
                        ],
                        "modality": None,
                        "polarity": None,
                    }
                ],
            }
        ],
        "time_constraints": [],
        "lifecycle": "active",
        "source_status_constraints": ["user_reported"],
        "conflict_policy": "require_resolved",
        "supersession_policy": "current_only",
        "evidence_policy": "provenance_closure",
        "explicit_absence_requested": False,
        "producer_id": "deepseek-query-draft",
        "producer_version": "v1",
    }


class _Response:
    def __init__(self, payload: dict[str, object]) -> None:
        self._bytes = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._bytes


def _response(content: str) -> _Response:
    return _Response(
        {
            "model": "deepseek-chat",
            "choices": [{"message": {"content": content}}],
        }
    )


def test_producer_returns_strict_typed_draft_without_putting_key_in_body() -> None:
    module = _module()
    request_bodies: list[bytes] = []

    def opener(request: Any, *, timeout: int) -> _Response:
        assert timeout == 17
        request_bodies.append(request.data)
        return _response(json.dumps(_draft_payload()))

    producer = module.OpenAICompatibleQueryDraftProducer(
        registry=_registry(),
        base_url="https://api.example.invalid/v1",
        api_key=API_KEY,
        model="deepseek-chat",
        timeout_seconds=17,
        opener=opener,
    )

    draft = producer.produce(_request())

    assert draft.query_id == "query-1"
    assert draft.pattern_groups[0].atoms[0].predicate_surface == "led"
    assert len(request_bodies) == 1
    assert API_KEY.encode("utf-8") not in request_bodies[0]


def test_request_exposes_only_executable_answer_kinds() -> None:
    module = _module()
    request_bodies: list[bytes] = []

    def opener(request: Any, *, timeout: int) -> _Response:
        request_bodies.append(request.data)
        return _response(json.dumps(_draft_payload()))

    producer = module.OpenAICompatibleQueryDraftProducer(
        registry=_registry(),
        base_url="https://api.example.invalid/v1",
        api_key=API_KEY,
        model="deepseek-v4-flash",
        opener=opener,
    )

    producer.produce(
        _request().model_copy(
            update={"raw_query": "What beverage is preferred?"}
        )
    )

    request_payload = json.loads(request_bodies[0])
    public_input = json.loads(request_payload["messages"][1]["content"])
    response_schema = public_input["response_schema"]
    answer_ref = response_schema["properties"]["answer"]["$ref"]
    answer_schema = response_schema["$defs"][answer_ref.rsplit("/", 1)[-1]]
    assert answer_schema["properties"]["kind"]["enum"] == ["fact", "count"]
    assert public_input["operational_contract"]["answer_kind"] == {
        "supported": ["fact", "count"],
        "entity_valued_what_which": "fact",
        "explicit_count_or_how_many": "count",
    }


def test_producer_rejects_answer_kind_outside_operational_contract() -> None:
    module = _module()
    payload = _draft_payload()
    answer = payload["answer"]
    assert isinstance(answer, dict)
    answer["kind"] = "entity_list"
    producer = module.OpenAICompatibleQueryDraftProducer(
        registry=_registry(),
        base_url="https://api.example.invalid/v1",
        api_key=API_KEY,
        model="deepseek-v4-flash",
        opener=lambda *_args, **_kwargs: _response(json.dumps(payload)),
        max_attempts=1,
    )

    with pytest.raises(module.QueryDraftProductionError, match="invalid response"):
        producer.produce(_request())


def test_producer_rejects_non_json_model_content() -> None:
    module = _module()
    producer = module.OpenAICompatibleQueryDraftProducer(
        registry=_registry(),
        base_url="https://api.example.invalid/v1",
        api_key=API_KEY,
        model="deepseek-chat",
        opener=lambda *_args, **_kwargs: _response("```json\\n{}\\n```"),
        max_attempts=1,
    )

    with pytest.raises(module.QueryDraftProductionError, match="invalid response"):
        producer.produce(_request())


def test_timeout_retries_once_and_terminal_error_redacts_credentials() -> None:
    module = _module()
    attempts = 0

    def opener(*_args: object, **_kwargs: object) -> _Response:
        nonlocal attempts
        attempts += 1
        raise TimeoutError(f"timed out with {API_KEY}")

    producer = module.OpenAICompatibleQueryDraftProducer(
        registry=_registry(),
        base_url="https://api.example.invalid/v1",
        api_key=API_KEY,
        model="deepseek-chat",
        opener=opener,
        max_attempts=2,
    )

    with pytest.raises(module.QueryDraftProductionError) as captured:
        producer.produce(_request())

    assert attempts == 2
    assert API_KEY not in str(captured.value)
    assert captured.value.__cause__ is None
