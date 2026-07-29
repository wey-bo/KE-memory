from __future__ import annotations

import subprocess
import sys
import json
from pathlib import Path

import pytest

from tools.natural_memory_benchmark import cli


RAW_ROOT = Path("artifacts/natural-benchmark-slices")


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "tools.natural_memory_benchmark.cli", *args],
        check=True,
        capture_output=True,
        text=True,
    )


def test_cli_freeze_and_validate_slice(tmp_path):
    out_root = tmp_path / "natural-benchmark-slices"

    result = _run_cli(
        "freeze-slice",
        "--raw-root",
        str(RAW_ROOT),
        "--root",
        str(out_root),
        "--slice-id",
        "slice-v1",
    )
    assert "slice-v1" in result.stdout

    validate = _run_cli(
        "validate-slice",
        "--root",
        str(out_root),
        "--slice-id",
        "slice-v1",
    )
    assert "valid" in validate.stdout

    ledger = _run_cli(
        "validate-ledger",
        "--path",
        str(out_root / "external-results-ledger.json"),
    )
    assert "valid" in ledger.stdout


@pytest.mark.parametrize(
    ("command", "terminal_flag"),
    (
        ("prepare-typed-extractor-l1-dev-repair", "--output-root"),
        ("validate-typed-extractor-l1-dev-repair", "--root"),
        ("prepare-typed-extractor-l2-dev-repair", "--output-root"),
        ("validate-typed-extractor-l2-dev-repair", "--root"),
    ),
)
def test_cli_parser_accepts_dev_repair_slice_commands(
    command: str,
    terminal_flag: str,
) -> None:
    args = cli.build_parser().parse_args(
        [
            command,
            "--source",
            "source.json",
            terminal_flag,
            "root",
            "--prior-root",
            "prior-a",
            "--prior-root",
            "prior-b",
        ]
    )

    assert args.command == command
    assert args.prior_root == ["prior-a", "prior-b"]


def test_cli_parser_accepts_strict_dev_repair_qualification() -> None:
    args = cli.build_parser().parse_args(
        [
            "qualify-typed-extractor-dev-repair",
            "--layer",
            "l2",
            "--score",
            "score.json",
            "--output",
            "qualification.json",
            "--report",
            "qualification.md",
        ]
    )

    assert args.command == "qualify-typed-extractor-dev-repair"
    assert args.layer == "l2"


@pytest.mark.parametrize(
    ("command", "function_name", "terminal_flag"),
    (
        (
            "prepare-typed-extractor-l1-dev-repair",
            "prepare_l1_dev_repair_slice",
            "--output-root",
        ),
        (
            "validate-typed-extractor-l1-dev-repair",
            "validate_l1_dev_repair_slice",
            "--root",
        ),
        (
            "prepare-typed-extractor-l2-dev-repair",
            "prepare_l2_dev_repair_slice",
            "--output-root",
        ),
        (
            "validate-typed-extractor-l2-dev-repair",
            "validate_l2_dev_repair_slice",
            "--root",
        ),
    ),
)
def test_cli_dispatches_dev_repair_slice_commands_with_summary_only(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: str,
    function_name: str,
    terminal_flag: str,
) -> None:
    calls: list[tuple] = []

    def fake(*args):
        calls.append(args)
        return {
            "status": "valid",
            "case_count": 16,
            "provenance": "diagnostic_authored",
            "private_detail": "must not print",
        }

    monkeypatch.setattr(cli, function_name, fake, raising=False)

    assert (
        cli.main(
            [
                command,
                "--source",
                "source.json",
                terminal_flag,
                "root",
                "--prior-root",
                "prior-a",
                "--prior-root",
                "prior-b",
            ]
        )
        == 0
    )

    assert calls == [
        (
            Path("source.json"),
            Path("root"),
            [Path("prior-a"), Path("prior-b")],
        )
    ]
    assert json.loads(capsys.readouterr().out) == {
        "case_count": 16,
        "provenance": "diagnostic_authored",
        "status": "valid",
    }


def test_cli_dispatches_strict_qualification_with_readiness_summary(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[tuple] = []

    def fake(*args):
        calls.append(args)
        return {
            "status": "qualified",
            "layer": "l2",
            "dataset_id": "typed-extractor-l2-dev-repair-v1",
            "run_id": "run-test",
            "raw_proposer_quality_ready": False,
            "deterministic_gate_safety_ready": True,
            "dev_repair_ready": False,
            "private_detail": "must not print",
        }

    monkeypatch.setattr(cli, "qualify_dev_repair", fake, raising=False)

    assert (
        cli.main(
            [
                "qualify-typed-extractor-dev-repair",
                "--layer",
                "l2",
                "--score",
                "score.json",
                "--output",
                "qualification.json",
                "--report",
                "qualification.md",
            ]
        )
        == 0
    )

    assert calls == [
        (
            "l2",
            Path("score.json"),
            Path("qualification.json"),
            Path("qualification.md"),
        )
    ]
    assert json.loads(capsys.readouterr().out) == {
        "dataset_id": "typed-extractor-l2-dev-repair-v1",
        "deterministic_gate_safety_ready": True,
        "dev_repair_ready": False,
        "layer": "l2",
        "raw_proposer_quality_ready": False,
        "run_id": "run-test",
        "status": "qualified",
    }
