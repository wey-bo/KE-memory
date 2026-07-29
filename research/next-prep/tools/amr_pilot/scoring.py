"""Deterministic blinding, semantic scoring, and efficiency aggregation."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Iterable, Literal, Mapping, Sequence

from tools.amr_pilot.models import AttemptSidecar, Route, SemanticChecklist


Outcome = Literal["supported", "omitted", "incorrect"]


@dataclass(frozen=True, slots=True)
class SemanticScore:
    supported_weight: float
    gold_weight: float
    recall: float
    precision: float
    hallucination_count: int
    incorrect_item_count: int
    critical_error_count: int


@dataclass(frozen=True, slots=True)
class EfficiencySummary:
    route: Route
    expected_samples: int
    first_pass_parse_rate: float
    final_parse_count: int
    latency_ms: int | None
    usage_status: Literal["measured", "unavailable"]
    total_tokens: int | None
    cost_usd: float | None
    latency_status: Literal["measured", "unavailable"] = "measured"


@dataclass(frozen=True, slots=True)
class EfficiencyComparison:
    latency_ratio: float | None
    token_ratio: float | None
    cost_ratio: float | None
    token_status: Literal["measured", "undecidable"]
    cost_status: Literal["measured", "undecidable"]


def _candidate_key(candidate: Mapping[str, object]) -> tuple[str, str]:
    sample_id = candidate.get("sample_id")
    route = candidate.get("route")
    if not isinstance(sample_id, str) or route not in {"A", "B", "C"}:
        raise ValueError("candidate must include a valid sample_id and route")
    output = candidate.get("output")
    output_sha256 = candidate.get("output_sha256")
    if not isinstance(output, str) or not isinstance(output_sha256, str):
        raise ValueError("candidate must include output and output_sha256")
    if hashlib.sha256(output.encode("utf-8")).hexdigest() != output_sha256:
        raise ValueError("candidate output_sha256 does not match output")
    return sample_id, route


def _blind_id(run_id: str, sample_id: str, route: str) -> str:
    digest = hashlib.sha256(f"{run_id}\0{sample_id}\0{route}".encode("utf-8")).digest()
    numeric = int.from_bytes(digest[:8], "big") % 1_000_000_000_000
    return f"BLIND-{numeric:012d}"


def _sorted_candidates(candidates: Sequence[Mapping[str, object]]) -> list[Mapping[str, object]]:
    ordered = sorted(candidates, key=_candidate_key)
    keys = [_candidate_key(candidate) for candidate in ordered]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate candidate sample and route")
    blind_ids = [_blind_id("collision-check", sample_id, route) for sample_id, route in keys]
    if len(blind_ids) != len(set(blind_ids)):
        raise ValueError("blind ID collision")
    return ordered


def make_blind_review_payloads(
    run_id: str,
    candidates: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    payloads: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    for candidate in _sorted_candidates(candidates):
        sample_id, route = _candidate_key(candidate)
        blind_id = _blind_id(run_id, sample_id, route)
        if blind_id in seen_ids:
            raise ValueError("blind ID collision")
        seen_ids.add(blind_id)
        payloads.append(
            {
                "schema_version": "amr-pilot-blind-review-item-v1",
                "blind_id": blind_id,
                "sample_id": sample_id,
                "output": candidate["output"],
                "output_sha256": candidate["output_sha256"],
            }
        )
    return payloads


def make_blind_mapping(
    run_id: str,
    candidates: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    mapping: list[dict[str, object]] = []
    for candidate in _sorted_candidates(candidates):
        sample_id, route = _candidate_key(candidate)
        mapping.append(
            {
                "blind_id": _blind_id(run_id, sample_id, route),
                "sample_id": sample_id,
                "route": route,
                "output_sha256": candidate["output_sha256"],
            }
        )
    return mapping


def score_semantics(
    checklist: SemanticChecklist,
    review: Mapping[str, object],
) -> SemanticScore:
    if set(review) != {"judgments", "hallucinations"}:
        raise ValueError("review has unknown or missing fields")
    judgments = review["judgments"]
    hallucinations = review["hallucinations"]
    if not isinstance(judgments, list) or not isinstance(hallucinations, list):
        raise ValueError("review judgments and hallucinations must be lists")

    expected = {item.item_id: item for item in checklist.items}
    outcomes: dict[str, Outcome] = {}
    for judgment in judgments:
        if not isinstance(judgment, dict) or set(judgment) != {"item_id", "outcome"}:
            raise ValueError("judgment has unknown or missing fields")
        item_id = judgment["item_id"]
        outcome = judgment["outcome"]
        if not isinstance(item_id, str) or outcome not in {"supported", "omitted", "incorrect"}:
            raise ValueError("judgment has an invalid item_id or outcome")
        if item_id in outcomes:
            raise ValueError(f"duplicate judgment: {item_id}")
        outcomes[item_id] = outcome
    if set(outcomes) != set(expected):
        raise ValueError("review judgments must exactly cover the gold items")

    hallucination_weight = 0.0
    critical_hallucinations = 0
    for hallucination in hallucinations:
        if not isinstance(hallucination, dict) or set(hallucination) != {
            "statement",
            "importance",
            "weight",
        }:
            raise ValueError("hallucination has unknown or missing fields")
        statement = hallucination["statement"]
        importance = hallucination["importance"]
        weight = hallucination["weight"]
        if not isinstance(statement, str) or not statement.strip():
            raise ValueError("hallucination statement must be non-empty")
        if importance not in {"critical", "ordinary"}:
            raise ValueError("hallucination importance is invalid")
        if not isinstance(weight, (int, float)) or isinstance(weight, bool) or weight <= 0:
            raise ValueError("hallucination weight must be positive")
        hallucination_weight += float(weight)
        critical_hallucinations += int(importance == "critical")

    gold_weight = sum(item.weight for item in checklist.items)
    supported_weight = sum(
        item.weight for item in checklist.items if outcomes[item.item_id] == "supported"
    )
    incorrect_items = [item for item in checklist.items if outcomes[item.item_id] == "incorrect"]
    incorrect_weight = sum(item.weight for item in incorrect_items)
    precision_denominator = supported_weight + incorrect_weight + hallucination_weight
    precision = supported_weight / precision_denominator if precision_denominator else 0.0
    recall = supported_weight / gold_weight
    critical_incorrect = sum(item.importance == "critical" for item in incorrect_items)
    return SemanticScore(
        supported_weight=supported_weight,
        gold_weight=gold_weight,
        recall=recall,
        precision=precision,
        hallucination_count=len(hallucinations),
        incorrect_item_count=len(incorrect_items),
        critical_error_count=critical_incorrect + critical_hallucinations,
    )


def _latest_attempts(attempts: Iterable[AttemptSidecar], route: Route) -> dict[str, AttemptSidecar]:
    latest: dict[str, AttemptSidecar] = {}
    for attempt in attempts:
        if attempt.route != route:
            continue
        current = latest.get(attempt.sample_id)
        if current is None or attempt.attempt > current.attempt:
            latest[attempt.sample_id] = attempt
    return latest


def aggregate_efficiency(
    attempts: Sequence[AttemptSidecar],
    route: Route,
    *,
    expected_samples: int,
) -> EfficiencySummary:
    if expected_samples <= 0:
        raise ValueError("expected_samples must be positive")
    included_routes: set[Route] = {route}
    if route == "B":
        included_routes.add("C")
    included = [attempt for attempt in attempts if attempt.route in included_routes]
    target = [attempt for attempt in attempts if attempt.route == route]
    first_pass_valid = sum(
        attempt.attempt == 1 and attempt.parse_status in {"valid", "not_applicable"}
        for attempt in target
    )
    latest = _latest_attempts(attempts, route)
    final_parse_count = sum(
        attempt.parse_status in {"valid", "not_applicable"} for attempt in latest.values()
    )
    latency_available = all(
        attempt.latency_status == "measured" and attempt.latency_ms is not None
        for attempt in included
    )
    latency_ms = (
        sum(attempt.latency_ms for attempt in included if attempt.latency_ms is not None)
        if latency_available
        else None
    )

    usage_available = all(attempt.usage.status == "measured" for attempt in included)
    total_tokens: int | None = None
    cost_usd: float | None = None
    if usage_available:
        total_tokens = sum(attempt.usage.total_tokens for attempt in included if attempt.usage.status == "measured")
        cost_usd = sum(attempt.usage.cost_usd for attempt in included if attempt.usage.status == "measured")
    return EfficiencySummary(
        route=route,
        expected_samples=expected_samples,
        first_pass_parse_rate=first_pass_valid / expected_samples,
        final_parse_count=final_parse_count,
        latency_ms=latency_ms,
        usage_status="measured" if usage_available else "unavailable",
        total_tokens=total_tokens,
        cost_usd=cost_usd,
        latency_status="measured" if latency_available else "unavailable",
    )


def _ratio(candidate: float | int | None, baseline: float | int | None) -> float | None:
    if candidate is None or baseline is None or baseline == 0:
        return None
    return candidate / baseline


def compare_efficiency(
    candidate: EfficiencySummary,
    baseline: EfficiencySummary,
) -> EfficiencyComparison:
    token_ratio = _ratio(candidate.total_tokens, baseline.total_tokens)
    cost_ratio = _ratio(candidate.cost_usd, baseline.cost_usd)
    return EfficiencyComparison(
        latency_ratio=_ratio(candidate.latency_ms, baseline.latency_ms),
        token_ratio=token_ratio,
        cost_ratio=cost_ratio,
        token_status="measured" if token_ratio is not None else "undecidable",
        cost_status="measured" if cost_ratio is not None else "undecidable",
    )
