"""Verify an expired temporal guard against frozen evidence, not the filesystem.

The fresh-v3 authoring stage asserted that the *later* materialization stage did
not exist yet: ``_require_future_absent`` checked that
``typed_extractor_fresh_v3_materialization.py`` and its test were absent from the
workspace. That proved the authoring receipt could not have been written with
knowledge of the downstream implementation.

Those files exist now, and have since before the reorganization baseline
``00d1e9f``, so the check is permanently false. Re-running it does not detect a
regression; it re-discovers that time passed.

This is not a relaxation. The temporal claim is still verified -- it just moves
to the artifact that actually witnesses it. The frozen authoring receipt records
``materialization_implementation_absent = true``, the exact paths it checked, and
a git snapshot binding each file's blob OID and SHA-256 at receipt time. Checking
those bytes is a stronger test than checking today's filesystem: a rewritten
receipt fails, whereas the live check would pass again the moment someone deleted
the downstream module.

What must never be inferred from this: that the materialization stage existed at
authoring time. The receipt says it did not, and if the receipt bytes change,
verification fails rather than adapting.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .portable_immutability import ImmutabilityViolation, sha256_bytes

SCHEMA_VERSION = "expired-temporal-guard-verification-v1"

# The authoring receipt as frozen. Pinned so a rewritten receipt fails here
# instead of being re-measured into agreement with itself.
AUTHORING_RECEIPT_SHA256 = (
    "c810f421d5a3b0726b862ec2f12c89e0d638e0747892637e2a32977587b7ef8c"
)

AUTHORING_RECEIPT_RELATIVE_PATH = (
    "artifacts/automatic-extraction-assessment/"
    "typed-extractor-v3-fresh-hidden-prereg-v1/authoring-implementation-receipt.json"
)


class ExpiredTemporalGuardReport(BaseModel):
    """What the receipt witnesses about the guard, and what is true now."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["expired-temporal-guard-verification-v1"] = SCHEMA_VERSION
    guard_name: str = Field(min_length=1)
    receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    receipt_time: str = Field(min_length=1)
    witnessed_absent_at_receipt_time: bool
    witnessed_paths: tuple[str, ...]
    paths_present_now: tuple[str, ...]
    expired: bool

    @model_validator(mode="after")
    def _expiry_follows_from_the_measurements(self) -> ExpiredTemporalGuardReport:
        if not self.witnessed_absent_at_receipt_time:
            raise ValueError(
                "receipt does not witness absence; the guard was never satisfied and "
                "cannot be treated as expired"
            )
        if not self.witnessed_paths:
            raise ValueError("receipt must name the paths the guard checked")
        expected = bool(self.paths_present_now)
        if self.expired != expected:
            raise ValueError(
                "expired must follow from whether the witnessed paths exist now"
            )
        return self


def load_authoring_receipt(workspace_root: Path) -> dict[str, object]:
    """Read the frozen authoring receipt and verify its bytes.

    Fails closed on a hash mismatch: if the receipt has been edited, it is no
    longer evidence of anything, and the temporal claim loses its witness.
    """
    path = Path(workspace_root) / AUTHORING_RECEIPT_RELATIVE_PATH
    if not path.is_file():
        raise ImmutabilityViolation("authoring_receipt_missing", str(path))
    data = path.read_bytes()
    actual = sha256_bytes(data)
    if actual != AUTHORING_RECEIPT_SHA256:
        raise ImmutabilityViolation(
            "authoring_receipt_hash_mismatch",
            f"expected {AUTHORING_RECEIPT_SHA256}, found {actual}",
        )
    return json.loads(data)


def verify_materialization_absence_was_witnessed(
    workspace_root: Path,
) -> ExpiredTemporalGuardReport:
    """Confirm the receipt witnesses the absence, and report present-day state.

    Returns rather than raises when the guard has expired: expiry is the expected
    condition, and callers need the report to record it. It *does* raise when the
    receipt fails to witness absence at all -- that would mean the original claim
    was never established, which is a different and much worse finding.
    """
    receipt = load_authoring_receipt(workspace_root)
    witnessed = bool(receipt.get("materialization_implementation_absent"))
    paths = tuple(receipt.get("materialization_workspace_paths") or ())
    present = tuple(
        raw for raw in paths if (Path(workspace_root) / raw).exists()
    )
    return ExpiredTemporalGuardReport(
        guard_name="materialization_implementation_absent",
        receipt_sha256=AUTHORING_RECEIPT_SHA256,
        receipt_time=str(receipt.get("receipt_time")),
        witnessed_absent_at_receipt_time=witnessed,
        witnessed_paths=paths,
        paths_present_now=present,
        expired=bool(present),
    )


PREREGISTRATION_RELATIVE_PATH = (
    "artifacts/automatic-extraction-assessment/"
    "typed-extractor-v3-fresh-hidden-prereg-v1/preregistration.json"
)

# The v1 preregistration as frozen. Pinned for the same reason as the receipt: a
# rewritten witness must fail rather than be re-measured into agreement.
PREREGISTRATION_SHA256 = (
    "183cf6fc2991361e5da57b17e06a5970f651000986d50b87e8af2e6796440204"
)


def load_frozen_preregistration(workspace_root: Path) -> dict[str, object]:
    """Read the v1 preregistration and verify its bytes."""
    path = Path(workspace_root) / PREREGISTRATION_RELATIVE_PATH
    if not path.is_file():
        raise ImmutabilityViolation("frozen_preregistration_missing", str(path))
    data = path.read_bytes()
    actual = sha256_bytes(data)
    if actual != PREREGISTRATION_SHA256:
        raise ImmutabilityViolation(
            "frozen_preregistration_hash_mismatch",
            f"expected {PREREGISTRATION_SHA256}, found {actual}",
        )
    return json.loads(data)


def verify_future_paths_were_declared(
    workspace_root: Path,
    guard_paths: tuple[str, ...],
) -> tuple[str, ...]:
    """Confirm the preregistration declared the guard's paths as future work.

    The earliest of the three expired temporal claims: at preregistration time
    none of the downstream implementation existed, and the preregistration lists
    every path it expected to be created later. Those files exist now, so the live
    absence check is permanently false.

    Verification moves to the frozen preregistration, which is a *stronger*
    witness than the filesystem check: it records the declaration itself, so a
    guard that quietly widened its path list no longer matches what was declared.

    Raises when a guard path was never declared -- that would mean the guard is
    checking something the preregistration never committed to.
    """
    preregistration = load_frozen_preregistration(workspace_root)
    declared = preregistration.get("expected_future_paths")
    if not isinstance(declared, (list, tuple)) or not declared:
        raise ImmutabilityViolation(
            "future_paths_not_declared",
            "preregistration does not declare expected_future_paths",
        )
    workspace_declared = tuple(
        str(entry).split("workspace:", 1)[1]
        for entry in declared
        if str(entry).startswith("workspace:")
    )
    undeclared = sorted(set(guard_paths) - set(workspace_declared))
    if undeclared:
        raise ImmutabilityViolation(
            "guard_path_not_declared_future",
            "guard checks paths the preregistration never declared as future work: "
            f"{undeclared}",
        )
    return workspace_declared


def verify_evaluation_root_absence_was_witnessed(
    workspace_root: Path,
) -> bool:
    """Confirm the receipt witnesses that the evaluation root was absent.

    The second expired temporal claim in this stage. The authoring receipt was
    written before the evaluation root existed, and that root has since been
    committed as evidence -- so requiring its absence today asserts a condition
    that only held before the commit that recorded the results.

    Like the materialization claim, it stays verified against the receipt, which
    records ``evaluation_root_absent`` alongside the normalized root path it
    checked. Raises when the receipt fails to witness it, because that would mean
    the authoring stage never established the ordering it claimed.
    """
    receipt = load_authoring_receipt(workspace_root)
    if not bool(receipt.get("evaluation_root_absent")):
        raise ImmutabilityViolation(
            "evaluation_root_absence_not_witnessed",
            "authoring receipt does not record evaluation_root_absent; the ordering "
            "claim was never established and cannot be treated as expired",
        )
    binding = receipt.get("path_binding")
    if not isinstance(binding, dict) or not binding.get("normalized_evaluation_root"):
        raise ImmutabilityViolation(
            "evaluation_root_not_named",
            "authoring receipt does not name the evaluation root it checked",
        )
    return True


def verify_git_snapshot_binds_witnessed_files(
    workspace_root: Path,
) -> dict[str, str]:
    """Check the receipt's git snapshot still names a blob for each bound file.

    The snapshot is what makes the receipt more than a boolean: it records a blob
    OID and digest per file at receipt time. Verifying it is present and
    well-formed keeps the witness auditable even though the guard has expired.
    """
    receipt = load_authoring_receipt(workspace_root)
    snapshot = receipt.get("git_snapshot")
    if not isinstance(snapshot, dict):
        raise ImmutabilityViolation("git_snapshot_missing", "receipt has no git_snapshot")
    files = snapshot.get("files")
    if not isinstance(files, dict) or not files:
        raise ImmutabilityViolation("git_snapshot_empty", "git_snapshot binds no files")
    bound: dict[str, str] = {}
    for label, entry in files.items():
        if not isinstance(entry, dict):
            raise ImmutabilityViolation("git_snapshot_malformed", str(label))
        oid = entry.get("git_blob_oid")
        if not isinstance(oid, str) or len(oid) != 40:
            raise ImmutabilityViolation("git_snapshot_malformed_oid", str(label))
        bound[str(label)] = oid
    return bound
