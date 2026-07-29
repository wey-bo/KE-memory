from __future__ import annotations

from datetime import datetime, timezone
import hashlib

import pytest

from tools.amr_pilot.models import AttemptSidecar, SemanticChecklist
from tools.amr_pilot.scoring import (
    aggregate_efficiency,
    compare_efficiency,
    make_blind_mapping,
    make_blind_review_payloads,
    score_semantics,
)


def checklist() -> SemanticChecklist:
    return SemanticChecklist.model_validate(
        {
            "sample_id": "AMR-S001",
            "source_text_sha256": "1" * 64,
            "items": [
                {
                    "item_id": "AMR-S001-G001",
                    "statement": "The cancellation is negated.",
                    "importance": "critical",
                    "weight": 2,
                    "evidence_quotes": ["did not cancel"],
                    "category": "polarity",
                },
                {
                    "item_id": "AMR-S001-G002",
                    "statement": "The object is the tablet order.",
                    "importance": "ordinary",
                    "weight": 1,
                    "evidence_quotes": ["tablet order"],
                    "category": "role",
                },
            ],
            "forbidden_inferences": ["The cancellation occurred."],
        }
    )


def test_blind_ids_are_deterministic_and_payloads_hide_routes() -> None:
    amr_output = "(c / cancel-01 :polarity -)"
    knowledge_output = '{"items":[]}'
    candidates = [
        {
            "sample_id": "AMR-S001",
            "route": "A",
            "output": amr_output,
            "output_sha256": hashlib.sha256(amr_output.encode("utf-8")).hexdigest(),
        },
        {
            "sample_id": "AMR-S001",
            "route": "C",
            "output": knowledge_output,
            "output_sha256": hashlib.sha256(knowledge_output.encode("utf-8")).hexdigest(),
        },
    ]

    first = make_blind_review_payloads("run-20260724T120000Z", candidates)
    second = make_blind_review_payloads("run-20260724T120000Z", candidates)
    mapping = make_blind_mapping("run-20260724T120000Z", candidates)

    assert first == second
    assert len({item["blind_id"] for item in first}) == 2
    assert all("route" not in item for item in first)
    assert all(not item["blind_id"].endswith(("A", "B", "C")) for item in first)
    assert {entry["blind_id"] for entry in mapping} == {item["blind_id"] for item in first}
    assert {entry["route"] for entry in mapping} == {"A", "C"}


def test_scoring_requires_complete_exact_gold_coverage() -> None:
    review = {
        "judgments": [
            {"item_id": "AMR-S001-G001", "outcome": "supported"},
        ],
        "hallucinations": [],
    }

    with pytest.raises(ValueError, match="exactly cover"):
        score_semantics(checklist(), review)


def test_weighted_precision_recall_and_error_counts_are_explicit() -> None:
    review = {
        "judgments": [
            {"item_id": "AMR-S001-G001", "outcome": "supported"},
            {"item_id": "AMR-S001-G002", "outcome": "incorrect"},
        ],
        "hallucinations": [
            {"statement": "The cancellation occurred.", "importance": "critical", "weight": 2},
        ],
    }

    result = score_semantics(checklist(), review)

    assert result.supported_weight == 2
    assert result.gold_weight == 3
    assert result.recall == pytest.approx(2 / 3)
    assert result.precision == pytest.approx(2 / 5)
    assert result.hallucination_count == 1
    assert result.critical_error_count == 1
    assert result.incorrect_item_count == 1


def attempt(
    route: str,
    *,
    sample_id: str = "AMR-S001",
    attempt_number: int = 1,
    parse_status: str = "valid",
    input_tokens: int | None = 10,
    output_tokens: int | None = 5,
    latency_ms: int | None = 100,
) -> AttemptSidecar:
    usage: dict[str, object]
    if input_tokens is None or output_tokens is None:
        usage = {"status": "unavailable", "reason": "not exposed"}
    else:
        usage = {
            "status": "measured",
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": 0.01,
        }
    return AttemptSidecar.model_validate(
        {
            "sample_id": sample_id,
            "route": route,
            "run_id": "run-20260724T120000Z",
            "attempt": attempt_number,
            "previous_attempt_sha256": None if attempt_number == 1 else "3" * 64,
            "model_id": "gpt-5.6-terra",
            "prompt_sha256": "1" * 64,
            "raw_output_sha256": "2" * 64,
            "started_at": datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc),
            "finished_at": datetime(2026, 7, 24, 12, 0, 1, tzinfo=timezone.utc),
            "latency_ms": latency_ms,
            "latency_status": "measured" if latency_ms is not None else "unavailable",
            "usage": usage,
            "parse_status": parse_status,
            "parse_errors": [] if parse_status == "valid" else ["failed"],
            "representation_gaps": [],
        }
    )


def test_efficiency_aggregates_first_pass_parse_latency_and_tokens() -> None:
    attempts = [
        attempt("A", sample_id="AMR-S001", parse_status="invalid", latency_ms=100),
        attempt("A", sample_id="AMR-S001", attempt_number=2, latency_ms=80),
        attempt("A", sample_id="AMR-S002", latency_ms=120),
    ]

    result = aggregate_efficiency(attempts, "A", expected_samples=2)

    assert result.first_pass_parse_rate == pytest.approx(0.5)
    assert result.final_parse_count == 2
    assert result.latency_ms == 300
    assert result.total_tokens == 45
    assert result.usage_status == "measured"


def test_route_b_end_to_end_includes_route_c_cost() -> None:
    attempts = [attempt("C", latency_ms=100), attempt("B", latency_ms=200)]

    result = aggregate_efficiency(attempts, "B", expected_samples=1)

    assert result.latency_ms == 300
    assert result.total_tokens == 30


def test_unavailable_usage_makes_token_and_cost_comparison_undecidable() -> None:
    baseline = aggregate_efficiency([attempt("C")], "C", expected_samples=1)
    candidate = aggregate_efficiency(
        [attempt("A", input_tokens=None, output_tokens=None)],
        "A",
        expected_samples=1,
    )

    comparison = compare_efficiency(candidate, baseline)

    assert candidate.usage_status == "unavailable"
    assert candidate.total_tokens is None
    assert comparison.token_ratio is None
    assert comparison.cost_ratio is None
    assert comparison.token_status == "undecidable"
    assert comparison.cost_status == "undecidable"


def test_unavailable_latency_makes_latency_comparison_undecidable() -> None:
    baseline = aggregate_efficiency([attempt("C")], "C", expected_samples=1)
    candidate = aggregate_efficiency(
        [attempt("A", latency_ms=None)],
        "A",
        expected_samples=1,
    )

    comparison = compare_efficiency(candidate, baseline)

    assert candidate.latency_status == "unavailable"
    assert candidate.latency_ms is None
    assert comparison.latency_ratio is None
