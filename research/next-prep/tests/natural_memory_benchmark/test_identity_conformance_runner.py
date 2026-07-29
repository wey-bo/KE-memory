from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tools.natural_memory_benchmark.identity_conformance_runner import (
    render_identity_conformance_report,
    run_identity_conformance,
    run_identity_conformance_file,
)


EXPERIMENT_ROOT = Path("artifacts/identity-memory-experiment")


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "tools.natural_memory_benchmark.cli", *args],
        check=True,
        capture_output=True,
        text=True,
    )


def test_identity_conformance_passes_every_pre_registered_gate():
    payload = run_identity_conformance(EXPERIMENT_ROOT, run_id="run-test-identity-v1")

    assert payload["schema_version"] == "identity-conformance-run-v1"
    assert payload["status"] == "pass"
    assert payload["identity_authoritative_ready"] is True
    assert payload["scenario_count"] == 8
    assert payload["dev_count"] == 4
    assert payload["hidden_count"] == 4
    assert payload["metrics"]["critical_false_merge_count"] == 0
    assert payload["metrics"]["answerable_count_exact_rate"] == 1.0
    assert payload["metrics"]["evidence_set_exact_rate"] == 1.0
    assert payload["metrics"]["abstention_correctness"] == 1.0
    assert payload["metrics"]["revision_correctness"] == 1.0
    assert payload["metrics"]["closure_freshness_rate"] == 1.0
    assert payload["metrics"]["structural_fallback_rate"] == 0.0
    assert payload["carriers"]["native_v4"]["round_trip_exact_rate"] == 1.0
    assert payload["carriers"]["extended_amr_v3"]["round_trip_exact_rate"] == 1.0
    assert payload["carriers"]["extended_amr_v3"]["query_parity_rate"] == 1.0
    assert payload["regressions"]["v5_longmemeval_abstention_preserved"] is True


def test_report_states_scope_and_does_not_claim_product_or_storage_superiority():
    payload = run_identity_conformance(EXPERIMENT_ROOT, run_id="run-test-identity-report")
    report = render_identity_conformance_report(payload)

    assert "Extended-AMR v3" in report
    assert "critical false merges: `0`" in report
    assert "automatic entity-linking benchmark" in report
    assert "does not select final storage" in report
    assert "LongMemEval" in report


def test_file_helper_is_immutable_and_deterministic(tmp_path):
    output = tmp_path / "identity-conformance-results-v1.json"
    report = tmp_path / "identity-conformance-report-v1.md"
    kwargs = {
        "experiment_root": EXPERIMENT_ROOT,
        "output_path": output,
        "report_path": report,
        "run_id": "run-file-identity-v1",
    }

    first = run_identity_conformance_file(**kwargs)
    second = run_identity_conformance_file(**kwargs)
    assert first == second
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "pass"

    output.write_text("tampered\n", encoding="utf-8")
    with pytest.raises(FileExistsError, match="immutable artifact differs"):
        run_identity_conformance_file(**kwargs)


def test_cli_writes_identity_conformance_artifacts(tmp_path):
    output = tmp_path / "identity-results.json"
    report = tmp_path / "identity-report.md"
    result = _run_cli(
        "run-identity-conformance",
        "--root",
        str(EXPERIMENT_ROOT),
        "--output",
        str(output),
        "--report",
        str(report),
        "--run-id",
        "run-cli-identity-v1",
    )

    assert "pass" in result.stdout
    assert json.loads(output.read_text(encoding="utf-8"))["run_id"] == "run-cli-identity-v1"
    assert "Extended-AMR v3" in report.read_text(encoding="utf-8")
