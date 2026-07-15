from __future__ import annotations

from collections.abc import Callable, Iterator
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import ClassVar

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from ke_memory_demo.core.json import canonical_json
from ke_memory_demo.domain import Exchange, Message, MessageRole
from ke_memory_demo.storage import (
    ArtifactDigest,
    ArtifactStore,
    ArtifactValidationError,
    InvalidStorageNameError,
    ModelRegistryError,
    StageManifest,
    UnsafeStoragePathError,
    WriterConflictError,
)


def _exchange(content: str = "tea", *, exchange_id: str = "exchange-1") -> Exchange:
    return Exchange(
        id=exchange_id,
        session_id="session-1",
        user=Message(
            id=f"{exchange_id}-user", role=MessageRole.USER, content=content, source_order=0
        ),
        assistant=Message(
            id=f"{exchange_id}-assistant",
            role=MessageRole.ASSISTANT,
            content="noted",
            source_order=1,
        ),
        global_ordinal=0,
    )


def _manifest_path(root: Path, *, canonical: bool = False) -> Path:
    base = root / ("runs" if canonical else ".staging")
    return base / "run-1" / "ingested" / "manifest.json"


def test_jsonl_bytes_and_manifest_are_deterministic(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    record = _exchange("茶")

    digest = store.write_jsonl("run-1", "ingested", "exchanges", [record])

    expected = canonical_json(record) + b"\n"
    artifact = tmp_path / ".staging/run-1/ingested/exchanges.jsonl"
    assert artifact.read_bytes() == expected
    assert digest == ArtifactDigest(
        name="exchanges",
        path="exchanges.jsonl",
        model="ke_memory_demo.domain.conversation.Exchange",
        record_count=1,
        sha256=hashlib.sha256(expected).hexdigest(),
    )
    manifest = StageManifest.model_validate_json(_manifest_path(tmp_path).read_bytes())
    assert manifest == StageManifest(run_id="run-1", stage="ingested", artifacts=(digest,))
    manifest_json = json.loads(_manifest_path(tmp_path).read_bytes())
    assert list(manifest_json) == ["artifacts", "run_id", "stage"]
    assert not {"created_at", "git_sha", "sqlite_path", "root"} & manifest_json.keys()

    first_artifact = artifact.read_bytes()
    first_manifest = _manifest_path(tmp_path).read_bytes()
    store.write_jsonl("run-1", "ingested", "exchanges", [record])
    assert artifact.read_bytes() == first_artifact
    assert _manifest_path(tmp_path).read_bytes() == first_manifest


def test_empty_artifact_is_an_empty_file_with_empty_sha(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)

    digest = store.write_jsonl("run-1", "ingested", "messages", [])

    assert (tmp_path / ".staging/run-1/ingested/messages.jsonl").read_bytes() == b""
    assert digest.record_count == 0
    assert digest.sha256 == hashlib.sha256(b"").hexdigest()


def test_short_writes_are_completed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from ke_memory_demo.storage import artifacts

    real_write = os.write
    calls = 0

    def short_write(fd: int, data: bytes | bytearray | memoryview) -> int:
        nonlocal calls
        calls += 1
        view = memoryview(data)
        return real_write(fd, view[: max(1, len(view) // 3)])

    monkeypatch.setattr(artifacts, "_write_once", short_write)
    record = _exchange("a payload long enough to require several writes")

    ArtifactStore(tmp_path).write_jsonl("run-1", "ingested", "exchanges", [record])

    assert calls > 1
    assert (tmp_path / ".staging/run-1/ingested/exchanges.jsonl").read_bytes() == canonical_json(
        record
    ) + b"\n"


class _CustomRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str


def test_registry_can_be_extended_but_unknown_and_wrong_models_fail(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path, registry={"custom_records": _CustomRecord})

    digest = store.write_jsonl("run-1", "custom", "custom_records", [{"id": "custom-1"}])

    assert digest.model == f"{__name__}._CustomRecord"
    with pytest.raises(ModelRegistryError, match="unknown artifact"):
        store.write_jsonl("run-1", "custom", "not_registered", [{"id": "x"}])
    with pytest.raises(ArtifactValidationError, match="exchanges"):
        store.write_jsonl("run-1", "custom", "exchanges", [{"id": "not-an-exchange"}])
    store.promote_stage("run-1", "custom")
    with pytest.raises(ModelRegistryError, match="requested model"):
        list(store.read_jsonl("run-1", "custom", "custom_records", Exchange))
    assert list(store.read_jsonl("run-1", "custom", "custom_records", _CustomRecord)) == [
        _CustomRecord(id="custom-1")
    ]


@pytest.mark.parametrize(
    ("run_id", "stage", "name"),
    [
        ("", "stage", "exchanges"),
        (".hidden", "stage", "exchanges"),
        ("../escape", "stage", "exchanges"),
        ("/absolute", "stage", "exchanges"),
        ("run", "two words", "exchanges"),
        ("run", "stäge", "exchanges"),
        ("run", "stage", ".hidden"),
        ("run", "stage", "bad/name"),
        ("run..escape", "stage", "exchanges"),
        ("run", "stage..escape", "exchanges"),
        ("run", "stage", "exchange..escape"),
    ],
)
def test_names_must_be_portable(run_id: str, stage: str, name: str, tmp_path: Path) -> None:
    with pytest.raises(InvalidStorageNameError):
        ArtifactStore(tmp_path).write_jsonl(run_id, stage, name, [])


def test_stage_symlink_outside_root_is_rejected(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    staging_run = tmp_path / ".staging/run-1"
    staging_run.mkdir(parents=True)
    (staging_run / "ingested").symlink_to(outside, target_is_directory=True)

    with pytest.raises(UnsafeStoragePathError, match="symlink"):
        ArtifactStore(tmp_path).write_jsonl("run-1", "ingested", "exchanges", [_exchange()])
    assert list(outside.iterdir()) == []


def test_canonical_artifact_symlink_outside_root_is_rejected(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    store.write_jsonl("run-1", "ingested", "exchanges", [_exchange()])
    store.promote_stage("run-1", "ingested")
    outside = tmp_path.parent / f"{tmp_path.name}-outside.jsonl"
    outside.write_bytes(b"outside")
    artifact = store.canonical_path("run-1", "ingested", "exchanges")
    artifact.unlink()
    artifact.symlink_to(outside)

    with pytest.raises(UnsafeStoragePathError, match="symlink"):
        list(store.read_jsonl("run-1", "ingested", "exchanges", Exchange))


def test_artifact_symlink_swap_during_descriptor_open_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ke_memory_demo.storage import artifacts

    store = ArtifactStore(tmp_path)
    store.write_jsonl("run-1", "ingested", "exchanges", [_exchange()])
    artifact = tmp_path / ".staging/run-1/ingested/exchanges.jsonl"
    outside = tmp_path / "outside.jsonl"
    outside.write_bytes(artifact.read_bytes())
    swapped = False

    def swap_before_open(
        directory_fd: int,
        name: str,
        flags: int,
        mode: int = 0o600,
    ) -> int:
        nonlocal swapped
        if name == "exchanges.jsonl" and not swapped:
            artifact.unlink()
            artifact.symlink_to(outside)
            swapped = True
        return os.open(
            name,
            flags | getattr(os, "O_NOFOLLOW", 0),
            mode,
            dir_fd=directory_fd,
        )

    monkeypatch.setattr(artifacts, "_open_regular_at", swap_before_open, raising=False)

    with pytest.raises(UnsafeStoragePathError, match="symlink|regular file"):
        store.validate_stage("run-1", "ingested")

    assert swapped


class _ReadSwapRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    tamper_path: ClassVar[Path | None] = None

    @model_validator(mode="after")
    def _tamper_after_snapshot_validation(self) -> _ReadSwapRecord:
        path = self.tamper_path
        if path is not None:
            type(self).tamper_path = None
            path.write_bytes(canonical_json({"id": "changed"}) + b"\n")
        return self


def test_read_yields_the_exact_snapshot_that_was_validated(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path, registry={"read_swap": _ReadSwapRecord})
    store.write_jsonl("run-1", "stage", "read_swap", [{"id": "original"}])
    store.promote_stage("run-1", "stage")
    artifact = store.canonical_path("run-1", "stage", "read_swap")
    _ReadSwapRecord.tamper_path = artifact

    try:
        records = tuple(store.read_jsonl("run-1", "stage", "read_swap", _ReadSwapRecord))
    finally:
        _ReadSwapRecord.tamper_path = None

    assert records == (_ReadSwapRecord(id="original"),)
    assert artifact.read_bytes() == canonical_json({"id": "changed"}) + b"\n"


def _remove_final_newline(data: bytes) -> bytes:
    return data.rstrip(b"\n")


def _add_blank_line(data: bytes) -> bytes:
    return data.replace(b"\n", b"\n\n", 1)


def _change_payload(data: bytes) -> bytes:
    return data.replace(b'"noted"', b'"changed"')


def _invalid_model(_data: bytes) -> bytes:
    return b'{"not":"an exchange"}\n'


@pytest.mark.parametrize(
    "tamper",
    [
        pytest.param(_remove_final_newline, id="missing-final-newline"),
        pytest.param(_add_blank_line, id="blank-line"),
        pytest.param(_change_payload, id="digest"),
        pytest.param(_invalid_model, id="model"),
    ],
)
def test_validation_rejects_tampered_artifact_bytes(
    tmp_path: Path,
    tamper: Callable[[bytes], bytes],
) -> None:
    store = ArtifactStore(tmp_path)
    store.write_jsonl("run-1", "ingested", "exchanges", [_exchange()])
    artifact = tmp_path / ".staging/run-1/ingested/exchanges.jsonl"
    artifact.write_bytes(tamper(artifact.read_bytes()))

    with pytest.raises(ArtifactValidationError):
        store.validate_stage("run-1", "ingested")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("record_count", 2),
        ("path", "other.jsonl"),
        ("model", "builtins.dict"),
        ("name", "messages"),
        ("sha256", "0" * 64),
    ],
)
def test_validation_rejects_manifest_disagreement(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    store = ArtifactStore(tmp_path)
    store.write_jsonl("run-1", "ingested", "exchanges", [_exchange()])
    path = _manifest_path(tmp_path)
    payload = json.loads(path.read_bytes())
    payload["artifacts"][0][field] = value
    path.write_bytes(canonical_json(payload))

    with pytest.raises(ArtifactValidationError):
        store.validate_stage("run-1", "ingested")


def test_canonical_validation_is_explicit_and_read_returns_typed_records(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    records = [
        _exchange("first", exchange_id="exchange-1"),
        _exchange("second", exchange_id="exchange-2"),
    ]
    store.write_jsonl("run-1", "ingested", "exchanges", records)
    promoted = store.promote_stage("run-1", "ingested")

    assert store.validate_stage("run-1", "ingested", canonical=True) == promoted
    assert list(store.read_jsonl("run-1", "ingested", "exchanges", Exchange)) == records
    with pytest.raises(ArtifactValidationError, match="staging stage"):
        store.validate_stage("run-1", "ingested")


def test_write_never_changes_an_already_promoted_stage(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    store.write_jsonl("run-1", "ingested", "exchanges", [_exchange("original")])
    store.promote_stage("run-1", "ingested")
    canonical = store.canonical_path("run-1", "ingested", "exchanges")
    original = canonical.read_bytes()

    store.write_jsonl("run-1", "ingested", "exchanges", [_exchange("replacement")])

    assert canonical.read_bytes() == original


def test_stage_writer_promotes_only_after_clean_exit(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)

    with store.stage_writer("run-1", "ingested") as writer:
        digest = writer.write("exchanges", [_exchange()])
        assert digest.name == "exchanges"
        assert not store.canonical_path("run-1", "ingested", "exchanges").exists()

    assert list(store.read_jsonl("run-1", "ingested", "exchanges", Exchange)) == [_exchange()]
    assert not (tmp_path / ".staging/run-1/ingested").exists()


def test_clean_empty_stage_writer_promotes_a_manifest_only_stage(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)

    with store.stage_writer("run-1", "empty-stage"):
        pass

    manifest = store.validate_stage("run-1", "empty-stage", canonical=True)
    assert manifest.artifacts == ()


def test_failed_stage_writer_preserves_canonical_and_cleans_staging(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    store.write_jsonl("run-1", "ingested", "exchanges", [_exchange("original")])
    store.promote_stage("run-1", "ingested")
    canonical = store.canonical_path("run-1", "ingested", "exchanges")
    original = canonical.read_bytes()

    with pytest.raises(RuntimeError, match="stop"):
        with store.stage_writer("run-1", "ingested") as writer:
            writer.write("exchanges", [_exchange("changed")])
            raise RuntimeError("stop")

    assert canonical.read_bytes() == original
    assert not (tmp_path / ".staging/run-1/ingested").exists()


def test_writer_conflict_is_rejected(tmp_path: Path) -> None:
    first = ArtifactStore(tmp_path)
    second = ArtifactStore(tmp_path)

    with first.stage_writer("run-1", "ingested"):
        with pytest.raises(WriterConflictError, match="already active"):
            second.write_jsonl("run-1", "ingested", "exchanges", [_exchange()])


def _wait_for_subprocess_marker(
    marker: Path,
    process: subprocess.Popen[str],
) -> None:
    deadline = time.monotonic() + 5
    while not marker.exists():
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            raise AssertionError(
                f"writer subprocess exited before acquiring ownership: {stdout}\n{stderr}"
            )
        if time.monotonic() >= deadline:
            process.kill()
            stdout, stderr = process.communicate()
            raise AssertionError(f"writer subprocess timed out: {stdout}\n{stderr}")
        time.sleep(0.01)


def test_writer_ownership_is_enforced_across_processes(tmp_path: Path) -> None:
    ready = tmp_path / "ready"
    release = tmp_path / "release"
    script = """
from pathlib import Path
import sys
import time
from ke_memory_demo.storage import ArtifactStore

root, ready, release = (Path(value) for value in sys.argv[1:])
with ArtifactStore(root).stage_writer("run-1", "ingested"):
    ready.write_text("ready")
    while not release.exists():
        time.sleep(0.01)
"""
    process = subprocess.Popen(
        [sys.executable, "-c", script, str(tmp_path), str(ready), str(release)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    _wait_for_subprocess_marker(ready, process)
    try:
        with pytest.raises(WriterConflictError, match="already active"):
            ArtifactStore(tmp_path).write_jsonl("run-1", "ingested", "exchanges", [_exchange()])
    finally:
        release.write_text("release")
        stdout, stderr = process.communicate(timeout=5)

    assert process.returncode == 0, (stdout, stderr)


def test_stage_writer_setup_failure_cleans_stage_and_releases_ownership(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ke_memory_demo.storage import artifacts

    def fail_initial_manifest(*_args: object, **_kwargs: object) -> None:
        raise OSError("injected initial manifest failure")

    monkeypatch.setattr(
        artifacts,
        "_write_bytes_atomic",
        fail_initial_manifest,
        raising=False,
    )
    monkeypatch.setattr(
        artifacts,
        "_write_bytes_atomic_at",
        fail_initial_manifest,
        raising=False,
    )
    store = ArtifactStore(tmp_path)

    with pytest.raises(OSError, match="initial manifest"):
        with store.stage_writer("run-1", "ingested"):
            pass

    assert not (tmp_path / ".staging/run-1/ingested").exists()
    monkeypatch.undo()
    with ArtifactStore(tmp_path).stage_writer("run-1", "ingested"):
        pass


def test_failed_replacement_rolls_back_the_prior_canonical_stage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ke_memory_demo.storage import artifacts

    store = ArtifactStore(tmp_path)
    store.write_jsonl("run-1", "ingested", "exchanges", [_exchange("original")])
    store.promote_stage("run-1", "ingested")
    canonical = store.canonical_path("run-1", "ingested", "exchanges")
    original = canonical.read_bytes()
    store.write_jsonl("run-1", "ingested", "exchanges", [_exchange("changed")])
    staging_stage = tmp_path / ".staging/run-1/ingested"
    canonical_stage = tmp_path / "runs/run-1/ingested"
    failed = False

    def fail_new_stage(
        source: str,
        destination: str,
        *,
        source_dir_fd: int,
        destination_dir_fd: int,
    ) -> None:
        nonlocal failed
        if source == "ingested" and destination == "ingested" and not failed:
            failed = True
            raise OSError("injected promotion failure")
        os.replace(
            source,
            destination,
            src_dir_fd=source_dir_fd,
            dst_dir_fd=destination_dir_fd,
        )

    monkeypatch.setattr(artifacts, "_replace_at", fail_new_stage)

    with pytest.raises(OSError, match="injected"):
        store.promote_stage("run-1", "ingested")

    assert canonical.read_bytes() == original
    assert staging_stage.exists()
    assert not list(canonical_stage.parent.glob(".ingested.backup-*"))


def _prepare_stage_replacement(tmp_path: Path) -> tuple[ArtifactStore, Path, bytes]:
    store = ArtifactStore(tmp_path)
    store.write_jsonl("run-1", "ingested", "exchanges", [_exchange("original")])
    store.promote_stage("run-1", "ingested")
    canonical = store.canonical_path("run-1", "ingested", "exchanges")
    original = canonical.read_bytes()
    store.write_jsonl("run-1", "ingested", "exchanges", [_exchange("changed")])
    return store, canonical, original


def test_old_to_backup_failure_keeps_the_prior_canonical_stage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ke_memory_demo.storage import artifacts

    store, canonical, original = _prepare_stage_replacement(tmp_path)

    def fail_old_to_backup(
        source: str,
        destination: str,
        *,
        source_dir_fd: int,
        destination_dir_fd: int,
    ) -> None:
        del source, source_dir_fd, destination_dir_fd
        if destination.startswith(".ingested.backup-"):
            raise OSError("injected old-to-backup failure")
        raise AssertionError(f"unexpected promotion destination: {destination}")

    monkeypatch.setattr(artifacts, "_replace_at", fail_old_to_backup, raising=False)

    with pytest.raises(OSError, match="old-to-backup"):
        store.promote_stage("run-1", "ingested")

    assert canonical.read_bytes() == original


def test_commit_fsync_failure_restores_the_prior_canonical_stage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ke_memory_demo.storage import artifacts

    store, canonical, original = _prepare_stage_replacement(tmp_path)

    def fail_commit_fsync(directory_fd: int, *, step: str) -> None:
        if step == "commit-canonical-parent":
            raise OSError("injected commit fsync failure")
        os.fsync(directory_fd)

    monkeypatch.setattr(artifacts, "_promotion_fsync", fail_commit_fsync, raising=False)

    with pytest.raises(OSError, match="commit fsync"):
        store.promote_stage("run-1", "ingested")

    assert canonical.read_bytes() == original


def test_restore_rename_failure_uses_the_durable_recovery_copy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ke_memory_demo.storage import artifacts

    store, canonical, original = _prepare_stage_replacement(tmp_path)
    failed_new_stage = False
    failed_primary_restore = False

    def inject_replace_failures(
        source: str,
        destination: str,
        *,
        source_dir_fd: int,
        destination_dir_fd: int,
    ) -> None:
        nonlocal failed_new_stage, failed_primary_restore
        if source == "ingested" and destination == "ingested" and not failed_new_stage:
            failed_new_stage = True
            raise OSError("injected staging-to-canonical failure")
        if (
            source.startswith(".ingested.backup-")
            and destination == "ingested"
            and not failed_primary_restore
        ):
            failed_primary_restore = True
            raise OSError("injected primary restore failure")
        os.replace(
            source,
            destination,
            src_dir_fd=source_dir_fd,
            dst_dir_fd=destination_dir_fd,
        )

    monkeypatch.setattr(artifacts, "_replace_at", inject_replace_failures, raising=False)

    with pytest.raises(OSError, match="staging-to-canonical"):
        store.promote_stage("run-1", "ingested")

    assert failed_primary_restore
    assert canonical.read_bytes() == original


def test_backup_cleanup_failure_is_non_failing_after_durable_promotion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ke_memory_demo.storage import artifacts

    store, canonical, original = _prepare_stage_replacement(tmp_path)
    attempted: list[str] = []

    def fail_backup_cleanup(_parent_fd: int, name: str) -> None:
        if ".backup-" in name:
            attempted.append(name)
            raise RuntimeError("injected backup cleanup failure")

    monkeypatch.setattr(artifacts, "_cleanup_tree_at", fail_backup_cleanup, raising=False)

    store.promote_stage("run-1", "ingested")

    assert attempted
    assert canonical.read_bytes() != original


def test_digest_and_manifest_are_frozen_and_forbid_extra_fields() -> None:
    digest = ArtifactDigest(
        name="messages",
        path="messages.jsonl",
        model="ke_memory_demo.domain.conversation.Message",
        record_count=0,
        sha256="0" * 64,
    )

    with pytest.raises(ValidationError, match="frozen"):
        digest.record_count = 1
    with pytest.raises(ValidationError, match="extra_forbidden"):
        StageManifest.model_validate(
            {"run_id": "run", "stage": "stage", "artifacts": [], "created_at": "now"}
        )


def test_read_jsonl_is_lazy_but_validates_before_yielding(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    store.write_jsonl("run-1", "ingested", "exchanges", [_exchange()])
    store.promote_stage("run-1", "ingested")

    records = store.read_jsonl("run-1", "ingested", "exchanges", Exchange)

    assert isinstance(records, Iterator)
    assert next(records) == _exchange()
    with pytest.raises(StopIteration):
        next(records)
