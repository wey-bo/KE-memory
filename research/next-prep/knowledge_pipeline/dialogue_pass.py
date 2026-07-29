"""Deterministic dialogue-pass preparation and validation."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any

from pydantic import ValidationError

from knowledge_pipeline.evidence import resolve_evidence
from knowledge_pipeline.models import (
    ContextCompletion,
    DialoguePassOutput,
    Evidence,
    EvidenceDraft,
    Knowledge,
    OperationEvidenceDraft,
    SourceStatus,
    TurnPassOutput,
)
from knowledge_pipeline.source import PROMPT_VERSION as TURN_PROMPT_VERSION, TurnUnit, load_turn_units
from knowledge_pipeline.source_segments import (
    ToolResultSpan,
    load_source_segments,
    parse_tool_result_spans,
    tool_marker_ranges,
)
from knowledge_pipeline.turn_pass import candidate_namespace, validate_turn_output


DIALOGUE_PROMPT_VERSION = "dialogue-reconciliation-v1"
_SHA256 = re.compile(r"[0-9a-f]{64}")


def _write_json(path: Path, value: object) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as output:
        json.dump(value, output, ensure_ascii=False, indent=2)
        output.write("\n")
        output.flush()
        os.fsync(output.fileno())


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _schema_hash(schema: object) -> str:
    encoded = json.dumps(schema, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return _sha256_bytes(encoded)


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _read_json(path: Path, label: str) -> tuple[bytes, Any]:
    try:
        content = path.read_bytes()
        return content, json.loads(content)
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"could not parse {label}: {error}") from error


def _resolve_turn_manifest(path: str | Path) -> Path:
    value = Path(path)
    if value.is_file():
        return value.resolve()
    candidates = (value / "manifest.json", value / "validated" / "manifest.json")
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise ValueError("validated turn-pass manifest is missing")


def _expected_turn_filename(unit: TurnUnit) -> str:
    return f"{unit.candidate_index:04d}-{unit.turn_index:04d}.json"


def _validate_persisted_knowledge(
    item: object, unit: TurnUnit, tool_result_spans: tuple[ToolResultSpan, ...]
) -> dict[str, Any]:
    try:
        knowledge = Knowledge.model_validate(item)
    except ValidationError as error:
        raise ValueError(f"invalid validated A-stage knowledge: {error}") from error
    if knowledge.candidate_id != unit.candidate_id:
        raise ValueError("validated A-stage knowledge candidate_id is invalid")
    expected_prefix = f"K_{candidate_namespace(unit.candidate_id)}_{unit.turn_index:03d}_"
    if not knowledge.knowledge_id.startswith(expected_prefix):
        raise ValueError("validated A-stage knowledge ID is not candidate scoped")
    for evidence in knowledge.evidence:
        if evidence.candidate_id != unit.candidate_id or evidence.turn_index != unit.turn_index:
            raise ValueError("validated A-stage evidence coordinates are invalid")
        text = unit.user if evidence.message == "user" else unit.agent
        resolved = resolve_evidence(
            unit.candidate_id,
            unit.turn_index,
            text,
            evidence.message,
            evidence.quote,
            evidence.occurrence_index,
            evidence.evidence_role,
        )
        if resolved != evidence:
            raise ValueError("validated A-stage evidence does not match exact source text")
    turns = {unit.turn_index: {"agent": unit.agent, "tool_result_spans": tool_result_spans}}
    _validate_source_status(knowledge.source_status, knowledge.evidence, turns)
    return knowledge.model_dump(mode="json")


def _validate_context_completion(item: object, unit: TurnUnit) -> None:
    if not isinstance(item, dict) or not isinstance(item.get("evidence"), list):
        raise ValueError("invalid validated A-stage context completion")
    drafts: list[dict[str, Any]] = []
    for evidence in item["evidence"]:
        if not isinstance(evidence, dict):
            raise ValueError("invalid validated A-stage completion evidence")
        try:
            persisted = Evidence.model_validate(evidence)
        except ValidationError as error:
            raise ValueError(f"invalid validated A-stage completion evidence: {error}") from error
        if persisted.candidate_id != unit.candidate_id or persisted.turn_index != unit.turn_index:
            raise ValueError("validated A-stage completion evidence coordinates are invalid")
        text = unit.user if persisted.message == "user" else unit.agent
        resolved = resolve_evidence(
            unit.candidate_id,
            unit.turn_index,
            text,
            persisted.message,
            persisted.quote,
            persisted.occurrence_index,
            persisted.evidence_role,
        )
        if resolved != persisted:
            raise ValueError("validated A-stage completion evidence does not match exact source text")
        drafts.append({
            "turn_index": persisted.turn_index,
            "message": persisted.message,
            "occurrence_index": persisted.occurrence_index,
            "quote": persisted.quote,
        })
    try:
        completion = ContextCompletion.model_validate({**item, "evidence": drafts})
    except ValidationError as error:
        raise ValueError(f"invalid validated A-stage context completion: {error}") from error
    expected_prefix = f"C_{candidate_namespace(unit.candidate_id)}_{unit.turn_index:03d}_"
    if (
        completion.candidate_id != unit.candidate_id
        or completion.turn_index != unit.turn_index
        or not completion.completion_id.startswith(expected_prefix)
    ):
        raise ValueError("validated A-stage context completion coordinates are invalid")


def _load_first_pass(
    source_path: str | Path, turn_manifest_path: str | Path
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    source_file = Path(source_path).resolve()
    units = load_turn_units(source_file)
    if len(units) != 43:
        raise ValueError("KE-test must contain exactly 43 turns")
    manifest_file = _resolve_turn_manifest(turn_manifest_path)
    manifest_bytes, manifest = _read_json(manifest_file, "validated turn-pass manifest")
    if not isinstance(manifest, dict) or set(manifest) != {
        "prompt_version", "prompt_sha256", "output_contract_sha256",
        "source_segments_file", "source_segments_sha256", "turns",
    }:
        raise ValueError("validated turn-pass manifest has an unexpected schema")
    if manifest["prompt_version"] != TURN_PROMPT_VERSION:
        raise ValueError("validated turn-pass prompt version is invalid")
    if manifest["output_contract_sha256"] != _schema_hash(TurnPassOutput.model_json_schema()):
        raise ValueError("validated turn-pass output contract SHA256 is invalid")
    source_segments_file = Path(str(manifest["source_segments_file"]))
    source_segments = load_source_segments(source_segments_file, units)
    if source_segments.sha256 != manifest["source_segments_sha256"]:
        raise ValueError("validated turn-pass source segments SHA256 is invalid")
    entries = manifest["turns"]
    if not isinstance(entries, list) or len(entries) != 43:
        raise ValueError("validated turn-pass manifest must contain exactly 43 records")
    by_filename: dict[str, dict[str, Any]] = {}
    required = {
        "validated_file", "candidate_id", "candidate_index", "candidate_namespace", "turn_index", "source",
        "source_coordinates", "canonical_filename", "user_hash", "agent_hash", "payload_sha256",
        "prompt_sha256", "output_contract_sha256", "source_segments_sha256",
        "raw_sha256_before", "raw_sha256_after",
    }
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != required:
            raise ValueError("validated turn-pass manifest contains an invalid record")
        filename = entry["canonical_filename"]
        if not isinstance(filename, str) or entry["validated_file"] != filename or filename in by_filename:
            raise ValueError("validated turn-pass canonical filenames are invalid")
        if entry["raw_sha256_before"] != entry["raw_sha256_after"] or not isinstance(entry["raw_sha256_before"], str) or not _SHA256.fullmatch(entry["raw_sha256_before"]):
            raise ValueError("validated turn-pass raw provenance hashes are invalid")
        by_filename[filename] = entry

    expected_files = {_expected_turn_filename(unit) for unit in units}
    actual_files = {path.name for path in manifest_file.parent.glob("[0-9][0-9][0-9][0-9]-[0-9][0-9][0-9][0-9].json")}
    missing = sorted(expected_files - actual_files)
    extra = sorted(actual_files - expected_files)
    if missing:
        raise ValueError(f"missing validated A-stage files: {', '.join(missing)}")
    if extra:
        raise ValueError(f"extra validated A-stage files: {', '.join(extra)}")
    if set(by_filename) != expected_files:
        raise ValueError("validated turn-pass manifest does not describe the exact 43 source turns")
    raw_root = manifest_file.parent.parent / "raw"
    if not raw_root.is_dir():
        raise ValueError("turn-pass raw outputs are required for trusted A-stage replay")
    actual_raw = {path.name for path in raw_root.glob("*.json")}
    missing_raw, extra_raw = sorted(expected_files - actual_raw), sorted(actual_raw - expected_files)
    if missing_raw or extra_raw:
        raise ValueError("turn-pass raw provenance does not contain the exact 43 files")
    for filename, entry in by_filename.items():
        if _sha256_bytes((raw_root / filename).read_bytes()) != entry["raw_sha256_before"]:
            raise ValueError(f"turn-pass raw output {filename} SHA256 does not match validated provenance")

    prepared_root = manifest_file.parent.parent / "prepared"
    prepared_manifest_file = prepared_root / "manifest.json"
    _, prepared_manifest = _read_json(prepared_manifest_file, "prepared turn-pass manifest")
    if not isinstance(prepared_manifest, dict) or set(prepared_manifest) != {
        "prompt_version", "prompt_sha256", "prompt_file", "output_contract_sha256",
        "source_segments_file", "source_segments_sha256", "turns",
    }:
        raise ValueError("prepared turn-pass manifest has an unexpected schema")
    if prepared_manifest.get("prompt_sha256") != manifest["prompt_sha256"]:
        raise ValueError("prepared and validated turn-pass prompt provenance differs")
    if prepared_manifest.get("output_contract_sha256") != manifest["output_contract_sha256"]:
        raise ValueError("prepared and validated turn-pass schema provenance differs")
    if (
        prepared_manifest.get("source_segments_file") != manifest["source_segments_file"]
        or prepared_manifest.get("source_segments_sha256") != source_segments.sha256
    ):
        raise ValueError("prepared and validated source-segment provenance differs")
    first_pass_prompt = Path(str(prepared_manifest["prompt_file"]))
    if not first_pass_prompt.is_file() or _sha256_bytes(first_pass_prompt.read_bytes()) != manifest["prompt_sha256"]:
        raise ValueError("prepared turn-pass prompt SHA256 is invalid")
    if not isinstance(prepared_manifest["turns"], list) or len(prepared_manifest["turns"]) != 43:
        raise ValueError("prepared turn-pass manifest must contain exactly 43 records")

    records: list[dict[str, Any]] = []
    candidate_whitelist = {unit.candidate_id for unit in units}
    for unit in units:
        filename = _expected_turn_filename(unit)
        entry = by_filename[filename]
        namespace = candidate_namespace(unit.candidate_id)
        expected_coordinates = {
            "user": unit.user_pointer,
            "agent": unit.agent_pointer,
        }
        if (
            entry["candidate_id"] != unit.candidate_id
            or entry["candidate_index"] != unit.candidate_index
            or entry["candidate_namespace"] != namespace
            or entry["turn_index"] != unit.turn_index
            or entry["source"] != unit.source
            or entry["source_coordinates"] != expected_coordinates
            or entry["user_hash"] != _sha256_bytes(unit.user.encode("utf-8"))
            or entry["agent_hash"] != _sha256_bytes(unit.agent.encode("utf-8"))
            or entry["prompt_sha256"] != manifest["prompt_sha256"]
            or entry["output_contract_sha256"] != manifest["output_contract_sha256"]
            or entry["source_segments_sha256"] != source_segments.sha256
        ):
            raise ValueError(f"validated turn-pass source provenance mismatch for {filename}")
        payload_file = prepared_root / "payloads" / filename
        payload_bytes, payload = _read_json(payload_file, f"turn payload {filename}")
        if _sha256_bytes(payload_bytes) != entry["payload_sha256"]:
            raise ValueError(f"turn payload {filename} SHA256 does not match provenance")
        if (
            not isinstance(payload, dict)
            or payload.get("candidate_id") != unit.candidate_id
            or payload.get("turn_index") != unit.turn_index
            or payload.get("source") != unit.source
            or payload.get("user") != unit.user
            or payload.get("agent") != unit.agent
            or payload.get("source_coordinates") != expected_coordinates
            or payload.get("candidate_namespace") != namespace
            or payload.get("output_contract") != TurnPassOutput.model_json_schema()
            or payload.get("source_segments_sha256") != source_segments.sha256
        ):
            raise ValueError(f"turn payload {filename} does not match KE-test source")
        tool_result_spans = parse_tool_result_spans(payload.get("tool_result_spans"), unit.agent)
        if tool_result_spans != source_segments.for_turn(unit.candidate_id, unit.turn_index):
            raise ValueError(f"turn payload {filename} differs from source-segment annotations")
        validated_file = manifest_file.parent / filename
        validated_bytes, output = _read_json(validated_file, f"validated A-stage file {filename}")
        if not isinstance(output, dict) or set(output) != {
            "candidate_id", "turn_index", "context_completions", "knowledge",
        }:
            raise ValueError(f"validated A-stage file {filename} has an unexpected schema")
        if output["candidate_id"] != unit.candidate_id or output["turn_index"] != unit.turn_index:
            raise ValueError(f"validated A-stage file {filename} source coordinates are invalid")
        if not isinstance(output["knowledge"], list) or not isinstance(output["context_completions"], list):
            raise ValueError(f"validated A-stage file {filename} lists are invalid")
        raw_bytes, raw = _read_json(raw_root / filename, f"raw A-stage file {filename}")
        raw_before = _sha256_bytes(raw_bytes)
        if raw_before != entry["raw_sha256_before"] or raw_before != entry["raw_sha256_after"]:
            raise ValueError(f"turn-pass raw output {filename} SHA256 does not match validated provenance")
        replayed = validate_turn_output(
            raw,
            unit.candidate_id,
            unit.turn_index,
            unit.user,
            unit.agent,
            candidate_whitelist,
            tool_result_spans,
        )
        if _canonical_json(replayed) != _canonical_json(output):
            raise ValueError(f"validated A-stage file {filename} differs from replayed raw output")
        for completion in output["context_completions"]:
            _validate_context_completion(completion, unit)
        output = dict(output)
        output["knowledge"] = [
            _validate_persisted_knowledge(item, unit, tool_result_spans) for item in output["knowledge"]
        ]
        records.append({
            "unit": unit,
            "canonical_filename": filename,
            "sha256": _sha256_bytes(validated_bytes),
            "output": output,
            "tool_result_spans": tool_result_spans,
            "source_segments_sha256": source_segments.sha256,
        })
    return records, {
        "source_file": str(source_file),
        "source_sha256": _sha256_bytes(source_file.read_bytes()),
        "first_pass_manifest_file": str(manifest_file),
        "first_pass_manifest_sha256": _sha256_bytes(manifest_bytes),
        "first_pass_prompt_sha256": manifest["prompt_sha256"],
        "first_pass_output_contract_sha256": manifest["output_contract_sha256"],
        "source_segments_file": str(source_segments.path),
        "source_segments_sha256": source_segments.sha256,
    }


def _candidate_payload(
    candidate_records: list[dict[str, Any]],
    candidate_index: int,
    prompt_sha256: str,
    output_contract_sha256: str,
) -> dict[str, Any]:
    first = candidate_records[0]
    first_unit: TurnUnit = first["unit"]
    namespace = candidate_namespace(first_unit.candidate_id)
    return {
        "prompt_version": DIALOGUE_PROMPT_VERSION,
        "candidate_id": first_unit.candidate_id,
        "candidate_index": candidate_index,
        "source": first_unit.source,
        "candidate_namespace": namespace,
        "conversation": [
            {
                "turn_index": record["unit"].turn_index,
                "user": record["unit"].user,
                "agent": record["unit"].agent,
                "source_coordinates": {
                    "user": record["unit"].user_pointer,
                    "agent": record["unit"].agent_pointer,
                },
                "tool_result_spans": [
                    {
                        "quote": span.quote,
                        "occurrence_index": span.occurrence_index,
                        "marker_occurrence_index": span.marker_occurrence_index,
                        "start": span.start,
                        "end": span.end,
                    }
                    for span in record["tool_result_spans"]
                ],
            }
            for record in candidate_records
        ],
        "first_pass_records": [
            {
                "turn_index": record["unit"].turn_index,
                "canonical_filename": record["canonical_filename"],
                "sha256": record["sha256"],
                "output": record["output"],
            }
            for record in candidate_records
        ],
        "knowledge_id_prefix": f"D_{namespace}_",
        "operation_id_prefix": f"R_{namespace}_",
        "output_contract": DialoguePassOutput.model_json_schema(),
        "prompt_sha256": prompt_sha256,
        "output_contract_sha256": output_contract_sha256,
        "source_segments_sha256": first["source_segments_sha256"],
    }


def prepare_dialogue_payloads(
    source_path: str | Path,
    turn_manifest_path: str | Path,
    output_dir: str | Path,
    prompt_path: str | Path,
) -> Path:
    """Prepare one immutable dialogue payload for each KE-test candidate."""
    records, provenance = _load_first_pass(source_path, turn_manifest_path)
    prompt_file = Path(prompt_path).resolve()
    try:
        prompt_sha256 = _sha256_bytes(prompt_file.read_bytes())
    except OSError as error:
        raise ValueError(f"dialogue prompt is unavailable: {error}") from error
    schema_sha256 = _schema_hash(DialoguePassOutput.model_json_schema())
    grouped: dict[str, list[dict[str, Any]]] = {}
    candidate_order: list[str] = []
    for record in records:
        candidate_id = record["unit"].candidate_id
        if candidate_id not in grouped:
            grouped[candidate_id] = []
            candidate_order.append(candidate_id)
        grouped[candidate_id].append(record)
    if len(grouped) != 10:
        raise ValueError("KE-test must contain exactly 10 candidates")

    root = Path(output_dir) / "knowledge-extraction" / "dialogue-pass"
    destination = root / "prepared"
    if destination.exists():
        raise ValueError("prepared dialogue-pass batch already exists")
    root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="prepared-", dir=root))
    payloads_dir = staging / "payloads"
    payloads_dir.mkdir()
    candidates: list[dict[str, Any]] = []
    try:
        for candidate_index, candidate_id in enumerate(candidate_order):
            filename = f"{candidate_index:04d}.json"
            payload = _candidate_payload(
                grouped[candidate_id], candidate_index, prompt_sha256, schema_sha256
            )
            payload_file = payloads_dir / filename
            _write_json(payload_file, payload)
            candidates.append({
                "candidate_id": candidate_id,
                "candidate_index": candidate_index,
                "candidate_namespace": payload["candidate_namespace"],
                "canonical_filename": filename,
                "turn_count": len(payload["conversation"]),
                "payload_sha256": _sha256_bytes(payload_file.read_bytes()),
                "first_pass_files": [
                    {"canonical_filename": item["canonical_filename"], "sha256": item["sha256"]}
                    for item in payload["first_pass_records"]
                ],
            })
        _write_json(staging / "manifest.json", {
            "prompt_version": DIALOGUE_PROMPT_VERSION,
            "prompt_file": str(prompt_file),
            "prompt_sha256": prompt_sha256,
            "output_contract_sha256": schema_sha256,
            **provenance,
            "candidates": candidates,
        })
        os.replace(staging, destination)
    except Exception:
        if staging.exists():
            try:
                shutil.rmtree(staging, ignore_errors=True)
            except Exception:
                pass
        raise
    return destination / "manifest.json"


def _payload_turns(payload: dict[str, Any]) -> dict[int, dict[str, Any]]:
    conversation = payload.get("conversation")
    if not isinstance(conversation, list) or not conversation:
        raise ValueError("candidate payload conversation is invalid")
    turns: dict[int, dict[str, str]] = {}
    for expected_index, turn in enumerate(conversation):
        if (
            not isinstance(turn, dict)
            or turn.get("turn_index") != expected_index
            or not isinstance(turn.get("user"), str)
            or not isinstance(turn.get("agent"), str)
        ):
            raise ValueError("candidate payload conversation turn is invalid")
        spans = parse_tool_result_spans(turn.get("tool_result_spans"), turn["agent"])
        turns[expected_index] = {
            "user": turn["user"],
            "agent": turn["agent"],
            "tool_result_spans": spans,
        }
    return turns


def _resolve_dialogue_evidence(
    drafts: list[EvidenceDraft], candidate_id: str, turns: dict[int, dict[str, Any]], evidence_role: SourceStatus,
) -> list[Evidence]:
    resolved: list[Evidence] = []
    for draft in drafts:
        turn = turns.get(draft.turn_index)
        if turn is None:
            raise ValueError("evidence turn_index is outside the exact candidate conversation")
        resolved.append(resolve_evidence(
            candidate_id,
            draft.turn_index,
            turn[draft.message],
            draft.message,
            draft.quote,
            draft.occurrence_index,
            evidence_role,
        ))
    return resolved


def _validate_source_status(
    status: SourceStatus, evidence: list[Evidence], turns: dict[int, dict[str, Any]]
) -> None:
    if status == "user_reported" and any(item.message != "user" for item in evidence):
        raise ValueError("user_reported knowledge must be supported only by user evidence")
    if status == "agent_generated" and any(item.message != "agent" for item in evidence):
        raise ValueError("agent_generated knowledge must be supported only by agent evidence")
    if status == "agent_generated" and any(
        any(
            item.start < end and start < item.end
            for start, end in [
                *((span.start, span.end) for span in turns[item.turn_index]["tool_result_spans"]),
                *tool_marker_ranges(turns[item.turn_index]["agent"]),
            ]
        )
        for item in evidence
    ):
        raise ValueError("agent_generated knowledge evidence must be outside tool result and marker spans")
    if status == "tool_observed":
        for item in evidence:
            ranges = [
                (span.start, span.end) for span in turns[item.turn_index]["tool_result_spans"]
            ]
            if (
                item.message != "agent"
                or not item.quote.strip()
                or not any(start <= item.start and item.end <= end for start, end in ranges)
            ):
                raise ValueError("tool_observed knowledge requires content after an explicit [tool result] marker")


def _validate_operation_evidence_role(
    draft: OperationEvidenceDraft, evidence: Evidence, turns: dict[int, dict[str, Any]]
) -> None:
    if evidence.message == "user":
        if draft.evidence_role != "user_reported":
            raise ValueError("user operation evidence_role must be user_reported")
        return
    if draft.evidence_role == "user_reported":
        raise ValueError("agent operation evidence_role cannot be user_reported")
    agent = turns[evidence.turn_index]["agent"]
    result_ranges = [
        (span.start, span.end) for span in turns[evidence.turn_index]["tool_result_spans"]
    ]
    marker_ranges = list(tool_marker_ranges(agent))
    inside_result = any(start <= evidence.start and evidence.end <= end for start, end in result_ranges)
    overlaps_result = any(evidence.start < end and start < evidence.end for start, end in result_ranges)
    overlaps_marker = any(evidence.start < end and start < evidence.end for start, end in marker_ranges)
    if draft.evidence_role == "tool_observed":
        if not evidence.quote.strip() or not inside_result or overlaps_marker:
            raise ValueError("tool_observed operation evidence must be content after an explicit [tool result] marker")
    elif overlaps_result or overlaps_marker:
        raise ValueError("agent_generated operation evidence must be outside explicit tool result segments")


def _knowledge_ids(payload: dict[str, Any]) -> set[str]:
    records = payload.get("first_pass_records")
    if not isinstance(records, list):
        raise ValueError("candidate payload first_pass_records is invalid")
    candidate_id = payload.get("candidate_id")
    identifiers: set[str] = set()
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("output"), dict):
            raise ValueError("candidate payload first-pass record is invalid")
        output = record["output"]
        if output.get("candidate_id") != candidate_id or not isinstance(output.get("knowledge"), list):
            raise ValueError("candidate payload first-pass record candidate is invalid")
        for item in output["knowledge"]:
            if not isinstance(item, dict) or item.get("candidate_id") != candidate_id or not isinstance(item.get("knowledge_id"), str):
                raise ValueError("candidate payload A-stage knowledge reference is invalid")
            if not item["knowledge_id"].startswith(f"K_{candidate_namespace(str(candidate_id))}_"):
                raise ValueError("candidate payload A-stage knowledge ID is cross-candidate")
            if item["knowledge_id"] in identifiers:
                raise ValueError("candidate payload A-stage knowledge IDs must be unique")
            identifiers.add(item["knowledge_id"])
    return identifiers


def _require_contiguous_ids(values: list[str], prefix: str, label: str) -> None:
    expected = [f"{prefix}{index:03d}" for index in range(1, len(values) + 1)]
    if values != expected:
        raise ValueError(f"{label} must be unique, contiguous, ordered, and candidate scoped")


def validate_dialogue_output(raw: object, candidate_payload: dict[str, Any]) -> dict[str, Any]:
    """Validate one dialogue reconciliation and materialize exact evidence spans."""
    try:
        output = DialoguePassOutput.model_validate(raw)
    except ValidationError as error:
        raise ValueError(f"invalid DialoguePassOutput: {error}") from error
    candidate_id = candidate_payload.get("candidate_id")
    namespace = candidate_payload.get("candidate_namespace")
    if not isinstance(candidate_id, str) or output.candidate_id != candidate_id:
        raise ValueError("candidate_id does not match the candidate payload")
    if namespace != candidate_namespace(candidate_id):
        raise ValueError("candidate payload namespace is invalid")
    if any(item.candidate_id != candidate_id for item in output.new_knowledge):
        raise ValueError("new knowledge candidate_id does not match the candidate payload")
    if any(item.candidate_id != candidate_id for item in output.operations):
        raise ValueError("operation candidate_id does not match the candidate payload")
    _require_contiguous_ids(
        [item.knowledge_id for item in output.new_knowledge], f"D_{namespace}_", "new knowledge IDs"
    )
    _require_contiguous_ids(
        [item.operation_id for item in output.operations], f"R_{namespace}_", "operation IDs"
    )

    turns = _payload_turns(candidate_payload)
    a_ids = _knowledge_ids(candidate_payload)
    d_ids = {item.knowledge_id for item in output.new_knowledge}
    all_ids = a_ids | d_ids
    replacement_counts = {identifier: 0 for identifier in d_ids}
    state_assignments: dict[str, str] = {}
    corrected_or_superseded: set[str] = set()
    for operation in output.operations:
        if operation.operation in {"confirm", "correct", "supersede"}:
            invalid_targets = [target for target in operation.targets if target not in a_ids]
            if invalid_targets:
                raise ValueError(f"{operation.operation} targets must reference existing A-stage knowledge IDs only")
            for target in operation.targets:
                previous = state_assignments.get(target)
                if previous is not None:
                    raise ValueError(
                        f"A-stage target may have at most one state operation; got {previous} and {operation.operation}"
                    )
                state_assignments[target] = operation.operation
        if operation.operation in {"correct", "supersede"}:
            corrected_or_superseded.update(operation.targets)
    for operation in output.operations:
        if operation.operation == "conflict" and corrected_or_superseded.intersection(operation.targets):
            raise ValueError("conflict may not include knowledge corrected or superseded in the same output")

    for operation in output.operations:
        unknown_targets = [target for target in operation.targets if target not in all_ids]
        if unknown_targets:
            raise ValueError("operation target is unknown or cross-candidate")
        replacement = operation.replacement
        if operation.operation in {"correct", "add"}:
            if replacement not in d_ids:
                raise ValueError(f"{operation.operation} replacement must reference new dialogue knowledge")
        elif operation.operation == "supersede" and replacement is not None:
            if replacement not in all_ids:
                raise ValueError("supersede replacement is unknown or cross-candidate")
            if replacement in operation.targets:
                raise ValueError("supersede replacement must not self-reference a target")
            if replacement in corrected_or_superseded:
                raise ValueError("supersede replacement chains and cycles are forbidden; replacement is also a target")
        if replacement in replacement_counts:
            replacement_counts[replacement] += 1
    orphaned = sorted(identifier for identifier, count in replacement_counts.items() if count == 0)
    reused = sorted(identifier for identifier, count in replacement_counts.items() if count > 1)
    if orphaned:
        raise ValueError(f"orphan dialogue knowledge: {', '.join(orphaned)}")
    if reused:
        raise ValueError(f"dialogue knowledge replacement must be referenced exactly once: {', '.join(reused)}")

    knowledge: list[dict[str, Any]] = []
    for item in output.new_knowledge:
        if item.source_status == "user_reported" and any(draft.message != "user" for draft in item.evidence):
            raise ValueError("user_reported knowledge must be supported only by user evidence")
        if item.source_status in {"agent_generated", "tool_observed"} and any(
            draft.message != "agent" for draft in item.evidence
        ):
            raise ValueError(f"{item.source_status} knowledge must be supported only by agent evidence")
        evidence = _resolve_dialogue_evidence(item.evidence, candidate_id, turns, item.source_status)
        _validate_source_status(item.source_status, evidence, turns)
        persisted = Knowledge.model_validate({**item.model_dump(exclude={"evidence"}), "evidence": evidence})
        knowledge.append(persisted.model_dump(mode="json"))
    operations: list[dict[str, Any]] = []
    for operation in output.operations:
        evidence: list[Evidence] = []
        for draft in operation.evidence:
            resolved = _resolve_dialogue_evidence(
                [draft], candidate_id, turns, draft.evidence_role,
            )[0]
            _validate_operation_evidence_role(draft, resolved, turns)
            evidence.append(resolved)
        data = operation.model_dump(exclude={"evidence"})
        data["evidence"] = [item.model_dump(mode="json") for item in evidence]
        operations.append(data)
    return {"candidate_id": candidate_id, "new_knowledge": knowledge, "operations": operations}


def _load_dialogue_manifest(manifest_path: str | Path) -> tuple[Path, dict[str, Any], list[dict[str, Any]]]:
    manifest_file = Path(manifest_path).resolve()
    _, manifest = _read_json(manifest_file, "dialogue payload manifest")
    expected_keys = {
        "prompt_version", "prompt_file", "prompt_sha256", "output_contract_sha256", "source_file",
        "source_sha256", "first_pass_manifest_file", "first_pass_manifest_sha256", "first_pass_prompt_sha256",
        "first_pass_output_contract_sha256", "source_segments_file", "source_segments_sha256", "candidates",
    }
    if not isinstance(manifest, dict) or set(manifest) != expected_keys:
        raise ValueError("dialogue payload manifest has an unexpected schema")
    if manifest["prompt_version"] != DIALOGUE_PROMPT_VERSION:
        raise ValueError("dialogue prompt version is invalid")
    source_file = Path(str(manifest["source_file"]))
    if not source_file.is_file() or _sha256_bytes(source_file.read_bytes()) != manifest["source_sha256"]:
        raise ValueError("dialogue source SHA256 does not match the manifest")
    prompt_file = Path(str(manifest["prompt_file"]))
    if not prompt_file.is_file() or _sha256_bytes(prompt_file.read_bytes()) != manifest["prompt_sha256"]:
        raise ValueError("dialogue prompt SHA256 does not match the manifest")
    if manifest["output_contract_sha256"] != _schema_hash(DialoguePassOutput.model_json_schema()):
        raise ValueError("dialogue output schema SHA256 does not match the manifest")
    first_pass_file = Path(str(manifest["first_pass_manifest_file"]))
    if not first_pass_file.is_file() or _sha256_bytes(first_pass_file.read_bytes()) != manifest["first_pass_manifest_sha256"]:
        raise ValueError("first-pass manifest SHA256 does not match the dialogue manifest")
    source_segments_file = Path(str(manifest["source_segments_file"]))
    if (
        not source_segments_file.is_file()
        or _sha256_bytes(source_segments_file.read_bytes()) != manifest["source_segments_sha256"]
    ):
        raise ValueError("source segments SHA256 does not match the dialogue manifest")
    records, provenance = _load_first_pass(source_file, first_pass_file)
    for key in (
        "source_file", "source_sha256", "first_pass_manifest_file", "first_pass_manifest_sha256",
        "first_pass_prompt_sha256", "first_pass_output_contract_sha256",
        "source_segments_file", "source_segments_sha256",
    ):
        if manifest[key] != provenance[key]:
            raise ValueError(f"dialogue manifest {key} provenance is invalid")
    grouped: dict[str, list[dict[str, Any]]] = {}
    order: list[str] = []
    for record in records:
        candidate_id = record["unit"].candidate_id
        if candidate_id not in grouped:
            grouped[candidate_id] = []
            order.append(candidate_id)
        grouped[candidate_id].append(record)
    candidates = manifest["candidates"]
    if not isinstance(candidates, list) or len(candidates) != 10:
        raise ValueError("dialogue manifest must contain exactly 10 candidates")
    payloads: list[dict[str, Any]] = []
    for index, entry in enumerate(candidates):
        required = {
            "candidate_id", "candidate_index", "candidate_namespace", "canonical_filename", "turn_count",
            "payload_sha256", "first_pass_files",
        }
        if not isinstance(entry, dict) or set(entry) != required:
            raise ValueError("dialogue manifest contains an invalid candidate entry")
        candidate_id = order[index]
        filename = f"{index:04d}.json"
        expected_payload = _candidate_payload(
            grouped[candidate_id], index, str(manifest["prompt_sha256"]), str(manifest["output_contract_sha256"])
        )
        payload_file = manifest_file.parent / "payloads" / filename
        payload_bytes, payload = _read_json(payload_file, f"dialogue payload {filename}")
        if _sha256_bytes(payload_bytes) != entry["payload_sha256"]:
            raise ValueError(f"dialogue payload {filename} SHA256 does not match the manifest")
        if (
            entry["candidate_id"] != candidate_id
            or entry["candidate_index"] != index
            or entry["candidate_namespace"] != candidate_namespace(candidate_id)
            or entry["canonical_filename"] != filename
            or entry["turn_count"] != len(grouped[candidate_id])
            or entry["first_pass_files"] != [
                {"canonical_filename": item["canonical_filename"], "sha256": item["sha256"]}
                for item in expected_payload["first_pass_records"]
            ]
            or payload != expected_payload
        ):
            raise ValueError(f"dialogue payload {filename} does not match source, schema, or first-pass provenance")
        payloads.append(payload)
    return manifest_file, manifest, payloads


def validate_dialogue_batch(
    manifest_path: str | Path, raw_dir: str | Path, output_dir: str | Path
) -> Path:
    """Validate all ten dialogue outputs in memory, then publish atomically."""
    manifest_file, manifest, payloads = _load_dialogue_manifest(manifest_path)
    raw_path = Path(raw_dir).resolve()
    root = Path(output_dir).resolve() / "knowledge-extraction" / "dialogue-pass"
    destination = (root / "validated").resolve()
    if raw_path == destination or raw_path.is_relative_to(destination) or destination.is_relative_to(raw_path):
        raise ValueError("raw_dir and validated destination must be disjoint, non-nested paths")
    if destination.exists():
        raise ValueError("validated dialogue-pass output already exists")
    expected = {entry["canonical_filename"] for entry in manifest["candidates"]}
    actual = {path.name for path in raw_path.glob("*.json")} if raw_path.is_dir() else set()
    missing, extra = sorted(expected - actual), sorted(actual - expected)
    if missing:
        raise ValueError(f"missing raw dialogue output files: {', '.join(missing)}")
    if extra:
        raise ValueError(f"extra raw dialogue output files: {', '.join(extra)}")

    validated: dict[str, dict[str, Any]] = {}
    raw_hashes: dict[str, tuple[str, str]] = {}
    for entry, payload in zip(manifest["candidates"], payloads, strict=True):
        filename = entry["canonical_filename"]
        raw_file = raw_path / filename
        raw_bytes, raw = _read_json(raw_file, f"raw dialogue output {filename}")
        raw_before = _sha256_bytes(raw_bytes)
        validated[filename] = validate_dialogue_output(raw, payload)
        raw_after = _sha256_bytes(raw_file.read_bytes())
        if raw_before != raw_after:
            raise ValueError(f"raw dialogue output {filename} changed during validation")
        raw_hashes[filename] = (raw_before, raw_after)

    root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="validated-", dir=root))
    try:
        validated_hashes: dict[str, str] = {}
        for filename, value in validated.items():
            validated_file = staging / filename
            _write_json(validated_file, value)
            validated_hashes[filename] = _sha256_bytes(validated_file.read_bytes())
        _write_json(staging / "manifest.json", {
            "prompt_version": manifest["prompt_version"],
            "prompt_sha256": manifest["prompt_sha256"],
            "output_contract_sha256": manifest["output_contract_sha256"],
            "source_sha256": manifest["source_sha256"],
            "first_pass_manifest_sha256": manifest["first_pass_manifest_sha256"],
            "source_segments_file": manifest["source_segments_file"],
            "source_segments_sha256": manifest["source_segments_sha256"],
            "candidates": [
                {
                    **entry,
                    "validated_file": entry["canonical_filename"],
                    "validated_sha256": validated_hashes[entry["canonical_filename"]],
                    "raw_sha256_before": raw_hashes[entry["canonical_filename"]][0],
                    "raw_sha256_after": raw_hashes[entry["canonical_filename"]][1],
                }
                for entry in manifest["candidates"]
            ],
        })
        os.replace(staging, destination)
    except Exception:
        if staging.exists():
            try:
                shutil.rmtree(staging, ignore_errors=True)
            except Exception:
                pass
        raise
    return destination / "manifest.json"
