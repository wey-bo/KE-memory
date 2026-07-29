from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


KEOL_COMMIT = "44631e64fd07c9b85f22e36035bf49c882dba592"


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    if not slug:
        raise ValueError(f"cannot create a stable slug from {value!r}")
    return slug


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def build_turn_units(ke_test: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = ke_test.get("candidates")
    if not isinstance(candidates, list):
        raise ValueError("KE-test must contain a candidates array")

    units: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for candidate_index, candidate in enumerate(candidates):
        candidate_id = str(candidate.get("id") or "").strip()
        turns = candidate.get("turns")
        if not candidate_id or not isinstance(turns, list):
            raise ValueError(f"invalid candidate at index {candidate_index}")
        for turn_offset, turn in enumerate(turns):
            turn_index = turn_offset + 1
            user = turn.get("user")
            agent = turn.get("agent")
            if not isinstance(user, str) or not isinstance(agent, str):
                raise ValueError(f"invalid turn {turn_index} in {candidate_id}")
            unit_id = f"{_slug(candidate_id)}__turn-{turn_index:03d}"
            if unit_id in seen_ids:
                raise ValueError(f"duplicate unit id: {unit_id}")
            seen_ids.add(unit_id)
            units.append(
                {
                    "unit_id": unit_id,
                    "candidate_id": candidate_id,
                    "candidate_index": candidate_index,
                    "turn_index": turn_index,
                    "json_pointer": f"/candidates/{candidate_index}/turns/{turn_offset}",
                    "source": candidate.get("source", ""),
                    "user": user,
                    "agent": agent,
                    "text": f"用户：\n{user}\n\nAgent：\n{agent}",
                }
            )
    return units


def write_turn_bundle(units: list[dict[str, Any]], output_dir: Path) -> Path:
    turns_dir = output_dir / "turns"
    turns_dir.mkdir(parents=True, exist_ok=True)
    manifest_units: list[dict[str, Any]] = []
    for unit in units:
        relative_path = f"turns/{unit['unit_id']}.txt"
        (output_dir / relative_path).write_text(unit["text"], encoding="utf-8")
        manifest_units.append(
            {
                key: value
                for key, value in unit.items()
                if key != "text"
            }
            | {"text_path": relative_path}
        )
    manifest_path = output_dir / "manifest.json"
    _write_json(
        manifest_path,
        {
            "schema_version": "keol_turn_bundle_v1",
            "source": "data/gold-candidates/KE-test.json",
            "keol_commit": KEOL_COMMIT,
            "unit_count": len(units),
            "units": manifest_units,
        },
    )
    return manifest_path


def merge_model_graph_batches(batches: list[dict[str, Any]]) -> dict[str, Any]:
    merged_units: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    providers: list[str] = []
    for batch in batches:
        if batch.get("keol_commit") != KEOL_COMMIT:
            raise ValueError("model graph batch uses the wrong KEOL commit")
        provider = str(batch.get("model_provider") or "").strip()
        if provider and provider not in providers:
            providers.append(provider)
        graph_units = batch.get("units")
        if not isinstance(graph_units, list):
            raise ValueError("model graph batch must contain a units array")
        for graph in graph_units:
            unit_id = str(graph.get("unit_id") or "").strip()
            if unit_id in seen_ids:
                raise ValueError(f"duplicate model graph unit: {unit_id}")
            seen_ids.add(unit_id)
            merged_units.append(graph)
    return {
        "keol_commit": KEOL_COMMIT,
        "model_provider": "+".join(providers) or "codex_subagent",
        "units": merged_units,
    }


def validate_model_graphs(
    units: list[dict[str, Any]], payload: dict[str, Any]
) -> None:
    if payload.get("keol_commit") != KEOL_COMMIT:
        raise ValueError("model graph KEOL commit does not match the required commit")
    graph_units = payload.get("units")
    if not isinstance(graph_units, list):
        raise ValueError("model graph payload must contain a units array")

    expected_ids = [unit["unit_id"] for unit in units]
    actual_ids = [graph.get("unit_id") for graph in graph_units]
    if len(actual_ids) != len(set(actual_ids)):
        raise ValueError("model graph contains duplicate unit ids")
    if set(expected_ids) != set(actual_ids):
        missing = sorted(set(expected_ids) - set(actual_ids))
        extra = sorted(set(actual_ids) - set(expected_ids))
        raise ValueError(f"model graph unit coverage mismatch: missing={missing}, extra={extra}")

    for graph in graph_units:
        unit_id = graph["unit_id"]
        nodes = graph.get("nodes")
        edges = graph.get("edges")
        if not isinstance(nodes, list) or not isinstance(edges, list):
            raise ValueError(f"{unit_id}: nodes and edges must be arrays")
        node_ids: set[str] = set()
        for node in nodes:
            node_id = str(node.get("id") or "").strip()
            name = str(node.get("name") or "").strip()
            node_type = str(node.get("type") or "").strip()
            if not node_id or not name or not node_type:
                raise ValueError(f"{unit_id}: every node needs id, name, and type")
            if node_id in node_ids:
                raise ValueError(f"{unit_id}: duplicate node id {node_id}")
            node_ids.add(node_id)
        for edge in edges:
            source_id = str(edge.get("source_node_id") or "").strip()
            target_id = str(edge.get("target_node_id") or "").strip()
            relation = str(edge.get("relationship_name") or "").strip()
            if source_id not in node_ids:
                raise ValueError(f"{unit_id}: edge references unknown source node {source_id}")
            if target_id not in node_ids:
                raise ValueError(f"{unit_id}: edge references unknown target node {target_id}")
            if not relation:
                raise ValueError(f"{unit_id}: edge relationship_name is required")


def materialize_keol_dataset(
    units: list[dict[str, Any]],
    payload: dict[str, Any],
    output_root: Path,
    dataset_name: str,
) -> Path:
    validate_model_graphs(units, payload)
    dataset_root = output_root / dataset_name
    graphs_by_id = {graph["unit_id"]: graph for graph in payload["units"]}
    text_sources: list[dict[str, Any]] = []

    for unit in units:
        unit_id = unit["unit_id"]
        source_id = f"src_{unit_id.replace('-', '_')}"
        source_path = f"text/{source_id}"
        original_file = f"artifacts/keol-baseline/input/turns/{unit_id}.txt"
        chunk_id = "chunk_" + hashlib.sha256(
            f"{unit_id}\0{unit['text']}".encode("utf-8")
        ).hexdigest()[:20]
        graph = graphs_by_id[unit_id]

        entities = []
        for node in graph["nodes"]:
            entities.append(
                {
                    "id": node["id"],
                    "name": node["name"],
                    "type": node["type"],
                    "description": node.get("description", ""),
                    "source_chunk_id": chunk_id,
                }
            )
        relations = []
        for edge in graph["edges"]:
            relations.append(
                {
                    "source_entity": edge["source_node_id"],
                    "target_entity": edge["target_node_id"],
                    "relation_type": edge["relationship_name"],
                    "description": edge.get("description", ""),
                }
            )

        turn_metadata = {
            "unit_id": unit_id,
            "candidate_id": unit["candidate_id"],
            "turn_index": unit["turn_index"],
            "json_pointer": unit["json_pointer"],
            "source": unit["source"],
            "speaker_order": ["user", "agent"],
        }
        _write_json(
            dataset_root / source_path / "chunk_000.json",
            {
                "source": {
                    "source_id": source_id,
                    "file": original_file,
                    "file_type": "txt",
                    "category": "text",
                    "metadata": turn_metadata,
                },
                "chunk": {
                    "id": chunk_id,
                    "index": 0,
                    "text": unit["text"],
                    "size": len(unit["text"]),
                    "metadata": turn_metadata,
                },
                "entities": entities,
                "relations": relations,
            },
        )
        text_sources.append(
            {
                "source_id": source_id,
                "source_name": unit_id,
                "display_name": f"{unit_id}.txt",
                "original_file": original_file,
                "file_type": "txt",
                "path": source_path,
                "metadata": turn_metadata,
            }
        )

    _write_json(
        dataset_root / "_metadata.json",
        {
            "dataset_name": dataset_name,
            "text_sources": text_sources,
            "structured_sources": [],
            "metadata": {
                "keol_commit": payload["keol_commit"],
                "model_provider": payload.get("model_provider", ""),
                "source": "data/gold-candidates/KE-test.json",
                "unit_strategy": "one_user_agent_turn_per_chunk",
            },
        },
    )
    return dataset_root
