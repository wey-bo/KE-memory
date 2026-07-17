from collections.abc import Mapping
from pathlib import Path
import os
import tempfile
from typing import AbstractSet


RUNTIME_ENV_NAMES: AbstractSet[str] = frozenset(
    {
        "KE_MEMORY_WORK_API_KEY",
        "KE_MEMORY_JUDGE_API_KEY",
        "KE_MEMORY_ES_URL",
        "KE_MEMORY_ES_INDEX",
        "KE_MEMORY_ES_API_KEY",
    }
)


def write_env_local(path: Path, work_key: str, judge_key: str) -> None:
    if (
        not work_key
        or not judge_key
        or "\r" in work_key
        or "\n" in work_key
        or "\r" in judge_key
        or "\n" in judge_key
    ):
        raise ValueError("Both API keys must be non-empty single-line values")

    payload = (f"KE_MEMORY_WORK_API_KEY={work_key}\nKE_MEMORY_JUDGE_API_KEY={judge_key}\n").encode()
    _atomic_private_write(path, payload)


def write_runtime_env_local(path: Path, values: Mapping[str, str]) -> None:
    if set(values) != RUNTIME_ENV_NAMES:
        raise ValueError("runtime environment values must match the exact allowlist")
    if any(not value or "\r" in value or "\n" in value for value in values.values()):
        raise ValueError("runtime environment values must be non-empty single-line strings")
    payload = "".join(f"{name}={values[name]}\n" for name in sorted(values)).encode()
    _atomic_private_write(path, payload)


def _atomic_private_write(path: Path, payload: bytes) -> None:
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary_path = Path(temporary_name)
    try:
        try:
            os.fchmod(fd, 0o600)
            _write_all(fd, payload)
            os.fsync(fd)
        finally:
            os.close(fd)

        os.replace(temporary_path, path)
        _fsync_directory(path.parent)
    except BaseException:
        try:
            temporary_path.unlink()
        except OSError:
            pass
        raise


def _write_all(fd: int, payload: bytes) -> None:
    remaining = payload
    while remaining:
        written = os.write(fd, remaining)
        if written <= 0:
            raise OSError("Unable to complete secret file write")
        remaining = remaining[written:]


def _fsync_directory(path: Path) -> None:
    directory_fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
