from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal


AnswerabilityDecisionValue = Literal["not_applicable", "supported", "blocked"]


_CAUSAL_QUESTION_PATTERN = re.compile(
    r"\b(why|how|influence|influenced|affect|affected|impact|impacted|cause|caused|because|based on)\b|\b(leads?|led)\s+to\b",
    re.IGNORECASE,
)
_CHANGE_DETAIL_PATTERN = re.compile(
    r"\b(changed|added|removed|simplified|redesigned|reworked|fixed|updated|prioritized|implemented|moved|split|renamed|reduced|increased)\b",
    re.IGNORECASE,
)
_FEEDBACK_OBSERVATION_PATTERN = re.compile(
    r"\bfeedback\b.{0,120}\b(showed|revealed|reported|identified|pointed out|indicated|requested|asked|complained|highlighted)\b",
    re.IGNORECASE | re.DOTALL,
)
_CAUSAL_MARKER_PATTERN = re.compile(
    r"\b(because|therefore|so|as a result|which led to|led to|caused|prompted|due to|in response to)\b",
    re.IGNORECASE,
)
_BASED_ON_FEEDBACK_CHANGE_PATTERN = re.compile(
    r"\b(based on|after|from|in response to)\b.{0,40}\bfeedback\b.{0,120}\b(changed|added|removed|simplified|redesigned|reworked|fixed|updated|prioritized|implemented|moved|split|renamed|reduced|increased)\b",
    re.IGNORECASE | re.DOTALL,
)


@dataclass(frozen=True)
class AnswerabilityDecision:
    decision: AnswerabilityDecisionValue
    reason: str
    answerable: bool
    supporting_cues: tuple[str, ...] = ()

    def metadata(self) -> dict[str, Any]:
        return {
            "answerability_policy": "causal_gate_v1",
            "answerability_decision": self.decision,
            "answerability_reason": self.reason,
            "answerability_supporting_cues": list(self.supporting_cues),
        }


def _is_causal_question(question: str) -> bool:
    lowered = question.casefold()
    if not _CAUSAL_QUESTION_PATTERN.search(question):
        return False
    if lowered.startswith(("how many ", "how much ", "how old ", "how long ")):
        return False
    if "how " in lowered and (
        any(term in lowered for term in ("influence", "affect", "impact", "cause", "because", "based on"))
        or re.search(r"\b(leads?|led)\s+to\b", lowered)
    ):
        return True
    if lowered.startswith("why ") or "what led to" in lowered or "what caused" in lowered:
        return True
    return any(term in lowered for term in ("influenced", "affected", "impacted", "because", "based on")) or bool(
        re.search(r"\b(leads?|led)\s+to\b", lowered)
    )


def _supporting_cues(text: str) -> tuple[str, ...]:
    cues: list[str] = []
    has_change_detail = bool(_CHANGE_DETAIL_PATTERN.search(text))
    if _CAUSAL_MARKER_PATTERN.search(text):
        cues.append("explicit_causal_marker")
    if _FEEDBACK_OBSERVATION_PATTERN.search(text):
        cues.append("feedback_observation")
    if _BASED_ON_FEEDBACK_CHANGE_PATTERN.search(text):
        cues.append("feedback_to_change")
    if has_change_detail:
        cues.append("change_detail")

    cue_set = set(cues)
    supported = (
        {"explicit_causal_marker", "change_detail"}.issubset(cue_set)
        and ("feedback_observation" in cue_set or "feedback" not in text.casefold())
    ) or "feedback_to_change" in cue_set
    if not supported:
        return ()
    return tuple(dict.fromkeys(cues))


def assess_answerability(public_item: dict[str, Any], evidence_units: list[dict[str, Any]]) -> AnswerabilityDecision:
    question = str(public_item.get("question", ""))
    if not _is_causal_question(question):
        return AnswerabilityDecision(
            decision="not_applicable",
            reason="not_causal_question",
            answerable=True,
        )

    if not evidence_units:
        return AnswerabilityDecision(
            decision="blocked",
            reason="no_candidate_evidence",
            answerable=False,
        )

    combined_text = "\n".join(str(unit.get("text", "")) for unit in evidence_units)
    cues = _supporting_cues(combined_text)
    if cues:
        return AnswerabilityDecision(
            decision="supported",
            reason="causal_support_present",
            answerable=True,
            supporting_cues=cues,
        )

    return AnswerabilityDecision(
        decision="blocked",
        reason="causal_relation_missing",
        answerable=False,
    )
