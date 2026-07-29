from __future__ import annotations

from pathlib import Path

from .authoritative_memory import (
    ClaimClosureContext,
    L1MemoryUnitV2,
    L2MemoryUnitV2,
    MemoryRepresentationBundleV3,
    MemoryUnitRevision,
    assess_authoritative_bundle_integrity,
    canonical_sha256,
)
from .git_memory_history import (
    GitMemoryHistoryRepository,
    HistoryArtifact,
    make_turn_bundle_history_artifact,
)
from .identity_resolution import (
    IdentityAwareMemoryBundleV4,
    IdentitySnapshot,
    assess_identity_bundle_integrity,
)
from .query_compiler_v2 import (
    CompiledQueryPlanV2,
    CompilerRegistryV1,
    GitMemoryViewRefV1,
)
from .query_plan_v2_executor import (
    ExecutionFactProvenanceV1,
    ExecutionRoleBindingV1,
    ExecutionTimeV1,
    QueryExecutionAuthorityV1,
    QueryExecutionFactV1,
    QueryExecutionResultV3,
    QueryExecutionSnapshotV1,
    QuerySnapshotEvaluationV1,
    _evaluate_compiled_query_snapshot,
)
from .turn_bundle import TurnBundleRevision, validate_turn_bundle_closure


def _ordered_unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _memory_view(repository: GitMemoryHistoryRepository) -> GitMemoryViewRefV1:
    report = repository.verify()
    if report.status != "valid":
        raise ValueError("memory history verification failed: " + "; ".join(report.errors))
    metadata = repository.read_repository_metadata()
    state = repository.read_state()
    head = repository.head_commit()
    if state.checkpoint_id is None or state.git_commit is None:
        raise ValueError("query execution snapshot requires a committed checkpoint")
    if state.git_commit != head:
        raise ValueError("repository state git commit differs from authoritative HEAD")
    return GitMemoryViewRefV1(
        workspace_id=metadata.workspace_id,
        repository_epoch_id=metadata.repository_epoch_id,
        checkpoint_id=state.checkpoint_id,
        git_commit=head,
        authoritative_ref=repository.AUTHORITATIVE_REF,
    )


def _validate_bundle_artifact(
    repository: GitMemoryHistoryRepository,
    bundle: MemoryRepresentationBundleV3,
    artifact: HistoryArtifact,
    turn_bundles: list[TurnBundleRevision],
    *,
    commit: str,
) -> None:
    if artifact.artifact_kind != "l2_bundle":
        raise ValueError("bundle history artifact must use l2_bundle kind")
    if artifact.logical_id != bundle.bundle_id:
        raise ValueError("bundle history artifact logical ID does not match bundle")
    expected_payload = {"memory_representation_bundle": bundle.model_dump(mode="json")}
    if artifact.payload != expected_payload:
        raise ValueError("bundle history artifact payload does not match bundle")
    expected_turn_refs = {
        (item.turn_bundle_id, item.bundle_revision_id) for item in turn_bundles
    }
    actual_turn_refs = {
        (item.logical_id, item.revision_id)
        for item in artifact.references
        if item.relation == "derived_from" and item.artifact_kind == "turn_bundle"
    }
    if actual_turn_refs != expected_turn_refs:
        raise ValueError("bundle history artifact turn references mismatch")
    try:
        published = repository.read_artifact(
            artifact_kind=artifact.artifact_kind,
            logical_id=artifact.logical_id,
            revision_id=artifact.revision_id,
            commit=commit,
        )
    except Exception as exc:
        raise ValueError(f"bundle history artifact is not published: {exc}") from exc
    if published != artifact:
        raise ValueError("bundle history artifact differs from authoritative HEAD")


def _validate_turn_bundles(
    repository: GitMemoryHistoryRepository,
    bundle: MemoryRepresentationBundleV3,
    turn_bundles: list[TurnBundleRevision],
    *,
    commit: str,
) -> dict[str, int]:
    source_revisions = {
        item.source_revision_id: item for item in bundle.source_record_revisions
    }
    unit_revisions = {item.revision_id: item for item in bundle.unit_revisions}
    logical_ids = [item.turn_bundle_id for item in turn_bundles]
    if len(logical_ids) != len(set(logical_ids)):
        raise ValueError("turn bundle logical IDs must be unique at a snapshot")
    ownership: dict[str, int] = {}
    current_revision_ids = set(bundle.current_revision_ids.values())
    for turn_bundle in turn_bundles:
        selected_sources = {
            item.source_revision_id: source_revisions[item.source_revision_id]
            for item in turn_bundle.source_records
            if item.source_revision_id in source_revisions
        }
        selected_units = {
            revision_id: unit_revisions[revision_id]
            for revision_id in turn_bundle.l1_unit_revision_ids
            if revision_id in unit_revisions
        }
        validate_turn_bundle_closure(
            turn_bundle,
            source_revisions=selected_sources,
            unit_revisions=selected_units,
        )
        if any(
            revision_id not in current_revision_ids
            for revision_id in turn_bundle.l1_unit_revision_ids
        ):
            raise ValueError("turn bundle contains a non-current L1 revision")
        for revision_id in turn_bundle.l1_unit_revision_ids:
            ownership[revision_id] = ownership.get(revision_id, 0) + 1
        expected_artifact = make_turn_bundle_history_artifact(
            bundle=turn_bundle,
            source_revisions=list(selected_sources.values()),
            unit_revisions=list(selected_units.values()),
        )
        try:
            published = repository.read_artifact(
                artifact_kind="turn_bundle",
                logical_id=turn_bundle.turn_bundle_id,
                revision_id=turn_bundle.bundle_revision_id,
                commit=commit,
            )
        except Exception as exc:
            raise ValueError(f"turn bundle history artifact is not published: {exc}") from exc
        if published != expected_artifact:
            raise ValueError("turn bundle history artifact differs from authoritative HEAD")
    return ownership


def _execution_time(
    revision: MemoryUnitRevision,
    *,
    event_time: str | None,
    valid_time: str | None,
    payload_transaction_time: str | None,
) -> ExecutionTimeV1:
    if (
        payload_transaction_time is not None
        and payload_transaction_time != revision.transaction_time
    ):
        raise ValueError(
            f"transaction time disagreement for revision {revision.revision_id}"
        )
    return ExecutionTimeV1(
        event_time=event_time,
        valid_time=valid_time,
        transaction_time=revision.transaction_time,
    )


def _roles(unit_roles: list[object]) -> list[ExecutionRoleBindingV1]:
    return [
        ExecutionRoleBindingV1(
            role=item.role,
            role_name=item.role_name,
            entity_id=item.entity_id,
        )
        for item in unit_roles
    ]


def _l1_fact(revision: MemoryUnitRevision) -> QueryExecutionFactV1:
    payload = revision.payload
    if not isinstance(payload, L1MemoryUnitV2):
        raise ValueError("L1 fact mapping requires an L1 revision")
    evidence_ids = _ordered_unique(
        [item.evidence_id for item in payload.source.evidence_spans]
    )
    return QueryExecutionFactV1(
        fact_id=revision.revision_id,
        unit_id=payload.unit_id,
        level="L1",
        predicate_sense=payload.predicate.sense,
        canonical_operator=payload.predicate.canonical_operator,
        roles=_roles(payload.roles),
        modality=payload.modality,
        polarity=payload.polarity,
        time=_execution_time(
            revision,
            event_time=payload.time.event_time,
            valid_time=payload.time.valid_time,
            payload_transaction_time=payload.time.transaction_time,
        ),
        source_status=payload.source.source_status,
        lifecycle=payload.lifecycle,
        evidence_ids=evidence_ids,
        provenance=ExecutionFactProvenanceV1(
            unit_revision_id=revision.revision_id,
            source_revision_ids=list(revision.source_revision_ids),
        ),
    )


def _l2_fact(
    bundle: MemoryRepresentationBundleV3,
    revision: MemoryUnitRevision,
    l1_facts: dict[str, QueryExecutionFactV1],
) -> QueryExecutionFactV1:
    payload = revision.payload
    if not isinstance(payload, L2MemoryUnitV2):
        raise ValueError("L2 fact mapping requires an L2 revision")
    if len(payload.structured_claims) != 1:
        raise ValueError("active L2 execution requires exactly one structured claim")
    claim = payload.structured_claims[0]
    if claim.aggregate is not None:
        raise ValueError("aggregate L2 claims are not supported by execution snapshot v1")
    evaluation = next(
        (
            item
            for item in bundle.closure_evaluations
            if item.evaluation_id == payload.closure_evaluation_id
        ),
        None,
    )
    if (
        evaluation is None
        or not isinstance(evaluation.context, ClaimClosureContext)
        or evaluation.context.claim_id != claim.claim_id
        or not evaluation.complete
    ):
        raise ValueError("active L2 claim lacks a complete claim closure evaluation")
    support_revision_ids = [
        bundle.current_revision_ids[unit_id] for unit_id in claim.supporting_l1_units
    ]
    if not set(support_revision_ids).issubset(revision.derived_from_revision_ids):
        raise ValueError("L2 revision does not pin all supporting L1 revisions")
    support_facts = [l1_facts[unit_id] for unit_id in claim.supporting_l1_units]
    source_statuses = {item.source_status for item in support_facts}
    if len(source_statuses) != 1:
        raise ValueError("mixed-source L2 claims are unsupported by execution snapshot v1")
    evidence_ids = _ordered_unique(
        [
            evidence_id
            for support in support_facts
            for evidence_id in support.evidence_ids
        ]
    )
    source_revision_ids = _ordered_unique(
        [
            source_revision_id
            for support in support_facts
            for source_revision_id in support.provenance.source_revision_ids
            if support.provenance is not None
        ]
    )
    fact_identity = {
        "unit_revision_id": revision.revision_id,
        "claim_id": claim.claim_id,
        "claim_hash": claim.semantic_hash,
    }
    return QueryExecutionFactV1(
        fact_id=f"l2-claim-{canonical_sha256(fact_identity)[:24]}",
        unit_id=payload.unit_id,
        level="L2",
        predicate_sense=claim.predicate.sense,
        canonical_operator=claim.predicate.canonical_operator,
        roles=_roles(claim.roles),
        modality=claim.modality,
        polarity=claim.polarity,
        time=_execution_time(
            revision,
            event_time=claim.time.event_time,
            valid_time=claim.time.valid_time,
            payload_transaction_time=claim.time.transaction_time,
        ),
        source_status=next(iter(source_statuses)),
        lifecycle=payload.lifecycle,
        evidence_ids=evidence_ids,
        provenance=ExecutionFactProvenanceV1(
            unit_revision_id=revision.revision_id,
            claim_id=claim.claim_id,
            source_revision_ids=source_revision_ids,
            supporting_l1_revision_ids=support_revision_ids,
            closure_evaluation_id=evaluation.evaluation_id,
        ),
    )


def _identity_maps(
    bundle: MemoryRepresentationBundleV3,
    facts: list[QueryExecutionFactV1],
    identity_snapshot_id: str | None,
) -> tuple[dict[str, str], dict[str, str], IdentitySnapshot | None]:
    entity_ids = {
        role.entity_id for fact in facts for role in fact.roles
    }
    if identity_snapshot_id is None:
        return (
            {entity_id: entity_id for entity_id in sorted(entity_ids)},
            {entity_id: "unresolved" for entity_id in sorted(entity_ids)},
            None,
        )
    if not isinstance(bundle, IdentityAwareMemoryBundleV4):
        raise ValueError("identity snapshot requires an identity-aware memory bundle")
    report = assess_identity_bundle_integrity(bundle)
    if not report.valid:
        raise ValueError("identity bundle integrity failed: " + "; ".join(report.errors))
    snapshot = next(
        (
            item
            for item in bundle.identity_snapshots
            if item.snapshot_id == identity_snapshot_id
        ),
        None,
    )
    if snapshot is None:
        raise ValueError("identity snapshot is missing from the authoritative bundle")
    canonical: dict[str, str] = {}
    for group in snapshot.groups:
        canonical[group.canonical_entity_id] = group.canonical_entity_id
        for member in group.member_entity_ids:
            canonical[member] = group.canonical_entity_id
    unresolved = {item for group in snapshot.unresolved_groups for item in group}
    scoped = set(snapshot.scoped_entity_ids)
    status: dict[str, str] = {}
    for entity_id in sorted(entity_ids):
        target = canonical.get(entity_id, entity_id)
        canonical.setdefault(entity_id, target)
        canonical.setdefault(target, target)
        candidate_status = (
            "resolved"
            if entity_id in scoped and entity_id not in unresolved
            else "unresolved"
        )
        prior = status.get(target)
        if prior == "unresolved" or candidate_status == "unresolved":
            status[target] = "unresolved"
        else:
            status[target] = "resolved"
    return canonical, status, snapshot


def build_query_execution_snapshot(
    *,
    repository_path: Path,
    bundle: MemoryRepresentationBundleV3,
    bundle_history_artifact: HistoryArtifact,
    turn_bundles: list[TurnBundleRevision],
    registry: CompilerRegistryV1,
    identity_snapshot_id: str | None = None,
) -> QueryExecutionSnapshotV1:
    registry = CompilerRegistryV1.model_validate(
        registry.model_dump(mode="json")
    )
    if identity_snapshot_id != registry.identity_snapshot_id:
        raise ValueError(
            "identity snapshot binding does not match compiler registry"
        )
    repository = GitMemoryHistoryRepository(repository_path)
    memory_view = _memory_view(repository)
    integrity = assess_authoritative_bundle_integrity(bundle)
    if not integrity.valid:
        raise ValueError("authoritative bundle integrity failed: " + "; ".join(integrity.errors))
    _validate_bundle_artifact(
        repository,
        bundle,
        bundle_history_artifact,
        turn_bundles,
        commit=memory_view.git_commit,
    )
    ownership = _validate_turn_bundles(
        repository,
        bundle,
        turn_bundles,
        commit=memory_view.git_commit,
    )
    revisions = {item.revision_id: item for item in bundle.unit_revisions}
    l1_facts: dict[str, QueryExecutionFactV1] = {}
    for l1 in bundle.l1_units:
        revision_id = bundle.current_revision_ids[l1.unit_id]
        if ownership.get(revision_id) != 1:
            raise ValueError(
                f"current L1 revision {revision_id} must belong to exactly one turn bundle"
            )
        l1_facts[l1.unit_id] = _l1_fact(revisions[revision_id])
    facts = list(l1_facts.values())
    for l2 in bundle.l2_units:
        if l2.lifecycle != "active":
            continue
        revision_id = bundle.current_revision_ids[l2.unit_id]
        facts.append(_l2_fact(bundle, revisions[revision_id], l1_facts))
    canonical_ids, identity_status, identity_snapshot = _identity_maps(
        bundle,
        facts,
        identity_snapshot_id,
    )
    if (
        identity_snapshot is not None
        and identity_snapshot.input_fingerprint
        != registry.identity_input_fingerprint
    ):
        raise ValueError(
            "identity snapshot fingerprint does not match compiler registry"
        )
    if registry.registry_sha256 is None:
        raise ValueError("compiler registry content hash is missing")
    return QueryExecutionSnapshotV1(
        bundle_id=bundle.bundle_id,
        memory_view=memory_view,
        ontology_revision=registry.ontology_revision,
        identity_revision=registry.identity_revision,
        registry_revision=registry.registry_revision,
        registry_sha256=registry.registry_sha256,
        facts=facts,
        identity_status=identity_status,
        canonical_entity_ids=canonical_ids,
        identity_snapshot_id=(
            identity_snapshot.snapshot_id if identity_snapshot is not None else None
        ),
        identity_input_fingerprint=(
            identity_snapshot.input_fingerprint
            if identity_snapshot is not None
            else None
        ),
    )


def _query_execution_authority(
    *,
    snapshot: QueryExecutionSnapshotV1,
    bundle_history_artifact: HistoryArtifact,
    plan: CompiledQueryPlanV2,
    evaluation: QuerySnapshotEvaluationV1,
) -> QueryExecutionAuthorityV1:
    authority_payload = {
        "schema_version": "query-execution-authority-v1",
        "memory_view": snapshot.memory_view.model_dump(mode="json"),
        "bundle_id": snapshot.bundle_id,
        "bundle_history_artifact_sha256": canonical_sha256(
            bundle_history_artifact
        ),
        "registry_sha256": snapshot.registry_sha256,
        "identity_snapshot_id": snapshot.identity_snapshot_id,
        "identity_input_fingerprint": snapshot.identity_input_fingerprint,
        "snapshot_sha256": canonical_sha256(snapshot),
        "plan_sha256": plan.plan_sha256,
        "evaluation_sha256": canonical_sha256(evaluation),
    }
    return QueryExecutionAuthorityV1(
        **authority_payload,
        authority_sha256=canonical_sha256(authority_payload),
    )


def execute_authoritative_query(
    *,
    repository_path: Path,
    bundle: MemoryRepresentationBundleV3,
    bundle_history_artifact: HistoryArtifact,
    turn_bundles: list[TurnBundleRevision],
    registry: CompilerRegistryV1,
    plan: CompiledQueryPlanV2,
    identity_snapshot_id: str | None = None,
) -> QueryExecutionResultV3:
    validated_plan = CompiledQueryPlanV2.model_validate(
        plan.model_dump(mode="json")
    )
    snapshot = build_query_execution_snapshot(
        repository_path=repository_path,
        bundle=bundle,
        bundle_history_artifact=bundle_history_artifact,
        turn_bundles=turn_bundles,
        registry=registry,
        identity_snapshot_id=identity_snapshot_id,
    )
    evaluation = _evaluate_compiled_query_snapshot(validated_plan, snapshot)
    authority = _query_execution_authority(
        snapshot=snapshot,
        bundle_history_artifact=bundle_history_artifact,
        plan=validated_plan,
        evaluation=evaluation,
    )
    return QueryExecutionResultV3(
        evaluation=evaluation,
        authority=authority,
    )
