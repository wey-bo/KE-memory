"""Portable immutability verification for frozen artifacts.

POSIX mode bits do not survive a Git clone. Git records only the executable
bit, so an artifact frozen at 0444 checks out 0644 and any guard that reads
``st_mode & 0o222`` fails on a fresh clone. Restoring 0444 in one worktree
makes that worktree green while a fresh clone still fails, which is worse than
failing: it manufactures confidence that does not transfer.

So mode bits are demoted here to what they can actually deliver -- local
protection against accidental overwrite, applied after generation as defense in
depth. The immutability contract itself is content-addressed and portable: a
manifest binds each artifact's relative path, byte count, SHA-256, artifact
type and artifact version, and every consumer recomputes before use and fails
closed.

There is deliberately no option to skip verification. A configurable integrity
check is not an integrity check: the first time a hash mismatch is
inconvenient, the switch gets flipped and the guarantee is gone. Callers that
cannot satisfy the manifest are meant to fail.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "portable-frozen-set-manifest-v1"

_SHA256_PATTERN = r"^[0-9a-f]{64}$"

# Applied after generation so a stray local write is refused by the filesystem
# too. Never read back as a correctness signal -- see the module docstring.
FROZEN_FILE_MODE = 0o444


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize deterministically: sorted keys, no incidental whitespace.

    Kept byte-identical to ``io.canonical_json_bytes`` (trailing newline
    included) so a manifest built here binds the same bytes the existing
    writers produce.
    """
    plain = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    text = json.dumps(plain, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return (text + "\n").encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def sha256_json(value: Any) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def sha256_file(path: Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


class ImmutabilityViolation(Exception):
    """Raised when a frozen set does not match its manifest.

    Carries the violation class so a caller can report *how* the frozen set
    diverged without re-deriving it from message text.
    """

    def __init__(self, violation: str, detail: str) -> None:
        super().__init__(f"{violation}: {detail}")
        self.violation = violation
        self.detail = detail


def _validate_relative_path(value: str) -> str:
    if not value:
        raise ValueError("relative_path must not be empty")
    if "\\" in value:
        raise ValueError(f"relative_path must use POSIX separators: {value!r}")
    pure = PurePosixPath(value)
    if pure.is_absolute():
        raise ValueError(f"relative_path must be relative: {value!r}")
    parts = pure.parts
    if any(part in {"..", "."} for part in parts):
        raise ValueError(f"relative_path must be normalized: {value!r}")
    if str(pure) != value:
        raise ValueError(f"relative_path must be canonical: {value!r}")
    return value


class FrozenArtifactEntryV1(BaseModel):
    """One frozen artifact, bound by content rather than by inode state."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    relative_path: str
    byte_count: int = Field(ge=0)
    sha256: str = Field(pattern=_SHA256_PATTERN)
    artifact_type: str = Field(min_length=1)
    artifact_version: str = Field(min_length=1)

    @model_validator(mode="after")
    def _check_path(self) -> FrozenArtifactEntryV1:
        _validate_relative_path(self.relative_path)
        return self


def compute_entries_sha256(entries: tuple[FrozenArtifactEntryV1, ...]) -> str:
    """Hash the entry list itself, so the manifest cannot be edited silently."""
    return sha256_json([entry.model_dump(mode="json") for entry in entries])


class FrozenSetManifestV1(BaseModel):
    """A self-verifying description of a frozen artifact set.

    ``entries_sha256`` covers the entry list, so dropping, adding or swapping
    an entry invalidates the manifest at validation time -- before any consumer
    gets a chance to trust it.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["portable-frozen-set-manifest-v1"] = SCHEMA_VERSION
    frozen_set_id: str = Field(min_length=1)
    entries: tuple[FrozenArtifactEntryV1, ...]
    entries_sha256: str = Field(pattern=_SHA256_PATTERN)

    @model_validator(mode="after")
    def _check_self_describing(self) -> FrozenSetManifestV1:
        if not self.entries:
            raise ValueError("frozen set must not be empty")
        paths = [entry.relative_path for entry in self.entries]
        if len(set(paths)) != len(paths):
            raise ValueError("frozen set has duplicate relative_path")
        if paths != sorted(paths):
            raise ValueError("frozen set entries must be sorted by relative_path")
        expected = compute_entries_sha256(self.entries)
        if self.entries_sha256 != expected:
            raise ValueError("entries_sha256 does not describe entries")
        return self

    def entry(self, relative_path: str) -> FrozenArtifactEntryV1:
        for candidate in self.entries:
            if candidate.relative_path == relative_path:
                return candidate
        raise ImmutabilityViolation("not_in_frozen_set", relative_path)


def build_frozen_set_manifest(
    *,
    frozen_set_id: str,
    entries: tuple[FrozenArtifactEntryV1, ...],
) -> FrozenSetManifestV1:
    ordered = tuple(sorted(entries, key=lambda entry: entry.relative_path))
    return FrozenSetManifestV1(
        frozen_set_id=frozen_set_id,
        entries=ordered,
        entries_sha256=compute_entries_sha256(ordered),
    )


def describe_frozen_file(
    root: Path,
    relative_path: str,
    *,
    artifact_type: str,
    artifact_version: str,
) -> FrozenArtifactEntryV1:
    """Measure a file on disk into an entry. Used when freezing, not verifying."""
    path = Path(root) / relative_path
    data = path.read_bytes()
    return FrozenArtifactEntryV1(
        relative_path=relative_path,
        byte_count=len(data),
        sha256=sha256_bytes(data),
        artifact_type=artifact_type,
        artifact_version=artifact_version,
    )


def scan_frozen_set(root: Path) -> tuple[str, ...]:
    """Every file under ``root``, as sorted POSIX-relative paths.

    Needed because a hash-per-manifest-entry check alone cannot see an *added*
    file. Comparing the scan against the manifest closes that gap.
    """
    root = Path(root)
    if not root.is_dir():
        raise ImmutabilityViolation("frozen_root_missing", str(root))
    found: list[str] = []
    for path in sorted(root.rglob("*")):
        if path.is_dir():
            continue
        if "__pycache__" in path.parts:
            continue
        found.append(path.relative_to(root).as_posix())
    return tuple(sorted(found))


def verify_frozen_file(
    root: Path,
    entry: FrozenArtifactEntryV1,
) -> bytes:
    """Read one artifact and prove it is the bytes the manifest names.

    Returns the verified bytes so a caller never has to read the file a second
    time -- a second read is a second chance to read something different.
    Deliberately silent about ``st_mode``: a 0644 checkout of the right bytes is
    valid, a 0444 file with the wrong bytes is not.
    """
    path = Path(root) / entry.relative_path
    if not path.is_file():
        raise ImmutabilityViolation("frozen_file_missing", entry.relative_path)
    data = path.read_bytes()
    if len(data) != entry.byte_count:
        raise ImmutabilityViolation(
            "byte_count_mismatch",
            f"{entry.relative_path}: expected {entry.byte_count}, found {len(data)}",
        )
    actual = sha256_bytes(data)
    if actual != entry.sha256:
        raise ImmutabilityViolation(
            "content_hash_mismatch",
            f"{entry.relative_path}: expected {entry.sha256}, found {actual}",
        )
    return data


def verify_frozen_set(
    root: Path,
    manifest: FrozenSetManifestV1,
    *,
    allow_extra_files: tuple[str, ...] = (),
) -> dict[str, bytes]:
    """Verify a whole frozen set, fail closed, and return the verified bytes.

    Three distinct failures are separated because they have different causes:
    a mismatched hash is a mutation, a missing entry is a deletion, and an
    unexpected file is an addition. ``allow_extra_files`` exists only for
    genuinely out-of-contract siblings (a later correction record, for
    instance) and must be named explicitly -- it is not a wildcard.
    """
    root = Path(root)
    verified: dict[str, bytes] = {}
    for entry in manifest.entries:
        verified[entry.relative_path] = verify_frozen_file(root, entry)

    declared = {entry.relative_path for entry in manifest.entries}
    permitted = declared | set(allow_extra_files)
    for relative_path in scan_frozen_set(root):
        if relative_path not in permitted:
            raise ImmutabilityViolation("unexpected_file_in_frozen_set", relative_path)
    return verified


def require_frozen_set(
    root: Path,
    manifest_relative_path: str,
    *,
    allow_extra_files: tuple[str, ...] = (),
) -> dict[str, bytes]:
    """Load a set manifest from inside the set itself, then verify the set.

    The manifest cannot bind its own hash, so it is excluded from its entries
    and protected instead by ``entries_sha256`` plus every consumer recomputing
    artifact hashes. An edited manifest therefore either fails its own
    self-description or disagrees with the artifacts it points at.
    """
    root = Path(root)
    manifest_path = root / manifest_relative_path
    if not manifest_path.is_file():
        raise ImmutabilityViolation("frozen_manifest_missing", manifest_relative_path)
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ImmutabilityViolation(
            "frozen_manifest_unreadable", f"{manifest_relative_path}: {error}"
        ) from error
    try:
        manifest = FrozenSetManifestV1.model_validate(payload)
    except Exception as error:  # pydantic ValidationError or our ValueError
        raise ImmutabilityViolation(
            "frozen_manifest_invalid", f"{manifest_relative_path}: {error}"
        ) from error
    return verify_frozen_set(
        root,
        manifest,
        allow_extra_files=(*allow_extra_files, manifest_relative_path),
    )


def write_frozen_file(root: Path, relative_path: str, data: bytes) -> str:
    """Write one artifact atomically, refusing an existing target outright.

    Refuses even when the bytes are identical. An idempotent writer cannot tell
    "already correct" from "a second producer is writing the same path", and the
    second case is how a frozen record silently acquires a new author.
    """
    _validate_relative_path(relative_path)
    root = Path(root)
    path = root / relative_path
    if path.exists():
        raise ImmutabilityViolation("frozen_target_exists", relative_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    handle, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=".partial-")
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        # os.link rather than os.replace: link fails if the target appeared
        # while we were writing, so a concurrent writer loses instead of
        # overwriting.
        try:
            os.link(temporary_path, path)
        except FileExistsError as error:
            raise ImmutabilityViolation("frozen_target_exists", relative_path) from error
    finally:
        temporary_path.unlink(missing_ok=True)

    os.chmod(path, FROZEN_FILE_MODE)
    return sha256_bytes(data)


def freeze_json_set(
    root: Path,
    *,
    frozen_set_id: str,
    payloads: dict[str, Any],
    artifact_types: dict[str, tuple[str, str]],
    manifest_relative_path: str = "frozen-set-manifest.json",
) -> FrozenSetManifestV1:
    """Write a JSON artifact set plus its portable manifest, once.

    ``artifact_types`` maps each relative path to ``(artifact_type,
    artifact_version)`` and must cover every payload: an unlabelled artifact is
    an artifact whose contract nobody declared.
    """
    root = Path(root)
    if root.exists() and any(root.iterdir()):
        raise ImmutabilityViolation("frozen_root_already_populated", str(root))
    missing = sorted(set(payloads) - set(artifact_types))
    if missing:
        raise ValueError(f"artifact type not declared for: {missing}")
    if manifest_relative_path in payloads:
        raise ValueError("manifest path collides with a payload path")

    entries: list[FrozenArtifactEntryV1] = []
    for relative_path in sorted(payloads):
        data = canonical_json_bytes(payloads[relative_path])
        digest = write_frozen_file(root, relative_path, data)
        artifact_type, artifact_version = artifact_types[relative_path]
        entries.append(
            FrozenArtifactEntryV1(
                relative_path=relative_path,
                byte_count=len(data),
                sha256=digest,
                artifact_type=artifact_type,
                artifact_version=artifact_version,
            )
        )

    manifest = build_frozen_set_manifest(
        frozen_set_id=frozen_set_id, entries=tuple(entries)
    )
    write_frozen_file(
        root, manifest_relative_path, canonical_json_bytes(manifest)
    )
    return manifest
