from __future__ import annotations

import json
import subprocess
import sys

from tools.natural_memory_benchmark.semantic_ir_runner import (
    build_diagnostic_suite,
    render_semantic_ir_report,
    run_semantic_ir_diagnostics,
)


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "tools.natural_memory_benchmark.cli", *args],
        check=True,
        capture_output=True,
        text=True,
    )


def test_diagnostic_suite_contains_the_five_minimal_ir_cases():
    suite = build_diagnostic_suite()

    assert [case.case_id for case in suite] == [
        "led_manage_vs_led_to_cause",
        "led_to_cause_match",
        "feedback_causal_answerability_missing_link",
        "multi_session_evidence_closure",
        "current_preference_supersession",
    ]
    assert {case.category for case in suite} == {
        "predicate_sense",
        "causal_answerability",
        "evidence_closure",
        "lifecycle",
    }


def test_run_semantic_ir_diagnostics_returns_machine_results():
    payload = run_semantic_ir_diagnostics(run_id="semantic-ir-diagnostic-test")

    assert payload["schema_version"] == "semantic-ir-diagnostic-results-v1"
    assert payload["run_id"] == "semantic-ir-diagnostic-test"
    assert payload["metrics"] == {
        "case_count": 5,
        "pass_count": 5,
        "fail_count": 0,
        "abstention_count": 1,
        "fallback_allowed_count": 0,
        "closure_complete_count": 4,
    }
    feedback_case = next(case for case in payload["cases"] if case["case_id"] == "feedback_causal_answerability_missing_link")
    assert feedback_case["passed"] is True
    assert feedback_case["query_result"]["abstained"] is True
    assert feedback_case["query_result"]["reason"] == "missing causal answerability roles"


def test_semantic_ir_report_states_scope_and_results():
    payload = run_semantic_ir_diagnostics(run_id="semantic-ir-diagnostic-test")
    report = render_semantic_ir_report(payload)

    assert "hand-authored IR" in report
    assert "no model extraction" in report
    assert "no benchmark expansion" in report
    assert "5/5" in report
    assert "led/manage" in report
    assert "led-to/cause" in report


def test_cli_run_semantic_ir_diagnostics_writes_json_and_report(tmp_path):
    output_path = tmp_path / "semantic-ir-diagnostic-results.json"
    report_path = tmp_path / "semantic-ir-diagnostic-report.md"

    result = _run_cli(
        "run-semantic-ir-diagnostics",
        "--output",
        str(output_path),
        "--report",
        str(report_path),
        "--run-id",
        "semantic-ir-cli-test",
    )

    assert "valid" in result.stdout
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    report = report_path.read_text(encoding="utf-8")
    assert payload["run_id"] == "semantic-ir-cli-test"
    assert payload["metrics"]["pass_count"] == 5
    assert "# Semantic IR Diagnostic Report" in report
