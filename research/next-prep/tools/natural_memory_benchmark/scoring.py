from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

from .io import load_json, write_json_immutable
from .models import GoldArtifact, PublicSliceArtifact, ResultsArtifact, ScoreReport


def _normalize_answer(value: str | None) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", value.strip().casefold())


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _evidence_recall(gold_refs: set[str], retrieved_refs: set[str]) -> float:
    if not gold_refs:
        return 1.0 if not retrieved_refs else 0.0
    return len(gold_refs & retrieved_refs) / len(gold_refs)


def _evidence_precision(gold_refs: set[str], retrieved_refs: set[str]) -> float:
    if not retrieved_refs:
        return 1.0 if not gold_refs else 0.0
    return len(gold_refs & retrieved_refs) / len(retrieved_refs)


def _validate_item_alignment(
    public_slice: PublicSliceArtifact,
    gold: GoldArtifact,
    results: ResultsArtifact,
) -> None:
    if public_slice.slice_id != gold.slice_id or public_slice.slice_id != results.slice_id:
        raise ValueError("slice_id mismatch")
    if public_slice.source_manifest_sha256 != gold.source_manifest_sha256:
        raise ValueError("gold source_manifest_sha256 mismatch")
    if public_slice.source_manifest_sha256 != results.source_manifest_sha256:
        raise ValueError("results source_manifest_sha256 mismatch")
    public_ids = [item["item_id"] for item in public_slice.public_items]
    gold_ids = [item["item_id"] for item in gold.items]
    result_ids = [item.item_id for item in results.items]
    if public_ids != gold_ids:
        raise ValueError("public slice and gold item ids diverge")
    if public_ids != result_ids:
        raise ValueError("result item ids diverge")


def score_results(
    slice_payload: dict[str, Any],
    gold_payload: dict[str, Any],
    results_payload: dict[str, Any],
) -> dict[str, Any]:
    public_slice = PublicSliceArtifact.model_validate(slice_payload)
    gold = GoldArtifact.model_validate(gold_payload)
    results = ResultsArtifact.model_validate(results_payload)
    _validate_item_alignment(public_slice, gold, results)

    evidence_exact = 0
    evidence_recalls: list[float] = []
    evidence_precisions: list[float] = []
    all_evidence = 0
    answer_exact = 0
    answer_scoreable = 0
    manual_required = 0
    abstention_items = 0
    abstention_correct = 0
    critical_false_positive = 0
    fallback_by_reason: Counter[str] = Counter()
    fallback_count = 0
    latencies: list[float] = []
    token_counts: list[float] = []

    for public_item, gold_item, result_item in zip(public_slice.public_items, gold.items, results.items, strict=True):
        gold_refs = set(gold_item.get("evidence_refs", []))
        retrieved_refs = set(result_item.retrieved_evidence_refs)
        if gold_refs == retrieved_refs:
            evidence_exact += 1
        recall = _evidence_recall(gold_refs, retrieved_refs)
        evidence_recalls.append(recall)
        evidence_precisions.append(_evidence_precision(gold_refs, retrieved_refs))
        if recall == 1.0:
            all_evidence += 1

        if gold_item.get("answer_policy") == "manual_required":
            manual_required += 1
        else:
            answer_scoreable += 1
            if _normalize_answer(gold_item.get("answer")) == _normalize_answer(result_item.predicted_answer):
                answer_exact += 1

        is_abstention = public_item.get("slice_group") == "abstention" or not gold_refs
        if is_abstention:
            abstention_items += 1
            if result_item.abstained and not retrieved_refs:
                abstention_correct += 1
            elif retrieved_refs or not result_item.abstained:
                critical_false_positive += 1

        if result_item.critical_false_positive:
            critical_false_positive += 1
        if result_item.fallback_triggered:
            fallback_count += 1
            if result_item.fallback_reason is not None:
                fallback_by_reason[result_item.fallback_reason] += 1
        if result_item.latency_ms is not None:
            latencies.append(result_item.latency_ms)
        if result_item.evidence_token_count is not None:
            token_counts.append(float(result_item.evidence_token_count))

    item_count = len(results.items)
    return {
        "item_count": item_count,
        "answer_scoreable_count": answer_scoreable,
        "manual_required_count": manual_required,
        "evidence_set_exact_match": evidence_exact / item_count if item_count else 0.0,
        "evidence_recall": _mean(evidence_recalls) or 0.0,
        "all_evidence_at_k": all_evidence / item_count if item_count else 0.0,
        "evidence_precision": _mean(evidence_precisions) or 0.0,
        "answer_exact_match": answer_exact / answer_scoreable if answer_scoreable else None,
        "abstention_item_count": abstention_items,
        "abstention_correct": abstention_correct / abstention_items if abstention_items else None,
        "critical_false_positive_count": critical_false_positive,
        "fallback_trigger_rate": fallback_count / item_count if item_count else 0.0,
        "fallback_by_reason": dict(sorted(fallback_by_reason.items())),
        "mean_latency_ms": _mean(latencies),
        "mean_evidence_token_count": _mean(token_counts),
    }


def build_oracle_results(
    slice_payload: dict[str, Any],
    gold_payload: dict[str, Any],
    *,
    run_id: str,
) -> dict[str, Any]:
    public_slice = PublicSliceArtifact.model_validate(slice_payload)
    gold = GoldArtifact.model_validate(gold_payload)
    if [item["item_id"] for item in public_slice.public_items] != [item["item_id"] for item in gold.items]:
        raise ValueError("public slice and gold item ids diverge")
    return {
        "schema_version": "natural-benchmark-results-v1",
        "slice_id": public_slice.slice_id,
        "source_manifest_sha256": public_slice.source_manifest_sha256,
        "run_id": run_id,
        "arm": "oracle",
        "items": [
            {
                "item_id": item["item_id"],
                "predicted_answer": item.get("answer"),
                "retrieved_evidence_refs": list(item.get("evidence_refs", [])),
                "abstained": not item.get("evidence_refs", []),
                "fallback_triggered": False,
                "fallback_reason": None,
            }
            for item in gold.items
        ],
    }


def score_results_file(root: Path, slice_id: str, results_path: Path, output_path: Path) -> ScoreReport:
    slice_payload = load_json(root / slice_id / "slice.json")
    gold_payload = load_json(root / slice_id / "gold.json")
    results_payload = load_json(results_path)
    results = ResultsArtifact.model_validate(results_payload)
    metrics = score_results(slice_payload, gold_payload, results_payload)
    report = ScoreReport(
        run_id=results.run_id,
        slice_id=results.slice_id,
        source_manifest_sha256=results.source_manifest_sha256,
        arm=results.arm,
        metrics=metrics,
    )
    write_json_immutable(output_path, report)
    return report
