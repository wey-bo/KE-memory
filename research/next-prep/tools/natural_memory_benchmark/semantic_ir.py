from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


MemoryLevel = Literal["L1", "L2"]
MemoryKind = Literal[
    "event",
    "state",
    "preference",
    "task",
    "attribute",
    "project",
    "preference_profile",
    "habit",
    "long_running_state",
    "summary_event",
]
Modality = Literal["actual", "planned", "hypothetical", "requested", "recommended", "denied"]
Polarity = Literal["positive", "negative"]
Speaker = Literal["user", "assistant", "tool", "simulator", "named_speaker"]
SourceStatus = Literal["user_reported", "agent_generated", "tool_observed", "inferred"]
EpistemicTrust = Literal["high", "medium", "low"]
MemoryUtility = Literal["candidate", "useful", "low"]
Lifecycle = Literal["active", "superseded", "conflicted", "forgotten", "candidate"]
ClosurePattern = Literal[
    "single_fact",
    "multi_evidence_set",
    "temporal_chain",
    "update_supersession",
    "causal_answerability",
]
QueryIntent = Literal[
    "fact_lookup",
    "multi_evidence",
    "causal_how",
    "temporal_latest",
    "preference_current",
    "task_status",
]
TargetLevel = Literal["L1", "L2", "both"]


DEFAULT_FALLBACK_ALLOWED_REASONS = [
    "unresolved_entity",
    "lexical_predicate_missing_link",
    "incomplete_evidence_slot",
]
DEFAULT_FALLBACK_BLOCKED_REASONS = [
    "temporal_missing",
    "conflict_unresolved",
    "modality_mismatch",
    "answerability_missing",
]
STRUCTURAL_FALLBACK_ALLOWED_ROLES = set(DEFAULT_FALLBACK_ALLOWED_REASONS)
_CAUSAL_REQUIRED_ROLES = {"cause", "effect", "causal_link"}


class Predicate(StrictModel):
    surface: str = Field(min_length=1)
    sense: str = Field(min_length=1)
    canonical_operator: str = Field(min_length=1)


class RoleBinding(StrictModel):
    role: str = Field(min_length=1)
    entity_id: str = Field(min_length=1)
    role_name: str = Field(min_length=1)


class EvidenceSpan(StrictModel):
    evidence_id: str = Field(min_length=1)
    turn_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)
    text: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_offsets(self) -> "EvidenceSpan":
        if self.char_end < self.char_start:
            raise ValueError("char_end must be greater than or equal to char_start")
        return self


class SourceBinding(StrictModel):
    speaker: Speaker
    source_status: SourceStatus
    evidence_spans: list[EvidenceSpan] = Field(min_length=1)


class TimeBinding(StrictModel):
    event_time: str | None = None
    valid_time: str | None = None
    transaction_time: str | None = None


class EpistemicBinding(StrictModel):
    extraction_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    epistemic_trust: EpistemicTrust = "medium"
    memory_utility: MemoryUtility = "candidate"


class LinkBinding(StrictModel):
    same_as: list[str] = Field(default_factory=list)
    supersedes: list[str] = Field(default_factory=list)
    conflicts_with: list[str] = Field(default_factory=list)
    derived_from: list[str] = Field(default_factory=list)


class L1MemoryUnit(StrictModel):
    schema_version: Literal["semantic-ir-l1-v1"] = "semantic-ir-l1-v1"
    unit_id: str = Field(min_length=1)
    level: Literal["L1"] = "L1"
    kind: Literal["event", "state", "preference", "task", "attribute"]
    predicate: Predicate
    roles: list[RoleBinding] = Field(min_length=1)
    modality: Modality = "actual"
    polarity: Polarity = "positive"
    time: TimeBinding = Field(default_factory=TimeBinding)
    source: SourceBinding
    epistemic: EpistemicBinding = Field(default_factory=EpistemicBinding)
    links: LinkBinding = Field(default_factory=LinkBinding)
    lifecycle: Lifecycle = "active"


class L2MemoryUnit(StrictModel):
    schema_version: Literal["semantic-ir-l2-v1"] = "semantic-ir-l2-v1"
    unit_id: str = Field(min_length=1)
    level: Literal["L2"] = "L2"
    kind: Literal["task", "preference_profile", "project", "habit", "long_running_state", "summary_event"]
    abstracts: list[str] = Field(min_length=1)
    summary: str = Field(min_length=1)
    assertions: list[str] = Field(min_length=1)
    closure_id: str = Field(min_length=1)
    lifecycle: Lifecycle = "candidate"
    valid_time: str | None = None
    abstraction_method: dict[str, str | None] = Field(default_factory=dict)
    source_l1_units: list[str] = Field(min_length=1)
    source_turns: list[str] = Field(min_length=1)
    source_sessions: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_provenance_covers_abstracts(self) -> "L2MemoryUnit":
        missing = set(self.abstracts) - set(self.source_l1_units)
        if missing:
            raise ValueError(f"source_l1_units must include all abstracts: {sorted(missing)}")
        return self


class ClosureRequirement(StrictModel):
    unit_id: str = Field(min_length=1)
    role: str = Field(min_length=1)


class ClosureRecord(StrictModel):
    schema_version: Literal["semantic-ir-closure-v1"] = "semantic-ir-closure-v1"
    closure_id: str = Field(min_length=1)
    claim_or_query_id: str = Field(min_length=1)
    pattern: ClosurePattern
    required_units: list[ClosureRequirement] = Field(min_length=1)
    optional_units: list[ClosureRequirement] = Field(default_factory=list)
    missing_slots: list[ClosureRequirement] = Field(default_factory=list)
    complete: bool = False
    reason: str | None = None


class QuerySlotPlan(StrictModel):
    schema_version: Literal["semantic-ir-query-plan-v1"] = "semantic-ir-query-plan-v1"
    query_id: str = Field(min_length=1)
    intent: QueryIntent
    target_level: TargetLevel
    entity_ids: list[str] = Field(default_factory=list)
    predicate_sense: str | None = None
    canonical_operator: str | None = None
    role_constraints: list[RoleBinding] = Field(default_factory=list)
    time_constraints: list[str] = Field(default_factory=list)
    source_status_constraints: list[SourceStatus] = Field(default_factory=list)
    required_closure_pattern: ClosurePattern | None = None
    closure_id: str | None = None
    lifecycle: Lifecycle | None = None
    fallback_allowed_reasons: list[str] = Field(default_factory=lambda: list(DEFAULT_FALLBACK_ALLOWED_REASONS))
    fallback_blocked_reasons: list[str] = Field(default_factory=lambda: list(DEFAULT_FALLBACK_BLOCKED_REASONS))


class QueryResult(StrictModel):
    schema_version: Literal["semantic-ir-query-result-v1"] = "semantic-ir-query-result-v1"
    query_id: str = Field(min_length=1)
    matched_unit_ids: list[str] = Field(default_factory=list)
    required_evidence_ids: list[str] = Field(default_factory=list)
    closure_complete: bool = False
    abstained: bool = True
    missing_slots: list[str] = Field(default_factory=list)
    fallback_allowed: bool = False
    reason: str = Field(min_length=1)


def _missing_required_roles(closure: ClosureRecord) -> list[ClosureRequirement]:
    if closure.pattern != "causal_answerability":
        return []
    present_roles = {unit.role for unit in closure.required_units}
    return [
        ClosureRequirement(unit_id=f"__missing_role__:{role}", role=role)
        for role in sorted(_CAUSAL_REQUIRED_ROLES - present_roles)
    ]


def evaluate_closure(closure: ClosureRecord, available_unit_ids: set[str]) -> ClosureRecord:
    missing_units = [unit for unit in closure.required_units if unit.unit_id not in available_unit_ids]
    missing_roles = _missing_required_roles(closure)
    missing_slots = [*missing_units, *missing_roles]
    if missing_roles:
        reason = "missing causal answerability roles"
    elif missing_units:
        reason = "missing required closure slots"
    else:
        reason = "closure complete"
    return closure.model_copy(
        update={
            "missing_slots": missing_slots,
            "complete": not missing_slots,
            "reason": reason,
        }
    )


def fallback_allowed_for_closure(closure: ClosureRecord) -> bool:
    if closure.complete or not closure.missing_slots:
        return False
    return all(slot.role in STRUCTURAL_FALLBACK_ALLOWED_ROLES for slot in closure.missing_slots)


def _role_constraint_matches(unit: L1MemoryUnit, constraint: RoleBinding) -> bool:
    for role in unit.roles:
        if role.role != constraint.role:
            continue
        if role.entity_id != constraint.entity_id:
            continue
        if role.role_name != constraint.role_name:
            continue
        return True
    return False


def _l1_matches(plan: QuerySlotPlan, unit: L1MemoryUnit) -> bool:
    if plan.canonical_operator and unit.predicate.canonical_operator != plan.canonical_operator:
        return False
    if plan.predicate_sense and unit.predicate.sense != plan.predicate_sense:
        return False
    if plan.lifecycle and unit.lifecycle != plan.lifecycle:
        return False
    if plan.source_status_constraints and unit.source.source_status not in plan.source_status_constraints:
        return False
    unit_entity_ids = {role.entity_id for role in unit.roles}
    if plan.entity_ids and not set(plan.entity_ids).issubset(unit_entity_ids):
        return False
    if plan.role_constraints and not all(_role_constraint_matches(unit, constraint) for constraint in plan.role_constraints):
        return False
    return True


def _l2_matches(plan: QuerySlotPlan, unit: L2MemoryUnit) -> bool:
    if plan.lifecycle and unit.lifecycle != plan.lifecycle:
        return False
    if plan.closure_id and unit.closure_id != plan.closure_id:
        return False
    return True


def _evidence_ids_for_units(unit_ids: list[str], l1_by_id: dict[str, L1MemoryUnit]) -> list[str]:
    evidence_ids: list[str] = []
    for unit_id in unit_ids:
        unit = l1_by_id.get(unit_id)
        if unit is None:
            continue
        evidence_ids.extend(span.evidence_id for span in unit.source.evidence_spans)
    return list(dict.fromkeys(evidence_ids))


def _find_closure(plan: QuerySlotPlan, closures: list[ClosureRecord]) -> ClosureRecord | None:
    if plan.closure_id is not None:
        for closure in closures:
            if closure.closure_id == plan.closure_id:
                return closure
        return None
    for closure in closures:
        if closure.claim_or_query_id == plan.query_id:
            return closure
    return None


def execute_query(
    plan: QuerySlotPlan,
    l1_units: list[L1MemoryUnit],
    l2_units: list[L2MemoryUnit],
    closures: list[ClosureRecord],
) -> QueryResult:
    matched_l1: list[L1MemoryUnit] = []
    if plan.target_level in {"L1", "both"}:
        matched_l1 = [unit for unit in l1_units if _l1_matches(plan, unit)]
    matched_l2: list[L2MemoryUnit] = []
    if plan.target_level in {"L2", "both"}:
        matched_l2 = [unit for unit in l2_units if _l2_matches(plan, unit)]

    matched_unit_ids = [unit.unit_id for unit in matched_l1] + [unit.unit_id for unit in matched_l2]
    l1_by_id = {unit.unit_id: unit for unit in l1_units}
    closure = _find_closure(plan, closures)
    if closure is not None:
        evaluated = evaluate_closure(closure, set(matched_unit_ids))
        missing_slots = [slot.unit_id for slot in evaluated.missing_slots]
        if not evaluated.complete:
            return QueryResult(
                query_id=plan.query_id,
                matched_unit_ids=matched_unit_ids,
                required_evidence_ids=[],
                closure_complete=False,
                abstained=True,
                missing_slots=missing_slots,
                fallback_allowed=fallback_allowed_for_closure(evaluated),
                reason=evaluated.reason or "closure incomplete",
            )
        required_unit_ids = [unit.unit_id for unit in evaluated.required_units]
        return QueryResult(
            query_id=plan.query_id,
            matched_unit_ids=matched_unit_ids,
            required_evidence_ids=_evidence_ids_for_units(required_unit_ids, l1_by_id),
            closure_complete=True,
            abstained=False,
            missing_slots=[],
            fallback_allowed=False,
            reason=evaluated.reason or "closure complete",
        )

    if not matched_unit_ids:
        return QueryResult(
            query_id=plan.query_id,
            matched_unit_ids=[],
            required_evidence_ids=[],
            closure_complete=False,
            abstained=True,
            missing_slots=[],
            fallback_allowed=False,
            reason="no matching units",
        )

    return QueryResult(
        query_id=plan.query_id,
        matched_unit_ids=matched_unit_ids,
        required_evidence_ids=_evidence_ids_for_units([unit.unit_id for unit in matched_l1], l1_by_id),
        closure_complete=True,
        abstained=False,
        missing_slots=[],
        fallback_allowed=False,
        reason="matched units without explicit closure",
    )
