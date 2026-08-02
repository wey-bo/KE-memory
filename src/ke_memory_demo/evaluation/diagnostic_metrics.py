"""Diagnostic metrics added for diagnostic-v1.

These sit alongside the existing ``QuestionMetrics`` rather than replacing it. Prior
BEAM results were computed with those fields, so redefining any of them would silently
change what an old number meant; everything here is new and additive.

Definitions worth stating precisely, because loose versions of them hide failures:

- Evidence Set Exact Match is set equality, not overlap. Extra evidence fails it.
- All-Evidence at K asks whether the complete gold set appears within the first K
  selections, which is what a downstream answer actually needs.
- Constraint satisfaction is only meaningful when a question states constraints, so it
  is ``None`` rather than ``1.0`` when none exist. Scoring "no constraints" as perfect
  would inflate the average with unearned credit.
- The answer-evidence matrix keeps answer correctness and evidence correctness
  separate, so a right answer built on wrong evidence stays visible.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

NonEmptyString = Annotated[str, Field(min_length=1)]


class AnswerEvidenceCell(StrEnum):
    """The four cells the plan requires be reported separately."""

    ANSWER_CORRECT_EVIDENCE_CORRECT = "answer_correct_evidence_correct"
    ANSWER_CORRECT_EVIDENCE_WRONG = "answer_correct_evidence_wrong"
    ANSWER_WRONG_EVIDENCE_CORRECT = "answer_wrong_evidence_correct"
    ANSWER_WRONG_EVIDENCE_WRONG = "answer_wrong_evidence_wrong"


class _Record(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class DiagnosticQuestionMetrics(_Record):
    """Per-question diagnostic metrics, additive to QuestionMetrics.

    Selection and delivery are scored separately throughout. Reporting only one figure
    conflates "chose the wrong evidence" with "chose correctly but could not deliver it
    within the budget", which are different defects with different owners.
    """

    question_id: NonEmptyString
    selection_evidence_set_exact_match: bool
    delivery_evidence_set_exact_match: bool
    all_evidence_at_k: bool
    k: int
    selection_evidence_recall: float
    selection_evidence_precision: float
    delivery_evidence_recall: float
    delivery_evidence_precision: float
    budget_limited: bool
    constraint_satisfaction: float | None
    answer_correct: bool | None
    answer_evidence_cell: AnswerEvidenceCell | None
    abstention_expected: bool
    abstention_taken: bool
    abstention_correct: bool | None
    critical_false_positive: bool | None


def evidence_set_exact_match(
    selected: Sequence[str],
    gold: Sequence[str],
) -> bool:
    """Set equality between selected and gold evidence."""
    return set(selected) == set(gold)


def all_evidence_at_k(
    selected: Sequence[str],
    gold: Sequence[str],
    k: int,
) -> bool:
    """Whether the complete gold set appears within the first ``k`` selections."""
    if k <= 0:
        raise ValueError("k must be positive")
    if not gold:
        # No gold evidence means nothing to recover; an empty selection satisfies it.
        return not set(selected[:k])
    return set(gold).issubset(set(selected[:k]))


def evidence_recall(selected: Sequence[str], gold: Sequence[str]) -> float:
    if not gold:
        return 1.0 if not set(selected) else 0.0
    found = len(set(gold) & set(selected))
    return found / len(set(gold))


def evidence_precision(selected: Sequence[str], gold: Sequence[str]) -> float:
    if not selected:
        return 1.0 if not set(gold) else 0.0
    correct = len(set(gold) & set(selected))
    return correct / len(set(selected))


def constraint_satisfaction(
    satisfied_constraints: int,
    total_constraints: int,
) -> float | None:
    """Fraction of stated constraints satisfied, or ``None`` when none were stated."""
    if total_constraints < 0 or satisfied_constraints < 0:
        raise ValueError("constraint counts cannot be negative")
    if satisfied_constraints > total_constraints:
        raise ValueError("satisfied constraints cannot exceed total constraints")
    if total_constraints == 0:
        return None
    return satisfied_constraints / total_constraints


def answer_evidence_cell(
    *,
    answer_correct: bool,
    evidence_correct: bool,
) -> AnswerEvidenceCell:
    if answer_correct and evidence_correct:
        return AnswerEvidenceCell.ANSWER_CORRECT_EVIDENCE_CORRECT
    if answer_correct:
        return AnswerEvidenceCell.ANSWER_CORRECT_EVIDENCE_WRONG
    if evidence_correct:
        return AnswerEvidenceCell.ANSWER_WRONG_EVIDENCE_CORRECT
    return AnswerEvidenceCell.ANSWER_WRONG_EVIDENCE_WRONG


def is_critical_false_positive(
    *,
    abstention_expected: bool,
    abstained: bool,
    answer_correct: bool,
) -> bool:
    """A confident wrong answer where abstention was required.

    This is the failure that matters most for a memory system: inventing an answer the
    evidence does not support is worse than declining, so it is counted separately
    rather than folded into answer accuracy.
    """
    return abstention_expected and not abstained and not answer_correct


def compute_diagnostic_question_metrics(
    *,
    question_id: str,
    selected_evidence: Sequence[str],
    delivered_evidence: Sequence[str],
    gold_evidence: Sequence[str],
    k: int,
    abstention_expected: bool,
    abstained: bool,
    budget_limited: bool = False,
    answer_correct: bool | None = None,
    satisfied_constraints: int | None = None,
    total_constraints: int = 0,
) -> DiagnosticQuestionMetrics:
    """Score one question.

    ``answer_correct`` and ``satisfied_constraints`` are optional and default to unknown.
    A stub answer model cannot establish either, and recording its output under a formal
    metric name would put a fabricated number into an artifact. Passing zero satisfied
    constraints is not a safer default than passing all of them: both invent a result. So
    when no judge evaluated the rubric, constraint satisfaction is None.
    """
    selection_exact = evidence_set_exact_match(selected_evidence, gold_evidence)
    delivery_exact = evidence_set_exact_match(delivered_evidence, gold_evidence)
    return DiagnosticQuestionMetrics(
        question_id=question_id,
        selection_evidence_set_exact_match=selection_exact,
        delivery_evidence_set_exact_match=delivery_exact,
        all_evidence_at_k=all_evidence_at_k(delivered_evidence, gold_evidence, k),
        k=k,
        selection_evidence_recall=evidence_recall(selected_evidence, gold_evidence),
        selection_evidence_precision=evidence_precision(selected_evidence, gold_evidence),
        delivery_evidence_recall=evidence_recall(delivered_evidence, gold_evidence),
        delivery_evidence_precision=evidence_precision(delivered_evidence, gold_evidence),
        budget_limited=budget_limited,
        constraint_satisfaction=(
            constraint_satisfaction(satisfied_constraints, total_constraints)
            if satisfied_constraints is not None
            else None
        ),
        answer_correct=answer_correct,
        answer_evidence_cell=(
            answer_evidence_cell(
                answer_correct=answer_correct,
                evidence_correct=delivery_exact,
            )
            if answer_correct is not None
            else None
        ),
        abstention_expected=abstention_expected,
        abstention_taken=abstained,
        # Whether declining was correct is only knowable once an answer has been judged:
        # a stub that abstains because it received no evidence has not demonstrated
        # correct abstention behaviour.
        abstention_correct=(
            abstention_expected == abstained if answer_correct is not None else None
        ),
        critical_false_positive=(
            is_critical_false_positive(
                abstention_expected=abstention_expected,
                abstained=abstained,
                answer_correct=answer_correct,
            )
            if answer_correct is not None
            else None
        ),
    )


class AnswerEvidenceMatrix(_Record):
    """Counts per cell, plus the disagreement rate that motivates reporting it."""

    answer_correct_evidence_correct: int = 0
    answer_correct_evidence_wrong: int = 0
    answer_wrong_evidence_correct: int = 0
    answer_wrong_evidence_wrong: int = 0

    @property
    def total(self) -> int:
        return (
            self.answer_correct_evidence_correct
            + self.answer_correct_evidence_wrong
            + self.answer_wrong_evidence_correct
            + self.answer_wrong_evidence_wrong
        )

    @property
    def answer_correct_on_wrong_evidence_rate(self) -> float | None:
        """How often a correct answer rests on wrong evidence.

        The headline risk in a memory benchmark: a system can look accurate while its
        retrieval is broken, and averaging answer accuracy alone conceals that.
        """
        correct = self.answer_correct_evidence_correct + self.answer_correct_evidence_wrong
        if correct == 0:
            return None
        return self.answer_correct_evidence_wrong / correct


def build_answer_evidence_matrix(
    metrics: Sequence[DiagnosticQuestionMetrics],
) -> AnswerEvidenceMatrix:
    """Count cells over questions whose answer correctness is actually known.

    Questions with unknown correctness are excluded rather than assumed wrong, so a run
    without a real judge produces an empty matrix instead of a misleading one.
    """
    counts = {cell: 0 for cell in AnswerEvidenceCell}
    for metric in metrics:
        if metric.answer_evidence_cell is not None:
            counts[metric.answer_evidence_cell] += 1
    return AnswerEvidenceMatrix(
        answer_correct_evidence_correct=counts[
            AnswerEvidenceCell.ANSWER_CORRECT_EVIDENCE_CORRECT
        ],
        answer_correct_evidence_wrong=counts[AnswerEvidenceCell.ANSWER_CORRECT_EVIDENCE_WRONG],
        answer_wrong_evidence_correct=counts[AnswerEvidenceCell.ANSWER_WRONG_EVIDENCE_CORRECT],
        answer_wrong_evidence_wrong=counts[AnswerEvidenceCell.ANSWER_WRONG_EVIDENCE_WRONG],
    )


class DiagnosticSummary(_Record):
    """Arm-level rollup. Every rate is reported with its own denominator.

    All questions are retained. An earlier version reported an exact-match rate computed
    after dropping budget-truncated questions, which a review rejected as a headline
    number: excluding the hardest samples flatters the result. Both figures appear here,
    over the full sample, and ``budget_limited_count`` states how many questions could not
    reach delivery exact match at this budget.
    """

    question_count: int
    selection_exact_match_rate: float
    delivery_exact_match_rate: float
    all_evidence_at_k_rate: float
    mean_selection_recall: float
    mean_selection_precision: float
    mean_delivery_recall: float
    mean_delivery_precision: float
    budget_limited_count: int
    constraint_satisfaction_rate: float | None
    constraint_question_count: int
    answer_correct_rate: float | None
    answer_scored_count: int
    abstention_correct_rate: float | None
    critical_false_positive_count: int | None
    matrix: AnswerEvidenceMatrix


def summarize_diagnostics(
    metrics: Sequence[DiagnosticQuestionMetrics],
) -> DiagnosticSummary:
    if not metrics:
        raise ValueError("cannot summarize an empty metric set")
    total = len(metrics)
    constrained = [m for m in metrics if m.constraint_satisfaction is not None]
    answer_scored = [m for m in metrics if m.answer_correct is not None]
    return DiagnosticSummary(
        question_count=total,
        selection_exact_match_rate=sum(
            m.selection_evidence_set_exact_match for m in metrics
        )
        / total,
        delivery_exact_match_rate=sum(m.delivery_evidence_set_exact_match for m in metrics)
        / total,
        all_evidence_at_k_rate=sum(m.all_evidence_at_k for m in metrics) / total,
        mean_selection_recall=sum(m.selection_evidence_recall for m in metrics) / total,
        mean_selection_precision=sum(m.selection_evidence_precision for m in metrics) / total,
        mean_delivery_recall=sum(m.delivery_evidence_recall for m in metrics) / total,
        mean_delivery_precision=sum(m.delivery_evidence_precision for m in metrics) / total,
        budget_limited_count=sum(m.budget_limited for m in metrics),
        constraint_satisfaction_rate=(
            sum(m.constraint_satisfaction or 0.0 for m in constrained) / len(constrained)
            if constrained
            else None
        ),
        constraint_question_count=len(constrained),
        answer_correct_rate=(
            sum(bool(m.answer_correct) for m in answer_scored) / len(answer_scored)
            if answer_scored
            else None
        ),
        answer_scored_count=len(answer_scored),
        abstention_correct_rate=(
            sum(bool(m.abstention_correct) for m in answer_scored) / len(answer_scored)
            if answer_scored
            else None
        ),
        critical_false_positive_count=(
            sum(bool(m.critical_false_positive) for m in answer_scored)
            if answer_scored
            else None
        ),
        matrix=build_answer_evidence_matrix(metrics),
    )
