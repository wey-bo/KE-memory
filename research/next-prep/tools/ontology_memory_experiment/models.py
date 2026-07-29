from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceTurn(StrictModel):
    turn_id: str = Field(pattern=r"^OME-S\d{3}-T\d{2}$")
    speaker: Literal["user", "agent", "tool"]
    text: str = Field(min_length=1)


class SourceScenario(StrictModel):
    scenario_id: str = Field(pattern=r"^OME-S\d{3}$")
    language: Literal["en"]
    turns: list[SourceTurn]
    question: str = Field(min_length=1)
    candidate_answer_budget: int = Field(ge=1, le=256)

    @model_validator(mode="after")
    def validate_turns(self) -> "SourceScenario":
        if not 4 <= len(self.turns) <= 8:
            raise ValueError("scenarios require four to eight turns")
        expected_prefix = f"{self.scenario_id}-"
        if len({turn.turn_id for turn in self.turns}) != len(self.turns):
            raise ValueError("turn IDs must be unique")
        if any(not turn.turn_id.startswith(expected_prefix) for turn in self.turns):
            raise ValueError("turn IDs must belong to their scenario")
        return self


class SourceDocument(StrictModel):
    schema_version: Literal["ontology-memory-source-v1"] = "ontology-memory-source-v1"
    scenarios: list[SourceScenario]


class Answer(StrictModel):
    kind: Literal["value", "unanswerable"]
    values: list[str]

    @model_validator(mode="after")
    def validate_exclusive_answer(self) -> "Answer":
        if self.kind == "unanswerable" and self.values:
            raise ValueError("unanswerable answers cannot contain values")
        if self.kind == "value" and not self.values:
            raise ValueError("value answers require at least one value")
        return self


Family = Literal[
    "roles_polarity_modality_quantity",
    "temporal_updates_conflicts_provenance",
    "conjunction_exact_set_multihop",
    "synonymy_sense_external_unanswerable",
]
Primitive = Literal[
    "role", "polarity", "modality", "quantity", "valid_time", "transaction_time",
    "provenance", "conflict", "supersession", "conjunction", "exact_set", "traversal",
    "synonym", "sense", "unanswerable",
]


class GoldScenario(StrictModel):
    scenario_id: str = Field(pattern=r"^OME-S\d{3}$")
    family: Family
    origin: Literal["architecture_directed", "neutral"]
    primary_system: Literal["mem0", "graphiti", "hindsight", "mempalace"] | None = None
    split: Literal["dev", "hidden"]
    competency: str = Field(min_length=1)
    answer: Answer
    required_evidence_turn_ids: list[str] = Field(min_length=1)
    hard_negative_turn_ids: list[str] = Field(min_length=2, max_length=4)
    required_primitives: list[Primitive] = Field(min_length=1)
    ablation_primitive: Primitive
    critical_constraints: list[str] = Field(min_length=1)
    architecture_claim_ids: list[str] = Field(min_length=1)
    proposed_ontology_remedy: str = Field(min_length=1)
    falsifier: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_origin(self) -> "GoldScenario":
        if (self.origin == "architecture_directed") != (self.primary_system is not None):
            raise ValueError("architecture attribution must match scenario origin")
        if len(set(self.required_evidence_turn_ids)) != len(self.required_evidence_turn_ids):
            raise ValueError("required evidence IDs must be unique")
        if len(set(self.hard_negative_turn_ids)) != len(self.hard_negative_turn_ids):
            raise ValueError("hard-negative IDs must be unique")
        if self.ablation_primitive not in self.required_primitives:
            raise ValueError("ablation primitive must be required by the scenario")
        return self


class GoldDocument(StrictModel):
    schema_version: Literal["ontology-memory-gold-v1"] = "ontology-memory-gold-v1"
    status: Literal["frozen"] = "frozen"
    scenarios: list[GoldScenario]


class OracleRepresentationScenario(StrictModel):
    scenario_id: str = Field(pattern=r"^OME-S\d{3}$")
    records: list["MemoryRecord"] = Field(min_length=1)
    ablated_records: list["MemoryRecord"] = Field(min_length=1)
    distractor_records: dict[str, list["MemoryRecord"]] = Field(default_factory=dict)


class OracleRepresentationDocument(StrictModel):
    schema_version: Literal[
        "ontology-memory-oracle-representations-v1",
        "ontology-memory-oracle-representations-v2",
    ] = "ontology-memory-oracle-representations-v2"
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    scenarios: list[OracleRepresentationScenario]


class OracleQueryPlanScenario(StrictModel):
    scenario_id: str = Field(pattern=r"^OME-S\d{3}$")
    query_plan: "QueryPlan"


class OracleQueryPlanDocument(StrictModel):
    schema_version: Literal[
        "ontology-memory-oracle-query-plans-v1",
        "ontology-memory-oracle-query-plans-v2",
    ] = "ontology-memory-oracle-query-plans-v2"
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    scenarios: list[OracleQueryPlanScenario]


class DistractorMemory(StrictModel):
    record_id: str = Field(pattern=r"^OME-D-S\d{3}-(50|500)-\d{3}$")
    scenario_id: str = Field(pattern=r"^OME-S\d{3}$")
    distractor_scale: Literal[50, 500]
    text: str = Field(min_length=1)


class DistractorDocument(StrictModel):
    schema_version: Literal["ontology-memory-distractors-v1"] = "ontology-memory-distractors-v1"
    records: list[DistractorMemory]


class MemoryRecord(StrictModel):
    record_id: str = Field(min_length=1)
    source_turn_ids: list[str] = Field(min_length=1)
    surface_text: str = Field(min_length=1)
    entities: list[str] = Field(default_factory=list)
    predicate: str | None = None
    roles: dict[str, str] = Field(default_factory=dict)
    polarity: Literal["positive", "negative"] | None = None
    modality: Literal["asserted", "possible", "requested", "planned"] | None = None
    quantity: str | None = None
    valid_time: str | None = None
    transaction_time: str | None = None
    provenance_status: Literal["user_reported", "agent_generated", "tool_observed"] | None = None
    lifecycle_status: Literal["supported", "current", "historical", "corroborating", "obsolete", "rejected"] | None = None
    conflict_group: str | None = None
    supersedes: list[str] = Field(default_factory=list)
    derived_from: list[str] = Field(default_factory=list)
    absent_slots: list[str] = Field(default_factory=list)
    relations: list[dict[str, str]] = Field(default_factory=list)


class TraversalStep(StrictModel):
    source: str = Field(min_length=1)
    predicate: str = Field(min_length=1)
    target: str | None = Field(default=None, min_length=1)
    target_slot: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_target(self) -> "TraversalStep":
        if (self.target is None) == (self.target_slot is None):
            raise ValueError("traversal step requires exactly one of target or target_slot")
        return self


class QueryPlan(StrictModel):
    entity_candidates: list[str] = Field(default_factory=list)
    predicate: str | None = None
    role_constraints: dict[str, str] = Field(default_factory=dict)
    polarity: Literal["positive", "negative"] | None = None
    modality: Literal["asserted", "possible", "requested", "planned"] | None = None
    quantity: str | None = None
    time_filter: str | None = None
    status_filter: str | None = None
    context_filter: str | None = None
    transaction_filter: Literal["latest"] | None = None
    provenance_filter: str | None = None
    conjunction_groups: list[list[str]] = Field(default_factory=list)
    traversal_steps: list[TraversalStep] = Field(default_factory=list)
    required_answer_slot: str = Field(min_length=1)
    declared_unresolved_slots: list[str] = Field(default_factory=list)
    evidence_expansion: Literal["none", "provenance_closure"] = "none"
    require_supersession: bool = False
    answer_policy: Literal["value_or_abstain", "require_explicit_absence"] = "value_or_abstain"

    @model_validator(mode="after")
    def validate_answer_is_not_bound(self) -> "QueryPlan":
        if self.required_answer_slot == "quantity" and self.quantity is not None:
            raise ValueError("a quantity answer cannot also be a quantity filter")
        if self.required_answer_slot == "polarity" and self.polarity is not None:
            raise ValueError("a polarity answer cannot also be a polarity filter")
        if self.required_answer_slot in self.role_constraints:
            raise ValueError("the required answer slot cannot be fixed by a role constraint")
        if self.traversal_steps and not any(
            step.target_slot == self.required_answer_slot for step in self.traversal_steps
        ):
            raise ValueError("a traversal answer must be produced by a target_slot binding")
        return self


class RankedEvidence(StrictModel):
    turn_id: str = Field(min_length=1)
    score: float
    rank: int = Field(ge=1)


class ArmResult(StrictModel):
    run_id: str = Field(min_length=1)
    track: Literal["oracle", "automatic"]
    arm: Literal["B0", "B1", "B2", "O-", "O+", "O+E"]
    scenario_id: str = Field(pattern=r"^OME-S\d{3}$")
    distractor_scale: Literal[0, 50, 500]
    ranked_evidence: list[RankedEvidence] = Field(default_factory=list)
    selected_evidence_turn_ids: list[str]
    predicted_answer: Answer | None = None
    constraint_checks: dict[str, bool] = Field(default_factory=dict)
    symbolic_trace: list[str] = Field(default_factory=list)
    fallback_reason: Literal["unresolved_entity", "uncovered_predicate", "missing_required_slot", "empty_symbolic_result"] | None = None
    rejected_fallback_turn_ids: list[str] = Field(default_factory=list)
    latency_ms: float | None = Field(default=None, ge=0)
    model_metadata: dict[str, Any] = Field(default_factory=dict)
    status: Literal["ok", "error", "abstained"]
    error: str | None = None


class RunManifest(StrictModel):
    schema_version: Literal["ontology-memory-run-manifest-v1"] = "ontology-memory-run-manifest-v1"
    files: dict[str, dict[str, str]]
