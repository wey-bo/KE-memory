from __future__ import annotations

from inspect import signature
from pathlib import Path

import pytest
from pydantic import ValidationError

from tools.natural_memory_benchmark.authoritative_memory import (
    ClaimClosureContext,
    ClosureEvaluationInputs,
    canonical_sha256,
    ClosureSlotSpec,
    L1MemoryUnitV2,
    L2MemoryUnitV2,
    L2StructuredClaim,
    MemoryRepresentationBundleV3,
    ProducerIdentity,
    SourceBindingV2,
    evaluate_closure_spec,
    make_closure_spec,
    make_evidence_span,
    make_memory_unit_revision,
    make_raw_artifact_revision,
    make_source_record_revision,
)
from tools.natural_memory_benchmark.git_memory_history import (
    GitMemoryHistoryRepository,
    HistoryArtifactReference,
    make_history_artifact,
    make_turn_bundle_history_artifact,
)
from tools.natural_memory_benchmark.identity_resolution import (
    IdentityAwareMemoryBundleV4,
    build_identity_snapshot,
)
from tools.natural_memory_benchmark.query_execution_snapshot_adapter import (
    build_query_execution_snapshot,
    execute_authoritative_query,
)
from tools.natural_memory_benchmark.query_plan_v2_executor import (
    QueryExecutionAuthorityV1,
    QueryExecutionResultV3,
)
from tools.natural_memory_benchmark.query_compiler_v2 import (
    AnswerDraftV1,
    CompilerRegistryV1,
    PredicateRegistryEntryV1,
    QueryAtomDraftV1,
    QueryContextV1,
    QueryDraftV1,
    QueryPatternGroupDraftV1,
    QueryRoleDraftV1,
    QueryTermDraftV1,
    compile_query_draft,
)
from tools.natural_memory_benchmark.representation_contract import (
    REQUIRED_MEMORY_CAPABILITIES,
    CapabilityDeclaration,
    RepresentationProfile,
)
from tools.natural_memory_benchmark.semantic_ir import (
    Predicate,
    RoleBinding,
    TimeBinding,
)
from tools.natural_memory_benchmark.turn_bundle import (
    TurnSourceRevisionRef,
    make_turn_bundle_revision,
)


def _profile() -> RepresentationProfile:
    return RepresentationProfile(
        representation_id="query-execution-adapter-test",
        family="semantic_ir",
        format_version="memory-representation-bundle-v3",
        role="authoritative_candidate",
        capabilities=[
            CapabilityDeclaration(
                capability=name,
                support_mode="native",
                location="test",
            )
            for name in REQUIRED_MEMORY_CAPABILITIES
        ],
    )


def _producer() -> ProducerIdentity:
    return ProducerIdentity(
        workflow_run_id="run-query-execution-adapter",
        producer_id="query-execution-adapter-test",
        producer_version="1",
    )


def _compiler_registry() -> CompilerRegistryV1:
    return CompilerRegistryV1(
        ontology_revision="ontology-v7",
        identity_revision="identity-v4",
        registry_revision="registry-v1",
        entity_aliases={"i": ["entity-user"]},
        entity_types={"entity-user": ["Person"]},
        identity_status={"entity-user": "resolved"},
        predicate_aliases={
            "lead": [
                PredicateRegistryEntryV1(
                    sense="lead/manage",
                    canonical_operator="manage",
                    role_types={"agent": "Person", "theme": "Project"},
                )
            ]
        },
    )


def _identity_bound_registry(snapshot) -> CompilerRegistryV1:
    payload = _compiler_registry().model_dump(
        mode="json",
        exclude={"registry_sha256"},
    )
    payload.update(
        {
            "identity_snapshot_id": snapshot.snapshot_id,
            "identity_input_fingerprint": snapshot.input_fingerprint,
        }
    )
    return CompilerRegistryV1.model_validate(payload)


def _compiled_plan(memory_view):
    draft = QueryDraftV1(
        query_id="query-adapter-1",
        intent="fact_lookup",
        target_level="both",
        answer=AnswerDraftV1(kind="fact", variable="?project"),
        pattern_groups=[
            QueryPatternGroupDraftV1(
                group_id="group-lead",
                atoms=[
                    QueryAtomDraftV1(
                        atom_id="atom-lead",
                        predicate_surface="lead",
                        roles=[
                            QueryRoleDraftV1(
                                role="agent",
                                role_name="ARG0",
                                term=QueryTermDraftV1(
                                    kind="entity_surface",
                                    value="i",
                                    expected_type="Person",
                                ),
                            ),
                            QueryRoleDraftV1(
                                role="theme",
                                role_name="ARG1",
                                term=QueryTermDraftV1(
                                    kind="variable",
                                    value="?project",
                                    expected_type="Project",
                                ),
                            ),
                        ],
                    )
                ],
            )
        ],
        source_status_constraints=["user_reported"],
        conflict_policy="require_resolved",
        supersession_policy="current_only",
        evidence_policy="provenance_closure",
        producer_id="adapter-query-test",
        producer_version="1",
    )
    context = QueryContextV1(
        query_id=draft.query_id,
        raw_query="Which project do I lead?",
        query_time="2026-07-28T00:01:00Z",
        current_user_entity_id="entity-user",
        memory_view=memory_view,
        ontology_revision="ontology-v7",
        identity_revision="identity-v4",
        compiler_policy_revision="query-policy-v1",
    )
    result = compile_query_draft(draft, context, _compiler_registry())
    assert result.plan is not None
    return result.plan


def _fixture(
    tmp_path: Path,
    *,
    payload_transaction_time: str = "2026-07-28T00:00:03Z",
    identity_scope: list[str] | None = None,
    bundle_artifact_logical_id: str | None = None,
):
    artifact = make_raw_artifact_revision(
        source_id="source-adapter",
        frozen_identity="fixture|adapter",
        official_url="https://example.test/adapter.json",
        local_path="artifacts/raw/adapter.json",
        reader="json",
        size_bytes=64,
        content_sha256="a" * 64,
    )
    user_source = make_source_record_revision(
        source_record_id="source-user",
        revision_number=1,
        previous_revision_id=None,
        artifact_revision_id=artifact.artifact_revision_id,
        source_ref="fixture=user",
        turn_id="turn-1",
        session_id="session-1",
        record_kind="message",
        text="I lead Project Alpha.",
        resolver_id="adapter-test",
        resolver_version="1",
        transaction_time="2026-07-28T00:00:00Z",
        metadata={"speaker": "user"},
    )
    assistant_source = make_source_record_revision(
        source_record_id="source-assistant",
        revision_number=1,
        previous_revision_id=None,
        artifact_revision_id=artifact.artifact_revision_id,
        source_ref="fixture=assistant",
        turn_id="turn-1",
        session_id="session-1",
        record_kind="message",
        text="Understood.",
        resolver_id="adapter-test",
        resolver_version="1",
        transaction_time="2026-07-28T00:00:01Z",
        metadata={"speaker": "assistant"},
    )
    evidence = make_evidence_span(
        evidence_id="evidence-lead-alpha",
        source_revision=user_source,
        turn_id="turn-1",
        session_id="session-1",
        char_start=0,
        char_end=len(user_source.text),
        text=user_source.text,
    )
    l1 = L1MemoryUnitV2(
        unit_id="l1-lead-alpha",
        kind="event",
        predicate=Predicate(
            surface="lead",
            sense="lead/manage",
            canonical_operator="manage",
        ),
        roles=[
            RoleBinding(role="agent", role_name="ARG0", entity_id="entity-user"),
            RoleBinding(
                role="theme",
                role_name="ARG1",
                entity_id="project-alpha",
            ),
        ],
        time=TimeBinding(
            event_time="2026-07-01",
            valid_time="2026-07-01",
            transaction_time=payload_transaction_time,
        ),
        source=SourceBindingV2(
            speaker="user",
            source_status="user_reported",
            evidence_spans=[evidence],
        ),
        lifecycle="active",
    )
    l1_revision = make_memory_unit_revision(
        payload=l1,
        revision_number=1,
        previous_revision_id=None,
        revision_kind="create",
        transaction_time="2026-07-28T00:00:03Z",
        source_revision_ids=[user_source.source_revision_id],
        derived_from_revision_ids=[],
        producer=_producer(),
    )
    turn_bundle = make_turn_bundle_revision(
        turn_bundle_id="turn-bundle-1",
        revision_number=1,
        previous_revision_id=None,
        session_id="session-1",
        turn_id="turn-1",
        turn_index=0,
        source_records=[
            TurnSourceRevisionRef(
                ordinal=0,
                source_revision_id=user_source.source_revision_id,
                speaker="user",
            ),
            TurnSourceRevisionRef(
                ordinal=1,
                source_revision_id=assistant_source.source_revision_id,
                speaker="assistant",
            ),
        ],
        extraction_state="complete",
        l1_unit_revision_ids=[l1_revision.revision_id],
        no_memory_reason=None,
        failure_reason=None,
        extractor_id="adapter-test",
        extractor_version="1",
        transaction_time="2026-07-28T00:00:04Z",
    )
    claim = L2StructuredClaim(
        claim_id="claim-lead-alpha",
        predicate=l1.predicate,
        roles=l1.roles,
        modality=l1.modality,
        polarity=l1.polarity,
        time=TimeBinding(
            event_time=l1.time.event_time,
            valid_time=l1.time.valid_time,
        ),
        supporting_l1_units=[l1.unit_id],
    )
    l2 = L2MemoryUnitV2(
        unit_id="l2-project-alpha",
        kind="project",
        abstracts=[l1.unit_id],
        summary="The user leads Project Alpha.",
        structured_claims=[claim],
        closure_id="closure-claim-lead-alpha",
        closure_spec_revision=1,
        closure_evaluation_id="pending",
        lifecycle="candidate",
        source_l1_units=[l1.unit_id],
        source_turns=["turn-1"],
        source_sessions=["session-1"],
    )
    closure_spec = make_closure_spec(
        closure_id=l2.closure_id,
        revision=1,
        target_id=claim.claim_id,
        pattern="multi_evidence_set",
        slots=[
            ClosureSlotSpec(
                slot_id="slot-lead-alpha",
                role="evidence",
                bound_unit_id=l1.unit_id,
                fallback_class="blocked",
            )
        ],
    )
    closure_inputs = ClosureEvaluationInputs(
        evaluated_bundle_id="bundle-query-execution-adapter",
        context=ClaimClosureContext(
            l2_unit_id=l2.unit_id,
            claim_id=claim.claim_id,
            claim_hash=claim.semantic_hash,
            support_unit_ids=[l1.unit_id],
            support_scope=[l1.unit_id],
        ),
        current_revision_ids={l1.unit_id: l1_revision.revision_id},
        unit_revisions=[l1_revision],
        source_revisions=[user_source, assistant_source],
        evaluator_id="closure-evaluator",
        evaluator_version="1",
        policy_version="1",
    )
    closure_evaluation = evaluate_closure_spec(closure_spec, closure_inputs)
    l2 = l2.model_copy(
        update={
            "closure_evaluation_id": closure_evaluation.evaluation_id,
            "lifecycle": "active",
        }
    )
    l2_revision = make_memory_unit_revision(
        payload=l2,
        revision_number=1,
        previous_revision_id=None,
        revision_kind="create",
        transaction_time="2026-07-28T00:00:05Z",
        source_revision_ids=[user_source.source_revision_id],
        derived_from_revision_ids=[l1_revision.revision_id],
        producer=_producer(),
    )
    bundle = MemoryRepresentationBundleV3(
        bundle_id="bundle-query-execution-adapter",
        profile=_profile(),
        raw_artifact_revisions=[artifact],
        source_record_revisions=[user_source, assistant_source],
        unit_revisions=[l1_revision, l2_revision],
        current_revision_ids={
            l1.unit_id: l1_revision.revision_id,
            l2.unit_id: l2_revision.revision_id,
        },
        l1_units=[l1],
        l2_units=[l2],
        closure_specs=[closure_spec],
        closure_evaluations=[closure_evaluation],
        query_plans=[],
        metadata={
            "closure_evaluator_id": "closure-evaluator",
            "closure_evaluator_version": "1",
            "closure_policy_version": "1",
        },
    )
    if identity_scope is not None:
        identity_bundle = IdentityAwareMemoryBundleV4(
            **bundle.model_dump(mode="python", exclude={"schema_version"}),
            concept_registry=[],
            entity_records=[],
            identity_decisions=[],
            identity_closures=[],
            identity_snapshots=[],
            aggregate_claims=[],
        )
        identity_snapshot = build_identity_snapshot(
            identity_bundle,
            scoped_entity_ids=identity_scope,
        )
        bundle = identity_bundle.model_copy(
            update={"identity_snapshots": [identity_snapshot]}
        )
    turn_artifact = make_turn_bundle_history_artifact(
        bundle=turn_bundle,
        source_revisions=[user_source, assistant_source],
        unit_revisions=[l1_revision],
    )
    bundle_artifact = make_history_artifact(
        artifact_kind="l2_bundle",
        logical_id=bundle_artifact_logical_id or bundle.bundle_id,
        revision_id="bundle-revision-1",
        transaction_time="2026-07-28T00:00:06Z",
        payload={"memory_representation_bundle": bundle.model_dump(mode="json")},
        references=[
            HistoryArtifactReference(
                relation="derived_from",
                artifact_kind="turn_bundle",
                logical_id=turn_bundle.turn_bundle_id,
                revision_id=turn_bundle.bundle_revision_id,
            )
        ],
    )
    repository = GitMemoryHistoryRepository.initialize(
        tmp_path / "memory-history.git",
        workspace_id="workspace-main",
        created_at="2026-07-28T00:00:00Z",
    )
    manifest = repository.make_checkpoint(
        artifacts=[turn_artifact, bundle_artifact],
        transaction_time="2026-07-28T00:00:07Z",
    )
    repository.commit_checkpoint(
        manifest=manifest,
        artifacts=[turn_artifact, bundle_artifact],
        expected_head=repository.head_commit(),
    )
    return repository, bundle, bundle_artifact, [turn_bundle]


def test_adapter_maps_closed_current_l1_and_active_l2_claim(tmp_path: Path) -> None:
    repository, bundle, bundle_artifact, turn_bundles = _fixture(tmp_path)

    snapshot = build_query_execution_snapshot(
        repository_path=repository.repo_path,
        bundle=bundle,
        bundle_history_artifact=bundle_artifact,
        turn_bundles=turn_bundles,
        registry=_compiler_registry(),
    )

    assert snapshot.bundle_id == bundle.bundle_id
    assert snapshot.memory_view.git_commit == repository.head_commit()
    assert snapshot.ontology_revision == "ontology-v7"
    assert snapshot.identity_revision == "identity-v4"
    assert snapshot.registry_revision == "registry-v1"
    assert snapshot.registry_sha256 == _compiler_registry().registry_sha256
    assert len(snapshot.facts) == 2
    l1_fact = next(item for item in snapshot.facts if item.level == "L1")
    l2_fact = next(item for item in snapshot.facts if item.level == "L2")
    assert l1_fact.fact_id == bundle.current_revision_ids["l1-lead-alpha"]
    assert l1_fact.predicate_sense == "lead/manage"
    assert l1_fact.canonical_operator == "manage"
    assert l1_fact.evidence_ids == ["evidence-lead-alpha"]
    assert l1_fact.provenance is not None
    assert l1_fact.provenance.claim_id is None
    assert l2_fact.provenance is not None
    assert l2_fact.provenance.claim_id == "claim-lead-alpha"
    assert l2_fact.provenance.supporting_l1_revision_ids == [
        bundle.current_revision_ids["l1-lead-alpha"]
    ]
    assert l2_fact.evidence_ids == ["evidence-lead-alpha"]
    assert snapshot.identity_status == {
        "entity-user": "unresolved",
        "project-alpha": "unresolved",
    }


def test_adapter_rejects_payload_and_revision_transaction_time_disagreement(
    tmp_path: Path,
) -> None:
    repository, bundle, bundle_artifact, turn_bundles = _fixture(
        tmp_path,
        payload_transaction_time="2026-07-27T23:59:59Z",
    )

    with pytest.raises(ValueError, match="transaction time disagreement"):
        build_query_execution_snapshot(
            repository_path=repository.repo_path,
            bundle=bundle,
            bundle_history_artifact=bundle_artifact,
            turn_bundles=turn_bundles,
            registry=_compiler_registry(),
        )


def test_adapter_rejects_bundle_artifact_not_published_at_verified_head(
    tmp_path: Path,
) -> None:
    repository, bundle, bundle_artifact, turn_bundles = _fixture(tmp_path)
    unpublished = bundle_artifact.model_copy(
        update={"revision_id": "bundle-revision-unpublished"}
    )

    with pytest.raises(ValueError, match="bundle history artifact"):
        build_query_execution_snapshot(
            repository_path=repository.repo_path,
            bundle=bundle,
            bundle_history_artifact=unpublished,
            turn_bundles=turn_bundles,
            registry=_compiler_registry(),
        )


def test_adapter_reads_artifacts_from_the_verified_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository, bundle, bundle_artifact, turn_bundles = _fixture(tmp_path)
    original = GitMemoryHistoryRepository.read_artifact
    observed_commits: list[str | None] = []

    def read_artifact_at_commit(self, **kwargs):
        if kwargs["artifact_kind"] in {"l2_bundle", "turn_bundle"}:
            observed_commits.append(kwargs.get("commit"))
        return original(self, **kwargs)

    monkeypatch.setattr(
        GitMemoryHistoryRepository,
        "read_artifact",
        read_artifact_at_commit,
    )

    snapshot = build_query_execution_snapshot(
        repository_path=repository.repo_path,
        bundle=bundle,
        bundle_history_artifact=bundle_artifact,
        turn_bundles=turn_bundles,
        registry=_compiler_registry(),
    )

    assert observed_commits
    assert set(observed_commits) == {snapshot.memory_view.git_commit}


def test_adapter_rejects_bundle_published_under_wrong_logical_id(
    tmp_path: Path,
) -> None:
    repository, bundle, bundle_artifact, turn_bundles = _fixture(
        tmp_path,
        bundle_artifact_logical_id="wrong-bundle-id",
    )

    with pytest.raises(ValueError, match="bundle history artifact logical ID"):
        build_query_execution_snapshot(
            repository_path=repository.repo_path,
            bundle=bundle,
            bundle_history_artifact=bundle_artifact,
            turn_bundles=turn_bundles,
            registry=_compiler_registry(),
        )


def test_adapter_keeps_entities_outside_identity_scope_unresolved(
    tmp_path: Path,
) -> None:
    repository, bundle, bundle_artifact, turn_bundles = _fixture(
        tmp_path,
        identity_scope=["entity-user"],
    )
    assert isinstance(bundle, IdentityAwareMemoryBundleV4)

    snapshot = build_query_execution_snapshot(
        repository_path=repository.repo_path,
        bundle=bundle,
        bundle_history_artifact=bundle_artifact,
        turn_bundles=turn_bundles,
        registry=_identity_bound_registry(bundle.identity_snapshots[0]),
        identity_snapshot_id=bundle.identity_snapshots[0].snapshot_id,
    )

    assert snapshot.identity_status == {
        "entity-user": "resolved",
        "project-alpha": "unresolved",
    }


def test_adapter_rejects_identity_snapshot_not_bound_by_registry(
    tmp_path: Path,
) -> None:
    repository, bundle, bundle_artifact, turn_bundles = _fixture(
        tmp_path,
        identity_scope=["entity-user"],
    )
    assert isinstance(bundle, IdentityAwareMemoryBundleV4)

    with pytest.raises(ValueError, match="identity snapshot binding"):
        build_query_execution_snapshot(
            repository_path=repository.repo_path,
            bundle=bundle,
            bundle_history_artifact=bundle_artifact,
            turn_bundles=turn_bundles,
            registry=_compiler_registry(),
            identity_snapshot_id=bundle.identity_snapshots[0].snapshot_id,
        )


def test_public_authoritative_execution_builds_verified_snapshot_internally(
    tmp_path: Path,
) -> None:
    repository, bundle, bundle_artifact, turn_bundles = _fixture(tmp_path)
    registry = _compiler_registry()
    snapshot = build_query_execution_snapshot(
        repository_path=repository.repo_path,
        bundle=bundle,
        bundle_history_artifact=bundle_artifact,
        turn_bundles=turn_bundles,
        registry=registry,
    )
    plan = _compiled_plan(snapshot.memory_view)

    assert "snapshot" not in signature(execute_authoritative_query).parameters
    result = execute_authoritative_query(
        repository_path=repository.repo_path,
        bundle=bundle,
        bundle_history_artifact=bundle_artifact,
        turn_bundles=turn_bundles,
        registry=registry,
        plan=plan,
    )

    assert isinstance(result, QueryExecutionResultV3)
    assert result.abstained is False
    assert result.answer_values == ("project-alpha",)
    assert result.required_evidence_ids == ("evidence-lead-alpha",)
    assert result.authority.memory_view == snapshot.memory_view
    assert result.authority.bundle_id == bundle.bundle_id
    assert result.authority.bundle_history_artifact_sha256 == canonical_sha256(
        bundle_artifact
    )
    assert result.authority.registry_sha256 == registry.registry_sha256
    assert result.authority.snapshot_sha256 == canonical_sha256(snapshot)
    assert result.authority.plan_sha256 == plan.plan_sha256
    assert result.authority.evaluation_sha256 == canonical_sha256(result.evaluation)
    authority_payload = result.authority.model_dump(
        mode="json", exclude={"authority_sha256"}
    )
    assert result.authority.authority_sha256 == canonical_sha256(authority_payload)


def test_public_authoritative_execution_revalidates_plan_hash(
    tmp_path: Path,
) -> None:
    repository, bundle, bundle_artifact, turn_bundles = _fixture(tmp_path)
    registry = _compiler_registry()
    snapshot = build_query_execution_snapshot(
        repository_path=repository.repo_path,
        bundle=bundle,
        bundle_history_artifact=bundle_artifact,
        turn_bundles=turn_bundles,
        registry=registry,
    )
    plan = _compiled_plan(snapshot.memory_view).model_copy(
        update={"raw_query": "tampered after validation"}
    )

    with pytest.raises(ValidationError, match="compiled query plan hash mismatch"):
        execute_authoritative_query(
            repository_path=repository.repo_path,
            bundle=bundle,
            bundle_history_artifact=bundle_artifact,
            turn_bundles=turn_bundles,
            registry=registry,
            plan=plan,
        )


def test_authority_binding_rejects_content_tampering(tmp_path: Path) -> None:
    repository, bundle, bundle_artifact, turn_bundles = _fixture(tmp_path)
    registry = _compiler_registry()
    snapshot = build_query_execution_snapshot(
        repository_path=repository.repo_path,
        bundle=bundle,
        bundle_history_artifact=bundle_artifact,
        turn_bundles=turn_bundles,
        registry=registry,
    )
    result = execute_authoritative_query(
        repository_path=repository.repo_path,
        bundle=bundle,
        bundle_history_artifact=bundle_artifact,
        turn_bundles=turn_bundles,
        registry=registry,
        plan=_compiled_plan(snapshot.memory_view),
    )
    payload = result.authority.model_dump(mode="json")
    payload["bundle_id"] = "tampered-bundle"

    with pytest.raises(ValidationError, match="authority hash mismatch"):
        QueryExecutionAuthorityV1.model_validate(payload)


def test_authoritative_result_rejects_evaluation_tampering(tmp_path: Path) -> None:
    repository, bundle, bundle_artifact, turn_bundles = _fixture(tmp_path)
    registry = _compiler_registry()
    snapshot = build_query_execution_snapshot(
        repository_path=repository.repo_path,
        bundle=bundle,
        bundle_history_artifact=bundle_artifact,
        turn_bundles=turn_bundles,
        registry=registry,
    )
    result = execute_authoritative_query(
        repository_path=repository.repo_path,
        bundle=bundle,
        bundle_history_artifact=bundle_artifact,
        turn_bundles=turn_bundles,
        registry=registry,
        plan=_compiled_plan(snapshot.memory_view),
    )
    payload = result.model_dump(mode="json")
    payload["evaluation"]["answer_values"] = ["tampered-project"]

    with pytest.raises(ValidationError, match="evaluation hash mismatch"):
        QueryExecutionResultV3.model_validate(payload)


def test_authoritative_result_collections_are_deeply_immutable(
    tmp_path: Path,
) -> None:
    repository, bundle, bundle_artifact, turn_bundles = _fixture(tmp_path)
    registry = _compiler_registry()
    snapshot = build_query_execution_snapshot(
        repository_path=repository.repo_path,
        bundle=bundle,
        bundle_history_artifact=bundle_artifact,
        turn_bundles=turn_bundles,
        registry=registry,
    )
    result = execute_authoritative_query(
        repository_path=repository.repo_path,
        bundle=bundle,
        bundle_history_artifact=bundle_artifact,
        turn_bundles=turn_bundles,
        registry=registry,
        plan=_compiled_plan(snapshot.memory_view),
    )

    with pytest.raises(AttributeError):
        result.answer_values.append("tampered-project")
    with pytest.raises(AttributeError):
        result.evaluation.required_evidence_ids.append("tampered-evidence")


def test_authority_model_copy_revalidates_hash(tmp_path: Path) -> None:
    repository, bundle, bundle_artifact, turn_bundles = _fixture(tmp_path)
    registry = _compiler_registry()
    snapshot = build_query_execution_snapshot(
        repository_path=repository.repo_path,
        bundle=bundle,
        bundle_history_artifact=bundle_artifact,
        turn_bundles=turn_bundles,
        registry=registry,
    )
    result = execute_authoritative_query(
        repository_path=repository.repo_path,
        bundle=bundle,
        bundle_history_artifact=bundle_artifact,
        turn_bundles=turn_bundles,
        registry=registry,
        plan=_compiled_plan(snapshot.memory_view),
    )

    with pytest.raises(ValidationError, match="authority hash mismatch"):
        result.authority.model_copy(update={"bundle_id": "tampered-bundle"})


def test_authoritative_result_model_copy_revalidates_evaluation_hash(
    tmp_path: Path,
) -> None:
    repository, bundle, bundle_artifact, turn_bundles = _fixture(tmp_path)
    registry = _compiler_registry()
    snapshot = build_query_execution_snapshot(
        repository_path=repository.repo_path,
        bundle=bundle,
        bundle_history_artifact=bundle_artifact,
        turn_bundles=turn_bundles,
        registry=registry,
    )
    result = execute_authoritative_query(
        repository_path=repository.repo_path,
        bundle=bundle,
        bundle_history_artifact=bundle_artifact,
        turn_bundles=turn_bundles,
        registry=registry,
        plan=_compiled_plan(snapshot.memory_view),
    )
    tampered_evaluation = result.evaluation.model_copy(
        update={"answer_values": ("tampered-project",)}
    )

    with pytest.raises(ValidationError, match="evaluation hash mismatch"):
        result.model_copy(update={"evaluation": tampered_evaluation})


def test_authority_binding_rejects_inconsistent_identity_pair() -> None:
    payload = {
        "memory_view": {
            "workspace_id": "workspace-main",
            "repository_epoch_id": "epoch-001",
            "checkpoint_id": "checkpoint-0007",
            "git_commit": "a" * 40,
            "authoritative_ref": "refs/heads/authoritative",
        },
        "bundle_id": "bundle-1",
        "bundle_history_artifact_sha256": "a" * 64,
        "registry_sha256": "b" * 64,
        "identity_snapshot_id": "identity-snapshot-1",
        "identity_input_fingerprint": None,
        "snapshot_sha256": "c" * 64,
        "plan_sha256": "d" * 64,
        "evaluation_sha256": "e" * 64,
        "authority_sha256": "f" * 64,
    }

    with pytest.raises(ValidationError, match="identity snapshot"):
        QueryExecutionAuthorityV1.model_validate(payload)


def test_authoritative_execution_replay_is_byte_deterministic(
    tmp_path: Path,
) -> None:
    repository, bundle, bundle_artifact, turn_bundles = _fixture(tmp_path)
    registry = _compiler_registry()
    snapshot = build_query_execution_snapshot(
        repository_path=repository.repo_path,
        bundle=bundle,
        bundle_history_artifact=bundle_artifact,
        turn_bundles=turn_bundles,
        registry=registry,
    )
    plan = _compiled_plan(snapshot.memory_view)
    arguments = {
        "repository_path": repository.repo_path,
        "bundle": bundle,
        "bundle_history_artifact": bundle_artifact,
        "turn_bundles": turn_bundles,
        "registry": registry,
        "plan": plan,
    }

    first = execute_authoritative_query(**arguments)
    second = execute_authoritative_query(**arguments)

    assert first.authority.model_dump_json().encode(
        "utf-8"
    ) == second.authority.model_dump_json().encode("utf-8")
    assert first.model_dump_json().encode(
        "utf-8"
    ) == second.model_dump_json().encode("utf-8")
