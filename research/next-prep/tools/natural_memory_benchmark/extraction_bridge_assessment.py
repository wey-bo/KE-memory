from __future__ import annotations

from dataclasses import dataclass
from collections import Counter
import hashlib
from pathlib import Path
from typing import Any, Literal

from knowledge_pipeline.evidence import resolve_evidence
from knowledge_pipeline.projector import FinalKnowledgeView, project_validated_manifests
from knowledge_pipeline.source import TurnUnit, load_turn_units
from pydantic import BaseModel, ConfigDict, Field

from .io import canonical_json_bytes, load_json, sha256_file
from .authoritative_memory import MemoryRepresentationBundleV3, canonical_sha256
from .authoritative_conformance_runner import build_authoritative_conformance_bundle
from .io import write_json_immutable, write_text_immutable


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


CandidateLevel = Literal[
    "l1_single_turn_candidate",
    "l2_cross_turn_candidate",
    "blocked_candidate",
]
MappingStatus = Literal["exact", "normalized", "unsupported", "missing"]


class FieldMapping(StrictModel):
    field: str = Field(min_length=1)
    status: MappingStatus
    source_value: Any | None = None
    target_value: Any | None = None
    reason: str = Field(min_length=1)


class AutomaticWriteClaims(StrictModel):
    l1: Literal[False] = False
    l2: Literal[False] = False
    unit_revision: Literal[False] = False
    closure: Literal[False] = False
    identity: Literal[False] = False
    membership: Literal[False] = False


class ExtractionCompatibilityEnvelope(StrictModel):
    schema_version: Literal["automatic-extraction-compatibility-envelope-v3"] = (
        "automatic-extraction-compatibility-envelope-v3"
    )
    envelope_id: str = Field(min_length=1)
    knowledge_id: str = Field(min_length=1)
    candidate_id: str = Field(min_length=1)
    source_stage: Literal["turn", "dialogue"]
    projection_status: str = Field(min_length=1)
    candidate_level: CandidateLevel
    evidence_ids: list[str] = Field(min_length=1)
    evidence_turns: list[int] = Field(min_length=1)
    mappings: list[FieldMapping] = Field(min_length=1)
    blocking_gaps: list[str] = Field(min_length=1)
    authoritative_materialization_allowed: Literal[False] = False
    automatic_write_claims: AutomaticWriteClaims = Field(
        default_factory=AutomaticWriteClaims
    )


_NORMALIZED_MODALITIES = {
    "asserted": "actual",
    "observed": "actual",
    "planned": "planned",
    "requested": "requested",
    "hypothetical": "hypothetical",
    "advised": "recommended",
}
_UNSUPPORTED_MODALITIES = {
    "possible",
    "preferred",
    "questioned",
    "committed",
    "claimed_completed",
}
_LIFECYCLE_MAP = {
    "active": "active",
    "active_conflict": "conflicted",
    "corrected": "superseded",
    "superseded": "superseded",
}
_L1_REQUIRED_GAPS = {
    "missing_memory_kind",
    "missing_predicate_sense",
    "missing_canonical_operator",
    "missing_typed_role_bindings",
    "missing_local_entity_ids",
}
_L2_REQUIRED_GAPS = {
    "missing_supporting_l1_unit_ids",
    "missing_structured_claim",
    "missing_abstraction_method",
    "missing_closure_specification",
    "missing_source_turn_session_closure",
}
TYPED_EXTRACTOR_V2_REQUIREMENTS = (
    "explicit_level_and_typed_memory_kind",
    "typed_predicate_surface_sense_and_canonical_operator",
    "typed_role_bindings_and_candidate_scoped_local_entity_ids",
    "typed_modality_polarity_and_time_bindings",
    "typed_condition_and_scope_bindings",
    "typed_derivation_and_inference_provenance",
    "typed_evidence_speaker_bindings",
    "exact_evidence_references",
    "explicit_lifecycle_correction_supersession_and_conflict_links",
    "l2_supporting_l1_candidate_ids",
    "l2_structured_claims_and_abstraction_method",
    "l2_closure_pattern_and_source_turn_session_coverage",
    "explicit_abstention_or_no_memory_for_unresolved_required_fields",
)


class ExtractionCompatibilityLedger(StrictModel):
    schema_version: Literal["automatic-extraction-compatibility-ledger-v3"] = (
        "automatic-extraction-compatibility-ledger-v3"
    )
    input_sha256: dict[str, str]
    record_count: int = Field(ge=0)
    envelopes: list[ExtractionCompatibilityEnvelope]


class ExtractionBridgeAssessment(StrictModel):
    schema_version: Literal["automatic-extraction-bridge-assessment-v3"] = (
        "automatic-extraction-bridge-assessment-v3"
    )
    status: Literal["pass"] = "pass"
    raw_extraction_structure: dict[str, Any]
    deterministic_bridge_safety: dict[str, Any]
    guard_state: dict[str, Any]
    typed_extractor_v2_requirements: list[str]
    automatic_extraction_integration_ready: bool
    claim_boundary: dict[str, bool | str]


@dataclass(frozen=True)
class ExtractionReplay:
    view: FinalKnowledgeView
    source_turns: dict[tuple[str, int], TurnUnit]
    operation_candidates: dict[str, str]
    input_sha256: dict[str, str]
    record_count: int
    active_record_count: int


def map_modality(value: str) -> FieldMapping:
    if value in _NORMALIZED_MODALITIES:
        return FieldMapping(
            field="modality",
            status="normalized",
            source_value=value,
            target_value=_NORMALIZED_MODALITIES[value],
            reason="explicit loss-aware modality normalization",
        )
    if value in _UNSUPPORTED_MODALITIES:
        return FieldMapping(
            field="modality",
            status="unsupported",
            source_value=value,
            target_value=None,
            reason="authoritative modality contract has no exact representation",
        )
    return FieldMapping(
        field="modality",
        status="unsupported",
        source_value=value,
        target_value=None,
        reason="unknown extraction modality",
    )


def _semantic_payload(value: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value[key]
        for key in ("schema_version", "active_ids", "counts", "records")
    }


def _expected_provenance_hashes(
    *,
    turn_manifest_path: Path,
    dialogue_manifest_path: Path,
    source_segments_path: Path,
) -> dict[str, str]:
    return {
        "turn_manifest_sha256": sha256_file(turn_manifest_path),
        "dialogue_manifest_sha256": sha256_file(dialogue_manifest_path),
        "source_segments_sha256": sha256_file(source_segments_path),
    }


def _validate_final_projection(
    view: FinalKnowledgeView,
    frozen: dict[str, Any],
    *,
    expected_provenance: dict[str, str],
) -> None:
    replayed = view.to_dict()
    if canonical_json_bytes(_semantic_payload(replayed)) != canonical_json_bytes(
        _semantic_payload(frozen)
    ):
        raise ValueError("final knowledge semantic payload mismatch")
    provenance = frozen.get("provenance")
    if not isinstance(provenance, dict):
        raise ValueError("final knowledge provenance is missing")
    actual = {key: provenance.get(key) for key in expected_provenance}
    if actual != expected_provenance:
        raise ValueError("final knowledge provenance hashes mismatch")


def _validate_run_binding(
    run: dict[str, Any],
    *,
    expected_provenance: dict[str, str],
    final_knowledge_path: Path,
    view: FinalKnowledgeView,
) -> None:
    actual = {
        "turn_manifest_sha256": run.get("turn_pass", {})
        .get("validated_manifest", {})
        .get("sha256"),
        "dialogue_manifest_sha256": run.get("dialogue_pass", {})
        .get("validated_manifest", {})
        .get("sha256"),
        "source_segments_sha256": run.get("source_segments", {}).get("sha256"),
    }
    if actual != expected_provenance:
        raise ValueError("run metadata does not bind extraction inputs")
    projection = run.get("projection")
    if not isinstance(projection, dict):
        raise ValueError("run projection does not bind final knowledge")
    view_payload = view.to_dict()
    expected_projection = {
        "active_count": len(view.active_ids),
        "counts": view_payload["counts"],
        "deterministic_replay": True,
        "dialogue_manifest_sha256": expected_provenance[
            "dialogue_manifest_sha256"
        ],
        "output_sha256": sha256_file(final_knowledge_path),
        "source_segments_sha256": expected_provenance["source_segments_sha256"],
        "status": "projected",
        "turn_manifest_sha256": expected_provenance["turn_manifest_sha256"],
    }
    actual_projection = {key: projection.get(key) for key in expected_projection}
    if actual_projection != expected_projection:
        raise ValueError("run projection does not bind final knowledge")


def _validate_evidence(
    view: FinalKnowledgeView,
    source_turns: dict[tuple[str, int], TurnUnit],
) -> None:
    _validate_evidence_definitions(view)
    knowledge_ids: set[str] = set()
    for record in view.records:
        knowledge = record.knowledge
        knowledge_id = str(knowledge.get("knowledge_id", ""))
        candidate_id = str(knowledge.get("candidate_id", ""))
        if not knowledge_id or knowledge_id in knowledge_ids:
            raise ValueError(f"duplicate or missing knowledge ID: {knowledge_id}")
        knowledge_ids.add(knowledge_id)
        source_status = knowledge.get("source_status")
        evidence_items = knowledge.get("evidence")
        if not isinstance(evidence_items, list) or not evidence_items:
            raise ValueError(f"knowledge {knowledge_id} has no evidence")
        for evidence in evidence_items:
            if not isinstance(evidence, dict):
                raise ValueError(f"knowledge {knowledge_id} has invalid evidence")
            if evidence.get("candidate_id") != candidate_id:
                raise ValueError(f"knowledge {knowledge_id} has cross-candidate evidence")
            turn_index = evidence.get("turn_index")
            if not isinstance(turn_index, int):
                raise ValueError(f"knowledge {knowledge_id} has invalid evidence turn")
            turn = source_turns.get((candidate_id, turn_index))
            if turn is None:
                raise ValueError(f"knowledge {knowledge_id} references an unknown source turn")
            message = evidence.get("message")
            text = turn.user if message == "user" else turn.agent if message == "agent" else None
            if text is None:
                raise ValueError(f"knowledge {knowledge_id} has invalid evidence message")
            expected = resolve_evidence(
                candidate_id=candidate_id,
                turn_index=turn_index,
                text=text,
                message=message,
                quote=evidence.get("quote"),
                occurrence_index=evidence.get("occurrence_index"),
                evidence_role=evidence.get("evidence_role"),
            ).model_dump(mode="json")
            if evidence != expected:
                raise ValueError(f"knowledge {knowledge_id} evidence binding mismatch")
            if evidence.get("evidence_role") != source_status:
                raise ValueError(f"knowledge {knowledge_id} source status mismatch")


def _validate_evidence_definitions(view: FinalKnowledgeView) -> None:
    evidence_definitions: dict[str, bytes] = {}
    for record in view.records:
        for evidence in record.knowledge.get("evidence", []):
            evidence_id = str(evidence.get("evidence_id", ""))
            definition = canonical_json_bytes(evidence)
            prior = evidence_definitions.get(evidence_id)
            if prior is not None and prior != definition:
                raise ValueError(f"conflicting evidence ID reuse: {evidence_id}")
            evidence_definitions[evidence_id] = definition


def _load_operation_candidates(dialogue_manifest_path: Path) -> dict[str, str]:
    manifest = load_json(dialogue_manifest_path)
    if not isinstance(manifest, dict) or not isinstance(manifest.get("candidates"), list):
        raise ValueError("dialogue manifest has invalid candidate entries")
    operation_candidates: dict[str, str] = {}
    for entry in manifest["candidates"]:
        if not isinstance(entry, dict):
            raise ValueError("dialogue manifest has invalid candidate entry")
        candidate_id = entry.get("candidate_id")
        filename = entry.get("validated_file")
        expected_sha256 = entry.get("validated_sha256")
        if (
            not isinstance(candidate_id, str)
            or not candidate_id
            or not isinstance(filename, str)
            or not filename.endswith(".json")
            or not isinstance(expected_sha256, str)
            or len(expected_sha256) != 64
        ):
            raise ValueError("dialogue manifest has invalid operation binding")
        validated_path = dialogue_manifest_path.parent / filename
        if sha256_file(validated_path) != expected_sha256:
            raise ValueError(f"dialogue validated file hash mismatch: {filename}")
        output = load_json(validated_path)
        if not isinstance(output, dict) or output.get("candidate_id") != candidate_id:
            raise ValueError(f"dialogue validated identity mismatch: {filename}")
        operations = output.get("operations")
        if not isinstance(operations, list):
            raise ValueError(f"dialogue validated operations are invalid: {filename}")
        for operation in operations:
            if not isinstance(operation, dict):
                raise ValueError(f"dialogue validated operation is invalid: {filename}")
            operation_id = operation.get("operation_id")
            if not isinstance(operation_id, str) or not operation_id:
                raise ValueError(f"dialogue validated operation has no ID: {filename}")
            if operation.get("candidate_id") != candidate_id:
                raise ValueError(f"dialogue operation candidate mismatch: {operation_id}")
            if operation_id in operation_candidates:
                raise ValueError(f"duplicate dialogue operation ID: {operation_id}")
            operation_candidates[operation_id] = candidate_id
    return operation_candidates


def _validate_projection_candidate_boundaries(
    view: FinalKnowledgeView,
    operation_candidates: dict[str, str],
) -> None:
    candidate_by_knowledge = {
        record.knowledge_id: record.candidate_id for record in view.records
    }
    for record in view.records:
        references = {
            "replacement_id": [record.replacement_id]
            if record.replacement_id is not None
            else [],
            "replaces": list(record.replaces),
            "supersedes": list(record.supersedes),
            "conflicts_with": list(record.conflicts_with),
        }
        for field, values in references.items():
            for referenced_id in values:
                referenced_candidate = candidate_by_knowledge.get(referenced_id)
                if referenced_candidate is None:
                    raise ValueError(
                        f"unknown projection reference: {record.knowledge_id} "
                        f"{field} {referenced_id}"
                    )
                if referenced_candidate != record.candidate_id:
                    raise ValueError(
                        f"cross-candidate projection reference: {record.knowledge_id} "
                        f"{field} {referenced_id}"
                    )
        operation_references = {
            "confirmed_by": list(record.confirmed_by),
            "added_by": list(record.added_by),
        }
        for field, values in operation_references.items():
            for operation_id in values:
                operation_candidate = operation_candidates.get(operation_id)
                if operation_candidate is None:
                    raise ValueError(
                        f"unknown projection operation reference: {record.knowledge_id} "
                        f"{field} {operation_id}"
                    )
                if operation_candidate != record.candidate_id:
                    raise ValueError(
                        f"cross-candidate projection operation: {record.knowledge_id} "
                        f"{field} {operation_id}"
                    )


def replay_extraction_inputs(
    *,
    source_path: Path,
    turn_manifest_path: Path,
    dialogue_manifest_path: Path,
    final_knowledge_path: Path,
    run_path: Path,
    source_segments_path: Path,
) -> ExtractionReplay:
    source_path = source_path.resolve()
    turn_manifest_path = turn_manifest_path.resolve()
    dialogue_manifest_path = dialogue_manifest_path.resolve()
    final_knowledge_path = final_knowledge_path.resolve()
    run_path = run_path.resolve()
    source_segments_path = source_segments_path.resolve()

    view = project_validated_manifests(turn_manifest_path, dialogue_manifest_path)
    frozen = load_json(final_knowledge_path)
    if not isinstance(frozen, dict):
        raise ValueError("final knowledge must be a JSON object")
    expected_provenance = _expected_provenance_hashes(
        turn_manifest_path=turn_manifest_path,
        dialogue_manifest_path=dialogue_manifest_path,
        source_segments_path=source_segments_path,
    )
    _validate_final_projection(view, frozen, expected_provenance=expected_provenance)
    run = load_json(run_path)
    if not isinstance(run, dict):
        raise ValueError("run metadata must be a JSON object")
    _validate_run_binding(
        run,
        expected_provenance=expected_provenance,
        final_knowledge_path=final_knowledge_path,
        view=view,
    )

    turns = load_turn_units(source_path)
    source_turns = {(turn.candidate_id, turn.turn_index): turn for turn in turns}
    if len(source_turns) != len(turns):
        raise ValueError("source turns are not unique")
    operation_candidates = _load_operation_candidates(dialogue_manifest_path)
    _validate_evidence(view, source_turns)
    _validate_projection_candidate_boundaries(view, operation_candidates)

    return ExtractionReplay(
        view=view,
        source_turns=source_turns,
        operation_candidates=operation_candidates,
        input_sha256={
            "dialogue_manifest": sha256_file(dialogue_manifest_path),
            "final_knowledge": sha256_file(final_knowledge_path),
            "run": sha256_file(run_path),
            "source": sha256_file(source_path),
            "source_segments": sha256_file(source_segments_path),
            "turn_manifest": sha256_file(turn_manifest_path),
        },
        record_count=len(view.records),
        active_record_count=len(view.active_ids),
    )


def _mapping(
    field: str,
    *,
    status: MappingStatus,
    source_value: Any,
    target_value: Any,
    reason: str,
) -> FieldMapping:
    return FieldMapping(
        field=field,
        status=status,
        source_value=source_value,
        target_value=target_value,
        reason=reason,
    )


def _candidate_level(record: Any, evidence_turns: list[int]) -> CandidateLevel:
    if not evidence_turns:
        return "blocked_candidate"
    if len(evidence_turns) > 1 or record.added_by:
        return "l2_cross_turn_candidate"
    return "l1_single_turn_candidate"


def _evidence_speaker_bindings(evidence: list[dict[str, Any]]) -> list[dict[str, str]]:
    speakers = {
        ("user", "user_reported"): "user",
        ("agent", "agent_generated"): "assistant",
        ("agent", "tool_observed"): "tool",
    }
    bindings = []
    for item in evidence:
        key = (str(item.get("message")), str(item.get("evidence_role")))
        speaker = speakers.get(key)
        if speaker is None:
            raise ValueError(f"unsupported evidence speaker binding: {key}")
        bindings.append(
            {
                "evidence_id": str(item["evidence_id"]),
                "speaker": speaker,
            }
        )
    return sorted(bindings, key=lambda item: item["evidence_id"])


def _envelope(record: Any) -> ExtractionCompatibilityEnvelope:
    knowledge = record.knowledge
    evidence = knowledge["evidence"]
    evidence_ids = sorted({str(item["evidence_id"]) for item in evidence})
    evidence_turns = sorted({int(item["turn_index"]) for item in evidence})
    level = _candidate_level(record, evidence_turns)
    qualifiers = knowledge["qualifiers"]
    lifecycle = _LIFECYCLE_MAP.get(record.status)
    if lifecycle is None:
        raise ValueError(f"unsupported projection lifecycle: {record.status}")
    replacement_links = {
        "conflicts_with": list(record.conflicts_with),
        "replacement_id": record.replacement_id,
        "replaces": list(record.replaces),
        "supersedes": list(record.supersedes),
    }
    operation_links = {
        "added_by": list(record.added_by),
        "confirmed_by": list(record.confirmed_by),
    }
    mappings = [
        _mapping(
            "evidence",
            status="exact",
            source_value=evidence_ids,
            target_value=evidence_ids,
            reason="validated exact source spans are preserved",
        ),
        _mapping(
            "evidence_speaker_bindings",
            status="exact",
            source_value=[
                {
                    "evidence_id": str(item["evidence_id"]),
                    "evidence_role": str(item["evidence_role"]),
                    "message": str(item["message"]),
                }
                for item in sorted(evidence, key=lambda item: str(item["evidence_id"]))
            ],
            target_value=_evidence_speaker_bindings(evidence),
            reason="message side and evidence role deterministically bind evidence speakers",
        ),
        _mapping(
            "source_status",
            status="exact",
            source_value=knowledge["source_status"],
            target_value=knowledge["source_status"],
            reason="source-status enums are shared",
        ),
        _mapping(
            "polarity",
            status="exact",
            source_value=qualifiers["polarity"],
            target_value=qualifiers["polarity"],
            reason="polarity enums are shared",
        ),
        _mapping(
            "confidence",
            status="exact",
            source_value=knowledge["confidence"],
            target_value=knowledge["confidence"],
            reason="extraction confidence is preserved",
        ),
        _mapping(
            "lifecycle",
            status="normalized" if record.status != lifecycle else "exact",
            source_value=record.status,
            target_value=lifecycle,
            reason="append-only projection lifecycle is preserved",
        ),
        _mapping(
            "replacement_links",
            status="exact",
            source_value=replacement_links,
            target_value=replacement_links,
            reason="explicit correction, supersession, and conflict links are preserved",
        ),
        _mapping(
            "operation_links",
            status="exact",
            source_value=operation_links,
            target_value=operation_links,
            reason="dialogue confirm and add operation provenance is preserved",
        ),
        map_modality(str(qualifiers["modality"])),
        _mapping(
            "memory_kind",
            status="missing",
            source_value=None,
            target_value=None,
            reason="existing extraction has no typed memory kind",
        ),
        _mapping(
            "predicate_sense",
            status="missing",
            source_value=knowledge["predicate"],
            target_value=None,
            reason="free-text predicate is not a typed predicate sense",
        ),
        _mapping(
            "canonical_operator",
            status="missing",
            source_value=knowledge["predicate"],
            target_value=None,
            reason="canonical operator was not extracted",
        ),
        _mapping(
            "typed_role_bindings",
            status="missing",
            source_value={
                "subject": knowledge["subject"],
                "object": knowledge["object"],
            },
            target_value=None,
            reason="free-text subject/object do not define typed roles",
        ),
        _mapping(
            "local_entity_ids",
            status="missing",
            source_value={
                "subject": knowledge["subject"],
                "object": knowledge["object"],
            },
            target_value=None,
            reason="candidate-scoped entity identifiers were not extracted",
        ),
    ]
    gaps = set(_L1_REQUIRED_GAPS)
    modality = map_modality(str(qualifiers["modality"]))
    if modality.status == "unsupported":
        gaps.add("unsupported_modality")
    temporal = list(qualifiers.get("temporal", []))
    if temporal:
        mappings.append(
            _mapping(
                "typed_time_binding",
                status="missing",
                source_value=temporal,
                target_value=None,
                reason="free-text temporal qualifiers are not typed time bindings",
            )
        )
        gaps.add("missing_typed_time_binding")
    else:
        mappings.append(
            _mapping(
                "typed_time_binding",
                status="exact",
                source_value=[],
                target_value={
                    "event_time": None,
                    "transaction_time": None,
                    "valid_time": None,
                },
                reason="record declares no temporal qualifier",
            )
        )
    conditions = list(qualifiers.get("conditions", []))
    if conditions:
        mappings.append(
            _mapping(
                "typed_condition_bindings",
                status="missing",
                source_value=conditions,
                target_value=None,
                reason="free-text conditions are not typed executable condition bindings",
            )
        )
        gaps.add("missing_typed_condition_bindings")
    else:
        mappings.append(
            _mapping(
                "typed_condition_bindings",
                status="exact",
                source_value=[],
                target_value=[],
                reason="record declares no condition qualifier",
            )
        )
    scope = list(qualifiers.get("scope", []))
    if scope:
        mappings.append(
            _mapping(
                "typed_scope_bindings",
                status="missing",
                source_value=scope,
                target_value=None,
                reason="free-text scope is not a typed scope binding",
            )
        )
        gaps.add("missing_typed_scope_bindings")
    else:
        mappings.append(
            _mapping(
                "typed_scope_bindings",
                status="exact",
                source_value=[],
                target_value=[],
                reason="record declares no scope qualifier",
            )
        )
    derivation = str(knowledge.get("derivation"))
    derivation_source = {
        "derivation": derivation,
        "inference_basis": knowledge.get("inference_basis"),
    }
    if derivation == "explicit":
        mappings.append(
            _mapping(
                "typed_derivation_provenance",
                status="exact",
                source_value=derivation_source,
                target_value=derivation_source,
                reason="explicit knowledge requires no inferred completion provenance",
            )
        )
    else:
        mappings.append(
            _mapping(
                "typed_derivation_provenance",
                status="missing",
                source_value=derivation_source,
                target_value=None,
                reason="free-text inference basis is not typed derivation provenance",
            )
        )
        gaps.add("missing_typed_derivation_provenance")
    if level == "l2_cross_turn_candidate":
        gaps.update(_L2_REQUIRED_GAPS)
    elif level == "blocked_candidate":
        gaps.add("missing_evidence_boundary")

    payload = {
        "knowledge_id": knowledge["knowledge_id"],
        "candidate_id": knowledge["candidate_id"],
        "source_stage": record.stage,
        "projection_status": record.status,
        "candidate_level": level,
        "evidence_ids": evidence_ids,
        "evidence_turns": evidence_turns,
        "mappings": [
            item.model_dump(mode="json") for item in sorted(mappings, key=lambda item: item.field)
        ],
        "blocking_gaps": sorted(gaps),
    }
    envelope_id = "extraction-envelope-" + hashlib.sha256(
        canonical_json_bytes(payload)
    ).hexdigest()[:24]
    return ExtractionCompatibilityEnvelope(
        envelope_id=envelope_id,
        mappings=sorted(mappings, key=lambda item: item.field),
        blocking_gaps=sorted(gaps),
        **{key: value for key, value in payload.items() if key not in {"mappings", "blocking_gaps"}},
    )


def build_compatibility_envelopes(
    replay: ExtractionReplay,
) -> list[ExtractionCompatibilityEnvelope]:
    _validate_projection_candidate_boundaries(
        replay.view,
        replay.operation_candidates,
    )
    return [_envelope(record) for record in sorted(replay.view.records, key=lambda item: item.knowledge_id)]


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _raw_structure_metrics(replay: ExtractionReplay) -> dict[str, Any]:
    stage_counts: Counter[str] = Counter()
    modality_counts: Counter[str] = Counter()
    source_status_counts: Counter[str] = Counter()
    projection_status_counts: Counter[str] = Counter()
    evidence_definitions: set[str] = set()
    evidence_count = 0
    single_turn = 0
    cross_turn = 0
    complete = 0
    dialogue_add = 0
    conditions = 0
    scopes = 0
    non_explicit_derivations = 0
    object_present = 0
    for record in replay.view.records:
        knowledge = record.knowledge
        stage_counts[record.stage] += 1
        modality_counts[str(knowledge["qualifiers"]["modality"])] += 1
        source_status_counts[str(knowledge["source_status"])] += 1
        projection_status_counts[record.status] += 1
        evidence = knowledge["evidence"]
        evidence_count += len(evidence)
        evidence_definitions.update(str(item["evidence_id"]) for item in evidence)
        evidence_turns = {int(item["turn_index"]) for item in evidence}
        if len(evidence_turns) == 1:
            single_turn += 1
        elif len(evidence_turns) > 1:
            cross_turn += 1
        if record.added_by:
            dialogue_add += 1
        qualifiers = knowledge.get("qualifiers")
        if isinstance(qualifiers, dict):
            conditions += bool(qualifiers.get("conditions"))
            scopes += bool(qualifiers.get("scope"))
        non_explicit_derivations += knowledge.get("derivation") != "explicit"
        object_present += knowledge.get("object") is not None
        if (
            isinstance(knowledge.get("statement"), str)
            and bool(knowledge["statement"].strip())
            and isinstance(knowledge.get("subject"), str)
            and bool(knowledge["subject"].strip())
            and isinstance(knowledge.get("predicate"), str)
            and bool(knowledge["predicate"].strip())
            and isinstance(qualifiers, dict)
        ):
            complete += 1
    return {
        "projected_record_count": replay.record_count,
        "active_record_count": replay.active_record_count,
        "stage_counts": dict(sorted(stage_counts.items())),
        "modality_counts": dict(sorted(modality_counts.items())),
        "source_status_counts": dict(sorted(source_status_counts.items())),
        "projection_status_counts": dict(sorted(projection_status_counts.items())),
        "evidence_reference_count": evidence_count,
        "unique_evidence_count": len(evidence_definitions),
        "single_turn_evidence_record_count": single_turn,
        "cross_turn_evidence_record_count": cross_turn,
        "dialogue_add_record_count": dialogue_add,
        "corrected_record_count": projection_status_counts["corrected"],
        "superseded_record_count": projection_status_counts["superseded"],
        "conflicted_record_count": projection_status_counts["active_conflict"],
        "exact_evidence_binding_rate": 1.0,
        "source_status_admissibility_rate": 1.0,
        "required_surface_field_completeness_rate": _ratio(complete, replay.record_count),
        "object_present_rate": _ratio(object_present, replay.record_count),
        "condition_qualifier_record_count": conditions,
        "scope_qualifier_record_count": scopes,
        "non_explicit_derivation_record_count": non_explicit_derivations,
        "scope": "existing validated model extraction structure; no gold semantic quality claim",
    }


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


def _safety_metrics(
    envelopes: list[ExtractionCompatibilityEnvelope],
) -> dict[str, Any]:
    level_counts = Counter(item.candidate_level for item in envelopes)
    gap_counts: Counter[str] = Counter(
        gap for item in envelopes for gap in item.blocking_gaps
    )
    ready_l1 = sum(
        item.candidate_level == "l1_single_turn_candidate"
        and item.authoritative_materialization_allowed
        for item in envelopes
    )
    ready_l2 = sum(
        item.candidate_level == "l2_cross_turn_candidate"
        and item.authoritative_materialization_allowed
        for item in envelopes
    )
    claims = [item.automatic_write_claims.model_dump(mode="json") for item in envelopes]
    return {
        "l1_candidate_count": level_counts["l1_single_turn_candidate"],
        "l2_candidate_count": level_counts["l2_cross_turn_candidate"],
        "blocked_candidate_count": level_counts["blocked_candidate"],
        "materialization_blocked_count": sum(bool(item.blocking_gaps) for item in envelopes),
        "authoritative_ready_l1_count": ready_l1,
        "authoritative_ready_l2_count": ready_l2,
        "gap_counts": dict(sorted(gap_counts.items())),
        "automatic_l1_write_count": sum(item["l1"] for item in claims),
        "automatic_l2_write_count": sum(item["l2"] for item in claims),
        "automatic_unit_revision_write_count": sum(
            item["unit_revision"] for item in claims
        ),
        "automatic_closure_write_count": sum(item["closure"] for item in claims),
        "automatic_identity_write_count": sum(item["identity"] for item in claims),
        "automatic_membership_write_count": sum(
            item["membership"] for item in claims
        ),
    }


def assess_extraction_bridge(
    replay: ExtractionReplay,
    envelopes: list[ExtractionCompatibilityEnvelope],
    *,
    guard_bundle: MemoryRepresentationBundleV3,
) -> tuple[ExtractionCompatibilityLedger, ExtractionBridgeAssessment]:
    if len(envelopes) != replay.record_count:
        raise ValueError("compatibility envelope coverage mismatch")
    if len({item.knowledge_id for item in envelopes}) != len(envelopes):
        raise ValueError("compatibility envelopes repeat knowledge IDs")
    expected_candidates = {
        record.knowledge_id: record.candidate_id for record in replay.view.records
    }
    actual_ids = {item.knowledge_id for item in envelopes}
    if actual_ids != set(expected_candidates):
        raise ValueError("compatibility envelope record coverage mismatch")
    for item in envelopes:
        if item.candidate_id != expected_candidates[item.knowledge_id]:
            raise ValueError("compatibility envelope candidate mismatch")
    before_fingerprint = canonical_sha256(guard_bundle)
    before_counts = _guard_counts(guard_bundle)
    ledger = ExtractionCompatibilityLedger(
        input_sha256=dict(sorted(replay.input_sha256.items())),
        record_count=replay.record_count,
        envelopes=envelopes,
    )
    raw = _raw_structure_metrics(replay)
    safety = _safety_metrics(envelopes)
    after_fingerprint = canonical_sha256(guard_bundle)
    after_counts = _guard_counts(guard_bundle)
    unchanged = (
        before_fingerprint == after_fingerprint and before_counts == after_counts
    )
    if not unchanged:
        raise ValueError("authoritative guard bundle mutated during assessment")
    write_count = sum(
        safety[key]
        for key in (
            "automatic_l1_write_count",
            "automatic_l2_write_count",
            "automatic_unit_revision_write_count",
            "automatic_closure_write_count",
            "automatic_identity_write_count",
            "automatic_membership_write_count",
        )
    )
    if write_count:
        raise ValueError("automatic authoritative write claim detected")
    ready = bool(
        unchanged
        and write_count == 0
        and (
            safety["authoritative_ready_l1_count"]
            + safety["authoritative_ready_l2_count"]
        )
        > 0
    )
    assessment = ExtractionBridgeAssessment(
        raw_extraction_structure=raw,
        deterministic_bridge_safety=safety,
        guard_state={
            "before_counts": before_counts,
            "after_counts": after_counts,
            "before_fingerprint": before_fingerprint,
            "after_fingerprint": after_fingerprint,
            "unchanged": unchanged,
        },
        typed_extractor_v2_requirements=list(TYPED_EXTRACTOR_V2_REQUIREMENTS),
        automatic_extraction_integration_ready=ready,
        claim_boundary={
            "automatic_closure_write_authorized": False,
            "automatic_identity_write_authorized": False,
            "automatic_l1_write_authorized": False,
            "automatic_l2_write_authorized": False,
            "automatic_membership_write_authorized": False,
            "automatic_unit_revision_write_authorized": False,
            "embedding_authority": False,
            "longmemeval_status": "structured_l2_identity_unresolved",
        },
    )
    return ledger, assessment


def _automatic_write_count(assessment: ExtractionBridgeAssessment) -> int:
    safety = assessment.deterministic_bridge_safety
    return sum(
        int(safety[key])
        for key in (
            "automatic_l1_write_count",
            "automatic_l2_write_count",
            "automatic_unit_revision_write_count",
            "automatic_closure_write_count",
            "automatic_identity_write_count",
            "automatic_membership_write_count",
        )
    )


def render_extraction_bridge_report(
    assessment: ExtractionBridgeAssessment,
) -> str:
    raw = assessment.raw_extraction_structure
    safety = assessment.deterministic_bridge_safety
    gap_lines = [
        f"- `{name}`: {count}"
        for name, count in sorted(safety["gap_counts"].items())
    ]
    requirement_lines = [
        f"- `{requirement}`"
        for requirement in assessment.typed_extractor_v2_requirements
    ]
    lines = [
        "# Automatic L1/L2 Extraction Bridge Assessment",
        "",
        f"Status: `{assessment.status}`",
        "",
        "## Raw extraction structure",
        "",
        f"- Projected records: {raw['projected_record_count']}",
        f"- Active records: {raw['active_record_count']}",
        f"- Exact evidence binding rate: {raw['exact_evidence_binding_rate']}",
        f"- Source-status admissibility rate: {raw['source_status_admissibility_rate']}",
        "- These are structural measurements over existing model output, not gold semantic accuracy.",
        "",
        "## Deterministic bridge safety",
        "",
        f"- L1 single-turn candidates: {safety['l1_candidate_count']}",
        f"- L2 cross-turn candidates: {safety['l2_candidate_count']}",
        f"- Authoritative-ready L1/L2: {safety['authoritative_ready_l1_count']}/{safety['authoritative_ready_l2_count']}",
        f"- Materialization-blocked records: {safety['materialization_blocked_count']}",
        f"- Automatic authoritative writes: {_automatic_write_count(assessment)}",
        f"- Guard unchanged: {str(assessment.guard_state['unchanged']).lower()}",
        f"- Integration ready: {str(assessment.automatic_extraction_integration_ready).lower()}",
        "",
        "### Blocking gaps",
        "",
        *gap_lines,
        "",
        "## Typed extractor v2 requirements",
        "",
        *requirement_lines,
        "",
        "## Limitations",
        "",
        "- No model was rerun in this wave.",
        "- The assessment does not publish authoritative L1, L2, unit revisions, closure, identity, or membership writes.",
        "- Missing semantic fields are blocked rather than filled by heuristics, WordNet, schema.org, or embeddings.",
        "- `LONGMEMEVAL-6d550036` remains `structured_l2_identity_unresolved`.",
        "- This wave does not compile questions, execute new benchmark queries, aggregate across sessions, or select a storage profile.",
        "",
    ]
    return "\n".join(lines)


def _require_new_output_paths(paths: list[Path]) -> None:
    resolved = [path.resolve() for path in paths]
    if len(set(resolved)) != len(resolved):
        raise ValueError("assessment output paths must be distinct")
    existing = next((path for path in resolved if path.exists()), None)
    if existing is not None:
        raise FileExistsError(f"assessment output already exists: {existing}")


def _freeze_existing(paths: list[Path]) -> None:
    for path in paths:
        if path.exists():
            path.chmod(0o444)


def run_extraction_bridge_assessment(
    *,
    source_path: Path,
    turn_manifest_path: Path,
    dialogue_manifest_path: Path,
    final_knowledge_path: Path,
    run_path: Path,
    source_segments_path: Path,
    guard_root: Path,
    guard_slice_id: str,
    guard_results_path: Path,
    ledger_path: Path,
    assessment_path: Path,
    report_path: Path,
) -> dict[str, Any]:
    output_paths = [ledger_path.resolve(), assessment_path.resolve(), report_path.resolve()]
    _require_new_output_paths(output_paths)
    try:
        replay = replay_extraction_inputs(
            source_path=source_path,
            turn_manifest_path=turn_manifest_path,
            dialogue_manifest_path=dialogue_manifest_path,
            final_knowledge_path=final_knowledge_path,
            run_path=run_path,
            source_segments_path=source_segments_path,
        )
        envelopes = build_compatibility_envelopes(replay)
        guard_bundle = build_authoritative_conformance_bundle(
            guard_root,
            guard_slice_id,
            guard_results_path,
        )
        ledger, assessment = assess_extraction_bridge(
            replay,
            envelopes,
            guard_bundle=guard_bundle,
        )
        write_json_immutable(ledger_path, ledger)
        ledger_path.chmod(0o444)
        write_json_immutable(assessment_path, assessment)
        assessment_path.chmod(0o444)
        write_text_immutable(
            report_path,
            render_extraction_bridge_report(assessment),
        )
        report_path.chmod(0o444)
    except Exception:
        _freeze_existing(output_paths)
        raise
    return {
        "status": assessment.status,
        "record_count": ledger.record_count,
        "automatic_extraction_integration_ready": (
            assessment.automatic_extraction_integration_ready
        ),
        "automatic_authoritative_write_count": _automatic_write_count(assessment),
        "output_sha256": {
            "assessment": sha256_file(assessment_path),
            "ledger": sha256_file(ledger_path),
            "report": sha256_file(report_path),
        },
    }
