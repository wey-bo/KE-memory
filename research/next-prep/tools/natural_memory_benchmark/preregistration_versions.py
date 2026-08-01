"""Append-only registry of fresh-v3 preregistration versions.

The v1 preregistration binds ``code_sha256`` for 11 source files. Six of those
changed when the duplicated ``_require_read_only`` guard was replaced with the
portable content-based one, and two had already drifted at the reorganization
baseline ``00d1e9f`` -- before any of this session's edits. That is 8 drifted
bindings with two distinct causes, and collapsing them into one "refreshed the
hashes" step would erase the distinction.

So v1 is not rewritten. It stays exactly as frozen, still reporting its original
drift, and v2 is registered beside it with bindings measured against the current
code. Each version declares which run may use it, so an old run cannot silently
be re-scored under new bindings and a new run cannot claim v1's provenance.

What a version deliberately does *not* cover: the producer contract hash and the
extraction profile hash. Those describe the prompt, schemas, materialization
contract, policy and registry -- none of which a preregistration refresh touches.
Registering v2 must leave both unchanged, and ``test_preregistration_versions``
asserts it.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "fresh-v3-preregistration-version-registry-v1"

_SHA256 = r"^[0-9a-f]{64}$"

# The commit the reorganization branch started from. Used to separate drift that
# predates this session from drift this session introduced.
REORG_BASELINE_COMMIT = "00d1e9f0b23008232aba941ec1571dab45ee1daa"

V1_DIRECTORY = "typed-extractor-v3-fresh-hidden-prereg-v1"
V2_DIRECTORY = "typed-extractor-v3-fresh-hidden-prereg-v2"

DriftCause = Literal[
    "preexisting_historical_drift",
    "portable_guard_migration",
    "preexisting_and_migration",
    "no_drift",
]


class CodeBindingDisposition(BaseModel):
    """Why one bound source file drifted, recorded per file rather than in bulk."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    file_name: str = Field(min_length=1)
    v1_bound_sha256: str = Field(pattern=_SHA256)
    sha256_at_baseline_commit: str | None = Field(default=None, pattern=_SHA256)
    sha256_now: str = Field(pattern=_SHA256)
    cause: DriftCause
    justification: str = Field(min_length=20)

    @model_validator(mode="after")
    def _cause_matches_the_measurements(self) -> CodeBindingDisposition:
        drifted_at_baseline = (
            self.sha256_at_baseline_commit is not None
            and self.v1_bound_sha256 != self.sha256_at_baseline_commit
        )
        changed_since_baseline = self.sha256_at_baseline_commit != self.sha256_now
        if self.cause == "no_drift":
            if drifted_at_baseline or changed_since_baseline:
                raise ValueError(f"{self.file_name}: cause no_drift contradicts measurement")
        elif self.cause == "preexisting_historical_drift":
            if not drifted_at_baseline or changed_since_baseline:
                raise ValueError(
                    f"{self.file_name}: preexisting drift must differ at baseline and be "
                    "unchanged since"
                )
        elif self.cause == "portable_guard_migration":
            if drifted_at_baseline or not changed_since_baseline:
                raise ValueError(
                    f"{self.file_name}: migration drift must match at baseline and differ now"
                )
        elif self.cause == "preexisting_and_migration":
            if not (drifted_at_baseline and changed_since_baseline):
                raise ValueError(
                    f"{self.file_name}: combined cause requires both baseline drift and a "
                    "change since"
                )
        return self


class PreregistrationVersion(BaseModel):
    """One registered preregistration version and the runs allowed to use it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal["v1", "v2"]
    directory: str = Field(min_length=1)
    preregistration_sha256: str = Field(pattern=_SHA256)
    evaluation_id: str = Field(min_length=1)
    code_sha256: dict[str, str]
    usable_by: Literal["historical_runs_only", "future_runs_only"]
    superseded_by: str | None = None

    @model_validator(mode="after")
    def _bindings_are_well_formed(self) -> PreregistrationVersion:
        if not self.code_sha256:
            raise ValueError("a version must bind at least one source file")
        for name, digest in self.code_sha256.items():
            if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                raise ValueError(f"malformed code hash for {name}")
        return self


class PreregistrationVersionRegistry(BaseModel):
    """Both versions plus the per-file dispositions explaining the difference."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["fresh-v3-preregistration-version-registry-v1"] = SCHEMA_VERSION
    baseline_commit: str = Field(min_length=7)
    versions: tuple[PreregistrationVersion, ...]
    dispositions: tuple[CodeBindingDisposition, ...]

    @model_validator(mode="after")
    def _registry_is_append_only_and_complete(self) -> PreregistrationVersionRegistry:
        labels = [version.version for version in self.versions]
        if labels != ["v1", "v2"]:
            raise ValueError("registry must list exactly v1 then v2")
        v1, v2 = self.versions
        if v1.preregistration_sha256 == v2.preregistration_sha256:
            raise ValueError("v1 and v2 must not be byte-identical")
        if v1.directory == v2.directory:
            raise ValueError("v2 must live in its own directory: v1 is append-only")
        if v1.usable_by != "historical_runs_only":
            raise ValueError("v1 may only be used by the runs already scored against it")
        if v2.usable_by != "future_runs_only":
            raise ValueError("v2 may only be used by future runs")
        if v1.superseded_by != "v2":
            raise ValueError("v1 must record that v2 supersedes it")
        if v2.superseded_by is not None:
            raise ValueError("v2 is current and must not be superseded")
        if set(v1.code_sha256) != set(v2.code_sha256):
            raise ValueError("both versions must bind the same file set")
        described = {item.file_name for item in self.dispositions}
        if described != set(v1.code_sha256):
            raise ValueError("every bound file needs a disposition, and no extras")
        return self

    def version(self, label: str) -> PreregistrationVersion:
        for candidate in self.versions:
            if candidate.version == label:
                return candidate
        raise KeyError(label)

    def cause_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in self.dispositions:
            counts[item.cause] = counts.get(item.cause, 0) + 1
        return counts


def sha256_path(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def repository_relative_path(path: Path, worktree_root: Path) -> str:
    """Derive a repo-relative POSIX path without asking Git.

    ``git ls-files --full-name`` returns an empty string for an absolute path
    given from inside a worktree, which silently turns a drift comparison into a
    comparison against nothing. Deriving the path arithmetically cannot fail
    quietly: a path outside the worktree raises instead.
    """
    return Path(path).resolve().relative_to(Path(worktree_root).resolve()).as_posix()


class ActiveReceiptVersion(BaseModel):
    """One registered authoring-receipt version and its source bindings.

    Separate from ``PreregistrationVersion`` because the two bind different
    things: a preregistration binds ``code_sha256`` only, while the authoring
    receipt additionally binds dependency hashes and a git snapshot. Conflating
    them would let a rebinding of one silently imply the other.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal["v1", "v2"]
    receipt_sha256: str = Field(pattern=_SHA256)
    code_sha256: dict[str, str]
    dependency_sha256: dict[str, str]
    usable_by: Literal["historical_runs_only", "future_runs_only"]
    superseded_by: str | None = None

    @model_validator(mode="after")
    def _bindings_are_present(self) -> ActiveReceiptVersion:
        if not self.code_sha256 or not self.dependency_sha256:
            raise ValueError("an active receipt version must bind code and dependencies")
        return self


def load_code_bindings(preregistration_path: Path) -> dict[str, str]:
    return dict(json.loads(Path(preregistration_path).read_bytes())["code_sha256"])
