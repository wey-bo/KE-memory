from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

from tools.keol_baseline.keol_ke_test_adapter import (
    build_turn_units,
    materialize_keol_dataset,
    merge_model_graph_batches,
    validate_model_graphs,
    write_turn_bundle,
)
from tools.keol_baseline.run_keol_pipeline import (
    apply_normalization_plan_files,
    write_normalization_payloads,
)


def _sample_ke_test() -> dict:
    return {
        "candidates": [
            {
                "id": "CAND-001",
                "source": "fixture",
                "turns": [
                    {"user": "用户第一问。", "agent": "Agent 第一答。"},
                    {"user": "用户第二问。", "agent": "Agent 第二答。"},
                ],
            }
        ]
    }


def _graphs_for(units: list[dict]) -> dict:
    return {
        "keol_commit": "44631e64fd07c9b85f22e36035bf49c882dba592",
        "model_provider": "codex_subagent",
        "units": [
            {
                "unit_id": unit["unit_id"],
                "nodes": [
                    {
                        "id": "user",
                        "name": "用户",
                        "type": "Person",
                        "description": "提出问题的人。",
                    },
                    {
                        "id": "question",
                        "name": f"问题{unit['turn_index']}",
                        "type": "Question",
                        "description": unit["user"],
                    },
                ],
                "edges": [
                    {
                        "source_node_id": "user",
                        "target_node_id": "question",
                        "relationship_name": "asks",
                        "description": unit["user"],
                    }
                ],
            }
            for unit in units
        ],
    }


def test_build_turn_units_preserves_turns_and_coordinates() -> None:
    units = build_turn_units(_sample_ke_test())

    assert [unit["unit_id"] for unit in units] == [
        "cand-001__turn-001",
        "cand-001__turn-002",
    ]
    assert units[0]["candidate_id"] == "CAND-001"
    assert units[0]["turn_index"] == 1
    assert units[0]["json_pointer"] == "/candidates/0/turns/0"
    assert units[0]["text"] == "用户：\n用户第一问。\n\nAgent：\nAgent 第一答。"
    assert units[1]["user"] == "用户第二问。"
    assert units[1]["agent"] == "Agent 第二答。"


def test_validate_model_graphs_requires_exact_unit_coverage() -> None:
    units = build_turn_units(_sample_ke_test())
    payload = _graphs_for(units)
    payload["units"].pop()

    with pytest.raises(ValueError, match="unit coverage"):
        validate_model_graphs(units, payload)


def test_validate_model_graphs_rejects_unknown_edge_nodes() -> None:
    units = build_turn_units(_sample_ke_test())
    payload = _graphs_for(units)
    payload["units"][0]["edges"][0]["target_node_id"] = "missing"

    with pytest.raises(ValueError, match="unknown target node"):
        validate_model_graphs(units, payload)


def test_materialize_keol_dataset_preserves_turn_text_and_metadata(tmp_path: Path) -> None:
    units = build_turn_units(_sample_ke_test())
    payload = _graphs_for(units)
    validate_model_graphs(units, payload)

    dataset = materialize_keol_dataset(units, payload, tmp_path, "KE-test")
    metadata = json.loads((dataset / "_metadata.json").read_text(encoding="utf-8"))
    first_source = metadata["text_sources"][0]
    chunk_path = dataset / first_source["path"] / "chunk_000.json"
    chunk = json.loads(chunk_path.read_text(encoding="utf-8"))

    assert metadata["dataset_name"] == "KE-test"
    assert len(metadata["text_sources"]) == 2
    assert chunk["chunk"]["text"] == units[0]["text"]
    assert chunk["chunk"]["metadata"]["candidate_id"] == "CAND-001"
    assert chunk["chunk"]["metadata"]["turn_index"] == 1
    assert chunk["chunk"]["metadata"]["json_pointer"] == "/candidates/0/turns/0"
    assert chunk["entities"][0]["source_chunk_id"] == chunk["chunk"]["id"]
    assert chunk["relations"][0]["relation_type"] == "asks"


def test_write_turn_bundle_writes_manifest_and_exact_text(tmp_path: Path) -> None:
    units = build_turn_units(_sample_ke_test())

    manifest_path = write_turn_bundle(units, tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["unit_count"] == 2
    assert manifest["units"][0]["text_path"] == "turns/cand-001__turn-001.txt"
    assert (tmp_path / manifest["units"][0]["text_path"]).read_text(
        encoding="utf-8"
    ) == units[0]["text"]


def test_merge_model_graph_batches_rejects_duplicate_units() -> None:
    units = build_turn_units(_sample_ke_test())
    first = _graphs_for(units[:1])
    duplicate = _graphs_for(units[:1])

    with pytest.raises(ValueError, match="duplicate model graph unit"):
        merge_model_graph_batches([first, duplicate])


def test_merge_model_graph_batches_combines_disjoint_units() -> None:
    units = build_turn_units(_sample_ke_test())

    merged = merge_model_graph_batches(
        [_graphs_for(units[:1]), _graphs_for(units[1:])]
    )

    assert merged["keol_commit"] == "44631e64fd07c9b85f22e36035bf49c882dba592"
    assert [item["unit_id"] for item in merged["units"]] == [
        "cand-001__turn-001",
        "cand-001__turn-002",
    ]


def test_materialized_dataset_builds_with_latest_keol(tmp_path: Path) -> None:
    units = build_turn_units(_sample_ke_test())
    payload = _graphs_for(units)
    dataset = materialize_keol_dataset(units, payload, tmp_path, "KE-test")
    keol_src = Path(r"C:\Users\86137\Desktop\Haitun-agent\KEOL\src")
    sys.path.insert(0, str(keol_src))
    try:
        from onto.builder import build_ontology
        from onto.validator import validate_ontology_output

        result = build_ontology(
            dataset,
            use_llm=False,
            validate=True,
            strict_validation=True,
        )
        report = validate_ontology_output(dataset, write=True, strict=True)
    finally:
        sys.path.remove(str(keol_src))

    assert report.ok is True
    assert {item.name for item in result.concepts} >= {"Person", "Question"}
    assert "asks" in {item.name for item in result.operators}
    assert len(result.assertions) == 2


def test_write_normalization_payloads_covers_all_ids(tmp_path: Path) -> None:
    units = build_turn_units(_sample_ke_test())
    dataset = materialize_keol_dataset(
        units, _graphs_for(units), tmp_path, "KE-test"
    )
    keol_root = Path(r"C:\Users\86137\Desktop\Haitun-agent\KEOL")
    sys.path.insert(0, str(keol_root / "src"))
    try:
        from onto.builder import build_ontology

        result = build_ontology(dataset, write=False, use_llm=False, validate=False)
    finally:
        sys.path.remove(str(keol_root / "src"))

    paths = write_normalization_payloads(
        result, keol_root, tmp_path / "normalization", batch_size=1
    )
    payloads = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    concept_ids = {
        item["id"] for payload in payloads for item in payload["concepts"]
    }
    operator_ids = {
        item["id"] for payload in payloads for item in payload["operators"]
    }

    assert concept_ids == {item.id for item in result.concepts}
    assert operator_ids == {item.id for item in result.operators}


def test_apply_normalization_plan_files_rejects_invented_ids(tmp_path: Path) -> None:
    units = build_turn_units(_sample_ke_test())
    dataset = materialize_keol_dataset(
        units, _graphs_for(units), tmp_path, "KE-test"
    )
    keol_root = Path(r"C:\Users\86137\Desktop\Haitun-agent\KEOL")
    sys.path.insert(0, str(keol_root / "src"))
    try:
        from onto.builder import build_ontology

        result = build_ontology(dataset, write=False, use_llm=False, validate=False)
    finally:
        sys.path.remove(str(keol_root / "src"))
    payload_paths = write_normalization_payloads(
        result, keol_root, tmp_path / "normalization", batch_size=100
    )
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "concept_updates": [
                    {
                        "id": "invented",
                        "canonical_name": "Invented",
                        "description": "Invalid update.",
                    }
                ],
                "operator_updates": [],
                "notes": [],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="normalization concept ID coverage"):
        apply_normalization_plan_files(
            result, keol_root, payload_paths, [plan_path]
        )


def test_apply_normalization_preserves_seeded_operator_provenance(tmp_path: Path) -> None:
    units = build_turn_units(_sample_ke_test())
    dataset = materialize_keol_dataset(
        units, _graphs_for(units), tmp_path, "KE-test"
    )
    keol_root = Path(r"C:\Users\86137\Desktop\Haitun-agent\KEOL")
    sys.path.insert(0, str(keol_root / "src"))
    try:
        from onto.builder import build_ontology

        result = build_ontology(dataset, write=False, use_llm=False, validate=False)
    finally:
        sys.path.remove(str(keol_root / "src"))
    payload_paths = write_normalization_payloads(
        result, keol_root, tmp_path / "normalization", batch_size=100
    )
    payload = json.loads(payload_paths[0].read_text(encoding="utf-8"))
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "concept_updates": [
                    {"id": item["id"], "description": "Class description."}
                    for item in payload["concepts"]
                ],
                "operator_updates": [
                    {
                        "id": item["id"],
                        "description": "Operator description.",
                        "semantic_status": "meta" if item["name"] in {"instance_of", "build_ontology"} else "needs_review",
                    }
                    for item in payload["operators"]
                ],
                "notes": [],
            }
        ),
        encoding="utf-8",
    )

    apply_normalization_plan_files(result, keol_root, payload_paths, [plan_path])
    seeded = {item.name: item.source_kind for item in result.operators if item.name in {"instance_of", "build_ontology"}}

    assert seeded == {"instance_of": "seeded", "build_ontology": "seeded"}
