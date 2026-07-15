from pathlib import Path
import stat

import pytest

from ke_memory_demo.infra import secrets
from ke_memory_demo.infra.secrets import write_env_local


def test_write_env_local_is_private_and_complete(tmp_path: Path):
    target = tmp_path / ".env.local"
    write_env_local(target, "work-test-value", "judge-test-value")
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert target.read_text().splitlines() == [
        "KE_MEMORY_WORK_API_KEY=work-test-value",
        "KE_MEMORY_JUDGE_API_KEY=judge-test-value",
    ]


@pytest.mark.parametrize(
    ("work_key", "judge_key"),
    [
        ("", "judge-test-value"),
        ("work-test-value", ""),
        ("work-test-value\nsecond-line", "judge-test-value"),
        ("work-test-value", "judge-test-value\nsecond-line"),
        ("work-test-value\rsecond-line", "judge-test-value"),
        ("work-test-value", "judge-test-value\rsecond-line"),
    ],
)
def test_write_env_local_rejects_invalid_keys_before_touching_destination(
    tmp_path: Path,
    work_key: str,
    judge_key: str,
):
    target = tmp_path / ".env.local"
    original = b"existing-local-settings\n"
    target.write_bytes(original)

    with pytest.raises(ValueError, match="non-empty single-line"):
        write_env_local(target, work_key, judge_key)

    assert target.read_bytes() == original


def test_write_env_local_repairs_permissions_on_an_existing_file(tmp_path: Path):
    target = tmp_path / ".env.local"
    target.write_text("old-value")
    target.chmod(0o644)

    write_env_local(target, "work-test-value", "judge-test-value")

    assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_write_env_local_completes_partial_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    target = tmp_path / ".env.local"
    real_write = secrets.os.write
    write_calls = 0

    def partial_write(fd: int, payload: bytes) -> int:
        nonlocal write_calls
        write_calls += 1
        chunk_size = max(1, len(payload) // 2)
        return real_write(fd, payload[:chunk_size])

    monkeypatch.setattr(secrets.os, "write", partial_write)

    write_env_local(target, "work-test-value", "judge-test-value")

    assert write_calls > 1
    assert target.read_text().splitlines() == [
        "KE_MEMORY_WORK_API_KEY=work-test-value",
        "KE_MEMORY_JUDGE_API_KEY=judge-test-value",
    ]


def test_write_env_local_stages_payload_with_private_permissions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    target = tmp_path / ".env.local"
    target.write_text("old-value")
    target.chmod(0o644)
    real_write = secrets.os.write
    modes_during_write: list[int] = []

    def record_mode(fd: int, payload: bytes) -> int:
        modes_during_write.append(stat.S_IMODE(secrets.os.fstat(fd).st_mode))
        return real_write(fd, payload)

    monkeypatch.setattr(secrets.os, "write", record_mode)

    write_env_local(target, "work-test-value", "judge-test-value")

    assert modes_during_write
    assert set(modes_during_write) == {0o600}


def test_write_env_local_atomically_replaces_existing_file(tmp_path: Path):
    target = tmp_path / ".env.local"
    original = b"old-value\n"
    target.write_bytes(original)

    with target.open("rb") as previous_file:
        write_env_local(target, "work-test-value", "judge-test-value")
        assert previous_file.read() == original


def test_write_env_local_replaces_symlink_without_following_it(tmp_path: Path):
    target = tmp_path / ".env.local"
    symlink_target = tmp_path / "existing-secrets"
    original = "do-not-overwrite\n"
    symlink_target.write_text(original)
    target.symlink_to(symlink_target)

    write_env_local(target, "work-test-value", "judge-test-value")

    assert not target.is_symlink()
    assert symlink_target.read_text() == original
    assert target.read_text().splitlines() == [
        "KE_MEMORY_WORK_API_KEY=work-test-value",
        "KE_MEMORY_JUDGE_API_KEY=judge-test-value",
    ]


def test_write_env_local_fsyncs_payload_and_destination_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    real_fsync = secrets.os.fsync
    synced_modes: list[int] = []

    def record_fsync(fd: int) -> None:
        synced_modes.append(secrets.os.fstat(fd).st_mode)
        real_fsync(fd)

    monkeypatch.setattr(secrets.os, "fsync", record_fsync)

    write_env_local(tmp_path / ".env.local", "work-test-value", "judge-test-value")

    assert any(stat.S_ISREG(mode) for mode in synced_modes)
    assert any(stat.S_ISDIR(mode) for mode in synced_modes)


def test_write_env_local_preserves_destination_and_cleans_temp_on_replace_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    target = tmp_path / ".env.local"
    original = b"old-value\n"
    target.write_bytes(original)

    staged_paths: list[Path] = []

    def fail_replace(source: Path, destination: Path) -> None:
        staged_paths.append(source)
        assert source.parent == target.parent
        assert stat.S_IMODE(source.stat().st_mode) == 0o600
        assert destination == target
        raise OSError("simulated replace failure")

    monkeypatch.setattr(secrets.os, "replace", fail_replace)

    with pytest.raises(OSError, match="simulated replace failure"):
        write_env_local(target, "work-test-value", "judge-test-value")

    assert target.read_bytes() == original
    assert len(staged_paths) == 1
    assert list(tmp_path.iterdir()) == [target]
