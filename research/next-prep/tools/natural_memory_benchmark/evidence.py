from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .io import load_json, write_json_immutable
from .models import EvidenceUnit, GoldArtifact, PublicSliceArtifact


def _parse_source_ref(source_ref: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for part in source_ref.split(";"):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        parsed[key] = value
    return parsed


def _unique_ordered(refs: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for ref in refs:
        if ref not in seen:
            seen.add(ref)
            ordered.append(ref)
    return ordered


def _unit_sort_key(unit: EvidenceUnit) -> tuple[int, str]:
    if unit.unit_id.isdigit():
        return (int(unit.unit_id), unit.unit_id)
    if unit.unit_id.startswith("D") and ":" in unit.unit_id:
        session, turn = unit.unit_id.removeprefix("D").split(":", 1)
        if session.isdigit() and turn.isdigit():
            return (int(session) * 10000 + int(turn), unit.unit_id)
    return (10**9, unit.unit_id)


def _load_beam_message_index(path: Path, conversation_id: str) -> dict[str, EvidenceUnit]:
    # Same contract as loaders.load_beam_candidates: source validation is part of
    # the evidence chain, so a missing reader is a failure, not a skip.
    from .evaluation_environment import require_duckdb

    duckdb = require_duckdb()

    connection = duckdb.connect()
    row = connection.execute(
        "select chat from read_parquet(?) where conversation_id=?",
        [str(path), conversation_id],
    ).fetchone()
    if row is None:
        raise ValueError(f"BEAM conversation_id not found: {conversation_id}")
    index: dict[str, EvidenceUnit] = {}
    for session_index, session in enumerate(row[0], start=1):
        for message_index, message in enumerate(session, start=1):
            unit_id = str(message["id"])
            text = str(message.get("content") or "").strip()
            if not text:
                continue
            index[unit_id] = EvidenceUnit(
                benchmark="beam",
                source_id="beam-100K",
                unit_id=unit_id,
                source_ref=f"conversation_id={conversation_id};message_id={unit_id};session_index={session_index};message_index={message_index}",
                text=text,
                metadata={
                    "role": message.get("role"),
                    "time_anchor": message.get("time_anchor"),
                    "question_type": message.get("question_type"),
                    "index": message.get("index"),
                },
            )
    return index


def _load_locomo_dialogue_index(path: Path, sample_id: str) -> dict[str, EvidenceUnit]:
    data = json.loads(path.read_text(encoding="utf-8"))
    sample = next((item for item in data if str(item.get("sample_id")) == sample_id), None)
    if sample is None:
        raise ValueError(f"LoCoMo sample_id not found: {sample_id}")
    conversation = sample["conversation"]
    index: dict[str, EvidenceUnit] = {}
    for key, value in conversation.items():
        if not key.startswith("session_") or key.endswith("_date_time") or not isinstance(value, list):
            continue
        session_number = key.removeprefix("session_")
        for message in value:
            unit_id = str(message["dia_id"])
            index[unit_id] = EvidenceUnit(
                benchmark="locomo",
                source_id="locomo10",
                unit_id=unit_id,
                source_ref=f"sample_id={sample_id};session={session_number};dia_id={unit_id}",
                text=str(message["text"]).strip(),
                metadata={"speaker": message.get("speaker")},
            )
    return index


def _load_longmemeval_session_index(path: Path, question_id: str) -> dict[str, EvidenceUnit]:
    data = json.loads(path.read_text(encoding="utf-8"))
    item = next((entry for entry in data if str(entry.get("question_id")) == question_id), None)
    if item is None:
        raise ValueError(f"LongMemEval question_id not found: {question_id}")
    index: dict[str, EvidenceUnit] = {}
    for session_id, session in zip(item["haystack_session_ids"], item["haystack_sessions"], strict=True):
        text_parts = [f"{message.get('role', 'unknown')}: {message.get('content', '')}" for message in session]
        index[str(session_id)] = EvidenceUnit(
            benchmark="longmemeval",
            source_id="longmemeval-oracle",
            unit_id=str(session_id),
            source_ref=f"question_id={question_id};session_id={session_id}",
            text="\n".join(part.strip() for part in text_parts if part.strip()),
            metadata={
                "message_count": len(session),
                "has_answer_count": sum(1 for message in session if message.get("has_answer")),
            },
        )
    return index


def resolve_gold_evidence_units(root: Path, slice_id: str = "slice-v1") -> dict[str, list[dict[str, Any]]]:
    public_slice = PublicSliceArtifact.model_validate(load_json(root / slice_id / "slice.json"))
    gold = GoldArtifact.model_validate(load_json(root / slice_id / "gold.json"))
    if [item["item_id"] for item in public_slice.public_items] != [item["item_id"] for item in gold.items]:
        raise ValueError("public slice and gold item ids diverge")

    beam_cache: dict[str, dict[str, EvidenceUnit]] = {}
    locomo_cache: dict[str, dict[str, EvidenceUnit]] = {}
    longmem_cache: dict[str, dict[str, EvidenceUnit]] = {}
    resolved: dict[str, list[dict[str, Any]]] = {}

    for item in gold.items:
        evidence_refs = _unique_ordered([str(ref) for ref in item.get("evidence_refs", [])])
        if not evidence_refs:
            resolved[item["item_id"]] = []
            continue
        source_ref = _parse_source_ref(str(item["source_ref"]))
        if item["benchmark"] == "beam":
            conversation_id = source_ref["conversation_id"]
            index = beam_cache.setdefault(
                conversation_id,
                _load_beam_message_index(root / "raw" / "beam" / "100K-00000-of-00001.parquet", conversation_id),
            )
        elif item["benchmark"] == "locomo":
            sample_id = source_ref["sample_id"]
            index = locomo_cache.setdefault(
                sample_id,
                _load_locomo_dialogue_index(root / "raw" / "locomo" / "locomo10.json", sample_id),
            )
        elif item["benchmark"] == "longmemeval":
            question_id = source_ref["question_id"]
            index = longmem_cache.setdefault(
                question_id,
                _load_longmemeval_session_index(root / "raw" / "longmemeval" / "longmemeval_oracle.json", question_id),
            )
        else:  # pragma: no cover - pydantic protects this
            raise ValueError(f"unsupported benchmark: {item['benchmark']}")
        missing = [ref for ref in evidence_refs if ref not in index]
        if missing:
            raise ValueError(f"unresolved evidence refs for {item['item_id']}: {missing}")
        resolved[item["item_id"]] = [index[ref].model_dump(mode="json") for ref in evidence_refs]
    return resolved


def build_item_evidence_corpus(root: Path, slice_id: str = "slice-v1") -> dict[str, list[dict[str, Any]]]:
    public_slice = PublicSliceArtifact.model_validate(load_json(root / slice_id / "slice.json"))
    beam_cache: dict[str, dict[str, EvidenceUnit]] = {}
    locomo_cache: dict[str, dict[str, EvidenceUnit]] = {}
    longmem_cache: dict[str, dict[str, EvidenceUnit]] = {}
    corpus: dict[str, list[dict[str, Any]]] = {}

    for item in public_slice.public_items:
        source_ref = _parse_source_ref(str(item["source_ref"]))
        if item["benchmark"] == "beam":
            conversation_id = source_ref["conversation_id"]
            index = beam_cache.setdefault(
                conversation_id,
                _load_beam_message_index(root / "raw" / "beam" / "100K-00000-of-00001.parquet", conversation_id),
            )
        elif item["benchmark"] == "locomo":
            sample_id = source_ref["sample_id"]
            index = locomo_cache.setdefault(
                sample_id,
                _load_locomo_dialogue_index(root / "raw" / "locomo" / "locomo10.json", sample_id),
            )
        elif item["benchmark"] == "longmemeval":
            question_id = source_ref["question_id"]
            index = longmem_cache.setdefault(
                question_id,
                _load_longmemeval_session_index(root / "raw" / "longmemeval" / "longmemeval_oracle.json", question_id),
            )
        else:  # pragma: no cover - pydantic protects this
            raise ValueError(f"unsupported benchmark: {item['benchmark']}")
        corpus[item["item_id"]] = [
            unit.model_dump(mode="json")
            for unit in sorted(index.values(), key=_unit_sort_key)
        ]
    return corpus


def export_evidence_corpus_file(root: Path, slice_id: str, output_path: Path) -> dict[str, Any]:
    items = build_item_evidence_corpus(root, slice_id)
    payload = {
        "schema_version": "natural-benchmark-evidence-corpus-v1",
        "slice_id": slice_id,
        "item_count": len(items),
        "items": items,
    }
    write_json_immutable(output_path, payload)
    return payload


def export_gold_evidence_file(root: Path, slice_id: str, output_path: Path) -> dict[str, Any]:
    items = resolve_gold_evidence_units(root, slice_id)
    payload = {
        "schema_version": "natural-benchmark-gold-evidence-v1",
        "slice_id": slice_id,
        "item_count": len(items),
        "items": items,
    }
    write_json_immutable(output_path, payload)
    return payload
