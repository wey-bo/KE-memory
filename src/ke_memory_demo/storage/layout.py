from __future__ import annotations

import os
from pathlib import Path
import re
import stat


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
