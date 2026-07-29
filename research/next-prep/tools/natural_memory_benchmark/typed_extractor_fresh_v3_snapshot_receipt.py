from __future__ import annotations

import ctypes
import errno
import hashlib
import json
import os
import stat
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from . import typed_extractor_fresh_v3_authoring as authoring
from .typed_extractor_fresh_v3_authoring import _read_regular_path
from .typed_extractor_fresh_v3_prereg import L1_FAMILIES, L2_FAMILIES


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
PREREGISTRATION_SHA256 = authoring.PREREGISTRATION_SHA256
PREREGISTRATION_SCHEMA = authoring.PREREGISTRATION_SCHEMA
EVALUATION_ID = authoring.EVALUATION_ID
RECEIPT_NAME = authoring.RECEIPT_NAME
CANDIDATE_QUEUE_SHA256 = authoring.CANDIDATE_QUEUE_SHA256
GUARD_FINGERPRINT = authoring.GUARD_FINGERPRINT
GUARD_RESULTS_WORKSPACE_PATH = authoring.GUARD_RESULTS_WORKSPACE_PATH
GUARD_RESULTS_SHA256 = authoring.GUARD_RESULTS_SHA256
GUARD_COUNTS = dict(authoring.GUARD_COUNTS)
AUTOMATIC_WRITE_COUNTS = dict(authoring.AUTOMATIC_WRITE_COUNTS)
MATERIALIZATION_WORKSPACE_PATHS = tuple(authoring.MATERIALIZATION_WORKSPACE_PATHS)
_AT_FDCWD = -100
_RENAME_NOREPLACE = 1

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


class PathNeutralAuthoringBinding(StrictModel):
    preregistration_sha256: Literal[
        "183cf6fc2991361e5da57b17e06a5970f651000986d50b87e8af2e6796440204"
    ] = PREREGISTRATION_SHA256
    preregistration_schema: Literal[
        "typed-extractor-fresh-v3-preregistration-v1"
    ] = PREREGISTRATION_SCHEMA
    preregistration_mode: Literal["0444"] = "0444"
    code_sha256: dict[str, str]
    dependency_sha256: dict[str, str]
    blueprint_manifest_sha256: dict[str, str]
    prior_input_sha256: dict[str, str]
    l1_case_count: Literal[24] = 24
    l2_case_count: Literal[18] = 18
    l1_families: dict[str, int]
    l2_families: dict[str, int]

    @model_validator(mode="after")
    def validate_exact_binding(self) -> "PathNeutralAuthoringBinding":
        if self.l1_families != L1_FAMILIES or self.l2_families != L2_FAMILIES:
            raise ValueError("authoring receipt family contract mismatch")
        if set(self.code_sha256) != {
            "typed_extractor_fresh_v3_authoring.py",
            "test_typed_extractor_fresh_v3_authoring.py",
        }:
            raise ValueError("authoring receipt code registry mismatch")
        if set(self.dependency_sha256) != {
            "authoritative_conformance_runner.py",
            "authoritative_memory.py",
            "io.py",
            "typed_extractor_fresh_v3_prereg.py",
            "typed_extractor_l1.py",
            "typed_extractor_l2.py",
        }:
            raise ValueError("authoring receipt dependency registry mismatch")
        if set(self.blueprint_manifest_sha256) != {"l1", "l2"}:
            raise ValueError("authoring receipt blueprint manifest mismatch")
        if len(self.prior_input_sha256) != 39:
            raise ValueError("authoring receipt prior input registry mismatch")
        for hashes in (
            self.code_sha256,
            self.dependency_sha256,
            self.blueprint_manifest_sha256,
            self.prior_input_sha256,
        ):
            if any(not _is_sha256(value) for value in hashes.values()):
                raise ValueError("invalid authoring receipt hash")
        return self


class FreshV3SnapshotRelocationReceipt(StrictModel):
    schema_version: Literal[
        "typed-extractor-fresh-v3-authoring-receipt-v2"
    ] = "typed-extractor-fresh-v3-authoring-receipt-v2"
    status: Literal["frozen"] = "frozen"
    evaluation_id: Literal["typed-extractor-v3-fresh-hidden-v1"] = EVALUATION_ID
    receipt_time: str = Field(
        pattern=r"^2026-07-29T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$"
    )
    receipt_time_source: Literal[
        "caller_supplied_untrusted_utc_label"
    ] = "caller_supplied_untrusted_utc_label"
    git_snapshot: GitSnapshotBinding
    path_binding: RelocationPathBinding
    authoring_binding: PathNeutralAuthoringBinding
    relocation_code_sha256: dict[str, str]
    evaluation_root_absent: Literal[True] = True
    materialization_workspace_paths: list[str]
    materialization_implementation_absent: Literal[True] = True
    hidden_artifact_write_count: Literal[0] = 0
    model_request_count: Literal[0] = 0
    automatic_write_counts: dict[str, int]
    candidate_v3_queue_sha256: Literal[
        "518ead9de8627a9a4384df8cdd9b8728a21fcf797f6b0f3d208dfcb28ac41c0f"
    ] = CANDIDATE_QUEUE_SHA256
    guard_fingerprint: Literal[
        "e184b6caf2998acf1c8700bc84d24bbafd49ab9c8f15738d1af8cc484ee5ebcc"
    ] = GUARD_FINGERPRINT
    guard_results_path: Literal[
        "artifacts/natural-benchmark-slices/slice-v1/"
        "symbolic-fallback-answerability-v2-fastembed-results.json"
    ] = GUARD_RESULTS_WORKSPACE_PATH
    guard_results_sha256: Literal[
        "f90ee6a8d9ee4a0beb993ae2055c2e7ededd013de9a70e6ce588efbbfedd2645"
    ] = GUARD_RESULTS_SHA256
    guard_counts: dict[str, int]
    pipeline_integration_authorized: Literal[False] = False
    embedding_authority: Literal[False] = False
    manual_identity_adjudications_materialized: Literal[False] = False
    external_memory_systems_rerun: Literal[False] = False
    longmemeval_status: Literal[
        "structured_l2_identity_unresolved"
    ] = "structured_l2_identity_unresolved"

    @field_validator("receipt_time")
    @classmethod
    def validate_receipt_time(cls, value: str) -> str:
        try:
            parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError as exc:
            raise ValueError("receipt_time must be a valid UTC timestamp") from exc
        if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
            raise ValueError("receipt_time must be a valid UTC timestamp")
        return value

    @model_validator(mode="after")
    def validate_exact_contract(self) -> "FreshV3SnapshotRelocationReceipt":
        if set(self.relocation_code_sha256) != {
            "typed_extractor_fresh_v3_snapshot_receipt.py",
            "test_typed_extractor_fresh_v3_snapshot_receipt.py",
        }:
            raise ValueError("relocation receipt code registry mismatch")
        if any(
            not _is_sha256(value)
            for value in self.relocation_code_sha256.values()
        ):
            raise ValueError("invalid relocation receipt code hash")
        if self.materialization_workspace_paths != list(
            MATERIALIZATION_WORKSPACE_PATHS
        ):
            raise ValueError("materialization path registry mismatch")
        if self.automatic_write_counts != AUTOMATIC_WRITE_COUNTS:
            raise ValueError("authoring receipt write boundary mismatch")
        if self.guard_counts != GUARD_COUNTS:
            raise ValueError("authoring receipt guard count mismatch")
        return self


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


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _entry_exists(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    return True


def _require_future_absent(evaluation_root: Path, workspace_root: Path) -> None:
    if _entry_exists(evaluation_root):
        raise ValueError("fresh v3 evaluation root must be absent before authoring receipt")
    for raw_path in MATERIALIZATION_WORKSPACE_PATHS:
        path = _absolute_lexical_path(workspace_root / raw_path)
        if _entry_exists(path):
            raise ValueError(f"materialization artifact must be absent: {path}")


def _protected_state(workspace_root: Path) -> dict[str, Any]:
    return authoring._protected_state(workspace_root)


def _relocation_code_paths(workspace_root: Path) -> dict[str, Path]:
    return {
        "typed_extractor_fresh_v3_snapshot_receipt.py": (
            workspace_root
            / "tools/natural_memory_benchmark/"
            "typed_extractor_fresh_v3_snapshot_receipt.py"
        ),
        "test_typed_extractor_fresh_v3_snapshot_receipt.py": (
            workspace_root
            / "tests/natural_memory_benchmark/"
            "test_typed_extractor_fresh_v3_snapshot_receipt.py"
        ),
    }


def _hash_regular_file(path: Path, *, label: str) -> str:
    content, _ = _read_regular_path(path, label=label)
    return hashlib.sha256(content).hexdigest()


def build_fresh_v3_snapshot_relocation_receipt(
    repository_root: Path,
    workspace_root: Path,
    evaluation_root: Path,
    receipt_time: str,
) -> FreshV3SnapshotRelocationReceipt:
    repository_root = _require_repository_root(repository_root)
    workspace_root = _require_workspace_root(repository_root, workspace_root)
    evaluation_root = _absolute_lexical_path(evaluation_root)
    preregistration_path = repository_root / NORMALIZED_PREREGISTRATION_PATH
    preregistration = authoring._load_preregistration(preregistration_path)
    path_binding = _validate_relocation_paths(
        preregistration=preregistration,
        repository_root=repository_root,
        workspace_root=workspace_root,
        evaluation_root=evaluation_root,
    )
    git_snapshot = _build_git_snapshot_binding(repository_root, workspace_root)
    _require_future_absent(evaluation_root, workspace_root)
    protected_state = _protected_state(workspace_root)
    bundle = authoring.build_fresh_v3_authoring_bundle(preregistration_path)

    preregistration_bytes, preregistration_stat = _read_regular_path(
        preregistration_path,
        label="normalized fresh v3 preregistration",
    )
    if hashlib.sha256(preregistration_bytes).hexdigest() != PREREGISTRATION_SHA256:
        raise ValueError("fresh v3 preregistration hash drift")
    if stat.S_IMODE(preregistration_stat.st_mode) != 0o444:
        raise ValueError("fresh v3 preregistration must have mode 0444")

    code_paths = authoring._code_paths(workspace_root)
    dependency_paths = authoring._dependency_paths(workspace_root)
    relocation_paths = _relocation_code_paths(workspace_root)
    code_sha256 = {
        name: _hash_regular_file(path, label=f"authoring code {name}")
        for name, path in code_paths.items()
    }
    dependency_sha256 = {
        name: _hash_regular_file(path, label=f"authoring dependency {name}")
        for name, path in dependency_paths.items()
    }
    relocation_code_sha256 = {
        name: _hash_regular_file(path, label=f"relocation code {name}")
        for name, path in relocation_paths.items()
    }

    authoring_binding = PathNeutralAuthoringBinding(
        code_sha256=code_sha256,
        dependency_sha256=dependency_sha256,
        blueprint_manifest_sha256={
            "l1": authoring._hash_value(
                [item.model_dump(mode="json") for item in bundle.l1.blueprints]
            ),
            "l2": authoring._hash_value(
                [item.model_dump(mode="json") for item in bundle.l2.blueprints]
            ),
        },
        prior_input_sha256=preregistration["input_sha256"],
        l1_families=dict(L1_FAMILIES),
        l2_families=dict(L2_FAMILIES),
    )
    return FreshV3SnapshotRelocationReceipt(
        receipt_time=receipt_time,
        git_snapshot=git_snapshot,
        path_binding=path_binding,
        authoring_binding=authoring_binding,
        relocation_code_sha256=relocation_code_sha256,
        materialization_workspace_paths=list(MATERIALIZATION_WORKSPACE_PATHS),
        automatic_write_counts=dict(AUTOMATIC_WRITE_COUNTS),
        guard_results_sha256=protected_state["guard_results_sha256"],
        guard_counts=protected_state["guard_counts"],
    )


def _write_snapshot_receipt_no_clobber(
    receipt_path: Path,
    receipt: FreshV3SnapshotRelocationReceipt,
    *,
    before_publish: Callable[[], None] | None = None,
) -> None:
    _require_no_stale_named_staging(receipt_path)
    content = authoring.canonical_json_bytes(receipt)
    matching_receipt = authoring._require_matching_existing_receipt(
        receipt_path,
        content,
    )
    if matching_receipt is not None:
        if before_publish is not None:
            before_publish()
        _validate_matching_receipt_after_barrier(
            receipt_path,
            content,
            missing_message="fresh v3 relocation receipt disappeared",
        )
        return

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{receipt_path.name}.staging-",
        suffix=".tmp",
        dir=receipt_path.parent,
    )
    temporary_path = Path(temporary_name)
    try:
        authoring._write_all(descriptor, content)
        os.fsync(descriptor)
        os.fchmod(descriptor, 0o444)
        os.fsync(descriptor)
        if before_publish is not None:
            before_publish()
        authoring._assert_path_matches_opened(
            temporary_path,
            os.fstat(descriptor),
            label="fresh v3 relocation receipt staging file",
        )
        _assert_staging_descriptor_content(descriptor, content)
        try:
            _publish_named_receipt_noreplace(temporary_path, receipt_path)
        except FileExistsError:
            matching_receipt = authoring._require_matching_existing_receipt(
                receipt_path,
                content,
            )
            if matching_receipt is None:
                raise ValueError(
                    "fresh v3 relocation receipt disappeared during publication"
                )
            _validate_matching_receipt_after_barrier(
                receipt_path,
                content,
                missing_message=(
                    "fresh v3 relocation receipt disappeared during publication"
                ),
            )
            return
        authoring._fsync_directory(receipt_path.parent)
        authoring._assert_path_matches_opened(
            receipt_path,
            os.fstat(descriptor),
            label="fresh v3 relocation receipt",
        )
    finally:
        os.close(descriptor)
        temporary_path.unlink(missing_ok=True)

    matching_receipt = authoring._require_matching_existing_receipt(
        receipt_path,
        content,
    )
    if matching_receipt is None:
        raise ValueError("fresh v3 relocation receipt missing after publication")
    authoring._assert_path_matches_opened(
        receipt_path,
        matching_receipt,
        label="fresh v3 relocation receipt",
    )


def _require_no_stale_named_staging(receipt_path: Path) -> None:
    prefix = f".{receipt_path.name}.staging-"
    stale = sorted(
        path.name
        for path in receipt_path.parent.iterdir()
        if path.name.startswith(prefix) and path.name.endswith(".tmp")
    )
    if stale:
        raise ValueError(f"fresh v3 relocation receipt stale staging file exists: {stale}")


def _validate_matching_receipt_after_barrier(
    receipt_path: Path,
    content: bytes,
    *,
    missing_message: str,
) -> None:
    authoring._fsync_directory(receipt_path.parent)
    matching_receipt = authoring._require_matching_existing_receipt(
        receipt_path,
        content,
    )
    if matching_receipt is None:
        raise ValueError(missing_message)
    authoring._assert_path_matches_opened(
        receipt_path,
        matching_receipt,
        label="fresh v3 relocation receipt",
    )


def _assert_staging_descriptor_content(
    descriptor: int,
    expected: bytes,
) -> None:
    opened = os.fstat(descriptor)
    if stat.S_IMODE(opened.st_mode) != 0o444 or opened.st_size != len(expected):
        raise ValueError("fresh v3 relocation receipt staging bytes changed")
    chunks: list[bytes] = []
    offset = 0
    while offset < len(expected):
        chunk = os.pread(descriptor, len(expected) - offset, offset)
        if not chunk:
            raise ValueError("fresh v3 relocation receipt staging bytes changed")
        chunks.append(chunk)
        offset += len(chunk)
    if b"".join(chunks) != expected:
        raise ValueError("fresh v3 relocation receipt staging bytes changed")
    rechecked = os.fstat(descriptor)
    if (
        (rechecked.st_dev, rechecked.st_ino) != (opened.st_dev, opened.st_ino)
        or stat.S_IMODE(rechecked.st_mode) != 0o444
        or rechecked.st_size != len(expected)
    ):
        raise ValueError("fresh v3 relocation receipt staging bytes changed")


def _publish_named_receipt_noreplace(source: Path, target: Path) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None:
        raise RuntimeError(
            "renameat2 is required for relocation receipt publication"
        )
    renameat2.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    renameat2.restype = ctypes.c_int
    result = renameat2(
        _AT_FDCWD,
        os.fsencode(source),
        _AT_FDCWD,
        os.fsencode(target),
        _RENAME_NOREPLACE,
    )
    if result == 0:
        return
    error_number = ctypes.get_errno()
    if error_number == errno.EEXIST:
        raise FileExistsError(
            error_number,
            f"fresh v3 relocation receipt already exists: {target}",
            str(target),
        )
    raise OSError(error_number, os.strerror(error_number), f"{source} -> {target}")


def _read_snapshot_receipt(
    receipt_path: Path,
) -> tuple[FreshV3SnapshotRelocationReceipt, bytes, os.stat_result]:
    existing = authoring._read_existing_receipt(receipt_path)
    if existing is None:
        raise FileNotFoundError(f"fresh v3 relocation receipt missing: {receipt_path}")
    receipt_bytes, opened = existing
    payload = json.loads(receipt_bytes)
    receipt = FreshV3SnapshotRelocationReceipt.model_validate(
        payload,
        strict=True,
    )
    if receipt_bytes != authoring.canonical_json_bytes(receipt):
        raise ValueError("fresh v3 relocation receipt must use canonical JSON bytes")
    return receipt, receipt_bytes, opened


def freeze_fresh_v3_snapshot_relocation_receipt(
    repository_root: Path,
    workspace_root: Path,
    evaluation_root: Path,
    receipt_time: str,
) -> dict[str, Any]:
    repository_root = _require_repository_root(repository_root)
    workspace_root = _require_workspace_root(repository_root, workspace_root)
    evaluation_root = _absolute_lexical_path(evaluation_root)
    preregistration_path = repository_root / NORMALIZED_PREREGISTRATION_PATH
    receipt_path = preregistration_path.parent / RECEIPT_NAME

    with authoring.fresh_v3_chronology_lock(
        preregistration_path
    ) as locked_preregistration:
        receipt = build_fresh_v3_snapshot_relocation_receipt(
            repository_root,
            workspace_root,
            evaluation_root,
            receipt_time,
        )

        def recheck_before_publication() -> None:
            authoring._assert_path_matches_opened(
                preregistration_path,
                locked_preregistration,
                label="normalized fresh v3 preregistration",
            )
            rechecked = build_fresh_v3_snapshot_relocation_receipt(
                repository_root,
                workspace_root,
                evaluation_root,
                receipt_time,
            )
            if authoring.canonical_json_bytes(rechecked) != authoring.canonical_json_bytes(
                receipt
            ):
                raise ValueError(
                    "fresh v3 relocation inputs changed during receipt freeze"
                )
            _require_future_absent(evaluation_root, workspace_root)
            _protected_state(workspace_root)
            authoring._assert_path_matches_opened(
                preregistration_path,
                locked_preregistration,
                label="normalized fresh v3 preregistration",
            )

        recheck_before_publication()
        _write_snapshot_receipt_no_clobber(
            receipt_path,
            receipt,
            before_publish=recheck_before_publication,
        )
    return receipt.model_dump(mode="json")


def validate_fresh_v3_snapshot_relocation_receipt(
    repository_root: Path,
    workspace_root: Path,
    evaluation_root: Path,
) -> dict[str, Any]:
    repository_root = _require_repository_root(repository_root)
    workspace_root = _require_workspace_root(repository_root, workspace_root)
    evaluation_root = _absolute_lexical_path(evaluation_root)
    preregistration_path = repository_root / NORMALIZED_PREREGISTRATION_PATH
    receipt_path = preregistration_path.parent / RECEIPT_NAME
    actual, receipt_bytes, opened_receipt = _read_snapshot_receipt(receipt_path)
    expected = build_fresh_v3_snapshot_relocation_receipt(
        repository_root,
        workspace_root,
        evaluation_root,
        actual.receipt_time,
    )
    if actual != expected:
        raise ValueError("fresh v3 snapshot relocation receipt drift")
    authoring._assert_path_matches_opened(
        receipt_path,
        opened_receipt,
        label="fresh v3 snapshot relocation receipt",
    )
    return {
        "status": "valid",
        "active_receipt": RECEIPT_NAME,
        "schema_version": actual.schema_version,
        "l1_case_count": actual.authoring_binding.l1_case_count,
        "l2_case_count": actual.authoring_binding.l2_case_count,
        "evaluation_root_absent": True,
        "materialization_implementation_absent": True,
        "hidden_artifacts_created": False,
        "model_request_count": actual.model_request_count,
        "receipt_sha256": hashlib.sha256(receipt_bytes).hexdigest(),
    }
