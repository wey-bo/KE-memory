from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tools.natural_memory_benchmark.identity_proposal import (
    freeze_natural_identity_slice,
    run_reference_identity_proposer,
)
from tools.natural_memory_benchmark.identity_proposal_runner import (
    render_identity_proposal_report,
    run_reference_identity_proposer_file,
    score_identity_proposals_file,
)


SOURCE_CONFIG = Path(
    "artifacts/identity-memory-experiment/natural-v1/source-cases.json"
)


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "tools.natural_memory_benchmark.cli", *args],
        check=True,
        capture_output=True,
        text=True,
    )


def test_file_helpers_are_immutable_and_deterministic(tmp_path):
    root = tmp_path / "natural-v1"
    freeze_natural_identity_slice(SOURCE_CONFIG, root, workspace_root=Path("."))
    proposal_path = tmp_path / "reference-proposals.json"
    score_path = tmp_path / "reference-score.json"
    report_path = tmp_path / "reference-report.md"

    first_proposals = run_reference_identity_proposer_file(
        root / "public.json",
        proposal_path,
        run_id="run-file-reference-v1",
    )
    second_proposals = run_reference_identity_proposer_file(
        root / "public.json",
        proposal_path,
        run_id="run-file-reference-v1",
    )
    assert first_proposals == second_proposals

    first_score = score_identity_proposals_file(
        root,
        proposal_path,
        score_path,
        report_path,
        workspace_root=Path("."),
    )
    second_score = score_identity_proposals_file(
        root,
        proposal_path,
        score_path,
        report_path,
        workspace_root=Path("."),
    )
    assert first_score == second_score

    proposal_path.write_text("tampered\n", encoding="utf-8")
    with pytest.raises(FileExistsError, match="immutable artifact differs"):
        run_reference_identity_proposer_file(
            root / "public.json",
            proposal_path,
            run_id="run-file-reference-v1",
        )


def test_report_keeps_safety_and_proposal_quality_claims_separate(tmp_path):
    root = tmp_path / "natural-v1"
    freeze_natural_identity_slice(SOURCE_CONFIG, root, workspace_root=Path("."))
    proposals = run_reference_identity_proposer(
        root / "public.json",
        run_id="run-report-reference-v1",
    )
    proposal_path = tmp_path / "proposals.json"
    proposal_path.write_text(json.dumps(proposals), encoding="utf-8")
    score_path = tmp_path / "score.json"
    report_path = tmp_path / "report.md"
    score = score_identity_proposals_file(
        root,
        proposal_path,
        score_path,
        report_path,
        workspace_root=Path("."),
    )
    report = render_identity_proposal_report(score)

    assert "Gate safety: `pass`" in report
    assert "Proposal quality: `fail`" in report
    assert "reference proposer is not a model run" in report
    assert "does not modify the core memory skeleton" in report
    assert "structured_l2_identity_unresolved" in report


def test_cli_freeze_validate_propose_and_score(tmp_path):
    root = tmp_path / "natural-v1"
    proposal_path = tmp_path / "reference-proposals.json"
    score_path = tmp_path / "reference-score.json"
    report_path = tmp_path / "reference-report.md"

    freeze = _run_cli(
        "freeze-natural-identity-slice",
        "--source-config",
        str(SOURCE_CONFIG),
        "--output-root",
        str(root),
        "--workspace-root",
        ".",
    )
    assert '"case_count": 12' in freeze.stdout

    validate = _run_cli(
        "validate-natural-identity-slice",
        "--root",
        str(root),
        "--workspace-root",
        ".",
    )
    assert '"status": "valid"' in validate.stdout

    propose = _run_cli(
        "run-identity-proposal-reference",
        "--public",
        str(root / "public.json"),
        "--output",
        str(proposal_path),
        "--run-id",
        "run-cli-reference-v1",
    )
    assert '"case_count": 12' in propose.stdout

    score = _run_cli(
        "score-identity-proposals",
        "--root",
        str(root),
        "--proposals",
        str(proposal_path),
        "--output",
        str(score_path),
        "--report",
        str(report_path),
        "--workspace-root",
        ".",
    )
    assert '"gate_safety_ready": true' in score.stdout
    assert json.loads(score_path.read_text(encoding="utf-8"))["status"] == "pass"
    assert "Proposal quality: `fail`" in report_path.read_text(encoding="utf-8")
