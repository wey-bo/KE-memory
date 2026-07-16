from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath
import stat
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ke_memory_demo.core.json import JsonValue, canonical_json

from .index import EmbeddingInvariantError


Sha256Hex = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
ModelFileKind = Literal["config", "tokenizer", "weight"]

_TOKENIZER_NAMES = frozenset(
    {
        "added_tokens.json",
        "merges.txt",
        "sentencepiece.bpe.model",
        "special_tokens_map.json",
        "spiece.model",
        "tokenizer.model",
        "vocab.json",
        "vocab.txt",
    }
)
_WEIGHT_SUFFIXES = (
    ".bin",
    ".bin.index.json",
    ".ckpt",
    ".pt",
    ".pth",
    ".safetensors",
    ".safetensors.index.json",
)


class ModelFileFingerprint(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str
    kind: ModelFileKind
    sha256: Sha256Hex

    @model_validator(mode="after")
    def _validate_relative_path(self) -> ModelFileFingerprint:
        path = PurePosixPath(self.path)
        if (
            path.is_absolute()
            or not path.parts
            or ".." in path.parts
            or self.path != path.as_posix()
        ):
            raise ValueError("fingerprinted model file path must be a normalized relative path")
        return self


class ModelFingerprint(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    files: tuple[ModelFileFingerprint, ...]
    sha256: Sha256Hex

    @model_validator(mode="after")
    def _validate_files_and_digest(self) -> ModelFingerprint:
        paths = tuple(item.path for item in self.files)
        if paths != tuple(sorted(paths)) or len(paths) != len(set(paths)):
            raise ValueError("fingerprinted model files must have unique sorted paths")
        kinds = {item.kind for item in self.files}
        missing = sorted({"config", "tokenizer", "weight"}.difference(kinds))
        if missing:
            raise ValueError(f"model fingerprint is missing required {missing[0]} files")
        expected = _combined_digest(self.files)
        if self.sha256 != expected:
            raise ValueError("model fingerprint digest does not match its file entries")
        return self


def fingerprint_model_directory(root: Path) -> ModelFingerprint:
    try:
        model_root = root.expanduser().resolve(strict=True)
    except OSError as error:
        raise EmbeddingInvariantError(
            f"local embedding model directory is unavailable: {root}"
        ) from error
    if not model_root.is_dir():
        raise EmbeddingInvariantError(
            f"local embedding model path is not a directory: {model_root}"
        )

    entries: list[ModelFileFingerprint] = []
    for relative_path, physical_path in _walk_model_files(model_root):
        kind = _model_file_kind(relative_path)
        if kind is None:
            continue
        entries.append(
            ModelFileFingerprint(
                path=relative_path,
                kind=kind,
                sha256=_sha256_file(physical_path),
            )
        )
    entries.sort(key=lambda item: item.path)
    try:
        return ModelFingerprint(files=tuple(entries), sha256=_combined_digest(entries))
    except ValueError as error:
        raise EmbeddingInvariantError(str(error)) from error


def _walk_model_files(root: Path) -> tuple[tuple[str, Path], ...]:
    found: list[tuple[str, Path]] = []

    def visit(
        directory: Path, logical_parts: tuple[str, ...], ancestors: frozenset[tuple[int, int]]
    ) -> None:
        try:
            directory_target = directory.resolve(strict=True)
            metadata = directory_target.stat()
        except OSError as error:
            raise EmbeddingInvariantError(
                f"unable to inspect model directory {directory}"
            ) from error
        if not directory_target.is_relative_to(root):
            raise EmbeddingInvariantError(
                f"model symlink escapes configured model root: {directory}"
            )
        identity = (metadata.st_dev, metadata.st_ino)
        if identity in ancestors:
            raise EmbeddingInvariantError(f"model directory symlink cycle detected: {directory}")
        next_ancestors = ancestors | {identity}

        try:
            children = sorted(os.scandir(directory), key=lambda entry: entry.name)
        except OSError as error:
            raise EmbeddingInvariantError(f"unable to list model directory {directory}") from error
        for child in children:
            child_path = Path(child.path)
            child_parts = (*logical_parts, child.name)
            is_symlink = child.is_symlink()
            try:
                target = child_path.resolve(strict=True)
            except OSError as error:
                label = "model symlink" if is_symlink else "model path"
                raise EmbeddingInvariantError(
                    f"{label} is broken or unreadable: {child_path}"
                ) from error
            if not target.is_relative_to(root):
                label = "model symlink" if is_symlink else "model path"
                raise EmbeddingInvariantError(
                    f"{label} escapes configured model root: {child_path}"
                )
            try:
                target_metadata = target.stat()
            except OSError as error:
                raise EmbeddingInvariantError(
                    f"unable to inspect model path {child_path}"
                ) from error
            if stat.S_ISDIR(target_metadata.st_mode):
                visit(child_path, child_parts, next_ancestors)
            elif stat.S_ISREG(target_metadata.st_mode):
                found.append((PurePosixPath(*child_parts).as_posix(), target))
            else:
                raise EmbeddingInvariantError(
                    f"model path is not a regular file or directory: {child_path}"
                )

    visit(root, (), frozenset())
    return tuple(found)


def _model_file_kind(relative_path: str) -> ModelFileKind | None:
    name = PurePosixPath(relative_path).name.lower()
    if name.endswith(_WEIGHT_SUFFIXES):
        return "weight"
    if "tokenizer" in name or name in _TOKENIZER_NAMES:
        return "tokenizer"
    if "config" in name or name == "modules.json":
        return "config"
    return None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            while block := stream.read(1024 * 1024):
                digest.update(block)
    except OSError as error:
        raise EmbeddingInvariantError(f"unable to hash model file {path}") from error
    return digest.hexdigest()


def _combined_digest(entries: tuple[ModelFileFingerprint, ...] | list[ModelFileFingerprint]) -> str:
    payload: JsonValue = [{"path": entry.path, "sha256": entry.sha256} for entry in entries]
    return hashlib.sha256(canonical_json(payload)).hexdigest()
