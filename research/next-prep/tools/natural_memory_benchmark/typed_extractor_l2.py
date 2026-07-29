from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .typed_extractor_l1 import (
    AutomaticWriteAuthorizations,
    PublicEvidenceSpan,
    PublicUntypedCandidate,
    TypedEvidenceBinding,
    TypedLocalEntity,
    TypedModality,
    TypedPolarity,
    TypedPredicate,
    TypedRoleBinding,
    TypedTimeBinding,
)
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


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


L2Decision = Literal["emit_l2", "abstain"]
L2Kind = Literal[
    "task",
    "preference_profile",
    "project",
    "habit",
    "long_running_state",
    "summary_event",
]
L2AbstractionMethod = Literal[
    "coreference_resolution",
    "task_composition",
    "preference_aggregation",
    "lifecycle_resolution",
    "state_summary",
]
ClosurePattern = Literal[
    "single_fact",
    "multi_evidence_set",
    "temporal_chain",
    "update_supersession",
    "causal_answerability",
]

L2_DEV_THRESHOLDS: dict[str, float | int] = {
    "proposal_coverage": 1.0,
    "schema_valid_rate": 1.0,
    "raw_decision_accuracy": 0.9,
    "raw_abstention_f1": 0.8,
    "exact_evidence_rate": 1.0,
    "support_id_accuracy": 1.0,
    "source_coverage_accuracy": 1.0,
    "safety_field_accuracy": 0.85,
    "raw_critical_false_emission_count": 0,
    "deterministic_critical_false_materialization_count": 0,
}

L1_QUALIFICATION_ARTIFACTS = (
    "error-analysis.json",
    "proposals.json",
    "provenance.json",
    "report.md",
    "score.json",
)


class L1QualificationSelection(StrictModel):
    schema_version: Literal["typed-extractor-l1-qualification-selection-v1"] = (
        "typed-extractor-l1-qualification-selection-v1"
    )
    status: Literal["frozen"] = "frozen"
    purpose: Literal["typed-extractor-l2-dev-source-binding"] = (
        "typed-extractor-l2-dev-source-binding"
    )
    run_id: str = Field(min_length=1)
    artifact_sha256: dict[str, str]

    @model_validator(mode="after")
    def validate_artifact_hashes(self) -> "L1QualificationSelection":
        if set(self.artifact_sha256) != set(L1_QUALIFICATION_ARTIFACTS):
            raise ValueError("L1 qualification selection artifact set mismatch")
        if any(
            len(value) != 64
            or any(char not in "0123456789abcdef" for char in value)
            for value in self.artifact_sha256.values()
        ):
            raise ValueError("invalid L1 qualification selection hash")
        return self


class TypedL1SupportCandidate(StrictModel):
    support_ref: str = Field(pattern=r"^support-[0-9a-f]{16}$")
    source_turn_ref: str = Field(pattern=r"^turn-[0-9a-f]{16}$")
    source_session_ref: str = Field(pattern=r"^session-[0-9a-f]{16}$")
    kind: Literal["event", "state", "preference", "task", "attribute"]
    predicate: TypedPredicate
    local_entities: list[TypedLocalEntity] = Field(min_length=1)
    roles: list[TypedRoleBinding] = Field(min_length=1)
    modality: TypedModality
    polarity: TypedPolarity
    time: TypedTimeBinding
    evidence_bindings: list[TypedEvidenceBinding] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_reference_closure(self) -> "TypedL1SupportCandidate":
        local_ids = [item.local_entity_id for item in self.local_entities]
        expected = [f"entity-{index:02d}" for index in range(1, len(local_ids) + 1)]
        if local_ids != expected:
            raise ValueError("local entity IDs must be contiguous and ordered")
        if not {item.local_entity_id for item in self.roles}.issubset(set(local_ids)):
            raise ValueError("support role references unknown local entity")
        evidence = [(item.evidence_id, item.speaker) for item in self.evidence_bindings]
        if len(evidence) != len(set(evidence)):
            raise ValueError("duplicate support evidence binding")
        return self


class TypedL2StructuredClaim(StrictModel):
    claim_ref: str = Field(pattern=r"^claim-[0-9]{2}$")
    predicate: TypedPredicate
    local_entities: list[TypedLocalEntity] = Field(min_length=1)
    roles: list[TypedRoleBinding] = Field(min_length=1)
    modality: TypedModality
    polarity: TypedPolarity
    time: TypedTimeBinding
    supporting_l1_refs: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_reference_closure(self) -> "TypedL2StructuredClaim":
        local_ids = [item.local_entity_id for item in self.local_entities]
        expected = [f"entity-{index:02d}" for index in range(1, len(local_ids) + 1)]
        if local_ids != expected:
            raise ValueError("local entity IDs must be contiguous and ordered")
        if not {item.local_entity_id for item in self.roles}.issubset(set(local_ids)):
            raise ValueError("claim role references unknown local entity")
        theme_ids = {
            item.local_entity_id for item in self.roles if item.role == "theme"
        }
        target_ids = {
            item.local_entity_id for item in self.roles if item.role == "target_format"
        }
        if theme_ids & target_ids:
            raise ValueError("theme and target format require distinct local entities")
        if len(self.supporting_l1_refs) != len(set(self.supporting_l1_refs)):
            raise ValueError("duplicate claim support ref")
        return self


class TypedL2Abstraction(StrictModel):
    method: L2AbstractionMethod
    basis: str = Field(min_length=1)


class TypedL2Closure(StrictModel):
    pattern: ClosurePattern
    required_support_refs: list[str] = Field(min_length=1)
    optional_support_refs: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_refs(self) -> "TypedL2Closure":
        all_refs = [*self.required_support_refs, *self.optional_support_refs]
        if len(all_refs) != len(set(all_refs)):
            raise ValueError("duplicate closure support ref")
        return self


class TypedL2Candidate(StrictModel):
    kind: L2Kind
    summary: str = Field(min_length=1)
    supporting_l1_refs: list[str] = Field(min_length=1)
    structured_claims: list[TypedL2StructuredClaim] = Field(min_length=1)
    abstraction: TypedL2Abstraction
    closure: TypedL2Closure
    source_turn_refs: list[str] = Field(min_length=1)
    source_session_refs: list[str] = Field(min_length=1)
    evidence_bindings: list[TypedEvidenceBinding] = Field(min_length=1)
    lifecycle: Literal["candidate"] = "candidate"

    @model_validator(mode="after")
    def validate_provenance_closure(self) -> "TypedL2Candidate":
        claim_refs = [item.claim_ref for item in self.structured_claims]
        expected_claim_refs = [
            f"claim-{index:02d}" for index in range(1, len(claim_refs) + 1)
        ]
        if claim_refs != expected_claim_refs:
            raise ValueError("claim refs must be contiguous, unique, and ordered")
        support_refs = self.supporting_l1_refs
        if len(support_refs) != len(set(support_refs)):
            raise ValueError("duplicate L1 support ref")
        support_set = set(support_refs)
        claim_support_refs: set[str] = set()
        for claim in self.structured_claims:
            if not set(claim.supporting_l1_refs).issubset(support_set):
                raise ValueError("structured claim references unknown support")
            claim_support_refs.update(claim.supporting_l1_refs)
        closure_refs = {
            *self.closure.required_support_refs,
            *self.closure.optional_support_refs,
        }
        if not closure_refs.issubset(support_set):
            raise ValueError("closure references unknown support")
        if not set().union(
            *(set(claim.supporting_l1_refs) for claim in self.structured_claims)
        ).issubset(set(self.closure.required_support_refs)):
            raise ValueError("claim support is missing from required closure")
        if (
            claim_support_refs != support_set
            or set(self.closure.required_support_refs) != support_set
        ):
            raise ValueError("every L1 support must be used by a claim and required closure")
        return self


class L2ProposalRecord(StrictModel):
    case_id: str = Field(pattern=r"^case-[0-9a-f]{16}$")
    candidate_ref: str = Field(pattern=r"^candidate-[0-9a-f]{16}$")
    decision: L2Decision
    confidence: float = Field(ge=0.0, le=1.0)
    typed_candidate: TypedL2Candidate | None = None
    reason_code: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_decision_union(self) -> "L2ProposalRecord":
        if self.decision == "emit_l2" and self.typed_candidate is None:
            raise ValueError("emit_l2 requires typed candidate")
        if self.decision != "emit_l2" and self.typed_candidate is not None:
            raise ValueError("non-emission decision must not include typed candidate")
        return self


class L2ProposalPayload(StrictModel):
    schema_version: Literal["typed-extractor-l2-proposals-v1"] = (
        "typed-extractor-l2-proposals-v1"
    )
    dataset_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    proposer_id: str = Field(min_length=1)
    proposer_version: str = Field(min_length=1)
    case_count: int = Field(ge=1)
    proposals: list[L2ProposalRecord] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_cases(self) -> "L2ProposalPayload":
        case_ids = [item.case_id for item in self.proposals]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("duplicate proposal case")
        if self.case_count != len(self.proposals):
            raise ValueError("proposal case count mismatch")
        return self


class L2SourceCase(StrictModel):
    private_case_id: str = Field(min_length=1)
    knowledge_id: str = Field(min_length=1)
    expected_decision: L2Decision
    typed_l1_support_pack: list[TypedL1SupportCandidate] = Field(min_length=2)
    expected_typed_candidate: TypedL2Candidate | None = None
    emission_allowed: bool
    allowed_abstraction_methods: list[L2AbstractionMethod] = Field(default_factory=list)
    allowed_closure_patterns: list[ClosurePattern] = Field(default_factory=list)
    unresolved_required_fields: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_expected_union(self) -> "L2SourceCase":
        if self.expected_decision == "emit_l2" and self.expected_typed_candidate is None:
            raise ValueError("emitting source case requires an expected typed candidate")
        if self.expected_decision != "emit_l2" and self.expected_typed_candidate is not None:
            raise ValueError("abstaining source case cannot include an expected typed candidate")
        if self.emission_allowed != (self.expected_decision == "emit_l2"):
            raise ValueError("emission authority must match the expected decision")
        if self.emission_allowed and (
            not self.allowed_abstraction_methods or not self.allowed_closure_patterns
        ):
            raise ValueError("emitting source case requires abstraction and closure authority")
        if not self.emission_allowed and not self.unresolved_required_fields:
            raise ValueError("abstaining source case requires unresolved fields")
        return self


class L2SourceConfig(StrictModel):
    schema_version: Literal["typed-extractor-l2-source-v1"] = (
        "typed-extractor-l2-source-v1"
    )
    dataset_id: str = Field(min_length=1)
    public_vocabulary: dict[str, list[str]] = Field(default_factory=dict)
    cases: list[L2SourceCase] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_cases(self) -> "L2SourceConfig":
        private_ids = [item.private_case_id for item in self.cases]
        knowledge_ids = [item.knowledge_id for item in self.cases]
        if len(private_ids) != len(set(private_ids)):
            raise ValueError("duplicate private case ID")
        if len(knowledge_ids) != len(set(knowledge_ids)):
            raise ValueError("duplicate source knowledge ID")
        for key, values in self.public_vocabulary.items():
            if not key or not values or len(values) != len(set(values)):
                raise ValueError("public vocabulary entries must be non-empty and unique")
        return self


class L2PublicTurn(StrictModel):
    source_turn_ref: str = Field(pattern=r"^turn-[0-9a-f]{16}$")
    turn_index: int = Field(ge=0)
    user: str
    agent: str


class L2PublicCase(StrictModel):
    case_id: str = Field(pattern=r"^case-[0-9a-f]{16}$")
    candidate_ref: str = Field(pattern=r"^candidate-[0-9a-f]{16}$")
    source_session_ref: str = Field(pattern=r"^session-[0-9a-f]{16}$")
    source_turns: list[L2PublicTurn] = Field(min_length=2)
    untyped_candidate: PublicUntypedCandidate
    typed_l1_support_pack: list[TypedL1SupportCandidate] = Field(min_length=2)


class L2PublicPayload(StrictModel):
    schema_version: Literal["typed-extractor-l2-public-v1"] = (
        "typed-extractor-l2-public-v1"
    )
    dataset_id: str = Field(min_length=1)
    case_count: int = Field(ge=1)
    allowed_vocabulary: dict[str, list[str]]
    cases: list[L2PublicCase] = Field(min_length=1)


class L2AuthorityCase(StrictModel):
    case_id: str = Field(pattern=r"^case-[0-9a-f]{16}$")
    candidate_ref: str = Field(pattern=r"^candidate-[0-9a-f]{16}$")
    knowledge_id: str = Field(min_length=1)
    candidate_id: str = Field(min_length=1)
    emission_allowed: bool
    required_support_refs: list[str] = Field(min_length=2)
    required_evidence_bindings: list[TypedEvidenceBinding] = Field(min_length=1)
    required_source_turn_refs: list[str] = Field(min_length=2)
    required_source_session_refs: list[str] = Field(min_length=1)
    allowed_abstraction_methods: list[L2AbstractionMethod] = Field(default_factory=list)
    allowed_closure_patterns: list[ClosurePattern] = Field(default_factory=list)
    unresolved_required_fields: list[str] = Field(default_factory=list)
    automatic_write_authorizations: AutomaticWriteAuthorizations = Field(
        default_factory=AutomaticWriteAuthorizations
    )


class L2AuthorityPayload(StrictModel):
    schema_version: Literal["typed-extractor-l2-authority-v1"] = (
        "typed-extractor-l2-authority-v1"
    )
    dataset_id: str = Field(min_length=1)
    case_count: int = Field(ge=1)
    cases: list[L2AuthorityCase] = Field(min_length=1)


class L2GoldItem(StrictModel):
    case_id: str = Field(pattern=r"^case-[0-9a-f]{16}$")
    candidate_ref: str = Field(pattern=r"^candidate-[0-9a-f]{16}$")
    expected_decision: L2Decision
    expected_typed_candidate: TypedL2Candidate | None = None


class L2GoldPayload(StrictModel):
    schema_version: Literal["typed-extractor-l2-gold-v1"] = (
        "typed-extractor-l2-gold-v1"
    )
    dataset_id: str = Field(min_length=1)
    case_count: int = Field(ge=1)
    items: list[L2GoldItem] = Field(min_length=1)


class L2Manifest(StrictModel):
    schema_version: Literal["typed-extractor-l2-manifest-v1"] = (
        "typed-extractor-l2-manifest-v1"
    )
    dataset_id: str = Field(min_length=1)
    case_count: int = Field(ge=1)
    input_sha256: dict[str, str]
    l1_qualification_sha256: dict[str, str]
    output_sha256: dict[str, str]
    distribution: dict[str, Any]
    thresholds: dict[str, float | int]
    claim_boundary: dict[str, Any]


_ALLOWED_VOCABULARY = {
    "l2_kinds": [
        "habit",
        "long_running_state",
        "preference_profile",
        "project",
        "summary_event",
        "task",
    ],
    "abstraction_methods": [
        "coreference_resolution",
        "lifecycle_resolution",
        "preference_aggregation",
        "state_summary",
        "task_composition",
    ],
    "closure_patterns": [
        "causal_answerability",
        "multi_evidence_set",
        "single_fact",
        "temporal_chain",
        "update_supersession",
    ],
    "modalities": [
        "actual",
        "denied",
        "hypothetical",
        "planned",
        "recommended",
        "requested",
    ],
    "polarities": ["negative", "positive"],
}


def _require_read_only(path: Path, label: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"{label} missing: {path}")
    if path.stat().st_mode & 0o222:
        raise ValueError(f"{label} must be read-only")


def _opaque_ref(prefix: str, value: str) -> str:
    digest = hashlib.sha256(f"typed-extractor-l2-v1:{value}".encode()).hexdigest()
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


def _candidate_refs(value: Any) -> set[str]:
    return {
        *value.replaces_candidate_refs,
        *value.supersedes_candidate_refs,
        *value.conflicts_with_candidate_refs,
        *(
            [value.replacement_candidate_ref]
            if value.replacement_candidate_ref is not None
            else []
        ),
    }


def _record_lifecycle(record: Any) -> Any:
    from .typed_extractor_l1 import TypedLifecycleBinding

    status = record.status
    lifecycle = {
        "active": "active",
        "corrected": "superseded",
        "superseded": "superseded",
        "active_conflict": "conflicted",
    }[status]
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


def _record_operations(record: Any) -> Any:
    from .typed_extractor_l1 import TypedOperationProvenance

    return TypedOperationProvenance(
        confirmed_by_operation_refs=[
            _opaque_ref("operation", item) for item in record.confirmed_by
        ],
        added_by_operation_refs=[
            _opaque_ref("operation", item) for item in record.added_by
        ],
    )


def _validate_l1_qualification(root: Path) -> dict[str, str]:
    root = root.resolve()
    required = [
        root / "public-l1.json",
        root / "authority-l1.json",
        root / "gold-l1.json",
        root / "manifest-l1.json",
        root / "proposer-prompt-l1.md",
        root / "source-cases-l1.json",
    ]
    for path in required:
        _require_read_only(path, f"L1 qualification {path.name}")
    selection_path = root / "l2-source-qualification-receipt.json"
    _require_read_only(selection_path, "L1 qualification selection")
    selection = L1QualificationSelection.model_validate(load_json(selection_path))
    run_root = root / "model-runs" / selection.run_id
    for name in L1_QUALIFICATION_ARTIFACTS:
        path = run_root / name
        _require_read_only(path, f"L1 selected {name}")
        if sha256_file(path) != selection.artifact_sha256[name]:
            raise ValueError(f"L1 qualification selection hash mismatch: {name}")
    score = load_json(run_root / "score.json")
    if (
        score.get("run_id") != selection.run_id
        or score.get("raw_proposer_quality_ready") is not True
        or score.get("deterministic_gate_safety_ready") is not True
    ):
        raise ValueError("selected L1 qualification is not a passing frozen run")
    return {
        **{path.name: sha256_file(path) for path in required},
        **{
            f"passing/{name}": sha256_file(run_root / name)
            for name in L1_QUALIFICATION_ARTIFACTS
        },
    }


def _build_l2_dev_slice(
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
    l1_qualification_root: Path,
) -> tuple[L2PublicPayload, L2AuthorityPayload, L2GoldPayload, dict[str, Any], dict[str, str]]:
    for path, label in (
        (source_config_path, "source config"),
        (prompt_path, "proposer prompt"),
        (bridge_ledger_path, "bridge-v3 ledger"),
    ):
        _require_read_only(path, label)
    l1_hashes = _validate_l1_qualification(l1_qualification_root)
    config = L2SourceConfig.model_validate(load_json(source_config_path))
    overlap = set(config.public_vocabulary) & set(_ALLOWED_VOCABULARY)
    if overlap:
        raise ValueError("public vocabulary cannot override base vocabulary")
    if len(config.cases) != 6:
        raise ValueError("L2 dev slice must contain exactly 6 cases")
    ledger = ExtractionCompatibilityLedger.model_validate(load_json(bridge_ledger_path))
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
    public_cases: list[L2PublicCase] = []
    authority_cases: list[L2AuthorityCase] = []
    gold_items: list[L2GoldItem] = []
    emit_count = abstain_count = 0
    closure_patterns: set[str] = set()
    abstraction_methods: set[str] = set()

    for source_case in config.cases:
        record = records.get(source_case.knowledge_id)
        envelope = envelopes.get(source_case.knowledge_id)
        if record is None or envelope is None:
            raise ValueError(f"unknown bridge-v3 knowledge ID: {source_case.knowledge_id}")
        if envelope.candidate_level != "l2_cross_turn_candidate":
            raise ValueError("L2 dev source must be a cross-turn bridge candidate")
        evidence_turns = sorted(
            {int(item["turn_index"]) for item in record.knowledge["evidence"]}
        )
        if len(evidence_turns) < 2:
            raise ValueError("L2 dev source evidence must span at least two turns")
        case_id = _opaque_ref("case", source_case.knowledge_id)
        candidate_ref = _opaque_ref("candidate", source_case.knowledge_id)
        session_ref = _opaque_ref("session", record.candidate_id)
        support_refs = [item.support_ref for item in source_case.typed_l1_support_pack]
        expected_support_refs = [
            _opaque_ref("support", f"{source_case.knowledge_id}:{index}")
            for index in range(1, len(support_refs) + 1)
        ]
        if support_refs != expected_support_refs:
            raise ValueError("typed L1 support refs are not deterministic and ordered")
        expected_evidence = sorted(
            (
                str(item["evidence_id"]),
                _speaker(str(item["message"]), str(item["evidence_role"])),
                int(item["turn_index"]),
            )
            for item in record.knowledge["evidence"]
        )
        actual_evidence: list[tuple[str, str, int]] = []
        for support in source_case.typed_l1_support_pack:
            if support.source_session_ref != session_ref:
                raise ValueError("typed L1 support has incorrect session ref")
            matching_turns = [
                turn_index
                for turn_index in evidence_turns
                if support.source_turn_ref
                == _opaque_ref("turn", f"{record.candidate_id}:{turn_index}")
            ]
            if len(matching_turns) != 1:
                raise ValueError("typed L1 support has incorrect turn ref")
            turn_index = matching_turns[0]
            actual_evidence.extend(
                (binding.evidence_id, binding.speaker, turn_index)
                for binding in support.evidence_bindings
            )
        if sorted(actual_evidence) != expected_evidence:
            raise ValueError("typed L1 support pack does not exactly cover bridge evidence")
        evidence_bindings = [
            TypedEvidenceBinding(evidence_id=evidence_id, speaker=speaker)
            for evidence_id, speaker, _ in expected_evidence
        ]
        turn_refs = [
            _opaque_ref("turn", f"{record.candidate_id}:{turn_index}")
            for turn_index in evidence_turns
        ]
        expected = source_case.expected_typed_candidate
        if expected is not None:
            if expected.supporting_l1_refs != support_refs:
                raise ValueError("gold L2 support refs do not match public support pack")
            if expected.source_turn_refs != turn_refs:
                raise ValueError("gold L2 source turn coverage mismatch")
            if expected.source_session_refs != [session_ref]:
                raise ValueError("gold L2 source session coverage mismatch")
            if expected.evidence_bindings != evidence_bindings:
                raise ValueError("gold L2 evidence coverage mismatch")
            if expected.abstraction.method not in source_case.allowed_abstraction_methods:
                raise ValueError("gold L2 abstraction is not authorized")
            if expected.closure.pattern not in source_case.allowed_closure_patterns:
                raise ValueError("gold L2 closure is not authorized")
            closure_patterns.add(expected.closure.pattern)
            abstraction_methods.add(expected.abstraction.method)

        lifecycle = _record_lifecycle(record)
        operations = _record_operations(record)
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
            L2PublicCase(
                case_id=case_id,
                candidate_ref=candidate_ref,
                source_session_ref=session_ref,
                source_turns=[
                    L2PublicTurn(
                        source_turn_ref=_opaque_ref(
                            "turn", f"{record.candidate_id}:{turn_index}"
                        ),
                        turn_index=turn_index,
                        user=replay.source_turns[(record.candidate_id, turn_index)].user,
                        agent=replay.source_turns[(record.candidate_id, turn_index)].agent,
                    )
                    for turn_index in evidence_turns
                ],
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
                typed_l1_support_pack=source_case.typed_l1_support_pack,
            )
        )
        authority_cases.append(
            L2AuthorityCase(
                case_id=case_id,
                candidate_ref=candidate_ref,
                knowledge_id=source_case.knowledge_id,
                candidate_id=record.candidate_id,
                emission_allowed=source_case.emission_allowed,
                required_support_refs=support_refs,
                required_evidence_bindings=evidence_bindings,
                required_source_turn_refs=turn_refs,
                required_source_session_refs=[session_ref],
                allowed_abstraction_methods=source_case.allowed_abstraction_methods,
                allowed_closure_patterns=source_case.allowed_closure_patterns,
                unresolved_required_fields=source_case.unresolved_required_fields,
            )
        )
        gold_items.append(
            L2GoldItem(
                case_id=case_id,
                candidate_ref=candidate_ref,
                expected_decision=source_case.expected_decision,
                expected_typed_candidate=expected,
            )
        )
        emit_count += source_case.expected_decision == "emit_l2"
        abstain_count += source_case.expected_decision == "abstain"

    distribution = {
        "emit_count": emit_count,
        "abstain_count": abstain_count,
        "closure_patterns": sorted(closure_patterns),
        "abstraction_methods": sorted(abstraction_methods),
    }
    expected_distribution = {
        "emit_count": 4,
        "abstain_count": 2,
        "closure_patterns": ["multi_evidence_set", "update_supersession"],
        "abstraction_methods": [
            "coreference_resolution",
            "lifecycle_resolution",
            "task_composition",
        ],
    }
    if distribution != expected_distribution:
        raise ValueError("L2 dev distribution mismatch")
    public = L2PublicPayload(
        dataset_id=config.dataset_id,
        case_count=len(public_cases),
        allowed_vocabulary={**_ALLOWED_VOCABULARY, **config.public_vocabulary},
        cases=public_cases,
    )
    authority = L2AuthorityPayload(
        dataset_id=config.dataset_id,
        case_count=len(authority_cases),
        cases=authority_cases,
    )
    gold = L2GoldPayload(
        dataset_id=config.dataset_id,
        case_count=len(gold_items),
        items=gold_items,
    )
    return public, authority, gold, distribution, l1_hashes


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
    l1_qualification_root: Path,
) -> dict[str, str]:
    del l1_qualification_root
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


def _resolved_paths(**paths: Path) -> dict[str, Path]:
    return {key: value.resolve() for key, value in paths.items()}


def prepare_l2_dev_slice(
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
    l1_qualification_root: Path,
    output_root: Path,
) -> dict[str, Any]:
    paths = _resolved_paths(
        source_config_path=source_config_path,
        prompt_path=prompt_path,
        bridge_ledger_path=bridge_ledger_path,
        source_path=source_path,
        turn_manifest_path=turn_manifest_path,
        dialogue_manifest_path=dialogue_manifest_path,
        final_knowledge_path=final_knowledge_path,
        run_path=run_path,
        source_segments_path=source_segments_path,
        l1_qualification_root=l1_qualification_root,
    )
    public, authority, gold, distribution, l1_hashes = _build_l2_dev_slice(**paths)
    output_root = output_root.resolve()
    outputs = {
        "public-l2.json": public,
        "authority-l2.json": authority,
        "gold-l2.json": gold,
    }
    for name, payload in outputs.items():
        write_json_immutable(output_root / name, payload)
    manifest = L2Manifest(
        dataset_id=public.dataset_id,
        case_count=public.case_count,
        input_sha256=_input_sha256(**paths),
        l1_qualification_sha256=l1_hashes,
        output_sha256={name: sha256_file(output_root / name) for name in sorted(outputs)},
        distribution=distribution,
        thresholds=dict(L2_DEV_THRESHOLDS),
        claim_boundary={
            "automatic_authoritative_writes": False,
            "embedding_authority": False,
            "fresh_hidden_created": False,
            "l1_support_pack_is_authoritative": False,
            "longmemeval_status": "structured_l2_identity_unresolved",
        },
    )
    write_json_immutable(output_root / "manifest-l2.json", manifest)
    for name in (*outputs, "manifest-l2.json"):
        (output_root / name).chmod(0o444)
    return {"status": "valid", "case_count": public.case_count, **distribution}


def validate_l2_dev_slice(
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
    l1_qualification_root: Path,
    root: Path,
) -> dict[str, Any]:
    paths = _resolved_paths(
        source_config_path=source_config_path,
        prompt_path=prompt_path,
        bridge_ledger_path=bridge_ledger_path,
        source_path=source_path,
        turn_manifest_path=turn_manifest_path,
        dialogue_manifest_path=dialogue_manifest_path,
        final_knowledge_path=final_knowledge_path,
        run_path=run_path,
        source_segments_path=source_segments_path,
        l1_qualification_root=l1_qualification_root,
    )
    public, authority, gold, distribution, l1_hashes = _build_l2_dev_slice(**paths)
    root = root.resolve()
    expected_outputs = {
        "authority-l2.json": authority,
        "gold-l2.json": gold,
        "public-l2.json": public,
    }
    for name, expected in expected_outputs.items():
        path = root / name
        _require_read_only(path, name)
        if path.read_bytes() != canonical_json_bytes(expected):
            raise ValueError(f"typed L2 artifact drift: {name}")
    manifest_path = root / "manifest-l2.json"
    _require_read_only(manifest_path, "manifest-l2.json")
    actual = L2Manifest.model_validate(load_json(manifest_path))
    expected_manifest = L2Manifest(
        dataset_id=public.dataset_id,
        case_count=public.case_count,
        input_sha256=_input_sha256(**paths),
        l1_qualification_sha256=l1_hashes,
        output_sha256={name: sha256_file(root / name) for name in sorted(expected_outputs)},
        distribution=distribution,
        thresholds=dict(L2_DEV_THRESHOLDS),
        claim_boundary={
            "automatic_authoritative_writes": False,
            "embedding_authority": False,
            "fresh_hidden_created": False,
            "l1_support_pack_is_authoritative": False,
            "longmemeval_status": "structured_l2_identity_unresolved",
        },
    )
    if canonical_json_bytes(actual) != canonical_json_bytes(expected_manifest):
        raise ValueError("typed L2 manifest drift")
    return {"status": "valid", "case_count": public.case_count, **distribution}


class L2ScoredCase(StrictModel):
    case_id: str = Field(pattern=r"^case-[0-9a-f]{16}$")
    expected_decision: L2Decision
    raw_decision: L2Decision
    gated_decision: L2Decision
    raw_errors: list[str] = Field(default_factory=list)
    gate_reasons: list[str] = Field(default_factory=list)


class L2ScorePayload(StrictModel):
    schema_version: Literal["typed-extractor-l2-score-v2"] = (
        "typed-extractor-l2-score-v2"
    )
    status: Literal["scored"] = "scored"
    scoring_policy_version: Literal["evidence-set-abstraction-method-v2"] = (
        "evidence-set-abstraction-method-v2"
    )
    dataset_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    case_count: int = Field(ge=1)
    raw_proposer_quality_ready: bool
    deterministic_gate_safety_ready: bool
    metrics: dict[str, Any]
    cases: list[L2ScoredCase] = Field(min_length=1)
    error_taxonomy: dict[str, int]
    gate_reason_counts: dict[str, int]
    guard_state: dict[str, Any]
    claim_boundary: dict[str, Any]


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 1.0


def _f1(
    *, true_positive: int, false_positive: int, false_negative: int
) -> tuple[float, float, float]:
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


def _evidence_binding_set(
    bindings: list[TypedEvidenceBinding],
) -> set[tuple[str, str]]:
    return {(item.evidence_id, item.speaker) for item in bindings}


def _gate_proposal(
    proposal: L2ProposalRecord,
    authority: L2AuthorityCase,
) -> tuple[L2Decision, list[str]]:
    if proposal.decision != "emit_l2":
        return proposal.decision, []
    typed = proposal.typed_candidate
    if typed is None:
        raise ValueError("emit_l2 proposal has no typed candidate")
    reasons: list[str] = []
    if not authority.emission_allowed:
        reasons.append("emission_not_authorized")
    if authority.unresolved_required_fields:
        reasons.append("unresolved_required_fields")
    if typed.supporting_l1_refs != authority.required_support_refs:
        reasons.append("support_ids_not_authorized")
    if _evidence_binding_set(typed.evidence_bindings) != _evidence_binding_set(
        authority.required_evidence_bindings
    ):
        reasons.append("evidence_not_authorized")
    if typed.source_turn_refs != authority.required_source_turn_refs:
        reasons.append("source_turn_coverage_not_authorized")
    if typed.source_session_refs != authority.required_source_session_refs:
        reasons.append("source_session_coverage_not_authorized")
    if typed.abstraction.method not in authority.allowed_abstraction_methods:
        reasons.append("abstraction_method_not_authorized")
    if typed.closure.pattern not in authority.allowed_closure_patterns:
        reasons.append("closure_pattern_not_authorized")
    return ("abstain", sorted(reasons)) if reasons else ("emit_l2", [])


def _raw_errors(proposal: L2ProposalRecord, gold: L2GoldItem) -> list[str]:
    errors: set[str] = set()
    if proposal.decision != gold.expected_decision:
        if proposal.decision == "emit_l2" and gold.expected_decision != "emit_l2":
            errors.add("false_emission")
        elif proposal.decision != "emit_l2" and gold.expected_decision == "emit_l2":
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
                "abstraction_error",
                "closure_error",
                "evidence_error",
                "kind_error",
                "source_coverage_error",
                "structured_claim_error",
                "summary_error",
                "support_id_error",
            }
        )
        return sorted(errors)
    if _evidence_binding_set(actual.evidence_bindings) != _evidence_binding_set(
        expected.evidence_bindings
    ):
        errors.add("evidence_error")
    if actual.kind != expected.kind:
        errors.add("kind_error")
    if actual.summary != expected.summary:
        errors.add("summary_error")
    if actual.supporting_l1_refs != expected.supporting_l1_refs:
        errors.add("support_id_error")
    if actual.structured_claims != expected.structured_claims:
        errors.add("structured_claim_error")
    if actual.abstraction.method != expected.abstraction.method:
        errors.add("abstraction_error")
    if actual.closure != expected.closure:
        errors.add("closure_error")
    if (
        actual.source_turn_refs != expected.source_turn_refs
        or actual.source_session_refs != expected.source_session_refs
    ):
        errors.add("source_coverage_error")
    return sorted(errors)


def _require_scoring_inputs(
    root: Path, proposals_path: Path, provenance_path: Path
) -> None:
    for path, label in (
        (root / "public-l2.json", "public-l2.json"),
        (root / "authority-l2.json", "authority-l2.json"),
        (root / "gold-l2.json", "gold-l2.json"),
        (root / "manifest-l2.json", "manifest-l2.json"),
        (proposals_path, "proposals"),
        (provenance_path, "provenance"),
    ):
        _require_read_only(path, label)


def score_l2_proposals(
    root: Path,
    proposals_path: Path,
    provenance_path: Path,
    *,
    guard_bundle: MemoryRepresentationBundleV3,
) -> L2ScorePayload:
    from .typed_extractor_l2_model_run import (
        L2ModelDispatch,
        L2ModelProvenance,
        extract_l2_proposal_payload,
    )

    root = root.resolve()
    proposals_path = proposals_path.resolve()
    provenance_path = provenance_path.resolve()
    _require_scoring_inputs(root, proposals_path, provenance_path)
    public = L2PublicPayload.model_validate(load_json(root / "public-l2.json"))
    authority = L2AuthorityPayload.model_validate(load_json(root / "authority-l2.json"))
    gold = L2GoldPayload.model_validate(load_json(root / "gold-l2.json"))
    manifest = L2Manifest.model_validate(load_json(root / "manifest-l2.json"))
    proposals = L2ProposalPayload.model_validate(load_json(proposals_path))
    provenance = L2ModelProvenance.model_validate(load_json(provenance_path))
    dispatch_path = provenance_path.parent / provenance.dispatch_filename
    raw_response_path = provenance_path.parent / provenance.raw_response_filename
    _require_read_only(dispatch_path, "dispatch")
    _require_read_only(raw_response_path, "raw response")
    dispatch = L2ModelDispatch.model_validate(load_json(dispatch_path))
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
    if extract_l2_proposal_payload(response_payload) != proposals:
        raise ValueError("frozen proposals do not match raw response")
    if provenance.allowed_input_sha256.get("public-l2.json") != sha256_file(
        root / "public-l2.json"
    ):
        raise ValueError("provenance does not bind public input")
    if proposals.dataset_id != public.dataset_id or provenance.dataset_id != public.dataset_id:
        raise ValueError("scoring dataset mismatch")
    if proposals.run_id != provenance.run_id:
        raise ValueError("scoring run metadata mismatch")
    expected_output_hashes = {
        name: sha256_file(root / name)
        for name in ("authority-l2.json", "gold-l2.json", "public-l2.json")
    }
    if manifest.output_sha256 != expected_output_hashes:
        raise ValueError("manifest does not bind scoring inputs")
    if manifest.thresholds != L2_DEV_THRESHOLDS:
        raise ValueError("manifest does not match fixed qualification thresholds")
    public_by_id = {item.case_id: item for item in public.cases}
    authority_by_id = {item.case_id: item for item in authority.cases}
    gold_by_id = {item.case_id: item for item in gold.items}
    proposal_by_id = {item.case_id: item for item in proposals.proposals}
    if not (
        set(public_by_id)
        == set(authority_by_id)
        == set(gold_by_id)
        == set(proposal_by_id)
    ):
        raise ValueError("scoring case coverage mismatch")

    before_fingerprint = canonical_sha256(guard_bundle)
    before_counts = _guard_counts(guard_bundle)
    scored_cases: list[L2ScoredCase] = []
    error_taxonomy = {
        key: 0
        for key in (
            "abstraction_error",
            "closure_error",
            "decision_error",
            "evidence_error",
            "false_abstention",
            "false_emission",
            "kind_error",
            "source_coverage_error",
            "structured_claim_error",
            "summary_error",
            "support_id_error",
        )
    }
    gate_reason_counts: dict[str, int] = {}
    correct_decisions = gated_correct = critical_false_emission = 0
    gate_interventions = deterministic_critical_false = 0
    abstain_tp = abstain_fp = abstain_fn = 0
    emitted_gold_count = 0
    field_correct = {
        "evidence": 0,
        "kind": 0,
        "support": 0,
        "claim": 0,
        "abstraction": 0,
        "closure": 0,
        "source": 0,
        "summary": 0,
    }

    for case_id in sorted(gold_by_id):
        proposal = proposal_by_id[case_id]
        gold_item = gold_by_id[case_id]
        authority_item = authority_by_id[case_id]
        errors = _raw_errors(proposal, gold_item)
        for error in errors:
            error_taxonomy[error] += 1
        gated_decision, gate_reasons = _gate_proposal(proposal, authority_item)
        for reason in gate_reasons:
            gate_reason_counts[reason] = gate_reason_counts.get(reason, 0) + 1
        correct_decisions += proposal.decision == gold_item.expected_decision
        gated_correct += gated_decision == gold_item.expected_decision
        critical_false_emission += (
            proposal.decision == "emit_l2" and gold_item.expected_decision != "emit_l2"
        )
        gate_interventions += proposal.decision == "emit_l2" and gated_decision == "abstain"
        deterministic_critical_false += (
            gated_decision == "emit_l2" and gold_item.expected_decision != "emit_l2"
        )
        gold_abstain = gold_item.expected_decision == "abstain"
        raw_abstain = proposal.decision == "abstain"
        abstain_tp += gold_abstain and raw_abstain
        abstain_fp += not gold_abstain and raw_abstain
        abstain_fn += gold_abstain and not raw_abstain
        expected = gold_item.expected_typed_candidate
        actual = proposal.typed_candidate
        if expected is not None:
            emitted_gold_count += 1
            field_correct["evidence"] += actual is not None and _evidence_binding_set(actual.evidence_bindings) == _evidence_binding_set(expected.evidence_bindings)
            field_correct["kind"] += actual is not None and actual.kind == expected.kind
            field_correct["support"] += actual is not None and actual.supporting_l1_refs == expected.supporting_l1_refs
            field_correct["claim"] += actual is not None and actual.structured_claims == expected.structured_claims
            field_correct["abstraction"] += actual is not None and actual.abstraction.method == expected.abstraction.method
            field_correct["closure"] += actual is not None and actual.closure == expected.closure
            field_correct["source"] += actual is not None and actual.source_turn_refs == expected.source_turn_refs and actual.source_session_refs == expected.source_session_refs
            field_correct["summary"] += actual is not None and actual.summary == expected.summary
        scored_cases.append(
            L2ScoredCase(
                case_id=case_id,
                expected_decision=gold_item.expected_decision,
                raw_decision=proposal.decision,
                gated_decision=gated_decision,
                raw_errors=errors,
                gate_reasons=gate_reasons,
            )
        )

    abstain_precision, abstain_recall, abstain_f1 = _f1(
        true_positive=abstain_tp,
        false_positive=abstain_fp,
        false_negative=abstain_fn,
    )
    metrics = {
        "proposal_coverage": 1.0,
        "schema_valid_rate": 1.0,
        "raw_decision_accuracy": _ratio(correct_decisions, public.case_count),
        "gated_decision_accuracy": _ratio(gated_correct, public.case_count),
        "raw_abstention_precision": abstain_precision,
        "raw_abstention_recall": abstain_recall,
        "raw_abstention_f1": abstain_f1,
        "raw_critical_false_emission_count": critical_false_emission,
        "exact_evidence_rate": _ratio(field_correct["evidence"], emitted_gold_count),
        "kind_accuracy": _ratio(field_correct["kind"], emitted_gold_count),
        "support_id_accuracy": _ratio(field_correct["support"], emitted_gold_count),
        "structured_claim_accuracy": _ratio(field_correct["claim"], emitted_gold_count),
        "abstraction_accuracy": _ratio(field_correct["abstraction"], emitted_gold_count),
        "closure_accuracy": _ratio(field_correct["closure"], emitted_gold_count),
        "source_coverage_accuracy": _ratio(field_correct["source"], emitted_gold_count),
        "summary_accuracy": _ratio(field_correct["summary"], emitted_gold_count),
        "gate_intervention_count": gate_interventions,
        "deterministic_critical_false_materialization_count": deterministic_critical_false,
    }
    thresholds = L2_DEV_THRESHOLDS
    raw_ready = (
        metrics["proposal_coverage"] >= thresholds["proposal_coverage"]
        and metrics["schema_valid_rate"] >= thresholds["schema_valid_rate"]
        and metrics["raw_decision_accuracy"] >= thresholds["raw_decision_accuracy"]
        and metrics["raw_abstention_f1"] >= thresholds["raw_abstention_f1"]
        and metrics["raw_critical_false_emission_count"]
        == thresholds["raw_critical_false_emission_count"]
        and metrics["exact_evidence_rate"] >= thresholds["exact_evidence_rate"]
        and metrics["support_id_accuracy"] >= thresholds["support_id_accuracy"]
        and metrics["source_coverage_accuracy"]
        >= thresholds["source_coverage_accuracy"]
        and all(
            metrics[name] >= thresholds["safety_field_accuracy"]
            for name in (
                "kind_accuracy",
                "structured_claim_accuracy",
                "abstraction_accuracy",
                "closure_accuracy",
                "summary_accuracy",
            )
        )
    )
    after_fingerprint = canonical_sha256(guard_bundle)
    after_counts = _guard_counts(guard_bundle)
    automatic_writes = {
        "closure": 0,
        "identity": 0,
        "l1": 0,
        "l2": 0,
        "membership": 0,
        "unit_revision": 0,
    }
    gate_ready = (
        deterministic_critical_false
        == thresholds["deterministic_critical_false_materialization_count"]
        and before_fingerprint == after_fingerprint
        and before_counts == after_counts
        and all(value == 0 for value in automatic_writes.values())
    )
    return L2ScorePayload(
        dataset_id=public.dataset_id,
        run_id=proposals.run_id,
        case_count=public.case_count,
        raw_proposer_quality_ready=raw_ready,
        deterministic_gate_safety_ready=gate_ready,
        metrics=metrics,
        cases=scored_cases,
        error_taxonomy=error_taxonomy,
        gate_reason_counts=gate_reason_counts,
        guard_state={
            "before_fingerprint": before_fingerprint,
            "after_fingerprint": after_fingerprint,
            "before_counts": before_counts,
            "after_counts": after_counts,
        },
        claim_boundary={
            "automatic_write_counts": automatic_writes,
            "embedding_authority": False,
            "fresh_hidden_created": False,
            "pipeline_integration_authorized": False,
            "longmemeval_status": "structured_l2_identity_unresolved",
        },
    )


def render_l2_score_report(score: L2ScorePayload) -> str:
    metrics = score.metrics
    lines = [
        "# Typed Extractor V2 L2 Dev Qualification Report",
        "",
        f"- Score schema: `{score.schema_version}`",
        f"- Scoring policy: `{score.scoring_policy_version}`",
        f"- Dataset: `{score.dataset_id}`",
        f"- Run: `{score.run_id}`",
        f"- Cases: `{score.case_count}`",
        f"- Raw proposer quality ready: `{str(score.raw_proposer_quality_ready).lower()}`",
        f"- Deterministic gate safety ready: `{str(score.deterministic_gate_safety_ready).lower()}`",
        "",
        "## Raw Proposer Quality",
        "",
    ]
    for key in (
        "raw_decision_accuracy",
        "raw_abstention_f1",
        "raw_critical_false_emission_count",
        "exact_evidence_rate",
        "kind_accuracy",
        "support_id_accuracy",
        "structured_claim_accuracy",
        "abstraction_accuracy",
        "closure_accuracy",
        "source_coverage_accuracy",
        "summary_accuracy",
    ):
        lines.append(f"- {key}: `{metrics[key]}`")
    lines.extend(["", "## Deterministic Gate Safety", ""])
    for key in (
        "gated_decision_accuracy",
        "gate_intervention_count",
        "deterministic_critical_false_materialization_count",
    ):
        lines.append(f"- {key}: `{metrics[key]}`")
    lines.extend(
        [
            f"- Guard fingerprint unchanged: `{score.guard_state['before_fingerprint'] == score.guard_state['after_fingerprint']}`",
            f"- Automatic write counts: `{score.claim_boundary['automatic_write_counts']}`",
            "",
            "## Boundary",
            "",
            "This dev result does not authorize pipeline integration, fresh hidden evaluation, or authoritative L1/L2/revision/closure/identity/membership writes.",
            "`LONGMEMEVAL-6d550036` remains `structured_l2_identity_unresolved`.",
            "",
        ]
    )
    return "\n".join(lines)


def run_l2_scoring_file(
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
    from .authoritative_conformance_runner import build_authoritative_conformance_bundle

    guard_bundle = build_authoritative_conformance_bundle(
        guard_root,
        guard_slice_id,
        guard_results_path,
    )
    score = score_l2_proposals(
        root,
        proposals_path,
        provenance_path,
        guard_bundle=guard_bundle,
    )
    write_json_immutable(score_path, score)
    write_text_immutable(report_path, render_l2_score_report(score))
    write_json_immutable(
        error_analysis_path,
        {
            "schema_version": "typed-extractor-l2-error-analysis-v1",
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
