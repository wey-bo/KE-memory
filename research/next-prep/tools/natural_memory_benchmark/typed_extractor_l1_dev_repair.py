from __future__ import annotations

import hashlib
from collections import Counter
from pathlib import Path
from typing import Any, Literal, Sequence

from pydantic import Field, model_validator

from .io import canonical_json_bytes, load_json, sha256_file, write_json_immutable
from .typed_extractor_l1 import (
    AutomaticWriteAuthorizations,
    L1AuthorityCase,
    L1AuthorityPayload,
    L1Decision,
    L1GoldItem,
    L1GoldPayload,
    L1Manifest,
    L1PublicCase,
    L1PublicPayload,
    PublicUntypedCandidate,
    StrictModel,
    TypedDerivationProvenance,
    TypedEvidenceBinding,
    TypedL1Candidate,
    TypedLifecycleBinding,
    TypedModality,
    TypedOperationProvenance,
    TypedPolarity,
)


L1RepairFamily = Literal[
    "false_emission",
    "false_abstention",
    "evidence",
    "condition_or_scope",
    "time",
    "role_or_local_entity",
    "lifecycle",
    "modality_or_polarity",
    "derivation_or_speaker",
    "predicate_or_operator",
    "kind",
    "operation_provenance",
]


DATASET_ID = "typed-extractor-l1-dev-repair-v1"
OPAQUE_NAMESPACE = "typed-extractor-l1-dev-repair-v1:2026-07-28"
_OPAQUE_NAMESPACES = {
    "typed-extractor-l1-dev-repair-v1": OPAQUE_NAMESPACE,
    "typed-extractor-l1-dev-repair-v2": (
        "typed-extractor-l1-dev-repair-v2:2026-07-28"
    ),
}

_L1_V6_REQUIRED_CATALOGS = {
    "canonical_operators",
    "condition_operators",
    "modality_policy",
    "operator_kind_bindings",
    "operator_role_bindings",
    "operator_time_bindings",
    "predicate_senses",
    "scope_operators",
    "time_policy",
}

EXPECTED_L1_PRIMARY_COUNTS: dict[str, int] = {
    "condition_or_scope": 2,
    "derivation_or_speaker": 1,
    "evidence": 2,
    "false_abstention": 3,
    "false_emission": 2,
    "lifecycle": 1,
    "modality_or_polarity": 1,
    "role_or_local_entity": 2,
    "time": 2,
}

_EXPECTED_CASES = (
    ("control-question-no-durable-fact", "false_emission"),
    ("control-instruction-no-state", "false_emission"),
    ("unsupported-modal-rumor", "modality_or_polarity"),
    ("insufficient-evidence-attribution", "evidence"),
    ("valid-user-state", "false_abstention"),
    ("valid-requested-task", "false_abstention"),
    ("valid-tool-event", "false_abstention"),
    ("evidence-same-speaker-distractor", "evidence"),
    ("evidence-cross-speaker-distractor", "derivation_or_speaker"),
    ("condition-explicit-approver", "condition_or_scope"),
    ("scope-explicit-project", "condition_or_scope"),
    ("resolved-calendar-valid-time", "time"),
    ("unresolved-deictic-time", "time"),
    ("role-two-people-transfer", "role_or_local_entity"),
    ("role-agent-versus-beneficiary", "role_or_local_entity"),
    ("lifecycle-correction-confirmation", "lifecycle"),
)

_BASE_VOCABULARY = {
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

_ALL_FAMILIES = {
    "false_emission",
    "false_abstention",
    "evidence",
    "condition_or_scope",
    "time",
    "role_or_local_entity",
    "lifecycle",
    "modality_or_polarity",
    "derivation_or_speaker",
    "predicate_or_operator",
    "kind",
    "operation_provenance",
}


class L1DiagnosticAuthority(StrictModel):
    knowledge_id: str = Field(min_length=1)
    candidate_id: str = Field(min_length=1)
    emission_allowed: bool
    required_evidence_bindings: list[TypedEvidenceBinding] = Field(min_length=1)
    allowed_modalities: list[TypedModality] = Field(default_factory=list)
    allowed_polarities: list[TypedPolarity] = Field(default_factory=list)
    allowed_event_times: list[str] = Field(default_factory=list)
    event_time_may_be_null: bool = True
    allowed_valid_times: list[str] = Field(default_factory=list)
    valid_time_may_be_null: bool = True
    allowed_condition_values: list[str] = Field(default_factory=list)
    allowed_scope_values: list[str] = Field(default_factory=list)
    required_derivation: TypedDerivationProvenance
    required_lifecycle: TypedLifecycleBinding
    required_operation_provenance: TypedOperationProvenance
    unresolved_required_fields: list[str] = Field(default_factory=list)


class L1DiagnosticCase(StrictModel):
    private_case_id: str = Field(min_length=1)
    primary_family: L1RepairFamily
    secondary_families: list[L1RepairFamily] = Field(default_factory=list)
    source_turn: dict[Literal["user", "agent"], str]
    untyped_candidate: PublicUntypedCandidate
    expected_decision: L1Decision
    expected_typed_candidate: TypedL1Candidate | None = None
    authority: L1DiagnosticAuthority

    @model_validator(mode="after")
    def validate_case_contract(self) -> "L1DiagnosticCase":
        if set(self.source_turn) != {"user", "agent"}:
            raise ValueError("source turn must contain exactly user and agent")
        if len(self.secondary_families) != len(set(self.secondary_families)):
            raise ValueError("duplicate secondary family")
        if self.primary_family in self.secondary_families:
            raise ValueError("primary family cannot be repeated as secondary")
        emits = self.expected_decision == "emit_l1"
        if emits != (self.expected_typed_candidate is not None):
            raise ValueError("expected decision and typed candidate disagree")
        if emits != self.authority.emission_allowed:
            raise ValueError("expected decision and emission authority disagree")
        if emits and not self.authority.allowed_modalities:
            raise ValueError("emission authority requires an allowed modality")
        return self


class L1DiagnosticSource(StrictModel):
    schema_version: Literal[
        "typed-extractor-l1-diagnostic-source-v1",
        "typed-extractor-l1-diagnostic-source-v2",
    ]
    dataset_id: Literal[
        "typed-extractor-l1-dev-repair-v1",
        "typed-extractor-l1-dev-repair-v2",
    ]
    provenance: Literal["diagnostic_authored"]
    public_vocabulary: dict[str, list[str]]
    cases: list[L1DiagnosticCase]

    @model_validator(mode="after")
    def validate_source_contract(self) -> "L1DiagnosticSource":
        version = self.schema_version.rsplit("-", 1)[-1]
        if not self.dataset_id.endswith(f"-{version}"):
            raise ValueError("L1 diagnostic schema and dataset versions differ")
        if version == "v2":
            missing_catalogs = _L1_V6_REQUIRED_CATALOGS - set(
                _BASE_VOCABULARY | self.public_vocabulary
            )
            if missing_catalogs:
                raise ValueError(
                    "missing L1 V6 public catalogs: "
                    + ", ".join(sorted(missing_catalogs))
                )
        if len(self.cases) != 16:
            raise ValueError("L1 diagnostic source must contain exactly 16 cases")
        private_ids = [case.private_case_id for case in self.cases]
        if len(private_ids) != len(set(private_ids)):
            raise ValueError("duplicate private case ID")
        case_pairs = tuple(
            (case.private_case_id, case.primary_family) for case in self.cases
        )
        if case_pairs != _EXPECTED_CASES:
            raise ValueError("L1 diagnostic case IDs or primary families differ")
        knowledge_ids = [case.authority.knowledge_id for case in self.cases]
        candidate_ids = [case.authority.candidate_id for case in self.cases]
        if len(knowledge_ids) != len(set(knowledge_ids)):
            raise ValueError("duplicate diagnostic knowledge ID")
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("duplicate diagnostic candidate ID")
        primary_counts = Counter(case.primary_family for case in self.cases)
        if dict(sorted(primary_counts.items())) != EXPECTED_L1_PRIMARY_COUNTS:
            raise ValueError("L1 diagnostic primary-family distribution differs")
        if set(self.public_vocabulary) & set(_BASE_VOCABULARY):
            raise ValueError("public vocabulary cannot override base vocabulary")
        for key, values in self.public_vocabulary.items():
            if not key or not values or len(values) != len(set(values)):
                raise ValueError("public vocabulary entries must be unique and non-empty")
        if version == "v2":
            vocabulary = {**_BASE_VOCABULARY, **self.public_vocabulary}
            canonical_operators = set(vocabulary["canonical_operators"])
            predicate_senses = set(vocabulary["predicate_senses"])
            kind_bindings = set(vocabulary["operator_kind_bindings"])
            role_bindings = set(vocabulary["operator_role_bindings"])
            condition_operators = set(vocabulary["condition_operators"])
            scope_operators = set(vocabulary["scope_operators"])
            time_bindings = set(vocabulary["operator_time_bindings"])
            for case in self.cases:
                candidate = case.expected_typed_candidate
                if candidate is None:
                    continue
                operator = candidate.predicate.canonical_operator
                if (
                    operator not in canonical_operators
                    or candidate.predicate.sense not in predicate_senses
                    or f"{operator}|{candidate.kind}" not in kind_bindings
                ):
                    raise ValueError(
                        "L1 V6 public catalog does not cover emitted candidate: "
                        "L1 V6 operator-kind catalog mismatch"
                    )
                expected_roles = {
                    f"{operator}|{role.role}|{role.role_name}"
                    for role in candidate.roles
                }
                if not expected_roles.issubset(role_bindings):
                    raise ValueError(
                        "L1 V6 public catalog does not cover emitted candidate: "
                        "L1 V6 operator-role catalog mismatch"
                    )
                if not {
                    binding.operator for binding in candidate.condition_bindings
                }.issubset(condition_operators):
                    raise ValueError("L1 V6 condition-operator catalog mismatch")
                if not {
                    binding.operator for binding in candidate.scope_bindings
                }.issubset(scope_operators):
                    raise ValueError("L1 V6 scope-operator catalog mismatch")
                qualifiers = case.untyped_candidate.qualifiers
                if candidate.time.valid_time is not None and (
                    f"{operator}|valid_time_from_object_iso_8601"
                    not in time_bindings
                ):
                    raise ValueError("L1 V6 operator-time catalog mismatch")
                has_unresolved_time = (
                    candidate.time.event_time is None
                    and ("event_time" in qualifiers or "time" in qualifiers)
                )
                if has_unresolved_time and (
                    f"{operator}|unresolved_deictic_event_time_to_null"
                    not in time_bindings
                ):
                    raise ValueError("L1 V6 operator-time catalog mismatch")
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


def _remap_lifecycle(
    value: TypedLifecycleBinding,
    namespace: str = OPAQUE_NAMESPACE,
) -> TypedLifecycleBinding:
    def one(item: str | None) -> str | None:
        return _opaque_ref("candidate", item, namespace) if item else None

    return TypedLifecycleBinding(
        lifecycle=value.lifecycle,
        replacement_candidate_ref=one(value.replacement_candidate_ref),
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


def _remap_evidence_binding(
    value: TypedEvidenceBinding,
    namespace: str = OPAQUE_NAMESPACE,
) -> TypedEvidenceBinding:
    return TypedEvidenceBinding(
        evidence_id=_opaque_ref("evidence", value.evidence_id, namespace),
        speaker=value.speaker,
    )


def _remap_derivation(
    value: TypedDerivationProvenance,
    namespace: str = OPAQUE_NAMESPACE,
) -> TypedDerivationProvenance:
    return TypedDerivationProvenance(
        method=value.method,
        basis=value.basis,
        evidence_ids=[
            _opaque_ref("evidence", item, namespace) for item in value.evidence_ids
        ],
    )


def _remap_typed_candidate(
    value: TypedL1Candidate,
    namespace: str = OPAQUE_NAMESPACE,
) -> TypedL1Candidate:
    payload = value.model_dump(mode="json")
    payload["evidence_bindings"] = [
        _remap_evidence_binding(item, namespace).model_dump(mode="json")
        for item in value.evidence_bindings
    ]
    payload["derivation"] = _remap_derivation(value.derivation, namespace).model_dump(
        mode="json"
    )
    payload["lifecycle"] = _remap_lifecycle(value.lifecycle, namespace).model_dump(
        mode="json"
    )
    payload["operation_provenance"] = _remap_operations(
        value.operation_provenance,
        namespace,
    ).model_dump(mode="json")
    return TypedL1Candidate.model_validate(payload)


def _remap_untyped_candidate(
    value: PublicUntypedCandidate,
    namespace: str = OPAQUE_NAMESPACE,
) -> PublicUntypedCandidate:
    payload = value.model_dump(mode="json")
    for evidence in payload["evidence"]:
        evidence["evidence_id"] = _opaque_ref(
            "evidence", evidence["evidence_id"], namespace
        )
    payload["lifecycle_links"] = _remap_lifecycle(
        value.lifecycle_links, namespace
    ).model_dump(mode="json")
    payload["operation_provenance"] = _remap_operations(
        value.operation_provenance,
        namespace,
    ).model_dump(mode="json")
    return PublicUntypedCandidate.model_validate(payload)


def _validate_evidence(case: L1DiagnosticCase) -> None:
    evidence_by_id: dict[str, TypedEvidenceBinding] = {}
    for evidence in case.untyped_candidate.evidence:
        message = case.source_turn[evidence.message]
        if message[evidence.start : evidence.end] != evidence.quote:
            raise ValueError(f"evidence offset mismatch: {case.private_case_id}")
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
            raise ValueError(f"evidence occurrence mismatch: {case.private_case_id}")
        if evidence.evidence_id in evidence_by_id:
            raise ValueError("duplicate evidence ID within diagnostic case")
        evidence_by_id[evidence.evidence_id] = TypedEvidenceBinding(
            evidence_id=evidence.evidence_id,
            speaker=evidence.speaker,
        )
    required = case.authority.required_evidence_bindings
    for binding in required:
        if evidence_by_id.get(binding.evidence_id) != binding:
            raise ValueError("required evidence is not an exact public evidence span")
    expected = case.expected_typed_candidate
    if expected is not None:
        if expected.evidence_bindings != required:
            raise ValueError("gold and authority evidence bindings differ")
        if expected.derivation != case.authority.required_derivation:
            raise ValueError("gold and authority derivation differ")
        if expected.lifecycle != case.authority.required_lifecycle:
            raise ValueError("gold and authority lifecycle differ")
        if expected.operation_provenance != case.authority.required_operation_provenance:
            raise ValueError("gold and authority operation provenance differ")
        if expected.modality not in case.authority.allowed_modalities:
            raise ValueError("gold modality is not authorized")
        if expected.polarity not in case.authority.allowed_polarities:
            raise ValueError("gold polarity is not authorized")
        if {item.value for item in expected.condition_bindings} - set(
            case.authority.allowed_condition_values
        ):
            raise ValueError("gold condition is not authorized")
        if {item.value for item in expected.scope_bindings} - set(
            case.authority.allowed_scope_values
        ):
            raise ValueError("gold scope is not authorized")


def _owned_identifiers(source: L1DiagnosticSource, namespace: str) -> set[str]:
    values: set[str] = set()
    for case in source.cases:
        values.update(
            {
                case.private_case_id,
                case.authority.knowledge_id,
                case.authority.candidate_id,
                _opaque_ref("case", case.private_case_id, namespace),
                _opaque_ref("candidate", case.private_case_id, namespace),
            }
        )
        lifecycle_values = (
            case.untyped_candidate.lifecycle_links.replaces_candidate_refs
            + case.untyped_candidate.lifecycle_links.supersedes_candidate_refs
            + case.untyped_candidate.lifecycle_links.conflicts_with_candidate_refs
        )
        if case.untyped_candidate.lifecycle_links.replacement_candidate_ref:
            lifecycle_values.append(
                case.untyped_candidate.lifecycle_links.replacement_candidate_ref
            )
        for value in lifecycle_values:
            values.add(value)
            values.add(_opaque_ref("candidate", value, namespace))
        operations = case.untyped_candidate.operation_provenance
        for value in (
            operations.confirmed_by_operation_refs + operations.added_by_operation_refs
        ):
            values.add(value)
            values.add(_opaque_ref("operation", value, namespace))
    return values


def _owned_evidence(
    source: L1DiagnosticSource,
    namespace: str,
) -> tuple[set[str], set[str]]:
    evidence_ids: set[str] = set()
    evidence_text: set[str] = set()
    for case in source.cases:
        for evidence in case.untyped_candidate.evidence:
            evidence_ids.add(evidence.evidence_id)
            evidence_ids.add(_opaque_ref("evidence", evidence.evidence_id, namespace))
            evidence_text.add(evidence.quote)
        evidence_text.update(case.source_turn.values())
    return evidence_ids, evidence_text


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
        if key == "evidence_id" or key == "evidence_ids":
            evidence_ids.add(node)
        elif key in {
            "case_id",
            "candidate_ref",
            "private_case_id",
            "knowledge_id",
            "candidate_id",
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
) -> tuple[set[str], set[str], set[str], dict[str, str]]:
    identifiers: set[str] = set()
    evidence_ids: set[str] = set()
    evidence_text: set[str] = set()
    fingerprints: dict[str, str] = {}
    for index, root in enumerate(prior_roots):
        root = root.resolve()
        if not root.is_dir():
            raise FileNotFoundError(f"prior root missing: {root}")
        digest = hashlib.sha256()
        paths = sorted(path for path in root.rglob("*.json") if path.is_file())
        if not paths:
            raise ValueError(f"prior root has no JSON artifacts: {root}")
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
    return identifiers, evidence_ids, evidence_text, fingerprints


def _build(
    source_path: Path,
    prior_roots: Sequence[Path],
) -> tuple[L1PublicPayload, L1AuthorityPayload, L1GoldPayload, dict[str, Any], dict[str, str]]:
    source_path = source_path.resolve()
    _require_read_only(source_path, "L1 diagnostic source")
    source = L1DiagnosticSource.model_validate(load_json(source_path))
    namespace = _OPAQUE_NAMESPACES[source.dataset_id]
    for case in source.cases:
        _validate_evidence(case)

    source_evidence_ids = [
        evidence.evidence_id
        for case in source.cases
        for evidence in case.untyped_candidate.evidence
    ]
    if len(source_evidence_ids) != len(set(source_evidence_ids)):
        raise ValueError("duplicate evidence ID across diagnostic cases")

    prior_ids, prior_evidence, prior_text, prior_hashes = _prior_inventory(prior_roots)
    owned_ids = _owned_identifiers(source, namespace)
    owned_evidence_ids, owned_evidence_text = _owned_evidence(source, namespace)
    identifier_overlap = owned_ids & prior_ids
    if identifier_overlap:
        raise ValueError("prior identifier overlap detected")
    evidence_overlap = (owned_evidence_ids & prior_evidence) | (
        owned_evidence_text & prior_text
    )
    if evidence_overlap:
        raise ValueError("prior evidence overlap detected")

    public_cases: list[L1PublicCase] = []
    authority_cases: list[L1AuthorityCase] = []
    gold_items: list[L1GoldItem] = []
    for case in source.cases:
        case_id = _opaque_ref("case", case.private_case_id, namespace)
        candidate_ref = _opaque_ref("candidate", case.private_case_id, namespace)
        expected = (
            _remap_typed_candidate(case.expected_typed_candidate, namespace)
            if case.expected_typed_candidate
            else None
        )
        public_cases.append(
            L1PublicCase(
                case_id=case_id,
                candidate_ref=candidate_ref,
                source_turn=case.source_turn,
                untyped_candidate=_remap_untyped_candidate(
                    case.untyped_candidate, namespace
                ),
            )
        )
        authority = case.authority
        authority_cases.append(
            L1AuthorityCase(
                case_id=case_id,
                candidate_ref=candidate_ref,
                knowledge_id=authority.knowledge_id,
                candidate_id=authority.candidate_id,
                emission_allowed=authority.emission_allowed,
                required_evidence_bindings=[
                    _remap_evidence_binding(item, namespace)
                    for item in authority.required_evidence_bindings
                ],
                allowed_modalities=authority.allowed_modalities,
                allowed_polarities=authority.allowed_polarities,
                allowed_event_times=authority.allowed_event_times,
                event_time_may_be_null=authority.event_time_may_be_null,
                allowed_valid_times=authority.allowed_valid_times,
                valid_time_may_be_null=authority.valid_time_may_be_null,
                allowed_condition_values=authority.allowed_condition_values,
                allowed_scope_values=authority.allowed_scope_values,
                required_derivation=_remap_derivation(
                    authority.required_derivation, namespace
                ),
                required_lifecycle=_remap_lifecycle(
                    authority.required_lifecycle, namespace
                ),
                required_operation_provenance=_remap_operations(
                    authority.required_operation_provenance,
                    namespace,
                ),
                unresolved_required_fields=authority.unresolved_required_fields,
                automatic_write_authorizations=AutomaticWriteAuthorizations(),
            )
        )
        gold_items.append(
            L1GoldItem(
                case_id=case_id,
                candidate_ref=candidate_ref,
                expected_decision=case.expected_decision,
                expected_typed_candidate=expected,
            )
        )

    family_opportunities = Counter()
    for case in source.cases:
        family_opportunities.update({case.primary_family, *case.secondary_families})
    missing = _ALL_FAMILIES - set(family_opportunities)
    undercovered = {
        family: count
        for family, count in family_opportunities.items()
        if count < 2
    }
    if missing or undercovered:
        raise ValueError("L1 diagnostic family opportunities are incomplete")

    decision_counts = Counter(case.expected_decision for case in source.cases)
    distribution = {
        "provenance": source.provenance,
        "primary_family_counts": dict(
            sorted(Counter(case.primary_family for case in source.cases).items())
        ),
        "family_opportunity_counts": dict(sorted(family_opportunities.items())),
        "decision_counts": dict(sorted(decision_counts.items())),
        "non_emission_count": sum(
            case.expected_decision != "emit_l1" for case in source.cases
        ),
        "prior_identifier_overlap_count": 0,
        "prior_evidence_overlap_count": 0,
    }
    if distribution["non_emission_count"] != 4:
        raise ValueError("L1 diagnostic source requires four non-emissions")

    public = L1PublicPayload(
        dataset_id=source.dataset_id,
        case_count=len(public_cases),
        allowed_vocabulary={**_BASE_VOCABULARY, **source.public_vocabulary},
        cases=public_cases,
    )
    authority_payload = L1AuthorityPayload(
        dataset_id=source.dataset_id,
        case_count=len(authority_cases),
        cases=authority_cases,
    )
    gold = L1GoldPayload(
        dataset_id=source.dataset_id,
        case_count=len(gold_items),
        items=gold_items,
    )
    return public, authority_payload, gold, distribution, prior_hashes


def _manifest(
    *,
    source_path: Path,
    prior_hashes: dict[str, str],
    public: L1PublicPayload,
    authority: L1AuthorityPayload,
    gold: L1GoldPayload,
    distribution: dict[str, Any],
    output_root: Path,
) -> L1Manifest:
    output_names = ("authority-l1.json", "gold-l1.json", "public-l1.json")
    return L1Manifest(
        dataset_id=public.dataset_id,
        case_count=public.case_count,
        input_sha256={
            "diagnostic_source": sha256_file(source_path),
            **prior_hashes,
        },
        output_sha256={
            name: sha256_file(output_root / name) for name in output_names
        },
        distribution=distribution,
        claim_boundary={
            "automatic_authoritative_writes": False,
            "diagnostic_only": True,
            "embedding_authority": False,
            "fresh_hidden_v2_created": False,
            "longmemeval_status": "structured_l2_identity_unresolved",
        },
    )


def prepare_l1_dev_repair_slice(
    source_path: Path,
    output_root: Path,
    prior_roots: Sequence[Path],
) -> dict[str, Any]:
    source_path = source_path.resolve()
    output_root = output_root.resolve()
    public, authority, gold, distribution, prior_hashes = _build(
        source_path,
        prior_roots,
    )
    outputs = {
        "authority-l1.json": authority,
        "gold-l1.json": gold,
        "public-l1.json": public,
    }
    for name, payload in outputs.items():
        write_json_immutable(output_root / name, payload)
    manifest = _manifest(
        source_path=source_path,
        prior_hashes=prior_hashes,
        public=public,
        authority=authority,
        gold=gold,
        distribution=distribution,
        output_root=output_root,
    )
    write_json_immutable(output_root / "manifest-l1.json", manifest)
    for name in (*outputs, "manifest-l1.json"):
        (output_root / name).chmod(0o444)
    return {"status": "valid", "case_count": public.case_count, **distribution}


def validate_l1_dev_repair_slice(
    source_path: Path,
    root: Path,
    prior_roots: Sequence[Path],
) -> dict[str, Any]:
    source_path = source_path.resolve()
    root = root.resolve()
    public, authority, gold, distribution, prior_hashes = _build(
        source_path,
        prior_roots,
    )
    expected_outputs = {
        "authority-l1.json": authority,
        "gold-l1.json": gold,
        "public-l1.json": public,
    }
    for name, expected in expected_outputs.items():
        path = root / name
        _require_read_only(path, name)
        if path.read_bytes() != canonical_json_bytes(expected):
            raise ValueError(f"typed L1 diagnostic artifact drift: {name}")
    manifest_path = root / "manifest-l1.json"
    _require_read_only(manifest_path, "manifest-l1.json")
    actual = L1Manifest.model_validate(load_json(manifest_path))
    expected_manifest = _manifest(
        source_path=source_path,
        prior_hashes=prior_hashes,
        public=public,
        authority=authority,
        gold=gold,
        distribution=distribution,
        output_root=root,
    )
    if canonical_json_bytes(actual) != canonical_json_bytes(expected_manifest):
        raise ValueError("typed L1 diagnostic manifest drift")
    return {"status": "valid", "case_count": public.case_count, **distribution}
