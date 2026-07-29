"""Balanced go/no-go report for the AMR single-sentence pilot."""

from __future__ import annotations

from typing import Collection, Literal, Mapping

from tools.amr_pilot.scoring import EfficiencySummary, compare_efficiency


GateStatus = Literal["pass", "fail", "undecidable"]


def _check(status: GateStatus, value: object, requirement: str) -> dict[str, object]:
    return {"status": status, "value": value, "requirement": requirement}


def _metric(metrics: Mapping[str, object], key: str) -> float:
    value = metrics.get(key)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"route metric {key} must be numeric")
    return float(value)


def _route_status(checks: Mapping[str, Mapping[str, object]]) -> GateStatus:
    statuses = {check["status"] for check in checks.values()}
    if "fail" in statuses:
        return "fail"
    if "undecidable" in statuses:
        return "undecidable"
    return "pass"


def _hard_fix_check(
    metrics: Mapping[str, object],
    hard_categories: Collection[str],
) -> dict[str, object]:
    fixes = metrics.get("net_fixes_by_category")
    if not isinstance(fixes, dict):
        raise ValueError("net_fixes_by_category must be an object")
    eligible: dict[str, int] = {}
    for category in hard_categories:
        value = fixes.get(category, 0)
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("net fix counts must be integers")
        eligible[category] = value
    best = max(eligible.values(), default=0)
    return _check(
        "pass" if best >= 2 else "fail",
        eligible,
        "at least 2 net fixes in one predefined hard category",
    )


def _candidate_checks(
    route: str,
    metrics: Mapping[str, object],
    summary: EfficiencySummary,
    baseline: EfficiencySummary,
    hard_categories: Collection[str],
) -> dict[str, dict[str, object]]:
    ceiling = 1.5 if route == "A" else 2.5
    comparison = compare_efficiency(summary, baseline)
    recall = _metric(metrics, "recall")
    precision = _metric(metrics, "precision")
    critical_errors = _metric(metrics, "critical_error_count")
    checks = {
        "final_parse_count": _check(
            "pass" if summary.final_parse_count == 12 else "fail",
            summary.final_parse_count,
            "12 final outputs parse or validate",
        ),
        "first_pass_parse": _check(
            "pass" if summary.first_pass_parse_rate + 1e-12 >= 11 / 12 else "fail",
            summary.first_pass_parse_rate,
            "at least 11 of 12 valid on attempt 1",
        ),
        "semantic_recall": _check(
            "pass" if recall + 1e-12 >= 0.90 else "fail",
            recall,
            "weighted recall >= 0.90",
        ),
        "semantic_precision": _check(
            "pass" if precision + 1e-12 >= 0.95 else "fail",
            precision,
            "weighted precision >= 0.95",
        ),
        "critical_errors": _check(
            "pass" if critical_errors == 0 else "fail",
            int(critical_errors),
            "zero unresolved critical errors",
        ),
        "hard_category_net_fixes": _hard_fix_check(metrics, hard_categories),
        "latency_efficiency": _check(
            "undecidable"
            if comparison.latency_ratio is None
            else "pass"
            if comparison.latency_ratio <= ceiling
            else "fail",
            comparison.latency_ratio,
            f"end-to-end latency <= {ceiling}x route C",
        ),
        "token_efficiency": _check(
            "undecidable"
            if comparison.token_ratio is None
            else "pass"
            if comparison.token_ratio <= ceiling
            else "fail",
            comparison.token_ratio,
            f"end-to-end tokens <= {ceiling}x route C",
        ),
    }
    return checks


def _b_improvement_check(
    a_metrics: Mapping[str, object],
    b_metrics: Mapping[str, object],
) -> dict[str, object]:
    recall_delta = _metric(b_metrics, "recall") - _metric(a_metrics, "recall")
    precision_delta = _metric(b_metrics, "precision") - _metric(a_metrics, "precision")
    a_critical = int(_metric(a_metrics, "critical_error_count"))
    b_critical = int(_metric(b_metrics, "critical_error_count"))
    critical_fixed = a_critical - b_critical
    quality_gain = max(recall_delta, precision_delta)
    passed = quality_gain + 1e-12 >= 0.05 or (critical_fixed >= 2 and b_critical <= a_critical)
    return _check(
        "pass" if passed else "fail",
        {
            "recall_delta": recall_delta,
            "precision_delta": precision_delta,
            "critical_errors_fixed": critical_fixed,
        },
        "B gains >= 0.05 quality or fixes >= 2 critical errors without adding a new one",
    )


def build_gate_report(
    *,
    route_metrics: Mapping[str, Mapping[str, object]],
    efficiency: Mapping[str, EfficiencySummary],
    hard_categories: Collection[str],
) -> dict[str, object]:
    if set(route_metrics) != {"A", "B", "C"} or set(efficiency) != {"A", "B", "C"}:
        raise ValueError("route metrics and efficiency must exactly cover A, B, and C")
    if not hard_categories:
        raise ValueError("at least one predefined hard category is required")

    routes: dict[str, dict[str, object]] = {}
    for route in ("A", "B"):
        checks = _candidate_checks(
            route,
            route_metrics[route],
            efficiency[route],
            efficiency["C"],
            hard_categories,
        )
        if route == "B":
            checks["improvement_over_A"] = _b_improvement_check(
                route_metrics["A"], route_metrics["B"]
            )
        routes[route] = {"status": _route_status(checks), "checks": checks}

    if routes["B"]["status"] == "pass":
        decision = "select_B"
    elif routes["A"]["status"] == "pass":
        decision = "select_A"
    elif "undecidable" in {routes["A"]["status"], routes["B"]["status"]}:
        decision = "undecidable"
    else:
        decision = "stop"
    return {
        "schema_version": "amr-pilot-balanced-gate-report-v1",
        "decision": decision,
        "hard_categories": sorted(hard_categories),
        "baseline": {
            "route": "C",
            "recall": _metric(route_metrics["C"], "recall"),
            "precision": _metric(route_metrics["C"], "precision"),
            "latency_ms": efficiency["C"].latency_ms,
            "latency_status": efficiency["C"].latency_status,
            "total_tokens": efficiency["C"].total_tokens,
            "usage_status": efficiency["C"].usage_status,
        },
        "routes": routes,
    }


def render_report_markdown(report: Mapping[str, object]) -> str:
    routes = report.get("routes")
    if not isinstance(routes, dict):
        raise ValueError("report routes are missing")
    lines = [
        "# AMR Single-Sentence Pilot Gate Report",
        "",
        f"Decision: {report.get('decision')}",
        "",
        "| Route | Overall | Check | Status | Value | Requirement |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for route in ("A", "B"):
        route_result = routes.get(route)
        if not isinstance(route_result, dict) or not isinstance(route_result.get("checks"), dict):
            raise ValueError(f"report route {route} is invalid")
        for name, check in route_result["checks"].items():
            lines.append(
                f"| {route} | {route_result.get('status')} | {name} | "
                f"{check.get('status')} | {check.get('value')} | {check.get('requirement')} |"
            )
    return "\n".join(lines) + "\n"
