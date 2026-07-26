from __future__ import annotations

from dataclasses import dataclass

from ke_memory_demo.domain import KnowledgeEquation, Modality, Speaker

from .models import (
    AdmissionAssessment,
    AdmissionStatus,
    MemoryKind,
    SourceStatus,
)


@dataclass(frozen=True)
class _SourceRule:
    source_status: SourceStatus
    epistemic_trust: float


_SOURCE_RULES = {
    Speaker.USER: _SourceRule(SourceStatus.USER_REPORTED, 0.75),
    Speaker.ASSISTANT: _SourceRule(SourceStatus.AGENT_GENERATED, 0.3),
    Speaker.TOOL: _SourceRule(SourceStatus.TOOL_OBSERVED, 0.95),
    Speaker.DERIVED: _SourceRule(SourceStatus.DERIVED, 0.6),
}

_KIND_BY_MODALITY = {
    Modality.PREFERENCE: MemoryKind.PREFERENCE,
    Modality.GOAL: MemoryKind.TASK,
    Modality.PLAN: MemoryKind.TASK,
    Modality.INSTRUCTION: MemoryKind.CONSTRAINT,
    Modality.FACT: MemoryKind.FACT,
    Modality.BELIEF: MemoryKind.FACT,
    Modality.HYPOTHESIS: MemoryKind.OTHER,
    Modality.QUESTION: MemoryKind.OTHER,
}

_UTILITY_BY_KIND = {
    MemoryKind.PREFERENCE: 0.9,
    MemoryKind.TASK: 0.95,
    MemoryKind.STATE: 0.85,
    MemoryKind.CONSTRAINT: 0.9,
    MemoryKind.PROCEDURE: 0.85,
    MemoryKind.FACT: 0.7,
    MemoryKind.OTHER: 0.2,
}


class AdmissionPolicy:
    """Deterministic first gate for durable online memory."""

    def __init__(self, *, minimum_extraction_confidence: float = 0.6) -> None:
        if not 0 <= minimum_extraction_confidence <= 1:
            raise ValueError("minimum_extraction_confidence must be between 0 and 1")
        self._minimum_extraction_confidence = minimum_extraction_confidence

    def assess(self, equation: KnowledgeEquation) -> AdmissionAssessment:
        source_rule = _SOURCE_RULES[equation.speaker]
        memory_kind = self._memory_kind(equation)
        utility = _UTILITY_BY_KIND[memory_kind]

        if equation.modality in {Modality.QUESTION, Modality.HYPOTHESIS}:
            return self._assessment(
                equation,
                status=AdmissionStatus.REJECTED,
                memory_kind=MemoryKind.OTHER,
                source_rule=source_rule,
                utility=utility,
                reason="question-or-hypothesis-is-not-durable-memory",
            )

        if equation.confidence < self._minimum_extraction_confidence:
            return self._assessment(
                equation,
                status=AdmissionStatus.CANDIDATE,
                memory_kind=memory_kind,
                source_rule=source_rule,
                utility=utility,
                reason="extraction-confidence-below-admission-threshold",
            )

        if equation.speaker is Speaker.ASSISTANT:
            return self._assessment(
                equation,
                status=AdmissionStatus.CANDIDATE,
                memory_kind=memory_kind,
                source_rule=source_rule,
                utility=utility,
                reason="agent-generated-fact-requires-confirmation",
            )

        reason = {
            MemoryKind.PREFERENCE: "durable-user-preference",
            MemoryKind.TASK: "durable-user-task",
            MemoryKind.STATE: "tool-observed-state",
            MemoryKind.CONSTRAINT: "durable-user-constraint",
            MemoryKind.PROCEDURE: "durable-procedure",
            MemoryKind.FACT: "sufficiently-supported-fact",
            MemoryKind.OTHER: "durable-memory",
        }[memory_kind]
        return self._assessment(
            equation,
            status=AdmissionStatus.ADMITTED,
            memory_kind=memory_kind,
            source_rule=source_rule,
            utility=utility,
            reason=reason,
        )

    @staticmethod
    def _memory_kind(equation: KnowledgeEquation) -> MemoryKind:
        if equation.speaker is Speaker.TOOL and equation.modality is Modality.FACT:
            return MemoryKind.STATE
        return _KIND_BY_MODALITY[equation.modality]

    @staticmethod
    def _assessment(
        equation: KnowledgeEquation,
        *,
        status: AdmissionStatus,
        memory_kind: MemoryKind,
        source_rule: _SourceRule,
        utility: float,
        reason: str,
    ) -> AdmissionAssessment:
        return AdmissionAssessment(
            status=status,
            memory_kind=memory_kind,
            source_status=source_rule.source_status,
            extraction_confidence=equation.confidence,
            epistemic_trust=source_rule.epistemic_trust,
            memory_utility=utility,
            reasons=(reason,),
        )
