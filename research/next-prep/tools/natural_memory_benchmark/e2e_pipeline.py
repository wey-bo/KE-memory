from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal, Protocol, Sequence

from pydantic import Field

from .authoritative_memory import (
    ClaimClosureContext,
    ClosureEvaluation,
    ClosureEvaluationInputs,
    ClosureSlotSpec,
    ClosureSpec,
    EvidenceSpanV2,
    L1MemoryUnitV2,
    L2MemoryUnitV2,
    L2StructuredClaim,
    MemoryRepresentationBundleV3,
    MemoryUnitRevision,
    ProducerIdentity,
    RawArtifactRevision,
    SourceBindingV2,
    SourceRecordRevision,
    StrictModel,
    assess_authoritative_bundle_integrity,
    canonical_sha256,
    evaluate_closure_spec,
    is_closure_evaluation_fresh,
    make_closure_spec,
    make_evidence_span,
    make_memory_unit_revision,
    make_raw_artifact_revision,
    make_source_record_revision,
)
from .git_memory_history import (
    GitMemoryHistoryRepository,
    HistoryArtifact,
    HistoryArtifactReference,
    make_history_artifact,
    make_turn_bundle_history_artifact,
)
from .l1_admission import (
    AdmissionContext,
    AdmissionDecision,
    AdmissionPolicy,
    SourceEpistemicBinding,
    admit_linked_l1,
)
from .l1_ontology_linking import (
    LinkedL1Candidate,
    OntologyRegistry,
    build_diagnostic_ontology_registry,
    link_l1_candidate,
)
from .query_compiler_v2 import (
    CompilerRegistryV1,
    GitMemoryViewRefV1,
    PredicateRegistryEntryV1,
    QueryCompilationResultV1,
    QueryContextV1,
    QueryDraftProducer,
    compile_natural_query,
)
from .query_execution_snapshot_adapter import execute_authoritative_query
from .query_plan_v2_executor import QueryExecutionResultV3
from .representation_contract import (
    REQUIRED_MEMORY_CAPABILITIES,
    CapabilityDeclaration,
    RepresentationProfile,
)
from .semantic_ir import Predicate, RoleBinding, TimeBinding
from .turn_bundle import (
    TurnBundleRevision,
    TurnSourceRevisionRef,
    make_turn_bundle_revision,
)
from .typed_extractor_l1 import TypedL1Candidate
from .typed_extractor_l2 import TypedL2Candidate


_BASE_TIME = datetime(2026, 7, 30, tzinfo=timezone.utc)


class RawTurnV1(StrictModel):
    session_id: str = Field(min_length=1)
    turn_id: str = Field(min_length=1)
    turn_index: int = Field(ge=0)
    user_text: str = Field(min_length=1)
    assistant_text: str = Field(min_length=1)


class TurnExtractionInputV1(StrictModel):
    turn: RawTurnV1
    user_source: SourceRecordRevision
    assistant_source: SourceRecordRevision
    user_evidence: EvidenceSpanV2


class ProposedL1CandidateV1(StrictModel):
    candidate_ref: str = Field(pattern=r"^support-[0-9a-f]{16}$")
    typed_candidate: TypedL1Candidate


class ProposedL2CandidateV1(StrictModel):
    candidate_ref: str = Field(
        min_length=1,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$",
    )
    typed_candidate: TypedL2Candidate


class AdmittedL1Record(StrictModel):
    candidate_ref: str
    turn_id: str
    session_id: str
    linked_candidate: LinkedL1Candidate
    decision: AdmissionDecision
    revision: MemoryUnitRevision


class ClosedL2Record(StrictModel):
    candidate_ref: str
    closure_spec: ClosureSpec
    closure_evaluation: ClosureEvaluation
    revision: MemoryUnitRevision


class AuthoritativeSnapshotReceipt(StrictModel):
    repository_path: str
    checkpoint_id: str
    git_commit: str = Field(pattern=r"^[0-9a-f]{40,64}$")
    previous_git_commit: str = Field(pattern=r"^[0-9a-f]{40,64}$")
    verification_status: Literal["valid"] = "valid"
    bundle_history_artifact: HistoryArtifact


class EvidenceBackedAnswerV1(StrictModel):
    query_id: str
    answer_values: tuple[str, ...] = Field(default_factory=tuple)
    evidence_spans: tuple[EvidenceSpanV2, ...] = Field(default_factory=tuple)
    closure_complete: bool
    abstained: bool
    fallback_triggered: Literal[False] = False
    authority_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class EndToEndResultV1(StrictModel):
    bundle: MemoryRepresentationBundleV3
    turn_bundles: tuple[TurnBundleRevision, ...]
    snapshot: AuthoritativeSnapshotReceipt
    compilation: QueryCompilationResultV1
    execution: QueryExecutionResultV3
    answer: EvidenceBackedAnswerV1


class L1CandidateProducer(Protocol):
    def produce(
        self, value: TurnExtractionInputV1
    ) -> list[ProposedL1CandidateV1]: ...


class L2CandidateProducer(Protocol):
    def produce(
        self, admitted_l1: Sequence[AdmittedL1Record]
    ) -> list[ProposedL2CandidateV1]: ...


def _timestamp(offset_seconds: int) -> str:
    value = _BASE_TIME + timedelta(seconds=offset_seconds)
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def _normalized(value: str) -> str:
    return " ".join(value.casefold().split())


def _profile() -> RepresentationProfile:
    return RepresentationProfile(
        representation_id="e2e-authoritative-semantic-ir",
        family="semantic_ir",
        format_version="memory-representation-bundle-v3",
        role="authoritative_candidate",
        capabilities=[
            CapabilityDeclaration(
                capability=name,
                support_mode="native",
                location="e2e_pipeline",
            )
            for name in REQUIRED_MEMORY_CAPABILITIES
        ],
    )


def _validate_turns(turns: Sequence[RawTurnV1]) -> list[RawTurnV1]:
    ordered = list(turns)
    if not ordered:
        raise ValueError("at least one raw turn is required")
    if [item.turn_index for item in ordered] != list(range(len(ordered))):
        raise ValueError("turn indexes must be contiguous and ordered from zero")
    if len({item.turn_id for item in ordered}) != len(ordered):
        raise ValueError("raw turn IDs must be unique")
    if len({item.session_id for item in ordered}) != 1:
        raise ValueError("the minimal pipeline accepts exactly one session")
    return ordered


def _make_source_inputs(
    turns: Sequence[RawTurnV1],
) -> tuple[
    RawArtifactRevision,
    list[SourceRecordRevision],
    dict[str, TurnExtractionInputV1],
]:
    raw_bytes = "\n\x1e\n".join(
        f"{item.turn_id}\nuser:{item.user_text}\nassistant:{item.assistant_text}"
        for item in turns
    ).encode("utf-8")
    artifact = make_raw_artifact_revision(
        source_id="e2e-inline-turns",
        frozen_identity=f"e2e-inline:{hashlib.sha256(raw_bytes).hexdigest()}",
        official_url="urn:ke-memory:e2e-inline",
        local_path="inline:e2e-turns",
        reader="json",
        size_bytes=len(raw_bytes),
        content_sha256=hashlib.sha256(raw_bytes).hexdigest(),
    )
    source_revisions: list[SourceRecordRevision] = []
    inputs: dict[str, TurnExtractionInputV1] = {}
    for turn in turns:
        offset = turn.turn_index * 10
        user_source = make_source_record_revision(
            source_record_id=f"source-{turn.turn_id}-user",
            revision_number=1,
            previous_revision_id=None,
            artifact_revision_id=artifact.artifact_revision_id,
            source_ref=f"{turn.turn_id}:user",
            turn_id=turn.turn_id,
            session_id=turn.session_id,
            record_kind="message",
            text=turn.user_text,
            resolver_id="e2e-source-adapter",
            resolver_version="1",
            transaction_time=_timestamp(offset),
            metadata={"speaker": "user"},
        )
        assistant_source = make_source_record_revision(
            source_record_id=f"source-{turn.turn_id}-assistant",
            revision_number=1,
            previous_revision_id=None,
            artifact_revision_id=artifact.artifact_revision_id,
            source_ref=f"{turn.turn_id}:assistant",
            turn_id=turn.turn_id,
            session_id=turn.session_id,
            record_kind="message",
            text=turn.assistant_text,
            resolver_id="e2e-source-adapter",
            resolver_version="1",
            transaction_time=_timestamp(offset + 1),
            metadata={"speaker": "assistant"},
        )
        user_evidence = make_evidence_span(
            evidence_id=f"evidence-{turn.turn_id}-user",
            source_revision=user_source,
            turn_id=turn.turn_id,
            session_id=turn.session_id,
            char_start=0,
            char_end=len(user_source.text),
            text=user_source.text,
        )
        source_revisions.extend([user_source, assistant_source])
        inputs[turn.turn_id] = TurnExtractionInputV1(
            turn=turn,
            user_source=user_source,
            assistant_source=assistant_source,
            user_evidence=user_evidence,
        )
    return artifact, source_revisions, inputs


def _assert_decision_binding(
    *,
    linked: LinkedL1Candidate,
    decision: AdmissionDecision,
    context: AdmissionContext,
) -> None:
    if decision.status != "accept":
        raise ValueError(
            "L1 admission did not accept the candidate: "
            + ",".join(decision.reason_codes)
        )
    if decision.proposed_action.action != "create":
        raise ValueError("the minimal pipeline accepts create actions only")
    if decision.source_candidate_hash != linked.source_candidate_hash:
        raise ValueError("admission decision source candidate binding mismatch")
    if decision.linked_candidate_hash != linked.linked_candidate_hash:
        raise ValueError("admission decision linked candidate binding mismatch")
    if (
        decision.registry_id != linked.registry_id
        or decision.registry_version != linked.registry_version
        or decision.registry_revision != linked.registry_revision
        or decision.registry_hash != linked.registry_hash
    ):
        raise ValueError("admission decision ontology registry binding mismatch")
    raw = sorted(context.raw_artifacts, key=lambda item: item.artifact_revision_id)
    sources = sorted(
        context.source_revisions, key=lambda item: item.source_revision_id
    )
    if decision.raw_artifact_revision_ids != [
        item.artifact_revision_id for item in raw
    ] or decision.raw_artifact_content_hashes != [item.content_sha256 for item in raw]:
        raise ValueError("admission decision raw artifact binding mismatch")
    if decision.source_revision_ids != [
        item.source_revision_id for item in sources
    ] or decision.source_revision_content_hashes != [
        item.content_sha256 for item in sources
    ]:
        raise ValueError("admission decision source revision binding mismatch")
    if decision.transaction_time != context.transaction_time:
        raise ValueError("admission decision transaction time binding mismatch")
    if (
        decision.policy_id != context.policy.policy_id
        or decision.policy_version != context.policy.policy_version
    ):
        raise ValueError("admission decision policy binding mismatch")
    if context.identity_bindings or context.identity_snapshot_authorities:
        raise ValueError("identity authority is outside the category-only pipeline")


def materialize_admitted_l1(
    *,
    proposal: ProposedL1CandidateV1,
    linked: LinkedL1Candidate,
    decision: AdmissionDecision,
    context: AdmissionContext,
    producer: ProducerIdentity,
) -> AdmittedL1Record:
    _assert_decision_binding(linked=linked, decision=decision, context=context)
    if any(item.interpretation != "category" for item in linked.entity_links):
        raise ValueError("identity-bearing L1 candidates are outside category-only scope")
    if linked.unresolved_local_entity_ids:
        raise ValueError("unresolved L1 entity cannot be materialized")
    if linked.typed_candidate.lifecycle.lifecycle != "active":
        raise ValueError("the minimal pipeline accepts active create candidates only")

    entity_id_by_local: dict[str, str] = {}
    for item in linked.entity_links:
        if len(item.selected_concept_ids) != 1:
            raise ValueError("category entity requires exactly one selected concept")
        entity_id_by_local[item.local_entity_id] = item.selected_concept_ids[0]

    span_by_id = {item.evidence_id: item for item in linked.evidence_spans}
    evidence_ids = [
        item.evidence_id for item in linked.typed_candidate.evidence_bindings
    ]
    if decision.evidence_bindings != sorted(evidence_ids):
        raise ValueError("admission decision evidence binding mismatch")
    spans = [span_by_id[item] for item in evidence_ids]
    speakers = {item.speaker for item in linked.typed_candidate.evidence_bindings}
    if len(speakers) != 1:
        raise ValueError("one L1 unit cannot mix evidence speakers")
    epistemic_by_source = {
        item.source_revision_id: item for item in context.source_epistemics
    }
    statuses = {
        epistemic_by_source[span.source_revision_id].source_status for span in spans
    }
    if len(statuses) != 1:
        raise ValueError("one L1 unit cannot mix source epistemic statuses")

    typed = linked.typed_candidate
    unit = L1MemoryUnitV2(
        unit_id=f"l1-{hashlib.sha256(proposal.candidate_ref.encode('utf-8')).hexdigest()[:16]}",
        kind=typed.kind,
        predicate=Predicate(
            surface=linked.predicate_link.predicate_surface,
            sense=linked.predicate_link.predicate_sense,
            canonical_operator=linked.predicate_link.canonical_operator,
        ),
        roles=[
            RoleBinding(
                role=item.role,
                role_name=item.role_name,
                entity_id=entity_id_by_local[item.local_entity_id],
            )
            for item in typed.roles
        ],
        modality=typed.modality,
        polarity=typed.polarity,
        time=TimeBinding(
            event_time=typed.time.event_time,
            valid_time=typed.time.valid_time,
            transaction_time=decision.transaction_time,
        ),
        source=SourceBindingV2(
            speaker=next(iter(speakers)),
            source_status=next(iter(statuses)),
            evidence_spans=spans,
        ),
        lifecycle="active",
    )
    if decision.transaction_time is None:
        raise ValueError("accepted L1 decision requires transaction time")
    revision = make_memory_unit_revision(
        payload=unit,
        revision_number=1,
        previous_revision_id=None,
        revision_kind="create",
        transaction_time=decision.transaction_time,
        source_revision_ids=sorted({item.source_revision_id for item in spans}),
        derived_from_revision_ids=[],
        producer=producer,
    )
    turn_ids = {item.turn_id for item in spans}
    session_ids = {item.session_id for item in spans}
    if len(turn_ids) != 1 or len(session_ids) != 1:
        raise ValueError("an L1 candidate must belong to exactly one turn and session")
    return AdmittedL1Record(
        candidate_ref=proposal.candidate_ref,
        turn_id=next(iter(turn_ids)),
        session_id=next(iter(session_ids)),
        linked_candidate=linked,
        decision=decision,
        revision=revision,
    )


def _surface_entity_bindings(
    admitted_l1: Sequence[AdmittedL1Record],
) -> dict[str, set[str]]:
    bindings: dict[str, set[str]] = defaultdict(set)
    for record in admitted_l1:
        surface_by_local = {
            item.local_entity_id: item.surface
            for item in record.linked_candidate.typed_candidate.local_entities
        }
        for link in record.linked_candidate.entity_links:
            if link.interpretation != "category" or len(link.selected_concept_ids) != 1:
                raise ValueError("L2 support contains a non-authoritative category binding")
            bindings[_normalized(surface_by_local[link.local_entity_id])].add(
                link.selected_concept_ids[0]
            )
    return bindings


def materialize_closed_l2(
    *,
    proposal: ProposedL2CandidateV1,
    admitted_l1: Sequence[AdmittedL1Record],
    bundle_id: str,
    source_revisions: Sequence[SourceRecordRevision],
    producer: ProducerIdentity,
    transaction_time: str,
) -> ClosedL2Record:
    typed = proposal.typed_candidate
    by_ref = {item.candidate_ref: item for item in admitted_l1}
    if len(by_ref) != len(admitted_l1):
        raise ValueError("admitted L1 candidate refs must be unique")
    expected_refs = set(by_ref)
    if set(typed.supporting_l1_refs) != expected_refs:
        raise ValueError("L2 support set must exactly cover admitted L1 records")
    if set(typed.closure.required_support_refs) != expected_refs:
        raise ValueError("L2 required closure must exactly cover admitted L1 records")
    if typed.closure.optional_support_refs:
        raise ValueError("the minimal closed L2 path does not accept optional support")
    if set(typed.source_turn_refs) != {item.turn_id for item in admitted_l1}:
        raise ValueError("L2 source turn closure mismatch")
    if set(typed.source_session_refs) != {item.session_id for item in admitted_l1}:
        raise ValueError("L2 source session closure mismatch")
    evidence_ids = {
        span.evidence_id
        for item in admitted_l1
        for span in item.revision.payload.source.evidence_spans
        if isinstance(item.revision.payload, L1MemoryUnitV2)
    }
    if {item.evidence_id for item in typed.evidence_bindings} != evidence_ids:
        raise ValueError("L2 evidence closure mismatch")

    surface_bindings = _surface_entity_bindings(admitted_l1)
    claims: list[L2StructuredClaim] = []
    for claim in typed.structured_claims:
        if not set(claim.supporting_l1_refs).issubset(expected_refs):
            raise ValueError("L2 claim references unknown admitted support")
        entity_id_by_local: dict[str, str] = {}
        for local in claim.local_entities:
            matches = surface_bindings.get(_normalized(local.surface), set())
            if len(matches) != 1:
                raise ValueError("L2 local entity lacks a unique authoritative L1 binding")
            entity_id_by_local[local.local_entity_id] = next(iter(matches))
        claims.append(
            L2StructuredClaim(
                claim_id=f"{proposal.candidate_ref}-{claim.claim_ref}",
                predicate=Predicate(
                    surface=claim.predicate.surface,
                    sense=claim.predicate.sense,
                    canonical_operator=claim.predicate.canonical_operator,
                ),
                roles=[
                    RoleBinding(
                        role=item.role,
                        role_name=item.role_name,
                        entity_id=entity_id_by_local[item.local_entity_id],
                    )
                    for item in claim.roles
                ],
                modality=claim.modality,
                polarity=claim.polarity,
                time=TimeBinding(
                    event_time=claim.time.event_time,
                    valid_time=claim.time.valid_time,
                ),
                supporting_l1_units=[
                    by_ref[item].revision.memory_unit_id
                    for item in claim.supporting_l1_refs
                ],
            )
        )
    if len(claims) != 1:
        raise ValueError("the minimal closed L2 path requires exactly one structured claim")

    unit_id = proposal.candidate_ref
    closure_id = f"closure-{unit_id}"
    source_l1_units = [
        by_ref[item].revision.memory_unit_id for item in typed.supporting_l1_refs
    ]
    provisional = L2MemoryUnitV2(
        unit_id=unit_id,
        kind=typed.kind,
        abstracts=source_l1_units,
        summary=typed.summary,
        structured_claims=claims,
        closure_id=closure_id,
        closure_spec_revision=1,
        closure_evaluation_id="pending",
        lifecycle="candidate",
        abstraction_method={
            "method": typed.abstraction.method,
            "basis": typed.abstraction.basis,
        },
        source_l1_units=source_l1_units,
        source_turns=typed.source_turn_refs,
        source_sessions=typed.source_session_refs,
    )
    closure_spec = make_closure_spec(
        closure_id=closure_id,
        revision=1,
        target_id=claims[0].claim_id,
        pattern=typed.closure.pattern,
        slots=[
            ClosureSlotSpec(
                slot_id=f"slot-{index:02d}",
                role="evidence",
                bound_unit_id=by_ref[support_ref].revision.memory_unit_id,
                fallback_class="blocked",
            )
            for index, support_ref in enumerate(
                typed.closure.required_support_refs, start=1
            )
        ],
    )
    l1_revisions = [item.revision for item in admitted_l1]
    closure_inputs = ClosureEvaluationInputs(
        evaluated_bundle_id=bundle_id,
        context=ClaimClosureContext(
            l2_unit_id=unit_id,
            claim_id=claims[0].claim_id,
            claim_hash=claims[0].semantic_hash,
            support_unit_ids=claims[0].supporting_l1_units,
            support_scope=source_l1_units,
        ),
        current_revision_ids={
            item.revision.memory_unit_id: item.revision.revision_id
            for item in admitted_l1
        },
        unit_revisions=l1_revisions,
        source_revisions=list(source_revisions),
        evaluator_id="e2e-closure-evaluator",
        evaluator_version="1",
        policy_version="1",
    )
    closure_evaluation = evaluate_closure_spec(closure_spec, closure_inputs)
    if (
        not closure_evaluation.complete
        or closure_evaluation.fallback_allowed
        or not is_closure_evaluation_fresh(
            closure_evaluation, closure_spec, closure_inputs
        )
    ):
        raise ValueError("L2 closure is incomplete, fallback-enabled, or stale")
    active = provisional.model_copy(
        update={
            "closure_evaluation_id": closure_evaluation.evaluation_id,
            "lifecycle": "active",
        }
    )
    revision = make_memory_unit_revision(
        payload=active,
        revision_number=1,
        previous_revision_id=None,
        revision_kind="create",
        transaction_time=transaction_time,
        source_revision_ids=sorted(
            {
                source_id
                for item in l1_revisions
                for source_id in item.source_revision_ids
            }
        ),
        derived_from_revision_ids=sorted(
            item.revision_id for item in l1_revisions
        ),
        producer=producer,
    )
    return ClosedL2Record(
        candidate_ref=proposal.candidate_ref,
        closure_spec=closure_spec,
        closure_evaluation=closure_evaluation,
        revision=revision,
    )


def build_compiler_registry(ontology: OntologyRegistry) -> CompilerRegistryV1:
    concepts = {item.concept_id: item for item in ontology.concepts}

    def ancestors(concept_id: str) -> set[str]:
        result = {concept_id}
        pending = list(concepts[concept_id].parent_concept_ids)
        while pending:
            current = pending.pop()
            if current in result:
                continue
            result.add(current)
            pending.extend(concepts[current].parent_concept_ids)
        return result

    grouped: dict[tuple[str, str, str], dict[str, str]] = {}
    for rule in ontology.predicate_role_constraints:
        if len(rule.allowed_concept_ids) != 1:
            raise ValueError("compiler registry requires one authoritative role type")
        key = (
            _normalized(rule.predicate_surface),
            rule.predicate_sense,
            rule.canonical_operator,
        )
        role_types = grouped.setdefault(key, {})
        required_type = rule.allowed_concept_ids[0]
        existing = role_types.get(rule.role_name)
        if existing is not None and existing != required_type:
            raise ValueError("compiler registry has conflicting predicate role types")
        role_types[rule.role_name] = required_type

    predicate_aliases: dict[str, list[PredicateRegistryEntryV1]] = defaultdict(list)
    for (surface, sense, operator), role_types in sorted(grouped.items()):
        predicate_aliases[surface].append(
            PredicateRegistryEntryV1(
                sense=sense,
                canonical_operator=operator,
                role_types=role_types,
            )
        )
    return CompilerRegistryV1(
        ontology_revision=ontology.revision,
        identity_revision=f"category-only-{ontology.registry_hash[:16]}",
        registry_revision=f"compiler-{ontology.registry_hash[:16]}",
        entity_aliases={},
        entity_types={
            concept_id: sorted(ancestors(concept_id)) for concept_id in concepts
        },
        identity_status={concept_id: "unresolved" for concept_id in concepts},
        predicate_aliases=dict(predicate_aliases),
    )


def commit_authoritative_snapshot(
    *,
    repository_path: Path,
    bundle: MemoryRepresentationBundleV3,
    turn_bundles: Sequence[TurnBundleRevision],
    transaction_time: str,
) -> AuthoritativeSnapshotReceipt:
    sources = {
        item.source_revision_id: item for item in bundle.source_record_revisions
    }
    revisions = {item.revision_id: item for item in bundle.unit_revisions}
    turn_artifacts = [
        make_turn_bundle_history_artifact(
            bundle=turn_bundle,
            source_revisions=[
                sources[item.source_revision_id]
                for item in turn_bundle.source_records
            ],
            unit_revisions=[
                revisions[item] for item in turn_bundle.l1_unit_revision_ids
            ],
        )
        for turn_bundle in turn_bundles
    ]
    bundle_artifact = make_history_artifact(
        artifact_kind="l2_bundle",
        logical_id=bundle.bundle_id,
        revision_id=f"bundle-revision-{canonical_sha256(bundle)[:24]}",
        transaction_time=transaction_time,
        payload={"memory_representation_bundle": bundle.model_dump(mode="json")},
        references=[
            HistoryArtifactReference(
                relation="derived_from",
                artifact_kind="turn_bundle",
                logical_id=item.turn_bundle_id,
                revision_id=item.bundle_revision_id,
            )
            for item in turn_bundles
        ],
    )
    repository = GitMemoryHistoryRepository.initialize(
        repository_path,
        workspace_id="ke-memory-e2e",
        created_at=_timestamp(0),
    )
    expected_head = repository.head_commit()
    artifacts = [*turn_artifacts, bundle_artifact]
    manifest = repository.make_checkpoint(
        artifacts=artifacts,
        transaction_time=transaction_time,
    )
    receipt = repository.commit_checkpoint(
        manifest=manifest,
        artifacts=artifacts,
        expected_head=expected_head,
    )
    verification = repository.verify()
    if verification.status != "valid":
        raise ValueError(
            "authoritative Git history verification failed: "
            + "; ".join(verification.errors)
        )
    return AuthoritativeSnapshotReceipt(
        repository_path=str(repository.repo_path),
        checkpoint_id=receipt.checkpoint_id,
        git_commit=receipt.git_commit,
        previous_git_commit=receipt.previous_git_commit,
        verification_status="valid",
        bundle_history_artifact=bundle_artifact,
    )


def build_evidence_backed_answer(
    *,
    execution: QueryExecutionResultV3,
    bundle: MemoryRepresentationBundleV3,
) -> EvidenceBackedAnswerV1:
    sources = {
        item.source_revision_id: item for item in bundle.source_record_revisions
    }
    evidence: dict[str, EvidenceSpanV2] = {}
    for unit in bundle.l1_units:
        for span in unit.source.evidence_spans:
            existing = evidence.get(span.evidence_id)
            if existing is not None and existing != span:
                raise ValueError("conflicting duplicate evidence definition")
            evidence[span.evidence_id] = span
    resolved: list[EvidenceSpanV2] = []
    for evidence_id in execution.required_evidence_ids:
        span = evidence.get(evidence_id)
        if span is None:
            raise ValueError(f"required evidence is missing: {evidence_id}")
        source = sources.get(span.source_revision_id)
        if source is None:
            raise ValueError(f"evidence source revision is missing: {evidence_id}")
        if source.text[span.char_start : span.char_end] != span.text:
            raise ValueError(f"evidence source offset mismatch: {evidence_id}")
        if hashlib.sha256(span.text.encode("utf-8")).hexdigest() != span.quote_sha256:
            raise ValueError(f"evidence quote hash mismatch: {evidence_id}")
        resolved.append(span)
    return EvidenceBackedAnswerV1(
        query_id=execution.query_id,
        answer_values=execution.answer_values,
        evidence_spans=tuple(resolved),
        closure_complete=execution.closure_complete,
        abstained=execution.abstained,
        fallback_triggered=False,
        authority_sha256=execution.authority.authority_sha256,
    )


def run_e2e_pipeline(
    *,
    turns: Sequence[RawTurnV1],
    l1_producer: L1CandidateProducer,
    l2_producer: L2CandidateProducer,
    query_producer: QueryDraftProducer,
    repository_path: Path,
    question: str,
    ontology_registry: OntologyRegistry | None = None,
) -> EndToEndResultV1:
    ordered_turns = _validate_turns(turns)
    ontology = ontology_registry or build_diagnostic_ontology_registry()
    artifact, source_revisions, extraction_inputs = _make_source_inputs(
        ordered_turns
    )
    producer = ProducerIdentity(
        workflow_run_id="run-e2e-closure",
        producer_id="e2e-pipeline",
        producer_version="1",
    )
    admitted_l1: list[AdmittedL1Record] = []
    seen_candidate_refs: set[str] = set()
    for turn in ordered_turns:
        extraction_input = extraction_inputs[turn.turn_id]
        proposals = l1_producer.produce(extraction_input)
        if not proposals:
            raise ValueError("each turn requires at least one L1 proposal")
        for proposal in proposals:
            if proposal.candidate_ref in seen_candidate_refs:
                raise ValueError("duplicate L1 candidate ref")
            seen_candidate_refs.add(proposal.candidate_ref)
            linked = link_l1_candidate(
                proposal.typed_candidate,
                registry=ontology,
                evidence_spans=[extraction_input.user_evidence],
                canonical_entity_bindings=[],
            )
            if any(item.interpretation != "category" for item in linked.entity_links):
                raise ValueError(
                    "identity-bearing or unresolved L1 candidate is outside category-only scope"
                )
            context = AdmissionContext(
                raw_artifacts=[artifact],
                source_revisions=[extraction_input.user_source],
                source_epistemics=[
                    SourceEpistemicBinding(
                        source_revision_id=extraction_input.user_source.source_revision_id,
                        source_status="user_reported",
                        speaker="user",
                    )
                ],
                identity_bindings=[],
                identity_snapshot_authorities=[],
                current_identity_snapshot_ids=[],
                identity_registry_revision=f"category-only-{ontology.registry_hash[:16]}",
                identity_registry_hash=ontology.registry_hash,
                transaction_time=_timestamp(turn.turn_index * 10 + 2),
                known_lifecycle_candidate_refs=[],
                policy=AdmissionPolicy(
                    policy_id="e2e-category-create",
                    policy_version="1",
                    allow_modalities=["actual"],
                    allow_source_statuses=["user_reported"],
                    require_transaction_time=True,
                ),
            )
            decision = admit_linked_l1(linked, ontology, context)
            admitted_l1.append(
                materialize_admitted_l1(
                    proposal=proposal,
                    linked=linked,
                    decision=decision,
                    context=context,
                    producer=producer,
                )
            )

    turn_bundles: list[TurnBundleRevision] = []
    for turn in ordered_turns:
        extraction_input = extraction_inputs[turn.turn_id]
        members = [item for item in admitted_l1 if item.turn_id == turn.turn_id]
        turn_bundles.append(
            make_turn_bundle_revision(
                turn_bundle_id=f"bundle-{turn.turn_id}",
                revision_number=1,
                previous_revision_id=None,
                session_id=turn.session_id,
                turn_id=turn.turn_id,
                turn_index=turn.turn_index,
                source_records=[
                    TurnSourceRevisionRef(
                        ordinal=0,
                        source_revision_id=extraction_input.user_source.source_revision_id,
                        speaker="user",
                    ),
                    TurnSourceRevisionRef(
                        ordinal=1,
                        source_revision_id=extraction_input.assistant_source.source_revision_id,
                        speaker="assistant",
                    ),
                ],
                extraction_state="complete",
                l1_unit_revision_ids=[item.revision.revision_id for item in members],
                no_memory_reason=None,
                failure_reason=None,
                extractor_id=producer.producer_id,
                extractor_version=producer.producer_version,
                transaction_time=_timestamp(turn.turn_index * 10 + 3),
            )
        )

    bundle_id = f"bundle-e2e-{artifact.content_sha256[:16]}"
    l2_proposals = l2_producer.produce(tuple(admitted_l1))
    if len(l2_proposals) != 1:
        raise ValueError("the minimal pipeline requires exactly one L2 proposal")
    l2_record = materialize_closed_l2(
        proposal=l2_proposals[0],
        admitted_l1=admitted_l1,
        bundle_id=bundle_id,
        source_revisions=source_revisions,
        producer=producer,
        transaction_time=_timestamp(len(ordered_turns) * 10 + 1),
    )
    l1_revisions = [item.revision for item in admitted_l1]
    l1_units = [
        item.payload for item in l1_revisions if isinstance(item.payload, L1MemoryUnitV2)
    ]
    l2_unit = l2_record.revision.payload
    if not isinstance(l2_unit, L2MemoryUnitV2):
        raise ValueError("materialized L2 revision does not contain an L2 payload")
    bundle = MemoryRepresentationBundleV3(
        bundle_id=bundle_id,
        profile=_profile(),
        raw_artifact_revisions=[artifact],
        source_record_revisions=source_revisions,
        unit_revisions=[*l1_revisions, l2_record.revision],
        current_revision_ids={
            item.memory_unit_id: item.revision_id
            for item in [*l1_revisions, l2_record.revision]
        },
        l1_units=l1_units,
        l2_units=[l2_unit],
        closure_specs=[l2_record.closure_spec],
        closure_evaluations=[l2_record.closure_evaluation],
        query_plans=[],
        metadata={
            "closure_evaluator_id": "e2e-closure-evaluator",
            "closure_evaluator_version": "1",
            "closure_policy_version": "1",
        },
    )
    integrity = assess_authoritative_bundle_integrity(bundle)
    if not integrity.valid:
        raise ValueError(
            "authoritative bundle integrity failed: " + "; ".join(integrity.errors)
        )

    commit_time = _timestamp(len(ordered_turns) * 10 + 2)
    snapshot = commit_authoritative_snapshot(
        repository_path=repository_path,
        bundle=bundle,
        turn_bundles=turn_bundles,
        transaction_time=commit_time,
    )
    repository = GitMemoryHistoryRepository(snapshot.repository_path)
    metadata = repository.read_repository_metadata(commit=snapshot.git_commit)
    state = repository.read_state(commit=snapshot.git_commit)
    if state.checkpoint_id != snapshot.checkpoint_id:
        raise ValueError("published checkpoint state does not match commit receipt")
    memory_view = GitMemoryViewRefV1(
        workspace_id=metadata.workspace_id,
        repository_epoch_id=metadata.repository_epoch_id,
        checkpoint_id=snapshot.checkpoint_id,
        git_commit=snapshot.git_commit,
    )
    compiler_registry = build_compiler_registry(ontology)
    query_context = QueryContextV1(
        query_id="query-e2e-1",
        raw_query=question,
        query_time=_timestamp(len(ordered_turns) * 10 + 3),
        current_user_entity_id=None,
        memory_view=memory_view,
        ontology_revision=compiler_registry.ontology_revision,
        identity_revision=compiler_registry.identity_revision,
        compiler_policy_revision="e2e-query-policy-v1",
    )
    compilation = compile_natural_query(
        question=question,
        context=query_context,
        registry=compiler_registry,
        producer=query_producer,
    )
    if compilation.status != "executable" or compilation.plan is None:
        raise ValueError(
            "query compilation abstained: "
            + ",".join([*compilation.blocked_reasons, *compilation.unresolved_slots])
        )
    execution = execute_authoritative_query(
        repository_path=repository_path,
        bundle=bundle,
        bundle_history_artifact=snapshot.bundle_history_artifact,
        turn_bundles=turn_bundles,
        registry=compiler_registry,
        plan=compilation.plan,
    )
    answer = build_evidence_backed_answer(execution=execution, bundle=bundle)
    return EndToEndResultV1(
        bundle=bundle,
        turn_bundles=tuple(turn_bundles),
        snapshot=snapshot,
        compilation=compilation,
        execution=execution,
        answer=answer,
    )
