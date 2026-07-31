"""Phase C scoring: the same grounding production uses, counted separately.

Attempt 2 failed because the modality guard lived only at the producer boundary,
which Phase C never invokes. The guard is imported here rather than reimplemented,
so the qualification path and the write path cannot drift: a second
implementation would be free to disagree with the first, which is the situation
that produced the failure.

The gate and the raw model are reported separately and both must be clean. A model
that emits a fact the evidence does not support, and is then stopped by the gate,
is not a model that read the evidence correctly — and Phase C measures raw
extraction quality. So ``qualified`` requires raw accuracy with no fabrication
*and* zero gate interventions; a green gated column can never carry the verdict on
its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from .e2e_openai_producers import _conditions_the_claim

#: 与 production 共用同一实现。测试断言二者是同一个对象，因此不可能各自漂移。
MODALITY_GROUNDING_IMPLEMENTATION = _conditions_the_claim

GateReason = Literal["modality_not_grounded", "modality_not_authorized"]


@dataclass(frozen=True)
class GateOutcome:
    """What the raw model said, what the gate did, and why."""

    raw_decision: str
    raw_modality: str | None
    gated_decision: str
    gate_intervened: bool
    gate_reason: GateReason | None


def apply_gate(
    *,
    evidence_quote: str,
    raw_decision: str,
    raw_modality: str | None,
    policy: Any,
) -> GateOutcome:
    """Apply the write-path modality rules to a raw proposal.

    Only emissions can be gated: a refusal cannot assert anything false, so
    intervening on one would invent a disagreement.
    """
    if raw_decision not in ("emit_l1", "emit_l2"):
        return GateOutcome(
            raw_decision=raw_decision,
            raw_modality=raw_modality,
            gated_decision=raw_decision,
            gate_intervened=False,
            gate_reason=None,
        )
    authorized = {item.modality for item in policy.modality_time_policies}
    reason: GateReason | None = None
    if raw_modality is not None and raw_modality not in authorized:
        reason = "modality_not_authorized"
    elif raw_modality == "actual" and MODALITY_GROUNDING_IMPLEMENTATION(
        evidence_quote
    ):
        # 被条件从句限定的事实尚未成立，记成 actual 就是断言原文没说的事。
        reason = "modality_not_grounded"
    if reason is None:
        return GateOutcome(
            raw_decision=raw_decision,
            raw_modality=raw_modality,
            gated_decision=raw_decision,
            gate_intervened=False,
            gate_reason=None,
        )
    return GateOutcome(
        raw_decision=raw_decision,
        raw_modality=raw_modality,
        gated_decision="abstain",
        gate_intervened=True,
        gate_reason=reason,
    )


def score_layer(*, cases: list[dict[str, Any]], policy: Any) -> dict[str, Any]:
    """Score one layer, keeping raw and gated results apart.

    Every count here is measured from the raw proposals. The gated column is
    reported alongside so a reader can see what the program stopped, never
    instead of what the model actually did.
    """
    from .operational_profile_fresh_authoring import classify_emission_outcome

    total = len(cases)
    if total == 0:
        raise ValueError("scoring requires at least one case")

    raw_correct = 0
    gated_correct = 0
    raw_false_emissions = 0
    scope_disagreements = 0
    convention_disagreements = 0
    interventions: list[dict[str, Any]] = []
    raw_errors: list[dict[str, Any]] = []

    for case in cases:
        expected = case["expected_decision"]
        raw_decision = case["raw_decision"]
        raw_modality = case.get("raw_modality")
        outcome = apply_gate(
            evidence_quote=case["evidence_quote"],
            raw_decision=raw_decision,
            raw_modality=raw_modality,
            policy=policy,
        )
        if raw_decision == expected:
            raw_correct += 1
        if outcome.gated_decision == expected:
            gated_correct += 1
        if outcome.gate_intervened:
            interventions.append(
                {
                    "knowledge_id": case["knowledge_id"],
                    "raw_decision": raw_decision,
                    "raw_modality": raw_modality,
                    "gate_reason": outcome.gate_reason,
                }
            )
        classification = classify_emission_outcome(
            expected_decision=expected,
            observed_decision=raw_decision,
            observed_modality=raw_modality,
            policy=policy,
        )
        if classification == "raw_semantic_false_emission":
            raw_false_emissions += 1
            raw_errors.append(
                {
                    "knowledge_id": case["knowledge_id"],
                    "expected_decision": expected,
                    "raw_decision": raw_decision,
                    "raw_modality": raw_modality,
                    "taxonomy": classification,
                }
            )
        elif classification == "policy_scope_disagreement":
            scope_disagreements += 1
        elif classification in ("convention_disagreement", "reported_mismatch"):
            convention_disagreements += 1
        elif classification != "match":
            raise ValueError(f"unhandled classification: {classification}")

    # 约定标签分歧不否决资格，但真实错误与 gate 拦截都会。
    raw_ready = raw_false_emissions == 0 and (
        raw_correct + convention_disagreements + scope_disagreements == total
    )
    return {
        "case_count": total,
        "raw_decision_accuracy": raw_correct / total,
        "gated_decision_accuracy": gated_correct / total,
        "raw_semantic_false_emission_count": raw_false_emissions,
        "policy_scope_disagreement_count": scope_disagreements,
        "convention_disagreement_count": convention_disagreements,
        "gate_intervention_count": len(interventions),
        "gate_interventions": interventions,
        "raw_errors": raw_errors,
        "raw_ready": raw_ready,
        # 通过必须同时满足：raw 全绿，且程序一次都没有出手。
        "qualified": raw_ready and len(interventions) == 0,
        "reporting_rule": (
            "gate interventions are reported separately and never substitute for "
            "raw model correctness"
        ),
    }
