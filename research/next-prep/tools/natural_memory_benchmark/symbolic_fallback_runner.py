from __future__ import annotations

from pathlib import Path
from typing import Any

from .answerability_policy import assess_answerability
from .dense_runner import Encoder, fastembed_encoder, lexical_encoder, run_dense_reference
from .fallback_policy import classify_fallback
from .io import load_json, write_json_immutable
from .models import PublicSliceArtifact, ResultsArtifact
from .symbolic_runner import run_symbolic


def _selected_units(corpus_units: list[dict[str, Any]], refs: list[str]) -> list[dict[str, Any]]:
    unit_by_id = {str(unit["unit_id"]): unit for unit in corpus_units}
    return [unit_by_id[ref] for ref in refs if ref in unit_by_id]


def _apply_answerability_gate(
    public_item: dict[str, Any],
    item: dict[str, Any],
    corpus_units: list[dict[str, Any]],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    retrieved_refs = list(item.get("retrieved_evidence_refs", []))
    decision = assess_answerability(public_item, _selected_units(corpus_units, retrieved_refs))
    metadata.update(decision.metadata())
    if decision.answerable:
        return {
            **item,
            "metadata": metadata,
        }

    metadata["answerability_blocked_evidence_refs"] = retrieved_refs
    return {
        **item,
        "retrieved_evidence_refs": [],
        "abstained": True,
        "fallback_triggered": False,
        "fallback_reason": None,
        "critical_false_positive": False,
        "evidence_token_count": 0,
        "metadata": metadata,
    }


def _merge_item(
    public_item: dict[str, Any],
    symbolic_item: dict[str, Any],
    dense_item: dict[str, Any],
    corpus_units: list[dict[str, Any]],
) -> dict[str, Any]:
    policy = classify_fallback(public_item, symbolic_item)
    if not policy.allowed:
        metadata = dict(symbolic_item.get("metadata", {}))
        metadata.update(policy.metadata())
        metadata["fallback_policy"] = "taxonomy_v1"
        item = {
            **symbolic_item,
            "fallback_triggered": False,
            "fallback_reason": None,
            "metadata": metadata,
        }
        return _apply_answerability_gate(public_item, item, corpus_units, metadata)

    metadata = {
        "symbolic_metadata": symbolic_item.get("metadata", {}),
        "fallback_metadata": dense_item.get("metadata", {}),
        "fallback_policy": "taxonomy_v1",
        **policy.metadata(),
    }
    symbolic_latency = symbolic_item.get("latency_ms") or 0.0
    dense_latency = dense_item.get("latency_ms") or 0.0
    item = {
        "item_id": symbolic_item["item_id"],
        "predicted_answer": None,
        "retrieved_evidence_refs": list(dense_item.get("retrieved_evidence_refs", [])),
        "abstained": not dense_item.get("retrieved_evidence_refs"),
        "fallback_triggered": True,
        "fallback_reason": policy.reason_candidate,
        "critical_false_positive": False,
        "latency_ms": symbolic_latency + dense_latency,
        "evidence_token_count": dense_item.get("evidence_token_count"),
        "metadata": metadata,
    }
    return _apply_answerability_gate(public_item, item, corpus_units, metadata)


def run_symbolic_fallback(
    slice_payload: dict[str, Any],
    corpus_payload: dict[str, Any],
    *,
    run_id: str,
    symbolic_top_k: int,
    fallback_top_k: int,
    encoder: Encoder,
) -> dict[str, Any]:
    public_slice = PublicSliceArtifact.model_validate(slice_payload)
    symbolic_payload = run_symbolic(
        slice_payload,
        corpus_payload,
        run_id=f"{run_id}-symbolic-stage",
        top_k=symbolic_top_k,
    )
    dense_payload = run_dense_reference(
        slice_payload,
        corpus_payload,
        run_id=f"{run_id}-fallback-stage",
        top_k=fallback_top_k,
        encoder=encoder,
    )
    corpus_by_item = corpus_payload["items"]
    items = [
        _merge_item(public_item, symbolic_item, dense_item, corpus_by_item[public_item["item_id"]])
        for public_item, symbolic_item, dense_item in zip(
            public_slice.public_items,
            symbolic_payload["items"],
            dense_payload["items"],
            strict=True,
        )
    ]
    payload = {
        "schema_version": "natural-benchmark-results-v1",
        "slice_id": public_slice.slice_id,
        "source_manifest_sha256": public_slice.source_manifest_sha256,
        "run_id": run_id,
        "arm": "symbolic_fallback",
        "items": items,
    }
    ResultsArtifact.model_validate(payload)
    return payload


def run_symbolic_fallback_file(
    slice_path: Path,
    corpus_path: Path,
    output_path: Path,
    *,
    run_id: str,
    symbolic_top_k: int,
    fallback_top_k: int,
    encoder_name: str,
) -> dict[str, Any]:
    if encoder_name == "lexical":
        encoder = lexical_encoder
    elif encoder_name == "fastembed":
        encoder = fastembed_encoder()
    else:
        raise ValueError(f"unsupported encoder: {encoder_name}")
    payload = run_symbolic_fallback(
        load_json(slice_path),
        load_json(corpus_path),
        run_id=run_id,
        symbolic_top_k=symbolic_top_k,
        fallback_top_k=fallback_top_k,
        encoder=encoder,
    )
    write_json_immutable(output_path, payload)
    return payload
