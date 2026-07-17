from __future__ import annotations

import hashlib
import os
from pathlib import Path
import tempfile
from typing import Annotated, TypeVar, cast

from pydantic import BaseModel, ConfigDict, Field

from ke_memory_demo.core.json import JsonObject, canonical_json
from ke_memory_demo.storage.layout import StateLayout, fsync_directory, validate_storage_name


ModelT = TypeVar("ModelT", bound=BaseModel)
Sha256Hex = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class CheckpointEnvelope(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    stage: str
    item_id: Annotated[str, Field(min_length=1)]
    input_sha256: Sha256Hex
    model: str
    payload_sha256: Sha256Hex
    payload: JsonObject


class CheckpointStore:
    def __init__(self, state_root: Path, run_id: str) -> None:
        self._run_id = validate_storage_name(run_id, label="run ID")
        self._layout = StateLayout(state_root)

    def save(
        self,
        stage: str,
        item_id: str,
        input_sha256: str,
        model_type: type[ModelT],
        value: ModelT,
    ) -> None:
        checkpoint_path, validated_stage = self._checkpoint_path(stage, item_id)
        validated = model_type.model_validate(value)
        payload = cast(JsonObject, validated.model_dump(mode="json"))
        envelope = CheckpointEnvelope(
            stage=validated_stage,
            item_id=item_id,
            input_sha256=input_sha256,
            model=_qualified_model_name(model_type),
            payload_sha256=hashlib.sha256(canonical_json(payload)).hexdigest(),
            payload=payload,
        )

        self._layout.ensure_directory(checkpoint_path.parent)
        _write_bytes_atomic(checkpoint_path, canonical_json(envelope))

    def load(
        self,
        stage: str,
        item_id: str,
        input_sha256: str,
        model_type: type[ModelT],
    ) -> ModelT | None:
        checkpoint_path, validated_stage = self._checkpoint_path(stage, item_id)
        try:
            data = checkpoint_path.read_bytes()
        except OSError:
            return None

        try:
            envelope = CheckpointEnvelope.model_validate_json(data)
        except (TypeError, ValueError):
            return None

        if (
            envelope.stage != validated_stage
            or envelope.item_id != item_id
            or envelope.input_sha256 != input_sha256
            or envelope.model != _qualified_model_name(model_type)
        ):
            return None
        try:
            payload_sha256 = hashlib.sha256(canonical_json(envelope.payload)).hexdigest()
        except (TypeError, ValueError):
            return None
        if payload_sha256 != envelope.payload_sha256:
            return None
        try:
            return model_type.model_validate(envelope.payload)
        except (TypeError, ValueError):
            return None

    def _checkpoint_path(self, stage: str, item_id: str) -> tuple[Path, str]:
        validated_stage = validate_storage_name(stage, label="stage")
        if not item_id:
            raise ValueError("checkpoint item ID must be nonempty")
        filename = f"{hashlib.sha256(item_id.encode('utf-8')).hexdigest()}.json"
        path = self._layout.root / "checkpoints" / self._run_id / validated_stage / filename
        self._layout.assert_safe(path)
        return path, validated_stage


def _qualified_model_name(model_type: type[BaseModel]) -> str:
    return f"{model_type.__module__}.{model_type.__qualname__}"


def _write_bytes_atomic(path: Path, payload: bytes) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary_path = Path(temporary_name)
    try:
        try:
            _write_all(descriptor, payload)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(temporary_path, path)
        fsync_directory(path.parent)
    except BaseException:
        try:
            temporary_path.unlink()
        except OSError:
            pass
        raise


def _write_all(descriptor: int, payload: bytes) -> None:
    view = memoryview(payload)
    written = 0
    while written < len(view):
        count = os.write(descriptor, view[written:])
        if count <= 0:
            raise OSError("unable to complete checkpoint write")
        written += count
