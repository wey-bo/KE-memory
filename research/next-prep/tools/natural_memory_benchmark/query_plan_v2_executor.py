from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .authoritative_memory import canonical_sha256
from .query_compiler_v2 import (
    CompiledQueryPlanV2,
    GitMemoryViewRefV1,
    QueryAtomV2,
    QueryTimeConstraintV1,
)
from .semantic_ir import Lifecycle, Modality, Polarity, SourceStatus


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ExecutionRoleBindingV1(StrictModel):
    schema_version: Literal["query-execution-role-v1"] = (
        "query-execution-role-v1"
    )
    role: str = Field(min_length=1)
    role_name: str = Field(min_length=1)
    entity_id: str = Field(min_length=1)


class ExecutionTimeV1(StrictModel):
    schema_version: Literal["query-execution-time-v1"] = (
        "query-execution-time-v1"
    )
    event_time: str | None = None
    valid_time: str | None = None
    transaction_time: str | None = None


class ExecutionFactProvenanceV1(StrictModel):
    schema_version: Literal["query-execution-fact-provenance-v1"] = (
        "query-execution-fact-provenance-v1"
    )
    unit_revision_id: str = Field(min_length=1)
    claim_id: str | None = None
    source_revision_ids: list[str] = Field(default_factory=list)
    supporting_l1_revision_ids: list[str] = Field(default_factory=list)
    closure_evaluation_id: str | None = None

    @model_validator(mode="after")
    def validate_references(self) -> "ExecutionFactProvenanceV1":
        for values, label in (
            (self.source_revision_ids, "source revision IDs"),
            (self.supporting_l1_revision_ids, "supporting L1 revision IDs"),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"execution fact {label} must be unique")
        if (self.claim_id is None) != (self.closure_evaluation_id is None):
            raise ValueError(
                "L2 claim ID and closure evaluation ID must be set together"
            )
        return self


class QueryExecutionFactV1(StrictModel):
    schema_version: Literal["query-execution-fact-v1"] = (
        "query-execution-fact-v1"
    )
    fact_id: str = Field(min_length=1)
    unit_id: str = Field(min_length=1)
    level: Literal["L1", "L2"]
    predicate_sense: str = Field(min_length=1)
    canonical_operator: str = Field(min_length=1)
    roles: list[ExecutionRoleBindingV1] = Field(min_length=1)
    modality: Modality
    polarity: Polarity
    time: ExecutionTimeV1 = Field(default_factory=ExecutionTimeV1)
    source_status: SourceStatus
    lifecycle: Lifecycle
    evidence_ids: list[str] = Field(default_factory=list)
    provenance: ExecutionFactProvenanceV1

    @model_validator(mode="after")
    def validate_roles(self) -> "QueryExecutionFactV1":
        roles = [item.role for item in self.roles]
        if len(roles) != len(set(roles)):
            raise ValueError("execution fact roles must be unique")
        return self


class QueryExecutionSnapshotV1(StrictModel):
    schema_version: Literal["query-execution-snapshot-v1"] = (
        "query-execution-snapshot-v1"
    )
    bundle_id: str = Field(min_length=1)
    memory_view: GitMemoryViewRefV1
    ontology_revision: str = Field(min_length=1)
    identity_revision: str = Field(min_length=1)
    registry_revision: str = Field(min_length=1)
    registry_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    facts: list[QueryExecutionFactV1]
    identity_status: dict[str, Literal["resolved", "unresolved"]]
    canonical_entity_ids: dict[str, str] = Field(default_factory=dict)
    identity_snapshot_id: str | None = None
    identity_input_fingerprint: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )

    @model_validator(mode="after")
    def validate_fact_ids(self) -> "QueryExecutionSnapshotV1":
        fact_ids = [item.fact_id for item in self.facts]
        if len(fact_ids) != len(set(fact_ids)):
            raise ValueError("query execution fact ids must be unique")
        for entity_id, canonical_id in self.canonical_entity_ids.items():
            if not entity_id or not canonical_id:
                raise ValueError("canonical entity IDs must be non-empty")
            target = self.canonical_entity_ids.get(canonical_id, canonical_id)
            if target != canonical_id:
                raise ValueError("canonical entity map must be idempotent")
        if (self.identity_snapshot_id is None) != (
            self.identity_input_fingerprint is None
        ):
            raise ValueError(
                "identity snapshot ID and input fingerprint must be set together"
            )
        return self


class QuerySnapshotEvaluationV1(StrictModel):
    schema_version: Literal["query-snapshot-evaluation-v1"] = (
        "query-snapshot-evaluation-v1"
    )
    query_id: str = Field(min_length=1)
    plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    matched_fact_ids: tuple[str, ...] = Field(default_factory=tuple)
    answer_values: tuple[str, ...] = Field(default_factory=tuple)
    count_value: int | None = Field(default=None, ge=0)
    required_evidence_ids: tuple[str, ...] = Field(default_factory=tuple)
    closure_complete: bool = False
    abstained: bool = True
    reason: str = Field(min_length=1)


class QueryExecutionAuthorityV1(StrictModel):
    schema_version: Literal["query-execution-authority-v1"] = (
        "query-execution-authority-v1"
    )
    memory_view: GitMemoryViewRefV1
    bundle_id: str = Field(min_length=1)
    bundle_history_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    registry_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    identity_snapshot_id: str | None = None
    identity_input_fingerprint: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evaluation_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    authority_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_authority(self) -> "QueryExecutionAuthorityV1":
        if (self.identity_snapshot_id is None) != (
            self.identity_input_fingerprint is None
        ):
            raise ValueError(
                "authority identity snapshot ID and input fingerprint "
                "must be set together"
            )
        payload = self.model_dump(
            mode="json",
            exclude={"authority_sha256"},
        )
        if self.authority_sha256 != canonical_sha256(payload):
            raise ValueError("query execution authority hash mismatch")
        return self

    def model_copy(
        self,
        *,
        update: dict[str, object] | None = None,
        deep: bool = False,
    ) -> Self:
        copied = super().model_copy(update=update, deep=deep)
        if not update:
            return copied
        return type(self).model_validate(copied.model_dump(mode="python"))


class QueryExecutionResultV3(StrictModel):
    schema_version: Literal["query-execution-result-v3"] = (
        "query-execution-result-v3"
    )
    evaluation: QuerySnapshotEvaluationV1
    authority: QueryExecutionAuthorityV1

    @model_validator(mode="after")
    def validate_plan_binding(self) -> "QueryExecutionResultV3":
        if self.evaluation.plan_sha256 != self.authority.plan_sha256:
            raise ValueError(
                "query execution evaluation and authority plan hashes differ"
            )
        if canonical_sha256(self.evaluation) != self.authority.evaluation_sha256:
            raise ValueError("query execution evaluation hash mismatch")
        return self

    def model_copy(
        self,
        *,
        update: dict[str, object] | None = None,
        deep: bool = False,
    ) -> Self:
        copied = super().model_copy(update=update, deep=deep)
        if not update:
            return copied
        return type(self).model_validate(copied.model_dump(mode="python"))

    @property
    def query_id(self) -> str:
        return self.evaluation.query_id

    @property
    def plan_sha256(self) -> str:
        return self.evaluation.plan_sha256

    @property
    def memory_view(self) -> GitMemoryViewRefV1:
        return self.authority.memory_view

    @property
    def matched_fact_ids(self) -> tuple[str, ...]:
        return self.evaluation.matched_fact_ids

    @property
    def answer_values(self) -> tuple[str, ...]:
        return self.evaluation.answer_values

    @property
    def count_value(self) -> int | None:
        return self.evaluation.count_value

    @property
    def required_evidence_ids(self) -> tuple[str, ...]:
        return self.evaluation.required_evidence_ids

    @property
    def closure_complete(self) -> bool:
        return self.evaluation.closure_complete

    @property
    def abstained(self) -> bool:
        return self.evaluation.abstained

    @property
    def reason(self) -> str:
        return self.evaluation.reason


@dataclass(frozen=True)
class _MatchState:
    bindings: dict[str, str]
    facts: tuple[QueryExecutionFactV1, ...]


def _abstain(
    plan: CompiledQueryPlanV2,
    reason: str,
    *,
    states: list[_MatchState] | None = None,
) -> QuerySnapshotEvaluationV1:
    matched_fact_ids, evidence_ids = _facts_and_evidence(states or [])
    return QuerySnapshotEvaluationV1(
        query_id=plan.query_id,
        plan_sha256=plan.plan_sha256,
        matched_fact_ids=matched_fact_ids,
        required_evidence_ids=evidence_ids,
        closure_complete=False,
        abstained=True,
        reason=reason,
    )


def _matches_plan_scope(
    plan: CompiledQueryPlanV2,
    fact: QueryExecutionFactV1,
) -> bool:
    if plan.target_level != "both" and fact.level != plan.target_level:
        return False
    if plan.lifecycle is not None and fact.lifecycle != plan.lifecycle:
        return False
    if plan.supersession_policy == "current_only":
        if fact.lifecycle in {"superseded", "forgotten", "candidate"}:
            return False
    if plan.source_status_constraints:
        if fact.source_status not in plan.source_status_constraints:
            return False
    return True


def _matches_exact_time(
    constraints: list[QueryTimeConstraintV1],
    fact: QueryExecutionFactV1,
) -> bool:
    for constraint in constraints:
        if constraint.operator == "latest":
            continue
        if constraint.operator != "exact":
            continue
        if getattr(fact.time, constraint.field) != constraint.value:
            return False
    return True


def _fact_role(
    fact: QueryExecutionFactV1,
    *,
    role: str,
) -> ExecutionRoleBindingV1 | None:
    for item in fact.roles:
        if item.role == role:
            return item
    return None


def _match_atom(
    plan: CompiledQueryPlanV2,
    atom: QueryAtomV2,
    fact: QueryExecutionFactV1,
    bindings: dict[str, str],
    canonical_entity_ids: dict[str, str],
) -> dict[str, str] | None:
    if not _matches_plan_scope(plan, fact):
        return None
    if not _matches_exact_time(plan.time_constraints, fact):
        return None
    if fact.predicate_sense != atom.predicate_sense:
        return None
    if fact.canonical_operator != atom.canonical_operator:
        return None
    if atom.modality is not None and fact.modality != atom.modality:
        return None
    if atom.polarity is not None and fact.polarity != atom.polarity:
        return None

    updated = dict(bindings)
    for pattern in atom.roles:
        fact_role = _fact_role(
            fact,
            role=pattern.role,
        )
        if fact_role is None:
            return None
        term = pattern.term
        fact_entity_id = canonical_entity_ids.get(
            fact_role.entity_id,
            fact_role.entity_id,
        )
        if term.kind == "entity":
            expected = canonical_entity_ids.get(term.value, term.value)
            if fact_entity_id != expected:
                return None
        if term.kind == "literal":
            return None
        if term.kind == "variable":
            existing = updated.get(term.value)
            if existing is not None and existing != fact_entity_id:
                return None
            updated[term.value] = fact_entity_id
    return updated


def _execute_group(
    plan: CompiledQueryPlanV2,
    group_index: int,
    snapshot: QueryExecutionSnapshotV1,
) -> list[_MatchState]:
    group = plan.pattern_groups[group_index]
    states = [_MatchState(bindings={}, facts=())]
    for atom in group.atoms:
        next_states: list[_MatchState] = []
        for state in states:
            for fact in snapshot.facts:
                bindings = _match_atom(
                    plan,
                    atom,
                    fact,
                    state.bindings,
                    snapshot.canonical_entity_ids,
                )
                if bindings is None:
                    continue
                next_states.append(
                    _MatchState(
                        bindings=bindings,
                        facts=(*state.facts, fact),
                    )
                )
        states = next_states
        if not states:
            break
    return states


def _deduplicate_states(
    states: list[_MatchState],
    *,
    answer_variable: str,
) -> list[_MatchState]:
    deduplicated: list[_MatchState] = []
    seen: set[tuple[str | None, tuple[str, ...]]] = set()
    for state in states:
        key = (
            state.bindings.get(answer_variable),
            tuple(item.fact_id for item in state.facts),
        )
        if key in seen:
            continue
        seen.add(key)
        deduplicated.append(state)
    return deduplicated


def _latest_states(
    plan: CompiledQueryPlanV2,
    states: list[_MatchState],
) -> tuple[list[_MatchState], str | None]:
    latest_constraints = [
        item for item in plan.time_constraints if item.operator == "latest"
    ]
    if not latest_constraints:
        return states, None
    if len(latest_constraints) != 1:
        return [], "unsupported_latest_constraint"
    field = latest_constraints[0].field
    state_times: list[tuple[_MatchState, datetime]] = []
    for state in states:
        values = [getattr(fact.time, field) for fact in state.facts]
        present = [value for value in values if value is not None]
        if not present:
            return [], "latest_time_missing"
        parsed: list[datetime] = []
        for value in present:
            try:
                timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return [], "latest_time_invalid"
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            parsed.append(timestamp.astimezone(timezone.utc))
        state_times.append((state, max(parsed)))
    latest = max(value for _, value in state_times)
    selected = [state for state, value in state_times if value == latest]
    answers = {
        state.bindings.get(plan.answer.variable)
        for state in selected
    }
    if len(answers) > 1:
        return selected, "latest_tie_unresolved"
    return selected, None


def _facts_and_evidence(
    states: list[_MatchState],
) -> tuple[list[str], list[str]]:
    fact_ids: set[str] = set()
    evidence_ids: set[str] = set()
    for state in states:
        for fact in state.facts:
            fact_ids.add(fact.fact_id)
            evidence_ids.update(fact.evidence_ids)
    return sorted(fact_ids), sorted(evidence_ids)


def _unsupported_time_operator(
    constraints: list[QueryTimeConstraintV1],
) -> bool:
    return any(item.operator not in {"exact", "latest"} for item in constraints)


def _contains_literal_term(plan: CompiledQueryPlanV2) -> bool:
    return any(
        role.term.kind == "literal"
        for group in plan.pattern_groups
        for atom in group.atoms
        for role in atom.roles
    )


def _has_ambiguous_time_scope(plan: CompiledQueryPlanV2) -> bool:
    return bool(plan.time_constraints) and any(
        len(group.atoms) > 1 for group in plan.pattern_groups
    )


def _evaluate_compiled_query_snapshot(
    plan: CompiledQueryPlanV2,
    snapshot: QueryExecutionSnapshotV1,
) -> QuerySnapshotEvaluationV1:
    if plan.memory_view != snapshot.memory_view:
        return _abstain(plan, "memory_view_mismatch")
    if plan.ontology_revision != snapshot.ontology_revision:
        return _abstain(plan, "ontology_revision_mismatch")
    if plan.identity_revision != snapshot.identity_revision:
        return _abstain(plan, "identity_revision_mismatch")
    if plan.registry_revision != snapshot.registry_revision:
        return _abstain(plan, "registry_revision_mismatch")
    if plan.registry_sha256 != snapshot.registry_sha256:
        return _abstain(plan, "registry_hash_mismatch")
    if (
        plan.identity_snapshot_id != snapshot.identity_snapshot_id
        or plan.identity_input_fingerprint
        != snapshot.identity_input_fingerprint
    ):
        return _abstain(plan, "identity_snapshot_mismatch")
    if plan.explicit_absence_requested:
        return _abstain(plan, "explicit_absence_unsupported")
    if plan.answer.kind not in {"fact", "count"}:
        return _abstain(plan, "unsupported_answer_kind")
    if _contains_literal_term(plan):
        return _abstain(plan, "literal_execution_unsupported")
    if _unsupported_time_operator(plan.time_constraints):
        return _abstain(plan, "unsupported_time_operator")
    if _has_ambiguous_time_scope(plan):
        return _abstain(plan, "multi_atom_time_scope_unsupported")

    states: list[_MatchState] = []
    for group_index in range(len(plan.pattern_groups)):
        states.extend(_execute_group(plan, group_index, snapshot))
    states = _deduplicate_states(states, answer_variable=plan.answer.variable)
    if not states:
        reason = (
            "explicit_absence_not_proven"
            if plan.evidence_policy == "require_explicit_absence"
            else "no_matching_facts"
        )
        return _abstain(plan, reason)

    if plan.conflict_policy == "require_resolved":
        if any(fact.lifecycle == "conflicted" for state in states for fact in state.facts):
            return _abstain(plan, "conflict_unresolved", states=states)

    states, latest_error = _latest_states(plan, states)
    if latest_error is not None:
        return _abstain(plan, latest_error, states=states)

    answer_values = sorted(
        {
            value
            for state in states
            if (value := state.bindings.get(plan.answer.variable)) is not None
        }
    )
    if not answer_values:
        return _abstain(plan, "answer_variable_unbound", states=states)

    if plan.answer.identity_resolution_required:
        if any(snapshot.identity_status.get(value) != "resolved" for value in answer_values):
            return _abstain(
                plan,
                "answer_identity_unresolved",
                states=states,
            )

    if plan.evidence_policy in {"provenance_closure", "require_explicit_absence"}:
        if any(
            fact.provenance is None
            or (
                fact.level == "L1"
                and fact.provenance.unit_revision_id != fact.fact_id
            )
            for state in states
            for fact in state.facts
        ):
            return _abstain(
                plan,
                "unverified_fact_provenance",
                states=states,
            )
        if any(not fact.evidence_ids for state in states for fact in state.facts):
            return _abstain(
                plan,
                "incomplete_evidence_closure",
                states=states,
            )

    fact_ids, evidence_ids = _facts_and_evidence(states)
    return QuerySnapshotEvaluationV1(
        query_id=plan.query_id,
        plan_sha256=plan.plan_sha256,
        matched_fact_ids=fact_ids,
        answer_values=answer_values,
        count_value=len(answer_values) if plan.answer.kind == "count" else None,
        required_evidence_ids=evidence_ids,
        closure_complete=True,
        abstained=False,
        reason="compiled_query_complete",
    )
