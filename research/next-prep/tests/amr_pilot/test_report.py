from __future__ import annotations

from tools.amr_pilot.report import build_gate_report, render_report_markdown
from tools.amr_pilot.scoring import EfficiencySummary


def efficiency(
    route: str,
    *,
    latency_ms: int,
    total_tokens: int | None,
    first_pass: float = 1.0,
    final_parses: int = 12,
) -> EfficiencySummary:
    return EfficiencySummary(
        route=route,
        expected_samples=12,
        first_pass_parse_rate=first_pass,
        final_parse_count=final_parses,
        latency_ms=latency_ms,
        usage_status="measured" if total_tokens is not None else "unavailable",
        total_tokens=total_tokens,
        cost_usd=0.12 if total_tokens is not None else None,
    )


def metrics(
    *,
    recall: float,
    precision: float,
    critical_errors: int = 0,
    fixes: dict[str, int] | None = None,
) -> dict[str, object]:
    return {
        "recall": recall,
        "precision": precision,
        "critical_error_count": critical_errors,
        "net_fixes_by_category": fixes or {"negation_modality_intent": 2},
    }


def test_balanced_report_selects_b_when_all_gates_and_improvement_pass() -> None:
    report = build_gate_report(
        route_metrics={
            "C": metrics(recall=0.82, precision=0.96),
            "A": metrics(recall=0.92, precision=0.97),
            "B": metrics(recall=0.98, precision=0.98),
        },
        efficiency={
            "C": efficiency("C", latency_ms=1000, total_tokens=1000),
            "A": efficiency("A", latency_ms=1400, total_tokens=1400, first_pass=11 / 12),
            "B": efficiency("B", latency_ms=2200, total_tokens=2200, first_pass=1.0),
        },
        hard_categories={"negation_modality_intent", "causality_comparison_multiclause"},
    )

    assert report["routes"]["A"]["status"] == "pass"
    assert report["routes"]["B"]["status"] == "pass"
    assert report["decision"] == "select_B"
    assert report["routes"]["A"]["checks"]["first_pass_parse"]["status"] == "pass"


def test_b_is_not_retained_without_five_point_or_two_critical_fix_gain() -> None:
    report = build_gate_report(
        route_metrics={
            "C": metrics(recall=0.82, precision=0.96),
            "A": metrics(recall=0.92, precision=0.96),
            "B": metrics(recall=0.96, precision=0.97),
        },
        efficiency={
            "C": efficiency("C", latency_ms=1000, total_tokens=1000),
            "A": efficiency("A", latency_ms=1200, total_tokens=1200),
            "B": efficiency("B", latency_ms=1800, total_tokens=1800),
        },
        hard_categories={"negation_modality_intent"},
    )

    assert report["routes"]["B"]["checks"]["improvement_over_A"]["status"] == "fail"
    assert report["routes"]["B"]["status"] == "fail"
    assert report["decision"] == "select_A"


def test_missing_usage_makes_efficiency_gate_undecidable() -> None:
    report = build_gate_report(
        route_metrics={
            "C": metrics(recall=0.82, precision=0.96),
            "A": metrics(recall=0.92, precision=0.97),
            "B": metrics(recall=0.98, precision=0.98),
        },
        efficiency={
            "C": efficiency("C", latency_ms=1000, total_tokens=1000),
            "A": efficiency("A", latency_ms=1200, total_tokens=None),
            "B": efficiency("B", latency_ms=1800, total_tokens=None),
        },
        hard_categories={"negation_modality_intent"},
    )

    assert report["routes"]["A"]["checks"]["token_efficiency"]["status"] == "undecidable"
    assert report["routes"]["A"]["status"] == "undecidable"
    assert report["decision"] == "undecidable"


def test_two_fixes_must_be_in_one_predefined_hard_category() -> None:
    report = build_gate_report(
        route_metrics={
            "C": metrics(recall=0.82, precision=0.96),
            "A": metrics(
                recall=0.92,
                precision=0.97,
                fixes={"negation_modality_intent": 1, "causality_comparison_multiclause": 1},
            ),
            "B": metrics(recall=0.80, precision=0.90, fixes={}),
        },
        efficiency={
            "C": efficiency("C", latency_ms=1000, total_tokens=1000),
            "A": efficiency("A", latency_ms=1200, total_tokens=1200),
            "B": efficiency("B", latency_ms=1800, total_tokens=1800),
        },
        hard_categories={"negation_modality_intent", "causality_comparison_multiclause"},
    )

    assert report["routes"]["A"]["checks"]["hard_category_net_fixes"]["status"] == "fail"
    assert report["routes"]["A"]["status"] == "fail"
    assert report["decision"] == "stop"


def test_report_markdown_surfaces_decision_and_undecidable_checks() -> None:
    report = build_gate_report(
        route_metrics={
            "C": metrics(recall=0.82, precision=0.96),
            "A": metrics(recall=0.92, precision=0.97),
            "B": metrics(recall=0.98, precision=0.98),
        },
        efficiency={
            "C": efficiency("C", latency_ms=1000, total_tokens=1000),
            "A": efficiency("A", latency_ms=1200, total_tokens=None),
            "B": efficiency("B", latency_ms=1800, total_tokens=None),
        },
        hard_categories={"negation_modality_intent"},
    )

    markdown = render_report_markdown(report)

    assert "Decision: undecidable" in markdown
    assert "token_efficiency" in markdown
    assert "undecidable" in markdown
