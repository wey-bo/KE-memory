from __future__ import annotations

from collections.abc import Callable, Generator, Iterable, Iterator, Mapping
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import shutil
import stat
import threading
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

from .layout import (
    StateLayout,
    StorageError,
    UnsafeStoragePathError,
    fsync_directory,
    validate_storage_name,
)


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
_replace = os.replace
_ACTIVE_WRITERS: set[tuple[Path, str, str]] = set()
_ACTIVE_WRITERS_LOCK = threading.Lock()


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
        stage_path = (
            self.layout.canonical_stage(run_id, stage)
            if canonical
            else self.layout.staging_stage(run_id, stage)
        )
        location = "canonical" if canonical else "staging"
        try:
            self.layout.require_directory(stage_path)
        except UnsafeStoragePathError as error:
            if not stage_path.exists():
                raise ArtifactValidationError(
                    f"{location} stage does not exist: {run_id}/{stage}"
                ) from error
            raise

        manifest = self._read_manifest(stage_path)
        if manifest.run_id != run_id or manifest.stage != stage:
            raise ArtifactValidationError(
                f"manifest identity does not match {location} stage {run_id}/{stage}"
            )

        expected_entries = {"manifest.json", *(artifact.path for artifact in manifest.artifacts)}
        actual_entries: set[str] = set()
        for entry in stage_path.iterdir():
            self.layout.assert_safe(entry)
            metadata = entry.lstat()
            if stat.S_ISLNK(metadata.st_mode):
                raise UnsafeStoragePathError(f"managed artifact is a symlink: {entry}")
            if not stat.S_ISREG(metadata.st_mode):
                raise ArtifactValidationError(f"unexpected non-file in stage: {entry.name}")
            actual_entries.add(entry.name)
        if actual_entries != expected_entries:
            raise ArtifactValidationError(
                f"manifest files disagree with stage contents: expected {sorted(expected_entries)}, "
                f"found {sorted(actual_entries)}"
            )

        for digest in manifest.artifacts:
            model = self._registered_model(digest.name)
            expected_model = _qualified_model_name(model)
            if digest.model != expected_model:
                raise ArtifactValidationError(
                    f"artifact {digest.name!r} model is {digest.model!r}, expected {expected_model!r}"
                )
            artifact_path = self.layout.artifact(stage_path, digest.name)
            self._validate_artifact(artifact_path, digest, model)
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
        manifest = self.validate_stage(run_id, stage, canonical=canonical)
        digest = next(
            (artifact for artifact in manifest.artifacts if artifact.name == name),
            None,
        )
        if digest is None:
            raise ArtifactValidationError(f"artifact {name!r} is not present in the stage manifest")
        stage_path = (
            self.layout.canonical_stage(run_id, stage)
            if canonical
            else self.layout.staging_stage(run_id, stage)
        )
        data = self.layout.artifact(stage_path, name).read_bytes()
        values = tuple(
            model.model_validate_json(line) for line in _record_lines(data, artifact_name=name)
        )
        return iter(values)

    def promote_stage(self, run_id: str, stage: str) -> StageManifest:
        with self._writer_guard(run_id, stage):
            return self._promote_unlocked(run_id, stage)

    @contextmanager
    def stage_writer(self, run_id: str, stage: str) -> Generator[_StageWriter, None, None]:
        with self._writer_guard(run_id, stage):
            stage_path = self.layout.staging_stage(run_id, stage)
            if stage_path.exists():
                self.layout.assert_safe(stage_path)
                raise WriterConflictError(
                    f"staging data already exists for {run_id}/{stage}; remove or promote it first"
                )
            self.layout.ensure_directory(stage_path)
            empty_manifest = StageManifest(run_id=run_id, stage=stage, artifacts=())
            _write_bytes_atomic(
                stage_path / "manifest.json",
                canonical_json(empty_manifest),
                layout=self.layout,
            )
            writer = _StageWriter(
                lambda name, records: self._write_jsonl_unlocked(
                    run_id,
                    stage,
                    name,
                    records,
                )
            )
            try:
                yield writer
                self._promote_unlocked(run_id, stage)
            except BaseException:
                self._remove_staging_stage(stage_path)
                raise
            finally:
                writer.close()

    def _write_jsonl_unlocked(
        self,
        run_id: str,
        stage: str,
        name: str,
        records: Iterable[object],
    ) -> ArtifactDigest:
        model = self._registered_model(name)
        stage_path = self.layout.staging_stage(run_id, stage)
        if stage_path.exists():
            self.layout.require_directory(stage_path)
            entries = tuple(stage_path.iterdir())
            if entries:
                if not (stage_path / "manifest.json").exists():
                    raise ArtifactValidationError(
                        f"staging stage {run_id}/{stage} is incomplete: manifest.json is missing"
                    )
                previous = self.validate_stage(run_id, stage)
            else:
                previous = StageManifest(run_id=run_id, stage=stage, artifacts=())
        else:
            self.layout.ensure_directory(stage_path)
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
        artifact_path = self.layout.artifact(stage_path, name)
        _write_bytes_atomic(artifact_path, payload, layout=self.layout)

        by_name = {artifact.name: artifact for artifact in previous.artifacts}
        by_name[name] = digest
        manifest = StageManifest(
            run_id=run_id,
            stage=stage,
            artifacts=tuple(by_name[key] for key in sorted(by_name)),
        )
        _write_bytes_atomic(
            stage_path / "manifest.json",
            canonical_json(manifest),
            layout=self.layout,
        )
        return digest

    def _promote_unlocked(self, run_id: str, stage: str) -> StageManifest:
        manifest = self.validate_stage(run_id, stage)
        staging = self.layout.staging_stage(run_id, stage)
        canonical = self.layout.canonical_stage(run_id, stage)
        self.layout.ensure_directory(canonical.parent)
        backup = canonical.parent / f".{stage}.backup-{uuid4().hex}"
        had_canonical = canonical.exists()
        if had_canonical:
            self.layout.require_directory(canonical)

        old_moved = False
        new_moved = False
        try:
            if had_canonical:
                _replace(canonical, backup)
                old_moved = True
                fsync_directory(canonical.parent)
            _replace(staging, canonical)
            new_moved = True
            fsync_directory(staging.parent)
            fsync_directory(canonical.parent)
        except BaseException as error:
            try:
                if new_moved and canonical.exists():
                    _replace(canonical, staging)
                    fsync_directory(staging.parent)
                    fsync_directory(canonical.parent)
                if old_moved and backup.exists():
                    _replace(backup, canonical)
                    fsync_directory(canonical.parent)
            except BaseException as rollback_error:
                raise ArtifactValidationError(
                    f"promotion failed and rollback failed for {run_id}/{stage}: {rollback_error}"
                ) from error
            raise

        if backup.exists():
            shutil.rmtree(backup)
            fsync_directory(canonical.parent)
        self._prune_empty_staging_parent(staging.parent)
        return manifest

    def _read_manifest(self, stage_path: Path) -> StageManifest:
        path = stage_path / "manifest.json"
        self.layout.assert_safe(path)
        try:
            metadata = path.lstat()
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
                raise UnsafeStoragePathError(f"stage manifest is not a regular file: {path}")
            return StageManifest.model_validate_json(path.read_bytes())
        except FileNotFoundError as error:
            raise ArtifactValidationError(f"stage manifest does not exist: {path}") from error
        except ValidationError as error:
            raise ArtifactValidationError(f"stage manifest is invalid: {error}") from error

    def _registered_model(self, name: str) -> type[BaseModel]:
        validate_storage_name(name, label="artifact name")
        try:
            return self.registry[name]
        except KeyError as error:
            raise ModelRegistryError(f"unknown artifact name: {name!r}") from error

    def _validate_artifact(
        self,
        path: Path,
        digest: ArtifactDigest,
        model: type[BaseModel],
    ) -> None:
        self.layout.assert_safe(path)
        try:
            metadata = path.lstat()
        except FileNotFoundError as error:
            raise ArtifactValidationError(f"artifact is missing: {path}") from error
        if stat.S_ISLNK(metadata.st_mode):
            raise UnsafeStoragePathError(f"managed artifact is a symlink: {path}")
        if not stat.S_ISREG(metadata.st_mode):
            raise ArtifactValidationError(f"artifact is not a regular file: {path}")
        data = path.read_bytes()
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

    @contextmanager
    def _writer_guard(self, run_id: str, stage: str) -> Generator[None, None, None]:
        validate_storage_name(run_id, label="run ID")
        validate_storage_name(stage, label="stage")
        key = (self.root, run_id, stage)
        with _ACTIVE_WRITERS_LOCK:
            if key in _ACTIVE_WRITERS:
                raise WriterConflictError(f"writer already active for {run_id}/{stage}")
            _ACTIVE_WRITERS.add(key)
        try:
            yield
        finally:
            with _ACTIVE_WRITERS_LOCK:
                _ACTIVE_WRITERS.remove(key)

    def _remove_staging_stage(self, stage_path: Path) -> None:
        if not stage_path.exists():
            return
        self.layout.require_directory(stage_path)
        shutil.rmtree(stage_path)
        fsync_directory(stage_path.parent)
        self._prune_empty_staging_parent(stage_path.parent)

    def _prune_empty_staging_parent(self, run_staging: Path) -> None:
        try:
            run_staging.rmdir()
        except OSError:
            return
        fsync_directory(run_staging.parent)


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


def _record_lines(data: bytes, *, artifact_name: str) -> tuple[bytes, ...]:
    if not data:
        return ()
    if not data.endswith(b"\n"):
        raise ArtifactValidationError(f"artifact {artifact_name!r} lacks a final newline")
    lines = tuple(data[:-1].split(b"\n"))
    if any(not line for line in lines):
        raise ArtifactValidationError(f"artifact {artifact_name!r} contains a blank record line")
    return lines


def _write_bytes_atomic(path: Path, payload: bytes, *, layout: StateLayout) -> None:
    layout.assert_safe(path)
    layout.ensure_directory(path.parent)
    if path.exists() or path.is_symlink():
        layout.assert_safe(path)
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            raise UnsafeStoragePathError(f"managed artifact is a symlink: {path}")
        if not stat.S_ISREG(metadata.st_mode):
            raise UnsafeStoragePathError(f"managed artifact is not a regular file: {path}")
    temporary = path.parent / f".{path.name}.tmp-{uuid4().hex}"
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        _write_all(descriptor, payload)
        os.fsync(descriptor)
    except BaseException:
        os.close(descriptor)
        temporary.unlink(missing_ok=True)
        raise
    else:
        os.close(descriptor)
    try:
        _replace(temporary, path)
        fsync_directory(path.parent)
    except BaseException:
        temporary.unlink(missing_ok=True)
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
