from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

import pytest

from tools.natural_memory_benchmark.io import load_json
from tools.natural_memory_benchmark import (
    typed_extractor_fresh_v3_snapshot_receipt as relocation,
)


REPOSITORY = Path(__file__).resolve().parents[4]
WORKSPACE = REPOSITORY / "research/next-prep"
ASSESSMENT = WORKSPACE / "artifacts/automatic-extraction-assessment"
FORMAL_PREREGISTRATION = (
    ASSESSMENT
    / "typed-extractor-v3-fresh-hidden-prereg-v1"
    / "preregistration.json"
)
FORMAL_EVALUATION = ASSESSMENT / "typed-extractor-v3-fresh-hidden-v1"
SNAPSHOT_COMMIT = "00fa803ee44bcef5a299babb9a8e2b7ba9f994e4"
EXPECTED_BLOBS = {
    "preregistration": "6433fef43d7c2d68f064d900ff28172f94b4968e",
    "authoring_module": "bbe36a908ce7210c2919bb66328d4d4275851fe9",
    "authoring_test": "d92a28b2dae92bc4ddeecaca05f7520b864f24c2",
}
EXPECTED_SHA256 = {
    "preregistration": (
        "183cf6fc2991361e5da57b17e06a5970f651000986d50b87e8af2e6796440204"
    ),
    "authoring_module": (
        "c8ffb3f9466583ecad42049b200224ef038c9c85b6edaec73f2723944ebd8bad"
    ),
    "authoring_test": (
        "ffba0281ca47d6e10781c06471c86367424780010e5cdeff458cba22f16db02a"
    ),
}


def _git(repository: Path, *args: str, input_bytes: bytes | None = None) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(repository), *args],
        check=True,
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return completed.stdout.strip()


def _temporary_repository(tmp_path: Path) -> tuple[Path, str, str, str]:
    repository = tmp_path / "repository"
    repository.mkdir()
    _git(repository, "init", "-q")
    tracked = repository / "research/next-prep/bound.txt"
    tracked.parent.mkdir(parents=True)
    tracked.write_bytes(b"fixed snapshot bytes\n")
    _git(repository, "add", "research/next-prep/bound.txt")
    _git(
        repository,
        "-c",
        "user.name=Snapshot Test",
        "-c",
        "user.email=snapshot@example.invalid",
        "commit",
        "-q",
        "-m",
        "snapshot",
    )
    commit = _git(repository, "rev-parse", "HEAD").decode()
    blob = _git(
        repository,
        "rev-parse",
        f"{commit}:research/next-prep/bound.txt",
    ).decode()
    sha256 = hashlib.sha256(tracked.read_bytes()).hexdigest()
    return repository, commit, blob, sha256


def test_formal_snapshot_binds_fixed_commit_blobs_and_current_bytes() -> None:
    binding = relocation._build_git_snapshot_binding(REPOSITORY, WORKSPACE)

    assert binding.evidence_kind == "git-commit-blob-plus-sha256"
    assert binding.snapshot_commit == SNAPSHOT_COMMIT
    assert binding.snapshot_commit_is_ancestor is True
    assert {
        name: item.git_blob_oid for name, item in binding.files.items()
    } == EXPECTED_BLOBS
    assert {name: item.sha256 for name, item in binding.files.items()} == EXPECTED_SHA256


def test_git_file_binding_rejects_dirty_or_symlink_worktree_file(
    tmp_path: Path,
) -> None:
    repository, commit, blob, sha256 = _temporary_repository(tmp_path)
    workspace = repository / "research/next-prep"
    path = "research/next-prep/bound.txt"

    binding = relocation._verify_git_snapshot_file(
        repository_root=repository,
        workspace_root=workspace,
        snapshot_commit=commit,
        name="bound",
        repository_path=path,
        expected_blob_oid=blob,
        expected_sha256=sha256,
    )
    assert binding.repository_path == path

    tracked = repository / path
    tracked.write_bytes(b"dirty bytes\n")
    with pytest.raises(ValueError, match="current working file drift"):
        relocation._verify_git_snapshot_file(
            repository_root=repository,
            workspace_root=workspace,
            snapshot_commit=commit,
            name="bound",
            repository_path=path,
            expected_blob_oid=blob,
            expected_sha256=sha256,
        )

    tracked.unlink()
    os.symlink(repository / ".git/HEAD", tracked)
    with pytest.raises(ValueError, match="regular non-symlink"):
        relocation._verify_git_snapshot_file(
            repository_root=repository,
            workspace_root=workspace,
            snapshot_commit=commit,
            name="bound",
            repository_path=path,
            expected_blob_oid=blob,
            expected_sha256=sha256,
        )


def test_git_snapshot_rejects_non_ancestor_commit(tmp_path: Path) -> None:
    repository, commit, _, _ = _temporary_repository(tmp_path)
    tree = _git(repository, "rev-parse", f"{commit}^{{tree}}").decode()
    unrelated = subprocess.run(
        ["git", "-C", str(repository), "commit-tree", tree],
        check=True,
        input=b"unrelated\n",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "Snapshot Test",
            "GIT_AUTHOR_EMAIL": "snapshot@example.invalid",
            "GIT_COMMITTER_NAME": "Snapshot Test",
            "GIT_COMMITTER_EMAIL": "snapshot@example.invalid",
        },
    ).stdout.strip().decode()
    _git(repository, "checkout", "-q", "--detach", unrelated)

    with pytest.raises(ValueError, match="not an ancestor"):
        relocation._require_commit_ancestor(repository, commit)


def test_git_snapshot_rejects_wrong_repository_or_workspace_root(
    tmp_path: Path,
) -> None:
    not_repository = tmp_path / "not-repository"
    not_repository.mkdir()
    with pytest.raises(ValueError, match="Git repository root"):
        relocation._require_repository_root(not_repository)

    with pytest.raises(ValueError, match="normalized workspace root"):
        relocation._build_git_snapshot_binding(REPOSITORY, WORKSPACE.parent)


def test_relocation_mapping_preserves_original_and_normalized_paths() -> None:
    preregistration = load_json(FORMAL_PREREGISTRATION)

    binding = relocation._validate_relocation_paths(
        preregistration=preregistration,
        repository_root=REPOSITORY,
        workspace_root=WORKSPACE,
        evaluation_root=FORMAL_EVALUATION,
    )

    assert binding.original_preregistration_root == (
        "/public/home/wwb/KE-mem/KE-memory-next-prep-20260727/"
        "artifacts/automatic-extraction-assessment/"
        "typed-extractor-v3-fresh-hidden-prereg-v1"
    )
    assert binding.original_evaluation_root == (
        "/public/home/wwb/KE-mem/KE-memory-next-prep-20260727/"
        "artifacts/automatic-extraction-assessment/"
        "typed-extractor-v3-fresh-hidden-v1"
    )
    assert binding.normalized_repository_root == "."
    assert binding.normalized_workspace_root == "research/next-prep"
    assert binding.normalized_preregistration_path == (
        "research/next-prep/artifacts/automatic-extraction-assessment/"
        "typed-extractor-v3-fresh-hidden-prereg-v1/preregistration.json"
    )
    assert binding.normalized_evaluation_root == (
        "research/next-prep/artifacts/automatic-extraction-assessment/"
        "typed-extractor-v3-fresh-hidden-v1"
    )
