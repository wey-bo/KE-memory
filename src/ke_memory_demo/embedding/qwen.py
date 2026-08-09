from __future__ import annotations

from collections.abc import Callable, Sequence
import hashlib
import os
from pathlib import Path
from typing import Any, Protocol, cast

import numpy as np

from ke_memory_demo.core.json import JsonValue, canonical_json
from ke_memory_demo.settings import AppSettings, EmbeddingSettings

from .chunking import Tokenizer
from .fingerprint import ModelFingerprint, fingerprint_model_directory
from .index import EmbeddingInvariantError


QWEN_MODEL = "Qwen/Qwen3-Embedding-0.6B"
QWEN_REVISION = "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3"
QWEN_DIMENSION = 1024
QWEN_CHUNK_TOKENS = 1024
QWEN_OVERLAP_TOKENS = 128
QUERY_INSTRUCTION = (
    "Instruct: Given an agent-memory question, retrieve conversation evidence needed to answer it."
)
QUERY_TEMPLATE = f"{QUERY_INSTRUCTION}\nQuery: {{question}}"
ENCODING_BATCH_SIZE = 32


class _SentenceTransformerModel(Protocol):
    @property
    def tokenizer(self) -> Tokenizer: ...

    def get_sentence_embedding_dimension(self) -> int | None: ...

    def encode(self, sentences: list[str], **kwargs: object) -> object: ...


ModelFactory = Callable[..., _SentenceTransformerModel]


class QwenEmbeddingBackend:
    dimension = QWEN_DIMENSION

    def __init__(
        self,
        settings: AppSettings | EmbeddingSettings,
        local_path: Path | None = None,
        *,
        model_factory: ModelFactory | None = None,
    ) -> None:
        embedding_settings, model_path = _resolve_settings(settings, local_path)
        _validate_fixed_settings(embedding_settings)
        self.settings = embedding_settings
        self.local_path = model_path
        before_load = fingerprint_model_directory(model_path)
        factory = model_factory or _sentence_transformer_factory()
        try:
            model = factory(
                str(model_path),
                local_files_only=True,
                trust_remote_code=True,
            )
        except Exception as error:
            raise EmbeddingInvariantError(
                f"unable to load local Qwen3 embedding model: {error}"
            ) from error
        if model.get_sentence_embedding_dimension() != QWEN_DIMENSION:
            raise EmbeddingInvariantError("Qwen3 embedding dimension must be 1024")
        tokenizer = getattr(model, "tokenizer", None)
        if (
            tokenizer is None
            or not callable(getattr(tokenizer, "encode", None))
            or not callable(getattr(tokenizer, "decode", None))
        ):
            raise EmbeddingInvariantError("local Qwen3 model does not expose a usable tokenizer")
        after_load = fingerprint_model_directory(model_path)
        if after_load != before_load:
            raise EmbeddingInvariantError("local Qwen3 model fingerprint changed while loading")
        self._model = model
        self.tokenizer = cast(Tokenizer, tokenizer)
        self.fingerprint: ModelFingerprint = before_load
        self.configuration_hash = _configuration_hash(embedding_settings)

    def verify_model_fingerprint(self) -> None:
        current = fingerprint_model_directory(self.local_path)
        if current != self.fingerprint:
            raise EmbeddingInvariantError("local Qwen3 model fingerprint changed")

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        if isinstance(texts, str):
            raise EmbeddingInvariantError("document texts must be a sequence of strings")
        values = tuple(texts)
        if any(not text for text in values):
            raise EmbeddingInvariantError("document text must be a non-empty string")
        return self._encode(values)

    def embed_query(self, question: str) -> np.ndarray:
        if not question:
            raise EmbeddingInvariantError("query text must be a non-empty string")
        return self._encode((QUERY_TEMPLATE.format(question=question),))[0]

    def encode_documents(self, texts: Sequence[str]) -> np.ndarray:
        return self.embed_documents(texts)

    def encode_query(self, question: str) -> np.ndarray:
        return self.embed_query(question)

    def _encode(self, texts: Sequence[str]) -> np.ndarray:
        self.verify_model_fingerprint()
        if not texts:
            return np.empty((0, QWEN_DIMENSION), dtype=np.float32)
        try:
            raw = self._model.encode(
                list(texts),
                batch_size=ENCODING_BATCH_SIZE,
                convert_to_numpy=True,
                normalize_embeddings=False,
                precision="float32",
                show_progress_bar=False,
            )
        except Exception as error:
            raise EmbeddingInvariantError(f"local Qwen3 embedding failed: {error}") from error
        return _normalized_matrix(raw, expected_rows=len(texts), dimension=QWEN_DIMENSION)


def _resolve_settings(
    settings: AppSettings | EmbeddingSettings,
    local_path: Path | None,
) -> tuple[EmbeddingSettings, Path]:
    if isinstance(settings, AppSettings):
        embedding_settings = settings.embedding
        configured_path = settings.require_embedding_path() if local_path is None else local_path
    else:
        embedding_settings = settings
        configured_path = local_path
        if configured_path is None:
            raw_path = os.environ.get(settings.local_path_env, "").strip()
            if not raw_path:
                raise EmbeddingInvariantError(
                    f"local embedding path is required or must be set in {settings.local_path_env}"
                )
            configured_path = Path(raw_path).expanduser()
            if not configured_path.is_absolute():
                raise EmbeddingInvariantError(
                    "a relative local embedding path requires application settings"
                )
    try:
        model_path = configured_path.expanduser().resolve(strict=True)
    except OSError as error:
        raise EmbeddingInvariantError(
            f"local embedding model directory is unavailable: {configured_path}"
        ) from error
    if not model_path.is_dir():
        raise EmbeddingInvariantError(
            f"local embedding model path is not a directory: {model_path}"
        )
    return embedding_settings, model_path


def _validate_fixed_settings(settings: EmbeddingSettings) -> None:
    if settings.model != QWEN_MODEL:
        raise EmbeddingInvariantError(f"embedding model must be {QWEN_MODEL}")
    if settings.revision != QWEN_REVISION:
        raise EmbeddingInvariantError(f"embedding revision must be {QWEN_REVISION}")
    if settings.dimension != QWEN_DIMENSION:
        raise EmbeddingInvariantError("Qwen3 embedding dimension must be 1024")
    if settings.chunk_tokens != QWEN_CHUNK_TOKENS or settings.overlap_tokens != QWEN_OVERLAP_TOKENS:
        raise EmbeddingInvariantError(
            "Qwen3 embedding chunks must use 1024 tokens with 128-token overlap"
        )
    if not settings.local_files_only:
        raise EmbeddingInvariantError("Qwen3 embedding must use local_files_only=True")


def _sentence_transformer_factory() -> ModelFactory:
    try:
        # Optional dependency: installed via the `embedding` group, absent from the
        # default environment and from the wheel's requirements. Unresolved here is
        # the expected state, hence the ignores -- the ImportError below is the
        # contract, and the cast already discards the type either way.
        from sentence_transformers import (  # pyright: ignore[reportMissingImports]
            SentenceTransformer,  # pyright: ignore[reportUnknownVariableType]
        )
    except ImportError as error:
        raise EmbeddingInvariantError(
            "sentence-transformers is required for local embedding; install the "
            "embedding dependency group"
        ) from error
    return cast(Any, SentenceTransformer)


def _normalized_matrix(raw: object, *, expected_rows: int, dimension: int) -> np.ndarray:
    try:
        matrix = np.asarray(raw, dtype=np.float32)
    except (TypeError, ValueError, OverflowError) as error:
        raise EmbeddingInvariantError("model vectors must contain numeric values") from error
    if matrix.ndim == 1 and expected_rows == 1:
        matrix = matrix.reshape(1, -1)
    if matrix.ndim != 2 or matrix.shape != (expected_rows, dimension):
        raise EmbeddingInvariantError(
            f"model vectors must have dimension {dimension} for every input"
        )
    if not np.isfinite(matrix).all():
        raise EmbeddingInvariantError("model vectors contain NaN or infinity")
    norms = np.linalg.norm(matrix.astype(np.float64), axis=1)
    if not np.isfinite(norms).all() or np.any(norms == 0.0):
        raise EmbeddingInvariantError("model vectors must have a finite non-zero norm")
    normalized = np.asarray(matrix / norms[:, None], dtype=np.float32)
    if not np.isfinite(normalized).all():
        raise EmbeddingInvariantError("model vector normalization produced NaN or infinity")
    return normalized


def _configuration_hash(settings: EmbeddingSettings) -> str:
    payload: JsonValue = {
        "model": settings.model,
        "revision": settings.revision,
        "dimension": settings.dimension,
        "chunk_tokens": settings.chunk_tokens,
        "overlap_tokens": settings.overlap_tokens,
        "local_files_only": True,
        "query_template": QUERY_TEMPLATE,
        "document_instruction": None,
        "encoding": {
            "batch_size": ENCODING_BATCH_SIZE,
            "convert_to_numpy": True,
            "normalize_embeddings": False,
            "precision": "float32",
            "show_progress_bar": False,
            "output_normalization": "l2",
        },
    }
    return hashlib.sha256(canonical_json(payload)).hexdigest()
