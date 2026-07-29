from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tools.natural_memory_benchmark.semantic_ir_slice_runner import (
    build_real_slice_diagnostic_suite,
    render_real_slice_semantic_ir_report,
    run_real_slice_semantic_ir_diagnostics,
)


ROOT = Path("artifacts/natural-benchmark-slices")
SLICE_ID = "slice-v1"
RESULTS = ROOT / SLICE_ID / "symbolic-fallback-answerability-v2-fastembed-results.json"


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "tools.natural_memory_benchmark.cli", *args],
        check=True,
        capture_output=True,
        text=True,
    )


def test_real_slice_suite_contains_fixed_diagnostic_items():
    suite = build_real_slice_diagnostic_suite(ROOT, SLICE_ID, RESULTS)

    assert [case.item_id for case in suite] == [
        "BEAM-100K-C001-abstention-001",
        "LONGMEMEVAL-6d550036",
        "BEAM-100K-C001-contradiction_resolution-001",
        "BEAM-100K-C001-knowledge_update-002",
        "LONGMEMEVAL-gpt4_2655b836",
    ]
    assert {case.category for case in suite} == {
        "causal_answerability",
        "lexical_fallback_elimination",
        "conflict_evidence_closure",
        "update_supersession_closure",
        "temporal_chain_closure",
    }


def test_run_real_slice_semantic_ir_diagnostics_compares_existing_and_ir_behavior():
    payload = run_real_slice_semantic_ir_diagnostics(
        ROOT,
        SLICE_ID,
        RESULTS,
        run_id="semantic-ir-real-slice-test",
    )

    assert payload["schema_version"] == "semantic-ir-real-slice-diagnostic-results-v1"
    assert payload["run_id"] == "semantic-ir-real-slice-test"
    assert payload["metrics"] == {
        "case_count": 5,
        "pass_count": 5,
        "fail_count": 0,
        "ir_evidence_exact_count": 5,
        "existing_evidence_exact_count": 3,
        "ir_evidence_exact_improvement_count": 2,
        "existing_fallback_triggered_count": 1,
        "ir_fallback_allowed_count": 0,
        "ir_abstention_count": 1,
        "ir_closure_complete_count": 4,
    }

    fallback_case = next(case for case in payload["cases"] if case["item_id"] == "LONGMEMEVAL-6d550036")
    assert fallback_case["existing"]["fallback_triggered"] is True
    assert fallback_case["ir"]["fallback_allowed"] is False
    assert fallback_case["ir"]["evidence_exact"] is True

    contradiction_case = next(case for case in payload["cases"] if case["item_id"] == "BEAM-100K-C001-contradiction_resolution-001")
    assert contradiction_case["existing"]["evidence_exact"] is False
    assert contradiction_case["ir"]["required_evidence_ids"] == ["58", "24"]
    assert contradiction_case["ir"]["evidence_exact"] is True


def test_real_slice_semantic_ir_report_states_scope_and_improvements():
    payload = run_real_slice_semantic_ir_diagnostics(
        ROOT,
        SLICE_ID,
        RESULTS,
        run_id="semantic-ir-real-slice-test",
    )
    report = render_real_slice_semantic_ir_report(payload)

    assert "hand-authored real slice IR" in report
    assert "no model extraction" in report
    assert "5/5" in report
    assert "IR evidence-exact improvements: 2" in report
    assert "LONGMEMEVAL-6d550036" in report
    assert "BEAM-100K-C001-abstention-001" in report


def test_cli_run_semantic_ir_slice_diagnostics_writes_json_and_report(tmp_path):
    output_path = tmp_path / "semantic-ir-slice-diagnostic-results.json"
    report_path = tmp_path / "semantic-ir-slice-diagnostic-report.md"

    result = _run_cli(
        "run-semantic-ir-slice-diagnostics",
        "--root",
        str(ROOT),
        "--slice-id",
        SLICE_ID,
        "--results",
        str(RESULTS),
        "--output",
        str(output_path),
        "--report",
        str(report_path),
        "--run-id",
        "semantic-ir-real-slice-cli-test",
    )

    assert "valid" in result.stdout
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    report = report_path.read_text(encoding="utf-8")
    assert payload["run_id"] == "semantic-ir-real-slice-cli-test"
    assert payload["metrics"]["pass_count"] == 5
    assert "# Real Slice Semantic IR Diagnostic Report" in report
