from __future__ import annotations

import hashlib
from collections import Counter
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .authoritative_memory import AuthoritativeQueryPlan, ExactTimeConstraint
from .io import canonical_json_bytes
from .semantic_ir import (
    DEFAULT_FALLBACK_BLOCKED_REASONS,
    Lifecycle,
    Modality,
    Polarity,
    QueryIntent,
    RoleBinding,
    SourceStatus,
    TargetLevel,
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


DraftTermKind = Literal["entity_surface", "variable", "literal"]
CompiledTermKind = Literal["entity", "variable", "literal"]
AnswerKindV2 = Literal["fact", "evidence_set", "count", "polarity", "entity_list"]
DistinctPolicy = Literal["canonical_identity", "unit", "value"]
ConflictPolicy = Literal["require_resolved", "return_all"]
SupersessionPolicy = Literal["current_only", "include_history"]
EvidencePolicy = Literal[
    "single_fact",
    "provenance_closure",
    "require_explicit_absence",
]
IdentityStatus = Literal["resolved", "unresolved"]
TimeField = Literal["event_time", "valid_time", "transaction_time"]
TimeOperator = Literal["exact", "before", "after", "between", "latest", "as_of"]

FALLBACK_ALLOWED_REASONS = [
    "unresolved_entity",
    "lexical_predicate_missing_link",
]


class GitMemoryViewRefV1(StrictModel):
    schema_version: Literal["git-memory-view-ref-v1"] = "git-memory-view-ref-v1"
    workspace_id: str = Field(min_length=1)
    repository_epoch_id: str = Field(min_length=1)
    checkpoint_id: str = Field(min_length=1)
    git_commit: str = Field(pattern=r"^[0-9a-f]{40,64}$")
    authoritative_ref: Literal["refs/heads/authoritative"] = (
        "refs/heads/authoritative"
    )


class QueryContextV1(StrictModel):
    schema_version: Literal["query-context-v1"] = "query-context-v1"
    query_id: str = Field(min_length=1)
    raw_query: str = Field(min_length=1)
    query_time: str = Field(min_length=1)
    current_user_entity_id: str | None = None
    memory_view: GitMemoryViewRefV1
    ontology_revision: str = Field(min_length=1)
    identity_revision: str = Field(min_length=1)
    compiler_policy_revision: str = Field(min_length=1)


class PredicateRegistryEntryV1(StrictModel):
    schema_version: Literal["predicate-registry-entry-v1"] = (
        "predicate-registry-entry-v1"
    )
    sense: str = Field(min_length=1)
    canonical_operator: str = Field(min_length=1)
    role_types: dict[str, str] = Field(min_length=1)


class CompilerRegistryV1(StrictModel):
    schema_version: Literal["query-compiler-registry-v1"] = (
        "query-compiler-registry-v1"
    )
    ontology_revision: str = Field(min_length=1)
    identity_revision: str = Field(min_length=1)
    registry_revision: str = Field(min_length=1)
    registry_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    identity_snapshot_id: str | None = None
    identity_input_fingerprint: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    entity_aliases: dict[str, list[str]]
    entity_types: dict[str, list[str]]
    identity_status: dict[str, IdentityStatus]
    predicate_aliases: dict[str, list[PredicateRegistryEntryV1]]

    @model_validator(mode="after")
    def validate_content_binding(self) -> "CompilerRegistryV1":
        if (self.identity_snapshot_id is None) != (
            self.identity_input_fingerprint is None
        ):
            raise ValueError(
                "identity snapshot ID and input fingerprint must be set together"
            )
        payload = self.model_dump(mode="json", exclude={"registry_sha256"})
        expected = _plan_hash(payload)
        if self.registry_sha256 is None:
            object.__setattr__(self, "registry_sha256", expected)
        elif self.registry_sha256 != expected:
            raise ValueError("compiler registry hash mismatch")
        return self


class QueryTermDraftV1(StrictModel):
    schema_version: Literal["query-term-draft-v1"] = "query-term-draft-v1"
    kind: DraftTermKind
    value: str = Field(min_length=1)
    expected_type: str | None = None

    @model_validator(mode="after")
    def validate_term(self) -> "QueryTermDraftV1":
        if self.kind == "variable" and not self.value.startswith("?"):
            raise ValueError("draft variable must start with ?")
        if self.kind != "variable" and self.value.startswith("?"):
            raise ValueError("only variable terms may start with ?")
        return self


class QueryRoleDraftV1(StrictModel):
    schema_version: Literal["query-role-draft-v1"] = "query-role-draft-v1"
    role: str = Field(min_length=1)
    role_name: str = Field(min_length=1)
    term: QueryTermDraftV1


class QueryAtomDraftV1(StrictModel):
    schema_version: Literal["query-atom-draft-v1"] = "query-atom-draft-v1"
    atom_id: str = Field(min_length=1)
    predicate_surface: str = Field(min_length=1)
    roles: list[QueryRoleDraftV1] = Field(min_length=1)
    modality: Modality | None = None
    polarity: Polarity | None = None

    @model_validator(mode="after")
    def validate_roles(self) -> "QueryAtomDraftV1":
        roles = [item.role for item in self.roles]
        if len(roles) != len(set(roles)):
            raise ValueError("atom roles must be unique")
        return self


class QueryPatternGroupDraftV1(StrictModel):
    schema_version: Literal["query-pattern-group-draft-v1"] = (
        "query-pattern-group-draft-v1"
    )
    group_id: str = Field(min_length=1)
    atoms: list[QueryAtomDraftV1] = Field(min_length=1)


class AnswerDraftV1(StrictModel):
    schema_version: Literal["query-answer-draft-v1"] = "query-answer-draft-v1"
    kind: AnswerKindV2
    variable: str = Field(pattern=r"^\?[A-Za-z][A-Za-z0-9_]*$")
    distinct_by: DistinctPolicy | None = None


class QueryTimeConstraintV1(StrictModel):
    schema_version: Literal["query-time-constraint-v1"] = (
        "query-time-constraint-v1"
    )
    field: TimeField
    operator: TimeOperator
    value: str | None = None

    @model_validator(mode="after")
    def validate_value(self) -> "QueryTimeConstraintV1":
        if self.operator in {"exact", "before", "after", "between", "as_of"}:
            if self.value is None:
                raise ValueError(f"{self.operator} time constraint requires value")
        if self.operator == "latest" and self.value is not None:
            raise ValueError("latest time constraint cannot bind a value")
        return self


class QueryDraftV1(StrictModel):
    schema_version: Literal["natural-query-draft-v1"] = "natural-query-draft-v1"
    query_id: str = Field(min_length=1)
    intent: QueryIntent
    target_level: TargetLevel
    answer: AnswerDraftV1
    pattern_groups: list[QueryPatternGroupDraftV1] = Field(min_length=1)
    time_constraints: list[QueryTimeConstraintV1] = Field(default_factory=list)
    lifecycle: Lifecycle | None = None
    source_status_constraints: list[SourceStatus] = Field(default_factory=list)
    conflict_policy: ConflictPolicy
    supersession_policy: SupersessionPolicy
    evidence_policy: EvidencePolicy
    explicit_absence_requested: bool = False
    producer_id: str = Field(min_length=1)
    producer_version: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_ids(self) -> "QueryDraftV1":
        group_ids = [item.group_id for item in self.pattern_groups]
        if len(group_ids) != len(set(group_ids)):
            raise ValueError("query pattern group ids must be unique")
        atom_ids = [
            atom.atom_id
            for group in self.pattern_groups
            for atom in group.atoms
        ]
        if len(atom_ids) != len(set(atom_ids)):
            raise ValueError("query atom ids must be unique")
        return self


class QueryTermV2(StrictModel):
    schema_version: Literal["compiled-query-term-v2"] = "compiled-query-term-v2"
    kind: CompiledTermKind
    value: str = Field(min_length=1)
    entity_type: str | None = None

    @model_validator(mode="after")
    def validate_term(self) -> "QueryTermV2":
        if self.kind == "variable" and not self.value.startswith("?"):
            raise ValueError("compiled variable must start with ?")
        if self.kind != "variable" and self.value.startswith("?"):
            raise ValueError("only compiled variables may start with ?")
        return self


class QueryRoleV2(StrictModel):
    schema_version: Literal["compiled-query-role-v2"] = "compiled-query-role-v2"
    role: str = Field(min_length=1)
    role_name: str = Field(min_length=1)
    term: QueryTermV2


class QueryAtomV2(StrictModel):
    schema_version: Literal["compiled-query-atom-v2"] = "compiled-query-atom-v2"
    atom_id: str = Field(min_length=1)
    predicate_sense: str = Field(min_length=1)
    canonical_operator: str = Field(min_length=1)
    roles: list[QueryRoleV2] = Field(min_length=1)
    modality: Modality | None = None
    polarity: Polarity | None = None


class QueryPatternGroupV2(StrictModel):
    schema_version: Literal["compiled-query-pattern-group-v2"] = (
        "compiled-query-pattern-group-v2"
    )
    group_id: str = Field(min_length=1)
    atoms: list[QueryAtomV2] = Field(min_length=1)


class AnswerSpecV2(StrictModel):
    schema_version: Literal["compiled-query-answer-v2"] = (
        "compiled-query-answer-v2"
    )
    kind: AnswerKindV2
    variable: str = Field(pattern=r"^\?[A-Za-z][A-Za-z0-9_]*$")
    distinct_by: DistinctPolicy | None = None
    identity_resolution_required: bool = False


def _plan_hash(payload: dict[str, object]) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


class CompiledQueryPlanV2(StrictModel):
    schema_version: Literal["compiled-query-plan-v2"] = "compiled-query-plan-v2"
    query_id: str = Field(min_length=1)
    raw_query: str = Field(min_length=1)
    query_time: str = Field(min_length=1)
    memory_view: GitMemoryViewRefV1
    ontology_revision: str = Field(min_length=1)
    identity_revision: str = Field(min_length=1)
    compiler_policy_revision: str = Field(min_length=1)
    registry_revision: str = Field(min_length=1)
    registry_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    identity_snapshot_id: str | None = None
    identity_input_fingerprint: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    intent: QueryIntent
    target_level: TargetLevel
    answer: AnswerSpecV2
    pattern_groups: list[QueryPatternGroupV2] = Field(min_length=1)
    time_constraints: list[QueryTimeConstraintV1] = Field(default_factory=list)
    lifecycle: Lifecycle | None = None
    source_status_constraints: list[SourceStatus] = Field(default_factory=list)
    conflict_policy: ConflictPolicy
    supersession_policy: SupersessionPolicy
    evidence_policy: EvidencePolicy
    explicit_absence_requested: bool = False
    fallback_allowed_reasons: list[str]
    fallback_blocked_reasons: list[str]
    plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_plan_hash(self) -> "CompiledQueryPlanV2":
        if (self.identity_snapshot_id is None) != (
            self.identity_input_fingerprint is None
        ):
            raise ValueError(
                "identity snapshot ID and input fingerprint must be set together"
            )
        payload = self.model_dump(exclude={"plan_sha256"})
        if _plan_hash(payload) != self.plan_sha256:
            raise ValueError("compiled query plan hash mismatch")
        return self


class QueryCompilationResultV1(StrictModel):
    schema_version: Literal["query-compilation-result-v1"] = (
        "query-compilation-result-v1"
    )
    query_id: str = Field(min_length=1)
    status: Literal["executable", "abstain"]
    plan: CompiledQueryPlanV2 | None = None
    unresolved_slots: list[str] = Field(default_factory=list)
    blocked_reasons: list[str] = Field(default_factory=list)
    fallback_allowed: bool = False
    fallback_reason: str | None = None

    @model_validator(mode="after")
    def validate_status(self) -> "QueryCompilationResultV1":
        if self.status == "executable" and self.plan is None:
            raise ValueError("executable compilation requires plan")
        if self.status == "abstain" and self.plan is not None:
            raise ValueError("abstaining compilation cannot expose executable plan")
        if self.fallback_allowed and self.fallback_reason is None:
            raise ValueError("allowed fallback requires reason")
        if not self.fallback_allowed and self.fallback_reason is not None:
            raise ValueError("blocked fallback cannot expose reason")
        return self


class QueryDraftRequestV1(StrictModel):
    schema_version: Literal["query-draft-request-v1"] = "query-draft-request-v1"
    raw_query: str = Field(min_length=1)
    query_id: str = Field(min_length=1)
    query_time: str = Field(min_length=1)
    current_user_surface: str | None = None
    compiler_policy_revision: str = Field(min_length=1)


class QueryDraftProducer(Protocol):
    def produce(self, request: QueryDraftRequestV1) -> QueryDraftV1: ...


def _normalized(value: str) -> str:
    return " ".join(value.casefold().split())


def _entity_candidates(
    surface: str,
    *,
    context: QueryContextV1,
    registry: CompilerRegistryV1,
) -> list[str]:
    candidates = list(registry.entity_aliases.get(_normalized(surface), []))
    if _normalized(surface) in {"i", "me", "myself"}:
        current = context.current_user_entity_id
        if current is not None and current not in candidates:
            candidates.append(current)
    return list(dict.fromkeys(candidates))


def _fallback_result(
    *,
    query_id: str,
    unresolved_slots: list[str],
    blocked_reasons: list[str],
) -> QueryCompilationResultV1:
    fallback_reason: str | None = None
    if not blocked_reasons and unresolved_slots:
        if any(slot.startswith("entity:") for slot in unresolved_slots):
            fallback_reason = "unresolved_entity"
        elif all(slot.startswith("predicate:") for slot in unresolved_slots):
            fallback_reason = "lexical_predicate_missing_link"
    return QueryCompilationResultV1(
        query_id=query_id,
        status="abstain",
        unresolved_slots=list(dict.fromkeys(unresolved_slots)),
        blocked_reasons=list(dict.fromkeys(blocked_reasons)),
        fallback_allowed=fallback_reason is not None,
        fallback_reason=fallback_reason,
    )


def _is_current_query(raw_query: str) -> bool:
    value = _normalized(raw_query)
    markers = ("current", "currently", "latest", "recent", "now", "现在", "当前", "最近")
    return any(marker in value for marker in markers)


def _compile_term(
    *,
    atom_id: str,
    role: QueryRoleDraftV1,
    required_type: str,
    context: QueryContextV1,
    registry: CompilerRegistryV1,
    unresolved_slots: list[str],
    blocked_reasons: list[str],
) -> QueryTermV2 | None:
    term = role.term
    if term.kind == "variable":
        return QueryTermV2(
            kind="variable",
            value=term.value,
            entity_type=term.expected_type or required_type,
        )
    if term.kind == "literal":
        return QueryTermV2(
            kind="literal",
            value=term.value,
            entity_type=term.expected_type,
        )

    candidates = _entity_candidates(
        term.value,
        context=context,
        registry=registry,
    )
    if len(candidates) != 1:
        unresolved_slots.append(f"entity:{atom_id}:{role.role}")
        return None
    entity_id = candidates[0]
    if registry.identity_status.get(entity_id) != "resolved":
        blocked_reasons.append(f"identity_unresolved:{atom_id}:{role.role}")
        return None
    entity_types = set(registry.entity_types.get(entity_id, []))
    if required_type not in entity_types:
        blocked_reasons.append(f"role_type_mismatch:{atom_id}:{role.role}")
        return None
    return QueryTermV2(
        kind="entity",
        value=entity_id,
        entity_type=required_type,
    )


def _compile_atom(
    atom: QueryAtomDraftV1,
    *,
    context: QueryContextV1,
    registry: CompilerRegistryV1,
    unresolved_slots: list[str],
    blocked_reasons: list[str],
) -> QueryAtomV2 | None:
    predicates = registry.predicate_aliases.get(_normalized(atom.predicate_surface), [])
    if len(predicates) != 1:
        unresolved_slots.append(f"predicate:{atom.atom_id}")
        return None
    predicate = predicates[0]
    roles: list[QueryRoleV2] = []
    for role in atom.roles:
        required_type = predicate.role_types.get(role.role)
        if required_type is None:
            blocked_reasons.append(f"unknown_role:{atom.atom_id}:{role.role}")
            continue
        term = _compile_term(
            atom_id=atom.atom_id,
            role=role,
            required_type=required_type,
            context=context,
            registry=registry,
            unresolved_slots=unresolved_slots,
            blocked_reasons=blocked_reasons,
        )
        if term is not None:
            roles.append(
                QueryRoleV2(
                    role=role.role,
                    role_name=role.role_name,
                    term=term,
                )
            )
    if len(roles) != len(atom.roles):
        return None
    return QueryAtomV2(
        atom_id=atom.atom_id,
        predicate_sense=predicate.sense,
        canonical_operator=predicate.canonical_operator,
        roles=roles,
        modality=atom.modality,
        polarity=atom.polarity,
    )


def _validate_query_semantics(
    draft: QueryDraftV1,
    *,
    compiled_groups: list[QueryPatternGroupV2],
    raw_query: str,
) -> list[str]:
    blocked: list[str] = []
    if draft.answer.kind not in {"fact", "count"}:
        blocked.append(
            f"answer_kind_execution_unsupported:{draft.answer.kind}"
        )
    if draft.answer.kind == "count" and draft.answer.distinct_by != "canonical_identity":
        blocked.append("count_requires_canonical_identity")
    if any(
        role.term.kind == "literal"
        for group in compiled_groups
        for atom in group.atoms
        for role in atom.roles
    ):
        blocked.append("literal_execution_unsupported")
    unsupported_time_operators = sorted(
        {
            item.operator
            for item in draft.time_constraints
            if item.operator not in {"exact", "latest"}
        }
    )
    blocked.extend(
        f"time_operator_execution_unsupported:{operator}"
        for operator in unsupported_time_operators
    )
    if sum(
        item.operator == "latest" for item in draft.time_constraints
    ) > 1:
        blocked.append("multiple_latest_constraints_unsupported")
    if draft.time_constraints and any(
        len(group.atoms) > 1 for group in compiled_groups
    ):
        blocked.append("multi_atom_time_scope_unsupported")
    if _is_current_query(raw_query):
        has_latest = any(
            item.field == "valid_time" and item.operator == "latest"
            for item in draft.time_constraints
        )
        if not has_latest or draft.lifecycle != "active":
            blocked.append("current_query_requires_valid_time_latest")
    if draft.explicit_absence_requested:
        if draft.evidence_policy != "require_explicit_absence":
            blocked.append("explicit_absence_requires_closure")
        blocked.append("explicit_absence_execution_unsupported")

    for group in compiled_groups:
        counts = Counter(
            role.term.value
            for atom in group.atoms
            for role in atom.roles
            if role.term.kind == "variable"
        )
        if draft.answer.variable not in counts:
            blocked.append(
                f"answer_variable_unbound:{group.group_id}:{draft.answer.variable}"
            )
        for variable, count in counts.items():
            if variable != draft.answer.variable and count < 2:
                blocked.append(f"disconnected_variable:{variable}")
    return blocked


def _make_compiled_plan(
    *,
    draft: QueryDraftV1,
    context: QueryContextV1,
    registry: CompilerRegistryV1,
    compiled_groups: list[QueryPatternGroupV2],
) -> CompiledQueryPlanV2:
    if registry.registry_sha256 is None:
        raise ValueError("compiler registry content hash is missing")
    answer = AnswerSpecV2(
        kind=draft.answer.kind,
        variable=draft.answer.variable,
        distinct_by=draft.answer.distinct_by,
        identity_resolution_required=draft.answer.kind == "count",
    )
    payload: dict[str, object] = {
        "schema_version": "compiled-query-plan-v2",
        "query_id": draft.query_id,
        "raw_query": context.raw_query,
        "query_time": context.query_time,
        "memory_view": context.memory_view.model_dump(mode="json"),
        "ontology_revision": context.ontology_revision,
        "identity_revision": context.identity_revision,
        "compiler_policy_revision": context.compiler_policy_revision,
        "registry_revision": registry.registry_revision,
        "registry_sha256": registry.registry_sha256,
        "identity_snapshot_id": registry.identity_snapshot_id,
        "identity_input_fingerprint": registry.identity_input_fingerprint,
        "intent": draft.intent,
        "target_level": draft.target_level,
        "answer": answer.model_dump(mode="json"),
        "pattern_groups": [item.model_dump(mode="json") for item in compiled_groups],
        "time_constraints": [
            item.model_dump(mode="json") for item in draft.time_constraints
        ],
        "lifecycle": draft.lifecycle,
        "source_status_constraints": list(draft.source_status_constraints),
        "conflict_policy": draft.conflict_policy,
        "supersession_policy": draft.supersession_policy,
        "evidence_policy": draft.evidence_policy,
        "explicit_absence_requested": draft.explicit_absence_requested,
        "fallback_allowed_reasons": list(FALLBACK_ALLOWED_REASONS),
        "fallback_blocked_reasons": list(DEFAULT_FALLBACK_BLOCKED_REASONS),
    }
    return CompiledQueryPlanV2(
        **payload,
        plan_sha256=_plan_hash(payload),
    )


def compile_query_draft(
    draft: QueryDraftV1,
    context: QueryContextV1,
    registry: CompilerRegistryV1,
) -> QueryCompilationResultV1:
    registry = CompilerRegistryV1.model_validate(
        registry.model_dump(mode="json")
    )
    if draft.query_id != context.query_id:
        raise ValueError("draft query_id must match query context")
    if context.ontology_revision != registry.ontology_revision:
        raise ValueError("query context ontology revision must match compiler registry")
    if context.identity_revision != registry.identity_revision:
        raise ValueError("query context identity revision must match compiler registry")

    unresolved_slots: list[str] = []
    blocked_reasons: list[str] = []
    compiled_groups: list[QueryPatternGroupV2] = []
    for group in draft.pattern_groups:
        atoms: list[QueryAtomV2] = []
        for atom in group.atoms:
            compiled = _compile_atom(
                atom,
                context=context,
                registry=registry,
                unresolved_slots=unresolved_slots,
                blocked_reasons=blocked_reasons,
            )
            if compiled is not None:
                atoms.append(compiled)
        if len(atoms) == len(group.atoms):
            compiled_groups.append(
                QueryPatternGroupV2(group_id=group.group_id, atoms=atoms)
            )

    if not unresolved_slots and not blocked_reasons:
        blocked_reasons.extend(
            _validate_query_semantics(
                draft,
                compiled_groups=compiled_groups,
                raw_query=context.raw_query,
            )
        )
    if unresolved_slots or blocked_reasons:
        return _fallback_result(
            query_id=draft.query_id,
            unresolved_slots=unresolved_slots,
            blocked_reasons=blocked_reasons,
        )

    plan = _make_compiled_plan(
        draft=draft,
        context=context,
        registry=registry,
        compiled_groups=compiled_groups,
    )
    return QueryCompilationResultV1(
        query_id=draft.query_id,
        status="executable",
        plan=plan,
    )


def _lower_time_constraint(
    constraints: list[QueryTimeConstraintV1],
) -> ExactTimeConstraint | None:
    if not constraints:
        return None
    if any(item.operator != "exact" for item in constraints):
        raise ValueError("compiled query plan cannot lower non-exact time to v1")
    values: dict[str, str | None] = {
        "event_time": None,
        "valid_time": None,
        "transaction_time": None,
    }
    for item in constraints:
        if values[item.field] is not None:
            raise ValueError("compiled query plan cannot lower duplicate time axis to v1")
        values[item.field] = item.value
    return ExactTimeConstraint(**values)


def lower_to_authoritative_query_plan(
    plan: CompiledQueryPlanV2,
) -> AuthoritativeQueryPlan:
    if len(plan.pattern_groups) != 1 or len(plan.pattern_groups[0].atoms) != 1:
        raise ValueError("compiled query plan cannot lower OR or multi-hop to v1")
    if plan.explicit_absence_requested:
        raise ValueError("compiled query plan cannot lower explicit absence to v1")
    if plan.answer.kind == "count":
        raise ValueError("compiled query plan cannot lower generic count to v1")
    if plan.answer.kind not in {"fact", "evidence_set", "count"}:
        raise ValueError("compiled query plan cannot lower answer kind to v1")
    if any(
        role.term.kind == "literal"
        for group in plan.pattern_groups
        for atom in group.atoms
        for role in atom.roles
    ):
        raise ValueError("compiled query plan cannot lower literal terms to v1")

    atom = plan.pattern_groups[0].atoms[0]
    concrete_roles = [role for role in atom.roles if role.term.kind == "entity"]
    role_constraints = [
        RoleBinding(
            role=role.role,
            role_name=role.role_name,
            entity_id=role.term.value,
        )
        for role in concrete_roles
    ]
    entity_ids = list(dict.fromkeys(role.term.value for role in concrete_roles))
    return AuthoritativeQueryPlan(
        query_id=plan.query_id,
        intent=plan.intent,
        target_level=plan.target_level,
        answer_kind=plan.answer.kind,
        entity_ids=entity_ids,
        predicate_sense=atom.predicate_sense,
        canonical_operator=atom.canonical_operator,
        role_constraints=role_constraints,
        time_constraint=_lower_time_constraint(plan.time_constraints),
        modality=atom.modality,
        polarity=atom.polarity,
        source_status_constraints=plan.source_status_constraints,
        lifecycle=plan.lifecycle,
        fallback_allowed_reasons=plan.fallback_allowed_reasons,
        fallback_blocked_reasons=plan.fallback_blocked_reasons,
    )


def compile_natural_query(
    *,
    question: str,
    context: QueryContextV1,
    registry: CompilerRegistryV1,
    producer: QueryDraftProducer,
) -> QueryCompilationResultV1:
    request = QueryDraftRequestV1(
        raw_query=question,
        query_id=context.query_id,
        query_time=context.query_time,
        current_user_surface="I" if context.current_user_entity_id else None,
        compiler_policy_revision=context.compiler_policy_revision,
    )
    draft = producer.produce(request)
    effective_context = context.model_copy(update={"raw_query": question})
    return compile_query_draft(draft, effective_context, registry)
