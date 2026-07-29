"""Isolated turn-pass payload preparation and raw-output validation."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any, Collection

from pydantic import ValidationError

from knowledge_pipeline.evidence import resolve_evidence
from knowledge_pipeline.models import Evidence, EvidenceDraft, Knowledge, SourceStatus, TurnPassOutput
from knowledge_pipeline.source import PROMPT_VERSION, TurnUnit, load_turn_units
from knowledge_pipeline.source_segments import (
    ToolResultSpan,
    load_source_segments,
    parse_tool_result_spans,
    tool_marker_ranges,
    validate_tool_result_spans,
)


def _write_json(path: Path, value: object) -> None:
    """Write and flush a JSON artifact before its staged directory is published."""
    with path.open("w", encoding="utf-8", newline="\n") as output:
        json.dump(value, output, ensure_ascii=False, indent=2)
        output.write("\n")
        output.flush()
        os.fsync(output.fileno())


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _schema_hash(schema: object) -> str:
    return _sha256_bytes(json.dumps(schema, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def candidate_namespace(candidate_id: str) -> str:
    """Produce a readable, non-empty namespace which remains distinct across slug collisions."""
    readable = re.sub(r"[^a-z0-9]+", "-", candidate_id.lower()).strip("-") or "candidate"
    return f"{readable}-{_sha256_bytes(candidate_id.encode('utf-8'))[:12]}"


def _expected_id(prefix: str, candidate_id: str, turn_index: int) -> re.Pattern[str]:
    return re.compile(rf"{prefix}_{re.escape(candidate_namespace(candidate_id))}_{turn_index:03d}_[0-9]{{3}}")


def _payload(
    unit: TurnUnit,
    source_segments_sha256: str,
    tool_result_spans: tuple[ToolResultSpan, ...],
) -> dict[str, object]:
    namespace = candidate_namespace(unit.candidate_id)
    return {
        "prompt_version": PROMPT_VERSION,
        "candidate_id": unit.candidate_id,
        "turn_index": unit.turn_index,
        "source": unit.source,
        "user": unit.user,
        "agent": unit.agent,
        "source_coordinates": {"user": unit.user_pointer, "agent": unit.agent_pointer},
        "output_contract": TurnPassOutput.model_json_schema(),
        "candidate_namespace": namespace,
        "knowledge_id_prefix": f"K_{namespace}_{unit.turn_index:03d}_",
        "context_completion_id_prefix": f"C_{namespace}_{unit.turn_index:03d}_",
        "source_segments_sha256": source_segments_sha256,
        "tool_result_spans": [
            {
                "quote": span.quote,
                "occurrence_index": span.occurrence_index,
                "marker_occurrence_index": span.marker_occurrence_index,
                "start": span.start,
                "end": span.end,
            }
            for span in tool_result_spans
        ],
    }


def prepare_turn_payloads(
    input_path: str | Path,
    output_dir: str | Path,
    prompt_path: str | Path,
    source_segments_path: str | Path | None = None,
) -> Path:
    """Write exactly one schema-backed, context-isolated payload per source turn."""
    units = load_turn_units(input_path)
    segments_path = (
        Path(source_segments_path)
        if source_segments_path is not None
        else Path(input_path).resolve().parent / "knowledge-extraction" / "source-segments.json"
    )
    source_segments = load_source_segments(segments_path, units)
    prompt = Path(prompt_path).resolve()
    prompt_sha256 = _sha256_bytes(prompt.read_bytes())
    output_contract_sha256 = _schema_hash(TurnPassOutput.model_json_schema())
    root = Path(output_dir) / "knowledge-extraction" / "turn-pass"
    destination = root / "prepared"
    if destination.exists():
        raise ValueError("prepared turn-pass batch already exists")
    namespaces: dict[str, str] = {}
    for unit in units:
        namespace = candidate_namespace(unit.candidate_id)
        prior_candidate = namespaces.get(namespace)
        if prior_candidate is not None and prior_candidate != unit.candidate_id:
            raise ValueError(f"candidate namespace collision: {namespace}")
        namespaces[namespace] = unit.candidate_id
    root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="prepared-", dir=root))
    payloads_dir = staging / "payloads"
    payloads_dir.mkdir()
    turns: list[dict[str, object]] = []
    try:
        for unit in units:
            filename = f"{unit.candidate_index:04d}-{unit.turn_index:04d}.json"
            payload = _payload(
                unit,
                source_segments.sha256,
                source_segments.for_turn(unit.candidate_id, unit.turn_index),
            )
            _write_json(payloads_dir / filename, payload)
            turns.append({
                "candidate_id": unit.candidate_id,
                "candidate_index": unit.candidate_index,
                "candidate_namespace": payload["candidate_namespace"],
                "turn_index": unit.turn_index,
                "source": unit.source,
                "source_coordinates": payload["source_coordinates"],
                "canonical_filename": filename,
                "user_hash": _sha256_bytes(unit.user.encode("utf-8")),
                "agent_hash": _sha256_bytes(unit.agent.encode("utf-8")),
                "payload_sha256": _sha256_bytes((payloads_dir / filename).read_bytes()),
                "prompt_sha256": prompt_sha256,
                "output_contract_sha256": output_contract_sha256,
                "source_segments_sha256": source_segments.sha256,
            })
        _write_json(staging / "manifest.json", {
            "prompt_version": PROMPT_VERSION,
            "prompt_sha256": prompt_sha256,
            "prompt_file": str(prompt),
            "output_contract_sha256": output_contract_sha256,
            "source_segments_file": str(source_segments.path),
            "source_segments_sha256": source_segments.sha256,
            "turns": turns,
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


def _resolve(
    drafts: list[EvidenceDraft], candidate_id: str, turn_index: int, user: str, agent: str, evidence_role: SourceStatus,
) -> list[Evidence]:
    resolved: list[Evidence] = []
    for draft in drafts:
        if draft.turn_index != turn_index:
            raise ValueError("evidence turn_index must match the expected turn")
        text = user if draft.message == "user" else agent
        resolved.append(resolve_evidence(
            candidate_id, turn_index, text, draft.message, draft.quote, draft.occurrence_index, evidence_role,
        ))
    return resolved


def _validate_source_status(
    status: SourceStatus,
    evidence: list[Evidence],
    agent: str,
    tool_result_spans: tuple[ToolResultSpan, ...],
) -> None:
    if status == "user_reported" and any(item.message != "user" for item in evidence):
        raise ValueError("user_reported knowledge must be supported by user evidence")
    if status == "agent_generated" and any(item.message != "agent" for item in evidence):
        raise ValueError("agent_generated knowledge must be supported by agent evidence")
    ranges = [(span.start, span.end) for span in tool_result_spans]
    marker_ranges = list(tool_marker_ranges(agent))
    if status == "agent_generated" and any(
        any(item.start < end and start < item.end for start, end in ranges + marker_ranges)
        for item in evidence
    ):
        raise ValueError("agent_generated knowledge evidence must be outside tool result and marker spans")
    if status == "tool_observed":
        if not ranges or any(
            item.message != "agent" or not item.quote.strip()
            or not any(start <= item.start and item.end <= end for start, end in ranges)
            for item in evidence
        ):
            raise ValueError("tool_observed knowledge requires every evidence span in an explicit source-segment tool result")


def _reject_cross_candidate_references(output: TurnPassOutput, candidate_whitelist: Collection[str]) -> None:
    other_ids = [candidate_id for candidate_id in candidate_whitelist if candidate_id != output.candidate_id]
    semantic_text: list[str] = []
    for item in output.knowledge:
        semantic_text.extend([item.statement, item.subject, item.predicate])
        if item.object is not None:
            semantic_text.append(item.object)
        if item.inference_basis is not None:
            semantic_text.append(item.inference_basis)
        semantic_text.extend(item.qualifiers.temporal)
        semantic_text.extend(item.qualifiers.conditions)
        semantic_text.extend(item.qualifiers.scope)
    for completion in output.context_completions:
        semantic_text.extend([completion.original_span, completion.interpretation])
    for other_id in other_ids:
        if any(other_id in value for value in semantic_text):
            raise ValueError("semantic text may not reference another candidate ID")


def validate_turn_output(
    raw: object, expected_candidate: str, expected_turn: int, user: str, agent: str,
    candidate_whitelist: Collection[str] | None = None,
    tool_result_spans: tuple[ToolResultSpan, ...] = (),
) -> dict[str, Any]:
    """Validate one raw response and materialize evidence spans without mutating the raw object."""
    try:
        output = TurnPassOutput.model_validate(raw)
    except ValidationError as error:
        raise ValueError(f"invalid TurnPassOutput: {error}") from error
    if output.candidate_id != expected_candidate:
        raise ValueError("candidate_id does not match expected candidate")
    if output.turn_index != expected_turn:
        raise ValueError("turn_index does not match expected turn")
    validate_tool_result_spans(agent, tool_result_spans)
    if candidate_whitelist is not None:
        _reject_cross_candidate_references(output, candidate_whitelist)
    knowledge_pattern = _expected_id("K", expected_candidate, expected_turn)
    completion_pattern = _expected_id("C", expected_candidate, expected_turn)
    if any(not knowledge_pattern.fullmatch(item.knowledge_id) for item in output.knowledge):
        raise ValueError("knowledge_id must use the expected candidate-scoped format")
    if any(not completion_pattern.fullmatch(item.completion_id) for item in output.context_completions):
        raise ValueError("completion_id must use the expected candidate-scoped format")
    if any(item.candidate_id != expected_candidate for item in output.knowledge):
        raise ValueError("knowledge candidate_id does not match expected candidate")
    if any(item.candidate_id != expected_candidate or item.turn_index != expected_turn for item in output.context_completions):
        raise ValueError("context completion candidate_id or turn_index does not match expected turn")

    completions: list[dict[str, Any]] = []
    for completion in output.context_completions:
        evidence = [
            resolved
            for draft in completion.evidence
            for resolved in _resolve(
                [draft], expected_candidate, expected_turn, user, agent,
                "user_reported" if draft.message == "user" else "agent_generated",
            )
        ]
        data = completion.model_dump(exclude={"evidence"})
        data["evidence"] = [item.model_dump(mode="json") for item in evidence]
        completions.append(data)

    knowledge: list[dict[str, Any]] = []
    for item in output.knowledge:
        evidence = _resolve(item.evidence, expected_candidate, expected_turn, user, agent, item.source_status)
        _validate_source_status(item.source_status, evidence, agent, tool_result_spans)
        persisted = Knowledge.model_validate({**item.model_dump(exclude={"evidence"}), "evidence": evidence})
        knowledge.append(persisted.model_dump(mode="json"))
    return {
        "candidate_id": expected_candidate,
        "turn_index": expected_turn,
        "context_completions": completions,
        "knowledge": knowledge,
    }


def validate_turn_batch(manifest_path: str | Path, raw_dir: str | Path, output_dir: str | Path) -> Path:
    """Validate the complete raw batch in memory before publishing any validated output."""
    manifest_file = Path(manifest_path)
    try:
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"could not parse turn payload manifest: {error}") from error
    if not isinstance(manifest, dict) or set(manifest) != {
        "prompt_version", "prompt_sha256", "prompt_file", "output_contract_sha256",
        "source_segments_file", "source_segments_sha256", "turns",
    }:
        raise ValueError("turn payload manifest has an unexpected schema")
    if not isinstance(manifest["turns"], list):
        raise ValueError("turn payload manifest turns must be a list")
    if manifest["prompt_version"] != PROMPT_VERSION:
        raise ValueError("turn payload manifest prompt version is invalid")
    prompt_file = Path(str(manifest["prompt_file"]))
    if not prompt_file.is_file():
        raise ValueError("turn prompt file is missing")
    prompt_sha256 = _sha256_bytes(prompt_file.read_bytes())
    output_contract = TurnPassOutput.model_json_schema()
    output_contract_sha256 = _schema_hash(output_contract)
    if manifest["prompt_sha256"] != prompt_sha256:
        raise ValueError("turn prompt SHA256 does not match the manifest")
    if manifest["output_contract_sha256"] != output_contract_sha256:
        raise ValueError("turn output contract SHA256 does not match the manifest")
    source_segments_file = Path(str(manifest["source_segments_file"]))
    if not source_segments_file.is_file():
        raise ValueError("source segments file is missing")
    source_segments_sha256 = _sha256_bytes(source_segments_file.read_bytes())
    if manifest["source_segments_sha256"] != source_segments_sha256:
        raise ValueError("source segments SHA256 does not match the manifest")
    expected: dict[str, dict[str, object]] = {}
    for item in manifest["turns"]:
        if not isinstance(item, dict) or set(item) != {
            "candidate_id", "candidate_index", "candidate_namespace", "turn_index", "source", "source_coordinates",
            "canonical_filename", "user_hash", "agent_hash", "payload_sha256", "prompt_sha256", "output_contract_sha256",
            "source_segments_sha256",
        }:
            raise ValueError("turn payload manifest contains an invalid turn entry")
        if not isinstance(item["candidate_id"], str) or not isinstance(item["candidate_index"], int) or isinstance(item["candidate_index"], bool) or not isinstance(item["turn_index"], int) or isinstance(item["turn_index"], bool):
            raise ValueError("turn payload manifest contains invalid candidate coordinates")
        filename = item["canonical_filename"]
        if filename != f"{item['candidate_index']:04d}-{item['turn_index']:04d}.json":
            raise ValueError("turn payload manifest canonical filename is invalid")
        if item["candidate_namespace"] != candidate_namespace(item["candidate_id"]):
            raise ValueError("turn payload manifest candidate namespace is invalid")
        if (
            item["prompt_sha256"] != prompt_sha256
            or item["output_contract_sha256"] != output_contract_sha256
            or item["source_segments_sha256"] != source_segments_sha256
        ):
            raise ValueError("turn payload manifest provenance hashes are invalid")
        if filename in expected:
            raise ValueError("turn payload manifest contains duplicate payload files")
        expected[filename] = item
    raw_path = Path(raw_dir).resolve()
    output_path = Path(output_dir).resolve()
    root = output_path / "knowledge-extraction" / "turn-pass"
    destination = (root / "validated").resolve()
    if raw_path == destination or raw_path.is_relative_to(destination) or destination.is_relative_to(raw_path):
        raise ValueError("raw_dir and validated destination must be disjoint, non-nested paths")
    if destination.exists():
        raise ValueError("validated turn-pass output already exists")
    actual = {path.name for path in raw_path.glob("*.json")} if raw_path.is_dir() else set()
    missing, extra = sorted(set(expected) - actual), sorted(actual - set(expected))
    if missing:
        raise ValueError(f"missing raw output files: {', '.join(missing)}")
    if extra:
        raise ValueError(f"extra raw output files: {', '.join(extra)}")

    validated: dict[str, dict[str, Any]] = {}
    raw_hashes: dict[str, tuple[str, str]] = {}
    payloads_dir = manifest_file.parent / "payloads"
    candidate_whitelist = {str(item["candidate_id"]) for item in expected.values()}
    source_units: list[TurnUnit] = []
    for filename, expected_item in expected.items():
        try:
            payload = json.loads((payloads_dir / filename).read_bytes())
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"could not parse payload {filename}: {error}") from error
        coordinates = payload.get("source_coordinates") if isinstance(payload, dict) else None
        if (
            not isinstance(payload, dict)
            or not isinstance(payload.get("user"), str)
            or not isinstance(payload.get("agent"), str)
            or not isinstance(coordinates, dict)
            or not isinstance(coordinates.get("user"), str)
            or not isinstance(coordinates.get("agent"), str)
        ):
            raise ValueError(f"payload {filename} cannot bind source segments")
        source_units.append(TurnUnit(
            candidate_id=str(expected_item["candidate_id"]),
            candidate_index=int(expected_item["candidate_index"]),
            turn_index=int(expected_item["turn_index"]),
            source=str(expected_item["source"]),
            user=payload["user"],
            agent=payload["agent"],
            user_pointer=coordinates["user"],
            agent_pointer=coordinates["agent"],
        ))
    source_segments = load_source_segments(source_segments_file, source_units)
    if source_segments.sha256 != source_segments_sha256:
        raise ValueError("source segments SHA256 changed during validation")
    for filename, expected_item in expected.items():
        try:
            payload_bytes = (payloads_dir / filename).read_bytes()
            raw_bytes = (raw_path / filename).read_bytes()
            payload = json.loads(payload_bytes)
            raw = json.loads(raw_bytes)
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"could not parse payload or raw output {filename}: {error}") from error
        if _sha256_bytes(payload_bytes) != expected_item["payload_sha256"]:
            raise ValueError(f"payload {filename} SHA256 does not match its manifest entry")
        if not isinstance(payload, dict) or set(payload) != {
            "prompt_version", "candidate_id", "turn_index", "source", "user", "agent", "source_coordinates",
            "output_contract", "candidate_namespace", "knowledge_id_prefix", "context_completion_id_prefix",
            "source_segments_sha256", "tool_result_spans",
        }:
            raise ValueError(f"payload {filename} has an unexpected schema")
        if not all(isinstance(payload[field], str) for field in ("prompt_version", "candidate_id", "source", "user", "agent", "candidate_namespace", "knowledge_id_prefix", "context_completion_id_prefix")) or not isinstance(payload["turn_index"], int) or isinstance(payload["turn_index"], bool) or not isinstance(payload["source_coordinates"], dict) or set(payload["source_coordinates"]) != {"user", "agent"} or not all(isinstance(value, str) for value in payload["source_coordinates"].values()) or not isinstance(payload["output_contract"], dict):
            raise ValueError(f"payload {filename} has invalid provenance field types")
        candidate_id = str(expected_item["candidate_id"])
        turn_index = int(expected_item["turn_index"])
        namespace = candidate_namespace(candidate_id)
        if (
            payload.get("prompt_version") != manifest["prompt_version"]
            or payload.get("candidate_id") != candidate_id
            or payload.get("turn_index") != turn_index
            or payload.get("source") != expected_item["source"]
            or payload.get("source_coordinates") != expected_item["source_coordinates"]
            or payload.get("candidate_namespace") != namespace
            or payload.get("knowledge_id_prefix") != f"K_{namespace}_{turn_index:03d}_"
            or payload.get("context_completion_id_prefix") != f"C_{namespace}_{turn_index:03d}_"
            or payload.get("source_segments_sha256") != source_segments_sha256
            or _sha256_bytes(payload["user"].encode("utf-8")) != expected_item["user_hash"]
            or _sha256_bytes(payload["agent"].encode("utf-8")) != expected_item["agent_hash"]
            or payload.get("output_contract") != output_contract
            or _schema_hash(payload.get("output_contract")) != output_contract_sha256
        ):
            raise ValueError(f"payload {filename} does not match its manifest entry")
        tool_result_spans = parse_tool_result_spans(payload.get("tool_result_spans"), str(payload["agent"]))
        if tool_result_spans != source_segments.for_turn(candidate_id, turn_index):
            raise ValueError(f"payload {filename} tool_result_spans differ from the source segments sidecar")
        try:
            validated[filename] = validate_turn_output(
                raw, candidate_id, turn_index, str(payload["user"]), str(payload["agent"]), candidate_whitelist,
                tool_result_spans,
            )
        except ValueError as error:
            raise ValueError(f"raw output {filename} failed validation: {error}") from error
        raw_after = _sha256_bytes((raw_path / filename).read_bytes())
        raw_before = _sha256_bytes(raw_bytes)
        if raw_before != raw_after:
            raise ValueError(f"raw output {filename} changed during validation")
        raw_hashes[filename] = (raw_before, raw_after)
    root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="validated-", dir=root))
    try:
        for filename, value in validated.items():
            _write_json(staging / filename, value)
        _write_json(staging / "manifest.json", {
            "prompt_version": manifest["prompt_version"],
            "prompt_sha256": manifest["prompt_sha256"],
            "output_contract_sha256": manifest["output_contract_sha256"],
            "source_segments_file": manifest["source_segments_file"],
            "source_segments_sha256": manifest["source_segments_sha256"],
            "turns": [
                {
                    "validated_file": name,
                    **expected[name],
                    "raw_sha256_before": raw_hashes[name][0],
                    "raw_sha256_after": raw_hashes[name][1],
                }
                for name in sorted(expected)
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
