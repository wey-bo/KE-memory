from __future__ import annotations

import copy
import json
from pathlib import Path

from tools.natural_memory_benchmark.semantic_ir_keol_validate import (
    build_expected_closure_states,
    validate_keol_projection,
    validate_keol_projection_file,
)


ROOT = Path("artifacts/natural-benchmark-slices")
SLICE_ID = "slice-v1"
RESULTS = ROOT / SLICE_ID / "symbolic-fallback-answerability-v2-fastembed-results.json"
PROJECTION = ROOT / SLICE_ID / "semantic-ir-keol-projection.json"
KEOL_ROOT = Path("/public/home/wwb/KE_mem/KEOL-44631e6")


def test_current_projection_is_record_shape_valid_but_not_authoritative_ready():
    projection = json.loads(PROJECTION.read_text(encoding="utf-8"))
    expected = build_expected_closure_states(ROOT, SLICE_ID, RESULTS)

    report = validate_keol_projection(projection, KEOL_ROOT, expected_closure_states=expected)

    assert report["native_model_error_count"] == 0
    assert report["native_model_warning_count"] == 36
    assert report["record_shape_valid"] is True
    assert report["object_counts"] == {
        "concepts": 0,
        "individuals": 20,
        "operators": 8,
        "assertions": 19,
        "evidence": 13,
        "workflow_runs": 1,
    }
    assert report["closure_parity"]["mismatch_count"] == 4
    assert report["closure_parity"]["expected_complete_count"] == 4
    assert report["closure_parity"]["projected_complete_count"] == 0
    assert report["classification"] == "projection_only"
    assert report["reverse_round_trip_supported"] is False
    assert report["authoritative_ready"] is False
    assert report["warning_code_counts"] == {
        "agent_ontology.missing": 1,
        "assertion.unknown_status": 7,
        "individual.no_concepts": 20,
        "operator.no_description": 8,
    }


def test_native_validation_rejects_broken_evidence_reference():
    projection = json.loads(PROJECTION.read_text(encoding="utf-8"))
    broken = copy.deepcopy(projection)
    broken["assertions"][0]["evidence_ids"] = ["missing-evidence"]

    report = validate_keol_projection(broken, KEOL_ROOT)

    assert report["record_shape_valid"] is False
    assert report["native_model_error_count"] >= 1
    assert "assertion.missing_evidence" in report["error_code_counts"]


def test_file_validator_writes_machine_readable_assessment(tmp_path):
    output = tmp_path / "keol-validation.json"

    payload = validate_keol_projection_file(
        PROJECTION,
        KEOL_ROOT,
        output,
        root=ROOT,
        slice_id=SLICE_ID,
        results_path=RESULTS,
    )

    assert output.exists()
    assert json.loads(output.read_text(encoding="utf-8"))["classification"] == "projection_only"
    assert payload["closure_parity"]["mismatch_count"] == 4
