"""Review-oriented JSON export grouped by dialogue, turn, and speaker role."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _read_json(path: Path, label: str) -> tuple[bytes, dict[str, Any]]:
    try:
        data = path.read_bytes()
        value = json.loads(data.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"could not parse {label}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return data, value


def _knowledge_role(record: Mapping[str, Any]) -> str:
    knowledge = record.get("knowledge")
    if not isinstance(knowledge, Mapping):
        raise ValueError("final knowledge record is invalid")
    status = knowledge.get("source_status")
    if status == "user_reported":
        return "user"
    if status in {"agent_generated", "tool_observed"}:
        return "agent"
    raise ValueError(f"unsupported knowledge source_status: {status}")


def _evidence_turns(record: Mapping[str, Any]) -> set[int]:
    knowledge = record["knowledge"]
    evidence = knowledge.get("evidence")
    if not isinstance(evidence, list):
        raise ValueError("knowledge evidence is invalid")
    turns = {
        item.get("turn_index")
        for item in evidence
        if isinstance(item, Mapping) and isinstance(item.get("turn_index"), int)
    }
    return {item for item in turns if item >= 0}


def _display_knowledge(knowledge: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "statement": knowledge.get("statement"),
        "subject": knowledge.get("subject"),
        "predicate": knowledge.get("predicate"),
        "object": knowledge.get("object"),
        "qualifiers": knowledge.get("qualifiers"),
    }


def _display_keyword_item(item: Mapping[str, Any]) -> dict[str, Any]:
    displayed_keywords = []
    for keyword in item.get("keywords", []):
        if "keyword" in keyword:
            displayed = {"keyword": keyword.get("keyword")}
            if keyword.get("wordnet_synset") is not None:
                displayed["wordnet"] = {
                    "synset": keyword.get("wordnet_synset"),
                    "lemma": keyword.get("wordnet_lemma"),
                    "pos": keyword.get("wordnet_pos"),
                }
            displayed_keywords.append(displayed)
            continue
        displayed = {
            "surface": keyword.get("surface"),
            "normalized_zh": keyword.get("normalized_zh"),
            "lemma": keyword.get("query_lemma"),
            "kind": keyword.get("keyword_kind"),
            "type": keyword.get("keyword_type"),
            "role": keyword.get("semantic_role"),
        }
        optional = {
            "value": keyword.get("normalized_value"),
            "datatype": keyword.get("datatype"),
            "unit": keyword.get("unit"),
        }
        displayed.update({key: value for key, value in optional.items() if value is not None})
        displayed_keywords.append({key: value for key, value in displayed.items() if value is not None})
    return {
        "knowledge_id": item.get("knowledge_id"),
        "keywords": displayed_keywords,
    }


def build_turn_grouped_export(
    source_path: str | Path,
    final_knowledge_path: str | Path,
    keyword_pass_path: str | Path,
) -> list[dict[str, Any]]:
    """Build a display-only list where every item is exactly one dialogue turn."""
    source_file = Path(source_path).resolve()
    final_file = Path(final_knowledge_path).resolve()
    keyword_file = Path(keyword_pass_path).resolve()
    source_bytes, source = _read_json(source_file, "source dialogue")
    final_bytes, final = _read_json(final_file, "final knowledge")
    keyword_bytes, keyword_pass = _read_json(keyword_file, "keyword pass")
    if keyword_pass.get("final_knowledge_sha256") != _sha256(final_bytes):
        raise ValueError("keyword pass does not reference the exact final knowledge file")
    candidates = source.get("candidates")
    records = final.get("records")
    active_ids = final.get("active_ids")
    keyword_candidates = keyword_pass.get("candidates")
    canonical_keywords = keyword_pass.get("canonical_keywords")
    if not all(isinstance(value, list) for value in (candidates, records, active_ids, keyword_candidates, canonical_keywords)):
        raise ValueError("source/final/keyword collections are invalid")

    keyword_by_id: dict[str, dict[str, Any]] = {}
    for candidate in keyword_candidates:
        if not isinstance(candidate, dict) or not isinstance(candidate.get("items"), list):
            raise ValueError("keyword candidate output is invalid")
        for item in candidate["items"]:
            if not isinstance(item, dict) or not isinstance(item.get("knowledge_id"), str):
                raise ValueError("keyword item is invalid")
            knowledge_id = item["knowledge_id"]
            if knowledge_id in keyword_by_id:
                raise ValueError(f"duplicate keyword coverage for {knowledge_id}")
            keyword_by_id[knowledge_id] = item
    active_set = set(active_ids)
    if set(keyword_by_id) != active_set:
        raise ValueError("keyword coverage does not exactly match active knowledge IDs")

    source_by_id: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        if not isinstance(candidate, dict) or not isinstance(candidate.get("id"), str):
            raise ValueError("source candidate is invalid")
        if candidate["id"] in source_by_id:
            raise ValueError(f"duplicate source candidate {candidate['id']}")
        source_by_id[candidate["id"]] = candidate
    active_records: dict[str, list[dict[str, Any]]] = {candidate_id: [] for candidate_id in source_by_id}
    found_active: set[str] = set()
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("knowledge"), dict):
            raise ValueError("final knowledge record is invalid")
        knowledge_id = record["knowledge"].get("knowledge_id")
        candidate_id = record["knowledge"].get("candidate_id")
        if not isinstance(knowledge_id, str) or candidate_id not in source_by_id:
            raise ValueError("final knowledge identity is outside source candidates")
        if knowledge_id in active_set:
            active_records[candidate_id].append(record)
            found_active.add(knowledge_id)
    if found_active != active_set:
        raise ValueError("active knowledge IDs do not exactly match final records")

    exported_turns: list[dict[str, Any]] = []
    placed_ids: set[str] = set()
    for candidate in candidates:
        candidate_id = candidate["id"]
        turns = candidate.get("turns")
        if not isinstance(turns, list):
            raise ValueError(f"source turns are invalid for {candidate_id}")
        turn_views = []
        for index, turn in enumerate(turns):
            if not isinstance(turn, dict) or set(turn) != {"user", "agent"}:
                raise ValueError(f"source turn {candidate_id}/{index} is invalid")
            turn_views.append({
                "原始文本": {"user": turn["user"], "agent": turn["agent"]},
                "知识": {"user": [], "agent": []},
                "关键词": {"user": [], "agent": []},
            })
        for record in sorted(active_records[candidate_id], key=lambda item: item["knowledge"]["knowledge_id"]):
            knowledge_id = record["knowledge"]["knowledge_id"]
            role = _knowledge_role(record)
            evidence_turns = _evidence_turns(record)
            keyword_item = keyword_by_id[knowledge_id]
            if evidence_turns:
                turn_index = max(evidence_turns)
            else:
                projection = record.get("projection")
                turn_index = projection.get("source_turn") if isinstance(projection, Mapping) else None
            if not isinstance(turn_index, int) or turn_index < 0 or turn_index >= len(turn_views):
                raise ValueError(f"knowledge cannot be assigned to a source turn: {knowledge_id}")
            turn_views[turn_index]["知识"][role].append(_display_knowledge(record["knowledge"]))
            turn_views[turn_index]["关键词"][role].append(_display_keyword_item(keyword_item)["keywords"])
            if knowledge_id in placed_ids:
                raise ValueError(f"active knowledge was placed more than once: {knowledge_id}")
            placed_ids.add(knowledge_id)
        exported_turns.extend(turn_views)
    if placed_ids != active_set:
        raise ValueError("not every active knowledge record was placed exactly once")
    return exported_turns


def write_turn_grouped_export(
    source_path: str | Path,
    final_knowledge_path: str | Path,
    keyword_pass_path: str | Path,
    output_path: str | Path,
) -> str:
    """Atomically write a deterministic UTF-8 final JSON export and return its hash."""
    value = build_turn_grouped_export(source_path, final_knowledge_path, keyword_pass_path)
    content = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    destination = Path(output_path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.with_name(destination.name + ".new")
    try:
        staging.write_bytes(content)
        os.replace(staging, destination)
    except Exception:
        staging.unlink(missing_ok=True)
        raise
    return _sha256(content)
