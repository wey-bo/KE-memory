from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tools.natural_memory_benchmark.representation_conformance_runner import (
    build_real_slice_representation_bundle,
    run_representation_conformance,
    run_representation_conformance_file,
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


def test_real_slice_bundle_materializes_closure_state_before_persistence():
    bundle = build_real_slice_representation_bundle(ROOT, SLICE_ID, RESULTS)

    assert len(bundle.query_plans) == 5
    assert sum(1 for closure in bundle.closures if closure.complete) == 4
    assert sum(1 for closure in bundle.closures if not closure.complete) == 1
    causal = next(closure for closure in bundle.closures if closure.pattern == "causal_answerability")
    assert causal.complete is False
    assert {slot.role for slot in causal.missing_slots} == {"causal_link"}


def test_reference_carrier_round_trip_passes_but_is_not_authoritative_ready():
    payload = run_representation_conformance(
        ROOT,
        SLICE_ID,
        RESULTS,
        run_id="run-test-representation-conformance",
    )

    report = payload["reference_carrier"]
    assert report["status"] == "pass"
    assert report["round_trip_exact"] is True
    assert report["query_probe_count"] == 5
    assert report["query_probe_pass_count"] == 5
    assert report["authoritative_ready"] is False
    assert set(report["unsupported_capabilities"]) == {
        "raw_source_revision_binding",
        "lifecycle_and_revision",
        "structured_l2_semantics",
        "closure_evaluation_versioning",
    }
    causal_probe = next(
        probe
        for probe in report["query_probes"]
        if probe["query_id"] == "BEAM-100K-C001-abstention-001"
    )
    assert causal_probe["reference_result"]["matched_unit_ids"] == [
        "l1-beam-feedback-mentioned",
        "l1-beam-ui-ux-improvement-mentioned",
    ]
    assert payload["scope"] == (
        "representation conformance only; hand-authored IR; no model extraction; no final storage selection"
    )
    amr = payload["extended_amr_candidate"]
    assert amr["round_trip_exact"] is True
    assert amr["query_probe_pass_count"] == 5
    assert amr["authoritative_ready"] is False
    assert amr["status"] == "fail"
    assert "required_capability_unsupported" in amr["hard_gate_failures"]


def test_file_helper_and_cli_write_conformance_artifacts(tmp_path):
    output = tmp_path / "representation-conformance.json"
    report = tmp_path / "representation-conformance.md"

    payload = run_representation_conformance_file(
        ROOT,
        SLICE_ID,
        RESULTS,
        output,
        report,
        run_id="run-direct-representation-conformance",
    )

    assert json.loads(output.read_text(encoding="utf-8"))["run_id"] == payload["run_id"]
    assert "not the selected production database" in report.read_text(encoding="utf-8")

    cli_output = tmp_path / "representation-conformance-cli.json"
    cli_report = tmp_path / "representation-conformance-cli.md"
    result = _run_cli(
        "run-representation-conformance",
        "--root",
        str(ROOT),
        "--slice-id",
        SLICE_ID,
        "--results",
        str(RESULTS),
        "--output",
        str(cli_output),
        "--report",
        str(cli_report),
        "--run-id",
        "run-cli-representation-conformance",
    )

    assert "valid" in result.stdout
    assert json.loads(cli_output.read_text(encoding="utf-8"))["reference_carrier"]["query_probe_pass_count"] == 5


def test_file_helper_rejects_overwriting_a_different_existing_report(tmp_path):
    output = tmp_path / "representation-conformance.json"
    report = tmp_path / "representation-conformance.md"
    kwargs = {
        "root": ROOT,
        "slice_id": SLICE_ID,
        "results_path": RESULTS,
        "output_path": output,
        "report_path": report,
        "run_id": "run-immutable-representation-conformance",
    }
    run_representation_conformance_file(**kwargs)
    report.write_text("tampered report\n", encoding="utf-8")

    with pytest.raises(FileExistsError, match="immutable artifact differs"):
        run_representation_conformance_file(**kwargs)
