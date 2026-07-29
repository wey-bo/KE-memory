"""Base-scenario paired metrics, including report-ready slices and diagnostics."""

from __future__ import annotations

import math
import random
from collections import defaultdict
from collections.abc import Iterable, Mapping
from statistics import median
from typing import Any


METRICS = (
    "evidence_set_exact_match",
    "precision_at_k",
    "recall_at_k",
    "critical_false_positive_rate",
    "constraint_satisfaction_rate",
    "answer_correctness",
    "abstention_accuracy",
    "fallback_rate",
    "extraction_accuracy",
)


def _answer_ok(predicted: Any, answer: dict[str, Any], abstained: bool) -> bool:
    if answer.get("kind") == "unanswerable":
        return abstained or predicted in {None, "abstain", "unanswerable"}
    if abstained or predicted is None:
        return False
    if isinstance(predicted, dict):
        predicted = (
            predicted.get("values", [None])[0]
            if predicted.get("kind") == "value"
            else None
        )
    return str(predicted) in {str(value) for value in answer.get("values", [])}


def paired_bootstrap_interval(
    differences: dict[str, float | None],
    iterations: int = 2_000,
    seed: int = 20260725,
) -> dict[str, Any]:
    unavailable = sorted(key for key, value in differences.items() if value is None)
    values = [value for value in differences.values() if value is not None]
    base = {
        "unit": "base_scenario",
        "seed": seed,
        "pair_count": len(differences),
        "valid_pair_count": len(values),
        "unavailable_base_scenarios": unavailable,
    }
    if unavailable or not values:
        return {"point_estimate": None, "ci95": [None, None], **base}
    rng = random.Random(seed)
    samples = sorted(
        sum(rng.choice(values) for _ in values) / len(values)
        for _ in range(iterations)
    )
    return {
        "point_estimate": round(sum(values) / len(values), 12),
        "ci95": [
            samples[int(0.025 * (iterations - 1))],
            samples[int(0.975 * (iterations - 1))],
        ],
        **base,
    }


def _strict_mean(values: list[float | bool | None]) -> float | None:
    if not values or any(value is None for value in values):
        return None
    return sum(float(value) for value in values if value is not None) / len(values)


def _optional_mean(values: list[float | None]) -> float | None:
    available = [value for value in values if value is not None]
    return sum(available) / len(available) if available else None


def _summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    errors = sum(int(item.get("execution_error_count", 0)) for item in items)
    contaminated = sorted(
        {
            str(scenario_id)
            for item in items
            for scenario_id in item.get("contaminated_base_scenarios", [])
        }
    )
    result: dict[str, Any] = {
        "base_scenarios": len(items),
        "execution_error_count": errors,
        "contaminated_base_scenarios": contaminated,
        "comparison_eligible": bool(items) and errors == 0,
    }
    for name in METRICS:
        values = [item.get(name) for item in items]
        result[name] = (
            _optional_mean(values)
            if name == "extraction_accuracy" and errors == 0
            else _strict_mean(values)
        )
    result["critical_false_positive_denominator"] = sum(
        int(item.get("critical_false_positive_denominator", 0)) for item in items
    )
    latency = [
        value
        for item in items
        for value in item.get("latencies", [])
        if value is not None
    ]
    result["latency_p50_ms"] = median(latency) if latency else None
    result["latency_p95_ms"] = (
        sorted(latency)[max(0, math.ceil(0.95 * len(latency)) - 1)]
        if latency
        else None
    )
    return result


def aggregate_metrics(
    results: list[dict[str, Any]],
    gold: dict[str, dict[str, Any]],
    *,
    bootstrap_seed: int = 20260725,
    critical_distractor_ids: Mapping[str, Iterable[str]] | None = None,
) -> dict[str, Any]:
    """Aggregate immutable result rows without treating execution errors as outcomes."""
    extra_critical = critical_distractor_ids or {}
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in results:
        grouped[(row["track"], row["arm"], row["scenario_id"])].append(row)

    per_arm: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for (track, arm, scenario_id), rows in grouped.items():
        target = gold[scenario_id]
        required = set(target.get("required_evidence_turn_ids", []))
        negatives = set(target.get("hard_negative_turn_ids", []))
        negatives.update(str(value) for value in extra_critical.get(scenario_id, ()))
        values: list[dict[str, Any]] = []
        for row in rows:
            selected = set(row.get("selected_evidence_turn_ids") or [])
            checks = row.get("constraint_checks") or {}
            fallback = row.get("fallback") or {
                "triggered": bool(row.get("fallback_trigger"))
            }
            answer = target["answer"]
            is_error = row.get("status") == "error" or bool(row.get("error"))
            values.append(
                {
                    "exact": None if is_error else selected == required,
                    "precision": (
                        None
                        if is_error
                        else len(selected & required) / len(selected)
                        if selected
                        else 0.0
                    ),
                    "recall": (
                        None
                        if is_error
                        else len(selected & required) / len(required)
                        if required
                        else 1.0
                    ),
                    "cfp": (
                        None if is_error or not negatives else bool(selected & negatives)
                    ),
                    "constraints": (
                        None
                        if is_error
                        else all(checks.values())
                        if isinstance(checks, dict) and checks
                        else False
                    ),
                    "answer": (
                        None
                        if is_error
                        else _answer_ok(
                            row.get("predicted_answer"),
                            answer,
                            bool(row.get("abstained")),
                        )
                    ),
                    "abstain": (
                        None
                        if is_error
                        else _answer_ok(
                            row.get("predicted_answer"),
                            answer,
                            bool(row.get("abstained")),
                        )
                        if answer.get("kind") == "unanswerable"
                        else 0.0
                    ),
                    "fallback": None if is_error else bool(fallback.get("triggered")),
                    "latency": row.get("latency_ms"),
                    "scale": str(row.get("distractor_scale", 0)),
                    "extraction": None if is_error else row.get("extraction_accuracy"),
                    "is_error": is_error,
                    "error": row.get("error"),
                    "cfp_eligible": not is_error and bool(negatives),
                }
            )

        error_rows = [
            {
                "distractor_scale": value["scale"],
                "error": value["error"] or "status=error",
            }
            for value in values
            if value["is_error"]
        ]

        def summarize_values(subset: list[dict[str, Any]]) -> dict[str, Any]:
            errors = sum(value["is_error"] for value in subset)
            return {
                "evidence_set_exact_match": _strict_mean(
                    [value["exact"] for value in subset]
                ),
                "precision_at_k": _strict_mean(
                    [value["precision"] for value in subset]
                ),
                "recall_at_k": _strict_mean([value["recall"] for value in subset]),
                "critical_false_positive_rate": _strict_mean(
                    [value["cfp"] for value in subset]
                ),
                "critical_false_positive_denominator": sum(
                    value["cfp_eligible"] for value in subset
                ),
                "constraint_satisfaction_rate": _strict_mean(
                    [value["constraints"] for value in subset]
                ),
                "answer_correctness": _strict_mean(
                    [value["answer"] for value in subset]
                ),
                "abstention_accuracy": _strict_mean(
                    [value["abstain"] for value in subset]
                ),
                "fallback_rate": _strict_mean(
                    [value["fallback"] for value in subset]
                ),
                "extraction_accuracy": (
                    None
                    if errors
                    else _optional_mean([value["extraction"] for value in subset])
                ),
                "latencies": [
                    value["latency"]
                    for value in subset
                    if value["latency"] is not None
                ],
                "execution_error_count": errors,
                "contaminated_base_scenarios": (
                    [scenario_id] if errors else []
                ),
                "comparison_eligible": errors == 0,
            }

        entry = {
            "scenario_id": scenario_id,
            "family": target.get("family", "unknown"),
            "by_scale": {},
            **summarize_values(values),
            "execution_errors": error_rows,
        }
        for scale in sorted({value["scale"] for value in values}):
            entry["by_scale"][scale] = summarize_values(
                [value for value in values if value["scale"] == scale]
            )
        per_arm[(track, arm)].append(entry)

    output: dict[str, Any] = {"arms": {}, "fallback": {}, "bootstrap": {}}
    for (track, arm), entries in per_arm.items():
        families = {
            family: _summary(
                [entry for entry in entries if entry["family"] == family]
            )
            for family in sorted({entry["family"] for entry in entries})
        }
        scales = {
            scale: _summary(
                [
                    {
                        **entry["by_scale"][scale],
                        "scenario_id": entry["scenario_id"],
                    }
                    for entry in entries
                    if scale in entry["by_scale"]
                ]
            )
            for scale in sorted(
                {scale for entry in entries for scale in entry["by_scale"]}
            )
        }
        output["arms"].setdefault(track, {})[arm] = {
            "overall": _summary(entries),
            "families": families,
            "scales": scales,
            "by_base_scenario": entries,
        }

    fallback_entries = per_arm.get(("automatic", "O+E"), []) or [
        entry
        for (track, arm), values in per_arm.items()
        if arm == "O+E"
        for entry in values
    ]
    structural_fallback_entries = [
        entry
        for entry in fallback_entries
        if entry["family"] != "synonymy_sense_external_unanswerable"
    ]
    output["fallback"] = {
        "overall_rate": _strict_mean(
            [entry["fallback_rate"] for entry in fallback_entries]
        ),
        "structural_family_rate": _strict_mean(
            [entry["fallback_rate"] for entry in structural_fallback_entries]
        ),
        "execution_error_count": sum(
            entry["execution_error_count"] for entry in fallback_entries
        ),
    }

    def paired(
        track: str,
        left: str,
        right: str,
        family: str | None = None,
        scale: str | None = None,
    ) -> dict[str, Any]:
        left_rows = {
            row["scenario_id"]: row
            for row in per_arm.get((track, left), [])
            if family is None or row["family"] == family
        }
        right_rows = {
            row["scenario_id"]: row
            for row in per_arm.get((track, right), [])
            if family is None or row["family"] == family
        }
        scenario_ids = sorted(left_rows.keys() | right_rows.keys())
        differences: dict[str, float | None] = {}
        contaminated: list[str] = []
        missing: list[str] = []
        for scenario_id in scenario_ids:
            left_row = left_rows.get(scenario_id)
            right_row = right_rows.get(scenario_id)
            if left_row is None or right_row is None:
                missing.append(scenario_id)
                differences[scenario_id] = None
                continue
            left_metric = (
                left_row["by_scale"].get(scale, {}).get(
                    "evidence_set_exact_match"
                )
                if scale
                else left_row["evidence_set_exact_match"]
            )
            right_metric = (
                right_row["by_scale"].get(scale, {}).get(
                    "evidence_set_exact_match"
                )
                if scale
                else right_row["evidence_set_exact_match"]
            )
            left_errors = (
                left_row["by_scale"].get(scale, {}).get(
                    "execution_error_count", 0
                )
                if scale
                else left_row["execution_error_count"]
            )
            right_errors = (
                right_row["by_scale"].get(scale, {}).get(
                    "execution_error_count", 0
                )
                if scale
                else right_row["execution_error_count"]
            )
            if left_errors or right_errors:
                contaminated.append(scenario_id)
            differences[scenario_id] = (
                None
                if left_metric is None or right_metric is None
                else left_metric - right_metric
            )
        interval = paired_bootstrap_interval(
            differences, seed=bootstrap_seed
        )
        interval["contaminated_base_scenarios"] = contaminated
        interval["missing_base_scenarios"] = missing
        return interval

    families = sorted(
        {entry["family"] for entry in per_arm.get(("oracle", "O+"), [])}
    )
    dense_arms = ("B0", "B1", "B2")
    output["bootstrap"] = {
        "overall": {
            **{
                f"O+_minus_{arm}": paired("oracle", "O+", arm)
                for arm in dense_arms
            },
            "O+_minus_O-": paired("oracle", "O+", "O-"),
        },
        "families": {
            family: {
                **{
                    f"O+_minus_{arm}": paired(
                        "oracle", "O+", arm, family=family
                    )
                    for arm in dense_arms
                },
                "O+_minus_O-": paired(
                    "oracle", "O+", "O-", family=family
                ),
            }
            for family in families
        },
        "scale_500": {
            **{
                f"O+_minus_{arm}": paired(
                    "oracle", "O+", arm, scale="500"
                )
                for arm in dense_arms
            },
            "O+_minus_O-": paired(
                "oracle", "O+", "O-", scale="500"
            ),
        },
    }
    return output
