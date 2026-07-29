"""Approved six-gate decision logic for the ontology-memory pilot."""

from __future__ import annotations

from typing import Any


DENSE_ARMS = ("B0", "B1", "B2")
STRUCTURAL_FAMILIES = (
    "roles_polarity_modality_quantity",
    "temporal_updates_conflicts_provenance",
    "conjunction_exact_set_multihop",
    # Backward-compatible aliases used by early hand-computed fixtures.
    "roles",
    "polarity",
    "quantity",
    "temporal",
    "multi_constraint",
)
LEXICAL_FAMILIES = (
    "synonymy_sense_external_unanswerable",
    "lexical",
    "out_of_domain",
)


def _section(
    metrics: dict[str, Any], track: str, arm: str, location: str
) -> dict[str, Any] | None:
    value: Any = metrics.get("arms", {}).get(track, {}).get(arm)
    if not isinstance(value, dict):
        return None
    for part in location.split("."):
        value = value.get(part) if isinstance(value, dict) else None
    return value if isinstance(value, dict) else None


def _metric(
    metrics: dict[str, Any],
    track: str,
    arm: str,
    location: str,
    metric: str,
) -> float | None:
    section = _section(metrics, track, arm, location)
    if section is None:
        return None
    if section.get("comparison_eligible") is False:
        return None
    if int(section.get("execution_error_count", 0) or 0) > 0:
        return None
    value = section.get(metric)
    return float(value) if isinstance(value, (int, float)) else None


def _dense_baseline(metrics: dict[str, Any]) -> tuple[str | None, list[str]]:
    candidates: list[tuple[float, int, str]] = []
    reasons: list[str] = []
    oracle_arms = metrics.get("arms", {}).get("oracle", {})
    for index, arm in enumerate(DENSE_ARMS):
        if arm not in oracle_arms:
            reasons.append(f"missing oracle/{arm}")
            continue
        exact = _metric(
            metrics,
            "oracle",
            arm,
            "overall",
            "evidence_set_exact_match",
        )
        if exact is None:
            reasons.append(f"oracle/{arm} overall exact match is unavailable")
            continue
        candidates.append((exact, index, arm))
    if reasons or len(candidates) != len(DENSE_ARMS):
        return None, reasons
    # Primary-metric ties resolve toward the higher-capacity dense arm.
    return max(candidates)[2], []


def _gate(name: str, status: str, detail: str) -> dict[str, str]:
    return {"name": name, "status": status, "detail": detail}


def _structural_gate(
    metrics: dict[str, Any], dense_arm: str | None
) -> dict[str, str]:
    if dense_arm is None:
        return _gate(
            "structural_exact_match",
            "undecidable",
            "all B0/B1/B2 oracle metrics are required to select the strong dense baseline",
        )
    passes = 0
    undecidable = 0
    considered = 0
    for family in STRUCTURAL_FAMILIES:
        family_present = any(
            _section(metrics, "oracle", arm, f"families.{family}") is not None
            for arm in (dense_arm, "O-", "O+")
        )
        if not family_present:
            continue
        considered += 1
        oplus = _metric(
            metrics,
            "oracle",
            "O+",
            f"families.{family}",
            "evidence_set_exact_match",
        )
        dense = _metric(
            metrics,
            "oracle",
            dense_arm,
            f"families.{family}",
            "evidence_set_exact_match",
        )
        omin = _metric(
            metrics,
            "oracle",
            "O-",
            f"families.{family}",
            "evidence_set_exact_match",
        )
        if None in (oplus, dense, omin):
            undecidable += 1
        elif oplus - dense >= 0.15 and oplus - omin >= 0.15:
            passes += 1
    if passes >= 2:
        status = "pass"
    elif passes + undecidable < 2:
        status = "fail"
    else:
        status = "undecidable"
    return _gate(
        "structural_exact_match",
        status,
        (
            f"{passes} of {considered} structural families meet both +15pp "
            f"comparisons against {dense_arm} and O-; {undecidable} unavailable"
        ),
    )


def _critical_fp_gate(
    metrics: dict[str, Any], dense_arm: str | None
) -> dict[str, str]:
    name = "critical_false_positive_reduction"
    if dense_arm is None:
        return _gate(
            name,
            "undecidable",
            "strong dense baseline could not be selected",
        )
    arms = (dense_arm, "O-", "O+")
    rates = {
        arm: _metric(
            metrics,
            "oracle",
            arm,
            "overall",
            "critical_false_positive_rate",
        )
        for arm in arms
    }
    denominators = {
        arm: _metric(
            metrics,
            "oracle",
            arm,
            "overall",
            "critical_false_positive_denominator",
        )
        for arm in arms
    }
    if any(value is None or value <= 0 for value in denominators.values()):
        return _gate(
            name,
            "undecidable",
            (
                "critical false-positive comparison requires non-zero, "
                f"error-free denominators for {dense_arm}, O-, and O+"
            ),
        )
    if any(value is None for value in rates.values()):
        return _gate(
            name,
            "undecidable",
            "critical false-positive rates are missing or error-contaminated",
        )
    oplus = rates["O+"]
    passed = (
        oplus <= 0.5 * rates[dense_arm]
        and oplus <= 0.5 * rates["O-"]
    )
    return _gate(
        name,
        "pass" if passed else "fail",
        f"O+ CFPR is compared with the same {dense_arm} baseline and O-",
    )


def _scale_gate(
    metrics: dict[str, Any], dense_arm: str | None
) -> dict[str, str]:
    name = "distractor_500"
    if dense_arm is None:
        return _gate(
            name,
            "undecidable",
            "strong dense baseline could not be selected",
        )
    oplus = _metric(
        metrics,
        "oracle",
        "O+",
        "scales.500",
        "evidence_set_exact_match",
    )
    dense = _metric(
        metrics,
        "oracle",
        dense_arm,
        "scales.500",
        "evidence_set_exact_match",
    )
    if oplus is None or dense is None:
        return _gate(
            name,
            "undecidable",
            "500-distractor exact match is missing or error-contaminated",
        )
    return _gate(
        name,
        "pass" if oplus - dense >= 0.15 else "fail",
        f"O+ gain over {dense_arm} at 500 distractors is {oplus - dense}",
    )


def _retained_gain_gate(
    metrics: dict[str, Any], dense_arm: str | None
) -> dict[str, str]:
    name = "automatic_retained_gain"
    if dense_arm is None:
        return _gate(
            name,
            "undecidable",
            "strong dense baseline could not be selected",
        )
    oracle_oplus = _metric(
        metrics, "oracle", "O+", "overall", "evidence_set_exact_match"
    )
    oracle_dense = _metric(
        metrics,
        "oracle",
        dense_arm,
        "overall",
        "evidence_set_exact_match",
    )
    auto_oplus = _metric(
        metrics, "automatic", "O+", "overall", "evidence_set_exact_match"
    )
    auto_dense = _metric(
        metrics,
        "automatic",
        dense_arm,
        "overall",
        "evidence_set_exact_match",
    )
    if None in (oracle_oplus, oracle_dense, auto_oplus, auto_dense):
        return _gate(
            name,
            "undecidable",
            (
                f"oracle and automatic O+/{dense_arm} metrics must all be "
                "present and error-free"
            ),
        )
    oracle_gain = oracle_oplus - oracle_dense
    if oracle_gain == 0:
        return _gate(
            name,
            "undecidable",
            "oracle gain denominator is zero",
        )
    retained = (auto_oplus - auto_dense) / oracle_gain
    return _gate(
        name,
        "pass" if oracle_gain > 0 and retained >= 0.70 else "fail",
        f"retained gain against {dense_arm} is {retained}",
    )


def _lexical_gate(
    metrics: dict[str, Any], dense_arm: str | None
) -> dict[str, str]:
    name = "lexical_recall"
    if dense_arm is None:
        return _gate(
            name,
            "undecidable",
            "strong dense baseline could not be selected",
        )
    checks: list[bool] = []
    unavailable = 0
    for family in LEXICAL_FAMILIES:
        family_present = any(
            _section(metrics, "oracle", arm, f"families.{family}") is not None
            for arm in (dense_arm, "O+E")
        )
        if not family_present:
            continue
        recovered = _metric(
            metrics,
            "oracle",
            "O+E",
            f"families.{family}",
            "recall_at_k",
        )
        dense = _metric(
            metrics,
            "oracle",
            dense_arm,
            f"families.{family}",
            "recall_at_k",
        )
        if recovered is None or dense is None:
            unavailable += 1
        else:
            checks.append(recovered >= dense - 0.03)
    if unavailable or not checks:
        return _gate(
            name,
            "undecidable",
            (
                f"lexical/OOD recall against {dense_arm} has "
                f"{unavailable} unavailable slices"
            ),
        )
    return _gate(
        name,
        "pass" if all(checks) else "fail",
        f"O+E recall is within 3pp of {dense_arm} on all lexical/OOD slices",
    )


def _fallback_gate(metrics: dict[str, Any]) -> dict[str, str]:
    name = "fallback_limits"
    fallback = metrics.get("fallback", {})
    overall = fallback.get("overall_rate")
    structural = fallback.get("structural_family_rate")
    if (
        not isinstance(overall, (int, float))
        or not isinstance(structural, (int, float))
        or int(fallback.get("execution_error_count", 0) or 0) > 0
    ):
        return _gate(
            name,
            "undecidable",
            "fallback rates are missing or error-contaminated",
        )
    return _gate(
        name,
        "pass" if overall < 0.30 and structural < 0.10 else "fail",
        "fallback stays below overall and structural limits",
    )


def build_gate_report(metrics: dict[str, Any]) -> dict[str, Any]:
    """Evaluate the six pre-registered gates with independent tri-state results."""
    dense_arm, baseline_reasons = _dense_baseline(metrics)
    gates = [
        _structural_gate(metrics, dense_arm),
        _critical_fp_gate(metrics, dense_arm),
        _scale_gate(metrics, dense_arm),
        _retained_gain_gate(metrics, dense_arm),
        _lexical_gate(metrics, dense_arm),
        _fallback_gate(metrics),
    ]
    statuses = {gate["status"] for gate in gates}
    decision = (
        "fail"
        if "fail" in statuses
        else "undecidable"
        if "undecidable" in statuses
        else "pass"
    )
    reasons = [gate["detail"] for gate in gates if gate["status"] != "pass"]
    reasons.extend(baseline_reasons)
    return {
        "decision": decision,
        "strong_dense_baseline": dense_arm,
        "gates": gates,
        "reasons": reasons,
    }
