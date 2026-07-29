from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from .authoritative_memory import StrictModel, canonical_sha256
from .identity_proposal import (
    GatedIdentityDecision,
    IdentityProposalPayload,
    ProposalAction,
    PublicIdentityPayload,
    RelationKind,
    V5_RESULTS_SHA256,
)
from .identity_resolution import IdentityAwareMemoryBundleV4
from .identity_resolution import build_identity_scenario_bundle
from .io import (
    load_json,
    sha256_file,
    write_json_immutable,
    write_text_immutable,
)


CandidateDisposition = Literal[
    "eligible_for_manual_review",
    "gate_abstained",
    "review_required",
]


class CandidateEvidenceReference(StrictModel):
    mention_id: str = Field(min_length=1)
    evidence_unit_id: str = Field(min_length=1)
    source_item_id: str = Field(min_length=1)
    source_ref: str = Field(min_length=1)
    concept_id: str = Field(min_length=1)
    source_actor_id: str | None = None


class CandidateCompatibility(StrictModel):
    existing_entity_record_ids: list[str] = Field(default_factory=list)
    subject_ref_count: int = Field(ge=0)
    bound_subject_ref_count: int = Field(ge=0)
    l1_unit_ids: list[str] = Field(default_factory=list)
    evidence_ref_count: int = Field(ge=0)
    bound_l1_evidence_ref_count: int = Field(ge=0)
    source_revision_ids: list[str] = Field(default_factory=list)
    bound_source_revision_ref_count: int = Field(ge=0)
    evidence_chain_ids: list[str] = Field(default_factory=list)
    bound_evidence_chain_ref_count: int = Field(ge=0)
    gaps: list[str] = Field(default_factory=list)
    authoritative_materialization_allowed: Literal[False] = False


class AutomaticWriteClaims(StrictModel):
    aggregate: Literal[False] = False
    closure: Literal[False] = False
    identity_decision: Literal[False] = False
    merge: Literal[False] = False
    membership: Literal[False] = False
    l2: Literal[False] = False
    snapshot: Literal[False] = False


class IdentityCandidateEnvelope(StrictModel):
    schema_version: Literal["identity-candidate-envelope-v3"] = (
        "identity-candidate-envelope-v3"
    )
    candidate_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    relation_kind: RelationKind
    proposed_action: ProposalAction
    gated_action: ProposalAction
    gate_reason: str = Field(min_length=1)
    disposition: CandidateDisposition
    review_kind: Literal["identity_relation", "membership_relation", "no_action"]
    provisional_subject_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[CandidateEvidenceReference]
    public_case_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposal_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    gated_decision_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    compatibility: CandidateCompatibility
    automatic_write_claims: AutomaticWriteClaims = Field(
        default_factory=AutomaticWriteClaims
    )


class IdentityCandidateReviewQueue(StrictModel):
    schema_version: Literal["identity-candidate-review-queue-v3"] = (
        "identity-candidate-review-queue-v3"
    )
    dataset_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    proposer_id: str = Field(min_length=1)
    proposer_version: str = Field(min_length=1)
    case_count: int = Field(ge=1)
    input_sha256: dict[str, str]
    candidates: list[IdentityCandidateEnvelope] = Field(min_length=1)


class IdentityProposalScoreMetrics(StrictModel):
    accepted_non_abstain_coverage: float = Field(ge=0.0, le=1.0)
    gate_intervention_count: int = Field(ge=0)
    gate_intervention_rate: float = Field(ge=0.0, le=1.0)
    gated_abstention_correctness: float = Field(ge=0.0, le=1.0)
    gated_action_accuracy: float = Field(ge=0.0, le=1.0)
    gated_critical_false_membership_count: int = Field(ge=0)
    gated_critical_false_merge_count: int = Field(ge=0)
    proposal_evidence_exact_rate: float = Field(ge=0.0, le=1.0)
    raw_abstention_f1: float = Field(ge=0.0, le=1.0)
    raw_abstention_precision: float = Field(ge=0.0, le=1.0)
    raw_abstention_recall: float = Field(ge=0.0, le=1.0)
    raw_action_accuracy: float = Field(ge=0.0, le=1.0)
    raw_critical_false_membership_count: int = Field(ge=0)
    raw_critical_false_merge_count: int = Field(ge=0)
    required_evidence_exact_rate: float = Field(ge=0.0, le=1.0)
    structural_fallback_count: int = Field(ge=0)


class IdentityProposalScoreValidation(StrictModel):
    status: Literal["valid"]
    dataset_id: str = Field(min_length=1)
    case_count: int = Field(ge=1)
    dev_count: int = Field(ge=0)
    hidden_count: int = Field(ge=0)
    source_validation_valid: bool
    manifest_integrity_valid: bool


class IdentityProposalScoreRegressions(StrictModel):
    v5_hash_preserved: bool
    v5_longmemeval_abstention_preserved: bool
    v5_results_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class IdentityProposalScoreClaimBoundary(StrictModel):
    automatic_merge_authorized: bool
    core_impact: str = Field(min_length=1)
    longmemeval_status: str = Field(min_length=1)
    reference_proposer_is_model_run: bool


class IdentityProposalScoreInputHashes(StrictModel):
    authority: str = Field(pattern=r"^[0-9a-f]{64}$")
    gold: str = Field(pattern=r"^[0-9a-f]{64}$")
    manifest: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposals: str = Field(pattern=r"^[0-9a-f]{64}$")
    public: str = Field(pattern=r"^[0-9a-f]{64}$")


class IdentityProposalScorePayload(StrictModel):
    schema_version: Literal["natural-identity-proposal-score-v1"]
    status: Literal["pass", "fail"]
    dataset_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    proposer_id: str = Field(min_length=1)
    proposer_version: str = Field(min_length=1)
    case_count: int = Field(ge=1)
    validation: IdentityProposalScoreValidation
    input_sha256: IdentityProposalScoreInputHashes
    gated_decisions: list[GatedIdentityDecision] = Field(min_length=1)
    metrics: IdentityProposalScoreMetrics
    gate_safety_ready: bool
    proposal_quality_ready: bool
    regressions: IdentityProposalScoreRegressions
    claim_boundary: IdentityProposalScoreClaimBoundary


def _require_read_only(path: Path, label: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"{label} does not exist: {path}")
    if path.stat().st_mode & 0o222:
        raise ValueError(f"{label} must be read-only")


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 1.0


def _bundle_counts(bundle: IdentityAwareMemoryBundleV4) -> dict[str, int]:
    return {
        "entity_record_count": len(bundle.entity_records),
        "identity_decision_count": len(bundle.identity_decisions),
        "identity_closure_count": len(bundle.identity_closures),
        "identity_snapshot_count": len(bundle.identity_snapshots),
        "aggregate_claim_count": len(bundle.aggregate_claims),
        "membership_write_count": 0,
        "l2_unit_count": len(bundle.l2_units),
    }


def _validate_inputs(
    public_path: Path,
    proposals_path: Path,
    score_path: Path,
) -> tuple[
    PublicIdentityPayload,
    IdentityProposalPayload,
    IdentityProposalScorePayload,
    list[GatedIdentityDecision],
]:
    for path, label in (
        (public_path, "public input"),
        (proposals_path, "proposal input"),
        (score_path, "score input"),
    ):
        _require_read_only(path, label)

    public = PublicIdentityPayload.model_validate(load_json(public_path))
    proposals = IdentityProposalPayload.model_validate(load_json(proposals_path))
    score = IdentityProposalScorePayload.model_validate(load_json(score_path))
    if score.proposal_quality_ready is not True:
        raise ValueError("upstream proposal quality gate did not pass")
    if score.gate_safety_ready is not True:
        raise ValueError("upstream deterministic gate safety did not pass")
    if score.status != "pass":
        raise ValueError("upstream identity proposal score did not pass")
    metrics = score.metrics
    raw_metrics_ready = bool(
        metrics.raw_action_accuracy >= 0.85
        and metrics.raw_critical_false_merge_count == 0
        and metrics.raw_critical_false_membership_count == 0
        and metrics.raw_abstention_f1 >= 0.80
        and metrics.proposal_evidence_exact_rate >= 0.95
    )
    if not raw_metrics_ready:
        raise ValueError("score proposal quality metrics contradict readiness")
    gate_metrics_ready = bool(
        metrics.gated_action_accuracy == 1.0
        and metrics.gated_critical_false_merge_count == 0
        and metrics.gated_critical_false_membership_count == 0
        and metrics.gated_abstention_correctness == 1.0
        and metrics.required_evidence_exact_rate == 1.0
        and metrics.structural_fallback_count == 0
    )
    if not gate_metrics_ready:
        raise ValueError("score deterministic gate metrics contradict readiness")

    if not (
        score.validation.source_validation_valid
        and score.validation.manifest_integrity_valid
        and score.validation.status == "valid"
    ):
        raise ValueError("score validation boundary did not pass")
    if not (
        score.regressions.v5_hash_preserved
        and score.regressions.v5_longmemeval_abstention_preserved
        and score.regressions.v5_results_sha256 == V5_RESULTS_SHA256
    ):
        raise ValueError("score regression boundary did not pass")
    if not (
        score.claim_boundary.automatic_merge_authorized is False
        and score.claim_boundary.core_impact == "none"
        and score.claim_boundary.longmemeval_status
        == "structured_l2_identity_unresolved"
    ):
        raise ValueError("score claim boundary mismatch")

    if score.input_sha256.public != sha256_file(public_path):
        raise ValueError("score public input hash mismatch")
    if score.input_sha256.proposals != sha256_file(proposals_path):
        raise ValueError("score proposal input hash mismatch")

    if proposals.dataset_id != public.dataset_id or score.dataset_id != public.dataset_id:
        raise ValueError("candidate assessment dataset mismatch")
    if score.validation.dataset_id != public.dataset_id:
        raise ValueError("score validation dataset mismatch")
    if score.run_id != proposals.run_id:
        raise ValueError("candidate assessment run id mismatch")
    if score.proposer_id != proposals.proposer_id:
        raise ValueError("candidate assessment proposer id mismatch")
    if score.proposer_version != proposals.proposer_version:
        raise ValueError("candidate assessment proposer version mismatch")

    gated = score.gated_decisions
    public_by_id = {item.case_id: item for item in public.cases}
    proposal_by_id = {item.case_id: item for item in proposals.proposals}
    gated_by_id = {item.case_id: item for item in gated}
    expected_ids = set(public_by_id)
    if len(public.cases) != len(public_by_id):
        raise ValueError("duplicate public case id")
    if public.case_count != len(public.cases):
        raise ValueError("public case count mismatch")
    for case in public.cases:
        mention_ids = [item.mention_id for item in case.mentions]
        if len(mention_ids) != len(set(mention_ids)):
            raise ValueError(f"duplicate public mention id for {case.case_id}")
    if set(proposal_by_id) != expected_ids or set(gated_by_id) != expected_ids:
        raise ValueError("candidate assessment case coverage mismatch")
    if len(gated) != len(gated_by_id):
        raise ValueError("duplicate gated decision case id")
    if (
        public.case_count != proposals.case_count
        or public.case_count != score.case_count
        or public.case_count != score.validation.case_count
    ):
        raise ValueError("candidate assessment case count mismatch")

    for case_id, case in public_by_id.items():
        proposal = proposal_by_id[case_id]
        decision = gated_by_id[case_id]
        if proposal.relation_kind != case.relation_kind:
            raise ValueError(f"proposal relation mismatch for {case_id}")
        if decision.relation_kind != case.relation_kind:
            raise ValueError(f"gated relation mismatch for {case_id}")
        if decision.proposal != proposal:
            raise ValueError(f"gated proposal payload mismatch for {case_id}")
        if decision.proposed_action != proposal.action:
            raise ValueError(f"gated proposed action mismatch for {case_id}")
        allowed_actions = (
            {"merge", "keep_distinct", "abstain"}
            if case.relation_kind == "identity"
            else {"include", "exclude", "abstain"}
        )
        if decision.accepted_action not in allowed_actions:
            raise ValueError(f"gated accepted action mismatch for {case_id}")
        if (
            decision.accepted_action != "abstain"
            and decision.accepted_action != proposal.action
        ):
            raise ValueError(f"gated accepted action mismatch for {case_id}")
        if decision.evidence_mention_ids != proposal.evidence_mention_ids:
            raise ValueError(f"gated evidence mismatch for {case_id}")
        public_mention_ids = {item.mention_id for item in case.mentions}
        if (
            not decision.required_evidence_exact
            or set(decision.evidence_mention_ids) != public_mention_ids
        ):
            raise ValueError(f"gated evidence is not exact for {case_id}")
    exact_count = sum(item.required_evidence_exact for item in gated)
    intervention_count = sum(
        item.proposed_action != item.accepted_action for item in gated
    )
    if (
        metrics.required_evidence_exact_rate != _ratio(exact_count, public.case_count)
        or metrics.proposal_evidence_exact_rate
        != _ratio(exact_count, public.case_count)
        or metrics.gate_intervention_count != intervention_count
        or metrics.gate_intervention_rate
        != _ratio(intervention_count, public.case_count)
    ):
        raise ValueError("score gated decision metrics mismatch")
    return public, proposals, score, gated


def _candidate_envelope(
    case: Any,
    proposal: Any,
    gated: GatedIdentityDecision,
    guard_bundle: IdentityAwareMemoryBundleV4,
) -> IdentityCandidateEnvelope:
    mentions_by_id = {item.mention_id: item for item in case.mentions}
    missing_mentions = [
        mention_id
        for mention_id in proposal.evidence_mention_ids
        if mention_id not in mentions_by_id
    ]
    if missing_mentions:
        raise ValueError(
            f"proposal evidence is not present in public case {case.case_id}: {missing_mentions}"
        )
    evidence_refs = [
        CandidateEvidenceReference(
            mention_id=mention.mention_id,
            evidence_unit_id=mention.evidence_unit_id,
            source_item_id=mention.source_item_id,
            source_ref=mention.source_ref,
            concept_id=mention.concept_id,
            source_actor_id=mention.source_actor_id,
        )
        for mention in (mentions_by_id[item] for item in proposal.evidence_mention_ids)
    ]

    entity_ids = {item.entity_id for item in guard_bundle.entity_records}
    bound_entity_ids: list[str] = []
    if case.relation_kind == "identity":
        provisional_refs = [f"mention-candidate:{item.mention_id}" for item in evidence_refs]
        bound_entity_ids = [
            item.source_actor_id
            for item in evidence_refs
            if item.source_actor_id is not None and item.source_actor_id in entity_ids
        ]
        review_kind = "identity_relation" if gated.accepted_action != "abstain" else "no_action"
        structurally_reviewable = len(provisional_refs) >= 2
    else:
        provisional_refs = []
        if case.query_subject_id:
            provisional_refs.append(f"query-subject:{case.query_subject_id}")
            if case.query_subject_id in entity_ids:
                bound_entity_ids.append(case.query_subject_id)
        provisional_refs.extend(f"mention-candidate:{item.mention_id}" for item in evidence_refs)
        review_kind = "membership_relation" if gated.accepted_action != "abstain" else "no_action"
        structurally_reviewable = bool(case.query_subject_id and evidence_refs)

    if gated.accepted_action == "abstain":
        disposition: CandidateDisposition = "gate_abstained"
    elif gated.required_evidence_exact and structurally_reviewable:
        disposition = "eligible_for_manual_review"
    else:
        disposition = "review_required"

    l1_by_id: dict[str, list[Any]] = {}
    for unit in guard_bundle.l1_units:
        l1_by_id.setdefault(unit.unit_id, []).append(unit)
    source_by_ref: dict[str, list[Any]] = {}
    for source in guard_bundle.source_record_revisions:
        source_by_ref.setdefault(source.source_ref, []).append(source)
    bound_l1_refs: list[str] = []
    bound_source_refs: list[str] = []
    bound_chain_refs: list[str] = []
    ambiguous_l1 = False
    ambiguous_source = False
    for evidence in evidence_refs:
        l1_matches = l1_by_id.get(evidence.evidence_unit_id, [])
        source_matches = source_by_ref.get(evidence.source_ref, [])
        if len(l1_matches) == 1:
            bound_l1_refs.append(evidence.evidence_unit_id)
        elif len(l1_matches) > 1:
            ambiguous_l1 = True
        if len(source_matches) == 1:
            source_revision_id = source_matches[0].source_revision_id
            bound_source_refs.append(source_revision_id)
        elif len(source_matches) > 1:
            ambiguous_source = True
        if len(l1_matches) == 1 and len(source_matches) == 1:
            source_revision_id = source_matches[0].source_revision_id
            if any(
                span.source_revision_id == source_revision_id
                for span in l1_matches[0].source.evidence_spans
            ):
                bound_chain_refs.append(
                    f"{evidence.evidence_unit_id}->{source_revision_id}"
                )
    bound_l1 = sorted(set(bound_l1_refs))
    bound_sources = sorted(set(bound_source_refs))
    bound_chains = sorted(set(bound_chain_refs))
    gaps: list[str] = []
    if len(bound_entity_ids) < len(provisional_refs):
        gaps.append("missing_existing_entity_bindings")
    if len(bound_l1_refs) < len(evidence_refs):
        gaps.append("missing_l1_evidence_bindings")
    if len(bound_source_refs) < len(evidence_refs):
        gaps.append("missing_source_revision_bindings")
    if len(bound_chain_refs) < len(evidence_refs):
        gaps.append("missing_evidence_chain_bindings")
    if ambiguous_l1:
        gaps.append("ambiguous_l1_evidence_bindings")
    if ambiguous_source:
        gaps.append("ambiguous_source_revision_bindings")
    if gated.accepted_action != "abstain":
        gaps.append(
            "identity_evidence_closure_required"
            if case.relation_kind == "identity"
            else "membership_write_surface_unauthorized"
        )

    candidate_payload = {
        "case_id": case.case_id,
        "relation_kind": case.relation_kind,
        "proposed_action": proposal.action,
        "gated_action": gated.accepted_action,
        "public_case_sha256": canonical_sha256(case),
        "proposal_sha256": canonical_sha256(proposal),
        "gated_decision_sha256": canonical_sha256(gated),
    }
    return IdentityCandidateEnvelope(
        candidate_id=f"identity-candidate-{canonical_sha256(candidate_payload)[:24]}",
        case_id=case.case_id,
        relation_kind=case.relation_kind,
        proposed_action=proposal.action,
        gated_action=gated.accepted_action,
        gate_reason=gated.gate_reason,
        disposition=disposition,
        review_kind=review_kind,
        provisional_subject_refs=provisional_refs,
        evidence_refs=evidence_refs,
        public_case_sha256=candidate_payload["public_case_sha256"],
        proposal_sha256=candidate_payload["proposal_sha256"],
        gated_decision_sha256=candidate_payload["gated_decision_sha256"],
        compatibility=CandidateCompatibility(
            existing_entity_record_ids=sorted(set(bound_entity_ids)),
            subject_ref_count=len(provisional_refs),
            bound_subject_ref_count=len(bound_entity_ids),
            l1_unit_ids=bound_l1,
            evidence_ref_count=len(evidence_refs),
            bound_l1_evidence_ref_count=len(bound_l1_refs),
            source_revision_ids=bound_sources,
            bound_source_revision_ref_count=len(bound_source_refs),
            evidence_chain_ids=bound_chains,
            bound_evidence_chain_ref_count=len(bound_chain_refs),
            gaps=gaps,
        ),
    )


def assess_identity_candidate_generation(
    public_path: Path,
    proposals_path: Path,
    score_path: Path,
    *,
    guard_bundle: IdentityAwareMemoryBundleV4,
    guard_scenario_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    public_path = public_path.resolve()
    proposals_path = proposals_path.resolve()
    score_path = score_path.resolve()
    before_fingerprint = canonical_sha256(guard_bundle)
    before_counts = _bundle_counts(guard_bundle)

    public, proposals, score, gated = _validate_inputs(
        public_path,
        proposals_path,
        score_path,
    )
    proposal_by_id = {item.case_id: item for item in proposals.proposals}
    gated_by_id = {item.case_id: item for item in gated}
    candidates = [
        _candidate_envelope(
            case,
            proposal_by_id[case.case_id],
            gated_by_id[case.case_id],
            guard_bundle,
        )
        for case in public.cases
    ]
    queue = IdentityCandidateReviewQueue(
        dataset_id=public.dataset_id,
        run_id=proposals.run_id,
        proposer_id=proposals.proposer_id,
        proposer_version=proposals.proposer_version,
        case_count=len(candidates),
        input_sha256={
            "public": sha256_file(public_path),
            "proposals": sha256_file(proposals_path),
            "score": sha256_file(score_path),
        },
        candidates=candidates,
    )

    after_fingerprint = canonical_sha256(guard_bundle)
    after_counts = _bundle_counts(guard_bundle)
    state_unchanged = (
        before_fingerprint == after_fingerprint and before_counts == after_counts
    )
    if not state_unchanged:
        raise ValueError("authoritative state mutation detected")
    non_abstain = [item for item in candidates if item.gated_action != "abstain"]
    evidence_count = sum(len(item.evidence_refs) for item in candidates)
    public_mention_count = sum(len(item.mentions) for item in public.cases)
    provisional_count = sum(
        item.compatibility.subject_ref_count for item in candidates
    )
    entity_binding_count = sum(
        item.compatibility.bound_subject_ref_count for item in candidates
    )
    l1_binding_count = sum(
        item.compatibility.bound_l1_evidence_ref_count for item in candidates
    )
    source_binding_count = sum(
        item.compatibility.bound_source_revision_ref_count for item in candidates
    )
    evidence_chain_binding_count = sum(
        item.compatibility.bound_evidence_chain_ref_count for item in candidates
    )
    metrics = {
        "case_mapping_rate": _ratio(len(candidates), public.case_count),
        "mention_mapping_rate": _ratio(evidence_count, public_mention_count),
        "existing_entity_binding_rate": _ratio(entity_binding_count, provisional_count),
        "l1_evidence_binding_rate": _ratio(l1_binding_count, evidence_count),
        "source_revision_binding_rate": _ratio(source_binding_count, evidence_count),
        "evidence_chain_binding_rate": _ratio(
            evidence_chain_binding_count, evidence_count
        ),
        "manual_review_eligible_count": sum(
            item.disposition == "eligible_for_manual_review" for item in candidates
        ),
        "gate_abstained_count": sum(
            item.disposition == "gate_abstained" for item in candidates
        ),
        "review_required_count": sum(
            item.disposition == "review_required" for item in candidates
        ),
        "blocked_authoritative_write_count": len(non_abstain),
        "automatic_authoritative_write_count": 0,
        "authoritative_materialization_ready_count": 0,
    }
    raw_metric_names = (
        "raw_action_accuracy",
        "raw_critical_false_merge_count",
        "raw_critical_false_membership_count",
        "raw_abstention_f1",
        "proposal_evidence_exact_rate",
    )
    gated_metric_names = (
        "gated_action_accuracy",
        "gated_critical_false_merge_count",
        "gated_critical_false_membership_count",
        "gated_abstention_correctness",
        "gate_intervention_count",
        "required_evidence_exact_rate",
    )
    upstream_metrics = score.metrics.model_dump(mode="json")
    assessment = {
        "schema_version": "identity-candidate-generation-assessment-v3",
        "status": "pass",
        "dataset_id": public.dataset_id,
        "run_id": proposals.run_id,
        "case_count": len(candidates),
        "raw_proposer_quality_ready": score.proposal_quality_ready,
        "deterministic_gate_safety_ready": score.gate_safety_ready,
        "raw_proposer_metrics": {
            name: upstream_metrics[name] for name in raw_metric_names
        },
        "deterministic_gate_metrics": {
            name: upstream_metrics[name] for name in gated_metric_names
        },
        "candidate_generation_integration_ready": False,
        "queue_sha256": canonical_sha256(queue),
        "input_sha256": queue.input_sha256,
        "guard_scenario_id": guard_scenario_id,
        "state_guard": {
            "before_fingerprint": before_fingerprint,
            "after_fingerprint": after_fingerprint,
            "before_counts": before_counts,
            "after_counts": after_counts,
            "unchanged": state_unchanged,
        },
        "metrics": metrics,
        "claim_boundary": {
            "automatic_aggregate_write_authorized": False,
            "automatic_closure_write_authorized": False,
            "automatic_identity_decision_write_authorized": False,
            "automatic_merge_write_authorized": False,
            "automatic_membership_write_authorized": False,
            "automatic_l2_write_authorized": False,
            "automatic_snapshot_write_authorized": False,
            "embedding_authority": False,
            "queue_authoritative": False,
            "longmemeval_status": "structured_l2_identity_unresolved",
        },
    }
    return queue.model_dump(mode="json"), assessment


def render_identity_candidate_assessment_report(payload: dict[str, Any]) -> str:
    raw_status = "pass" if payload["raw_proposer_quality_ready"] else "fail"
    gate_status = "pass" if payload["deterministic_gate_safety_ready"] else "fail"
    integration_status = (
        "true" if payload["candidate_generation_integration_ready"] else "false"
    )
    mutation_status = "unchanged" if payload["state_guard"]["unchanged"] else "changed"
    metrics = payload["metrics"]
    return "\n".join(
        [
            "# Identity Candidate Generation Integration Assessment v3",
            "",
            f"- Run ID: `{payload['run_id']}`",
            f"- Cases: `{payload['case_count']}`",
            f"- Raw proposer quality: `{raw_status}`",
            f"- Deterministic gate safety: `{gate_status}`",
            f"- Candidate-generation integration ready: `{integration_status}`",
            f"- Manual-review eligible candidates: `{metrics['manual_review_eligible_count']}`",
            f"- Gate abstentions: `{metrics['gate_abstained_count']}`",
            f"- Existing entity binding rate: `{metrics['existing_entity_binding_rate']}`",
            f"- L1 evidence binding rate: `{metrics['l1_evidence_binding_rate']}`",
            f"- Source revision binding rate: `{metrics['source_revision_binding_rate']}`",
            f"- Evidence chain binding rate: `{metrics['evidence_chain_binding_rate']}`",
            f"- Blocked authoritative writes: `{metrics['blocked_authoritative_write_count']}`",
            f"- Automatic authoritative writes: `{metrics['automatic_authoritative_write_count']}`",
            f"- Mutation guard: `{mutation_status}`",
            "",
            "## Interpretation",
            "",
            "The queue is non-authoritative. Eligibility for manual review does not authorize an identity decision, merge, membership, snapshot, aggregate, or L2 write.",
            "",
            "Raw proposer quality and deterministic gate safety are independent upstream results. The gate result is not used to conceal or replace raw proposer quality.",
            "",
            "Gold-dependent action accuracy remains upstream scorer evidence. This stage verifies frozen input hashes, readiness thresholds, and decision-derived structural metrics without reading authority or gold directly.",
            "",
            "The current candidates do not have the existing entity, L1 evidence, source revision, and closure bindings required for authoritative materialization. This assessment records those gaps instead of synthesizing authority.",
            "",
            "Embedding remains non-authoritative, and `LONGMEMEVAL-6d550036` remains `structured_l2_identity_unresolved`.",
            "",
        ]
    )


def run_identity_candidate_assessment_file(
    public_path: Path,
    proposals_path: Path,
    score_path: Path,
    experiment_root: Path,
    guard_scenario_id: str,
    queue_path: Path,
    output_path: Path,
    report_path: Path,
) -> dict[str, Any]:
    guard_bundle = build_identity_scenario_bundle(
        experiment_root,
        guard_scenario_id,
    )
    queue, assessment = assess_identity_candidate_generation(
        public_path,
        proposals_path,
        score_path,
        guard_bundle=guard_bundle,
        guard_scenario_id=guard_scenario_id,
    )
    write_json_immutable(queue_path, queue)
    queue_path.chmod(0o444)
    if assessment["queue_sha256"] != sha256_file(queue_path):
        raise ValueError("candidate queue output hash mismatch")
    write_json_immutable(output_path, assessment)
    output_path.chmod(0o444)
    write_text_immutable(
        report_path,
        render_identity_candidate_assessment_report(assessment),
    )
    report_path.chmod(0o444)
    return assessment
