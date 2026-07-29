"""Dense provider boundary with query/passage separation and thread-safe text caching."""
from __future__ import annotations
import hashlib
import math
import threading
from collections.abc import Sequence
from pathlib import Path
from time import perf_counter
from typing import Any, Protocol


def _process_rss_mib() -> float | None:
    try:
        import psutil
    except ImportError:
        return None
    return float(psutil.Process().memory_info().rss / (1024 * 1024))

class DenseEncoder(Protocol):
    model_metadata: dict[str, Any]
    def encode(self, texts: Sequence[str]) -> Sequence[Sequence[float]]: ...

class DiagnosticEncoder:
    """Deterministic diagnostic-only encoder. It is not a dense experimental arm."""
    model_metadata = {"provider": "diagnostic", "model_id": "diagnostic-hash", "revision": "none", "dimensions": 8, "diagnostic_only": True}
    model_id, revision, dimensions = "diagnostic-hash", "none", 8
    def encode(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        return [[byte / 255 for byte in hashlib.sha256(text.encode("utf-8")).digest()[:self.dimensions]] for text in texts]

class CachingEncoder:
    """Thread-safe cache shared across arm/track/scale calls for identical text."""
    def __init__(self, inner: DenseEncoder) -> None:
        self.inner, self.model_metadata, self._cache, self._lock = inner, dict(inner.model_metadata), {}, threading.RLock()
        self.cache_hits = self.cache_misses = 0
    def _cached(self, texts: Sequence[str], method: str) -> list[list[float]]:
        with self._lock:
            missing = [text for text in texts if (method, text) not in self._cache]
            self.cache_hits += len(texts) - len(missing)
            self.cache_misses += len(missing)
            if missing:
                function = getattr(self.inner, method, self.inner.encode)
                vectors = function(missing)
                self._cache.update({(method, text): list(vector) for text, vector in zip(missing, vectors, strict=True)})
            self.model_metadata.update(cache_hits=self.cache_hits, cache_misses=self.cache_misses, encoded_text_count=self.cache_misses)
            return [self._cache[(method, text)] for text in texts]
    def encode(self, texts: Sequence[str]) -> Sequence[Sequence[float]]: return self._cached(texts, "encode")
    def encode_query(self, texts: Sequence[str]) -> Sequence[Sequence[float]]: return self._cached(texts, "encode_query")
    def encode_documents(self, texts: Sequence[str]) -> Sequence[Sequence[float]]: return self._cached(texts, "encode_documents")

class FastEmbedEncoder:
    UPSTREAM_MODEL_ID = "BAAI/bge-small-en-v1.5"
    UPSTREAM_REVISION = "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a"
    BACKEND_ARTIFACT_ID = "qdrant/bge-small-en-v1.5-onnx-q"
    BACKEND_ARTIFACT_REVISION = "52398278842ec682c6f32300af41344b1c0b0bb2"
    DIMENSIONS = 384
    MODEL_ID, REVISION = UPSTREAM_MODEL_ID, UPSTREAM_REVISION

    @classmethod
    def default_metadata(cls) -> dict[str, Any]:
        return {
            "provider": "fastembed",
            "model_id": cls.BACKEND_ARTIFACT_ID,
            "revision": cls.BACKEND_ARTIFACT_REVISION,
            "upstream_model_id": cls.UPSTREAM_MODEL_ID,
            "upstream_revision": cls.UPSTREAM_REVISION,
            "dimensions": cls.DIMENSIONS,
        }

    def __init__(self, model_name: str = MODEL_ID, revision: str = REVISION, cache_dir: str | None = None) -> None:
        try: from fastembed import TextEmbedding
        except ImportError as error: raise RuntimeError("FastEmbed is required for the real dense arm") from error
        cache_path = Path(cache_dir) if cache_dir else None
        cache_state = "unspecified"
        if cache_path is not None:
            cache_state = "warm" if cache_path.exists() and any(cache_path.iterdir()) else "cold"
        rss_before = _process_rss_mib()
        load_started_at = perf_counter()
        self._model, self._lock = TextEmbedding(model_name=model_name, cache_dir=cache_dir), threading.RLock()
        probe = self.encode_documents(["metadata probe"])[0]
        load_latency_ms = max(0.0, (perf_counter() - load_started_at) * 1000.0)
        rss_after = _process_rss_mib()
        self.model_metadata = self.default_metadata()
        self.model_metadata.update(
            dimensions=len(probe),
            upstream_model_id=model_name,
            upstream_revision=revision,
            model_load_latency_ms=load_latency_ms,
            cache_state_before_load=cache_state,
        )
        if rss_before is not None and rss_after is not None:
            self.model_metadata.update(
                rss_before_load_mib=rss_before,
                rss_after_load_mib=rss_after,
                rss_load_delta_mib=rss_after - rss_before,
            )
        if model_name != self.UPSTREAM_MODEL_ID:
            self.model_metadata.update(model_id="unverified-fastembed-backend", revision="unverified")
        self.model_id = str(self.model_metadata["model_id"])
        self.revision = str(self.model_metadata["revision"])
        self.dimensions = len(probe)
    def _embed(self, texts: Sequence[str], prefix: str, provider_method: str) -> list[list[float]]:
        with self._lock:
            method = getattr(self._model, provider_method, None)
            values = method(list(texts)) if method else self._model.embed([f"{prefix}{text}" for text in texts])
            return [list(vector) for vector in values]
    def encode(self, texts: Sequence[str]) -> Sequence[Sequence[float]]: return self.encode_documents(texts)
    def encode_query(self, texts: Sequence[str]) -> Sequence[Sequence[float]]: return self._embed(texts, "query: ", "query_embed")
    def encode_documents(self, texts: Sequence[str]) -> Sequence[Sequence[float]]: return self._embed(texts, "passage: ", "passage_embed")

def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    denom = math.sqrt(sum(x*x for x in a))*math.sqrt(sum(x*x for x in b))
    return float(0.0 if denom == 0 else sum(x*y for x,y in zip(a,b,strict=True))/denom)
def _encode_query(encoder: DenseEncoder, text: str): return getattr(encoder, "encode_query", encoder.encode)([text])[0]
def _encode_docs(encoder: DenseEncoder, texts: Sequence[str]): return getattr(encoder, "encode_documents", encoder.encode)(texts)
def rank_dense(query_text: str, records: Sequence[dict[str, Any]], encoder: DenseEncoder) -> list[dict[str, Any]]:
    if not records: return []
    query, docs = _encode_query(encoder, query_text), _encode_docs(encoder, [str(r.get("surface_text", "")) for r in records])
    return sorted(({"record_id": r["record_id"], "score": _cosine(query,v)} for r,v in zip(records,docs,strict=True)), key=lambda item:(-item["score"],item["record_id"]))
