from __future__ import annotations

import importlib
from typing import Any

import pytest

from tools.natural_memory_benchmark.authoritative_memory import canonical_sha256
from tools.natural_memory_benchmark.query_compiler_v2 import (
    CompilerRegistryV1,
    GitMemoryViewRefV1,
    PredicateRegistryEntryV1,
    QueryDraftRequestV1,
    QueryDraftV1,
)
from tools.natural_memory_benchmark.query_plan_v2_executor import (
    QueryExecutionAuthorityV1,
    QueryExecutionResultV3,
    QueryExecutionSnapshotV1,
    QuerySnapshotEvaluationV1,
)


def _module() -> Any:
    try:
        return importlib.import_module("tools.natural_memory_benchmark.query_runtime")
    except ModuleNotFoundError:
        pytest.fail("query_runtime module is missing")


def _memory_view() -> GitMemoryViewRefV1:
    return GitMemoryViewRefV1(
        workspace_id="workspace-1",
        repository_epoch_id="epoch-1",
        checkpoint_id="checkpoint-1",
        git_commit="a" * 40,
    )


def _registry() -> CompilerRegistryV1:
    return CompilerRegistryV1(
        ontology_revision="ontology-v1",
        identity_revision="identity-v1",
        registry_revision="registry-v1",
        identity_snapshot_id="identity-snapshot-v1",
        identity_input_fingerprint="b" * 64,
        entity_aliases={"user": ["entity-user"]},
        entity_types={
            "entity-user": ["Person"],
            "project-1": ["Project"],
        },
        identity_status={
            "entity-user": "resolved",
            "project-1": "resolved",
        },
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


def _snapshot(registry: CompilerRegistryV1) -> QueryExecutionSnapshotV1:
    return QueryExecutionSnapshotV1(
        bundle_id="bundle-1",
        memory_view=_memory_view(),
        ontology_revision=registry.ontology_revision,
        identity_revision=registry.identity_revision,
        registry_revision=registry.registry_revision,
        registry_sha256=registry.registry_sha256,
        facts=[],
        identity_status={"entity-user": "resolved", "project-1": "resolved"},
        canonical_entity_ids={
            "entity-user": "entity-user",
            "project-1": "project-1",
        },
        identity_snapshot_id=registry.identity_snapshot_id,
        identity_input_fingerprint=registry.identity_input_fingerprint,
    )


def _draft(query_id: str, *, predicate: str = "led") -> QueryDraftV1:
    return QueryDraftV1.model_validate(
        {
            "query_id": query_id,
            "intent": "fact_lookup",
            "target_level": "L1",
            "answer": {"kind": "fact", "variable": "?project"},
            "pattern_groups": [
                {
                    "group_id": "group-1",
                    "atoms": [
                        {
                            "atom_id": "atom-1",
                            "predicate_surface": predicate,
                            "roles": [
                                {
                                    "role": "ARG0",
                                    "role_name": "leader",
                                    "term": {
                                        "kind": "entity_surface",
                                        "value": "user",
                                        "expected_type": "Person",
                                    },
                                },
                                {
                                    "role": "ARG1",
                                    "role_name": "project",
                                    "term": {
                                        "kind": "variable",
                                        "value": "?project",
                                        "expected_type": "Project",
                                    },
                                },
                            ],
                        }
                    ],
                }
            ],
            "lifecycle": "active",
            "source_status_constraints": ["user_reported"],
            "conflict_policy": "require_resolved",
            "supersession_policy": "current_only",
            "evidence_policy": "provenance_closure",
            "producer_id": "test-producer",
            "producer_version": "v1",
        }
    )


class _Producer:
    def __init__(self, *, predicate: str = "led") -> None:
        self.predicate = predicate
        self.requests: list[QueryDraftRequestV1] = []

    def produce(self, request: QueryDraftRequestV1) -> QueryDraftV1:
        self.requests.append(request)
        return _draft(request.query_id, predicate=self.predicate)


def _execution_result(plan: Any, snapshot: QueryExecutionSnapshotV1) -> QueryExecutionResultV3:
    evaluation = QuerySnapshotEvaluationV1(
        query_id=plan.query_id,
        plan_sha256=plan.plan_sha256,
        matched_fact_ids=("fact-1",),
        answer_values=("project-1",),
        required_evidence_ids=("evidence-1",),
        closure_complete=True,
        abstained=False,
        reason="compiled_query_complete",
    )
    authority_payload = {
        "memory_view": snapshot.memory_view,
        "bundle_id": snapshot.bundle_id,
        "bundle_history_artifact_sha256": "c" * 64,
        "registry_sha256": snapshot.registry_sha256,
        "identity_snapshot_id": snapshot.identity_snapshot_id,
        "identity_input_fingerprint": snapshot.identity_input_fingerprint,
        "snapshot_sha256": canonical_sha256(snapshot),
        "plan_sha256": plan.plan_sha256,
        "evaluation_sha256": canonical_sha256(evaluation),
    }
    authority = QueryExecutionAuthorityV1(
        **authority_payload,
        authority_sha256=canonical_sha256(
            {
                "schema_version": "query-execution-authority-v1",
                **{
                    key: value.model_dump(mode="json")
                    if key == "memory_view"
                    else value
                    for key, value in authority_payload.items()
                },
            }
        ),
    )
    return QueryExecutionResultV3(evaluation=evaluation, authority=authority)


def _request(module: Any) -> Any:
    return module.NaturalQueryExecutionRequestV1(
        question="Which projects has user led?",
        query_id="query-1",
        query_time="2026-07-30T00:00:00Z",
        current_user_entity_id="entity-user",
        compiler_policy_revision="query-policy-v2",
    )


def test_execute_natural_query_compiles_against_verified_snapshot_and_executes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    registry = _registry()
    snapshot = _snapshot(registry)
    producer = _Producer()
    captured: dict[str, object] = {}

    monkeypatch.setattr(module, "build_query_execution_snapshot", lambda **_kwargs: snapshot)

    def execute(**kwargs: object) -> QueryExecutionResultV3:
        captured.update(kwargs)
        return _execution_result(kwargs["plan"], snapshot)

    monkeypatch.setattr(module, "execute_authoritative_query", execute)
    outcome = module.execute_natural_query(
        request=_request(module),
        repository_path="memory.git",
        bundle=object(),
        bundle_history_artifact=object(),
        turn_bundles=(),
        registry=registry,
        producer=producer,
        identity_snapshot_id=registry.identity_snapshot_id,
    )

    assert outcome.status == "executed"
    assert outcome.compilation.status == "executable"
    assert outcome.execution is not None
    assert outcome.execution.answer_values == ("project-1",)
    assert captured["plan"].memory_view == snapshot.memory_view
    assert producer.requests[0].raw_query == _request(module).question


def test_execute_natural_query_returns_compile_abstention_without_executor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    registry = _registry()
    monkeypatch.setattr(
        module,
        "build_query_execution_snapshot",
        lambda **_kwargs: _snapshot(registry),
    )
    monkeypatch.setattr(
        module,
        "execute_authoritative_query",
        lambda **_kwargs: pytest.fail("executor must not run after compile abstention"),
    )

    outcome = module.execute_natural_query(
        request=_request(module),
        repository_path="memory.git",
        bundle=object(),
        bundle_history_artifact=object(),
        turn_bundles=(),
        registry=registry,
        producer=_Producer(predicate="unknown predicate"),
        identity_snapshot_id=registry.identity_snapshot_id,
    )

    assert outcome.status == "compile_abstained"
    assert outcome.compilation.status == "abstain"
    assert outcome.compilation.fallback_reason == "lexical_predicate_missing_link"
    assert outcome.execution is None


def test_execute_natural_query_fails_before_model_when_snapshot_verification_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    registry = _registry()
    producer = _Producer()

    def fail_snapshot(**_kwargs: object) -> QueryExecutionSnapshotV1:
        raise ValueError("memory history verification failed")

    monkeypatch.setattr(module, "build_query_execution_snapshot", fail_snapshot)

    with pytest.raises(ValueError, match="memory history verification failed"):
        module.execute_natural_query(
            request=_request(module),
            repository_path="memory.git",
            bundle=object(),
            bundle_history_artifact=object(),
            turn_bundles=(),
            registry=registry,
            producer=producer,
            identity_snapshot_id=registry.identity_snapshot_id,
        )

    assert producer.requests == []
