from __future__ import annotations

from collections.abc import Callable, Generator, Iterable, Iterator, Mapping
from contextlib import contextmanager
import errno
import fcntl
import hashlib
import os
from pathlib import Path
import stat
from types import MappingProxyType
from typing import Annotated, TypeVar
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from ke_memory_demo.core.json import canonical_json
from ke_memory_demo.domain import (
    AggregateNode,
    Conversation,
    CoverageEntry,
    Evidence,
    Exchange,
    KnowledgeEquation,
    Message,
    Session,
    ToolEvent,
)

from .layout import StateLayout, StorageError, UnsafeStoragePathError, validate_storage_name


ModelT = TypeVar("ModelT", bound=BaseModel)
NonNegativeInt = Annotated[int, Field(ge=0)]
Sha256Hex = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class ArtifactValidationError(StorageError, ValueError):
    """Canonical framing, manifest agreement, or model validation failed."""


class ModelRegistryError(StorageError, ValueError):
    """An artifact is unknown or its requested model does not match the registry."""


class WriterConflictError(StorageError):
    """Another writer owns the same run and stage."""


class ArtifactDigest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    path: str
    model: str
    record_count: NonNegativeInt
    sha256: Sha256Hex

    @model_validator(mode="after")
    def _validate_identity(self) -> ArtifactDigest:
        validate_storage_name(self.name, label="artifact name")
        if self.path != f"{self.name}.jsonl":
            raise ValueError("artifact path must be relative to its stage and match its name")
        if not self.model or "." not in self.model:
            raise ValueError("artifact model must be a fully-qualified name")
        return self

    @property
    def model_name(self) -> str:
        return self.model


class StageManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    stage: str
    artifacts: tuple[ArtifactDigest, ...]

    @model_validator(mode="after")
    def _validate_identity_and_order(self) -> StageManifest:
        validate_storage_name(self.run_id, label="run ID")
        validate_storage_name(self.stage, label="stage")
        names = tuple(artifact.name for artifact in self.artifacts)
        if names != tuple(sorted(names)):
            raise ValueError("manifest artifacts must be sorted by name")
        if len(names) != len(set(names)):
            raise ValueError("manifest artifact names must be unique")
        return self


DEFAULT_MODEL_REGISTRY: Mapping[str, type[BaseModel]] = MappingProxyType(
    {
        "messages": Message,
        "tool_events": ToolEvent,
        "exchanges": Exchange,
        "sessions": Session,
        "conversations": Conversation,
        "knowledge_equations": KnowledgeEquation,
        "coverage": CoverageEntry,
        "aggregates": AggregateNode,
        "evidence": Evidence,
    }
)


_write_once = os.write


class ArtifactStore:
    def __init__(
        self,
        root: Path,
        *,
        registry: Mapping[str, type[BaseModel]] | None = None,
    ) -> None:
        self.layout = StateLayout(root)
        merged = dict(DEFAULT_MODEL_REGISTRY)
        for name, model in (registry or {}).items():
            validate_storage_name(name, label="artifact name")
            if name in merged and merged[name] is not model:
                raise ModelRegistryError(f"cannot replace registered model for artifact {name!r}")
            merged[name] = model
        self.registry: Mapping[str, type[BaseModel]] = MappingProxyType(merged)

    @property
    def root(self) -> Path:
        return self.layout.root

    def canonical_path(self, run_id: str, stage: str, name: str) -> Path:
        stage_path = self.layout.canonical_stage(run_id, stage)
        return self.layout.artifact(stage_path, name)

    def cache_path(self, run_id: str) -> Path:
        return self.layout.cache_database(run_id)

    def write_jsonl(
        self,
        run_id: str,
        stage: str,
        name: str,
        records: Iterable[object],
    ) -> ArtifactDigest:
        with self._writer_guard(run_id, stage):
            return self._write_jsonl_unlocked(run_id, stage, name, records)

    def validate_stage(
        self,
        run_id: str,
        stage: str,
        *,
        canonical: bool = False,
    ) -> StageManifest:
        manifest, _snapshots = self._validated_stage_snapshot(
            run_id,
            stage,
            canonical=canonical,
        )
        return manifest

    def read_jsonl(
        self,
        run_id: str,
        stage: str,
        name: str,
        model: type[ModelT],
        *,
        canonical: bool = True,
    ) -> Iterator[ModelT]:
        registered = self._registered_model(name)
        if registered is not model:
            raise ModelRegistryError(
                f"requested model {_qualified_model_name(model)!r} does not match registered "
                f"model {_qualified_model_name(registered)!r} for artifact {name!r}"
            )
        manifest, snapshots = self._validated_stage_snapshot(
            run_id,
            stage,
            canonical=canonical,
        )
        if not any(artifact.name == name for artifact in manifest.artifacts):
            raise ArtifactValidationError(f"artifact {name!r} is not present in the stage manifest")
        data = snapshots[name]
        values = tuple(
            model.model_validate_json(line) for line in _record_lines(data, artifact_name=name)
        )
        return iter(values)

    def promote_stage(self, run_id: str, stage: str) -> StageManifest:
        with self._writer_guard(run_id, stage):
            return self._promote_unlocked(run_id, stage)

    @contextmanager
    def stage_writer(self, run_id: str, stage: str) -> Generator[_StageWriter, None, None]:
        validate_storage_name(run_id, label="run ID")
        validate_storage_name(stage, label="stage")
        with self._writer_guard(run_id, stage):
            run_path = self.layout.staging_root / run_id
            with _pin_directory(self.layout, run_path, create=True) as run_fd:
                existing = _stat_at(run_fd, stage)
                if existing is not None:
                    if stat.S_ISLNK(existing.st_mode):
                        raise UnsafeStoragePathError(
                            f"staging stage is a symlink: {run_id}/{stage}"
                        )
                    raise WriterConflictError(
                        f"staging data already exists for {run_id}/{stage}; "
                        "remove or promote it first"
                    )

                stage_fd = -1
                created = False
                writer: _StageWriter | None = None
                try:
                    os.mkdir(stage, mode=0o700, dir_fd=run_fd)
                    created = True
                    os.fsync(run_fd)
                    stage_fd = _open_directory_checked(run_fd, stage)
                    empty_manifest = StageManifest(run_id=run_id, stage=stage, artifacts=())
                    _write_bytes_atomic_at(
                        stage_fd,
                        "manifest.json",
                        canonical_json(empty_manifest),
                    )
                    writer = _StageWriter(
                        lambda artifact_name, artifact_records: self._write_jsonl_to_fd(
                            stage_fd,
                            run_id,
                            stage,
                            artifact_name,
                            artifact_records,
                        )
                    )
                    yield writer
                    self._promote_pinned(
                        run_id,
                        stage,
                        staging_parent_fd=run_fd,
                        staging_fd=stage_fd,
                    )
                except BaseException:
                    if created:
                        _remove_owned_stage(run_fd, stage, stage_fd)
                    raise
                finally:
                    if writer is not None:
                        writer.close()
                    if stage_fd >= 0:
                        os.close(stage_fd)

    def _write_jsonl_unlocked(
        self,
        run_id: str,
        stage: str,
        name: str,
        records: Iterable[object],
    ) -> ArtifactDigest:
        stage_path = self.layout.staging_stage(run_id, stage)
        with _pin_directory(self.layout, stage_path, create=True) as stage_fd:
            return self._write_jsonl_to_fd(stage_fd, run_id, stage, name, records)

    def _write_jsonl_to_fd(
        self,
        stage_fd: int,
        run_id: str,
        stage: str,
        name: str,
        records: Iterable[object],
    ) -> ArtifactDigest:
        model = self._registered_model(name)
        entries = tuple(os.listdir(stage_fd))
        if entries:
            if "manifest.json" not in entries:
                raise ArtifactValidationError(
                    f"staging stage {run_id}/{stage} is incomplete: manifest.json is missing"
                )
            previous, _snapshots = self._validate_stage_fd(stage_fd, run_id, stage)
        else:
            previous = StageManifest(run_id=run_id, stage=stage, artifacts=())

        payload_parts: list[bytes] = []
        try:
            for record in records:
                validated = model.model_validate(record)
                payload_parts.append(canonical_json(validated) + b"\n")
        except (TypeError, ValueError, ValidationError) as error:
            raise ArtifactValidationError(
                f"record validation failed for artifact {name!r}: {error}"
            ) from error

        payload = b"".join(payload_parts)
        digest = ArtifactDigest(
            name=name,
            path=f"{name}.jsonl",
            model=_qualified_model_name(model),
            record_count=len(payload_parts),
            sha256=hashlib.sha256(payload).hexdigest(),
        )
        _write_bytes_atomic_at(stage_fd, digest.path, payload)

        by_name = {artifact.name: artifact for artifact in previous.artifacts}
        by_name[name] = digest
        manifest = StageManifest(
            run_id=run_id,
            stage=stage,
            artifacts=tuple(by_name[key] for key in sorted(by_name)),
        )
        _write_bytes_atomic_at(stage_fd, "manifest.json", canonical_json(manifest))
        return digest

    def _validated_stage_snapshot(
        self,
        run_id: str,
        stage: str,
        *,
        canonical: bool,
    ) -> tuple[StageManifest, dict[str, bytes]]:
        stage_path = (
            self.layout.canonical_stage(run_id, stage)
            if canonical
            else self.layout.staging_stage(run_id, stage)
        )
        location = "canonical" if canonical else "staging"
        try:
            with _pin_directory(self.layout, stage_path, create=False) as stage_fd:
                return self._validate_stage_fd(stage_fd, run_id, stage)
        except FileNotFoundError as error:
            raise ArtifactValidationError(
                f"{location} stage does not exist or is incomplete: {run_id}/{stage}"
            ) from error

    def _validate_stage_fd(
        self,
        stage_fd: int,
        run_id: str,
        stage: str,
    ) -> tuple[StageManifest, dict[str, bytes]]:
        manifest = _parse_manifest(_read_regular_at(stage_fd, "manifest.json"))
        if manifest.run_id != run_id or manifest.stage != stage:
            raise ArtifactValidationError(
                f"manifest identity does not match stage {run_id}/{stage}"
            )

        expected_entries = {"manifest.json", *(artifact.path for artifact in manifest.artifacts)}
        actual_entries = set(os.listdir(stage_fd))
        if actual_entries != expected_entries:
            raise ArtifactValidationError(
                f"manifest files disagree with stage contents: expected {sorted(expected_entries)}, "
                f"found {sorted(actual_entries)}"
            )

        snapshots: dict[str, bytes] = {}
        for digest in manifest.artifacts:
            model = self._registered_model(digest.name)
            expected_model = _qualified_model_name(model)
            if digest.model != expected_model:
                raise ArtifactValidationError(
                    f"artifact {digest.name!r} model is {digest.model!r}, expected {expected_model!r}"
                )
            data = _read_regular_at(stage_fd, digest.path)
            _validate_artifact_bytes(data, digest, model)
            snapshots[digest.name] = data
        return manifest, snapshots

    def _promote_unlocked(self, run_id: str, stage: str) -> StageManifest:
        staging_parent = self.layout.staging_root / run_id
        try:
            with _pin_directory(self.layout, staging_parent, create=False) as staging_parent_fd:
                staging_fd = _open_directory_checked(staging_parent_fd, stage)
                try:
                    return self._promote_pinned(
                        run_id,
                        stage,
                        staging_parent_fd=staging_parent_fd,
                        staging_fd=staging_fd,
                    )
                finally:
                    os.close(staging_fd)
        except FileNotFoundError as error:
            raise ArtifactValidationError(
                f"staging stage does not exist: {run_id}/{stage}"
            ) from error

    def _promote_pinned(
        self,
        run_id: str,
        stage: str,
        *,
        staging_parent_fd: int,
        staging_fd: int,
    ) -> StageManifest:
        manifest, _snapshots = self._validate_stage_fd(staging_fd, run_id, stage)
        canonical_parent = self.layout.runs_root / run_id
        with _pin_directory(self.layout, canonical_parent, create=True) as canonical_parent_fd:
            return _promote_directory(
                stage,
                manifest,
                staging_parent_fd=staging_parent_fd,
                staging_fd=staging_fd,
                canonical_parent_fd=canonical_parent_fd,
            )

    def _registered_model(self, name: str) -> type[BaseModel]:
        validate_storage_name(name, label="artifact name")
        try:
            return self.registry[name]
        except KeyError as error:
            raise ModelRegistryError(f"unknown artifact name: {name!r}") from error

    @contextmanager
    def _writer_guard(self, run_id: str, stage: str) -> Generator[None, None, None]:
        validate_storage_name(run_id, label="run ID")
        validate_storage_name(stage, label="stage")
        with _pin_directory(self.layout, self.layout.staging_root, create=True) as lock_fd:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error:
                if error.errno in (errno.EACCES, errno.EAGAIN):
                    raise WriterConflictError(
                        f"writer already active for {run_id}/{stage}"
                    ) from error
                raise
            try:
                yield
            finally:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)


class _StageWriter:
    def __init__(
        self,
        write_callback: Callable[[str, Iterable[object]], ArtifactDigest],
    ) -> None:
        self._write_callback = write_callback
        self._closed = False

    def write(self, name: str, records: Iterable[object]) -> ArtifactDigest:
        if self._closed:
            raise WriterConflictError("stage writer is no longer active")
        return self._write_callback(name, records)

    def close(self) -> None:
        self._closed = True


def _qualified_model_name(model: type[BaseModel]) -> str:
    return f"{model.__module__}.{model.__qualname__}"


def _parse_manifest(data: bytes) -> StageManifest:
    try:
        return StageManifest.model_validate_json(data)
    except ValidationError as error:
        raise ArtifactValidationError(f"stage manifest is invalid: {error}") from error


def _validate_artifact_bytes(
    data: bytes,
    digest: ArtifactDigest,
    model: type[BaseModel],
) -> None:
    if hashlib.sha256(data).hexdigest() != digest.sha256:
        raise ArtifactValidationError(f"artifact digest does not match manifest: {digest.name}")
    lines = _record_lines(data, artifact_name=digest.name)
    if len(lines) != digest.record_count:
        raise ArtifactValidationError(f"artifact record count does not match: {digest.name}")
    for index, line in enumerate(lines, start=1):
        try:
            record = model.model_validate_json(line)
        except ValidationError as error:
            raise ArtifactValidationError(
                f"artifact {digest.name!r} line {index} is invalid: {error}"
            ) from error
        if canonical_json(record) != line:
            raise ArtifactValidationError(
                f"artifact {digest.name!r} line {index} is not canonical JSON"
            )


def _record_lines(data: bytes, *, artifact_name: str) -> tuple[bytes, ...]:
    if not data:
        return ()
    if not data.endswith(b"\n"):
        raise ArtifactValidationError(f"artifact {artifact_name!r} lacks a final newline")
    lines = tuple(data[:-1].split(b"\n"))
    if any(not line for line in lines):
        raise ArtifactValidationError(f"artifact {artifact_name!r} contains a blank record line")
    return lines


@contextmanager
def _pin_directory(
    layout: StateLayout,
    path: Path,
    *,
    create: bool,
) -> Generator[int, None, None]:
    try:
        relative = path.relative_to(layout.root)
    except ValueError as error:
        raise UnsafeStoragePathError(f"managed path escapes state root: {path}") from error

    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(layout.root, flags)
    try:
        for component in relative.parts:
            try:
                child = _open_directory_at(descriptor, component)
            except FileNotFoundError:
                if not create:
                    raise
                try:
                    os.mkdir(component, mode=0o700, dir_fd=descriptor)
                    os.fsync(descriptor)
                except FileExistsError:
                    pass
                child = _open_directory_checked(descriptor, component)
            except OSError as error:
                raise _unsafe_component(path, component, error) from error
            os.close(descriptor)
            descriptor = child
        yield descriptor
    finally:
        os.close(descriptor)


def _open_directory_at(directory_fd: int, name: str) -> int:
    return os.open(
        name,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
        dir_fd=directory_fd,
    )


def _open_directory_checked(directory_fd: int, name: str) -> int:
    try:
        return _open_directory_at(directory_fd, name)
    except OSError as error:
        if isinstance(error, FileNotFoundError):
            raise
        raise UnsafeStoragePathError(f"managed directory is unsafe or a symlink: {name}") from error


def _open_regular_at(
    directory_fd: int,
    name: str,
    flags: int,
    mode: int = 0o600,
) -> int:
    descriptor = os.open(
        name,
        flags | getattr(os, "O_NOFOLLOW", 0),
        mode,
        dir_fd=directory_fd,
    )
    metadata = os.fstat(descriptor)
    if not stat.S_ISREG(metadata.st_mode):
        os.close(descriptor)
        raise UnsafeStoragePathError(f"managed artifact is not a regular file: {name}")
    return descriptor


def _read_regular_at(directory_fd: int, name: str) -> bytes:
    try:
        descriptor = _open_regular_at(directory_fd, name, os.O_RDONLY)
    except OSError as error:
        raise UnsafeStoragePathError(
            f"managed artifact is unsafe, missing, or a symlink: {name}"
        ) from error
    try:
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)
    finally:
        os.close(descriptor)


def _write_bytes_atomic_at(directory_fd: int, name: str, payload: bytes) -> None:
    existing = _stat_at(directory_fd, name)
    if existing is not None:
        if stat.S_ISLNK(existing.st_mode) or not stat.S_ISREG(existing.st_mode):
            raise UnsafeStoragePathError(f"managed artifact is not a regular file: {name}")

    temporary = f".{name}.tmp-{uuid4().hex}"
    descriptor = _open_regular_at(
        directory_fd,
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
    )
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
        _replace_at(
            temporary,
            name,
            source_dir_fd=directory_fd,
            destination_dir_fd=directory_fd,
        )
        os.fsync(directory_fd)
    except BaseException:
        _unlink_at_best_effort(directory_fd, temporary)
        raise


def _write_all(descriptor: int, payload: bytes) -> None:
    view = memoryview(payload)
    written = 0
    while written < len(view):
        try:
            count = _write_once(descriptor, view[written:])
        except InterruptedError:
            continue
        if count <= 0:
            raise OSError("write returned no progress")
        written += count


def _replace_at(
    source: str,
    destination: str,
    *,
    source_dir_fd: int,
    destination_dir_fd: int,
) -> None:
    os.replace(
        source,
        destination,
        src_dir_fd=source_dir_fd,
        dst_dir_fd=destination_dir_fd,
    )


def _promotion_fsync(directory_fd: int, *, step: str) -> None:
    del step
    os.fsync(directory_fd)


def _promote_directory(
    stage: str,
    manifest: StageManifest,
    *,
    staging_parent_fd: int,
    staging_fd: int,
    canonical_parent_fd: int,
) -> StageManifest:
    canonical_entry = _stat_at(canonical_parent_fd, stage)
    if canonical_entry is not None and (
        stat.S_ISLNK(canonical_entry.st_mode) or not stat.S_ISDIR(canonical_entry.st_mode)
    ):
        raise UnsafeStoragePathError(f"canonical stage is unsafe or a symlink: {stage}")

    backup_name = f".{stage}.backup-{uuid4().hex}"
    recovery_name = f".{stage}.recovery-{uuid4().hex}"
    failed_name = f".{stage}.failed-{uuid4().hex}"
    had_canonical = canonical_entry is not None
    if had_canonical:
        canonical_fd = _open_directory_checked(canonical_parent_fd, stage)
        try:
            _copy_tree_at(canonical_fd, canonical_parent_fd, recovery_name)
        finally:
            os.close(canonical_fd)

    old_moved = False
    new_moved = False
    committed = False
    try:
        if had_canonical:
            _replace_at(
                stage,
                backup_name,
                source_dir_fd=canonical_parent_fd,
                destination_dir_fd=canonical_parent_fd,
            )
            old_moved = True
            _promotion_fsync(canonical_parent_fd, step="old-to-backup-parent")

        _replace_at(
            stage,
            stage,
            source_dir_fd=staging_parent_fd,
            destination_dir_fd=canonical_parent_fd,
        )
        new_moved = True
        moved_metadata = _stat_at(canonical_parent_fd, stage)
        pinned_metadata = os.fstat(staging_fd)
        if moved_metadata is None or (
            moved_metadata.st_dev,
            moved_metadata.st_ino,
        ) != (pinned_metadata.st_dev, pinned_metadata.st_ino):
            raise UnsafeStoragePathError("promoted stage does not match the validated directory")
        _promotion_fsync(staging_parent_fd, step="commit-staging-parent")
        _promotion_fsync(canonical_parent_fd, step="commit-canonical-parent")
        committed = True
    except BaseException as error:
        try:
            _rollback_promotion(
                stage,
                backup_name=backup_name,
                recovery_name=recovery_name,
                failed_name=failed_name,
                had_canonical=had_canonical,
                old_moved=old_moved,
                new_moved=new_moved,
                staging_parent_fd=staging_parent_fd,
                canonical_parent_fd=canonical_parent_fd,
            )
        except BaseException as rollback_error:
            raise ArtifactValidationError(
                f"promotion failed and rollback failed for {manifest.run_id}/{stage}: "
                f"{rollback_error}"
            ) from error
        raise

    if committed:
        _cleanup_after_commit(canonical_parent_fd, backup_name, recovery_name, failed_name)
    return manifest


def _rollback_promotion(
    stage: str,
    *,
    backup_name: str,
    recovery_name: str,
    failed_name: str,
    had_canonical: bool,
    old_moved: bool,
    new_moved: bool,
    staging_parent_fd: int,
    canonical_parent_fd: int,
) -> None:
    if new_moved:
        try:
            _replace_at(
                stage,
                stage,
                source_dir_fd=canonical_parent_fd,
                destination_dir_fd=staging_parent_fd,
            )
        except BaseException:
            try:
                _replace_at(
                    stage,
                    failed_name,
                    source_dir_fd=canonical_parent_fd,
                    destination_dir_fd=canonical_parent_fd,
                )
            except BaseException:
                _cleanup_tree_at(canonical_parent_fd, stage)
        _promotion_fsync(staging_parent_fd, step="rollback-staging-parent")

    if had_canonical and old_moved:
        try:
            _replace_at(
                backup_name,
                stage,
                source_dir_fd=canonical_parent_fd,
                destination_dir_fd=canonical_parent_fd,
            )
        except BaseException:
            _replace_at(
                recovery_name,
                stage,
                source_dir_fd=canonical_parent_fd,
                destination_dir_fd=canonical_parent_fd,
            )
        _promotion_fsync(canonical_parent_fd, step="rollback-canonical-parent")
    elif not had_canonical:
        entry = _stat_at(canonical_parent_fd, stage)
        if entry is not None:
            _cleanup_tree_at(canonical_parent_fd, stage)
            _promotion_fsync(canonical_parent_fd, step="rollback-empty-canonical-parent")

    _cleanup_after_commit(canonical_parent_fd, backup_name, recovery_name, failed_name)


def _copy_tree_at(source_fd: int, destination_parent_fd: int, destination: str) -> None:
    os.mkdir(destination, mode=0o700, dir_fd=destination_parent_fd)
    destination_fd = -1
    try:
        destination_fd = _open_directory_checked(destination_parent_fd, destination)
        _copy_directory_contents(source_fd, destination_fd)
        os.fsync(destination_fd)
        os.fsync(destination_parent_fd)
    except BaseException:
        if destination_fd >= 0:
            os.close(destination_fd)
            destination_fd = -1
        try:
            _cleanup_tree_at(destination_parent_fd, destination)
        except Exception:
            pass
        raise
    finally:
        if destination_fd >= 0:
            os.close(destination_fd)


def _copy_directory_contents(source_fd: int, destination_fd: int) -> None:
    for name in sorted(os.listdir(source_fd)):
        metadata = os.stat(name, dir_fd=source_fd, follow_symlinks=False)
        if stat.S_ISREG(metadata.st_mode):
            source_file = _open_regular_at(source_fd, name, os.O_RDONLY)
            destination_file = _open_regular_at(
                destination_fd,
                name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                metadata.st_mode & 0o777,
            )
            try:
                while True:
                    chunk = os.read(source_file, 1024 * 1024)
                    if not chunk:
                        break
                    _write_all(destination_file, chunk)
                os.fsync(destination_file)
            finally:
                os.close(source_file)
                os.close(destination_file)
        elif stat.S_ISDIR(metadata.st_mode):
            os.mkdir(name, mode=metadata.st_mode & 0o777, dir_fd=destination_fd)
            source_child = _open_directory_checked(source_fd, name)
            destination_child = _open_directory_checked(destination_fd, name)
            try:
                _copy_directory_contents(source_child, destination_child)
                os.fsync(destination_child)
            finally:
                os.close(source_child)
                os.close(destination_child)
        else:
            raise UnsafeStoragePathError(f"canonical stage contains an unsafe entry: {name}")


def _cleanup_tree_at(parent_fd: int, name: str) -> None:
    metadata = _stat_at(parent_fd, name)
    if metadata is None:
        return
    if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        raise UnsafeStoragePathError(f"cleanup target is not a safe directory: {name}")
    directory_fd = _open_directory_checked(parent_fd, name)
    try:
        for entry in os.listdir(directory_fd):
            child = os.stat(entry, dir_fd=directory_fd, follow_symlinks=False)
            if stat.S_ISDIR(child.st_mode) and not stat.S_ISLNK(child.st_mode):
                _cleanup_tree_at(directory_fd, entry)
            else:
                os.unlink(entry, dir_fd=directory_fd)
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    os.rmdir(name, dir_fd=parent_fd)
    os.fsync(parent_fd)


def _cleanup_after_commit(parent_fd: int, *names: str) -> None:
    for name in names:
        try:
            _cleanup_tree_at(parent_fd, name)
        except Exception:
            pass


def _remove_owned_stage(parent_fd: int, name: str, stage_fd: int) -> None:
    entry = _stat_at(parent_fd, name)
    if entry is None:
        return
    if stage_fd >= 0:
        pinned = os.fstat(stage_fd)
        if (entry.st_dev, entry.st_ino) != (pinned.st_dev, pinned.st_ino):
            raise UnsafeStoragePathError("staging path changed while the writer owned it")
    _cleanup_tree_at(parent_fd, name)


def _stat_at(directory_fd: int, name: str) -> os.stat_result | None:
    try:
        return os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None


def _unlink_at_best_effort(directory_fd: int, name: str) -> None:
    try:
        os.unlink(name, dir_fd=directory_fd)
        os.fsync(directory_fd)
    except FileNotFoundError:
        pass


def _unsafe_component(path: Path, component: str, error: OSError) -> UnsafeStoragePathError:
    return UnsafeStoragePathError(
        f"managed path contains an unsafe or symlinked component {component!r}: {path}"
    )
