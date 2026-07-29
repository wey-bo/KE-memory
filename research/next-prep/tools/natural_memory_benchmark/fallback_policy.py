from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal


FallbackDecision = Literal["not_needed", "triggered", "blocked"]


_TEMPORAL_OR_CONFLICT_GROUPS = {
    "contradiction_resolution",
    "knowledge_update",
    "temporal_reasoning",
    "temporal-reasoning",
}

_STRUCTURAL_CUE_PATTERN = re.compile(
    r"\b(before|after|first|last|latest|earlier|later|still|not|never|no longer|changed|updated|contradict|conflict|instead|rather than)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class FallbackPolicy:
    decision: FallbackDecision
    reason_candidate: str
    allowed: bool

    def metadata(self) -> dict[str, Any]:
        return {
            "fallback_decision": self.decision,
            "fallback_reason_candidate": self.reason_candidate,
            "fallback_allowed": self.allowed,
        }


def classify_fallback(public_item: dict[str, Any], symbolic_item: dict[str, Any]) -> FallbackPolicy:
    if symbolic_item.get("retrieved_evidence_refs"):
        return FallbackPolicy(
            decision="not_needed",
            reason_candidate="symbolic_nonempty",
            allowed=False,
        )

    slice_group = str(public_item.get("slice_group", ""))
    question = str(public_item.get("question", ""))
    if slice_group == "abstention":
        return FallbackPolicy(
            decision="blocked",
            reason_candidate="abstention_or_answerability_missing",
            allowed=False,
        )

    if slice_group in _TEMPORAL_OR_CONFLICT_GROUPS or _STRUCTURAL_CUE_PATTERN.search(question):
        reason = "temporal_negation_modality_conflict_mismatch" if slice_group in {"temporal_reasoning", "temporal-reasoning"} else "structural_reasoning_failure"
        return FallbackPolicy(
            decision="blocked",
            reason_candidate=reason,
            allowed=False,
        )

    return FallbackPolicy(
        decision="triggered",
        reason_candidate="lexical_predicate_missing_link",
        allowed=True,
    )
