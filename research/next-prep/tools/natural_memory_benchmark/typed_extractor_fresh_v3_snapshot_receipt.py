from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .typed_extractor_fresh_v3_authoring import _read_regular_path


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


SNAPSHOT_COMMIT = "00fa803ee44bcef5a299babb9a8e2b7ba9f994e4"
NORMALIZED_WORKSPACE_PATH = "research/next-prep"
ORIGINAL_WORKSPACE_ROOT = "/public/home/wwb/KE-mem/KE-memory-next-prep-20260727"
ORIGINAL_PREREGISTRATION_ROOT = (
    f"{ORIGINAL_WORKSPACE_ROOT}/artifacts/automatic-extraction-assessment/"
    "typed-extractor-v3-fresh-hidden-prereg-v1"
)
ORIGINAL_EVALUATION_ROOT = (
    f"{ORIGINAL_WORKSPACE_ROOT}/artifacts/automatic-extraction-assessment/"
    "typed-extractor-v3-fresh-hidden-v1"
)
NORMALIZED_PREREGISTRATION_PATH = (
    f"{NORMALIZED_WORKSPACE_PATH}/artifacts/automatic-extraction-assessment/"
    "typed-extractor-v3-fresh-hidden-prereg-v1/preregistration.json"
)
NORMALIZED_EVALUATION_ROOT = (
    f"{NORMALIZED_WORKSPACE_PATH}/artifacts/automatic-extraction-assessment/"
    "typed-extractor-v3-fresh-hidden-v1"
)

_SNAPSHOT_FILES = {
    "preregistration": {
        "repository_path": NORMALIZED_PREREGISTRATION_PATH,
        "git_blob_oid": "6433fef43d7c2d68f064d900ff28172f94b4968e",
        "sha256": (
            "183cf6fc2991361e5da57b17e06a5970f651000986d50b87e8af2e6796440204"
        ),
    },
    "authoring_module": {
        "repository_path": (
            f"{NORMALIZED_WORKSPACE_PATH}/tools/natural_memory_benchmark/"
            "typed_extractor_fresh_v3_authoring.py"
        ),
        "git_blob_oid": "bbe36a908ce7210c2919bb66328d4d4275851fe9",
        "sha256": (
            "c8ffb3f9466583ecad42049b200224ef038c9c85b6edaec73f2723944ebd8bad"
        ),
    },
    "authoring_test": {
        "repository_path": (
            f"{NORMALIZED_WORKSPACE_PATH}/tests/natural_memory_benchmark/"
            "test_typed_extractor_fresh_v3_authoring.py"
        ),
        "git_blob_oid": "d92a28b2dae92bc4ddeecaca05f7520b864f24c2",
        "sha256": (
            "ffba0281ca47d6e10781c06471c86367424780010e5cdeff458cba22f16db02a"
        ),
    },
}


class GitSnapshotFileBinding(StrictModel):
    repository_path: str = Field(min_length=1)
    workspace_path: str = Field(min_length=1)
    git_blob_oid: str = Field(pattern=r"^[0-9a-f]{40}$")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=1)


class GitSnapshotBinding(StrictModel):
    evidence_kind: Literal["git-commit-blob-plus-sha256"] = (
        "git-commit-blob-plus-sha256"
    )
    snapshot_commit: Literal[
        "00fa803ee44bcef5a299babb9a8e2b7ba9f994e4"
    ] = SNAPSHOT_COMMIT
    snapshot_commit_is_ancestor: Literal[True] = True
    files: dict[str, GitSnapshotFileBinding]

    @model_validator(mode="after")
    def validate_file_registry(self) -> "GitSnapshotBinding":
        if set(self.files) != set(_SNAPSHOT_FILES):
            raise ValueError("Git snapshot file registry mismatch")
        return self


class RelocationPathBinding(StrictModel):
    original_preregistration_root: Literal[
        "/public/home/wwb/KE-mem/KE-memory-next-prep-20260727/"
        "artifacts/automatic-extraction-assessment/"
        "typed-extractor-v3-fresh-hidden-prereg-v1"
    ] = ORIGINAL_PREREGISTRATION_ROOT
    original_evaluation_root: Literal[
        "/public/home/wwb/KE-mem/KE-memory-next-prep-20260727/"
        "artifacts/automatic-extraction-assessment/"
        "typed-extractor-v3-fresh-hidden-v1"
    ] = ORIGINAL_EVALUATION_ROOT
    normalized_repository_root: Literal["."] = "."
    normalized_workspace_root: Literal["research/next-prep"] = (
        NORMALIZED_WORKSPACE_PATH
    )
    normalized_preregistration_path: Literal[
        "research/next-prep/artifacts/automatic-extraction-assessment/"
        "typed-extractor-v3-fresh-hidden-prereg-v1/preregistration.json"
    ] = NORMALIZED_PREREGISTRATION_PATH
    normalized_evaluation_root: Literal[
        "research/next-prep/artifacts/automatic-extraction-assessment/"
        "typed-extractor-v3-fresh-hidden-v1"
    ] = NORMALIZED_EVALUATION_ROOT


def _absolute_lexical_path(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _run_git(
    repository_root: Path,
    *arguments: str,
    accepted_returncodes: tuple[int, ...] = (0,),
) -> subprocess.CompletedProcess[bytes]:
    completed = subprocess.run(
        ["git", "-C", str(repository_root), *arguments],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode not in accepted_returncodes:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(f"Git command failed: {' '.join(arguments)}: {detail}")
    return completed


def _require_repository_root(repository_root: Path) -> Path:
    repository_root = _absolute_lexical_path(repository_root)
    try:
        completed = _run_git(repository_root, "rev-parse", "--show-toplevel")
    except ValueError as exc:
        raise ValueError("supplied path is not the exact Git repository root") from exc
    reported = _absolute_lexical_path(
        Path(completed.stdout.decode("utf-8").strip())
    )
    if reported != repository_root:
        raise ValueError("supplied path is not the exact Git repository root")
    return repository_root


def _require_workspace_root(repository_root: Path, workspace_root: Path) -> Path:
    workspace_root = _absolute_lexical_path(workspace_root)
    expected = repository_root / NORMALIZED_WORKSPACE_PATH
    if workspace_root != expected:
        raise ValueError("supplied path is not the exact normalized workspace root")
    return workspace_root


def _require_commit_ancestor(repository_root: Path, snapshot_commit: str) -> None:
    _run_git(repository_root, "cat-file", "-e", f"{snapshot_commit}^{{commit}}")
    ancestry = _run_git(
        repository_root,
        "merge-base",
        "--is-ancestor",
        snapshot_commit,
        "HEAD",
        accepted_returncodes=(0, 1),
    )
    if ancestry.returncode != 0:
        raise ValueError("snapshot commit is not an ancestor of HEAD")


def _validate_repository_path(repository_path: str) -> PurePosixPath:
    path = PurePosixPath(repository_path)
    workspace_path = PurePosixPath(NORMALIZED_WORKSPACE_PATH)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("snapshot repository path must be normalized and relative")
    try:
        path.relative_to(workspace_path)
    except ValueError as exc:
        raise ValueError("snapshot file must be inside the normalized workspace") from exc
    return path


def _verify_git_snapshot_file(
    *,
    repository_root: Path,
    workspace_root: Path,
    snapshot_commit: str,
    name: str,
    repository_path: str,
    expected_blob_oid: str,
    expected_sha256: str,
) -> GitSnapshotFileBinding:
    repository_root = _require_repository_root(repository_root)
    workspace_root = _require_workspace_root(repository_root, workspace_root)
    relative_path = _validate_repository_path(repository_path)
    actual_blob_oid = _run_git(
        repository_root,
        "rev-parse",
        f"{snapshot_commit}:{relative_path.as_posix()}",
    ).stdout.decode("ascii").strip()
    if actual_blob_oid != expected_blob_oid:
        raise ValueError(f"Git blob identity drift: {name}")
    commit_bytes = _run_git(
        repository_root,
        "show",
        f"{snapshot_commit}:{relative_path.as_posix()}",
    ).stdout
    commit_sha256 = hashlib.sha256(commit_bytes).hexdigest()
    if commit_sha256 != expected_sha256:
        raise ValueError(f"Git snapshot bytes drift: {name}")
    current_path = repository_root.joinpath(*relative_path.parts)
    current_bytes, _ = _read_regular_path(
        current_path,
        label=f"Git-bound {name}",
    )
    if current_bytes != commit_bytes:
        raise ValueError(f"current working file drift: {name}")
    workspace_relative = relative_path.relative_to(
        PurePosixPath(NORMALIZED_WORKSPACE_PATH)
    )
    if current_path != workspace_root.joinpath(*workspace_relative.parts):
        raise ValueError(f"normalized workspace mapping drift: {name}")
    return GitSnapshotFileBinding(
        repository_path=relative_path.as_posix(),
        workspace_path=workspace_relative.as_posix(),
        git_blob_oid=actual_blob_oid,
        sha256=commit_sha256,
        size_bytes=len(commit_bytes),
    )


def _build_git_snapshot_binding(
    repository_root: Path,
    workspace_root: Path,
) -> GitSnapshotBinding:
    repository_root = _require_repository_root(repository_root)
    workspace_root = _require_workspace_root(repository_root, workspace_root)
    _require_commit_ancestor(repository_root, SNAPSHOT_COMMIT)
    files = {
        name: _verify_git_snapshot_file(
            repository_root=repository_root,
            workspace_root=workspace_root,
            snapshot_commit=SNAPSHOT_COMMIT,
            name=name,
            repository_path=binding["repository_path"],
            expected_blob_oid=binding["git_blob_oid"],
            expected_sha256=binding["sha256"],
        )
        for name, binding in _SNAPSHOT_FILES.items()
    }
    return GitSnapshotBinding(files=files)


def _validate_relocation_paths(
    *,
    preregistration: dict[str, Any],
    repository_root: Path,
    workspace_root: Path,
    evaluation_root: Path,
) -> RelocationPathBinding:
    repository_root = _require_repository_root(repository_root)
    workspace_root = _require_workspace_root(repository_root, workspace_root)
    chronology = preregistration.get("chronology")
    if not isinstance(chronology, dict):
        raise ValueError("fresh v3 preregistration chronology missing")
    if chronology.get("preregistration_root") != ORIGINAL_PREREGISTRATION_ROOT:
        raise ValueError("original preregistration chronology path mismatch")
    if chronology.get("evaluation_root") != ORIGINAL_EVALUATION_ROOT:
        raise ValueError("original evaluation chronology path mismatch")
    expected_preregistration = repository_root / NORMALIZED_PREREGISTRATION_PATH
    if not expected_preregistration.is_file():
        raise FileNotFoundError(
            f"normalized fresh v3 preregistration missing: {expected_preregistration}"
        )
    expected_evaluation = repository_root / NORMALIZED_EVALUATION_ROOT
    if _absolute_lexical_path(evaluation_root) != expected_evaluation:
        raise ValueError("normalized evaluation root path mismatch")
    return RelocationPathBinding()
