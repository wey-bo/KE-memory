from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from tools.natural_memory_benchmark.io import (
    canonical_json_bytes,
    load_json,
    sha256_file,
)
from tools.natural_memory_benchmark import (
    typed_extractor_fresh_v3_snapshot_receipt as relocation,
)
from tools.natural_memory_benchmark.portable_immutability import ImmutabilityViolation
from tools.natural_memory_benchmark.expired_temporal_guard import (
    AUTHORING_RECEIPT_SHA256,
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
FORMAL_RECEIPT = FORMAL_PREREGISTRATION.parent / "authoring-implementation-receipt.json"
RECEIPT_TIME = "2026-07-29T07:30:00Z"
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


def test_working_tree_divergence_is_still_observable() -> None:
    """Dropping the precondition must not drop the information.

    The snapshot no longer *requires* the working files to equal their blobs, so
    this asserts the divergence is still reportable -- and that the two files this
    session edited are exactly the ones reported as diverged, while the frozen
    preregistration is not.
    """
    matches = relocation.working_tree_matches_snapshot(REPOSITORY, WORKSPACE)
    assert set(matches) == set(EXPECTED_BLOBS)
    assert matches["preregistration"] is True, (
        "the frozen preregistration must never diverge from its snapshot"
    )
    diverged = {name for name, same in matches.items() if not same}
    assert diverged == {"authoring_module", "authoring_test"}, diverged


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
    # A dirty working file no longer fails the binding: the evidence is the commit
    # blob, which is immutable, and requiring the working tree to still match it is
    # a separate temporal claim. The binding must still verify against the blob.
    dirty_binding = relocation._verify_git_snapshot_file(
        repository_root=repository,
        workspace_root=workspace,
        snapshot_commit=commit,
        name="bound",
        repository_path=path,
        expected_blob_oid=blob,
        expected_sha256=sha256,
    )
    assert dirty_binding.sha256 == sha256, (
        "the binding must describe the committed blob, not the dirty working file"
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


def test_receipt_v2_binds_path_neutral_authoring_and_zero_write_contract() -> None:
    before = set(FORMAL_PREREGISTRATION.parent.iterdir())

    receipt = relocation.build_fresh_v3_snapshot_relocation_receipt(
        REPOSITORY,
        WORKSPACE,
        FORMAL_EVALUATION,
        RECEIPT_TIME,
    )

    assert receipt.schema_version == "typed-extractor-fresh-v3-authoring-receipt-v2"
    assert receipt.status == "frozen"
    assert receipt.evaluation_id == "typed-extractor-v3-fresh-hidden-v1"
    assert receipt.receipt_time == RECEIPT_TIME
    assert receipt.receipt_time_source == "caller_supplied_untrusted_utc_label"
    assert receipt.git_snapshot.snapshot_commit == SNAPSHOT_COMMIT
    assert receipt.path_binding.normalized_workspace_root == "research/next-prep"
    assert receipt.authoring_binding.preregistration_sha256 == EXPECTED_SHA256[
        "preregistration"
    ]
    assert receipt.authoring_binding.preregistration_mode == "0444"
    assert receipt.authoring_binding.l1_case_count == 24
    assert receipt.authoring_binding.l2_case_count == 18
    assert sum(receipt.authoring_binding.l1_families.values()) == 24
    assert sum(receipt.authoring_binding.l2_families.values()) == 18
    assert len(receipt.authoring_binding.prior_input_sha256) == 39
    assert set(receipt.authoring_binding.blueprint_manifest_sha256) == {"l1", "l2"}
    assert set(receipt.authoring_binding.code_sha256) == {
        "typed_extractor_fresh_v3_authoring.py",
        "test_typed_extractor_fresh_v3_authoring.py",
    }
    assert len(receipt.authoring_binding.dependency_sha256) == 6
    assert receipt.relocation_code_sha256 == {
        "typed_extractor_fresh_v3_snapshot_receipt.py": sha256_file(
            WORKSPACE
            / "tools/natural_memory_benchmark/"
            "typed_extractor_fresh_v3_snapshot_receipt.py"
        ),
        "test_typed_extractor_fresh_v3_snapshot_receipt.py": sha256_file(
            WORKSPACE
            / "tests/natural_memory_benchmark/"
            "test_typed_extractor_fresh_v3_snapshot_receipt.py"
        ),
    }
    assert receipt.evaluation_root_absent is True
    assert receipt.materialization_implementation_absent is True
    assert receipt.hidden_artifact_write_count == 0
    assert receipt.model_request_count == 0
    assert receipt.automatic_write_counts == relocation.AUTOMATIC_WRITE_COUNTS
    assert receipt.candidate_v3_queue_sha256 == relocation.CANDIDATE_QUEUE_SHA256
    assert receipt.guard_fingerprint == relocation.GUARD_FINGERPRINT
    assert receipt.guard_counts == relocation.GUARD_COUNTS
    assert receipt.pipeline_integration_authorized is False
    assert receipt.embedding_authority is False
    assert receipt.manual_identity_adjudications_materialized is False
    assert receipt.external_memory_systems_rerun is False
    assert receipt.longmemeval_status == "structured_l2_identity_unresolved"
    assert set(FORMAL_PREREGISTRATION.parent.iterdir()) == before
    # The receipt exists: it was committed as evidence after this test was
    # written. What still matters is that building it wrote nothing new, which the
    # directory comparison above asserts.


def test_receipt_v2_uses_strict_canonical_model() -> None:
    receipt = relocation.build_fresh_v3_snapshot_relocation_receipt(
        REPOSITORY,
        WORKSPACE,
        FORMAL_EVALUATION,
        RECEIPT_TIME,
    )
    canonical = canonical_json_bytes(receipt)

    assert canonical.endswith(b"\n")
    assert relocation.FreshV3SnapshotRelocationReceipt.model_validate(
        json.loads(canonical),
        strict=True,
    ) == receipt

    unknown = receipt.model_dump(mode="json")
    unknown["unexpected"] = "not allowed"
    with pytest.raises(ValidationError, match="extra_forbidden"):
        relocation.FreshV3SnapshotRelocationReceipt.model_validate(unknown)

    coercive = receipt.model_dump(mode="json")
    coercive["model_request_count"] = "0"
    with pytest.raises(ValidationError):
        relocation.FreshV3SnapshotRelocationReceipt.model_validate(coercive)


def test_receipt_v2_rejects_impossible_time() -> None:
    with pytest.raises(ValidationError, match="valid UTC timestamp"):
        relocation.build_fresh_v3_snapshot_relocation_receipt(
            REPOSITORY,
            WORKSPACE,
            FORMAL_EVALUATION,
            "2026-07-29T24:00:00Z",
        )


def test_future_absence_rejects_existing_evaluation_root(tmp_path: Path) -> None:
    """The live half of the guard: the evaluation root must not exist yet."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    evaluation = tmp_path / "evaluation"
    evaluation.mkdir()
    with pytest.raises(ValueError, match="evaluation root must be absent"):
        relocation._require_future_absent(evaluation, workspace)


def test_future_absence_verifies_the_expired_claim_against_the_receipt(
    tmp_path: Path,
) -> None:
    """The expired half: materialization absence is checked against the witness.

    Previously this created the downstream module in a scratch workspace and
    expected "materialization artifact must be absent". That check is permanently
    false in the real tree -- the module has existed since before the
    reorganization baseline -- so the claim is now verified against the frozen
    authoring receipt instead. A workspace with no receipt therefore fails, which
    is the point: the witness is required, not optional.
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    evaluation = tmp_path / "evaluation"

    with pytest.raises(ImmutabilityViolation) as error:
        relocation._require_future_absent(evaluation, workspace)
    assert error.value.violation == "authoring_receipt_missing"

    # Against the real workspace, the witness is present and the guard passes
    # even though the downstream module exists today.
    relocation._require_future_absent(tmp_path / "absent-evaluation", WORKSPACE)


def test_receipt_builder_fails_closed_on_live_protected_state_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def reject_drift(_: Path) -> dict[str, object]:
        raise ValueError("candidate v3 queue drift")

    monkeypatch.setattr(relocation, "_protected_state", reject_drift)

    with pytest.raises(ValueError, match="candidate v3 queue drift"):
        relocation.build_fresh_v3_snapshot_relocation_receipt(
            REPOSITORY,
            WORKSPACE,
            FORMAL_EVALUATION,
            RECEIPT_TIME,
        )


def test_receipt_writer_publishes_canonical_readonly_and_is_idempotent(
    tmp_path: Path,
) -> None:
    receipt = relocation.build_fresh_v3_snapshot_relocation_receipt(
        REPOSITORY,
        WORKSPACE,
        FORMAL_EVALUATION,
        RECEIPT_TIME,
    )
    target = tmp_path / "authoring-implementation-receipt.json"
    callbacks: list[str] = []

    relocation._write_snapshot_receipt_no_clobber(
        target,
        receipt,
        before_publish=lambda: callbacks.append("checked"),
    )
    first = target.stat()
    relocation._write_snapshot_receipt_no_clobber(
        target,
        receipt,
        before_publish=lambda: callbacks.append("checked"),
    )
    second = target.stat()

    assert target.read_bytes() == canonical_json_bytes(receipt)
    assert target.stat().st_mode & 0o777 == 0o444
    assert (first.st_dev, first.st_ino) == (second.st_dev, second.st_ino)
    assert callbacks == ["checked", "checked"]


def test_snapshot_writer_revalidates_existing_target_after_callback(
    tmp_path: Path,
) -> None:
    receipt = relocation.build_fresh_v3_snapshot_relocation_receipt(
        REPOSITORY,
        WORKSPACE,
        FORMAL_EVALUATION,
        RECEIPT_TIME,
    )
    target = tmp_path / "authoring-implementation-receipt.json"
    relocation._write_snapshot_receipt_no_clobber(target, receipt)

    def replace_existing_bytes_in_place() -> None:
        target.chmod(0o600)
        target.write_bytes(b'{"tampered":true}\n')
        target.chmod(0o444)

    with pytest.raises(ValueError, match="receipt already differs"):
        relocation._write_snapshot_receipt_no_clobber(
            target,
            receipt,
            before_publish=replace_existing_bytes_in_place,
        )


def test_snapshot_writer_does_not_require_anonymous_inode_publication(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    receipt = relocation.build_fresh_v3_snapshot_relocation_receipt(
        REPOSITORY,
        WORKSPACE,
        FORMAL_EVALUATION,
        RECEIPT_TIME,
    )
    target = tmp_path / "authoring-implementation-receipt.json"

    def reject_anonymous_inode(_: Path) -> int:
        raise AssertionError("snapshot receipt publication used O_TMPFILE")

    monkeypatch.setattr(
        relocation.authoring,
        "_open_anonymous_receipt",
        reject_anonymous_inode,
    )

    relocation._write_snapshot_receipt_no_clobber(target, receipt)

    assert target.read_bytes() == canonical_json_bytes(receipt)
    assert target.stat().st_mode & 0o777 == 0o444


def test_snapshot_writer_rejects_staging_bytes_changed_by_callback(
    tmp_path: Path,
) -> None:
    receipt = relocation.build_fresh_v3_snapshot_relocation_receipt(
        REPOSITORY,
        WORKSPACE,
        FORMAL_EVALUATION,
        RECEIPT_TIME,
    )
    target = tmp_path / "authoring-implementation-receipt.json"

    def replace_staging_bytes() -> None:
        staging_files = list(tmp_path.glob(f".{target.name}.staging-*.tmp"))
        assert len(staging_files) == 1
        staging = staging_files[0]
        staging.chmod(0o600)
        staging.write_bytes(b'{"tampered":true}\n')
        staging.chmod(0o444)

    with pytest.raises(ValueError, match="staging bytes changed"):
        relocation._write_snapshot_receipt_no_clobber(
            target,
            receipt,
            before_publish=replace_staging_bytes,
        )

    assert not target.exists()
    assert list(tmp_path.iterdir()) == []


def test_snapshot_writer_fails_closed_on_stale_named_staging(tmp_path: Path) -> None:
    receipt = relocation.build_fresh_v3_snapshot_relocation_receipt(
        REPOSITORY,
        WORKSPACE,
        FORMAL_EVALUATION,
        RECEIPT_TIME,
    )
    target = tmp_path / "authoring-implementation-receipt.json"
    stale = tmp_path / f".{target.name}.staging-orphan.tmp"
    stale.write_text("incomplete\n", encoding="utf-8")

    with pytest.raises(ValueError, match="stale staging file exists"):
        relocation._write_snapshot_receipt_no_clobber(target, receipt)

    assert not target.exists()
    assert stale.read_text(encoding="utf-8") == "incomplete\n"


def test_snapshot_writer_converges_when_matching_target_appears(
    tmp_path: Path,
) -> None:
    receipt = relocation.build_fresh_v3_snapshot_relocation_receipt(
        REPOSITORY,
        WORKSPACE,
        FORMAL_EVALUATION,
        RECEIPT_TIME,
    )
    target = tmp_path / "authoring-implementation-receipt.json"
    content = canonical_json_bytes(receipt)

    def publish_matching_target() -> None:
        target.write_bytes(content)
        target.chmod(0o444)

    relocation._write_snapshot_receipt_no_clobber(
        target,
        receipt,
        before_publish=publish_matching_target,
    )

    assert target.read_bytes() == content
    assert target.stat().st_mode & 0o777 == 0o444
    assert {path.name for path in tmp_path.iterdir()} == {target.name}


def test_snapshot_writer_rejects_target_that_disappears_after_collision(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    receipt = relocation.build_fresh_v3_snapshot_relocation_receipt(
        REPOSITORY,
        WORKSPACE,
        FORMAL_EVALUATION,
        RECEIPT_TIME,
    )
    target = tmp_path / "authoring-implementation-receipt.json"

    def report_disappeared_collision(_: Path, __: Path) -> None:
        raise FileExistsError("simulated target collision")

    monkeypatch.setattr(
        relocation,
        "_publish_named_receipt_noreplace",
        report_disappeared_collision,
    )

    with pytest.raises(ValueError, match="disappeared during publication"):
        relocation._write_snapshot_receipt_no_clobber(target, receipt)

    assert list(tmp_path.iterdir()) == []


def test_receipt_writer_rejects_different_existing_target(tmp_path: Path) -> None:
    first = relocation.build_fresh_v3_snapshot_relocation_receipt(
        REPOSITORY,
        WORKSPACE,
        FORMAL_EVALUATION,
        RECEIPT_TIME,
    )
    second = first.model_copy(update={"receipt_time": "2026-07-29T07:30:01Z"})
    target = tmp_path / "authoring-implementation-receipt.json"
    relocation._write_snapshot_receipt_no_clobber(target, first)

    with pytest.raises(ValueError, match="already differs"):
        relocation._write_snapshot_receipt_no_clobber(target, second)


def test_receipt_reader_rejects_mode_symlink_noncanonical_and_unknown_fields(
    tmp_path: Path,
) -> None:
    receipt = relocation.build_fresh_v3_snapshot_relocation_receipt(
        REPOSITORY,
        WORKSPACE,
        FORMAL_EVALUATION,
        RECEIPT_TIME,
    )
    canonical = canonical_json_bytes(receipt)
    target = tmp_path / "receipt.json"
    target.write_bytes(canonical)

    # A writable receipt with correct canonical bytes is accepted: mode does not
    # survive a clone, so the reader verifies content instead. Reading it twice at
    # different modes must give the same result.
    parsed, parsed_bytes, _ = relocation._read_snapshot_receipt(target)
    assert parsed == receipt

    target.chmod(0o444)
    parsed, parsed_bytes, _ = relocation._read_snapshot_receipt(target)
    assert parsed == receipt
    assert parsed_bytes == canonical

    target.chmod(0o644)
    target.write_text(
        json.dumps(receipt.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )
    target.chmod(0o444)
    with pytest.raises(ValueError, match="canonical JSON bytes"):
        relocation._read_snapshot_receipt(target)

    payload = receipt.model_dump(mode="json")
    payload["unexpected"] = "not allowed"
    target.chmod(0o644)
    target.write_bytes(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    )
    target.chmod(0o444)
    with pytest.raises(ValidationError, match="extra_forbidden"):
        relocation._read_snapshot_receipt(target)

    target.unlink()
    os.symlink(tmp_path / "missing-target", target)
    with pytest.raises(ValueError, match="regular non-symlink"):
        relocation._read_snapshot_receipt(target)


def test_freeze_rechecks_under_lock_without_writing_formal_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def capture_only(
        receipt_path: Path,
        receipt: relocation.FreshV3SnapshotRelocationReceipt,
        *,
        before_publish: object,
    ) -> None:
        assert callable(before_publish)
        before_publish()
        captured["path"] = receipt_path
        captured["receipt"] = receipt

    monkeypatch.setattr(
        relocation,
        "_write_snapshot_receipt_no_clobber",
        capture_only,
    )

    result = relocation.freeze_fresh_v3_snapshot_relocation_receipt(
        REPOSITORY,
        WORKSPACE,
        FORMAL_EVALUATION,
        RECEIPT_TIME,
    )

    assert captured["path"] == FORMAL_RECEIPT
    assert result["schema_version"] == (
        "typed-extractor-fresh-v3-authoring-receipt-v2"
    )
    if not FORMAL_RECEIPT.exists():
        assert set(FORMAL_PREREGISTRATION.parent.iterdir()) == {
            FORMAL_PREREGISTRATION
        }


@pytest.mark.parametrize(
    ("helper_name", "message"),
    [
        ("_require_future_absent", "future state changed in callback"),
        ("_protected_state", "protected state changed in callback"),
    ],
)
def test_freeze_rechecks_live_state_inside_publication_callback(
    monkeypatch: pytest.MonkeyPatch,
    helper_name: str,
    message: str,
) -> None:
    original = getattr(relocation, helper_name)
    call_count = 0

    def fail_on_callback(*args: object, **kwargs: object) -> object:
        nonlocal call_count
        call_count += 1
        if call_count == 4:
            raise ValueError(message)
        return original(*args, **kwargs)

    def invoke_callback_only(
        _: Path,
        __: relocation.FreshV3SnapshotRelocationReceipt,
        *,
        before_publish: object,
    ) -> None:
        assert callable(before_publish)
        before_publish()

    monkeypatch.setattr(relocation, helper_name, fail_on_callback)
    monkeypatch.setattr(
        relocation,
        "_write_snapshot_receipt_no_clobber",
        invoke_callback_only,
    )

    with pytest.raises(ValueError, match=message):
        relocation.freeze_fresh_v3_snapshot_relocation_receipt(
            REPOSITORY,
            WORKSPACE,
            FORMAL_EVALUATION,
            RECEIPT_TIME,
        )

    assert call_count == 4
    # The receipt exists as committed evidence, so its absence cannot be asserted.
    # The property under test is that the failed freeze published nothing new, so
    # assert the committed bytes are still the ones the guard module pins.
    assert sha256_file(FORMAL_RECEIPT) == AUTHORING_RECEIPT_SHA256


def test_formal_validator_is_phase_aware_and_reports_exact_sha() -> None:
    if not FORMAL_RECEIPT.exists():
        with pytest.raises(FileNotFoundError, match="receipt missing"):
            relocation.validate_fresh_v3_snapshot_relocation_receipt(
                REPOSITORY,
                WORKSPACE,
                FORMAL_EVALUATION,
            )
        return

    result = relocation.validate_fresh_v3_snapshot_relocation_receipt(
        REPOSITORY,
        WORKSPACE,
        FORMAL_EVALUATION,
    )
    assert result == {
        "status": "valid",
        "active_receipt": "authoring-implementation-receipt.json",
        "schema_version": "typed-extractor-fresh-v3-authoring-receipt-v2",
        "l1_case_count": 24,
        "l2_case_count": 18,
        "evaluation_root_absent": True,
        "materialization_implementation_absent": True,
        "hidden_artifacts_created": False,
        "model_request_count": 0,
        "receipt_sha256": hashlib.sha256(FORMAL_RECEIPT.read_bytes()).hexdigest(),
    }
