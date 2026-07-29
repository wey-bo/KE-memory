from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .extraction_bridge_assessment import (
    ExtractionCompatibilityLedger,
    replay_extraction_inputs,
)
from .io import (
    canonical_json_bytes,
    load_json,
    sha256_file,
    write_json_immutable,
    write_text_immutable,
)
from .authoritative_memory import MemoryRepresentationBundleV3, canonical_sha256
from .authoritative_conformance_runner import build_authoritative_conformance_bundle


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


L1Decision = Literal["emit_l1", "abstain", "no_memory"]
L1Kind = Literal["event", "state", "preference", "task", "attribute"]
TypedModality = Literal[
    "actual",
    "planned",
    "hypothetical",
    "requested",
    "recommended",
    "denied",
]
TypedPolarity = Literal["positive", "negative"]


class TypedPredicate(StrictModel):
    surface: str = Field(min_length=1)
    sense: str = Field(min_length=1)
    canonical_operator: str = Field(min_length=1)


class TypedLocalEntity(StrictModel):
    local_entity_id: str = Field(pattern=r"^entity-[0-9]{2}$")
    surface: str = Field(min_length=1)


class TypedRoleBinding(StrictModel):
    role: str = Field(min_length=1)
    role_name: str = Field(min_length=1)
    local_entity_id: str = Field(pattern=r"^entity-[0-9]{2}$")


class TypedConditionBinding(StrictModel):
    operator: str = Field(min_length=1)
    value: str = Field(min_length=1)
    local_entity_ids: list[str] = Field(default_factory=list)


class TypedScopeBinding(StrictModel):
    operator: str = Field(min_length=1)
    value: str = Field(min_length=1)
    local_entity_ids: list[str] = Field(default_factory=list)


class TypedEvidenceBinding(StrictModel):
    evidence_id: str = Field(min_length=1)
    speaker: Literal["user", "assistant", "tool"]


class TypedDerivationProvenance(StrictModel):
    method: Literal["explicit", "context_completed", "inferred"]
    basis: str | None = None
    evidence_ids: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_basis(self) -> "TypedDerivationProvenance":
        if self.method == "explicit" and self.basis is not None:
            raise ValueError("explicit derivation must not include a basis")
        if self.method != "explicit" and not self.basis:
            raise ValueError("non-explicit derivation requires a basis")
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("duplicate derivation evidence")
        return self


class TypedTimeBinding(StrictModel):
    event_time: str | None = None
    valid_time: str | None = None


class TypedLifecycleBinding(StrictModel):
    lifecycle: Literal["active", "superseded", "conflicted"]
    replacement_candidate_ref: str | None = None
    replaces_candidate_refs: list[str] = Field(default_factory=list)
    supersedes_candidate_refs: list[str] = Field(default_factory=list)
    conflicts_with_candidate_refs: list[str] = Field(default_factory=list)


class TypedOperationProvenance(StrictModel):
    confirmed_by_operation_refs: list[str] = Field(default_factory=list)
    added_by_operation_refs: list[str] = Field(default_factory=list)


class TypedL1Candidate(StrictModel):
    kind: L1Kind
    predicate: TypedPredicate
    local_entities: list[TypedLocalEntity] = Field(min_length=1)
    roles: list[TypedRoleBinding] = Field(min_length=1)
    modality: TypedModality
    polarity: TypedPolarity
    time: TypedTimeBinding
    condition_bindings: list[TypedConditionBinding] = Field(default_factory=list)
    scope_bindings: list[TypedScopeBinding] = Field(default_factory=list)
    derivation: TypedDerivationProvenance
    evidence_bindings: list[TypedEvidenceBinding] = Field(min_length=1)
    lifecycle: TypedLifecycleBinding
    operation_provenance: TypedOperationProvenance

    @model_validator(mode="after")
    def validate_reference_closure(self) -> "TypedL1Candidate":
        local_ids = [item.local_entity_id for item in self.local_entities]
        expected_ids = [f"entity-{index:02d}" for index in range(1, len(local_ids) + 1)]
        if local_ids != expected_ids:
            raise ValueError("local entity IDs must be contiguous and ordered")
        local_id_set = set(local_ids)
        for role in self.roles:
            if role.local_entity_id not in local_id_set:
                raise ValueError("role references unknown local entity")
        for binding in [*self.condition_bindings, *self.scope_bindings]:
            if not set(binding.local_entity_ids).issubset(local_id_set):
                raise ValueError("qualifier references unknown local entity")
        evidence_ids = [item.evidence_id for item in self.evidence_bindings]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("duplicate evidence binding")
        if not set(self.derivation.evidence_ids).issubset(set(evidence_ids)):
            raise ValueError("derivation evidence is not bound to the candidate")
        return self


class L1ProposalRecord(StrictModel):
    case_id: str = Field(pattern=r"^case-[0-9a-f]{16}$")
    candidate_ref: str = Field(pattern=r"^candidate-[0-9a-f]{16}$")
    decision: L1Decision
    confidence: float = Field(ge=0.0, le=1.0)
    typed_candidate: TypedL1Candidate | None = None
    reason_code: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_decision_union(self) -> "L1ProposalRecord":
        if self.decision == "emit_l1" and self.typed_candidate is None:
            raise ValueError("emit_l1 requires typed_candidate")
        if self.decision != "emit_l1" and self.typed_candidate is not None:
            raise ValueError("non-emission decision must not include typed_candidate")
        return self


class L1ProposalPayload(StrictModel):
    schema_version: Literal["typed-extractor-l1-proposals-v1"] = (
        "typed-extractor-l1-proposals-v1"
    )
    dataset_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    proposer_id: str = Field(min_length=1)
    proposer_version: str = Field(min_length=1)
    case_count: int = Field(ge=1)
    proposals: list[L1ProposalRecord] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_cases(self) -> "L1ProposalPayload":
        case_ids = [item.case_id for item in self.proposals]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("duplicate proposal case")
        if self.case_count != len(self.proposals):
            raise ValueError("proposal case count mismatch")
        return self


class L1SourceCase(StrictModel):
    private_case_id: str = Field(min_length=1)
    knowledge_id: str = Field(min_length=1)
    expected_decision: L1Decision
    expected_typed_candidate: TypedL1Candidate | None = None
    emission_allowed: bool
    allowed_modalities: list[TypedModality] = Field(default_factory=list)
    allowed_event_times: list[str] = Field(default_factory=list)
    event_time_may_be_null: bool = True
    allowed_valid_times: list[str] = Field(default_factory=list)
    valid_time_may_be_null: bool = True
    unresolved_required_fields: list[str] = Field(default_factory=list)
    time_case: Literal["none", "resolved", "unresolved"] = "none"

    @model_validator(mode="after")
    def validate_expected_union(self) -> "L1SourceCase":
        if self.expected_decision == "emit_l1" and self.expected_typed_candidate is None:
            raise ValueError("emitting source case requires expected typed candidate")
        if self.expected_decision != "emit_l1" and self.expected_typed_candidate is not None:
            raise ValueError("non-emitting source case cannot include expected typed candidate")
        if self.emission_allowed != (self.expected_decision == "emit_l1"):
            raise ValueError("emission authority must match the dev decision")
        if self.emission_allowed and not self.allowed_modalities:
            raise ValueError("emitting source case requires an allowed modality")
        return self


class L1SourceConfig(StrictModel):
    schema_version: Literal["typed-extractor-l1-source-v1"] = (
        "typed-extractor-l1-source-v1"
    )
    dataset_id: str = Field(min_length=1)
    public_vocabulary: dict[str, list[str]] = Field(default_factory=dict)
    cases: list[L1SourceCase] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_cases(self) -> "L1SourceConfig":
        private_ids = [item.private_case_id for item in self.cases]
        knowledge_ids = [item.knowledge_id for item in self.cases]
        if len(private_ids) != len(set(private_ids)):
            raise ValueError("duplicate private case ID")
        if len(knowledge_ids) != len(set(knowledge_ids)):
            raise ValueError("duplicate source knowledge ID")
        for key, values in self.public_vocabulary.items():
            if not key or not values:
                raise ValueError("public vocabulary entries must be non-empty")
            if len(values) != len(set(values)):
                raise ValueError("duplicate public vocabulary value")
        return self


class PublicEvidenceSpan(StrictModel):
    evidence_id: str = Field(min_length=1)
    speaker: Literal["user", "assistant", "tool"]
    message: Literal["user", "agent"]
    quote: str = Field(min_length=1)
    occurrence_index: int = Field(ge=0)
    start: int = Field(ge=0)
    end: int = Field(ge=0)


class PublicUntypedCandidate(StrictModel):
    statement: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    predicate: str = Field(min_length=1)
    object: str | None = None
    qualifiers: dict[str, Any]
    source_status: Literal["user_reported", "agent_generated", "tool_observed"]
    derivation: Literal["explicit", "context_completed", "inferred"]
    inference_basis: str | None = None
    projection_status: Literal["active", "corrected", "superseded", "active_conflict"]
    lifecycle_links: TypedLifecycleBinding
    operation_provenance: TypedOperationProvenance
    evidence: list[PublicEvidenceSpan] = Field(min_length=1)


class L1PublicCase(StrictModel):
    case_id: str = Field(pattern=r"^case-[0-9a-f]{16}$")
    candidate_ref: str = Field(pattern=r"^candidate-[0-9a-f]{16}$")
    source_turn: dict[Literal["user", "agent"], str]
    untyped_candidate: PublicUntypedCandidate


class L1PublicPayload(StrictModel):
    schema_version: Literal["typed-extractor-l1-public-v1"] = (
        "typed-extractor-l1-public-v1"
    )
    dataset_id: str = Field(min_length=1)
    case_count: int = Field(ge=1)
    allowed_vocabulary: dict[str, list[str]]
    cases: list[L1PublicCase] = Field(min_length=1)


class AutomaticWriteAuthorizations(StrictModel):
    l1: Literal[False] = False
    l2: Literal[False] = False
    unit_revision: Literal[False] = False
    closure: Literal[False] = False
    identity: Literal[False] = False
    membership: Literal[False] = False


class L1AuthorityCase(StrictModel):
    case_id: str = Field(pattern=r"^case-[0-9a-f]{16}$")
    candidate_ref: str = Field(pattern=r"^candidate-[0-9a-f]{16}$")
    knowledge_id: str = Field(min_length=1)
    candidate_id: str = Field(min_length=1)
    emission_allowed: bool
    required_evidence_bindings: list[TypedEvidenceBinding] = Field(min_length=1)
    allowed_modalities: list[TypedModality] = Field(default_factory=list)
    allowed_polarities: list[TypedPolarity] = Field(default_factory=list)
    allowed_event_times: list[str] = Field(default_factory=list)
    event_time_may_be_null: bool
    allowed_valid_times: list[str] = Field(default_factory=list)
    valid_time_may_be_null: bool
    allowed_condition_values: list[str] = Field(default_factory=list)
    allowed_scope_values: list[str] = Field(default_factory=list)
    required_derivation: TypedDerivationProvenance
    required_lifecycle: TypedLifecycleBinding
    required_operation_provenance: TypedOperationProvenance
    unresolved_required_fields: list[str] = Field(default_factory=list)
    automatic_write_authorizations: AutomaticWriteAuthorizations = Field(
        default_factory=AutomaticWriteAuthorizations
    )


class L1AuthorityPayload(StrictModel):
    schema_version: Literal["typed-extractor-l1-authority-v1"] = (
        "typed-extractor-l1-authority-v1"
    )
    dataset_id: str = Field(min_length=1)
    case_count: int = Field(ge=1)
    cases: list[L1AuthorityCase] = Field(min_length=1)


class L1GoldItem(StrictModel):
    case_id: str = Field(pattern=r"^case-[0-9a-f]{16}$")
    candidate_ref: str = Field(pattern=r"^candidate-[0-9a-f]{16}$")
    expected_decision: L1Decision
    expected_typed_candidate: TypedL1Candidate | None = None


class L1GoldPayload(StrictModel):
    schema_version: Literal["typed-extractor-l1-gold-v1"] = (
        "typed-extractor-l1-gold-v1"
    )
    dataset_id: str = Field(min_length=1)
    case_count: int = Field(ge=1)
    items: list[L1GoldItem] = Field(min_length=1)


class L1Manifest(StrictModel):
    schema_version: Literal["typed-extractor-l1-manifest-v1"] = (
        "typed-extractor-l1-manifest-v1"
    )
    dataset_id: str = Field(min_length=1)
    case_count: int = Field(ge=1)
    input_sha256: dict[str, str]
    output_sha256: dict[str, str]
    distribution: dict[str, Any]
    claim_boundary: dict[str, bool | str]


_ALLOWED_VOCABULARY = {
    "decisions": ["abstain", "emit_l1", "no_memory"],
    "kinds": ["attribute", "event", "preference", "state", "task"],
    "modalities": [
        "actual",
        "denied",
        "hypothetical",
        "planned",
        "recommended",
        "requested",
    ],
    "polarities": ["negative", "positive"],
    "speakers": ["assistant", "tool", "user"],
}


def _require_read_only(path: Path, label: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"{label} missing: {path}")
    if path.stat().st_mode & 0o222:
        raise ValueError(f"{label} must be read-only")


def _opaque_ref(prefix: str, value: str) -> str:
    digest = hashlib.sha256(f"typed-extractor-l1-v1:{value}".encode()).hexdigest()
    return f"{prefix}-{digest[:16]}"


def _speaker(message: str, evidence_role: str) -> str:
    mapping = {
        ("user", "user_reported"): "user",
        ("agent", "agent_generated"): "assistant",
        ("agent", "tool_observed"): "tool",
    }
    value = mapping.get((message, evidence_role))
    if value is None:
        raise ValueError("unsupported evidence speaker binding")
    return value


def _remap_lifecycle(value: TypedLifecycleBinding) -> TypedLifecycleBinding:
    return TypedLifecycleBinding(
        lifecycle=value.lifecycle,
        replacement_candidate_ref=(
            _opaque_ref("candidate", value.replacement_candidate_ref)
            if value.replacement_candidate_ref
            else None
        ),
        replaces_candidate_refs=[
            _opaque_ref("candidate", item) for item in value.replaces_candidate_refs
        ],
        supersedes_candidate_refs=[
            _opaque_ref("candidate", item) for item in value.supersedes_candidate_refs
        ],
        conflicts_with_candidate_refs=[
            _opaque_ref("candidate", item)
            for item in value.conflicts_with_candidate_refs
        ],
    )


def _remap_operations(value: TypedOperationProvenance) -> TypedOperationProvenance:
    return TypedOperationProvenance(
        confirmed_by_operation_refs=[
            _opaque_ref("operation", item)
            for item in value.confirmed_by_operation_refs
        ],
        added_by_operation_refs=[
            _opaque_ref("operation", item) for item in value.added_by_operation_refs
        ],
    )


def _remap_candidate(value: TypedL1Candidate) -> TypedL1Candidate:
    payload = value.model_dump(mode="json")
    payload["lifecycle"] = _remap_lifecycle(value.lifecycle).model_dump(mode="json")
    payload["operation_provenance"] = _remap_operations(
        value.operation_provenance
    ).model_dump(mode="json")
    return TypedL1Candidate.model_validate(payload)


def _record_lifecycle(record: Any) -> TypedLifecycleBinding:
    lifecycle = {
        "active": "active",
        "corrected": "superseded",
        "superseded": "superseded",
        "active_conflict": "conflicted",
    }.get(record.status)
    if lifecycle is None:
        raise ValueError("unsupported projection lifecycle")
    return TypedLifecycleBinding(
        lifecycle=lifecycle,
        replacement_candidate_ref=(
            _opaque_ref("candidate", record.replacement_id)
            if record.replacement_id
            else None
        ),
        replaces_candidate_refs=[
            _opaque_ref("candidate", item) for item in record.replaces
        ],
        supersedes_candidate_refs=[
            _opaque_ref("candidate", item) for item in record.supersedes
        ],
        conflicts_with_candidate_refs=[
            _opaque_ref("candidate", item) for item in record.conflicts_with
        ],
    )


def _record_operations(record: Any) -> TypedOperationProvenance:
    return TypedOperationProvenance(
        confirmed_by_operation_refs=[
            _opaque_ref("operation", item) for item in record.confirmed_by
        ],
        added_by_operation_refs=[
            _opaque_ref("operation", item) for item in record.added_by
        ],
    )


def _build_l1_dev_slice(
    *,
    source_config_path: Path,
    prompt_path: Path,
    bridge_ledger_path: Path,
    source_path: Path,
    turn_manifest_path: Path,
    dialogue_manifest_path: Path,
    final_knowledge_path: Path,
    run_path: Path,
    source_segments_path: Path,
) -> tuple[L1PublicPayload, L1AuthorityPayload, L1GoldPayload, dict[str, Any]]:
    for path, label in (
        (source_config_path, "source config"),
        (prompt_path, "proposer prompt"),
        (bridge_ledger_path, "bridge-v3 ledger"),
    ):
        _require_read_only(path, label)
    config = L1SourceConfig.model_validate(load_json(source_config_path))
    vocabulary_overlap = set(config.public_vocabulary) & set(_ALLOWED_VOCABULARY)
    if vocabulary_overlap:
        raise ValueError("public vocabulary cannot override base vocabulary")
    if len(config.cases) != 12:
        raise ValueError("L1 dev slice must contain exactly 12 cases")
    ledger = ExtractionCompatibilityLedger.model_validate(load_json(bridge_ledger_path))
    if ledger.schema_version != "automatic-extraction-compatibility-ledger-v3":
        raise ValueError("L1 dev slice requires bridge-v3")
    replay = replay_extraction_inputs(
        source_path=source_path,
        turn_manifest_path=turn_manifest_path,
        dialogue_manifest_path=dialogue_manifest_path,
        final_knowledge_path=final_knowledge_path,
        run_path=run_path,
        source_segments_path=source_segments_path,
    )
    records = replay.view.by_id
    envelopes = {item.knowledge_id: item for item in ledger.envelopes}
    public_cases: list[L1PublicCase] = []
    authority_cases: list[L1AuthorityCase] = []
    gold_items: list[L1GoldItem] = []
    kinds: set[str] = set()
    source_statuses: set[str] = set()
    projection_statuses: set[str] = set()
    non_explicit = condition_emit = scope_emit = operation_emit = 0
    resolved_time = unresolved_time = abstain = no_memory = 0

    for source_case in config.cases:
        record = records.get(source_case.knowledge_id)
        envelope = envelopes.get(source_case.knowledge_id)
        if record is None or envelope is None:
            raise ValueError(f"unknown bridge-v3 knowledge ID: {source_case.knowledge_id}")
        if envelope.candidate_level != "l1_single_turn_candidate":
            raise ValueError("L1 dev source must be a single-turn bridge candidate")
        evidence_turns = {int(item["turn_index"]) for item in record.knowledge["evidence"]}
        if len(evidence_turns) != 1:
            raise ValueError("L1 dev source evidence must stay within one turn")
        turn_index = next(iter(evidence_turns))
        source_turn = replay.source_turns[(record.candidate_id, turn_index)]
        case_id = _opaque_ref("case", source_case.knowledge_id)
        candidate_ref = _opaque_ref("candidate", source_case.knowledge_id)
        evidence_bindings = [
            TypedEvidenceBinding(
                evidence_id=str(item["evidence_id"]),
                speaker=_speaker(str(item["message"]), str(item["evidence_role"])),
            )
            for item in sorted(
                record.knowledge["evidence"], key=lambda item: str(item["evidence_id"])
            )
        ]
        derivation = TypedDerivationProvenance(
            method=record.knowledge["derivation"],
            basis=record.knowledge.get("inference_basis"),
            evidence_ids=[item.evidence_id for item in evidence_bindings],
        )
        lifecycle = _record_lifecycle(record)
        operations = _record_operations(record)
        expected = (
            _remap_candidate(source_case.expected_typed_candidate)
            if source_case.expected_typed_candidate
            else None
        )
        if expected is not None:
            if expected.evidence_bindings != evidence_bindings:
                raise ValueError("gold evidence bindings do not match bridge-v3")
            if expected.derivation != derivation:
                raise ValueError("gold derivation does not match bridge-v3")
            if expected.lifecycle != lifecycle:
                raise ValueError("gold lifecycle does not match bridge-v3")
            if expected.operation_provenance != operations:
                raise ValueError("gold operation provenance does not match bridge-v3")

        public_evidence = [
            PublicEvidenceSpan(
                evidence_id=str(item["evidence_id"]),
                speaker=_speaker(str(item["message"]), str(item["evidence_role"])),
                message=item["message"],
                quote=item["quote"],
                occurrence_index=item["occurrence_index"],
                start=item["start"],
                end=item["end"],
            )
            for item in sorted(
                record.knowledge["evidence"], key=lambda item: str(item["evidence_id"])
            )
        ]
        public_cases.append(
            L1PublicCase(
                case_id=case_id,
                candidate_ref=candidate_ref,
                source_turn={"user": source_turn.user, "agent": source_turn.agent},
                untyped_candidate=PublicUntypedCandidate(
                    statement=record.knowledge["statement"],
                    subject=record.knowledge["subject"],
                    predicate=record.knowledge["predicate"],
                    object=record.knowledge["object"],
                    qualifiers=record.knowledge["qualifiers"],
                    source_status=record.knowledge["source_status"],
                    derivation=record.knowledge["derivation"],
                    inference_basis=record.knowledge.get("inference_basis"),
                    projection_status=record.status,
                    lifecycle_links=lifecycle,
                    operation_provenance=operations,
                    evidence=public_evidence,
                ),
            )
        )
        qualifiers = record.knowledge["qualifiers"]
        authority_cases.append(
            L1AuthorityCase(
                case_id=case_id,
                candidate_ref=candidate_ref,
                knowledge_id=record.knowledge_id,
                candidate_id=record.candidate_id,
                emission_allowed=source_case.emission_allowed,
                required_evidence_bindings=evidence_bindings,
                allowed_modalities=source_case.allowed_modalities,
                allowed_polarities=[record.knowledge["qualifiers"]["polarity"]],
                allowed_event_times=source_case.allowed_event_times,
                event_time_may_be_null=source_case.event_time_may_be_null,
                allowed_valid_times=source_case.allowed_valid_times,
                valid_time_may_be_null=source_case.valid_time_may_be_null,
                allowed_condition_values=list(qualifiers.get("conditions", [])),
                allowed_scope_values=list(qualifiers.get("scope", [])),
                required_derivation=derivation,
                required_lifecycle=lifecycle,
                required_operation_provenance=operations,
                unresolved_required_fields=source_case.unresolved_required_fields,
            )
        )
        gold_items.append(
            L1GoldItem(
                case_id=case_id,
                candidate_ref=candidate_ref,
                expected_decision=source_case.expected_decision,
                expected_typed_candidate=expected,
            )
        )
        source_statuses.add(record.knowledge["source_status"])
        projection_statuses.add(record.status)
        if record.knowledge["derivation"] != "explicit":
            non_explicit += 1
        if expected:
            kinds.add(expected.kind)
            condition_emit += bool(expected.condition_bindings)
            scope_emit += bool(expected.scope_bindings)
            operation_emit += bool(
                expected.operation_provenance.confirmed_by_operation_refs
                or expected.operation_provenance.added_by_operation_refs
            )
            resolved_time += source_case.time_case == "resolved"
            unresolved_time += source_case.time_case == "unresolved"
        abstain += source_case.expected_decision == "abstain"
        no_memory += source_case.expected_decision == "no_memory"

    distribution = {
        "kind_coverage": sorted(kinds),
        "source_status_coverage": sorted(source_statuses),
        "projection_status_coverage": sorted(projection_statuses),
        "non_explicit_derivation_count": non_explicit,
        "condition_emit_count": condition_emit,
        "scope_emit_count": scope_emit,
        "operation_emit_count": operation_emit,
        "resolved_time_emit_count": resolved_time,
        "unresolved_time_emit_count": unresolved_time,
        "abstain_count": abstain,
        "no_memory_count": no_memory,
    }
    expected_distribution = {
        "kind_coverage": ["attribute", "event", "preference", "state", "task"],
        "source_status_coverage": [
            "agent_generated",
            "tool_observed",
            "user_reported",
        ],
        "projection_status_coverage": ["active", "corrected", "superseded"],
    }
    for key, expected_value in expected_distribution.items():
        if distribution[key] != expected_value:
            raise ValueError(f"L1 dev distribution mismatch: {key}")
    for key, minimum in {
        "non_explicit_derivation_count": 2,
        "condition_emit_count": 1,
        "scope_emit_count": 1,
        "operation_emit_count": 1,
        "resolved_time_emit_count": 1,
        "unresolved_time_emit_count": 1,
        "abstain_count": 2,
        "no_memory_count": 1,
    }.items():
        if distribution[key] < minimum:
            raise ValueError(f"L1 dev distribution is incomplete: {key}")

    public = L1PublicPayload(
        dataset_id=config.dataset_id,
        case_count=len(public_cases),
        allowed_vocabulary={
            **_ALLOWED_VOCABULARY,
            **config.public_vocabulary,
        },
        cases=public_cases,
    )
    authority = L1AuthorityPayload(
        dataset_id=config.dataset_id,
        case_count=len(authority_cases),
        cases=authority_cases,
    )
    gold = L1GoldPayload(
        dataset_id=config.dataset_id,
        case_count=len(gold_items),
        items=gold_items,
    )
    return public, authority, gold, distribution


def _input_sha256(
    *,
    source_config_path: Path,
    prompt_path: Path,
    bridge_ledger_path: Path,
    source_path: Path,
    turn_manifest_path: Path,
    dialogue_manifest_path: Path,
    final_knowledge_path: Path,
    run_path: Path,
    source_segments_path: Path,
) -> dict[str, str]:
    return {
        "bridge_ledger": sha256_file(bridge_ledger_path),
        "dialogue_manifest": sha256_file(dialogue_manifest_path),
        "final_knowledge": sha256_file(final_knowledge_path),
        "prompt": sha256_file(prompt_path),
        "run": sha256_file(run_path),
        "source": sha256_file(source_path),
        "source_config": sha256_file(source_config_path),
        "source_segments": sha256_file(source_segments_path),
        "turn_manifest": sha256_file(turn_manifest_path),
    }


def prepare_l1_dev_slice(
    *,
    source_config_path: Path,
    prompt_path: Path,
    bridge_ledger_path: Path,
    source_path: Path,
    turn_manifest_path: Path,
    dialogue_manifest_path: Path,
    final_knowledge_path: Path,
    run_path: Path,
    source_segments_path: Path,
    output_root: Path,
) -> dict[str, Any]:
    paths = {
        "source_config_path": source_config_path.resolve(),
        "prompt_path": prompt_path.resolve(),
        "bridge_ledger_path": bridge_ledger_path.resolve(),
        "source_path": source_path.resolve(),
        "turn_manifest_path": turn_manifest_path.resolve(),
        "dialogue_manifest_path": dialogue_manifest_path.resolve(),
        "final_knowledge_path": final_knowledge_path.resolve(),
        "run_path": run_path.resolve(),
        "source_segments_path": source_segments_path.resolve(),
    }
    public, authority, gold, distribution = _build_l1_dev_slice(**paths)
    output_root = output_root.resolve()
    outputs = {
        "public-l1.json": public,
        "authority-l1.json": authority,
        "gold-l1.json": gold,
    }
    for name, payload in outputs.items():
        write_json_immutable(output_root / name, payload)
    manifest = L1Manifest(
        dataset_id=public.dataset_id,
        case_count=public.case_count,
        input_sha256=_input_sha256(**paths),
        output_sha256={
            name: sha256_file(output_root / name) for name in sorted(outputs)
        },
        distribution=distribution,
        claim_boundary={
            "automatic_authoritative_writes": False,
            "embedding_authority": False,
            "fresh_hidden_created": False,
            "longmemeval_status": "structured_l2_identity_unresolved",
        },
    )
    write_json_immutable(output_root / "manifest-l1.json", manifest)
    for name in (*outputs, "manifest-l1.json"):
        (output_root / name).chmod(0o444)
    return {"status": "valid", "case_count": public.case_count, **distribution}


def validate_l1_dev_slice(
    *,
    source_config_path: Path,
    prompt_path: Path,
    bridge_ledger_path: Path,
    source_path: Path,
    turn_manifest_path: Path,
    dialogue_manifest_path: Path,
    final_knowledge_path: Path,
    run_path: Path,
    source_segments_path: Path,
    root: Path,
) -> dict[str, Any]:
    paths = {
        "source_config_path": source_config_path.resolve(),
        "prompt_path": prompt_path.resolve(),
        "bridge_ledger_path": bridge_ledger_path.resolve(),
        "source_path": source_path.resolve(),
        "turn_manifest_path": turn_manifest_path.resolve(),
        "dialogue_manifest_path": dialogue_manifest_path.resolve(),
        "final_knowledge_path": final_knowledge_path.resolve(),
        "run_path": run_path.resolve(),
        "source_segments_path": source_segments_path.resolve(),
    }
    public, authority, gold, distribution = _build_l1_dev_slice(**paths)
    root = root.resolve()
    expected_outputs = {
        "authority-l1.json": authority,
        "gold-l1.json": gold,
        "public-l1.json": public,
    }
    for name, expected in expected_outputs.items():
        path = root / name
        _require_read_only(path, name)
        if path.read_bytes() != canonical_json_bytes(expected):
            raise ValueError(f"typed L1 artifact drift: {name}")
    manifest_path = root / "manifest-l1.json"
    _require_read_only(manifest_path, "manifest-l1.json")
    actual = L1Manifest.model_validate(load_json(manifest_path))
    expected_manifest = L1Manifest(
        dataset_id=public.dataset_id,
        case_count=public.case_count,
        input_sha256=_input_sha256(**paths),
        output_sha256={
            name: sha256_file(root / name) for name in sorted(expected_outputs)
        },
        distribution=distribution,
        claim_boundary={
            "automatic_authoritative_writes": False,
            "embedding_authority": False,
            "fresh_hidden_created": False,
            "longmemeval_status": "structured_l2_identity_unresolved",
        },
    )
    if canonical_json_bytes(actual) != canonical_json_bytes(expected_manifest):
        raise ValueError("typed L1 manifest drift")
    return {"status": "valid", "case_count": public.case_count, **distribution}


class L1ScoredCase(StrictModel):
    case_id: str = Field(pattern=r"^case-[0-9a-f]{16}$")
    expected_decision: L1Decision
    raw_decision: L1Decision
    gated_decision: L1Decision
    raw_errors: list[str] = Field(default_factory=list)
    gate_reasons: list[str] = Field(default_factory=list)


class L1ScorePayload(StrictModel):
    schema_version: Literal["typed-extractor-l1-score-v1"] = (
        "typed-extractor-l1-score-v1"
    )
    status: Literal["pass"] = "pass"
    dataset_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    case_count: int = Field(ge=1)
    raw_proposer_quality_ready: bool
    deterministic_gate_safety_ready: bool
    metrics: dict[str, Any]
    cases: list[L1ScoredCase] = Field(min_length=1)
    error_taxonomy: dict[str, int]
    gate_reason_counts: dict[str, int]
    guard_state: dict[str, Any]
    claim_boundary: dict[str, Any]


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 1.0


def _f1(*, true_positive: int, false_positive: int, false_negative: int) -> tuple[float, float, float]:
    precision = _ratio(true_positive, true_positive + false_positive)
    recall = _ratio(true_positive, true_positive + false_negative)
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0
    )
    return precision, recall, f1


def _guard_counts(bundle: MemoryRepresentationBundleV3) -> dict[str, int]:
    return {
        "closure_evaluation_count": len(bundle.closure_evaluations),
        "closure_spec_count": len(bundle.closure_specs),
        "l1_unit_count": len(bundle.l1_units),
        "l2_unit_count": len(bundle.l2_units),
        "query_plan_count": len(bundle.query_plans),
        "raw_artifact_revision_count": len(bundle.raw_artifact_revisions),
        "source_record_revision_count": len(bundle.source_record_revisions),
        "unit_revision_count": len(bundle.unit_revisions),
    }


def _gate_proposal(
    proposal: L1ProposalRecord,
    authority: L1AuthorityCase,
) -> tuple[L1Decision, list[str]]:
    if proposal.decision != "emit_l1":
        return proposal.decision, []
    typed = proposal.typed_candidate
    if typed is None:
        raise ValueError("emit_l1 proposal has no typed candidate")
    reasons: list[str] = []
    if not authority.emission_allowed:
        reasons.append("emission_not_authorized")
    if typed.evidence_bindings != authority.required_evidence_bindings:
        reasons.append("evidence_binding_not_authorized")
    if typed.modality not in authority.allowed_modalities:
        reasons.append("modality_not_authorized")
    if typed.polarity not in authority.allowed_polarities:
        reasons.append("polarity_not_authorized")
    if typed.time.event_time is None:
        if not authority.event_time_may_be_null:
            reasons.append("event_time_required")
    elif typed.time.event_time not in authority.allowed_event_times:
        reasons.append("event_time_not_authorized")
    if typed.time.valid_time is None:
        if not authority.valid_time_may_be_null:
            reasons.append("valid_time_required")
    elif typed.time.valid_time not in authority.allowed_valid_times:
        reasons.append("valid_time_not_authorized")
    if not {item.value for item in typed.condition_bindings}.issubset(
        set(authority.allowed_condition_values)
    ):
        reasons.append("condition_not_authorized")
    if not {item.value for item in typed.scope_bindings}.issubset(
        set(authority.allowed_scope_values)
    ):
        reasons.append("scope_not_authorized")
    if typed.derivation != authority.required_derivation:
        reasons.append("derivation_not_authorized")
    if typed.lifecycle != authority.required_lifecycle:
        reasons.append("lifecycle_not_authorized")
    if typed.operation_provenance != authority.required_operation_provenance:
        reasons.append("operation_provenance_not_authorized")
    return ("abstain", sorted(reasons)) if reasons else ("emit_l1", [])


def _raw_errors(
    proposal: L1ProposalRecord,
    gold: L1GoldItem,
) -> list[str]:
    errors: set[str] = set()
    if proposal.decision != gold.expected_decision:
        if proposal.decision == "emit_l1" and gold.expected_decision != "emit_l1":
            errors.add("false_emission")
        elif proposal.decision != "emit_l1" and gold.expected_decision == "emit_l1":
            errors.add("false_abstention")
        else:
            errors.add("decision_error")
    expected = gold.expected_typed_candidate
    actual = proposal.typed_candidate
    if expected is None:
        return sorted(errors)
    if actual is None:
        errors.update(
            {
                "condition_or_scope_error",
                "derivation_or_speaker_error",
                "evidence_error",
                "kind_error",
                "lifecycle_error",
                "modality_or_polarity_error",
                "operation_provenance_error",
                "predicate_or_operator_error",
                "role_or_local_entity_error",
                "time_error",
            }
        )
        return sorted(errors)
    if actual.evidence_bindings != expected.evidence_bindings:
        errors.add("evidence_error")
    if actual.kind != expected.kind:
        errors.add("kind_error")
    if actual.predicate != expected.predicate:
        errors.add("predicate_or_operator_error")
    if actual.local_entities != expected.local_entities or actual.roles != expected.roles:
        errors.add("role_or_local_entity_error")
    if actual.modality != expected.modality or actual.polarity != expected.polarity:
        errors.add("modality_or_polarity_error")
    if actual.time != expected.time:
        errors.add("time_error")
    if actual.lifecycle != expected.lifecycle:
        errors.add("lifecycle_error")
    if (
        actual.condition_bindings != expected.condition_bindings
        or actual.scope_bindings != expected.scope_bindings
    ):
        errors.add("condition_or_scope_error")
    if (
        actual.derivation != expected.derivation
        or actual.evidence_bindings != expected.evidence_bindings
    ):
        errors.add("derivation_or_speaker_error")
    if actual.operation_provenance != expected.operation_provenance:
        errors.add("operation_provenance_error")
    return sorted(errors)


def _require_scoring_inputs(root: Path, proposals_path: Path, provenance_path: Path) -> None:
    for path, label in (
        (root / "public-l1.json", "public-l1.json"),
        (root / "authority-l1.json", "authority-l1.json"),
        (root / "gold-l1.json", "gold-l1.json"),
        (root / "manifest-l1.json", "manifest-l1.json"),
        (proposals_path, "proposals"),
        (provenance_path, "provenance"),
    ):
        _require_read_only(path, label)


def score_l1_proposals(
    root: Path,
    proposals_path: Path,
    provenance_path: Path,
    *,
    guard_bundle: MemoryRepresentationBundleV3,
) -> L1ScorePayload:
    from .typed_extractor_model_run import (
        L1ModelDispatch,
        L1ModelProvenance,
        extract_l1_proposal_payload,
    )

    root = root.resolve()
    proposals_path = proposals_path.resolve()
    provenance_path = provenance_path.resolve()
    _require_scoring_inputs(root, proposals_path, provenance_path)
    public = L1PublicPayload.model_validate(load_json(root / "public-l1.json"))
    authority = L1AuthorityPayload.model_validate(load_json(root / "authority-l1.json"))
    gold = L1GoldPayload.model_validate(load_json(root / "gold-l1.json"))
    manifest = L1Manifest.model_validate(load_json(root / "manifest-l1.json"))
    proposals = L1ProposalPayload.model_validate(load_json(proposals_path))
    provenance = L1ModelProvenance.model_validate(load_json(provenance_path))
    dispatch_path = provenance_path.parent / provenance.dispatch_filename
    raw_response_path = provenance_path.parent / provenance.raw_response_filename
    _require_read_only(dispatch_path, "dispatch")
    _require_read_only(raw_response_path, "raw response")
    dispatch = L1ModelDispatch.model_validate(load_json(dispatch_path))
    if provenance.dispatch_sha256 != sha256_file(dispatch_path):
        raise ValueError("provenance does not bind frozen dispatch")
    if provenance.raw_response_sha256 != sha256_file(raw_response_path):
        raise ValueError("provenance does not bind frozen raw response")
    if provenance.proposals_sha256 != sha256_file(proposals_path):
        raise ValueError("provenance does not bind frozen proposals")
    if (
        dispatch.dataset_id != provenance.dataset_id
        or dispatch.run_id != provenance.run_id
        or dispatch.proposer_id != provenance.proposer_id
        or dispatch.proposer_version != provenance.proposer_version
        or dispatch.requested_model != provenance.requested_model
        or dispatch.allowed_files != provenance.allowed_files
        or dispatch.allowed_input_sha256 != provenance.allowed_input_sha256
    ):
        raise ValueError("provenance metadata does not match frozen dispatch")
    response_payload = load_json(raw_response_path)
    if response_payload.get("model") != provenance.response_model:
        raise ValueError("provenance response model does not match raw response")
    if extract_l1_proposal_payload(response_payload) != proposals:
        raise ValueError("frozen proposals do not match raw response")
    if provenance.allowed_input_sha256.get("public-l1.json") != sha256_file(
        root / "public-l1.json"
    ):
        raise ValueError("provenance does not bind public input")
    if proposals.dataset_id != public.dataset_id or provenance.dataset_id != public.dataset_id:
        raise ValueError("scoring dataset mismatch")
    if proposals.run_id != provenance.run_id:
        raise ValueError("scoring run metadata mismatch")
    if manifest.output_sha256 != {
        name: sha256_file(root / name)
        for name in ("authority-l1.json", "gold-l1.json", "public-l1.json")
    }:
        raise ValueError("manifest does not bind scoring inputs")
    public_by_id = {item.case_id: item for item in public.cases}
    authority_by_id = {item.case_id: item for item in authority.cases}
    gold_by_id = {item.case_id: item for item in gold.items}
    proposal_by_id = {item.case_id: item for item in proposals.proposals}
    case_ids = set(public_by_id)
    if not (
        case_ids
        == set(authority_by_id)
        == set(gold_by_id)
        == set(proposal_by_id)
    ):
        raise ValueError("scoring case coverage mismatch")
    for case_id in case_ids:
        candidate_ref = public_by_id[case_id].candidate_ref
        if (
            authority_by_id[case_id].candidate_ref != candidate_ref
            or gold_by_id[case_id].candidate_ref != candidate_ref
            or proposal_by_id[case_id].candidate_ref != candidate_ref
        ):
            raise ValueError("scoring candidate ref mismatch")

    before_fingerprint = canonical_sha256(guard_bundle)
    before_counts = _guard_counts(guard_bundle)
    cases: list[L1ScoredCase] = []
    gated_decisions: dict[str, L1Decision] = {}
    taxonomy: dict[str, int] = {}
    gate_counts: dict[str, int] = {}
    for case_id in sorted(case_ids):
        proposal = proposal_by_id[case_id]
        expected = gold_by_id[case_id]
        gated_decision, gate_reasons = _gate_proposal(
            proposal,
            authority_by_id[case_id],
        )
        raw_errors = _raw_errors(proposal, expected)
        for error in raw_errors:
            taxonomy[error] = taxonomy.get(error, 0) + 1
        for reason in gate_reasons:
            gate_counts[reason] = gate_counts.get(reason, 0) + 1
        gated_decisions[case_id] = gated_decision
        cases.append(
            L1ScoredCase(
                case_id=case_id,
                expected_decision=expected.expected_decision,
                raw_decision=proposal.decision,
                gated_decision=gated_decision,
                raw_errors=raw_errors,
                gate_reasons=gate_reasons,
            )
        )

    total = len(case_ids)
    expected_emit_ids = {
        case_id
        for case_id, item in gold_by_id.items()
        if item.expected_decision == "emit_l1"
    }
    raw_correct = sum(
        proposal_by_id[case_id].decision == gold_by_id[case_id].expected_decision
        for case_id in case_ids
    )
    gated_correct = sum(
        gated_decisions[case_id] == gold_by_id[case_id].expected_decision
        for case_id in case_ids
    )
    raw_false_emissions = sum(
        proposal_by_id[case_id].decision == "emit_l1"
        and gold_by_id[case_id].expected_decision != "emit_l1"
        for case_id in case_ids
    )
    gated_false_materializations = sum(
        gated_decisions[case_id] == "emit_l1"
        and gold_by_id[case_id].expected_decision != "emit_l1"
        for case_id in case_ids
    )
    abstain_tp = sum(
        proposal_by_id[case_id].decision == "abstain"
        and gold_by_id[case_id].expected_decision == "abstain"
        for case_id in case_ids
    )
    abstain_fp = sum(
        proposal_by_id[case_id].decision == "abstain"
        and gold_by_id[case_id].expected_decision != "abstain"
        for case_id in case_ids
    )
    abstain_fn = sum(
        proposal_by_id[case_id].decision != "abstain"
        and gold_by_id[case_id].expected_decision == "abstain"
        for case_id in case_ids
    )
    abstain_precision, abstain_recall, abstain_f1 = _f1(
        true_positive=abstain_tp,
        false_positive=abstain_fp,
        false_negative=abstain_fn,
    )

    def field_rate(check: Any) -> float:
        correct = 0
        for case_id in expected_emit_ids:
            actual = proposal_by_id[case_id].typed_candidate
            expected = gold_by_id[case_id].expected_typed_candidate
            correct += actual is not None and expected is not None and check(actual, expected)
        return _ratio(correct, len(expected_emit_ids))

    metrics = {
        "proposal_coverage": 1.0,
        "schema_valid_rate": 1.0,
        "raw_decision_accuracy": _ratio(raw_correct, total),
        "gated_decision_accuracy": _ratio(gated_correct, total),
        "raw_abstention_precision": abstain_precision,
        "raw_abstention_recall": abstain_recall,
        "raw_abstention_f1": abstain_f1,
        "raw_critical_false_emission_count": raw_false_emissions,
        "deterministic_critical_false_materialization_count": gated_false_materializations,
        "exact_evidence_rate": field_rate(
            lambda actual, expected: actual.evidence_bindings == expected.evidence_bindings
        ),
        "kind_accuracy": field_rate(lambda actual, expected: actual.kind == expected.kind),
        "predicate_or_operator_accuracy": field_rate(
            lambda actual, expected: actual.predicate == expected.predicate
        ),
        "role_or_local_entity_accuracy": field_rate(
            lambda actual, expected: actual.local_entities == expected.local_entities
            and actual.roles == expected.roles
        ),
        "modality_or_polarity_accuracy": field_rate(
            lambda actual, expected: actual.modality == expected.modality
            and actual.polarity == expected.polarity
        ),
        "time_accuracy": field_rate(lambda actual, expected: actual.time == expected.time),
        "lifecycle_accuracy": field_rate(
            lambda actual, expected: actual.lifecycle == expected.lifecycle
        ),
        "condition_or_scope_accuracy": field_rate(
            lambda actual, expected: actual.condition_bindings == expected.condition_bindings
            and actual.scope_bindings == expected.scope_bindings
        ),
        "derivation_or_speaker_accuracy": field_rate(
            lambda actual, expected: actual.derivation == expected.derivation
            and actual.evidence_bindings == expected.evidence_bindings
        ),
        "operation_provenance_accuracy": field_rate(
            lambda actual, expected: actual.operation_provenance
            == expected.operation_provenance
        ),
        "gate_intervention_count": sum(bool(item.gate_reasons) for item in cases),
    }
    field_metrics = [
        "kind_accuracy",
        "predicate_or_operator_accuracy",
        "role_or_local_entity_accuracy",
        "modality_or_polarity_accuracy",
        "time_accuracy",
        "lifecycle_accuracy",
        "condition_or_scope_accuracy",
        "derivation_or_speaker_accuracy",
        "operation_provenance_accuracy",
    ]
    raw_ready = (
        metrics["proposal_coverage"] == 1.0
        and metrics["schema_valid_rate"] == 1.0
        and metrics["exact_evidence_rate"] == 1.0
        and raw_false_emissions == 0
        and metrics["raw_decision_accuracy"] >= 0.90
        and metrics["raw_abstention_f1"] >= 0.80
        and all(metrics[name] >= 0.85 for name in field_metrics)
    )
    after_fingerprint = canonical_sha256(guard_bundle)
    after_counts = _guard_counts(guard_bundle)
    guard_state = {
        "before_fingerprint": before_fingerprint,
        "after_fingerprint": after_fingerprint,
        "before_counts": before_counts,
        "after_counts": after_counts,
        "unchanged": before_fingerprint == after_fingerprint
        and before_counts == after_counts,
    }
    claim_boundary = {
        "automatic_l1_write_count": 0,
        "automatic_l2_write_count": 0,
        "automatic_unit_revision_write_count": 0,
        "automatic_closure_write_count": 0,
        "automatic_identity_write_count": 0,
        "automatic_membership_write_count": 0,
        "embedding_authority": False,
        "fresh_hidden_created": False,
        "longmemeval_status": "structured_l2_identity_unresolved",
    }
    gate_ready = (
        gated_false_materializations == 0
        and guard_state["unchanged"]
        and all(
            value == 0
            for key, value in claim_boundary.items()
            if key.startswith("automatic_") and key.endswith("_count")
        )
    )
    return L1ScorePayload(
        dataset_id=public.dataset_id,
        run_id=proposals.run_id,
        case_count=total,
        raw_proposer_quality_ready=raw_ready,
        deterministic_gate_safety_ready=gate_ready,
        metrics=metrics,
        cases=cases,
        error_taxonomy=dict(sorted(taxonomy.items())),
        gate_reason_counts=dict(sorted(gate_counts.items())),
        guard_state=guard_state,
        claim_boundary=claim_boundary,
    )


def render_l1_score_report(score: L1ScorePayload) -> str:
    metrics = score.metrics
    return "\n".join(
        [
            "# Typed Extractor V2 L1 Dev Qualification",
            "",
            f"- Run ID: `{score.run_id}`",
            f"- Cases: `{score.case_count}`",
            "",
            "## Raw proposer quality",
            "",
            f"- Ready: `{str(score.raw_proposer_quality_ready).lower()}`",
            f"- Decision accuracy: `{metrics['raw_decision_accuracy']}`",
            f"- Abstention F1: `{metrics['raw_abstention_f1']}`",
            f"- Critical false emissions: `{metrics['raw_critical_false_emission_count']}`",
            f"- Exact evidence rate: `{metrics['exact_evidence_rate']}`",
            f"- Error taxonomy: `{score.error_taxonomy}`",
            "",
            "## Deterministic gate safety",
            "",
            f"- Ready: `{str(score.deterministic_gate_safety_ready).lower()}`",
            f"- Gated decision accuracy: `{metrics['gated_decision_accuracy']}`",
            f"- Critical false materializations: `{metrics['deterministic_critical_false_materialization_count']}`",
            f"- Gate interventions: `{metrics['gate_intervention_count']}`",
            f"- Gate reasons: `{score.gate_reason_counts}`",
            f"- Guard unchanged: `{str(score.guard_state['unchanged']).lower()}`",
            "",
            "## Boundaries",
            "",
            "The deterministic gate only preserves a proposal or reduces it to abstention. It does not correct semantic fields, and its safety result does not replace raw proposer quality.",
            "",
            "No authoritative L1, L2, unit revision, closure, identity, or membership write is authorized. Embeddings are not authority. `LONGMEMEVAL-6d550036` remains `structured_l2_identity_unresolved`.",
            "",
        ]
    )


def run_l1_scoring_file(
    root: Path,
    proposals_path: Path,
    provenance_path: Path,
    *,
    guard_root: Path,
    guard_slice_id: str,
    guard_results_path: Path,
    score_path: Path,
    report_path: Path,
    error_analysis_path: Path,
) -> dict[str, Any]:
    guard_bundle = build_authoritative_conformance_bundle(
        guard_root,
        guard_slice_id,
        guard_results_path,
    )
    score = score_l1_proposals(
        root,
        proposals_path,
        provenance_path,
        guard_bundle=guard_bundle,
    )
    score_path = score_path.resolve()
    report_path = report_path.resolve()
    error_analysis_path = error_analysis_path.resolve()
    write_json_immutable(score_path, score)
    write_text_immutable(report_path, render_l1_score_report(score))
    write_json_immutable(
        error_analysis_path,
        {
            "schema_version": "typed-extractor-l1-error-analysis-v1",
            "dataset_id": score.dataset_id,
            "run_id": score.run_id,
            "error_taxonomy": score.error_taxonomy,
            "gate_reason_counts": score.gate_reason_counts,
            "cases": [
                item.model_dump(mode="json")
                for item in score.cases
                if item.raw_errors or item.gate_reasons
            ],
        },
    )
    for path in (score_path, report_path, error_analysis_path):
        path.chmod(0o444)
    return score.model_dump(mode="json")
