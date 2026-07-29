from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tools.natural_memory_benchmark.io import load_json, write_json_immutable
from tools.natural_memory_benchmark.scoring import build_oracle_results, score_results
from tools.natural_memory_benchmark.evidence import resolve_gold_evidence_units


SLICE_ROOT = Path("artifacts/natural-benchmark-slices")


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "tools.natural_memory_benchmark.cli", *args],
        check=True,
        capture_output=True,
        text=True,
    )


def test_score_results_computes_evidence_and_answer_metrics():
    slice_payload = {
        "schema_version": "natural-benchmark-slice-v1",
        "slice_id": "unit-slice",
        "source_manifest_sha256": "0" * 64,
        "selection_policy": {},
        "public_items": [
            {"benchmark": "beam", "item_id": "I1", "source_id": "s", "source_index": 0, "source_ref": "r1", "question": "q1", "slice_group": "knowledge_update"},
            {"benchmark": "locomo", "item_id": "I2", "source_id": "s", "source_index": 1, "source_ref": "r2", "question": "q2", "slice_group": "5", "category": 5},
        ],
    }
    gold_payload = {
        "schema_version": "natural-benchmark-gold-v1",
        "slice_id": "unit-slice",
        "source_manifest_sha256": "0" * 64,
        "items": [
            {"benchmark": "beam", "item_id": "I1", "source_id": "s", "source_ref": "r1", "slice_group": "knowledge_update", "category": "knowledge_update", "answer": "250ms", "answer_policy": "gold", "evidence_refs": ["E1", "E2"], "metadata": {}},
            {"benchmark": "locomo", "item_id": "I2", "source_id": "s", "source_ref": "r2", "slice_group": "5", "category": 5, "answer": None, "answer_policy": "manual_required", "evidence_refs": ["D2:3"], "metadata": {"adversarial_answer": "self-care"}},
        ],
    }
    results_payload = {
        "schema_version": "natural-benchmark-results-v1",
        "slice_id": "unit-slice",
        "source_manifest_sha256": "0" * 64,
        "run_id": "unit-run",
        "arm": "symbolic_fallback",
        "items": [
            {"item_id": "I1", "predicted_answer": "  250MS ", "retrieved_evidence_refs": ["E2", "E1"], "abstained": False, "fallback_triggered": True, "fallback_reason": "missing_evidence_slot", "latency_ms": 10.0, "evidence_token_count": 42},
            {"item_id": "I2", "predicted_answer": "self-care", "retrieved_evidence_refs": ["D2:3"], "abstained": False, "fallback_triggered": False, "fallback_reason": None},
        ],
    }

    report = score_results(slice_payload, gold_payload, results_payload)

    assert report["item_count"] == 2
    assert report["manual_required_count"] == 1
    assert report["answer_scoreable_count"] == 1
    assert report["evidence_set_exact_match"] == 1.0
    assert report["evidence_recall"] == 1.0
    assert report["all_evidence_at_k"] == 1.0
    assert report["evidence_precision"] == 1.0
    assert report["answer_exact_match"] == 1.0
    assert report["fallback_trigger_rate"] == 0.5
    assert report["fallback_by_reason"] == {"missing_evidence_slot": 1}


def test_score_results_rejects_missing_items():
    slice_payload = {
        "schema_version": "natural-benchmark-slice-v1",
        "slice_id": "unit-slice",
        "source_manifest_sha256": "0" * 64,
        "selection_policy": {},
        "public_items": [
            {"benchmark": "beam", "item_id": "I1", "source_id": "s", "source_index": 0, "source_ref": "r1", "question": "q1", "slice_group": "abstention"}
        ],
    }
    gold_payload = {
        "schema_version": "natural-benchmark-gold-v1",
        "slice_id": "unit-slice",
        "source_manifest_sha256": "0" * 64,
        "items": [
            {"benchmark": "beam", "item_id": "I1", "source_id": "s", "source_ref": "r1", "slice_group": "abstention", "category": "abstention", "answer": "No information", "answer_policy": "gold", "evidence_refs": [], "metadata": {}}
        ],
    }
    results_payload = {
        "schema_version": "natural-benchmark-results-v1",
        "slice_id": "unit-slice",
        "source_manifest_sha256": "0" * 64,
        "run_id": "unit-run",
        "arm": "dense_reference",
        "items": [],
    }

    with pytest.raises(ValueError, match="result item ids diverge"):
        score_results(slice_payload, gold_payload, results_payload)


def test_build_oracle_results_scores_real_frozen_slice_as_perfect():
    slice_payload = load_json(SLICE_ROOT / "slice-v1" / "slice.json")
    gold_payload = load_json(SLICE_ROOT / "slice-v1" / "gold.json")
    results_payload = build_oracle_results(slice_payload, gold_payload, run_id="oracle-unit")

    report = score_results(slice_payload, gold_payload, results_payload)

    assert report["item_count"] == 32
    assert report["manual_required_count"] == 2
    assert report["answer_scoreable_count"] == 30
    assert report["evidence_set_exact_match"] == 1.0
    assert report["evidence_recall"] == 1.0
    assert report["all_evidence_at_k"] == 1.0
    assert report["evidence_precision"] == 1.0
    assert report["answer_exact_match"] == 1.0


def test_cli_score_results_writes_report(tmp_path):
    slice_payload = load_json(SLICE_ROOT / "slice-v1" / "slice.json")
    gold_payload = load_json(SLICE_ROOT / "slice-v1" / "gold.json")
    results_payload = build_oracle_results(slice_payload, gold_payload, run_id="oracle-cli")
    results_path = tmp_path / "oracle-results.json"
    output_path = tmp_path / "score-report.json"
    write_json_immutable(results_path, results_payload)

    result = _run_cli(
        "score-results",
        "--root",
        str(SLICE_ROOT),
        "--slice-id",
        "slice-v1",
        "--results",
        str(results_path),
        "--output",
        str(output_path),
    )

    assert "valid" in result.stdout
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["schema_version"] == "natural-benchmark-score-report-v1"
    assert report["metrics"]["evidence_set_exact_match"] == 1.0


def test_cli_export_gold_evidence_writes_raw_text_mapping(tmp_path):
    output_path = tmp_path / "gold-evidence.json"

    result = _run_cli(
        "export-gold-evidence",
        "--root",
        str(SLICE_ROOT),
        "--slice-id",
        "slice-v1",
        "--output",
        str(output_path),
    )

    assert "valid" in result.stdout
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "natural-benchmark-gold-evidence-v1"
    assert payload["item_count"] == 32
    assert "Researching adoption agencies" in json.dumps(payload["items"]["LOCOMO-S01-Q004"], ensure_ascii=False)


def test_resolve_gold_evidence_units_closes_raw_provenance():
    resolved = resolve_gold_evidence_units(SLICE_ROOT, "slice-v1")

    assert resolved["BEAM-100K-C001-abstention-001"] == []
    beam_units = resolved["BEAM-100K-C001-contradiction_resolution-001"]
    assert {unit["unit_id"] for unit in beam_units} == {"24", "58"}
    assert all(unit["text"] for unit in beam_units)
    assert any("Flask routes" in unit["text"] for unit in beam_units)

    locomo_units = resolved["LOCOMO-S01-Q004"]
    assert [unit["unit_id"] for unit in locomo_units] == ["D2:8"]
    assert "Researching adoption agencies" in locomo_units[0]["text"]

    longmem_units = resolved["LONGMEMEVAL-gpt4_2655b836"]
    assert {unit["unit_id"] for unit in longmem_units} == {
        "answer_4be1b6b4_1",
        "answer_4be1b6b4_2",
        "answer_4be1b6b4_3",
    }
    assert any("GPS system" in unit["text"] for unit in longmem_units)
