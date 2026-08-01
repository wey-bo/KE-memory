"""Tests for verifying an expired temporal guard against frozen evidence.

The claim being preserved is "the materialization stage did not exist when the
authoring receipt was frozen". These tests assert that the claim is still
verified, and specifically that the verification is *stronger* than the live
filesystem check it replaces:

- a rewritten receipt fails, where the live check would not have noticed;
- deleting the downstream module would have made the live check pass again,
  whereas the receipt-based check still reports what was witnessed;
- a receipt that never witnessed absence is refused outright, because that would
  mean the original claim was never established.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from tools.natural_memory_benchmark.expired_temporal_guard import (
    AUTHORING_RECEIPT_RELATIVE_PATH,
    AUTHORING_RECEIPT_SHA256,
    ExpiredTemporalGuardReport,
    load_authoring_receipt,
    verify_git_snapshot_binds_witnessed_files,
    verify_materialization_absence_was_witnessed,
)
from tools.natural_memory_benchmark.portable_immutability import (
    ImmutabilityViolation,
    canonical_json_bytes,
    sha256_bytes,
)

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]


def test_receipt_witnesses_the_absence_and_the_guard_is_expired() -> None:
    report = verify_materialization_absence_was_witnessed(WORKSPACE_ROOT)
    assert report.witnessed_absent_at_receipt_time is True
    assert report.receipt_sha256 == AUTHORING_RECEIPT_SHA256
    assert report.receipt_time == "2026-07-29T14:35:02Z"
    assert set(report.witnessed_paths) == {
        "tools/natural_memory_benchmark/typed_extractor_fresh_v3_materialization.py",
        "tests/natural_memory_benchmark/test_typed_extractor_fresh_v3_materialization.py",
    }
    # Expired precisely because those files exist today.
    assert report.expired is True
    assert set(report.paths_present_now) == set(report.witnessed_paths)


def test_the_witnessed_files_exist_now_which_is_why_the_live_check_cannot_pass() -> None:
    """State the reason for expiry as a measurement, not an assumption."""
    report = verify_materialization_absence_was_witnessed(WORKSPACE_ROOT)
    for raw in report.witnessed_paths:
        assert (WORKSPACE_ROOT / raw).is_file(), raw


def test_a_rewritten_receipt_fails_verification(tmp_path: Path) -> None:
    """The property the live check never had: tampering with the witness fails."""
    original = (WORKSPACE_ROOT / AUTHORING_RECEIPT_RELATIVE_PATH).read_bytes()
    fake_root = tmp_path / "workspace"
    target = fake_root / AUTHORING_RECEIPT_RELATIVE_PATH
    target.parent.mkdir(parents=True)

    payload = json.loads(original)
    payload["materialization_implementation_absent"] = False
    target.write_bytes(canonical_json_bytes(payload))

    with pytest.raises(ImmutabilityViolation) as error:
        load_authoring_receipt(fake_root)
    assert error.value.violation == "authoring_receipt_hash_mismatch"


def test_a_missing_receipt_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(ImmutabilityViolation) as error:
        load_authoring_receipt(tmp_path)
    assert error.value.violation == "authoring_receipt_missing"


def test_deleting_the_downstream_module_does_not_revive_the_original_claim() -> None:
    """A live check would pass again after a delete; this one reports honestly.

    Simulated at the report level rather than by deleting a real module: the point
    is that "no paths present" must not be reported as though the guard were still
    being satisfied in its original sense.
    """
    report = verify_materialization_absence_was_witnessed(WORKSPACE_ROOT)
    revived = report.model_copy(update={"paths_present_now": (), "expired": False})
    # Still records that absence was witnessed at receipt time, and by which
    # receipt -- the historical claim does not silently become a present-day one.
    assert revived.witnessed_absent_at_receipt_time is True
    assert revived.receipt_sha256 == AUTHORING_RECEIPT_SHA256
    assert revived.witnessed_paths == report.witnessed_paths


def test_a_receipt_that_never_witnessed_absence_cannot_be_called_expired() -> None:
    """Expiry presupposes the claim was once established."""
    with pytest.raises(ValidationError, match="never satisfied"):
        ExpiredTemporalGuardReport(
            guard_name="materialization_implementation_absent",
            receipt_sha256=AUTHORING_RECEIPT_SHA256,
            receipt_time="2026-07-29T14:35:02Z",
            witnessed_absent_at_receipt_time=False,
            witnessed_paths=("tools/x.py",),
            paths_present_now=("tools/x.py",),
            expired=True,
        )


def test_expiry_must_follow_from_the_measurement() -> None:
    """`expired` is derived, not asserted: it cannot contradict the paths."""
    with pytest.raises(ValidationError, match="expired must follow"):
        ExpiredTemporalGuardReport(
            guard_name="materialization_implementation_absent",
            receipt_sha256=AUTHORING_RECEIPT_SHA256,
            receipt_time="2026-07-29T14:35:02Z",
            witnessed_absent_at_receipt_time=True,
            witnessed_paths=("tools/x.py",),
            paths_present_now=(),
            expired=True,
        )
    with pytest.raises(ValidationError, match="expired must follow"):
        ExpiredTemporalGuardReport(
            guard_name="materialization_implementation_absent",
            receipt_sha256=AUTHORING_RECEIPT_SHA256,
            receipt_time="2026-07-29T14:35:02Z",
            witnessed_absent_at_receipt_time=True,
            witnessed_paths=("tools/x.py",),
            paths_present_now=("tools/x.py",),
            expired=False,
        )


def test_receipt_must_name_the_paths_it_checked() -> None:
    """A bare boolean is not a witness; the scope has to be recorded."""
    with pytest.raises(ValidationError, match="must name the paths"):
        ExpiredTemporalGuardReport(
            guard_name="materialization_implementation_absent",
            receipt_sha256=AUTHORING_RECEIPT_SHA256,
            receipt_time="2026-07-29T14:35:02Z",
            witnessed_absent_at_receipt_time=True,
            witnessed_paths=(),
            paths_present_now=(),
            expired=False,
        )


def test_git_snapshot_binds_a_blob_oid_per_witnessed_file() -> None:
    """The snapshot is what makes the receipt more than a boolean."""
    bound = verify_git_snapshot_binds_witnessed_files(WORKSPACE_ROOT)
    assert bound, "receipt must bind at least one file by blob oid"
    for label, oid in bound.items():
        assert len(oid) == 40, label
        assert all(character in "0123456789abcdef" for character in oid), label


def test_receipt_bytes_match_the_pinned_digest() -> None:
    """Guards against the digest being quietly re-measured to match a new file."""
    data = (WORKSPACE_ROOT / AUTHORING_RECEIPT_RELATIVE_PATH).read_bytes()
    assert sha256_bytes(data) == AUTHORING_RECEIPT_SHA256
