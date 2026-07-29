from __future__ import annotations

import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.natural_memory_benchmark import authoritative_conformance_runner as runner
from tools.natural_memory_benchmark.authoritative_conformance_runner import (
    _expected_correctness,
    build_authoritative_conformance_bundle,
    render_authoritative_conformance_report,
    run_authoritative_conformance,
    run_authoritative_conformance_file,
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


def test_v5_conformance_separates_adapter_parity_from_frozen_correctness_and_authority():
    payload = run_authoritative_conformance(
        ROOT,
        SLICE_ID,
        RESULTS,
        run_id="run-test-authoritative-v5",
    )

    assert payload["schema_version"] == "representation-conformance-run-v5"
    assert payload["source_validation"]["valid"] is True
    assert payload["reference_carrier"]["round_trip_exact"] is True
    assert payload["reference_carrier"]["query_probe_pass_count"] == 5
    assert payload["reference_carrier"]["correctness_pass_count"] == 5
    assert payload["reference_carrier"]["authoritative_ready"] is False
    assert "structured_l2_identity_unresolved" in payload["reference_carrier"]["hard_gate_failures"]
    assert payload["extended_amr_v2"]["round_trip_exact"] is True
    assert payload["extended_amr_v2"]["query_probe_pass_count"] == 5
    assert payload["extended_amr_v2"]["correctness_pass_count"] == 5
    assert payload["extended_amr_v2"]["authoritative_ready"] is False
    assert payload["extended_amr_v2"]["hard_gate_failures"] == payload["reference_carrier"]["hard_gate_failures"]
    assert payload["closure_metrics"]["fresh_evaluation_count"] == 6
    assert payload["closure_metrics"]["stale_evaluation_count"] == 0
    assert payload["closure_metrics"]["result_parity_pass_count"] == 6

    count_probe = next(
        probe
        for probe in payload["correctness_probes"]
        if probe["query_id"] == "LONGMEMEVAL-6d550036"
    )
    assert count_probe["expected"]["reason"] == "structured_l2_identity_unresolved"
    assert count_probe["expected"]["abstained"] is True
    assert count_probe["reference_result"]["abstained"] is True


def test_v5_bundle_builder_is_deterministic_and_contains_explicit_current_views():
    first = build_authoritative_conformance_bundle(ROOT, SLICE_ID, RESULTS)
    second = build_authoritative_conformance_bundle(ROOT, SLICE_ID, RESULTS)

    assert first == second
    assert len(first.unit_revisions) == 14
    assert set(first.current_revision_ids) == {
        *[unit.unit_id for unit in first.l1_units],
        *[unit.unit_id for unit in first.l2_units],
    }


def test_v5_file_helper_is_immutable(tmp_path):
    output = tmp_path / "v5.json"
    report = tmp_path / "v5.md"
    kwargs = {
        "root": ROOT,
        "slice_id": SLICE_ID,
        "results_path": RESULTS,
        "output_path": output,
        "report_path": report,
        "run_id": "run-file-authoritative-v5",
    }
    first = run_authoritative_conformance_file(**kwargs)
    second = run_authoritative_conformance_file(**kwargs)

    assert first == second
    assert json.loads(output.read_text(encoding="utf-8"))["run_id"] == kwargs["run_id"]
    assert "structured_l2_identity_unresolved" in report.read_text(encoding="utf-8")

    output.write_text("tampered\n", encoding="utf-8")
    with pytest.raises(FileExistsError, match="immutable artifact differs"):
        run_authoritative_conformance_file(**kwargs)


def test_v5_expected_correctness_uses_caller_paths(monkeypatch):
    expected_root = Path("custom-root")
    expected_slice_id = "custom-slice"
    expected_results = expected_root / expected_slice_id / "custom-results.json"
    observed: dict[str, object] = {}
    query_ids = [
        "BEAM-100K-C001-abstention-001",
        "LONGMEMEVAL-6d550036",
        "BEAM-100K-C001-contradiction_resolution-001",
        "BEAM-100K-C001-knowledge_update-002",
        "LONGMEMEVAL-gpt4_2655b836",
    ]
    cases = [SimpleNamespace(plan=SimpleNamespace(query_id=query_id)) for query_id in query_ids]
    bundle = SimpleNamespace(
        query_plans=[
            SimpleNamespace(
                query_id=query_id,
                answer_kind="count" if query_id == "LONGMEMEVAL-6d550036" else "fact",
            )
            for query_id in query_ids
        ]
    )

    def fake_build(root: Path, slice_id: str, results_path: Path):
        observed.update(root=root, slice_id=slice_id, results_path=results_path)
        return cases

    monkeypatch.setattr(runner, "build_real_slice_diagnostic_suite", fake_build)

    expected = _expected_correctness(
        bundle,
        expected_root,
        expected_slice_id,
        expected_results,
    )

    assert observed == {
        "root": expected_root,
        "slice_id": expected_slice_id,
        "results_path": expected_results,
    }
    assert expected["LONGMEMEVAL-6d550036"]["matched_unit_ids"] == [
        "l1-led-project-1",
        "l1-led-project-2",
        "l1-led-project-3",
        "l1-led-project-4",
        "l2-longmemeval-led-project-count",
    ]
    assert expected["LONGMEMEVAL-6d550036"]["matched_claim_ids"] == [
        "claim-l2-longmemeval-led-project-count"
    ]
    assert expected["LONGMEMEVAL-6d550036"]["abstained"] is True


def test_v5_frozen_correctness_oracle_hash_is_stable():
    assert (
        runner.FROZEN_CORRECTNESS_SHA256
        == "cfebd096c369c4a982e9db0b09cb4b32a98cb165853f005cf52fe049a45d8659"
    )


def test_v5_cli_writes_authoritative_conformance_artifacts(tmp_path):
    output = tmp_path / "representation-conformance-results-v5.json"
    report = tmp_path / "representation-conformance-report-v5.md"

    result = _run_cli(
        "run-authoritative-conformance",
        "--root",
        str(ROOT),
        "--slice-id",
        SLICE_ID,
        "--results",
        str(RESULTS),
        "--output",
        str(output),
        "--report",
        str(report),
        "--run-id",
        "run-cli-authoritative-v5",
    )

    assert "valid" in result.stdout
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "representation-conformance-run-v5"
    assert payload["run_id"] == "run-cli-authoritative-v5"
    assert "structured_l2_identity_unresolved" in report.read_text(encoding="utf-8")


def test_v5_cli_resolves_sources_from_absolute_root_outside_workspace_cwd(tmp_path):
    output = tmp_path / "absolute-root-v5.json"
    report = tmp_path / "absolute-root-v5.md"
    workspace_root = Path.cwd().resolve()
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(
        [str(workspace_root), environment.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)

    subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.natural_memory_benchmark.cli",
            "run-authoritative-conformance",
            "--root",
            str(ROOT.resolve()),
            "--slice-id",
            SLICE_ID,
            "--results",
            str(RESULTS.resolve()),
            "--output",
            str(output),
            "--report",
            str(report),
            "--run-id",
            "run-cli-authoritative-v5-absolute-root",
        ],
        cwd=tmp_path,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["source_validation"]["valid"] is True


def test_v5_carrier_recomputes_claim_aware_correctness_and_capability_gates():
    bundle = build_authoritative_conformance_bundle(ROOT, SLICE_ID, RESULTS)
    expected = _expected_correctness(bundle, ROOT, SLICE_ID, RESULTS)
    l2 = bundle.l2_units[0]
    claim = l2.structured_claims[0]
    drifted_l2 = l2.model_copy(
        update={
            "structured_claims": [claim.model_copy(update={"claim_id": "drifted-claim-id"})]
        }
    )
    drifted_bundle = bundle.model_copy(update={"l2_units": [drifted_l2]})

    class DriftedClaimAdapter:
        profile = runner._extended_profile()

        def encode(self, value):
            return b"drifted-claim"

        def decode(self, payload):
            return drifted_bundle

    carrier = runner._carrier_report(
        DriftedClaimAdapter(),
        bundle,
        expected,
        source_valid=True,
    )

    assert carrier["query_probe_pass_count"] == 5
    assert carrier["correctness_pass_count"] == 4
    assert "structured_l2_semantics" in carrier["unsupported_capabilities"]
    assert carrier["authoritative_ready"] is False


def test_v5_executes_stale_and_incomplete_active_l2_negative_gates(monkeypatch):
    bundle = build_authoritative_conformance_bundle(ROOT, SLICE_ID, RESULTS)

    assert runner._active_l2_negative_gate_failures(bundle) == []

    monkeypatch.setattr(
        runner,
        "assess_authoritative_bundle_integrity",
        lambda value: SimpleNamespace(valid=True, errors=[]),
    )
    assert runner._active_l2_negative_gate_failures(bundle) == [
        "stale_active_l2_not_rejected",
        "incomplete_active_l2_not_rejected",
    ]


def test_v5_report_does_not_claim_both_carriers_pass_when_one_fails():
    payload = run_authoritative_conformance(
        ROOT,
        SLICE_ID,
        RESULTS,
        run_id="run-report-failure-v5",
    )
    failed = deepcopy(payload)
    failed["extended_amr_v2"]["correctness_pass_count"] = 4
    failed["extended_amr_v2"]["status"] = "fail"
    failed["extended_amr_v2"]["hard_gate_failures"] = ["frozen_correctness_changed"]

    report = render_authoritative_conformance_report(failed)

    assert "Both carriers preserve" not in report
    assert "The carrier gates did not both pass" in report
