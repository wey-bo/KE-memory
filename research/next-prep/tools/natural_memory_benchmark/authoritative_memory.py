from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .io import canonical_json_bytes
from .representation_contract import RepresentationProfile
from .semantic_ir import (
    DEFAULT_FALLBACK_ALLOWED_REASONS,
    DEFAULT_FALLBACK_BLOCKED_REASONS,
    ClosurePattern,
    EpistemicBinding,
    Lifecycle,
    LinkBinding,
    MemoryKind,
    Modality,
    Polarity,
    Predicate,
    QueryIntent,
    RoleBinding,
    SourceStatus,
    Speaker,
    TargetLevel,
    TimeBinding,
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_text(value: str) -> str:
    return _sha256_bytes(value.encode("utf-8"))


def canonical_sha256(value: Any) -> str:
    return _sha256_bytes(canonical_json_bytes(value))


def _content_id(prefix: str, value: Any) -> str:
    return f"{prefix}-{canonical_sha256(value)[:24]}"


class RawArtifactRevision(StrictModel):
    schema_version: Literal["raw-artifact-revision-v1"] = "raw-artifact-revision-v1"
    artifact_revision_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    frozen_identity: str = Field(min_length=1)
    official_url: str = Field(min_length=1)
    local_path: str = Field(min_length=1)
    reader: Literal["duckdb", "json"]
    size_bytes: int = Field(ge=1)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


def make_raw_artifact_revision(
    *,
    source_id: str,
    frozen_identity: str,
    official_url: str,
    local_path: str,
    reader: Literal["duckdb", "json"],
    size_bytes: int,
    content_sha256: str,
) -> RawArtifactRevision:
    identity = {
        "source_id": source_id,
        "frozen_identity": frozen_identity,
        "official_url": official_url,
        "local_path": local_path,
        "reader": reader,
        "size_bytes": size_bytes,
        "content_sha256": content_sha256,
    }
    return RawArtifactRevision(
        artifact_revision_id=_content_id("artifact-revision", identity),
        **identity,
    )


RecordKind = Literal["message", "normalized_session", "dialogue_turn", "tool_event"]


class SourceRecordRevision(StrictModel):
    schema_version: Literal["source-record-revision-v1"] = "source-record-revision-v1"
    source_record_id: str = Field(min_length=1)
    source_revision_id: str = Field(min_length=1)
    revision_number: int = Field(ge=1)
    previous_revision_id: str | None = None
    artifact_revision_id: str = Field(min_length=1)
    source_ref: str = Field(min_length=1)
    turn_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    record_kind: RecordKind
    text: str = Field(min_length=1)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    resolver_id: str = Field(min_length=1)
    resolver_version: str = Field(min_length=1)
    transaction_time: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


def make_source_record_revision(
    *,
    source_record_id: str,
    revision_number: int,
    previous_revision_id: str | None,
    artifact_revision_id: str,
    source_ref: str,
    turn_id: str,
    session_id: str,
    record_kind: RecordKind,
    text: str,
    resolver_id: str,
    resolver_version: str,
    transaction_time: str,
    metadata: dict[str, Any] | None = None,
) -> SourceRecordRevision:
    content_sha256 = _sha256_text(text)
    identity = {
        "source_record_id": source_record_id,
        "revision_number": revision_number,
        "previous_revision_id": previous_revision_id,
        "artifact_revision_id": artifact_revision_id,
        "source_ref": source_ref,
        "turn_id": turn_id,
        "session_id": session_id,
        "record_kind": record_kind,
        "content_sha256": content_sha256,
        "resolver_id": resolver_id,
        "resolver_version": resolver_version,
    }
    return SourceRecordRevision(
        source_revision_id=_content_id("source-revision", identity),
        text=text,
        transaction_time=transaction_time,
        metadata=metadata or {},
        **identity,
    )


class EvidenceSpanV2(StrictModel):
    schema_version: Literal["semantic-ir-evidence-span-v2"] = "semantic-ir-evidence-span-v2"
    evidence_id: str = Field(min_length=1)
    source_revision_id: str = Field(min_length=1)
    turn_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)
    text: str = Field(min_length=1)
    quote_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    offset_unit: Literal["unicode_codepoint"] = "unicode_codepoint"

    @model_validator(mode="after")
    def validate_offsets(self) -> "EvidenceSpanV2":
        if self.char_end < self.char_start:
            raise ValueError("char_end must be greater than or equal to char_start")
        return self


def make_evidence_span(
    *,
    evidence_id: str,
    source_revision: SourceRecordRevision,
    turn_id: str,
    session_id: str,
    char_start: int,
    char_end: int,
    text: str,
) -> EvidenceSpanV2:
    return EvidenceSpanV2(
        evidence_id=evidence_id,
        source_revision_id=source_revision.source_revision_id,
        turn_id=turn_id,
        session_id=session_id,
        char_start=char_start,
        char_end=char_end,
        text=text,
        quote_sha256=_sha256_text(text),
    )


class SourceBindingV2(StrictModel):
    speaker: Speaker
    source_status: SourceStatus
    evidence_spans: list[EvidenceSpanV2] = Field(min_length=1)


class L1MemoryUnitV2(StrictModel):
    schema_version: Literal["semantic-ir-l1-v2"] = "semantic-ir-l1-v2"
    unit_id: str = Field(min_length=1)
    level: Literal["L1"] = "L1"
    kind: Literal["event", "state", "preference", "task", "attribute"]
    predicate: Predicate
    roles: list[RoleBinding] = Field(min_length=1)
    modality: Modality = "actual"
    polarity: Polarity = "positive"
    time: TimeBinding = Field(default_factory=TimeBinding)
    source: SourceBindingV2
    epistemic: EpistemicBinding = Field(default_factory=EpistemicBinding)
    links: LinkBinding = Field(default_factory=LinkBinding)
    lifecycle: Lifecycle = "active"


class AggregateClaim(StrictModel):
    function: Literal["count_distinct"]
    source_role: str = Field(min_length=1)
    value: int = Field(ge=0)
    identity_basis: list[str] = Field(min_length=1)


class L2StructuredClaim(StrictModel):
    schema_version: Literal["semantic-ir-l2-claim-v1"] = "semantic-ir-l2-claim-v1"
    claim_id: str = Field(min_length=1)
    predicate: Predicate
    roles: list[RoleBinding] = Field(min_length=1)
    modality: Modality = "actual"
    polarity: Polarity = "positive"
    time: TimeBinding = Field(default_factory=TimeBinding)
    supporting_l1_units: list[str] = Field(min_length=1)
    aggregate: AggregateClaim | None = None

    @property
    def semantic_hash(self) -> str:
        return canonical_sha256(self)


class L2MemoryUnitV2(StrictModel):
    schema_version: Literal["semantic-ir-l2-v2"] = "semantic-ir-l2-v2"
    unit_id: str = Field(min_length=1)
    level: Literal["L2"] = "L2"
    kind: Literal["task", "preference_profile", "project", "habit", "long_running_state", "summary_event"]
    abstracts: list[str] = Field(min_length=1)
    summary: str = Field(min_length=1)
    display_assertions: list[str] = Field(default_factory=list)
    structured_claims: list[L2StructuredClaim] = Field(default_factory=list)
    closure_id: str = Field(min_length=1)
    closure_spec_revision: int = Field(ge=1)
    closure_evaluation_id: str = Field(min_length=1)
    lifecycle: Lifecycle = "candidate"
    valid_time: str | None = None
    abstraction_method: dict[str, str | None] = Field(default_factory=dict)
    source_l1_units: list[str] = Field(min_length=1)
    source_turns: list[str] = Field(min_length=1)
    source_sessions: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_provenance(self) -> "L2MemoryUnitV2":
        missing = set(self.abstracts) - set(self.source_l1_units)
        if missing:
            raise ValueError(f"source_l1_units must include all abstracts: {sorted(missing)}")
        return self


class ExactTimeConstraint(StrictModel):
    event_time: str | None = None
    valid_time: str | None = None
    transaction_time: str | None = None


AnswerKind = Literal["fact", "evidence_set", "count"]


class AuthoritativeQueryPlan(StrictModel):
    schema_version: Literal["authoritative-query-plan-v1"] = "authoritative-query-plan-v1"
    query_id: str = Field(min_length=1)
    intent: QueryIntent
    target_level: TargetLevel
    answer_kind: AnswerKind = "evidence_set"
    entity_ids: list[str] = Field(default_factory=list)
    predicate_sense: str | None = None
    canonical_operator: str | None = None
    role_constraints: list[RoleBinding] = Field(default_factory=list)
    time_constraint: ExactTimeConstraint | None = None
    modality: Modality | None = None
    polarity: Polarity | None = None
    source_status_constraints: list[SourceStatus] = Field(default_factory=list)
    lifecycle: Lifecycle | None = None
    closure_id: str | None = None
    closure_spec_revision: int | None = Field(default=None, ge=1)
    fallback_allowed_reasons: list[str] = Field(default_factory=lambda: list(DEFAULT_FALLBACK_ALLOWED_REASONS))
    fallback_blocked_reasons: list[str] = Field(default_factory=lambda: list(DEFAULT_FALLBACK_BLOCKED_REASONS))

    @model_validator(mode="after")
    def validate_closure_reference(self) -> "AuthoritativeQueryPlan":
        if (self.closure_id is None) != (self.closure_spec_revision is None):
            raise ValueError("closure_id and closure_spec_revision must be set together")
        return self


class AuthoritativeQueryResult(StrictModel):
    schema_version: Literal["semantic-ir-query-result-v1"] = "semantic-ir-query-result-v1"
    query_id: str = Field(min_length=1)
    matched_unit_ids: list[str] = Field(default_factory=list)
    required_evidence_ids: list[str] = Field(default_factory=list)
    closure_complete: bool = False
    abstained: bool = True
    missing_slots: list[str] = Field(default_factory=list)
    fallback_allowed: bool = False
    reason: str = Field(min_length=1)


class ProducerIdentity(StrictModel):
    workflow_run_id: str = Field(min_length=1)
    producer_id: str = Field(min_length=1)
    producer_version: str = Field(min_length=1)


RevisionKind = Literal["create", "correction", "lifecycle_update", "forget", "reextract"]
MemoryPayload = L1MemoryUnitV2 | L2MemoryUnitV2


class MemoryUnitRevision(StrictModel):
    schema_version: Literal["memory-unit-revision-v1"] = "memory-unit-revision-v1"
    memory_unit_id: str = Field(min_length=1)
    revision_id: str = Field(min_length=1)
    revision_number: int = Field(ge=1)
    previous_revision_id: str | None = None
    revision_kind: RevisionKind
    transaction_time: str = Field(min_length=1)
    payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    payload: MemoryPayload
    source_revision_ids: list[str] = Field(default_factory=list)
    derived_from_revision_ids: list[str] = Field(default_factory=list)
    producer: ProducerIdentity


def make_memory_unit_revision(
    *,
    payload: MemoryPayload,
    revision_number: int,
    previous_revision_id: str | None,
    revision_kind: RevisionKind,
    transaction_time: str,
    source_revision_ids: list[str],
    derived_from_revision_ids: list[str],
    producer: ProducerIdentity,
) -> MemoryUnitRevision:
    payload_hash = canonical_sha256(payload)
    identity = {
        "memory_unit_id": payload.unit_id,
        "revision_number": revision_number,
        "previous_revision_id": previous_revision_id,
        "revision_kind": revision_kind,
        "payload_sha256": payload_hash,
        "source_revision_ids": sorted(source_revision_ids),
        "derived_from_revision_ids": sorted(derived_from_revision_ids),
        "producer": producer.model_dump(mode="json"),
    }
    return MemoryUnitRevision(
        revision_id=_content_id("unit-revision", identity),
        transaction_time=transaction_time,
        payload=payload,
        producer=producer,
        **{key: value for key, value in identity.items() if key != "producer"},
    )


class ClosureSlotSpec(StrictModel):
    slot_id: str = Field(min_length=1)
    role: str = Field(min_length=1)
    required: bool = True
    bound_unit_id: str | None = None
    fallback_class: Literal["blocked", "candidate_only"] = "blocked"


class ClosureSpec(StrictModel):
    schema_version: Literal["semantic-ir-closure-spec-v1"] = "semantic-ir-closure-spec-v1"
    closure_id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    target_id: str = Field(min_length=1)
    pattern: ClosurePattern
    slots: list[ClosureSlotSpec] = Field(min_length=1)
    spec_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


def make_closure_spec(
    *,
    closure_id: str,
    revision: int,
    target_id: str,
    pattern: ClosurePattern,
    slots: list[ClosureSlotSpec],
) -> ClosureSpec:
    semantic = {
        "closure_id": closure_id,
        "revision": revision,
        "target_id": target_id,
        "pattern": pattern,
        "slots": [slot.model_dump(mode="json") for slot in slots],
    }
    return ClosureSpec(spec_hash=canonical_sha256(semantic), **semantic)


class ClaimClosureContext(StrictModel):
    context_kind: Literal["claim"] = "claim"
    l2_unit_id: str = Field(min_length=1)
    claim_id: str = Field(min_length=1)
    claim_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    support_unit_ids: list[str]
    support_scope: list[str]


class QueryClosureContext(StrictModel):
    context_kind: Literal["query"] = "query"
    query_plan: AuthoritativeQueryPlan
    query_scope: list[str]
    available_unit_ids: list[str]

    @model_validator(mode="after")
    def normalize_scope(self) -> "QueryClosureContext":
        object.__setattr__(self, "query_scope", sorted(dict.fromkeys(self.query_scope)))
        object.__setattr__(self, "available_unit_ids", sorted(dict.fromkeys(self.available_unit_ids)))
        return self


ClosureContext = ClaimClosureContext | QueryClosureContext


class ClosureEvaluationInputs(StrictModel):
    evaluated_bundle_id: str = Field(min_length=1)
    context: ClosureContext
    current_revision_ids: dict[str, str]
    unit_revisions: list[MemoryUnitRevision]
    source_revisions: list[SourceRecordRevision]
    evaluator_id: str = Field(min_length=1)
    evaluator_version: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)

    @classmethod
    def for_query(
        cls,
        bundle: "MemoryRepresentationBundleV3",
        plan: AuthoritativeQueryPlan,
    ) -> "ClosureEvaluationInputs":
        matched_ids, _ = _matched_units_and_claims(plan, bundle)
        return cls(
            evaluated_bundle_id=bundle.bundle_id,
            context=QueryClosureContext(
                query_plan=plan,
                query_scope=list(bundle.query_unit_scopes.get(plan.query_id, [])),
                available_unit_ids=matched_ids,
            ),
            current_revision_ids=bundle.current_revision_ids,
            unit_revisions=bundle.unit_revisions,
            source_revisions=bundle.source_record_revisions,
            evaluator_id=str(bundle.metadata.get("closure_evaluator_id", "closure-evaluator")),
            evaluator_version=str(bundle.metadata.get("closure_evaluator_version", "1")),
            policy_version=str(bundle.metadata.get("closure_policy_version", "1")),
        )

    @classmethod
    def for_claim(
        cls,
        bundle: "MemoryRepresentationBundleV3",
        l2: L2MemoryUnitV2,
        claim: L2StructuredClaim,
    ) -> "ClosureEvaluationInputs":
        return cls(
            evaluated_bundle_id=bundle.bundle_id,
            context=ClaimClosureContext(
                l2_unit_id=l2.unit_id,
                claim_id=claim.claim_id,
                claim_hash=claim.semantic_hash,
                support_unit_ids=list(claim.supporting_l1_units),
                support_scope=list(l2.source_l1_units),
            ),
            current_revision_ids=bundle.current_revision_ids,
            unit_revisions=bundle.unit_revisions,
            source_revisions=bundle.source_record_revisions,
            evaluator_id=str(bundle.metadata.get("closure_evaluator_id", "closure-evaluator")),
            evaluator_version=str(bundle.metadata.get("closure_evaluator_version", "1")),
            policy_version=str(bundle.metadata.get("closure_policy_version", "1")),
        )


class DependencyFingerprint(StrictModel):
    reference_id: str = Field(min_length=1)
    reference_kind: Literal["unit_revision", "source_revision"]
    revision_id: str = Field(min_length=1)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ClosureSlotResult(StrictModel):
    slot_id: str = Field(min_length=1)
    role: str = Field(min_length=1)
    bound_unit_id: str | None = None
    bound_unit_revision_id: str | None = None
    satisfied: bool


ClosureReasonCode = Literal["complete", "missing_required_slot"]


class ClosureEvaluation(StrictModel):
    schema_version: Literal["semantic-ir-closure-evaluation-v1"] = "semantic-ir-closure-evaluation-v1"
    evaluation_id: str = Field(min_length=1)
    closure_id: str = Field(min_length=1)
    spec_revision: int = Field(ge=1)
    spec_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    evaluator_id: str = Field(min_length=1)
    evaluator_version: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    evaluated_bundle_id: str = Field(min_length=1)
    context: ClosureContext
    dependency_hashes: list[DependencyFingerprint]
    input_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    slot_results: list[ClosureSlotResult]
    complete: bool
    fallback_allowed: bool
    reason_code: ClosureReasonCode
    result_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


def _context_available_ids(context: ClosureContext) -> set[str]:
    if isinstance(context, QueryClosureContext):
        return set(context.available_unit_ids)
    return set(context.support_unit_ids)


def _dependency_fingerprints(
    spec: ClosureSpec,
    inputs: ClosureEvaluationInputs,
) -> list[DependencyFingerprint]:
    revisions_by_id = {revision.revision_id: revision for revision in inputs.unit_revisions}
    sources_by_id = {source.source_revision_id: source for source in inputs.source_revisions}
    fingerprints: list[DependencyFingerprint] = []
    seen_sources: set[str] = set()
    for unit_id in sorted({slot.bound_unit_id for slot in spec.slots if slot.bound_unit_id}):
        revision_id = inputs.current_revision_ids.get(unit_id)
        revision = revisions_by_id.get(revision_id or "")
        if revision is None:
            continue
        fingerprints.append(
            DependencyFingerprint(
                reference_id=unit_id,
                reference_kind="unit_revision",
                revision_id=revision.revision_id,
                content_sha256=revision.payload_sha256,
            )
        )
        for source_revision_id in revision.source_revision_ids:
            if source_revision_id in seen_sources:
                continue
            source = sources_by_id.get(source_revision_id)
            if source is None:
                continue
            seen_sources.add(source_revision_id)
            fingerprints.append(
                DependencyFingerprint(
                    reference_id=source.source_record_id,
                    reference_kind="source_revision",
                    revision_id=source.source_revision_id,
                    content_sha256=source.content_sha256,
                )
            )
    return sorted(fingerprints, key=lambda item: (item.reference_kind, item.reference_id, item.revision_id))


def evaluate_closure_spec(
    spec: ClosureSpec,
    inputs: ClosureEvaluationInputs,
) -> ClosureEvaluation:
    available = _context_available_ids(inputs.context)
    revisions_by_id = {revision.revision_id: revision for revision in inputs.unit_revisions}
    slot_results: list[ClosureSlotResult] = []
    missing_specs: list[ClosureSlotSpec] = []
    for slot in spec.slots:
        revision_id = inputs.current_revision_ids.get(slot.bound_unit_id or "")
        revision_exists = revision_id in revisions_by_id
        satisfied = bool(slot.bound_unit_id and slot.bound_unit_id in available and revision_exists)
        slot_results.append(
            ClosureSlotResult(
                slot_id=slot.slot_id,
                role=slot.role,
                bound_unit_id=slot.bound_unit_id,
                bound_unit_revision_id=revision_id if satisfied else None,
                satisfied=satisfied,
            )
        )
        if slot.required and not satisfied:
            missing_specs.append(slot)
    complete = not missing_specs
    fallback_allowed = bool(missing_specs) and all(
        slot.fallback_class == "candidate_only" for slot in missing_specs
    )
    reason_code: ClosureReasonCode = "complete" if complete else "missing_required_slot"
    dependency_hashes = _dependency_fingerprints(spec, inputs)
    input_payload = {
        "closure_id": spec.closure_id,
        "spec_revision": spec.revision,
        "spec_hash": spec.spec_hash,
        "evaluator_id": inputs.evaluator_id,
        "evaluator_version": inputs.evaluator_version,
        "policy_version": inputs.policy_version,
        "evaluated_bundle_id": inputs.evaluated_bundle_id,
        "context": inputs.context.model_dump(mode="json"),
        "dependency_hashes": [item.model_dump(mode="json") for item in dependency_hashes],
    }
    input_fingerprint = canonical_sha256(input_payload)
    result_payload = {
        "slot_results": [item.model_dump(mode="json") for item in slot_results],
        "complete": complete,
        "fallback_allowed": fallback_allowed,
        "reason_code": reason_code,
    }
    return ClosureEvaluation(
        evaluation_id=f"closure-evaluation-{input_fingerprint[:24]}",
        closure_id=spec.closure_id,
        spec_revision=spec.revision,
        spec_hash=spec.spec_hash,
        evaluator_id=inputs.evaluator_id,
        evaluator_version=inputs.evaluator_version,
        policy_version=inputs.policy_version,
        evaluated_bundle_id=inputs.evaluated_bundle_id,
        context=inputs.context,
        dependency_hashes=dependency_hashes,
        input_fingerprint=input_fingerprint,
        slot_results=slot_results,
        complete=complete,
        fallback_allowed=fallback_allowed,
        reason_code=reason_code,
        result_hash=canonical_sha256(result_payload),
    )


def is_closure_evaluation_fresh(
    evaluation: ClosureEvaluation,
    spec: ClosureSpec,
    inputs: ClosureEvaluationInputs,
) -> bool:
    recomputed = evaluate_closure_spec(spec, inputs)
    return (
        evaluation.evaluation_id == recomputed.evaluation_id
        and evaluation.closure_id == recomputed.closure_id
        and evaluation.spec_revision == recomputed.spec_revision
        and evaluation.spec_hash == recomputed.spec_hash
        and evaluation.evaluator_id == recomputed.evaluator_id
        and evaluation.evaluator_version == recomputed.evaluator_version
        and evaluation.policy_version == recomputed.policy_version
        and evaluation.evaluated_bundle_id == recomputed.evaluated_bundle_id
        and evaluation.context == recomputed.context
        and evaluation.dependency_hashes == recomputed.dependency_hashes
        and evaluation.input_fingerprint == recomputed.input_fingerprint
        and evaluation.result_hash == recomputed.result_hash
        and evaluation.slot_results == recomputed.slot_results
        and evaluation.complete == recomputed.complete
        and evaluation.fallback_allowed == recomputed.fallback_allowed
        and evaluation.reason_code == recomputed.reason_code
    )


class MemoryRepresentationBundleV3(StrictModel):
    schema_version: Literal["memory-representation-bundle-v3"] = "memory-representation-bundle-v3"
    bundle_id: str = Field(min_length=1)
    profile: RepresentationProfile
    raw_artifact_revisions: list[RawArtifactRevision]
    source_record_revisions: list[SourceRecordRevision]
    unit_revisions: list[MemoryUnitRevision]
    current_revision_ids: dict[str, str]
    l1_units: list[L1MemoryUnitV2]
    l2_units: list[L2MemoryUnitV2]
    closure_specs: list[ClosureSpec]
    closure_evaluations: list[ClosureEvaluation]
    query_plans: list[AuthoritativeQueryPlan]
    query_unit_scopes: dict[str, list[str]] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AuthoritativeIntegrityReport(StrictModel):
    schema_version: Literal["authoritative-memory-integrity-report-v1"] = (
        "authoritative-memory-integrity-report-v1"
    )
    bundle_id: str
    valid: bool
    errors: list[str]
    metrics: dict[str, int]


def _duplicate_id_errors(name: str, ids: list[str]) -> list[str]:
    duplicates = sorted({item for item in ids if ids.count(item) > 1})
    return [f"duplicate {name} id {item}" for item in duplicates]


def _revision_chain_errors(
    *,
    kind: str,
    logical_id: str,
    revisions: list[Any],
    revision_id_field: str,
    previous_field: str,
    number_field: str,
) -> list[str]:
    errors: list[str] = []
    ordered = sorted(revisions, key=lambda item: getattr(item, number_field))
    children: dict[str, int] = {}
    for revision in ordered:
        parent = getattr(revision, previous_field)
        if parent:
            children[parent] = children.get(parent, 0) + 1
    if any(count > 1 for count in children.values()):
        errors.append(f"{kind} {logical_id} revision chain has a branch")
    for index, revision in enumerate(ordered, start=1):
        number = getattr(revision, number_field)
        revision_id = getattr(revision, revision_id_field)
        if number != index:
            errors.append(f"{kind} {logical_id} revision chain has a gap at {revision_id}")
        expected_parent = None if index == 1 else getattr(ordered[index - 2], revision_id_field)
        if getattr(revision, previous_field) != expected_parent:
            errors.append(f"{kind} {logical_id} revision {revision_id} has wrong parent")
    return errors


def _evidence_errors(
    bundle: MemoryRepresentationBundleV3,
    l1: L1MemoryUnitV2,
) -> list[str]:
    errors: list[str] = []
    sources = {source.source_revision_id: source for source in bundle.source_record_revisions}
    for span in l1.source.evidence_spans:
        source = sources.get(span.source_revision_id)
        if source is None:
            errors.append(f"evidence {span.evidence_id} references missing source revision {span.source_revision_id}")
            continue
        if span.turn_id != source.turn_id or span.session_id != source.session_id:
            errors.append(f"evidence {span.evidence_id} source coordinates do not match source revision")
        if span.quote_sha256 != _sha256_text(span.text):
            errors.append(f"evidence {span.evidence_id} quote hash mismatch")
        if source.text[span.char_start : span.char_end] != span.text:
            errors.append(f"evidence {span.evidence_id} quote slice mismatch")
    return errors


def _find_spec(
    bundle: MemoryRepresentationBundleV3,
    closure_id: str,
    revision: int,
) -> ClosureSpec | None:
    return next(
        (
            spec
            for spec in bundle.closure_specs
            if spec.closure_id == closure_id and spec.revision == revision
        ),
        None,
    )


def _find_query_evaluation(
    bundle: MemoryRepresentationBundleV3,
    plan: AuthoritativeQueryPlan,
) -> ClosureEvaluation | None:
    return next(
        (
            evaluation
            for evaluation in bundle.closure_evaluations
            if evaluation.closure_id == plan.closure_id
            and evaluation.spec_revision == plan.closure_spec_revision
            and isinstance(evaluation.context, QueryClosureContext)
            and evaluation.context.query_plan.query_id == plan.query_id
        ),
        None,
    )


def assess_authoritative_bundle_integrity(
    bundle: MemoryRepresentationBundleV3,
) -> AuthoritativeIntegrityReport:
    errors: list[str] = []
    errors.extend(
        _duplicate_id_errors(
            "artifact revision",
            [item.artifact_revision_id for item in bundle.raw_artifact_revisions],
        )
    )
    errors.extend(
        _duplicate_id_errors(
            "source revision",
            [item.source_revision_id for item in bundle.source_record_revisions],
        )
    )
    errors.extend(
        _duplicate_id_errors("unit revision", [item.revision_id for item in bundle.unit_revisions])
    )
    errors.extend(
        _duplicate_id_errors(
            "closure evaluation",
            [item.evaluation_id for item in bundle.closure_evaluations],
        )
    )
    artifacts = {item.artifact_revision_id: item for item in bundle.raw_artifact_revisions}
    sources = {item.source_revision_id: item for item in bundle.source_record_revisions}
    revisions = {item.revision_id: item for item in bundle.unit_revisions}
    l1_by_id = {item.unit_id: item for item in bundle.l1_units}
    l2_by_id = {item.unit_id: item for item in bundle.l2_units}
    all_units = {**l1_by_id, **l2_by_id}

    source_groups: dict[str, list[SourceRecordRevision]] = {}
    for source in bundle.source_record_revisions:
        source_groups.setdefault(source.source_record_id, []).append(source)
        if source.artifact_revision_id not in artifacts:
            errors.append(
                f"source revision {source.source_revision_id} references missing artifact {source.artifact_revision_id}"
            )
        if source.content_sha256 != _sha256_text(source.text):
            errors.append(f"source revision {source.source_revision_id} content hash mismatch")
    for source_id, group in source_groups.items():
        errors.extend(
            _revision_chain_errors(
                kind="source record",
                logical_id=source_id,
                revisions=group,
                revision_id_field="source_revision_id",
                previous_field="previous_revision_id",
                number_field="revision_number",
            )
        )

    revision_groups: dict[str, list[MemoryUnitRevision]] = {}
    for revision in bundle.unit_revisions:
        revision_groups.setdefault(revision.memory_unit_id, []).append(revision)
        if revision.payload.unit_id != revision.memory_unit_id:
            errors.append(f"unit revision {revision.revision_id} payload unit id mismatch")
        if revision.payload_sha256 != canonical_sha256(revision.payload):
            errors.append(f"unit revision {revision.revision_id} payload hash mismatch")
        for source_revision_id in revision.source_revision_ids:
            if source_revision_id not in sources:
                errors.append(
                    f"unit revision {revision.revision_id} references missing source revision {source_revision_id}"
                )
        for parent_revision_id in revision.derived_from_revision_ids:
            if parent_revision_id not in revisions:
                errors.append(
                    f"unit revision {revision.revision_id} references missing derived revision {parent_revision_id}"
                )
    for unit_id, group in revision_groups.items():
        errors.extend(
            _revision_chain_errors(
                kind="memory unit",
                logical_id=unit_id,
                revisions=group,
                revision_id_field="revision_id",
                previous_field="previous_revision_id",
                number_field="revision_number",
            )
        )

    child_ids = {
        revision.previous_revision_id
        for revision in bundle.unit_revisions
        if revision.previous_revision_id is not None
    }
    for unit_id, revision_id in bundle.current_revision_ids.items():
        revision = revisions.get(revision_id)
        if revision is None:
            errors.append(f"current pointer {unit_id} references missing revision {revision_id}")
            continue
        if revision.memory_unit_id != unit_id:
            errors.append(f"current pointer {unit_id} references wrong-unit revision {revision_id}")
        if revision_id in child_ids:
            errors.append(f"current pointer {unit_id} references non-leaf revision {revision_id}")
        view = all_units.get(unit_id)
        if view is None:
            errors.append(f"current pointer {unit_id} has no materialized view")
        elif canonical_json_bytes(view) != canonical_json_bytes(revision.payload):
            errors.append(f"current view {unit_id} differs from selected revision payload")
    for unit_id in all_units:
        if unit_id not in bundle.current_revision_ids:
            errors.append(f"current view {unit_id} has no current revision pointer")

    for l1 in bundle.l1_units:
        errors.extend(_evidence_errors(bundle, l1))
        for link_name in ("same_as", "supersedes", "conflicts_with", "derived_from"):
            for target_id in getattr(l1.links, link_name):
                if target_id not in all_units:
                    errors.append(f"l1 {l1.unit_id} {link_name} references missing unit {target_id}")

    claim_ids: list[str] = []
    evaluations = {item.evaluation_id: item for item in bundle.closure_evaluations}
    for l2 in bundle.l2_units:
        local_claim_ids = [claim.claim_id for claim in l2.structured_claims]
        for duplicate_error in _duplicate_id_errors("structured claim", local_claim_ids):
            errors.append(f"l2 {l2.unit_id} {duplicate_error}")
        claim_ids.extend(local_claim_ids)
        source_set = set(l2.source_l1_units)
        for source_id in source_set:
            if source_id not in l1_by_id:
                errors.append(f"l2 {l2.unit_id} references missing L1 unit {source_id}")
        spec = _find_spec(bundle, l2.closure_id, l2.closure_spec_revision)
        if spec is None:
            errors.append(f"l2 {l2.unit_id} references missing closure spec {l2.closure_id}")
        evaluation = evaluations.get(l2.closure_evaluation_id)
        if evaluation is None:
            errors.append(f"active l2 {l2.unit_id} references missing closure evaluation")
            continue
        if not isinstance(evaluation.context, ClaimClosureContext):
            errors.append(f"active l2 {l2.unit_id} must reference a claim-context closure evaluation")
            continue
        claim = next(
            (item for item in l2.structured_claims if item.claim_id == evaluation.context.claim_id),
            None,
        )
        if claim is None:
            errors.append(f"active l2 {l2.unit_id} closure evaluation references missing structured claim")
            continue
        for support_id in claim.supporting_l1_units:
            if support_id not in source_set:
                errors.append(f"l2 {l2.unit_id} claim support {support_id} is outside source_l1_units")
        if spec is not None:
            current_inputs = ClosureEvaluationInputs.for_claim(bundle, l2, claim)
            fresh = is_closure_evaluation_fresh(evaluation, spec, current_inputs)
            resolved_revision_ids = {
                item.bound_unit_revision_id
                for item in evaluation.slot_results
                if item.satisfied and item.bound_unit_revision_id
            }
            support_revision_ids = {
                bundle.current_revision_ids.get(unit_id) for unit_id in claim.supporting_l1_units
            }
            if not support_revision_ids.issubset(resolved_revision_ids):
                errors.append(f"l2 {l2.unit_id} claim support is outside resolved closure revisions")
            if l2.lifecycle == "active" and not fresh:
                errors.append(f"active l2 {l2.unit_id} has stale closure evaluation")
            if l2.lifecycle == "active" and not evaluation.complete:
                errors.append(f"active l2 {l2.unit_id} has incomplete closure evaluation")

        current_revision = revisions.get(bundle.current_revision_ids.get(l2.unit_id, ""))
        if current_revision is not None:
            pinned = set(current_revision.derived_from_revision_ids)
            required = {
                bundle.current_revision_ids.get(unit_id) for unit_id in l2.source_l1_units
            }
            if not required.issubset(pinned):
                errors.append(f"l2 {l2.unit_id} does not pin all source L1 revisions")

    errors.extend(_duplicate_id_errors("structured claim", claim_ids))
    for spec in bundle.closure_specs:
        semantic = {
            "closure_id": spec.closure_id,
            "revision": spec.revision,
            "target_id": spec.target_id,
            "pattern": spec.pattern,
            "slots": [slot.model_dump(mode="json") for slot in spec.slots],
        }
        if spec.spec_hash != canonical_sha256(semantic):
            errors.append(f"closure spec {spec.closure_id}@{spec.revision} hash mismatch")
    for plan in bundle.query_plans:
        if plan.closure_id is None or plan.closure_spec_revision is None:
            continue
        spec = _find_spec(bundle, plan.closure_id, plan.closure_spec_revision)
        if spec is None:
            errors.append(f"query {plan.query_id} references missing closure spec {plan.closure_id}")
            continue
        evaluation = _find_query_evaluation(bundle, plan)
        if evaluation is None:
            errors.append(f"query {plan.query_id} references missing query closure evaluation")
            continue
        inputs = ClosureEvaluationInputs.for_query(bundle, plan)
        if not is_closure_evaluation_fresh(evaluation, spec, inputs):
            errors.append(f"query {plan.query_id} has stale query closure evaluation")
    query_ids = {plan.query_id for plan in bundle.query_plans}
    for query_id, scope in bundle.query_unit_scopes.items():
        if query_id not in query_ids:
            errors.append(f"query scope references missing query {query_id}")
        for unit_id in scope:
            if unit_id not in all_units:
                errors.append(f"query scope {query_id} references missing unit {unit_id}")

    unique_errors = list(dict.fromkeys(errors))
    return AuthoritativeIntegrityReport(
        bundle_id=bundle.bundle_id,
        valid=not unique_errors,
        errors=unique_errors,
        metrics={
            "raw_artifact_revision_count": len(bundle.raw_artifact_revisions),
            "source_record_revision_count": len(bundle.source_record_revisions),
            "unit_revision_count": len(bundle.unit_revisions),
            "l1_unit_count": len(bundle.l1_units),
            "l2_unit_count": len(bundle.l2_units),
            "closure_spec_count": len(bundle.closure_specs),
            "closure_evaluation_count": len(bundle.closure_evaluations),
            "query_plan_count": len(bundle.query_plans),
        },
    )


def _time_matches(constraint: ExactTimeConstraint | None, value: TimeBinding) -> bool:
    if constraint is None:
        return True
    for field in ("event_time", "valid_time", "transaction_time"):
        expected = getattr(constraint, field)
        if expected is not None and getattr(value, field) != expected:
            return False
    return True


def _role_matches(roles: list[RoleBinding], constraint: RoleBinding) -> bool:
    return any(role == constraint for role in roles)


def _semantic_matches(
    plan: AuthoritativeQueryPlan,
    *,
    predicate: Predicate,
    roles: list[RoleBinding],
    modality: Modality,
    polarity: Polarity,
    time: TimeBinding,
) -> bool:
    if plan.canonical_operator and predicate.canonical_operator != plan.canonical_operator:
        return False
    if plan.predicate_sense and predicate.sense != plan.predicate_sense:
        return False
    if plan.modality and modality != plan.modality:
        return False
    if plan.polarity and polarity != plan.polarity:
        return False
    if not _time_matches(plan.time_constraint, time):
        return False
    entity_ids = {role.entity_id for role in roles}
    if plan.entity_ids and not set(plan.entity_ids).issubset(entity_ids):
        return False
    if plan.role_constraints and not all(_role_matches(roles, item) for item in plan.role_constraints):
        return False
    return True


def _plan_has_semantic_constraints(plan: AuthoritativeQueryPlan) -> bool:
    return bool(
        plan.entity_ids
        or plan.predicate_sense
        or plan.canonical_operator
        or plan.role_constraints
        or plan.time_constraint
        or plan.modality
        or plan.polarity
        or plan.source_status_constraints
        or plan.answer_kind == "count"
    )


def _matched_units_and_claims(
    plan: AuthoritativeQueryPlan,
    bundle: MemoryRepresentationBundleV3,
) -> tuple[list[str], dict[str, list[L2StructuredClaim]]]:
    scope = set(bundle.query_unit_scopes.get(plan.query_id, []))
    matched_ids: list[str] = []
    matched_claims: dict[str, list[L2StructuredClaim]] = {}
    if plan.target_level in {"L1", "both"}:
        for unit in bundle.l1_units:
            if scope and unit.unit_id not in scope:
                continue
            if plan.lifecycle and unit.lifecycle != plan.lifecycle:
                continue
            if plan.source_status_constraints and unit.source.source_status not in plan.source_status_constraints:
                continue
            if _semantic_matches(
                plan,
                predicate=unit.predicate,
                roles=unit.roles,
                modality=unit.modality,
                polarity=unit.polarity,
                time=unit.time,
            ):
                matched_ids.append(unit.unit_id)
    if plan.target_level in {"L2", "both"}:
        for unit in bundle.l2_units:
            if scope and unit.unit_id not in scope:
                continue
            if plan.lifecycle and unit.lifecycle != plan.lifecycle:
                continue
            claims = [
                claim
                for claim in unit.structured_claims
                if _semantic_matches(
                    plan,
                    predicate=claim.predicate,
                    roles=claim.roles,
                    modality=claim.modality,
                    polarity=claim.polarity,
                    time=claim.time,
                )
            ]
            if claims:
                matched_ids.append(unit.unit_id)
                matched_claims[unit.unit_id] = claims
            elif not _plan_has_semantic_constraints(plan) and not unit.structured_claims:
                matched_ids.append(unit.unit_id)
    return matched_ids, matched_claims


def matched_claim_ids_for_query(
    plan: AuthoritativeQueryPlan,
    bundle: MemoryRepresentationBundleV3,
) -> list[str]:
    _, matched_claims = _matched_units_and_claims(plan, bundle)
    return [
        claim.claim_id
        for claims in matched_claims.values()
        for claim in claims
    ]


def _evidence_for_l1_ids(
    l1_ids: list[str],
    bundle: MemoryRepresentationBundleV3,
) -> list[str]:
    l1_by_id = {unit.unit_id: unit for unit in bundle.l1_units}
    evidence: list[str] = []
    for unit_id in l1_ids:
        unit = l1_by_id.get(unit_id)
        if unit is None:
            continue
        evidence.extend(span.evidence_id for span in unit.source.evidence_spans)
    return list(dict.fromkeys(evidence))


def execute_authoritative_query(
    plan: AuthoritativeQueryPlan,
    bundle: MemoryRepresentationBundleV3,
) -> AuthoritativeQueryResult:
    matched_ids, matched_claims = _matched_units_and_claims(plan, bundle)
    support_ids = [unit_id for unit_id in matched_ids if unit_id in {unit.unit_id for unit in bundle.l1_units}]
    for claims in matched_claims.values():
        for claim in claims:
            support_ids.extend(claim.supporting_l1_units)
    support_ids = list(dict.fromkeys(support_ids))
    evidence_ids = _evidence_for_l1_ids(support_ids, bundle)

    if plan.closure_id is not None and plan.closure_spec_revision is not None:
        spec = _find_spec(bundle, plan.closure_id, plan.closure_spec_revision)
        evaluation = _find_query_evaluation(bundle, plan)
        if spec is None or evaluation is None:
            return AuthoritativeQueryResult(
                query_id=plan.query_id,
                matched_unit_ids=matched_ids,
                required_evidence_ids=[],
                closure_complete=False,
                abstained=True,
                fallback_allowed=False,
                reason="missing_closure_evaluation",
            )
        inputs = ClosureEvaluationInputs.for_query(bundle, plan)
        if not is_closure_evaluation_fresh(evaluation, spec, inputs):
            return AuthoritativeQueryResult(
                query_id=plan.query_id,
                matched_unit_ids=matched_ids,
                required_evidence_ids=[],
                closure_complete=False,
                abstained=True,
                fallback_allowed=False,
                reason="stale_closure_evaluation",
            )
        if not evaluation.complete:
            return AuthoritativeQueryResult(
                query_id=plan.query_id,
                matched_unit_ids=matched_ids,
                required_evidence_ids=[],
                closure_complete=False,
                abstained=True,
                missing_slots=[item.slot_id for item in evaluation.slot_results if not item.satisfied],
                fallback_allowed=evaluation.fallback_allowed,
                reason=evaluation.reason_code,
            )

    if not matched_ids:
        return AuthoritativeQueryResult(
            query_id=plan.query_id,
            matched_unit_ids=[],
            required_evidence_ids=[],
            closure_complete=False,
            abstained=True,
            fallback_allowed=False,
            reason="no matching units",
        )

    if plan.answer_kind == "count":
        aggregate_claims = [
            claim
            for claims in matched_claims.values()
            for claim in claims
            if claim.aggregate is not None and claim.aggregate.function == "count_distinct"
        ]
        if not aggregate_claims:
            return AuthoritativeQueryResult(
                query_id=plan.query_id,
                matched_unit_ids=matched_ids,
                required_evidence_ids=evidence_ids,
                closure_complete=True,
                abstained=True,
                fallback_allowed=False,
                reason="structured_l2_identity_unresolved",
            )

    return AuthoritativeQueryResult(
        query_id=plan.query_id,
        matched_unit_ids=matched_ids,
        required_evidence_ids=evidence_ids,
        closure_complete=True,
        abstained=False,
        fallback_allowed=False,
        reason="authoritative_query_complete",
    )


def validate_raw_artifact_revisions(
    artifacts: list[RawArtifactRevision],
    *,
    workspace_root: Path,
) -> list[str]:
    errors: list[str] = []
    root = workspace_root.resolve()
    for artifact in artifacts:
        path = (root / artifact.local_path).resolve()
        try:
            path.relative_to(root)
        except ValueError:
            errors.append(f"artifact {artifact.artifact_revision_id} escapes workspace root")
            continue
        if not path.is_file():
            errors.append(f"artifact {artifact.artifact_revision_id} file is missing")
            continue
        if path.stat().st_size != artifact.size_bytes:
            errors.append(f"artifact {artifact.artifact_revision_id} size mismatch")
        if _sha256_bytes(path.read_bytes()) != artifact.content_sha256:
            errors.append(f"artifact {artifact.artifact_revision_id} hash mismatch")
    return errors


class AuthoritativeSourceValidationReport(StrictModel):
    schema_version: Literal["authoritative-source-validation-report-v1"] = (
        "authoritative-source-validation-report-v1"
    )
    valid: bool
    errors: list[str]
    metrics: dict[str, int]


def _parse_source_ref(source_ref: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for part in source_ref.split(";"):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        parsed[key] = value
    return parsed


def _replay_source_record(
    source: SourceRecordRevision,
    artifact: RawArtifactRevision,
    *,
    workspace_root: Path,
) -> str:
    from .evidence import (
        _load_beam_message_index,
        _load_locomo_dialogue_index,
        _load_longmemeval_session_index,
    )

    path = (workspace_root.resolve() / artifact.local_path).resolve()
    ref = _parse_source_ref(source.source_ref)
    if source.resolver_id == "beam-message-resolver":
        index = _load_beam_message_index(path, ref["conversation_id"])
        return index[ref["message_id"]].text
    if source.resolver_id == "locomo-dialogue-resolver":
        index = _load_locomo_dialogue_index(path, ref["sample_id"])
        return index[ref["dia_id"]].text
    if source.resolver_id == "longmemeval-session-resolver":
        index = _load_longmemeval_session_index(path, ref["question_id"])
        return index[ref["session_id"]].text
    raise ValueError(f"unsupported resolver {source.resolver_id}@{source.resolver_version}")


def validate_authoritative_sources(
    bundle: MemoryRepresentationBundleV3,
    *,
    workspace_root: Path,
) -> AuthoritativeSourceValidationReport:
    errors = validate_raw_artifact_revisions(
        bundle.raw_artifact_revisions,
        workspace_root=workspace_root,
    )
    artifacts = {item.artifact_revision_id: item for item in bundle.raw_artifact_revisions}
    replayed = 0
    for source in bundle.source_record_revisions:
        artifact = artifacts.get(source.artifact_revision_id)
        if artifact is None:
            errors.append(
                f"source revision {source.source_revision_id} references missing artifact {source.artifact_revision_id}"
            )
            continue
        try:
            replayed_text = _replay_source_record(
                source,
                artifact,
                workspace_root=workspace_root,
            )
        except Exception as exc:
            errors.append(
                f"source revision {source.source_revision_id} resolver replay failed: {type(exc).__name__}: {exc}"
            )
            continue
        if replayed_text != source.text:
            errors.append(f"source revision {source.source_revision_id} resolver text mismatch")
            continue
        if _sha256_text(replayed_text) != source.content_sha256:
            errors.append(f"source revision {source.source_revision_id} resolver hash mismatch")
            continue
        replayed += 1
    unique_errors = list(dict.fromkeys(errors))
    return AuthoritativeSourceValidationReport(
        valid=not unique_errors,
        errors=unique_errors,
        metrics={
            "artifact_verified_count": len(bundle.raw_artifact_revisions)
            - sum(1 for error in unique_errors if error.startswith("artifact ")),
            "source_record_replayed_count": replayed,
        },
    )


def _record_kind_and_resolver(source_id: str) -> tuple[RecordKind, str]:
    if source_id == "beam-100K":
        return "message", "beam-message-resolver"
    if source_id == "locomo10":
        return "dialogue_turn", "locomo-dialogue-resolver"
    if source_id == "longmemeval-oracle":
        return "normalized_session", "longmemeval-session-resolver"
    raise ValueError(f"unsupported source id for authoritative migration: {source_id}")


def _source_record_id(source_id: str, source_ref: str) -> str:
    return _content_id("source-record", {"source_id": source_id, "source_ref": source_ref})


def _common_roles(units: list[L1MemoryUnitV2]) -> list[RoleBinding]:
    if not units:
        return []
    return [
        role
        for role in units[0].roles
        if all(role in unit.roles for unit in units[1:])
    ]


def _claim_time(units: list[L1MemoryUnitV2]) -> TimeBinding:
    if not units:
        return TimeBinding()
    first = units[0].time
    return first if all(unit.time == first for unit in units[1:]) else TimeBinding()


def _legacy_slots(closure: Any) -> list[ClosureSlotSpec]:
    from .semantic_ir import STRUCTURAL_FALLBACK_ALLOWED_ROLES

    slots: list[ClosureSlotSpec] = []
    for index, requirement in enumerate(closure.required_units, start=1):
        slots.append(
            ClosureSlotSpec(
                slot_id=f"slot-{closure.closure_id}-required-{index}-{requirement.role}",
                role=requirement.role,
                required=True,
                bound_unit_id=requirement.unit_id,
                fallback_class=(
                    "candidate_only"
                    if requirement.role in STRUCTURAL_FALLBACK_ALLOWED_ROLES
                    else "blocked"
                ),
            )
        )
    for index, requirement in enumerate(closure.optional_units, start=1):
        slots.append(
            ClosureSlotSpec(
                slot_id=f"slot-{closure.closure_id}-optional-{index}-{requirement.role}",
                role=requirement.role,
                required=False,
                bound_unit_id=requirement.unit_id,
                fallback_class="candidate_only",
            )
        )
    if closure.pattern == "causal_answerability":
        present = {slot.role for slot in slots}
        for role in sorted({"cause", "effect", "causal_link"} - present):
            slots.append(
                ClosureSlotSpec(
                    slot_id=f"slot-{closure.closure_id}-unbound-{role}",
                    role=role,
                    required=True,
                    bound_unit_id=None,
                    fallback_class="blocked",
                )
            )
    return slots


def _convert_query_plan(
    plan: Any,
    *,
    answer_kind: AnswerKind,
) -> AuthoritativeQueryPlan:
    if plan.time_constraints:
        raise ValueError(
            f"legacy query {plan.query_id} has untyped time constraints and cannot be migrated authoritatively"
        )
    return AuthoritativeQueryPlan(
        query_id=plan.query_id,
        intent=plan.intent,
        target_level=plan.target_level,
        answer_kind=answer_kind,
        entity_ids=list(plan.entity_ids),
        predicate_sense=plan.predicate_sense,
        canonical_operator=plan.canonical_operator,
        role_constraints=list(plan.role_constraints),
        source_status_constraints=list(plan.source_status_constraints),
        lifecycle=plan.lifecycle,
        closure_id=f"{plan.closure_id}-query" if plan.closure_id else None,
        closure_spec_revision=1 if plan.closure_id else None,
        fallback_allowed_reasons=list(plan.fallback_allowed_reasons),
        fallback_blocked_reasons=list(plan.fallback_blocked_reasons),
    )


def migrate_v2_bundle_to_v3(
    bundle: Any,
    *,
    root: Path,
    slice_id: str,
    transaction_time: str,
    producer: ProducerIdentity,
    query_answer_kinds: dict[str, AnswerKind] | None = None,
) -> MemoryRepresentationBundleV3:
    from .io import load_json

    query_answer_kinds = query_answer_kinds or {}
    manifest = load_json(root / "source-manifest.json")
    corpus = load_json(root / slice_id / "evidence-corpus.json")["items"]
    evidence_candidates: dict[tuple[str, str, str], dict[str, Any]] = {}
    for item_units in corpus.values():
        for item in item_units:
            key = (str(item["source_ref"]), str(item["text"]), str(item["unit_id"]))
            existing = evidence_candidates.get(key)
            if existing is not None and existing != item:
                raise ValueError(f"conflicting evidence corpus definition: {key}")
            evidence_candidates[key] = item

    source_items: list[tuple[Any, dict[str, Any]]] = []
    referenced_source_ids: set[str] = set()
    for old_l1 in bundle.l1_units:
        if len(old_l1.source.evidence_spans) != 1:
            raise ValueError(f"v3 migration currently requires one evidence span per L1: {old_l1.unit_id}")
        span = old_l1.source.evidence_spans[0]
        evidence = evidence_candidates.get((span.turn_id, span.text, span.evidence_id))
        if evidence is None:
            raise ValueError(f"cannot resolve v2 evidence span for {old_l1.unit_id}")
        source_items.append((old_l1, evidence))
        referenced_source_ids.add(str(evidence["source_id"]))

    raw_artifacts: list[RawArtifactRevision] = []
    artifacts_by_source_id: dict[str, RawArtifactRevision] = {}
    for item in manifest["sources"]:
        if item["source_id"] not in referenced_source_ids:
            continue
        artifact = make_raw_artifact_revision(
            source_id=item["source_id"],
            frozen_identity=item["frozen_identity"],
            official_url=item["official_url"],
            local_path=item["local_path"],
            reader=item["reader"],
            size_bytes=item["size_bytes"],
            content_sha256=item["sha256"],
        )
        raw_artifacts.append(artifact)
        artifacts_by_source_id[artifact.source_id] = artifact

    source_revisions: list[SourceRecordRevision] = []
    sources_by_key: dict[tuple[str, str, str], SourceRecordRevision] = {}
    l1_units: list[L1MemoryUnitV2] = []
    unit_revisions: list[MemoryUnitRevision] = []
    current_revision_ids: dict[str, str] = {}
    l1_revision_by_unit: dict[str, MemoryUnitRevision] = {}
    for old_l1, evidence in source_items:
        old_span = old_l1.source.evidence_spans[0]
        source_id = str(evidence["source_id"])
        source_ref = str(evidence["source_ref"])
        text = str(evidence["text"])
        key = (source_id, source_ref, _sha256_text(text))
        source_revision = sources_by_key.get(key)
        if source_revision is None:
            record_kind, resolver_id = _record_kind_and_resolver(source_id)
            source_revision = make_source_record_revision(
                source_record_id=_source_record_id(source_id, source_ref),
                revision_number=1,
                previous_revision_id=None,
                artifact_revision_id=artifacts_by_source_id[source_id].artifact_revision_id,
                source_ref=source_ref,
                turn_id=old_span.turn_id,
                session_id=old_span.session_id,
                record_kind=record_kind,
                text=text,
                resolver_id=resolver_id,
                resolver_version="1",
                transaction_time=transaction_time,
                metadata={
                    "source_id": source_id,
                    "benchmark": evidence["benchmark"],
                    "evidence_metadata": evidence.get("metadata", {}),
                },
            )
            sources_by_key[key] = source_revision
            source_revisions.append(source_revision)
        new_span = make_evidence_span(
            evidence_id=old_span.evidence_id,
            source_revision=source_revision,
            turn_id=source_revision.turn_id,
            session_id=source_revision.session_id,
            char_start=old_span.char_start,
            char_end=old_span.char_end,
            text=old_span.text,
        )
        new_l1 = L1MemoryUnitV2(
            unit_id=old_l1.unit_id,
            kind=old_l1.kind,
            predicate=old_l1.predicate,
            roles=list(old_l1.roles),
            modality=old_l1.modality,
            polarity=old_l1.polarity,
            time=old_l1.time,
            source=SourceBindingV2(
                speaker=old_l1.source.speaker,
                source_status=old_l1.source.source_status,
                evidence_spans=[new_span],
            ),
            epistemic=old_l1.epistemic,
            links=old_l1.links,
            lifecycle=old_l1.lifecycle,
        )
        revision = make_memory_unit_revision(
            payload=new_l1,
            revision_number=1,
            previous_revision_id=None,
            revision_kind="create",
            transaction_time=transaction_time,
            source_revision_ids=[source_revision.source_revision_id],
            derived_from_revision_ids=[],
            producer=producer,
        )
        l1_units.append(new_l1)
        unit_revisions.append(revision)
        l1_revision_by_unit[new_l1.unit_id] = revision
        current_revision_ids[new_l1.unit_id] = revision.revision_id

    legacy_closures = {closure.closure_id: closure for closure in bundle.closures}
    bundle_id = f"{bundle.bundle_id}-authoritative-v3"
    closure_specs: list[ClosureSpec] = []
    closure_evaluations: list[ClosureEvaluation] = []
    l2_units: list[L2MemoryUnitV2] = []
    for old_l2 in bundle.l2_units:
        supporting = [l1 for l1 in l1_units if l1.unit_id in old_l2.source_l1_units]
        shared_predicate = supporting[0].predicate if supporting else None
        same_predicate = bool(
            supporting
            and all(
                item.predicate.sense == shared_predicate.sense
                and item.predicate.canonical_operator == shared_predicate.canonical_operator
                for item in supporting
            )
        )
        common_roles = _common_roles(supporting)
        claims: list[L2StructuredClaim] = []
        if shared_predicate is not None and same_predicate and common_roles:
            claims.append(
                L2StructuredClaim(
                    claim_id=f"claim-{old_l2.unit_id}",
                    predicate=shared_predicate.model_copy(
                        update={"surface": f"abstracted {shared_predicate.surface}"}
                    ),
                    roles=common_roles,
                    modality=supporting[0].modality,
                    polarity=supporting[0].polarity,
                    time=_claim_time(supporting),
                    supporting_l1_units=[item.unit_id for item in supporting],
                    aggregate=None,
                )
            )
        claim_id = claims[0].claim_id if claims else f"display-only-{old_l2.unit_id}"
        claim_closure_id = f"{old_l2.closure_id}-claim"
        claim_spec = make_closure_spec(
            closure_id=claim_closure_id,
            revision=1,
            target_id=claim_id,
            pattern=legacy_closures[old_l2.closure_id].pattern,
            slots=[
                ClosureSlotSpec(
                    slot_id=f"slot-{claim_closure_id}-{index}",
                    role="claim_support",
                    required=True,
                    bound_unit_id=item.unit_id,
                    fallback_class="blocked",
                )
                for index, item in enumerate(supporting, start=1)
            ],
        )
        closure_specs.append(claim_spec)
        claim_context = ClaimClosureContext(
            l2_unit_id=old_l2.unit_id,
            claim_id=claim_id,
            claim_hash=claims[0].semantic_hash if claims else "0" * 64,
            support_unit_ids=[item.unit_id for item in supporting] if claims else [],
            support_scope=[item.unit_id for item in supporting],
        )
        claim_inputs = ClosureEvaluationInputs(
            evaluated_bundle_id=bundle_id,
            context=claim_context,
            current_revision_ids={
                item.unit_id: l1_revision_by_unit[item.unit_id].revision_id for item in supporting
            },
            unit_revisions=[l1_revision_by_unit[item.unit_id] for item in supporting],
            source_revisions=source_revisions,
            evaluator_id="authoritative-closure-evaluator",
            evaluator_version="1",
            policy_version="authoritative-closure-policy-v1",
        )
        claim_evaluation = evaluate_closure_spec(claim_spec, claim_inputs)
        closure_evaluations.append(claim_evaluation)
        new_l2 = L2MemoryUnitV2(
            unit_id=old_l2.unit_id,
            kind=old_l2.kind,
            abstracts=list(old_l2.abstracts),
            summary=old_l2.summary,
            display_assertions=list(old_l2.assertions),
            structured_claims=claims,
            closure_id=claim_spec.closure_id,
            closure_spec_revision=claim_spec.revision,
            closure_evaluation_id=claim_evaluation.evaluation_id,
            lifecycle=old_l2.lifecycle if claims and claim_evaluation.complete else "candidate",
            valid_time=old_l2.valid_time,
            abstraction_method=dict(old_l2.abstraction_method),
            source_l1_units=list(old_l2.source_l1_units),
            source_turns=list(old_l2.source_turns),
            source_sessions=list(old_l2.source_sessions),
        )
        source_revision_ids = list(
            dict.fromkeys(
                source_id
                for item in supporting
                for source_id in l1_revision_by_unit[item.unit_id].source_revision_ids
            )
        )
        derived_revision_ids = [l1_revision_by_unit[item.unit_id].revision_id for item in supporting]
        revision = make_memory_unit_revision(
            payload=new_l2,
            revision_number=1,
            previous_revision_id=None,
            revision_kind="create",
            transaction_time=transaction_time,
            source_revision_ids=source_revision_ids,
            derived_from_revision_ids=derived_revision_ids,
            producer=producer,
        )
        l2_units.append(new_l2)
        unit_revisions.append(revision)
        current_revision_ids[new_l2.unit_id] = revision.revision_id

    query_plans = [
        _convert_query_plan(
            plan,
            answer_kind=query_answer_kinds.get(plan.query_id, "evidence_set"),
        )
        for plan in bundle.query_plans
    ]
    for old_plan, new_plan in zip(bundle.query_plans, query_plans, strict=True):
        if old_plan.closure_id is None:
            continue
        legacy = legacy_closures[old_plan.closure_id]
        closure_specs.append(
            make_closure_spec(
                closure_id=new_plan.closure_id or "",
                revision=new_plan.closure_spec_revision or 1,
                target_id=new_plan.query_id,
                pattern=legacy.pattern,
                slots=_legacy_slots(legacy),
            )
        )

    profile = bundle.profile.model_copy(
        update={"format_version": "memory-representation-bundle-v3"}
    )
    interim = MemoryRepresentationBundleV3(
        bundle_id=bundle_id,
        profile=profile,
        raw_artifact_revisions=raw_artifacts,
        source_record_revisions=source_revisions,
        unit_revisions=unit_revisions,
        current_revision_ids=current_revision_ids,
        l1_units=l1_units,
        l2_units=l2_units,
        closure_specs=closure_specs,
        closure_evaluations=closure_evaluations,
        query_plans=query_plans,
        query_unit_scopes={key: list(value) for key, value in bundle.query_unit_scopes.items()},
        metadata={
            **bundle.metadata,
            "migrated_from_schema": bundle.schema_version,
            "migration_transaction_time": transaction_time,
            "closure_evaluator_id": "authoritative-closure-evaluator",
            "closure_evaluator_version": "1",
            "closure_policy_version": "authoritative-closure-policy-v1",
            "legacy_closure_materialization": "ignored_and_recomputed",
        },
    )
    query_evaluations: list[ClosureEvaluation] = []
    for plan in query_plans:
        if plan.closure_id is None or plan.closure_spec_revision is None:
            continue
        spec = _find_spec(interim, plan.closure_id, plan.closure_spec_revision)
        if spec is None:  # pragma: no cover - constructed above
            raise ValueError(f"missing migrated query spec for {plan.query_id}")
        query_evaluations.append(
            evaluate_closure_spec(spec, ClosureEvaluationInputs.for_query(interim, plan))
        )
    return interim.model_copy(
        update={"closure_evaluations": [*closure_evaluations, *query_evaluations]}
    )


def build_real_slice_authoritative_bundle(
    root: Path,
    slice_id: str,
    results_path: Path,
    *,
    transaction_time: str,
    producer: ProducerIdentity,
    query_answer_kinds: dict[str, AnswerKind] | None = None,
) -> MemoryRepresentationBundleV3:
    from .representation_conformance_runner import build_real_slice_representation_bundle

    v2 = build_real_slice_representation_bundle(root, slice_id, results_path)
    return migrate_v2_bundle_to_v3(
        v2,
        root=root,
        slice_id=slice_id,
        transaction_time=transaction_time,
        producer=producer,
        query_answer_kinds=query_answer_kinds,
    )
