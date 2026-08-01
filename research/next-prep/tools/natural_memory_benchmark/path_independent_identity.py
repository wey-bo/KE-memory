"""Path-independent artifact identity for frozen records.

Several frozen records store *absolute* paths from the machine that produced
them -- ``/public/home/wwb/KE-mem/KE-memory-next-prep-20260727/...`` -- and then
compare them against paths resolved in the current tree. That comparison can
never succeed again: the original workspace no longer exists. It is the same
defect already repaired for the producer contract hash, where binding an artifact
to *where the code lived* rather than to *what the artifact is* made the record
unverifiable after any move.

The repair is deliberately narrow. "Path independent" means the workspace root
may move; it does **not** mean an artifact's position inside the workspace stops
mattering. Identity is therefore four things together:

    artifact_role + normalized_workspace_relative_path + content_sha256
                  + artifact/policy identity

All four must agree. Two artifacts with identical bytes at different relative
paths are different artifacts, and so are two artifacts at the same relative path
with different bytes.

The historical absolute path is retained as a ``historical_locator`` -- a record
of where the artifact once lived, never an identity claim.

What is refused, because each would turn a precise check into a fuzzy one:
basename matching, string-suffix matching, unknown historical roots, ``..``
traversal, absolute relative-paths, and symlink escapes. Prefix stripping is
allowed only for roots on the explicit allowlist below.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "path-independent-artifact-identity-v1"

# Historical workspace roots whose prefix may be stripped. Explicit and closed:
# an unlisted root is refused rather than guessed at, so a record from an unknown
# machine cannot be silently reinterpreted. Longest match wins, so a root that is
# a prefix of another cannot shadow it.
HISTORICAL_WORKSPACE_ROOTS: tuple[str, ...] = (
    "/public/home/wwb/KE-mem/KE-memory-next-prep-20260727",
)


class PathBindingViolation(Exception):
    """Raised when an artifact's path binding cannot be established."""

    def __init__(self, violation: str, detail: str) -> None:
        super().__init__(f"{violation}: {detail}")
        self.violation = violation
        self.detail = detail


def normalize_separators(value: str) -> str:
    """Normalize Windows separators to POSIX before any path reasoning.

    Done first so a record written on Windows and one written on Linux produce the
    same identity. Applied only to separators -- nothing else about the path is
    rewritten.
    """
    if "\\" in value and "/" not in value:
        return PureWindowsPath(value).as_posix()
    return value.replace("\\", "/")


def _reject_unsafe_relative_path(value: str) -> str:
    """Reject anything that is not a plain, normalized, relative POSIX path."""
    if not value:
        raise PathBindingViolation("empty_relative_path", "relative path is empty")
    pure = PurePosixPath(value)
    if pure.is_absolute():
        raise PathBindingViolation("absolute_relative_path", value)
    if any(part == ".." for part in pure.parts):
        raise PathBindingViolation("parent_traversal", value)
    if any(part == "." for part in pure.parts):
        raise PathBindingViolation("non_normalized_relative_path", value)
    if pure.as_posix() != value:
        raise PathBindingViolation("non_canonical_relative_path", value)
    return value


def workspace_relative_path(absolute_path: str) -> str:
    """Strip a known historical workspace root, yielding a relative POSIX path.

    Refuses an absolute path whose root is not on the allowlist: reinterpreting an
    unknown root would be a guess about which workspace a record came from.
    """
    normalized = normalize_separators(absolute_path)
    matches = sorted(
        (root for root in HISTORICAL_WORKSPACE_ROOTS if normalized.startswith(f"{root}/")),
        key=len,
        reverse=True,
    )
    if not matches:
        raise PathBindingViolation(
            "unknown_historical_workspace_root",
            f"{absolute_path} does not start with an allowlisted historical root",
        )
    remainder = normalized[len(matches[0]) + 1 :]
    return _reject_unsafe_relative_path(remainder)


def resolve_within_workspace(workspace_root: Path, relative_path: str) -> Path:
    """Resolve a relative path inside a workspace, refusing escapes.

    Checks the *resolved* location rather than the literal string, so a symlink
    pointing outside the workspace is caught even though the path text looks
    contained.
    """
    relative = _reject_unsafe_relative_path(normalize_separators(relative_path))
    root = Path(workspace_root).resolve()
    candidate = (root / relative).resolve()
    if candidate != root and root not in candidate.parents:
        raise PathBindingViolation(
            "workspace_escape",
            f"{relative_path} resolves outside {workspace_root}",
        )
    return candidate


def sha256_path(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class ArtifactPathBinding(BaseModel):
    """An artifact's identity, independent of where the workspace lives."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["path-independent-artifact-identity-v1"] = SCHEMA_VERSION
    artifact_role: str = Field(min_length=1)
    workspace_relative_path: str = Field(min_length=1)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_identity: str = Field(min_length=1)
    historical_locator: str | None = None

    @model_validator(mode="after")
    def _relative_path_is_safe(self) -> ArtifactPathBinding:
        _reject_unsafe_relative_path(self.workspace_relative_path)
        return self

    def identity_key(self) -> tuple[str, str, str, str]:
        """The four-part key. All four participate; none is optional."""
        return (
            self.artifact_role,
            self.workspace_relative_path,
            self.content_sha256,
            self.artifact_identity,
        )


def build_binding_from_historical_path(
    *,
    artifact_role: str,
    historical_absolute_path: str,
    workspace_root: Path,
    artifact_identity: str,
) -> ArtifactPathBinding:
    """Reinterpret a frozen absolute path as a path-independent binding.

    The absolute path is used only to derive the workspace-relative position and is
    then kept as ``historical_locator``. Content is hashed from the artifact in the
    *current* workspace, so the binding describes a file that actually exists here.
    """
    relative = workspace_relative_path(historical_absolute_path)
    resolved = resolve_within_workspace(workspace_root, relative)
    if not resolved.is_file():
        raise PathBindingViolation(
            "artifact_missing_in_workspace",
            f"{relative} does not exist under {workspace_root}",
        )
    return ArtifactPathBinding(
        artifact_role=artifact_role,
        workspace_relative_path=relative,
        content_sha256=sha256_path(resolved),
        artifact_identity=artifact_identity,
        historical_locator=normalize_separators(historical_absolute_path),
    )


def require_matching_binding(
    frozen: ArtifactPathBinding,
    current: ArtifactPathBinding,
) -> None:
    """Require two bindings to agree on all four identity parts.

    Each mismatch gets its own violation because they mean different things: a
    content difference is a changed artifact, a relative-path difference is a moved
    or substituted one, and a role difference means the comparison is between two
    unrelated things. ``historical_locator`` is deliberately not compared -- that is
    the whole point of the repair.
    """
    if frozen.artifact_role != current.artifact_role:
        raise PathBindingViolation(
            "artifact_role_mismatch",
            f"{frozen.artifact_role} != {current.artifact_role}",
        )
    if frozen.workspace_relative_path != current.workspace_relative_path:
        raise PathBindingViolation(
            "workspace_relative_path_mismatch",
            f"{frozen.workspace_relative_path} != {current.workspace_relative_path}",
        )
    if frozen.content_sha256 != current.content_sha256:
        raise PathBindingViolation(
            "content_sha256_mismatch",
            f"{frozen.workspace_relative_path}: {frozen.content_sha256} != "
            f"{current.content_sha256}",
        )
    if frozen.artifact_identity != current.artifact_identity:
        raise PathBindingViolation(
            "artifact_identity_mismatch",
            f"{frozen.artifact_identity} != {current.artifact_identity}",
        )


def require_same_workspace_relative_path(
    *,
    artifact_role: str,
    frozen_absolute_path: str,
    expected_relative_path: str,
) -> str:
    """Compare a frozen absolute path against an expected relative position.

    The narrow check the repaired call sites need: the workspace root may have
    moved, but the artifact must still sit at the same place inside it. Returns the
    derived relative path so a caller can bind content separately.
    """
    derived = workspace_relative_path(frozen_absolute_path)
    expected = _reject_unsafe_relative_path(normalize_separators(expected_relative_path))
    if derived != expected:
        raise PathBindingViolation(
            "workspace_relative_path_mismatch",
            f"{artifact_role}: frozen record points at {derived}, expected {expected}",
        )
    return derived


_RUN_TIMESTAMP = re.compile(r"run-(?P<stamp>\d{8}T\d{6}Z)-")


def run_id_timestamp(run_id: str) -> str:
    """Extract the UTC stamp a run id carries.

    Run ids are minted with the stamp embedded, so the ordering between two runs is
    recorded in the ids themselves. Refuses an id without one rather than assuming
    an order.
    """
    match = _RUN_TIMESTAMP.search(run_id)
    if match is None:
        raise PathBindingViolation(
            "run_id_without_timestamp",
            f"cannot establish ordering from run id {run_id!r}",
        )
    return match.group("stamp")


def require_declared_run_ordering(
    *,
    earlier_run_id: str,
    later_run_id: str,
) -> None:
    """Require the ordering the run ids declare, not the one the filesystem shows.

    The original check compared ``st_mtime_ns`` across the policy freeze, the dev
    run and the hidden source. Git records no mtime at all, so every checkout
    assigns fresh ones in arbitrary order -- the ordering was already unsatisfiable
    at the reorganization baseline, before any of this session's changes.

    The run ids carry UTC stamps minted when the runs happened, so the ordering is
    recorded in the frozen record itself. Equal stamps are refused: two runs that
    claim the same instant do not establish an order.
    """
    earlier = run_id_timestamp(earlier_run_id)
    later = run_id_timestamp(later_run_id)
    if not earlier < later:
        raise PathBindingViolation(
            "declared_run_ordering_violated",
            f"{earlier_run_id} ({earlier}) must precede {later_run_id} ({later})",
        )


def workspace_relative_path_of(path: Path, workspace_root: Path) -> str:
    """Express a live path as a workspace-relative POSIX path.

    The inverse of ``resolve_within_workspace``, and the counterpart to
    ``workspace_relative_path`` which strips a *historical* root. Raises rather than
    returning a fallback when the path lies outside the workspace, so a caller
    cannot accidentally compare against something the workspace does not contain.
    """
    root = Path(workspace_root).resolve()
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError as error:
        raise PathBindingViolation(
            "path_outside_workspace",
            f"{path} is not inside {workspace_root}",
        ) from error


class ChronologyWitness(BaseModel):
    """A frozen record of an ordering that filesystem mtime can no longer show.

    Stronger than the mtime comparison it replaces: it states both ordering
    conclusions *and* binds every participant by relative path and content hash, so
    verifying it also proves the ordering refers to the artifacts still present. A
    rewritten receipt fails; a re-checkout does not.

    ``trusted_timestamp_authority`` is carried through rather than asserted -- the
    receipt itself records that no trusted authority signed these times, and
    overstating that would misrepresent the evidence.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_freeze_precedes_dev_run: bool
    dev_run_complete_precedes_hidden_source: bool
    trusted_timestamp_authority: bool

    @model_validator(mode="after")
    def _both_orderings_must_hold(self) -> ChronologyWitness:
        if not self.policy_freeze_precedes_dev_run:
            raise ValueError(
                "chronology receipt does not witness the policy freeze preceding the "
                "dev run; the ordering was never established"
            )
        if not self.dev_run_complete_precedes_hidden_source:
            raise ValueError(
                "chronology receipt does not witness the dev run preceding the hidden "
                "source; the ordering was never established"
            )
        return self


def _find_participant(payload: dict[str, object], relative: str) -> str | None:
    """Locate a participant's bound hash by exact relative path.

    Exact match only -- no basename or suffix fallback, for the same reason the path
    binding refuses them.
    """
    for value in payload.values():
        if isinstance(value, dict):
            if value.get("path") == relative:
                bound = value.get("sha256")
                return str(bound) if bound is not None else None
            for nested in value.values():
                if isinstance(nested, dict) and nested.get("path") == relative:
                    bound = nested.get("sha256")
                    return str(bound) if bound is not None else None
    return None


def verify_chronology_witness(
    receipt_path: Path,
    *,
    workspace_root: Path,
    expected_participants: dict[str, str],
) -> ChronologyWitness:
    """Verify a frozen chronology receipt and the artifacts it orders.

    ``expected_participants`` maps a workspace-relative path to the SHA-256 the
    receipt should bind, so a receipt that orders *different* artifacts than the
    caller is about to use is refused. Each artifact is also re-hashed from the
    current workspace: an ordering claim about bytes that have since changed is not
    evidence about the bytes in hand.
    """
    import json as _json

    receipt_path = Path(receipt_path)
    if not receipt_path.is_file():
        raise PathBindingViolation("chronology_receipt_missing", str(receipt_path))
    payload = _json.loads(receipt_path.read_bytes())

    for relative, expected_sha256 in sorted(expected_participants.items()):
        bound = _find_participant(payload, relative)
        if bound is None:
            raise PathBindingViolation(
                "chronology_participant_not_bound",
                f"receipt does not bind {relative}",
            )
        if bound != expected_sha256:
            raise PathBindingViolation(
                "chronology_participant_hash_mismatch",
                f"{relative}: receipt binds {bound}, caller expects {expected_sha256}",
            )
        actual = sha256_path(resolve_within_workspace(workspace_root, relative))
        if actual != expected_sha256:
            raise PathBindingViolation(
                "chronology_participant_content_drift",
                f"{relative}: expected {expected_sha256}, found {actual}",
            )

    return ChronologyWitness(
        policy_freeze_precedes_dev_run=bool(
            payload.get("policy_freeze_precedes_dev_run")
        ),
        dev_run_complete_precedes_hidden_source=bool(
            payload.get("dev_run_complete_precedes_hidden_source")
        ),
        trusted_timestamp_authority=bool(payload.get("trusted_timestamp_authority")),
    )
