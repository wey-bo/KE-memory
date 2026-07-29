from __future__ import annotations

import math
import os
import re
import time
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .io import load_json, write_json_immutable
from .models import PublicSliceArtifact, ResultsArtifact


Vector = list[float]
Encoder = Callable[[list[str]], list[Vector]]


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.casefold())


def lexical_encoder(texts: list[str]) -> list[Vector]:
    vocabulary = sorted({token for text in texts for token in _tokenize(text)})
    if not vocabulary:
        return [[] for _ in texts]
    index = {token: offset for offset, token in enumerate(vocabulary)}
    vectors: list[Vector] = []
    for text in texts:
        counts = Counter(_tokenize(text))
        vector = [0.0] * len(vocabulary)
        for token, count in counts.items():
            vector[index[token]] = float(count)
        vectors.append(vector)
    return vectors


def fastembed_encoder(model_name: str = "BAAI/bge-small-en-v1.5") -> Encoder:
    try:
        from fastembed import TextEmbedding
    except ImportError as error:  # pragma: no cover - depends on optional env
        raise RuntimeError("fastembed is required for encoder=fastembed") from error
    model = TextEmbedding(model_name=model_name, cache_dir=os.environ.get("FASTEMBED_CACHE_PATH"))

    def encode(texts: list[str]) -> list[Vector]:
        return [list(vector) for vector in model.embed(texts)]

    return encode


def _cosine(left: Vector, right: Vector) -> float:
    if not left or not right:
        return 0.0
    numerator = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return float(numerator / (left_norm * right_norm))


def run_dense_reference(
    slice_payload: dict[str, Any],
    corpus_payload: dict[str, Any],
    *,
    run_id: str,
    top_k: int,
    encoder: Encoder,
) -> dict[str, Any]:
    public_slice = PublicSliceArtifact.model_validate(slice_payload)
    if corpus_payload.get("schema_version") != "natural-benchmark-evidence-corpus-v1":
        raise ValueError("unsupported evidence corpus schema_version")
    if corpus_payload.get("slice_id") != public_slice.slice_id:
        raise ValueError("corpus slice_id mismatch")
    if top_k < 1:
        raise ValueError("top_k must be >= 1")

    corpus_by_item = corpus_payload["items"]
    unique_texts = list(
        dict.fromkeys(
            [
                *(item["question"] for item in public_slice.public_items),
                *[
                    unit["text"]
                    for item in public_slice.public_items
                    for unit in corpus_by_item.get(item["item_id"], [])
                ],
            ]
        )
    )
    encode_start = time.perf_counter()
    unique_vectors = encoder(unique_texts)
    embedding_ms = (time.perf_counter() - encode_start) * 1000.0
    if len(unique_vectors) != len(unique_texts):
        raise ValueError("encoder returned a different number of vectors")
    dimensions = {len(vector) for vector in unique_vectors}
    if len(dimensions) != 1:
        raise ValueError("encoder returned inconsistent vector dimensions")
    vector_by_text = dict(zip(unique_texts, unique_vectors, strict=True))
    amortized_embedding_ms = embedding_ms / len(public_slice.public_items)

    results: list[dict[str, Any]] = []
    for public_item in public_slice.public_items:
        start = time.perf_counter()
        item_id = public_item["item_id"]
        units = corpus_by_item.get(item_id)
        if units is None:
            raise ValueError(f"missing evidence corpus for item: {item_id}")
        query_vector = vector_by_text[public_item["question"]]
        scored_units = [
            (_cosine(query_vector, vector_by_text[unit["text"]]), offset, unit)
            for offset, unit in enumerate(units)
        ]
        scored_units.sort(key=lambda entry: (-entry[0], entry[1]))
        top_units = [entry[2] for entry in scored_units[:top_k]]
        latency_ms = amortized_embedding_ms + (time.perf_counter() - start) * 1000.0
        results.append(
            {
                "item_id": item_id,
                "predicted_answer": None,
                "retrieved_evidence_refs": [unit["unit_id"] for unit in top_units],
                "abstained": len(top_units) == 0,
                "fallback_triggered": False,
                "fallback_reason": None,
                "latency_ms": latency_ms,
                "evidence_token_count": sum(len(_tokenize(unit["text"])) for unit in top_units),
                "metadata": {
                    "top_scores": [float(entry[0]) for entry in scored_units[:top_k]],
                    "top_k": top_k,
                    "encoder_batch_unique_text_count": len(unique_texts),
                    "shared_embedding_ms_per_item": amortized_embedding_ms,
                },
            }
        )

    payload = {
        "schema_version": "natural-benchmark-results-v1",
        "slice_id": public_slice.slice_id,
        "source_manifest_sha256": public_slice.source_manifest_sha256,
        "run_id": run_id,
        "arm": "dense_reference",
        "items": results,
    }
    ResultsArtifact.model_validate(payload)
    return payload


def run_dense_reference_file(
    slice_path: Path,
    corpus_path: Path,
    output_path: Path,
    *,
    run_id: str,
    top_k: int,
    encoder_name: str,
) -> dict[str, Any]:
    if encoder_name == "lexical":
        encoder = lexical_encoder
    elif encoder_name == "fastembed":
        encoder = fastembed_encoder()
    else:
        raise ValueError(f"unsupported encoder: {encoder_name}")
    payload = run_dense_reference(
        load_json(slice_path),
        load_json(corpus_path),
        run_id=run_id,
        top_k=top_k,
        encoder=encoder,
    )
    write_json_immutable(output_path, payload)
    return payload
