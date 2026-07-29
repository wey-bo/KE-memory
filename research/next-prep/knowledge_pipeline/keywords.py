"""Preparation and deterministic validation for semantic keyword subagents."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, Mapping

from pydantic import ValidationError

from knowledge_pipeline.models import KeywordPassOutput
from knowledge_pipeline.turn_pass import candidate_namespace


PROMPT_VERSION = "knowledge-keyword-extraction-v2.1"
REQUIRED_PROMPT_SECTIONS = (
    "## Input Boundary",
    "## Output Contract",
    "## Completeness Checklist",
    "## Evidence Rules",
    "## Epistemic Rules",
    "## Forbidden Behavior",
    "## Final Self-Check",
)


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _schema_hash(schema: object) -> str:
    return _sha256(json.dumps(schema, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def _read_json(path: Path, label: str) -> tuple[bytes, dict[str, Any]]:
    try:
        data = path.read_bytes()
        value = json.loads(data.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"could not parse {label}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return data, value


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as output:
        json.dump(value, output, ensure_ascii=False, indent=2)
        output.write("\n")
        output.flush()
        os.fsync(output.fileno())


def prepare_keyword_payloads(
    final_knowledge_path: str | Path,
    output_dir: str | Path,
    prompt_path: str | Path,
) -> Path:
    """Write one active-knowledge-only payload per candidate."""
    final_file = Path(final_knowledge_path).resolve()
    prompt_file = Path(prompt_path).resolve()
    final_bytes, final = _read_json(final_file, "final knowledge")
    try:
        prompt_bytes = prompt_file.read_bytes()
        prompt_text = prompt_bytes.decode("utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise ValueError(f"could not read keyword prompt: {error}") from error
    missing_sections = [section for section in REQUIRED_PROMPT_SECTIONS if section not in prompt_text]
    if missing_sections:
        raise ValueError(f"keyword prompt is missing sections: {', '.join(missing_sections)}")
    active_ids = final.get("active_ids")
    records = final.get("records")
    if not isinstance(active_ids, list) or not isinstance(records, list):
        raise ValueError("final knowledge has invalid active_ids or records")
    if len(active_ids) != len(set(active_ids)):
        raise ValueError("final knowledge active_ids contain duplicates")
    active_set = set(active_ids)
    grouped: dict[str, list[dict[str, Any]]] = {}
    found: set[str] = set()
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("knowledge"), dict):
            raise ValueError("final knowledge contains an invalid record")
        knowledge = record["knowledge"]
        knowledge_id = knowledge.get("knowledge_id")
        candidate_id = knowledge.get("candidate_id")
        if knowledge_id not in active_set:
            continue
        if not isinstance(knowledge_id, str) or not isinstance(candidate_id, str):
            raise ValueError("active final knowledge has invalid identity")
        projection = record.get("projection")
        if not isinstance(projection, dict) or projection.get("status") not in {"active", "active_conflict"}:
            raise ValueError(f"active ID {knowledge_id} does not have an active projection status")
        found.add(knowledge_id)
        grouped.setdefault(candidate_id, []).append({
            **knowledge,
            "projection": projection,
        })
    if found != active_set:
        raise ValueError("final knowledge active_ids do not exactly match active records")

    schema = KeywordPassOutput.model_json_schema()
    schema_sha256 = _schema_hash(schema)
    destination = Path(output_dir).resolve()
    if destination.exists():
        raise ValueError("keyword prepared output already exists")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="keywords-prepared-", dir=destination.parent))
    entries: list[dict[str, Any]] = []
    try:
        payload_dir = staging / "payloads"
        payload_dir.mkdir()
        for index, candidate_id in enumerate(sorted(grouped)):
            knowledge = sorted(grouped[candidate_id], key=lambda item: str(item["knowledge_id"]))
            filename = f"{index:04d}.json"
            payload = {
                "prompt_version": PROMPT_VERSION,
                "candidate_id": candidate_id,
                "candidate_namespace": candidate_namespace(candidate_id),
                "final_knowledge_sha256": _sha256(final_bytes),
                "active_knowledge": knowledge,
                "keyword_id_prefix": f"KW_{candidate_namespace(candidate_id)}_",
                "output_contract": schema,
                "prompt_sha256": _sha256(prompt_bytes),
                "output_contract_sha256": schema_sha256,
            }
            payload_file = payload_dir / filename
            _write_json(payload_file, payload)
            entries.append({
                "candidate_id": candidate_id,
                "candidate_index": index,
                "canonical_filename": filename,
                "payload_file": f"payloads/{filename}",
                "payload_sha256": _sha256(payload_file.read_bytes()),
                "knowledge_ids": [item["knowledge_id"] for item in knowledge],
            })
        _write_json(staging / "manifest.json", {
            "prompt_version": PROMPT_VERSION,
            "prompt_file": str(prompt_file),
            "prompt_sha256": _sha256(prompt_bytes),
            "output_contract_sha256": schema_sha256,
            "final_knowledge_file": str(final_file),
            "final_knowledge_sha256": _sha256(final_bytes),
            "active_knowledge_count": len(active_ids),
            "candidates": entries,
        })
        os.replace(staging, destination)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        raise
    return destination / "manifest.json"


def _source_values(knowledge: Mapping[str, Any], source_field: str) -> list[str]:
    if source_field in {"statement", "subject", "predicate", "object"}:
        value = knowledge.get(source_field)
    elif source_field.startswith("qualifiers."):
        qualifiers = knowledge.get("qualifiers")
        value = qualifiers.get(source_field.split(".", 1)[1]) if isinstance(qualifiers, Mapping) else None
    else:
        raise ValueError(f"unsupported keyword source_field: {source_field}")
    if isinstance(value, str):
        return [value]
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return value
    return []


def validate_keyword_output(raw: object, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate one candidate output without mutating model JSON."""
    try:
        output = KeywordPassOutput.model_validate(raw)
    except ValidationError as error:
        raise ValueError(f"invalid KeywordPassOutput: {error}") from error
    candidate_id = payload.get("candidate_id")
    if output.candidate_id != candidate_id:
        raise ValueError("keyword output candidate_id mismatch")
    active_knowledge = payload.get("active_knowledge")
    if not isinstance(active_knowledge, list):
        raise ValueError("keyword payload active_knowledge is invalid")
    by_id = {
        item["knowledge_id"]: item
        for item in active_knowledge
        if isinstance(item, dict) and isinstance(item.get("knowledge_id"), str)
    }
    item_ids = [item.knowledge_id for item in output.items]
    if len(item_ids) != len(set(item_ids)) or set(item_ids) != set(by_id):
        raise ValueError("keyword output coverage does not exactly match active knowledge")
    keyword_ids: list[str] = []
    for item in output.items:
        knowledge = by_id[item.knowledge_id]
        if not any(keyword.keyword_kind == "lexical" for keyword in item.keywords):
            raise ValueError("each knowledge item requires at least one lexical keyword")
        for keyword in item.keywords:
            if keyword.knowledge_id != item.knowledge_id:
                raise ValueError("keyword knowledge_id does not match its parent item")
            values = _source_values(knowledge, keyword.source_field)
            if not any(keyword.surface in value for value in values):
                raise ValueError("keyword surface is not traceable to source_field")
            keyword_ids.append(keyword.keyword_id)
        normalized_keys = [
            json.dumps(
                {**_canonical_descriptor(keyword.model_dump(mode="json")), "semantic_role": keyword.semantic_role},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            for keyword in item.keywords
        ]
        if len(normalized_keys) != len(set(normalized_keys)):
            raise ValueError("duplicate normalized keyword within one knowledge item")
        qualifiers = knowledge.get("qualifiers")
        if not isinstance(qualifiers, Mapping):
            raise ValueError("keyword knowledge qualifiers are invalid")
        coverage_rules = (
            ("temporal", "qualifiers.temporal", "time"),
            ("conditions", "qualifiers.conditions", "condition"),
            ("scope", "qualifiers.scope", None),
        )
        for qualifier_name, source_field, semantic_role in coverage_rules:
            qualifier_values = qualifiers.get(qualifier_name)
            if not isinstance(qualifier_values, list) or not all(isinstance(value, str) for value in qualifier_values):
                raise ValueError(f"keyword knowledge {qualifier_name} qualifier is invalid")
            for qualifier_value in qualifier_values:
                covered = any(
                    keyword.source_field == source_field
                    and keyword.surface in qualifier_value
                    and (semantic_role is None or keyword.semantic_role == semantic_role)
                    for keyword in item.keywords
                )
                if not covered:
                    label = "condition" if qualifier_name == "conditions" else qualifier_name
                    raise ValueError(f"missing {label} qualifier keyword coverage")
        modality = qualifiers.get("modality")
        modality_covered = any(
            keyword.source_field == "qualifiers.modality"
            and keyword.keyword_kind == "qualifier"
            and keyword.keyword_type == "modality"
            and keyword.normalized_value == modality
            for keyword in item.keywords
        )
        if not modality_covered:
            raise ValueError("missing modality qualifier keyword coverage")
        polarity = qualifiers.get("polarity")
        if polarity == "negative":
            polarity_covered = any(
                keyword.source_field == "qualifiers.polarity"
                and keyword.keyword_kind == "qualifier"
                and keyword.keyword_type == "polarity"
                and keyword.semantic_role == "polarity"
                and keyword.normalized_value == "negative"
                for keyword in item.keywords
            )
            if not polarity_covered:
                raise ValueError("missing negative polarity qualifier keyword coverage")
    prefix = payload.get("keyword_id_prefix")
    if not isinstance(prefix, str) or not prefix:
        raise ValueError("keyword payload has no valid keyword_id_prefix")
    pattern = re.compile(rf"{re.escape(prefix)}([0-9]{{4}})")
    indices: list[int] = []
    for keyword_id in keyword_ids:
        match = pattern.fullmatch(keyword_id)
        if match is None:
            raise ValueError("keyword ID is outside the candidate namespace")
        indices.append(int(match.group(1)))
    if indices != list(range(1, len(indices) + 1)):
        raise ValueError("keyword IDs must be contiguous from 0001 in canonical order")
    return output.model_dump(mode="json")


def _canonical_descriptor(keyword: Mapping[str, Any]) -> dict[str, Any]:
    kind = keyword.get("keyword_kind")
    if kind == "lexical":
        return {
            "keyword_kind": kind,
            "query_lemma": str(keyword.get("query_lemma", "")).strip().casefold(),
            "part_of_speech": keyword.get("part_of_speech"),
            "keyword_type": keyword.get("keyword_type"),
            "sense_key": keyword.get("sense_key"),
            "lookup_targets": sorted(keyword.get("lookup_targets", [])),
        }
    return {
        "keyword_kind": kind,
        "normalized_value": str(keyword.get("normalized_value", "")).strip().casefold(),
        "datatype": keyword.get("datatype"),
        "keyword_type": keyword.get("keyword_type"),
        "lookup_targets": sorted(keyword.get("lookup_targets", [])),
    }


def attach_canonical_keywords(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach stable canonical IDs to occurrence keywords and return their registry."""
    registry: dict[str, dict[str, Any]] = {}
    sense_descriptors: dict[str, tuple[str, str, str, str]] = {}
    for candidate in candidates:
        for item in candidate.get("items", []):
            for keyword in item.get("keywords", []):
                if keyword.get("keyword_kind") == "lexical":
                    sense_key = str(keyword.get("sense_key", ""))
                    sense_descriptor = (
                        str(keyword.get("query_lemma", "")).strip().casefold(),
                        str(keyword.get("part_of_speech", "")),
                        str(keyword.get("keyword_type", "")),
                        str(keyword.get("sense_hint", "")).strip().casefold(),
                    )
                    previous = sense_descriptors.setdefault(sense_key, sense_descriptor)
                    if previous != sense_descriptor:
                        raise ValueError(f"sense_key {sense_key} maps to multiple lexical descriptors")
                descriptor = _canonical_descriptor(keyword)
                canonical_bytes = json.dumps(
                    descriptor,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
                canonical_id = f"CK_{_sha256(canonical_bytes)[:16]}"
                keyword["canonical_id"] = canonical_id
                registry.setdefault(canonical_id, {"canonical_id": canonical_id, **descriptor})
    return [registry[canonical_id] for canonical_id in sorted(registry)]


def _load_keyword_manifest(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    _, manifest = _read_json(path, "keyword prepared manifest")
    entries = manifest.get("candidates")
    if not isinstance(entries, list):
        raise ValueError("keyword prepared manifest has invalid candidates")
    final_file = Path(str(manifest.get("final_knowledge_file", "")))
    prompt_file = Path(str(manifest.get("prompt_file", "")))
    if not final_file.is_file() or _sha256(final_file.read_bytes()) != manifest.get("final_knowledge_sha256"):
        raise ValueError("final knowledge hash mismatch")
    if not prompt_file.is_file() or _sha256(prompt_file.read_bytes()) != manifest.get("prompt_sha256"):
        raise ValueError("keyword prompt hash mismatch")
    payloads: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("keyword manifest entry is invalid")
        payload_file = path.parent / str(entry.get("payload_file", ""))
        payload_bytes, payload = _read_json(payload_file, "keyword payload")
        if _sha256(payload_bytes) != entry.get("payload_sha256"):
            raise ValueError("keyword payload hash mismatch")
        if payload.get("final_knowledge_sha256") != manifest.get("final_knowledge_sha256"):
            raise ValueError("keyword payload final knowledge hash mismatch")
        if payload.get("prompt_sha256") != manifest.get("prompt_sha256"):
            raise ValueError("keyword payload prompt hash mismatch")
        if payload.get("output_contract_sha256") != manifest.get("output_contract_sha256"):
            raise ValueError("keyword payload output contract hash mismatch")
        payloads.append(payload)
    return manifest, payloads


def validate_keyword_batch(
    manifest_path: str | Path,
    raw_dir: str | Path,
    output_path: str | Path,
) -> Path:
    """Validate all candidate keyword outputs and atomically publish one aggregate."""
    manifest_file = Path(manifest_path).resolve()
    raw_path = Path(raw_dir).resolve()
    manifest, payloads = _load_keyword_manifest(manifest_file)
    entries = manifest["candidates"]
    expected = {entry["canonical_filename"] for entry in entries}
    actual = {path.name for path in raw_path.glob("*.json")} if raw_path.is_dir() else set()
    if expected != actual:
        missing, extra = sorted(expected - actual), sorted(actual - expected)
        if missing:
            raise ValueError(f"missing raw keyword outputs: {', '.join(missing)}")
        raise ValueError(f"extra raw keyword outputs: {', '.join(extra)}")
    validated: list[dict[str, Any]] = []
    raw_hashes: list[dict[str, str]] = []
    for entry, payload in zip(entries, payloads, strict=True):
        raw_file = raw_path / entry["canonical_filename"]
        raw_before_bytes, raw = _read_json(raw_file, f"raw keyword output {raw_file.name}")
        before = _sha256(raw_before_bytes)
        validated.append(validate_keyword_output(raw, payload))
        after = _sha256(raw_file.read_bytes())
        if before != after:
            raise ValueError(f"raw keyword output changed during validation: {raw_file.name}")
        raw_hashes.append({"file": raw_file.name, "raw_sha256_before": before, "raw_sha256_after": after})
    canonical_keywords = attach_canonical_keywords(validated)
    aggregate = {
        "schema_version": "keyword-pass-v2",
        "prompt_version": manifest["prompt_version"],
        "prompt_sha256": manifest["prompt_sha256"],
        "output_contract_sha256": manifest["output_contract_sha256"],
        "final_knowledge_sha256": manifest["final_knowledge_sha256"],
        "active_knowledge_count": manifest["active_knowledge_count"],
        "canonical_keywords": canonical_keywords,
        "candidates": validated,
        "raw_hashes": raw_hashes,
    }
    destination = Path(output_path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.with_name(destination.name + ".new")
    try:
        _write_json(staging, aggregate)
        os.replace(staging, destination)
    except Exception:
        staging.unlink(missing_ok=True)
        raise
    return destination
