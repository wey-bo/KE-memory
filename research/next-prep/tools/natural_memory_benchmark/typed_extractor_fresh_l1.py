from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .frozen_input_guard import require_frozen_input
from .extraction_bridge_assessment import (
    ExtractionCompatibilityLedger,
    replay_extraction_inputs,
)
from .io import canonical_json_bytes, load_json, sha256_file, write_json_immutable
from .typed_extractor_fresh_prereg import (
    L1_STRATA,
    TypedExtractorFreshPreregistration,
)
from .typed_extractor_l1 import (
    L1AuthorityCase,
    L1AuthorityPayload,
    L1GoldItem,
    L1GoldPayload,
    L1Manifest,
    L1PublicCase,
    L1PublicPayload,
    L1SourceConfig,
    PublicEvidenceSpan,
    PublicUntypedCandidate,
    TypedDerivationProvenance,
    TypedEvidenceBinding,
    TypedLifecycleBinding,
    TypedOperationProvenance,
    _ALLOWED_VOCABULARY,
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


L1Stratum = Literal[
    "ordinary_explicit",
    "non_explicit_derivation",
    "condition_bearing",
    "scope_bearing",
    "non_active_lifecycle",
    "time_bearing",
    "negative_or_control",
]


class FreshL1SourceCase(StrictModel):
    private_case_id: str = Field(pattern=r"^private-[0-9a-f]{16}$")
    case_id: str = Field(pattern=r"^case-[0-9a-f]{16}$")
    candidate_ref: str = Field(pattern=r"^candidate-[0-9a-f]{16}$")
    knowledge_id: str = Field(min_length=1)
    candidate_id: str = Field(min_length=1)
    stratum: L1Stratum
    selection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    turn_index: int = Field(ge=0)
    evidence_ids: list[str] = Field(min_length=1)
    source_turn: dict[Literal["user", "agent"], str]
    untyped_candidate: PublicUntypedCandidate

    @model_validator(mode="after")
    def validate_evidence_ids(self) -> "FreshL1SourceCase":
        public_ids = [item.evidence_id for item in self.untyped_candidate.evidence]
        if self.evidence_ids != public_ids:
            raise ValueError("source evidence IDs must match the untyped candidate")
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("duplicate source evidence ID")
        return self


class FreshL1SourcePayload(StrictModel):
    schema_version: Literal["typed-extractor-fresh-l1-source-v1"] = (
        "typed-extractor-fresh-l1-source-v1"
    )
    dataset_id: Literal["typed-extractor-v2-fresh-hidden-v1-l1"] = (
        "typed-extractor-v2-fresh-hidden-v1-l1"
    )
    namespace: Literal["typed-extractor-l1-fresh-hidden-v1:2026-07-28"] = (
        "typed-extractor-l1-fresh-hidden-v1:2026-07-28"
    )
    selection_phase: Literal["frozen_before_gold"] = "frozen_before_gold"
    semantic_filtering_applied: Literal[False] = False
    case_count: Literal[24] = 24
    strata: dict[str, int]
    preregistration_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    cases: list[FreshL1SourceCase]

    @model_validator(mode="after")
    def validate_selection(self) -> "FreshL1SourcePayload":
        if self.strata != L1_STRATA:
            raise ValueError("fresh L1 source strata mismatch")
        if len(self.cases) != self.case_count:
            raise ValueError("fresh L1 source case count mismatch")
        for field in ("private_case_id", "case_id", "candidate_ref", "knowledge_id"):
            values = [getattr(case, field) for case in self.cases]
            if len(values) != len(set(values)):
                raise ValueError(f"duplicate fresh L1 {field}")
        counts = {name: 0 for name in L1_STRATA}
        for case in self.cases:
            counts[case.stratum] += 1
            expected = hashlib.sha256(
                f"{self.namespace}{case.knowledge_id}".encode()
            ).hexdigest()
            if case.selection_sha256 != expected:
                raise ValueError("fresh L1 selection hash mismatch")
        if counts != self.strata:
            raise ValueError("fresh L1 selected stratum distribution mismatch")
        return self


def _require_read_only(path: Path, label: str) -> None:
    """Verify a committed input portably.

    Content-based rather than mode-based: git records only the executable bit, so
    a 0444 input arrives as 0644 and a mode precondition rejects correct files on
    every fresh clone. Mode is retained only for freshly written output -- see
    ``frozen_input_guard``.
    """
    require_frozen_input(path, label)


def _selection_hash(namespace: str, knowledge_id: str) -> str:
    return hashlib.sha256(f"{namespace}{knowledge_id}".encode()).hexdigest()


def _opaque_ref(prefix: str, namespace: str, value: str) -> str:
    digest = hashlib.sha256(f"{namespace}|{prefix}|{value}".encode()).hexdigest()
    return f"{prefix}-{digest[:16]}"


def _speaker(message: str, evidence_role: str) -> str:
    value = {
        ("user", "user_reported"): "user",
        ("agent", "agent_generated"): "assistant",
        ("agent", "tool_observed"): "tool",
    }.get((message, evidence_role))
    if value is None:
        raise ValueError("unsupported evidence speaker binding")
    return value


def _lifecycle(record: Any, namespace: str) -> TypedLifecycleBinding:
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
            _opaque_ref("candidate", namespace, record.replacement_id)
            if record.replacement_id
            else None
        ),
        replaces_candidate_refs=[
            _opaque_ref("candidate", namespace, item) for item in record.replaces
        ],
        supersedes_candidate_refs=[
            _opaque_ref("candidate", namespace, item) for item in record.supersedes
        ],
        conflicts_with_candidate_refs=[
            _opaque_ref("candidate", namespace, item) for item in record.conflicts_with
        ],
    )


def _operations(record: Any, namespace: str) -> TypedOperationProvenance:
    return TypedOperationProvenance(
        confirmed_by_operation_refs=[
            _opaque_ref("operation", namespace, item) for item in record.confirmed_by
        ],
        added_by_operation_refs=[
            _opaque_ref("operation", namespace, item) for item in record.added_by
        ],
    )


def _is_negative_or_control(record: Any) -> bool:
    if record.knowledge["source_status"] != "agent_generated":
        return False
    quotes = " ".join(str(item["quote"]).strip() for item in record.knowledge["evidence"])
    return any(marker in quotes for marker in ("?", "？", "请确认"))


def _eligible_for(record: Any, stratum: str) -> bool:
    qualifiers = record.knowledge["qualifiers"]
    if stratum == "ordinary_explicit":
        return (
            record.knowledge["derivation"] == "explicit"
            and record.status == "active"
            and not qualifiers.get("conditions")
            and not qualifiers.get("scope")
            and not qualifiers.get("temporal")
            and not _is_negative_or_control(record)
        )
    if stratum == "non_explicit_derivation":
        return record.knowledge["derivation"] != "explicit"
    if stratum == "condition_bearing":
        return bool(qualifiers.get("conditions"))
    if stratum == "scope_bearing":
        return bool(qualifiers.get("scope"))
    if stratum == "non_active_lifecycle":
        return record.status != "active"
    if stratum == "time_bearing":
        return bool(qualifiers.get("temporal"))
    if stratum == "negative_or_control":
        return _is_negative_or_control(record)
    raise ValueError(f"unknown fresh L1 stratum: {stratum}")


def _verify_preregistration_inputs(
    preregistration_path: Path,
    preregistration: TypedExtractorFreshPreregistration,
    *,
    bridge_ledger_path: Path,
    l1_dev_root: Path,
    source_path: Path,
    turn_manifest_path: Path,
    dialogue_manifest_path: Path,
    final_knowledge_path: Path,
    run_path: Path,
    source_segments_path: Path,
) -> None:
    _require_read_only(preregistration_path, "fresh preregistration")
    paths = {
        "bridge-v3/compatibility-ledger.json": bridge_ledger_path,
        "l1/source-cases-l1.json": l1_dev_root / "source-cases-l1.json",
        "l1/public-l1.json": l1_dev_root / "public-l1.json",
        "source/KE-test.json": source_path,
        "source/turn-manifest.json": turn_manifest_path,
        "source/dialogue-manifest.json": dialogue_manifest_path,
        "source/final-knowledge.json": final_knowledge_path,
        "source/run.json": run_path,
        "source/source-segments.json": source_segments_path,
    }
    for name, path in paths.items():
        expected = preregistration.input_sha256.get(name)
        if expected is None or sha256_file(path) != expected:
            raise ValueError(f"fresh preregistration input drift: {name}")


def _build_source(
    *,
    preregistration_path: Path,
    bridge_ledger_path: Path,
    l1_dev_root: Path,
    source_path: Path,
    turn_manifest_path: Path,
    dialogue_manifest_path: Path,
    final_knowledge_path: Path,
    run_path: Path,
    source_segments_path: Path,
) -> FreshL1SourcePayload:
    preregistration = TypedExtractorFreshPreregistration.model_validate(
        load_json(preregistration_path)
    )
    _verify_preregistration_inputs(
        preregistration_path,
        preregistration,
        bridge_ledger_path=bridge_ledger_path,
        l1_dev_root=l1_dev_root,
        source_path=source_path,
        turn_manifest_path=turn_manifest_path,
        dialogue_manifest_path=dialogue_manifest_path,
        final_knowledge_path=final_knowledge_path,
        run_path=run_path,
        source_segments_path=source_segments_path,
    )
    namespace = preregistration.selection.l1_namespace
    if preregistration.selection.l1_strata != L1_STRATA:
        raise ValueError("fresh L1 preregistered strata drift")
    ledger = ExtractionCompatibilityLedger.model_validate(load_json(bridge_ledger_path))
    envelopes = {item.knowledge_id: item for item in ledger.envelopes}
    replay = replay_extraction_inputs(
        source_path=source_path,
        turn_manifest_path=turn_manifest_path,
        dialogue_manifest_path=dialogue_manifest_path,
        final_knowledge_path=final_knowledge_path,
        run_path=run_path,
        source_segments_path=source_segments_path,
    )
    dev_source = load_json(l1_dev_root / "source-cases-l1.json")
    dev_authority = load_json(l1_dev_root / "authority-l1.json")
    dev_ids = {str(item["knowledge_id"]) for item in dev_source["cases"]}
    dev_evidence = {
        str(binding["evidence_id"])
        for item in dev_authority["cases"]
        for binding in item["required_evidence_bindings"]
    }
    available: dict[str, Any] = {}
    for record in replay.view.by_id.values():
        evidence = record.knowledge["evidence"]
        evidence_ids = {str(item["evidence_id"]) for item in evidence}
        envelope = envelopes.get(record.knowledge_id)
        if (
            envelope is None
            or envelope.candidate_level != "l1_single_turn_candidate"
            or record.knowledge_id in dev_ids
            or evidence_ids & dev_evidence
            or len({int(item["turn_index"]) for item in evidence}) != 1
        ):
            continue
        available[record.knowledge_id] = record

    selected: list[tuple[str, Any]] = []
    for stratum in preregistration.selection.l1_priority_order:
        count = L1_STRATA[stratum]
        candidates = sorted(
            (record for record in available.values() if _eligible_for(record, stratum)),
            key=lambda record: _selection_hash(namespace, record.knowledge_id),
        )
        if stratum == "ordinary_explicit":
            chosen: list[Any] = []
            statuses = sorted(
                {record.knowledge["source_status"] for record in candidates}
            )
            for status in statuses:
                chosen.append(
                    next(
                        record
                        for record in candidates
                        if record.knowledge["source_status"] == status
                    )
                )
            chosen.extend(
                record
                for record in candidates
                if record not in chosen
            )
            chosen = sorted(chosen[:count], key=lambda record: _selection_hash(
                namespace, record.knowledge_id
            ))
        else:
            chosen = candidates[:count]
        if len(chosen) != count:
            raise ValueError(f"fresh L1 stratum cannot be filled: {stratum}")
        for record in chosen:
            available.pop(record.knowledge_id)
            selected.append((stratum, record))

    cases: list[FreshL1SourceCase] = []
    for stratum, record in selected:
        turn_index = next(
            iter({int(item["turn_index"]) for item in record.knowledge["evidence"]})
        )
        source_turn = replay.source_turns[(record.candidate_id, turn_index)]
        evidence = [
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
        selection_hash = _selection_hash(namespace, record.knowledge_id)
        cases.append(
            FreshL1SourceCase(
                private_case_id=f"private-{selection_hash[:16]}",
                case_id=_opaque_ref("case", namespace, record.knowledge_id),
                candidate_ref=_opaque_ref("candidate", namespace, record.knowledge_id),
                knowledge_id=record.knowledge_id,
                candidate_id=record.candidate_id,
                stratum=stratum,
                selection_sha256=selection_hash,
                turn_index=turn_index,
                evidence_ids=[item.evidence_id for item in evidence],
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
                    lifecycle_links=_lifecycle(record, namespace),
                    operation_provenance=_operations(record, namespace),
                    evidence=evidence,
                ),
            )
        )
    return FreshL1SourcePayload(
        strata=dict(L1_STRATA),
        preregistration_sha256=sha256_file(preregistration_path),
        cases=cases,
    )


def _resolve_paths(**paths: Path) -> dict[str, Path]:
    return {name: path.resolve() for name, path in paths.items()}


def freeze_fresh_l1_selection(
    *,
    preregistration_path: Path,
    bridge_ledger_path: Path,
    l1_dev_root: Path,
    source_path: Path,
    turn_manifest_path: Path,
    dialogue_manifest_path: Path,
    final_knowledge_path: Path,
    run_path: Path,
    source_segments_path: Path,
    output_root: Path,
) -> dict[str, Any]:
    paths = _resolve_paths(
        preregistration_path=preregistration_path,
        bridge_ledger_path=bridge_ledger_path,
        l1_dev_root=l1_dev_root,
        source_path=source_path,
        turn_manifest_path=turn_manifest_path,
        dialogue_manifest_path=dialogue_manifest_path,
        final_knowledge_path=final_knowledge_path,
        run_path=run_path,
        source_segments_path=source_segments_path,
    )
    source = _build_source(**paths)
    output_path = output_root.resolve() / "source-cases-l1.json"
    write_json_immutable(output_path, source)
    output_path.chmod(0o444)
    return {
        "status": "valid",
        "case_count": source.case_count,
        "selection_phase": source.selection_phase,
        "strata": dict(source.strata),
    }


def validate_fresh_l1_selection(
    *,
    preregistration_path: Path,
    bridge_ledger_path: Path,
    l1_dev_root: Path,
    source_path: Path,
    turn_manifest_path: Path,
    dialogue_manifest_path: Path,
    final_knowledge_path: Path,
    run_path: Path,
    source_segments_path: Path,
    root: Path,
) -> dict[str, Any]:
    paths = _resolve_paths(
        preregistration_path=preregistration_path,
        bridge_ledger_path=bridge_ledger_path,
        l1_dev_root=l1_dev_root,
        source_path=source_path,
        turn_manifest_path=turn_manifest_path,
        dialogue_manifest_path=dialogue_manifest_path,
        final_knowledge_path=final_knowledge_path,
        run_path=run_path,
        source_segments_path=source_segments_path,
    )
    expected = _build_source(**paths)
    source_path_out = root.resolve() / "source-cases-l1.json"
    _require_read_only(source_path_out, "fresh L1 source selection")
    actual = FreshL1SourcePayload.model_validate(load_json(source_path_out))
    if canonical_json_bytes(actual) != canonical_json_bytes(expected):
        raise ValueError("fresh L1 source selection drift")
    return {
        "status": "valid",
        "case_count": actual.case_count,
        "selection_phase": actual.selection_phase,
    }


def _build_final_artifacts(
    source: FreshL1SourcePayload,
    adjudications: L1SourceConfig,
) -> tuple[L1PublicPayload, L1AuthorityPayload, L1GoldPayload, dict[str, Any]]:
    if adjudications.dataset_id != source.dataset_id:
        raise ValueError("fresh L1 adjudication dataset mismatch")
    source_by_private = {case.private_case_id: case for case in source.cases}
    adjudication_by_private = {
        case.private_case_id: case for case in adjudications.cases
    }
    if set(source_by_private) != set(adjudication_by_private):
        raise ValueError("fresh L1 adjudications must cover the exact frozen selection")
    for private_id, source_case in source_by_private.items():
        if adjudication_by_private[private_id].knowledge_id != source_case.knowledge_id:
            raise ValueError("fresh L1 adjudication knowledge ID mismatch")

    vocabulary_overlap = set(adjudications.public_vocabulary) & set(
        _ALLOWED_VOCABULARY
    )
    if vocabulary_overlap:
        raise ValueError("fresh L1 vocabulary cannot override base vocabulary")
    public_cases: list[L1PublicCase] = []
    authority_cases: list[L1AuthorityCase] = []
    gold_items: list[L1GoldItem] = []
    decision_counts = {"emit_l1": 0, "abstain": 0, "no_memory": 0}
    kinds: set[str] = set()

    for source_case in source.cases:
        adjudication = adjudication_by_private[source_case.private_case_id]
        untyped = source_case.untyped_candidate
        evidence_bindings = [
            TypedEvidenceBinding(
                evidence_id=item.evidence_id,
                speaker=item.speaker,
            )
            for item in untyped.evidence
        ]
        derivation = TypedDerivationProvenance(
            method=untyped.derivation,
            basis=untyped.inference_basis,
            evidence_ids=[item.evidence_id for item in evidence_bindings],
        )
        expected = adjudication.expected_typed_candidate
        if expected is not None:
            if expected.predicate.surface != untyped.predicate:
                raise ValueError("fresh L1 gold predicate surface must copy public input")
            if expected.evidence_bindings != evidence_bindings:
                raise ValueError("fresh L1 gold evidence does not match frozen selection")
            if expected.derivation != derivation:
                raise ValueError("fresh L1 gold derivation does not match frozen selection")
            if expected.lifecycle != untyped.lifecycle_links:
                raise ValueError("fresh L1 gold lifecycle does not match frozen selection")
            if expected.operation_provenance != untyped.operation_provenance:
                raise ValueError("fresh L1 gold operations do not match frozen selection")
            if [item.value for item in expected.condition_bindings] != list(
                untyped.qualifiers.get("conditions", [])
            ):
                raise ValueError("fresh L1 gold conditions do not match public input")
            if [item.value for item in expected.scope_bindings] != list(
                untyped.qualifiers.get("scope", [])
            ):
                raise ValueError("fresh L1 gold scope does not match public input")
            if expected.modality not in adjudication.allowed_modalities:
                raise ValueError("fresh L1 gold modality is outside authority")
            if expected.polarity != untyped.qualifiers["polarity"]:
                raise ValueError("fresh L1 gold polarity does not match public input")
            if expected.time.event_time is None:
                if not adjudication.event_time_may_be_null:
                    raise ValueError("fresh L1 gold event time is required")
            elif expected.time.event_time not in adjudication.allowed_event_times:
                raise ValueError("fresh L1 gold event time is outside authority")
            if expected.time.valid_time is None:
                if not adjudication.valid_time_may_be_null:
                    raise ValueError("fresh L1 gold valid time is required")
            elif expected.time.valid_time not in adjudication.allowed_valid_times:
                raise ValueError("fresh L1 gold valid time is outside authority")
            kinds.add(expected.kind)

        public_cases.append(
            L1PublicCase(
                case_id=source_case.case_id,
                candidate_ref=source_case.candidate_ref,
                source_turn=source_case.source_turn,
                untyped_candidate=untyped,
            )
        )
        authority_cases.append(
            L1AuthorityCase(
                case_id=source_case.case_id,
                candidate_ref=source_case.candidate_ref,
                knowledge_id=source_case.knowledge_id,
                candidate_id=source_case.candidate_id,
                emission_allowed=adjudication.emission_allowed,
                required_evidence_bindings=evidence_bindings,
                allowed_modalities=adjudication.allowed_modalities,
                allowed_polarities=[untyped.qualifiers["polarity"]],
                allowed_event_times=adjudication.allowed_event_times,
                event_time_may_be_null=adjudication.event_time_may_be_null,
                allowed_valid_times=adjudication.allowed_valid_times,
                valid_time_may_be_null=adjudication.valid_time_may_be_null,
                allowed_condition_values=list(
                    untyped.qualifiers.get("conditions", [])
                ),
                allowed_scope_values=list(untyped.qualifiers.get("scope", [])),
                required_derivation=derivation,
                required_lifecycle=untyped.lifecycle_links,
                required_operation_provenance=untyped.operation_provenance,
                unresolved_required_fields=adjudication.unresolved_required_fields,
            )
        )
        gold_items.append(
            L1GoldItem(
                case_id=source_case.case_id,
                candidate_ref=source_case.candidate_ref,
                expected_decision=adjudication.expected_decision,
                expected_typed_candidate=expected,
            )
        )
        decision_counts[adjudication.expected_decision] += 1

    public = L1PublicPayload(
        dataset_id=source.dataset_id,
        case_count=source.case_count,
        allowed_vocabulary={
            **_ALLOWED_VOCABULARY,
            **adjudications.public_vocabulary,
        },
        cases=public_cases,
    )
    authority = L1AuthorityPayload(
        dataset_id=source.dataset_id,
        case_count=source.case_count,
        cases=authority_cases,
    )
    gold = L1GoldPayload(
        dataset_id=source.dataset_id,
        case_count=source.case_count,
        items=gold_items,
    )
    distribution = {
        "selection_strata": dict(source.strata),
        "decision_counts": decision_counts,
        "kind_coverage": sorted(kinds),
    }
    return public, authority, gold, distribution


def _manifest_input_sha256(
    *,
    preregistration_path: Path,
    prompt_path: Path,
    bridge_ledger_path: Path,
    l1_dev_root: Path,
    source_path: Path,
    turn_manifest_path: Path,
    dialogue_manifest_path: Path,
    final_knowledge_path: Path,
    run_path: Path,
    source_segments_path: Path,
    selection_root: Path,
) -> dict[str, str]:
    return {
        "adjudications": sha256_file(selection_root / "adjudications-l1.json"),
        "bridge_ledger": sha256_file(bridge_ledger_path),
        "dev_authority": sha256_file(l1_dev_root / "authority-l1.json"),
        "dev_source": sha256_file(l1_dev_root / "source-cases-l1.json"),
        "dialogue_manifest": sha256_file(dialogue_manifest_path),
        "final_knowledge": sha256_file(final_knowledge_path),
        "preregistration": sha256_file(preregistration_path),
        "prompt": sha256_file(prompt_path),
        "run": sha256_file(run_path),
        "selection_source": sha256_file(selection_root / "source-cases-l1.json"),
        "source": sha256_file(source_path),
        "source_segments": sha256_file(source_segments_path),
        "turn_manifest": sha256_file(turn_manifest_path),
    }


def _build_manifest(
    *,
    public: L1PublicPayload,
    distribution: dict[str, Any],
    paths: dict[str, Path],
) -> L1Manifest:
    root = paths["selection_root"]
    return L1Manifest(
        dataset_id=public.dataset_id,
        case_count=public.case_count,
        input_sha256=_manifest_input_sha256(**paths),
        output_sha256={
            name: sha256_file(root / name)
            for name in ("authority-l1.json", "gold-l1.json", "public-l1.json")
        },
        distribution=distribution,
        claim_boundary={
            "automatic_authoritative_writes": False,
            "embedding_authority": False,
            "fresh_hidden_created": True,
            "longmemeval_status": "structured_l2_identity_unresolved",
            "raw_gold_authored_after_selection": True,
        },
    )


def prepare_fresh_l1_slice(
    *,
    preregistration_path: Path,
    prompt_path: Path,
    bridge_ledger_path: Path,
    l1_dev_root: Path,
    source_path: Path,
    turn_manifest_path: Path,
    dialogue_manifest_path: Path,
    final_knowledge_path: Path,
    run_path: Path,
    source_segments_path: Path,
    selection_root: Path,
    adjudication_path: Path,
) -> dict[str, Any]:
    paths = _resolve_paths(
        preregistration_path=preregistration_path,
        prompt_path=prompt_path,
        bridge_ledger_path=bridge_ledger_path,
        l1_dev_root=l1_dev_root,
        source_path=source_path,
        turn_manifest_path=turn_manifest_path,
        dialogue_manifest_path=dialogue_manifest_path,
        final_knowledge_path=final_knowledge_path,
        run_path=run_path,
        source_segments_path=source_segments_path,
        selection_root=selection_root,
    )
    validate_fresh_l1_selection(
        **{
            key: value
            for key, value in paths.items()
            if key not in {"prompt_path", "selection_root"}
        },
        root=paths["selection_root"],
    )
    _require_read_only(paths["prompt_path"], "fresh L1 prompt")
    preregistration = TypedExtractorFreshPreregistration.model_validate(
        load_json(paths["preregistration_path"])
    )
    if sha256_file(paths["prompt_path"]) != preregistration.input_sha256[
        "l1/proposer-prompt-l1.md"
    ]:
        raise ValueError("fresh L1 prompt drift")
    source = FreshL1SourcePayload.model_validate(
        load_json(paths["selection_root"] / "source-cases-l1.json")
    )
    adjudication_path = adjudication_path.resolve()
    _require_read_only(adjudication_path, "fresh L1 adjudications")
    adjudications = L1SourceConfig.model_validate(load_json(adjudication_path))
    public, authority, gold, distribution = _build_final_artifacts(
        source, adjudications
    )
    root = paths["selection_root"]
    outputs: dict[str, BaseModel] = {
        "adjudications-l1.json": adjudications,
        "public-l1.json": public,
        "authority-l1.json": authority,
        "gold-l1.json": gold,
    }
    for name, payload in outputs.items():
        write_json_immutable(root / name, payload)
        (root / name).chmod(0o444)
    manifest = _build_manifest(public=public, distribution=distribution, paths=paths)
    write_json_immutable(root / "manifest-l1.json", manifest)
    (root / "manifest-l1.json").chmod(0o444)
    return {
        "status": "valid",
        "case_count": public.case_count,
        "raw_gold_authored_after_selection": True,
        **distribution,
    }


def validate_fresh_l1_slice(
    *,
    preregistration_path: Path,
    prompt_path: Path,
    bridge_ledger_path: Path,
    l1_dev_root: Path,
    source_path: Path,
    turn_manifest_path: Path,
    dialogue_manifest_path: Path,
    final_knowledge_path: Path,
    run_path: Path,
    source_segments_path: Path,
    root: Path,
) -> dict[str, Any]:
    paths = _resolve_paths(
        preregistration_path=preregistration_path,
        prompt_path=prompt_path,
        bridge_ledger_path=bridge_ledger_path,
        l1_dev_root=l1_dev_root,
        source_path=source_path,
        turn_manifest_path=turn_manifest_path,
        dialogue_manifest_path=dialogue_manifest_path,
        final_knowledge_path=final_knowledge_path,
        run_path=run_path,
        source_segments_path=source_segments_path,
        selection_root=root,
    )
    validate_fresh_l1_selection(
        **{
            key: value
            for key, value in paths.items()
            if key not in {"prompt_path", "selection_root"}
        },
        root=paths["selection_root"],
    )
    for name in (
        "adjudications-l1.json",
        "public-l1.json",
        "authority-l1.json",
        "gold-l1.json",
        "manifest-l1.json",
    ):
        _require_read_only(paths["selection_root"] / name, name)
    source = FreshL1SourcePayload.model_validate(
        load_json(paths["selection_root"] / "source-cases-l1.json")
    )
    adjudications = L1SourceConfig.model_validate(
        load_json(paths["selection_root"] / "adjudications-l1.json")
    )
    public, authority, gold, distribution = _build_final_artifacts(
        source, adjudications
    )
    expected_outputs = {
        "public-l1.json": public,
        "authority-l1.json": authority,
        "gold-l1.json": gold,
    }
    for name, expected in expected_outputs.items():
        if (paths["selection_root"] / name).read_bytes() != canonical_json_bytes(expected):
            raise ValueError(f"fresh L1 artifact drift: {name}")
    actual_manifest = L1Manifest.model_validate(
        load_json(paths["selection_root"] / "manifest-l1.json")
    )
    expected_manifest = _build_manifest(
        public=public,
        distribution=distribution,
        paths=paths,
    )
    if canonical_json_bytes(actual_manifest) != canonical_json_bytes(expected_manifest):
        raise ValueError("fresh L1 manifest drift")
    return {
        "status": "valid",
        "case_count": public.case_count,
        "raw_gold_authored_after_selection": True,
    }
