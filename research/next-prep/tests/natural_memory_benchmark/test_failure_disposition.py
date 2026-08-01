"""Tests for per-entry failure classification.

The classifier's job is to attribute a failure to its *root* cause, and the
mistake worth guarding against is the one it already made: attributing a masked
failure to the assertion that reported it. When a guard fires before the
behaviour under test, ``pytest.raises`` reports "Regex pattern did not match"
and the real cause is only visible in the captured input. Classifying on the
first line alone mislabelled 43 failures.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from tools.natural_memory_benchmark.failure_disposition import (
    FailureDisposition,
    build_disposition_record,
    classify_reason,
    compare_against_snapshot,
    load_structured_report,
    parse_failure_report,
)

_SHA_A = "a" * 64
_SHA_B = "b" * 64


def test_masked_read_only_failure_is_attributed_to_the_file_mode(
    ) -> None:
    """The 43-failure mislabelling: the reported line is not the cause."""
    detail = (
        "AssertionError: Regex pattern did not match.\n"
        " Regex: 'authoritative state mutation detected'\n"
        " Input: 'public input must be read-only'"
    )
    assert detail.splitlines()[0].startswith("AssertionError: Regex")
    assert classify_reason(detail) == "file_mode_precondition"


def test_masked_hash_drift_failure_is_attributed_to_the_drift() -> None:
    detail = (
        "AssertionError: Regex pattern did not match.\n"
        " Regex: 'receipt path changed'\n"
        " Input: 'preregistration code hash drift: typed_extractor_l1.py'"
    )
    assert classify_reason(detail) == "preregistration_code_hash_drift"


def test_direct_file_mode_failures_are_recognised() -> None:
    assert classify_reason("ValueError: source config must be read-only") == (
        "file_mode_precondition"
    )
    assert classify_reason(
        "ValueError: fresh v3 preregistration must have mode 0444"
    ) == "file_mode_precondition"


def test_missing_dependency_is_separated_from_code_defects() -> None:
    assert classify_reason("RuntimeError: DuckDB is required to read BEAM parquet") == (
        "missing_optional_dependency_duckdb"
    )


def test_child_process_reason_decides_the_category() -> None:
    """A non-zero exit code alone says nothing; the child's stderr does."""
    parent_only = "subprocess.CalledProcessError: Command '[...]' returned exit status 1"
    assert classify_reason(parent_only) == "needs_manual_inspection"
    with_child = parent_only + "\nstderr: ValueError: public input must be read-only"
    assert classify_reason(with_child) == "file_mode_precondition"


def test_file_mode_wins_over_hash_drift_when_both_appear() -> None:
    """Ordering is a real decision: the guard that fires first is the cause."""
    detail = (
        "ValueError: source config must be read-only\n"
        "context: preregistration code hash drift mentioned in the same trace"
    )
    assert classify_reason(detail) == "file_mode_precondition"


def test_parametrized_nodeids_with_spaces_are_parsed() -> None:
    """Nodeids contain spaces and brackets; the first token is not the id."""
    text = (
        "=== short test summary info ===\n"
        "FAILED tests/x.py::test_a[case_one-a message with spaces]\n"
        "FAILED tests/x.py::test_b - ValueError: boom\n"
    )
    parsed = parse_failure_report(text)
    assert set(parsed) == {
        "tests/x.py::test_a[case_one-a message with spaces]",
        "tests/x.py::test_b",
    }
    assert parsed["tests/x.py::test_b"] == "ValueError: boom"


def test_progress_output_is_not_counted_as_failures() -> None:
    text = (
        "FAILED tests/not-in-summary.py::test_z\n"
        "=== short test summary info ===\n"
        "FAILED tests/x.py::test_a\n"
    )
    assert set(parse_failure_report(text)) == {"tests/x.py::test_a"}


def test_structured_report_round_trips(tmp_path: Path) -> None:
    payload = {
        "failure_count": 1,
        "failures": [
            {
                "nodeid": "tests/x.py::test_a",
                "when": "call",
                "message": "ValueError: source config must be read-only",
                "child_reason": "",
                "path": "tests/x.py",
            }
        ],
    }
    report = tmp_path / "failures.json"
    report.write_text(json.dumps(payload), encoding="utf-8")
    assert load_structured_report(report) == {
        "tests/x.py::test_a": "ValueError: source config must be read-only"
    }


def test_new_failures_are_separated_from_the_snapshot() -> None:
    """Repairing a snapshot failure is allowed; introducing a new one is not."""
    comparison = compare_against_snapshot(
        snapshot_ids=("a", "b", "c"),
        measured_ids=("b", "d"),
    )
    assert comparison["resolved"] == ("a", "c")
    assert comparison["still_failing"] == ("b",)
    assert comparison["newly_failing"] == ("d",)


def test_archiving_requires_a_specific_justification() -> None:
    with pytest.raises(ValidationError):
        FailureDisposition(
            test_id="tests/x.py::test_a",
            reason_category="dead_contract",
            disposition="archived_dead_contract",
            justification="old",
        )


def test_record_binds_the_snapshot_it_remeasures() -> None:
    record = build_disposition_record(
        failures={
            "tests/x.py::test_a": "ValueError: source config must be read-only",
            "tests/x.py::test_b": "RuntimeError: DuckDB is required to read BEAM parquet",
        },
        source_ledger_sha256=_SHA_A,
        source_failure_ids_sha256=_SHA_B,
        measured_at_commit="00d1e9f",
    )
    assert record.source_ledger_sha256 == _SHA_A
    assert record.counts() == {
        "fixed_active_infrastructure": 1,
        "install_contract_or_legitimate_skip": 1,
    }
    assert [item.test_id for item in record.dispositions] == sorted(
        item.test_id for item in record.dispositions
    )


def test_every_reason_category_maps_to_a_disposition() -> None:
    """A reason with no mapping would raise KeyError mid-classification."""
    from tools.natural_memory_benchmark.failure_disposition import (
        _DISPOSITION_BY_REASON,
    )

    samples = [
        "ValueError: x must be read-only",
        "ValueError: preregistration code hash drift: a.py",
        "RuntimeError: DuckDB is required to read BEAM parquet",
        "ValueError: future implementation artifact must be absent: /tmp/x",
        "AssertionError: assert not True where True = exists() must be absent",
        "AssertionError: something entirely new",
    ]
    for detail in samples:
        assert classify_reason(detail) in _DISPOSITION_BY_REASON, detail
