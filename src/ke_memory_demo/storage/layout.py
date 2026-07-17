from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
import os
from pathlib import Path
import re
import stat
from uuid import uuid4


_PORTABLE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*", flags=re.ASCII)


class StorageError(Exception):
    """Base class for deterministic storage failures."""


class InvalidStorageNameError(StorageError, ValueError):
    """A run, stage, or artifact name is not portable and path-safe."""


class UnsafeStoragePathError(StorageError):
    """A managed path contains a symlink or escapes the state root."""


def validate_storage_name(value: str, *, label: str) -> str:
    if _PORTABLE_NAME.fullmatch(value) is None:
        raise InvalidStorageNameError(
            f"{label} must use nonempty ASCII letters, digits, '.', '_', or '-', "
            "and must not start with '.'"
        )
    return value


class StateLayout:
    """Construct and verify paths in the canonical state-root layout."""

    def __init__(self, root: Path) -> None:
        root.mkdir(parents=True, exist_ok=True)
        self.root = root.resolve(strict=True)
        if not self.root.is_dir():
            raise UnsafeStoragePathError(f"state root is not a directory: {self.root}")

    @property
    def staging_root(self) -> Path:
        return self.root / ".staging"

    @property
    def runs_root(self) -> Path:
        return self.root / "runs"

    @property
    def cache_root(self) -> Path:
        return self.root / "cache"

    def staging_stage(self, run_id: str, stage: str) -> Path:
        return self.staging_root / self._names(run_id, stage)[0] / stage

    def canonical_stage(self, run_id: str, stage: str) -> Path:
        return self.runs_root / self._names(run_id, stage)[0] / stage

    def artifact(self, stage_directory: Path, name: str) -> Path:
        validate_storage_name(name, label="artifact name")
        path = stage_directory / f"{name}.jsonl"
        self.assert_safe(path)
        return path

    def cache_database(self, run_id: str) -> Path:
        validate_storage_name(run_id, label="run ID")
        path = self.cache_root / run_id / "memory.sqlite3"
        self.assert_safe(path)
        return path

    def ensure_directory(self, path: Path) -> None:
        self.assert_safe(path)
        relative = path.relative_to(self.root)
        current = self.root
        for part in relative.parts:
            current /= part
            try:
                metadata = current.lstat()
            except FileNotFoundError:
                try:
                    current.mkdir()
                except FileExistsError:
                    metadata = current.lstat()
                else:
                    fsync_directory(current.parent)
                    continue
            if stat.S_ISLNK(metadata.st_mode):
                raise UnsafeStoragePathError(f"managed directory is a symlink: {current}")
            if not stat.S_ISDIR(metadata.st_mode):
                raise UnsafeStoragePathError(f"managed directory is not a directory: {current}")

    @contextmanager
    def pin_directory(self, path: Path, *, create: bool) -> Generator[int, None, None]:
        self.assert_safe(path)
        try:
            relative = path.relative_to(self.root)
        except ValueError as error:
            raise UnsafeStoragePathError(f"managed path escapes state root: {path}") from error

        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(self.root, flags)
        try:
            for component in relative.parts:
                try:
                    child = os.open(component, flags, dir_fd=descriptor)
                except FileNotFoundError:
                    if not create:
                        raise
                    try:
                        os.mkdir(component, mode=0o700, dir_fd=descriptor)
                        os.fsync(descriptor)
                    except FileExistsError:
                        pass
                    try:
                        child = os.open(component, flags, dir_fd=descriptor)
                    except OSError as error:
                        raise UnsafeStoragePathError(
                            f"managed directory is unsafe or a symlink: {component}"
                        ) from error
                except OSError as error:
                    raise UnsafeStoragePathError(
                        f"managed directory is unsafe or a symlink: {component}"
                    ) from error
                os.close(descriptor)
                descriptor = child
            yield descriptor
        finally:
            os.close(descriptor)

    def write_bytes_atomic(self, path: Path, payload: bytes) -> None:
        self.assert_safe(path)
        with self.pin_directory(path.parent, create=True) as directory_fd:
            try:
                existing = os.stat(path.name, dir_fd=directory_fd, follow_symlinks=False)
            except FileNotFoundError:
                existing = None
            if existing is not None and (
                stat.S_ISLNK(existing.st_mode) or not stat.S_ISREG(existing.st_mode)
            ):
                raise UnsafeStoragePathError(f"managed export is not a regular file: {path.name}")

            temporary = f".{path.name}.tmp-{uuid4().hex}"
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(temporary, flags, 0o600, dir_fd=directory_fd)
            try:
                _write_all(descriptor, payload)
                os.fsync(descriptor)
            except BaseException:
                os.close(descriptor)
                _unlink_at_best_effort(directory_fd, temporary)
                raise
            else:
                os.close(descriptor)
            try:
                os.replace(
                    temporary,
                    path.name,
                    src_dir_fd=directory_fd,
                    dst_dir_fd=directory_fd,
                )
                os.fsync(directory_fd)
            except BaseException:
                _unlink_at_best_effort(directory_fd, temporary)
                raise

    def assert_safe(self, path: Path) -> None:
        try:
            relative = path.relative_to(self.root)
        except ValueError as error:
            raise UnsafeStoragePathError(f"managed path escapes state root: {path}") from error
        if ".." in relative.parts:
            raise UnsafeStoragePathError(f"managed path contains a '..' component: {path}")

        normalized = Path(os.path.normpath(path))
        try:
            normalized.relative_to(self.root)
        except ValueError as error:
            raise UnsafeStoragePathError(f"managed path escapes state root: {path}") from error

        current = self.root
        for part in relative.parts:
            current /= part
            try:
                metadata = current.lstat()
            except FileNotFoundError:
                continue
            if stat.S_ISLNK(metadata.st_mode):
                raise UnsafeStoragePathError(f"managed path contains a symlink: {current}")

    def require_directory(self, path: Path) -> None:
        self.assert_safe(path)
        try:
            metadata = path.lstat()
        except FileNotFoundError as error:
            raise UnsafeStoragePathError(f"managed directory does not exist: {path}") from error
        if stat.S_ISLNK(metadata.st_mode):
            raise UnsafeStoragePathError(f"managed directory is a symlink: {path}")
        if not stat.S_ISDIR(metadata.st_mode):
            raise UnsafeStoragePathError(f"managed path is not a directory: {path}")

    @staticmethod
    def _names(run_id: str, stage: str) -> tuple[str, str]:
        return (
            validate_storage_name(run_id, label="run ID"),
            validate_storage_name(stage, label="stage"),
        )


def fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_all(descriptor: int, payload: bytes) -> None:
    view = memoryview(payload)
    written = 0
    while written < len(view):
        try:
            count = os.write(descriptor, view[written:])
        except InterruptedError:
            continue
        if count <= 0:
            raise OSError("write returned no progress")
        written += count


def _unlink_at_best_effort(directory_fd: int, name: str) -> None:
    try:
        os.unlink(name, dir_fd=directory_fd)
    except FileNotFoundError:
        pass
