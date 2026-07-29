from __future__ import annotations

import hashlib
from collections import Counter
from pathlib import Path
from typing import Any, Literal, Sequence

from pydantic import Field, model_validator

from .io import canonical_json_bytes, load_json, sha256_file, write_json_immutable
from .typed_extractor_l1 import (
    AutomaticWriteAuthorizations,
    PublicEvidenceSpan,
    PublicUntypedCandidate,
    TypedEvidenceBinding,
    TypedLifecycleBinding,
    TypedLocalEntity,
    TypedModality,
    TypedOperationProvenance,
    TypedPolarity,
    TypedPredicate,
    TypedRoleBinding,
    TypedTimeBinding,
)
from .typed_extractor_l2 import (
    ClosurePattern,
    L2AbstractionMethod,
    L2AuthorityCase,
    L2AuthorityPayload,
    L2Decision,
    L2GoldItem,
    L2GoldPayload,
    L2Kind,
    L2Manifest,
    L2PublicCase,
    L2PublicPayload,
    L2PublicTurn,
    L2_DEV_THRESHOLDS,
    StrictModel,
    TypedL1SupportCandidate,
    TypedL2Abstraction,
    TypedL2Candidate,
    TypedL2Closure,
    TypedL2StructuredClaim,
)


DATASET_ID = "typed-extractor-l2-dev-repair-v1"
OPAQUE_NAMESPACE = "typed-extractor-l2-dev-repair-v1:2026-07-28"
_OPAQUE_NAMESPACES = {
    "typed-extractor-l2-dev-repair-v1": OPAQUE_NAMESPACE,
    "typed-extractor-l2-dev-repair-v2": (
        "typed-extractor-l2-dev-repair-v2:2026-07-28"
    ),
    "typed-extractor-l2-dev-repair-v3": (
        "typed-extractor-l2-dev-repair-v3:2026-07-28"
    ),
}

_L2_V8_REQUIRED_CATALOGS = {
    "abstraction_methods",
    "canonical_operators",
    "closure_patterns",
    "l2_kinds",
    "modalities",
    "operator_kind_bindings",
    "operator_role_bindings",
    "polarities",
    "predicate_senses",
}
_L2_V9_REQUIRED_CATALOGS = _L2_V8_REQUIRED_CATALOGS | {
    "operator_sense_bindings"
}

EXPECTED_L2_CASE_IDS = (
    "abstain-unsupported-modality",
    "abstain-unresolved-selected-option",
    "abstain-incompatible-supports",
    "abstain-incomplete-evidence-closure",
    "emit-coreference-device-request",
    "emit-coreference-document-reference",
    "emit-task-composition-release",
    "emit-task-composition-travel",
    "emit-lifecycle-commitment",
    "emit-lifecycle-supersession",
    "emit-state-summary",
    "emit-preference-aggregation",
)

L2RepairFamily = Literal[
    "unsupported_modality_control",
    "unresolved_selection_control",
    "incompatible_support_control",
    "incomplete_closure_control",
    "coreference_case",
    "task_composition_case",
    "lifecycle_case",
    "state_summary_case",
    "preference_aggregation_case",
    "abstention",
    "evidence",
    "support",
    "source_coverage",
    "kind",
    "structured_claim",
    "abstraction",
    "closure",
    "summary",
]

_EXPECTED_PRIMARY_FAMILIES = (
    "unsupported_modality_control",
    "unresolved_selection_control",
    "incompatible_support_control",
    "incomplete_closure_control",
    "coreference_case",
    "coreference_case",
    "task_composition_case",
    "task_composition_case",
    "lifecycle_case",
    "lifecycle_case",
    "state_summary_case",
    "preference_aggregation_case",
)

_BASE_VOCABULARY = {
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


class L2DiagnosticTurn(StrictModel):
    private_turn_id: str = Field(min_length=1)
    turn_index: int = Field(ge=0)
    user: str
    agent: str


class L2DiagnosticL1Support(StrictModel):
    private_support_id: str = Field(min_length=1)
    private_turn_id: str = Field(min_length=1)
    kind: Literal["event", "state", "preference", "task", "attribute"]
    predicate: TypedPredicate
    local_entities: list[TypedLocalEntity] = Field(min_length=1)
    roles: list[TypedRoleBinding] = Field(min_length=1)
    modality: TypedModality = "actual"
    polarity: TypedPolarity = "positive"
    time: TypedTimeBinding = Field(default_factory=TypedTimeBinding)
    evidence_bindings: list[TypedEvidenceBinding] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_local_closure(self) -> "L2DiagnosticL1Support":
        local_ids = [item.local_entity_id for item in self.local_entities]
        expected = [f"entity-{index:02d}" for index in range(1, len(local_ids) + 1)]
        if local_ids != expected:
            raise ValueError("diagnostic support local entities are not ordered")
        if not {item.local_entity_id for item in self.roles}.issubset(set(local_ids)):
            raise ValueError("diagnostic support role references unknown entity")
        return self


class L2DiagnosticStructuredClaim(StrictModel):
    claim_ref: str = Field(pattern=r"^claim-[0-9]{2}$")
    predicate: TypedPredicate
    local_entities: list[TypedLocalEntity] = Field(min_length=1)
    roles: list[TypedRoleBinding] = Field(min_length=1)
    modality: TypedModality = "actual"
    polarity: TypedPolarity = "positive"
    time: TypedTimeBinding = Field(default_factory=TypedTimeBinding)
    supporting_l1_refs: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_local_closure(self) -> "L2DiagnosticStructuredClaim":
        local_ids = [item.local_entity_id for item in self.local_entities]
        expected = [f"entity-{index:02d}" for index in range(1, len(local_ids) + 1)]
        if local_ids != expected:
            raise ValueError("diagnostic claim local entities are not ordered")
        if not {item.local_entity_id for item in self.roles}.issubset(set(local_ids)):
            raise ValueError("diagnostic claim role references unknown entity")
        if len(self.supporting_l1_refs) != len(set(self.supporting_l1_refs)):
            raise ValueError("duplicate diagnostic claim support")
        return self


class L2DiagnosticClosure(StrictModel):
    pattern: ClosurePattern
    required_support_refs: list[str] = Field(min_length=1)
    optional_support_refs: list[str] = Field(default_factory=list)


class L2DiagnosticCandidate(StrictModel):
    kind: L2Kind
    summary: str = Field(min_length=1)
    supporting_l1_refs: list[str] = Field(min_length=1)
    structured_claims: list[L2DiagnosticStructuredClaim] = Field(min_length=1)
    abstraction: TypedL2Abstraction
    closure: L2DiagnosticClosure
    source_turn_refs: list[str] = Field(min_length=1)
    source_session_refs: list[str] = Field(min_length=1)
    evidence_bindings: list[TypedEvidenceBinding] = Field(min_length=1)
    lifecycle: Literal["candidate"] = "candidate"

    @model_validator(mode="after")
    def validate_support_closure(self) -> "L2DiagnosticCandidate":
        claim_refs = [claim.claim_ref for claim in self.structured_claims]
        expected_claims = [
            f"claim-{index:02d}" for index in range(1, len(claim_refs) + 1)
        ]
        if claim_refs != expected_claims:
            raise ValueError("diagnostic claim refs are not contiguous")
        support_refs = self.supporting_l1_refs
        support_set = set(support_refs)
        if len(support_refs) != len(support_set):
            raise ValueError("duplicate diagnostic L1 support")
        claim_supports = {
            ref for claim in self.structured_claims for ref in claim.supporting_l1_refs
        }
        required = set(self.closure.required_support_refs)
        optional = set(self.closure.optional_support_refs)
        if (
            claim_supports != support_set
            or required != support_set
            or optional & required
        ):
            raise ValueError("diagnostic support closure is incomplete")
        return self


class L2DiagnosticAuthority(StrictModel):
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


class L2DiagnosticUntypedCandidate(StrictModel):
    statement: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    predicate: str = Field(min_length=1)
    object: str | None = None
    qualifiers: dict[str, Any] = Field(default_factory=dict)
    source_status: Literal["user_reported", "agent_generated", "tool_observed"]
    derivation: Literal["explicit", "context_completed", "inferred"]
    inference_basis: str | None = None
    evidence: list[PublicEvidenceSpan] = Field(min_length=1)


class L2DiagnosticCase(StrictModel):
    private_case_id: str = Field(min_length=1)
    primary_family: L2RepairFamily
    secondary_families: list[L2RepairFamily] = Field(default_factory=list)
    private_session_id: str = Field(min_length=1)
    source_turns: list[L2DiagnosticTurn] = Field(min_length=2)
    untyped_candidate: L2DiagnosticUntypedCandidate
    typed_l1_support_pack: list[L2DiagnosticL1Support] = Field(min_length=2)
    expected_decision: L2Decision
    expected_typed_candidate: L2DiagnosticCandidate | None = None
    authority: L2DiagnosticAuthority

    @model_validator(mode="after")
    def validate_case_contract(self) -> "L2DiagnosticCase":
        if len(self.secondary_families) != len(set(self.secondary_families)):
            raise ValueError("duplicate L2 secondary family")
        if self.primary_family in self.secondary_families:
            raise ValueError("L2 primary family cannot repeat as secondary")
        emits = self.expected_decision == "emit_l2"
        if emits != (self.expected_typed_candidate is not None):
            raise ValueError("L2 expected decision and typed candidate disagree")
        if emits != self.authority.emission_allowed:
            raise ValueError("L2 expected decision and emission authority disagree")
        if emits and (
            not self.authority.allowed_abstraction_methods
            or not self.authority.allowed_closure_patterns
        ):
            raise ValueError("L2 emission requires abstraction and closure authority")
        if not emits and not self.authority.unresolved_required_fields:
            raise ValueError("L2 abstention requires unresolved fields")
        return self


class L2DiagnosticSource(StrictModel):
    schema_version: Literal[
        "typed-extractor-l2-diagnostic-source-v1",
        "typed-extractor-l2-diagnostic-source-v2",
        "typed-extractor-l2-diagnostic-source-v3",
    ]
    dataset_id: Literal[
        "typed-extractor-l2-dev-repair-v1",
        "typed-extractor-l2-dev-repair-v2",
        "typed-extractor-l2-dev-repair-v3",
    ]
    provenance: Literal["diagnostic_authored"]
    public_vocabulary: dict[str, list[str]]
    cases: list[L2DiagnosticCase]

    @model_validator(mode="after")
    def validate_source_contract(self) -> "L2DiagnosticSource":
        version = self.schema_version.rsplit("-", 1)[-1]
        if not self.dataset_id.endswith(f"-{version}"):
            raise ValueError("L2 diagnostic schema and dataset versions differ")
        if version in {"v2", "v3"}:
            required_catalogs = (
                _L2_V9_REQUIRED_CATALOGS
                if version == "v3"
                else _L2_V8_REQUIRED_CATALOGS
            )
            missing_catalogs = required_catalogs - set(
                _BASE_VOCABULARY | self.public_vocabulary
            )
            if missing_catalogs:
                raise ValueError(
                    f"missing L2 {'V9' if version == 'v3' else 'V8'} "
                    "public catalogs: "
                    + ", ".join(sorted(missing_catalogs))
                )
        if len(self.cases) != 12:
            raise ValueError("L2 diagnostic source must contain exactly 12 cases")
        private_ids = [case.private_case_id for case in self.cases]
        if len(private_ids) != len(set(private_ids)):
            raise ValueError("duplicate private case ID")
        if tuple(private_ids) != EXPECTED_L2_CASE_IDS:
            raise ValueError("L2 diagnostic case ID list differs")
        if tuple(case.primary_family for case in self.cases) != _EXPECTED_PRIMARY_FAMILIES:
            raise ValueError("L2 diagnostic primary-family list differs")
        for values, label in (
            ([case.private_session_id for case in self.cases], "session"),
            ([case.authority.knowledge_id for case in self.cases], "knowledge"),
            ([case.authority.candidate_id for case in self.cases], "candidate"),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"duplicate diagnostic {label} ID")
        if set(self.public_vocabulary) & set(_BASE_VOCABULARY):
            raise ValueError("public vocabulary cannot override L2 base vocabulary")
        for key, values in self.public_vocabulary.items():
            if not key or not values or len(values) != len(set(values)):
                raise ValueError("public vocabulary entries must be unique and non-empty")
        if version in {"v2", "v3"}:
            vocabulary = {**_BASE_VOCABULARY, **self.public_vocabulary}
            canonical_operators = set(vocabulary["canonical_operators"])
            predicate_senses = set(vocabulary["predicate_senses"])
            kind_bindings = set(vocabulary["operator_kind_bindings"])
            role_bindings = set(vocabulary["operator_role_bindings"])
            operator_sense_bindings = set(
                vocabulary.get("operator_sense_bindings", [])
            )
            closure_by_method = {
                "coreference_resolution": "multi_evidence_set",
                "lifecycle_resolution": "update_supersession",
                "preference_aggregation": "multi_evidence_set",
                "state_summary": "multi_evidence_set",
                "task_composition": "multi_evidence_set",
            }
            for case in self.cases:
                candidate = case.expected_typed_candidate
                if candidate is None:
                    continue
                for claim in candidate.structured_claims:
                    operator = claim.predicate.canonical_operator
                    if (
                        operator not in canonical_operators
                        or claim.predicate.sense not in predicate_senses
                        or f"{operator}|{candidate.kind}" not in kind_bindings
                    ):
                        raise ValueError(
                            "L2 V8 public catalog does not cover emitted candidate: "
                            "L2 V8 operator-kind catalog mismatch"
                        )
                    if version == "v3" and (
                        f"{operator}|{claim.predicate.sense}"
                        not in operator_sense_bindings
                    ):
                        raise ValueError(
                            "L2 V9 operator-sense catalog mismatch"
                        )
                    expected_roles = {
                        f"{operator}|{role.role}|{role.role_name}"
                        for role in claim.roles
                    }
                    if not expected_roles.issubset(role_bindings):
                        raise ValueError(
                            "L2 V8 public catalog does not cover emitted candidate: "
                            "L2 V8 operator-role catalog mismatch"
                        )
                expected_closure = closure_by_method[candidate.abstraction.method]
                if candidate.closure.pattern != expected_closure:
                    raise ValueError(
                        "L2 V8 abstraction-closure mapping: "
                        "L2 V8 abstraction-to-closure mapping differs"
                    )
        return self


def _require_read_only(path: Path, label: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"{label} missing: {path}")
    if path.stat().st_mode & 0o222:
        raise ValueError(f"{label} must be read-only")


def _opaque_ref(prefix: str, value: str, namespace: str = OPAQUE_NAMESPACE) -> str:
    digest = hashlib.sha256(f"{namespace}:{prefix}:{value}".encode()).hexdigest()
    length = 64 if prefix == "evidence" else 16
    return f"{prefix}-{digest[:length]}"


def _remap_evidence(
    value: TypedEvidenceBinding,
    namespace: str = OPAQUE_NAMESPACE,
) -> TypedEvidenceBinding:
    return TypedEvidenceBinding(
        evidence_id=_opaque_ref("evidence", value.evidence_id, namespace),
        speaker=value.speaker,
    )


def _remap_lifecycle(
    value: TypedLifecycleBinding,
    namespace: str = OPAQUE_NAMESPACE,
) -> TypedLifecycleBinding:
    return TypedLifecycleBinding(
        lifecycle=value.lifecycle,
        replacement_candidate_ref=(
            _opaque_ref("candidate", value.replacement_candidate_ref, namespace)
            if value.replacement_candidate_ref
            else None
        ),
        replaces_candidate_refs=[
            _opaque_ref("candidate", item, namespace)
            for item in value.replaces_candidate_refs
        ],
        supersedes_candidate_refs=[
            _opaque_ref("candidate", item, namespace)
            for item in value.supersedes_candidate_refs
        ],
        conflicts_with_candidate_refs=[
            _opaque_ref("candidate", item, namespace)
            for item in value.conflicts_with_candidate_refs
        ],
    )


def _remap_operations(
    value: TypedOperationProvenance,
    namespace: str = OPAQUE_NAMESPACE,
) -> TypedOperationProvenance:
    return TypedOperationProvenance(
        confirmed_by_operation_refs=[
            _opaque_ref("operation", item, namespace)
            for item in value.confirmed_by_operation_refs
        ],
        added_by_operation_refs=[
            _opaque_ref("operation", item, namespace)
            for item in value.added_by_operation_refs
        ],
    )


def _remap_untyped(
    value: L2DiagnosticUntypedCandidate,
    namespace: str = OPAQUE_NAMESPACE,
) -> PublicUntypedCandidate:
    evidence = []
    for item in value.evidence:
        payload = item.model_dump(mode="json")
        payload["evidence_id"] = _opaque_ref(
            "evidence", item.evidence_id, namespace
        )
        evidence.append(payload)
    return PublicUntypedCandidate(
        statement=value.statement,
        subject=value.subject,
        predicate=value.predicate,
        object=value.object,
        qualifiers=value.qualifiers,
        source_status=value.source_status,
        derivation=value.derivation,
        inference_basis=value.inference_basis,
        projection_status="active",
        lifecycle_links=TypedLifecycleBinding(lifecycle="active"),
        operation_provenance=TypedOperationProvenance(),
        evidence=evidence,
    )


def _remap_support(
    value: L2DiagnosticL1Support,
    private_session_id: str,
    namespace: str = OPAQUE_NAMESPACE,
) -> TypedL1SupportCandidate:
    return TypedL1SupportCandidate(
        support_ref=_opaque_ref("support", value.private_support_id, namespace),
        source_turn_ref=_opaque_ref("turn", value.private_turn_id, namespace),
        source_session_ref=_opaque_ref("session", private_session_id, namespace),
        kind=value.kind,
        predicate=value.predicate,
        local_entities=value.local_entities,
        roles=value.roles,
        modality=value.modality,
        polarity=value.polarity,
        time=value.time,
        evidence_bindings=[
            _remap_evidence(item, namespace) for item in value.evidence_bindings
        ],
    )


def _remap_candidate(
    value: L2DiagnosticCandidate,
    namespace: str = OPAQUE_NAMESPACE,
) -> TypedL2Candidate:
    return TypedL2Candidate(
        kind=value.kind,
        summary=value.summary,
        supporting_l1_refs=[
            _opaque_ref("support", item, namespace)
            for item in value.supporting_l1_refs
        ],
        structured_claims=[
            TypedL2StructuredClaim(
                claim_ref=claim.claim_ref,
                predicate=claim.predicate,
                local_entities=claim.local_entities,
                roles=claim.roles,
                modality=claim.modality,
                polarity=claim.polarity,
                time=claim.time,
                supporting_l1_refs=[
                    _opaque_ref("support", item, namespace)
                    for item in claim.supporting_l1_refs
                ],
            )
            for claim in value.structured_claims
        ],
        abstraction=value.abstraction,
        closure=TypedL2Closure(
            pattern=value.closure.pattern,
            required_support_refs=[
                _opaque_ref("support", item, namespace)
                for item in value.closure.required_support_refs
            ],
            optional_support_refs=[
                _opaque_ref("support", item, namespace)
                for item in value.closure.optional_support_refs
            ],
        ),
        source_turn_refs=[
            _opaque_ref("turn", item, namespace) for item in value.source_turn_refs
        ],
        source_session_refs=[
            _opaque_ref("session", item, namespace)
            for item in value.source_session_refs
        ],
        evidence_bindings=[
            _remap_evidence(item, namespace) for item in value.evidence_bindings
        ],
        lifecycle=value.lifecycle,
    )


def _validate_case(case: L2DiagnosticCase) -> None:
    turns = case.source_turns
    turn_ids = [turn.private_turn_id for turn in turns]
    if len(turn_ids) != len(set(turn_ids)):
        raise ValueError("duplicate L2 diagnostic turn ID")
    if [turn.turn_index for turn in turns] != list(range(len(turns))):
        raise ValueError("L2 diagnostic turn indexes must be contiguous")
    turn_by_id = {turn.private_turn_id: turn for turn in turns}
    evidence_by_id: dict[str, PublicEvidenceSpan] = {}
    for evidence in case.untyped_candidate.evidence:
        matching = [
            item
            for item in turns
            if getattr(item, evidence.message)[evidence.start : evidence.end]
            == evidence.quote
        ]
        if len(matching) != 1:
            raise ValueError("L2 diagnostic evidence offset is not uniquely resolved")
        message = getattr(matching[0], evidence.message)
        positions: list[int] = []
        offset = 0
        while True:
            position = message.find(evidence.quote, offset)
            if position < 0:
                break
            positions.append(position)
            offset = position + 1
        if (
            evidence.occurrence_index >= len(positions)
            or positions[evidence.occurrence_index] != evidence.start
        ):
            raise ValueError("L2 diagnostic evidence occurrence mismatch")
        if evidence.evidence_id in evidence_by_id:
            raise ValueError("duplicate L2 diagnostic evidence ID")
        evidence_by_id[evidence.evidence_id] = evidence

    supports = case.typed_l1_support_pack
    support_ids = [support.private_support_id for support in supports]
    if len(support_ids) != len(set(support_ids)):
        raise ValueError("duplicate L2 diagnostic support ID")
    support_evidence: list[TypedEvidenceBinding] = []
    for support in supports:
        if support.private_turn_id not in turn_by_id:
            raise ValueError("L2 support references unknown source turn")
        for binding in support.evidence_bindings:
            evidence = evidence_by_id.get(binding.evidence_id)
            if evidence is None or evidence.speaker != binding.speaker:
                raise ValueError("L2 support evidence is not closed to a source span")
            matching_turn = next(
                item
                for item in turns
                if getattr(item, evidence.message)[evidence.start : evidence.end]
                == evidence.quote
            )
            if matching_turn.private_turn_id != support.private_turn_id:
                raise ValueError("L2 support evidence belongs to another turn")
            support_evidence.append(binding)
    if len({item.evidence_id for item in support_evidence}) != len(support_evidence):
        raise ValueError("L2 support evidence must be uniquely owned")

    authority = case.authority
    expected_turn_refs = [turn.private_turn_id for turn in turns]
    if authority.required_support_refs != support_ids:
        raise ValueError("L2 authority support closure differs")
    if authority.required_evidence_bindings != support_evidence:
        raise ValueError("L2 authority evidence closure differs")
    if authority.required_source_turn_refs != expected_turn_refs:
        raise ValueError("L2 authority turn closure differs")
    if authority.required_source_session_refs != [case.private_session_id]:
        raise ValueError("L2 authority session closure differs")

    expected = case.expected_typed_candidate
    if expected is None:
        return
    if expected.supporting_l1_refs != support_ids:
        raise ValueError("L2 gold support closure differs")
    if expected.source_turn_refs != expected_turn_refs:
        raise ValueError("L2 gold turn closure differs")
    if expected.source_session_refs != [case.private_session_id]:
        raise ValueError("L2 gold session closure differs")
    if expected.evidence_bindings != support_evidence:
        raise ValueError("L2 gold evidence closure differs")
    if expected.abstraction.method not in authority.allowed_abstraction_methods:
        raise ValueError("L2 gold abstraction is not authorized")
    if expected.closure.pattern not in authority.allowed_closure_patterns:
        raise ValueError("L2 gold closure is not authorized")
    if expected.summary != case.untyped_candidate.statement:
        raise ValueError("L2 gold summary must preserve the untyped statement surface")
    first_claim = expected.structured_claims[0]
    if first_claim.predicate.surface != case.untyped_candidate.predicate:
        raise ValueError("L2 gold predicate must preserve the untyped surface")
    surfaces = {item.surface for item in first_claim.local_entities}
    required_surfaces = {case.untyped_candidate.subject}
    if case.untyped_candidate.object is not None:
        required_surfaces.add(case.untyped_candidate.object)
    if not required_surfaces.issubset(surfaces):
        raise ValueError("L2 gold claim does not preserve subject/object surfaces")


def _scan_json(value: Any) -> tuple[set[str], set[str], set[str]]:
    identifiers: set[str] = set()
    evidence_ids: set[str] = set()
    evidence_text: set[str] = set()

    def visit(node: Any, key: str | None = None) -> None:
        if isinstance(node, dict):
            for child_key, child in node.items():
                visit(child, child_key)
            return
        if isinstance(node, list):
            for child in node:
                visit(child, key)
            return
        if not isinstance(node, str) or key is None:
            return
        if key in {"evidence_id", "evidence_ids"}:
            evidence_ids.add(node)
        elif key in {
            "case_id",
            "candidate_ref",
            "private_case_id",
            "knowledge_id",
            "candidate_id",
            "support_ref",
            "supporting_l1_refs",
            "required_support_refs",
            "optional_support_refs",
            "source_turn_ref",
            "source_turn_refs",
            "source_session_ref",
            "source_session_refs",
            "replacement_candidate_ref",
            "replaces_candidate_refs",
            "supersedes_candidate_refs",
            "conflicts_with_candidate_refs",
            "confirmed_by_operation_refs",
            "added_by_operation_refs",
        }:
            identifiers.add(node)
        elif key in {"quote", "user", "agent"}:
            evidence_text.add(node)

    visit(value)
    return identifiers, evidence_ids, evidence_text


def _prior_inventory(
    prior_roots: Sequence[Path],
) -> tuple[set[str], set[str], set[str], dict[str, str], dict[str, str]]:
    identifiers: set[str] = set()
    evidence_ids: set[str] = set()
    evidence_text: set[str] = set()
    fingerprints: dict[str, str] = {}
    l1_hashes: dict[str, str] = {}
    l1_roots = 0
    for index, root_value in enumerate(prior_roots):
        root = root_value.resolve()
        if not root.is_dir():
            raise FileNotFoundError(f"prior root missing: {root}")
        l1_names = (
            "diagnostic-source-l1.json",
            "public-l1.json",
            "authority-l1.json",
            "gold-l1.json",
            "manifest-l1.json",
        )
        is_l1_root = all((root / name).is_file() for name in l1_names)
        paths = (
            sorted(root / name for name in l1_names)
            if is_l1_root
            else sorted(path for path in root.rglob("*.json") if path.is_file())
        )
        if not paths:
            raise ValueError(f"prior root has no JSON artifacts: {root}")
        digest = hashlib.sha256()
        for path in paths:
            relative = path.relative_to(root).as_posix().encode()
            content = path.read_bytes()
            digest.update(len(relative).to_bytes(8, "big"))
            digest.update(relative)
            digest.update(len(content).to_bytes(8, "big"))
            digest.update(content)
            found_ids, found_evidence, found_text = _scan_json(load_json(path))
            identifiers.update(found_ids)
            evidence_ids.update(found_evidence)
            evidence_text.update(found_text)
        fingerprints[f"prior_root_{index:02d}"] = digest.hexdigest()
        if is_l1_root:
            l1_roots += 1
            l1_hashes = {name: sha256_file(root / name) for name in l1_names}
    if l1_roots != 1:
        raise ValueError("exactly one L1 diagnostic root must be bound")
    return identifiers, evidence_ids, evidence_text, fingerprints, l1_hashes


def _owned_inventory(
    source: L2DiagnosticSource,
    namespace: str,
) -> tuple[set[str], set[str], set[str]]:
    identifiers: set[str] = set()
    evidence_ids: set[str] = set()
    evidence_text: set[str] = set()
    for case in source.cases:
        identifiers.update(
            {
                case.private_case_id,
                case.private_session_id,
                case.authority.knowledge_id,
                case.authority.candidate_id,
                _opaque_ref("case", case.private_case_id, namespace),
                _opaque_ref("candidate", case.private_case_id, namespace),
                _opaque_ref("session", case.private_session_id, namespace),
            }
        )
        for turn in case.source_turns:
            identifiers.update(
                {
                    turn.private_turn_id,
                    _opaque_ref("turn", turn.private_turn_id, namespace),
                }
            )
            evidence_text.update({turn.user, turn.agent})
        for support in case.typed_l1_support_pack:
            identifiers.update(
                {
                    support.private_support_id,
                    _opaque_ref("support", support.private_support_id, namespace),
                }
            )
        for evidence in case.untyped_candidate.evidence:
            evidence_ids.update(
                {
                    evidence.evidence_id,
                    _opaque_ref("evidence", evidence.evidence_id, namespace),
                }
            )
            evidence_text.add(evidence.quote)
    return identifiers, evidence_ids, evidence_text


def _build(
    source_path: Path,
    prior_roots: Sequence[Path],
) -> tuple[
    L2PublicPayload,
    L2AuthorityPayload,
    L2GoldPayload,
    dict[str, Any],
    dict[str, str],
    dict[str, str],
]:
    source_path = source_path.resolve()
    _require_read_only(source_path, "L2 diagnostic source")
    source = L2DiagnosticSource.model_validate(load_json(source_path))
    namespace = _OPAQUE_NAMESPACES[source.dataset_id]
    for case in source.cases:
        _validate_case(case)

    prior_ids, prior_evidence, prior_text, prior_hashes, l1_hashes = _prior_inventory(
        prior_roots
    )
    owned_ids, owned_evidence, owned_text = _owned_inventory(source, namespace)
    if owned_ids & prior_ids:
        raise ValueError("prior identifier overlap detected")
    if (owned_evidence & prior_evidence) | (owned_text & prior_text):
        raise ValueError("prior evidence overlap detected")

    public_cases: list[L2PublicCase] = []
    authority_cases: list[L2AuthorityCase] = []
    gold_items: list[L2GoldItem] = []
    for case in source.cases:
        case_id = _opaque_ref("case", case.private_case_id, namespace)
        candidate_ref = _opaque_ref("candidate", case.private_case_id, namespace)
        session_ref = _opaque_ref("session", case.private_session_id, namespace)
        supports = [
            _remap_support(item, case.private_session_id, namespace)
            for item in case.typed_l1_support_pack
        ]
        expected = (
            _remap_candidate(case.expected_typed_candidate, namespace)
            if case.expected_typed_candidate
            else None
        )
        public_cases.append(
            L2PublicCase(
                case_id=case_id,
                candidate_ref=candidate_ref,
                source_session_ref=session_ref,
                source_turns=[
                    L2PublicTurn(
                        source_turn_ref=_opaque_ref(
                            "turn", turn.private_turn_id, namespace
                        ),
                        turn_index=turn.turn_index,
                        user=turn.user,
                        agent=turn.agent,
                    )
                    for turn in case.source_turns
                ],
                untyped_candidate=_remap_untyped(case.untyped_candidate, namespace),
                typed_l1_support_pack=supports,
            )
        )
        authority = case.authority
        authority_cases.append(
            L2AuthorityCase(
                case_id=case_id,
                candidate_ref=candidate_ref,
                knowledge_id=authority.knowledge_id,
                candidate_id=authority.candidate_id,
                emission_allowed=authority.emission_allowed,
                required_support_refs=[
                    _opaque_ref("support", item, namespace)
                    for item in authority.required_support_refs
                ],
                required_evidence_bindings=[
                    _remap_evidence(item, namespace)
                    for item in authority.required_evidence_bindings
                ],
                required_source_turn_refs=[
                    _opaque_ref("turn", item, namespace)
                    for item in authority.required_source_turn_refs
                ],
                required_source_session_refs=[
                    _opaque_ref("session", item, namespace)
                    for item in authority.required_source_session_refs
                ],
                allowed_abstraction_methods=authority.allowed_abstraction_methods,
                allowed_closure_patterns=authority.allowed_closure_patterns,
                unresolved_required_fields=authority.unresolved_required_fields,
                automatic_write_authorizations=AutomaticWriteAuthorizations(),
            )
        )
        gold_items.append(
            L2GoldItem(
                case_id=case_id,
                candidate_ref=candidate_ref,
                expected_decision=case.expected_decision,
                expected_typed_candidate=expected,
            )
        )

    emitted = [
        case.expected_typed_candidate
        for case in source.cases
        if case.expected_typed_candidate is not None
    ]
    method_counts = Counter(item.abstraction.method for item in emitted)
    expected_methods = {
        "coreference_resolution": 2,
        "lifecycle_resolution": 2,
        "preference_aggregation": 1,
        "state_summary": 1,
        "task_composition": 2,
    }
    if dict(sorted(method_counts.items())) != expected_methods:
        raise ValueError("L2 diagnostic abstraction distribution differs")
    kind_counts = Counter(item.kind for item in emitted)
    distribution = {
        "provenance": source.provenance,
        "emit_count": len(emitted),
        "abstain_count": sum(
            case.expected_decision == "abstain" for case in source.cases
        ),
        "abstraction_method_counts": dict(sorted(method_counts.items())),
        "kind_counts": dict(sorted(kind_counts.items())),
        "non_task_kind_count": sum(item.kind != "task" for item in emitted),
        "prior_identifier_overlap_count": 0,
        "prior_evidence_overlap_count": 0,
    }
    if distribution["emit_count"] != 8 or distribution["abstain_count"] != 4:
        raise ValueError("L2 diagnostic decision distribution differs")
    if kind_counts.get("long_running_state") != 1:
        raise ValueError("L2 diagnostic state summary kind is missing")
    if kind_counts.get("preference_profile") != 1:
        raise ValueError("L2 diagnostic preference profile kind is missing")

    public = L2PublicPayload(
        dataset_id=source.dataset_id,
        case_count=len(public_cases),
        allowed_vocabulary={**_BASE_VOCABULARY, **source.public_vocabulary},
        cases=public_cases,
    )
    authority_payload = L2AuthorityPayload(
        dataset_id=source.dataset_id,
        case_count=len(authority_cases),
        cases=authority_cases,
    )
    gold = L2GoldPayload(
        dataset_id=source.dataset_id,
        case_count=len(gold_items),
        items=gold_items,
    )
    return (
        public,
        authority_payload,
        gold,
        distribution,
        prior_hashes,
        l1_hashes,
    )


def _manifest(
    *,
    source_path: Path,
    public: L2PublicPayload,
    authority: L2AuthorityPayload,
    gold: L2GoldPayload,
    distribution: dict[str, Any],
    prior_hashes: dict[str, str],
    l1_hashes: dict[str, str],
    output_root: Path,
) -> L2Manifest:
    output_names = ("authority-l2.json", "gold-l2.json", "public-l2.json")
    return L2Manifest(
        dataset_id=public.dataset_id,
        case_count=public.case_count,
        input_sha256={
            "diagnostic_source": sha256_file(source_path),
            **prior_hashes,
        },
        l1_qualification_sha256=l1_hashes,
        output_sha256={
            name: sha256_file(output_root / name) for name in output_names
        },
        distribution=distribution,
        thresholds=dict(L2_DEV_THRESHOLDS),
        claim_boundary={
            "automatic_authoritative_writes": False,
            "diagnostic_only": True,
            "embedding_authority": False,
            "fresh_hidden_v2_created": False,
            "longmemeval_status": "structured_l2_identity_unresolved",
        },
    )


def prepare_l2_dev_repair_slice(
    source_path: Path,
    output_root: Path,
    prior_roots: Sequence[Path],
) -> dict[str, Any]:
    source_path = source_path.resolve()
    output_root = output_root.resolve()
    public, authority, gold, distribution, prior_hashes, l1_hashes = _build(
        source_path,
        prior_roots,
    )
    outputs = {
        "authority-l2.json": authority,
        "gold-l2.json": gold,
        "public-l2.json": public,
    }
    for name, payload in outputs.items():
        write_json_immutable(output_root / name, payload)
    manifest = _manifest(
        source_path=source_path,
        public=public,
        authority=authority,
        gold=gold,
        distribution=distribution,
        prior_hashes=prior_hashes,
        l1_hashes=l1_hashes,
        output_root=output_root,
    )
    write_json_immutable(output_root / "manifest-l2.json", manifest)
    for name in (*outputs, "manifest-l2.json"):
        (output_root / name).chmod(0o444)
    return {"status": "valid", "case_count": public.case_count, **distribution}


def validate_l2_dev_repair_slice(
    source_path: Path,
    root: Path,
    prior_roots: Sequence[Path],
) -> dict[str, Any]:
    source_path = source_path.resolve()
    root = root.resolve()
    public, authority, gold, distribution, prior_hashes, l1_hashes = _build(
        source_path,
        prior_roots,
    )
    expected_outputs = {
        "authority-l2.json": authority,
        "gold-l2.json": gold,
        "public-l2.json": public,
    }
    for name, expected in expected_outputs.items():
        path = root / name
        _require_read_only(path, name)
        if path.read_bytes() != canonical_json_bytes(expected):
            raise ValueError(f"typed L2 diagnostic artifact drift: {name}")
    manifest_path = root / "manifest-l2.json"
    _require_read_only(manifest_path, "manifest-l2.json")
    actual = L2Manifest.model_validate(load_json(manifest_path))
    expected_manifest = _manifest(
        source_path=source_path,
        public=public,
        authority=authority,
        gold=gold,
        distribution=distribution,
        prior_hashes=prior_hashes,
        l1_hashes=l1_hashes,
        output_root=root,
    )
    if canonical_json_bytes(actual) != canonical_json_bytes(expected_manifest):
        raise ValueError("typed L2 diagnostic manifest drift")
    return {"status": "valid", "case_count": public.case_count, **distribution}
