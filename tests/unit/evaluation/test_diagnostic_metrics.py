"""Unit tests for the diagnostic metrics.

Expected values are worked out by hand rather than derived from the implementation, so
a change in behaviour shows up as a test failure instead of a silently updated number.
"""

from __future__ import annotations

import math

import pytest

from ke_memory_demo.evaluation.diagnostic_metrics import (
    AnswerEvidenceCell,
    all_evidence_at_k,
    answer_evidence_cell,
    build_answer_evidence_matrix,
    compute_diagnostic_question_metrics,
    constraint_satisfaction,
    evidence_precision,
    evidence_recall,
    evidence_set_exact_match,
    is_critical_false_positive,
    summarize_diagnostics,
)


def approx_equal(actual: float | None, expected: float) -> bool:
    """Typed float comparison.

    pytest.approx is untyped, so each use raises a pyright "partially unknown" error.
    An explicit tolerance check reads the same and keeps the type checker clean.
    """
    return actual is not None and math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-9)


def test_exact_match_is_set_equality_not_overlap() -> None:
    assert evidence_set_exact_match(["a", "b"], ["b", "a"]) is True
    # Superset must fail: extra evidence means the system did not identify the set.
    assert evidence_set_exact_match(["a", "b", "c"], ["a", "b"]) is False
    assert evidence_set_exact_match(["a"], ["a", "b"]) is False
    assert evidence_set_exact_match([], []) is True


def test_all_evidence_at_k_uses_only_the_first_k_selections() -> None:
    selected = ["x", "y", "a", "b"]
    assert all_evidence_at_k(selected, ["a", "b"], 4) is True
    # Gold is present overall but outside the cutoff, which is a miss at k=2.
    assert all_evidence_at_k(selected, ["a", "b"], 2) is False
    # No gold evidence: an empty selection satisfies it, a non-empty one does not.
    assert all_evidence_at_k([], [], 3) is True
    assert all_evidence_at_k(["x"], [], 3) is False
    with pytest.raises(ValueError):
        all_evidence_at_k(["a"], ["a"], 0)


def test_recall_and_precision_hand_checked() -> None:
    # 2 of 3 gold found, 2 of 4 selected correct.
    assert approx_equal(evidence_recall(["a", "b", "z", "w"], ["a", "b", "c"]), 2 / 3)
    assert approx_equal(evidence_precision(["a", "b", "z", "w"], ["a", "b", "c"]), 0.5)
    # Empty gold with empty selection is perfect; with a selection it is zero.
    assert evidence_recall([], []) == 1.0
    assert evidence_precision([], []) == 1.0
    assert evidence_precision(["a"], []) == 0.0


def test_constraint_satisfaction_is_none_when_no_constraints_exist() -> None:
    """Unstated constraints must not be scored as perfect.

    Returning 1.0 here would add unearned credit to every average over questions that
    state no constraints at all.
    """
    assert constraint_satisfaction(0, 0) is None
    assert approx_equal(constraint_satisfaction(1, 2), 0.5)
    assert constraint_satisfaction(3, 3) == 1.0
    with pytest.raises(ValueError):
        constraint_satisfaction(3, 2)
    with pytest.raises(ValueError):
        constraint_satisfaction(-1, 2)


def test_answer_evidence_cells_keep_the_two_axes_separate() -> None:
    assert (
        answer_evidence_cell(answer_correct=True, evidence_correct=False)
        is AnswerEvidenceCell.ANSWER_CORRECT_EVIDENCE_WRONG
    )
    assert (
        answer_evidence_cell(answer_correct=False, evidence_correct=True)
        is AnswerEvidenceCell.ANSWER_WRONG_EVIDENCE_CORRECT
    )


def test_critical_false_positive_only_fires_on_unwarranted_confidence() -> None:
    # Abstention was required, the system answered anyway, and it was wrong.
    assert is_critical_false_positive(
        abstention_expected=True, abstained=False, answer_correct=False
    ) is True
    # Correctly declining is not a critical failure.
    assert is_critical_false_positive(
        abstention_expected=True, abstained=True, answer_correct=False
    ) is False
    # Answering a question that had an answer is not a critical failure.
    assert is_critical_false_positive(
        abstention_expected=False, abstained=False, answer_correct=False
    ) is False


def test_matrix_exposes_correct_answers_built_on_wrong_evidence() -> None:
    metrics = [
        compute_diagnostic_question_metrics(
            question_id="q1",
            selected_evidence=["a"],
            delivered_evidence=["a"],
            gold_evidence=["a"],
            k=5,
            answer_correct=True,
            abstention_expected=False,
            abstained=False,
        ),
        compute_diagnostic_question_metrics(
            question_id="q2",
            selected_evidence=["wrong"],
            delivered_evidence=["wrong"],
            gold_evidence=["b"],
            k=5,
            answer_correct=True,
            abstention_expected=False,
            abstained=False,
        ),
    ]
    matrix = build_answer_evidence_matrix(metrics)
    assert matrix.answer_correct_evidence_correct == 1
    assert matrix.answer_correct_evidence_wrong == 1
    assert matrix.total == 2
    # One of two correct answers rested on wrong evidence.
    assert approx_equal(matrix.answer_correct_on_wrong_evidence_rate, 0.5)


def test_summary_reports_constraint_rate_with_its_own_denominator() -> None:
    metrics = [
        compute_diagnostic_question_metrics(
            question_id="q1",
            selected_evidence=["a"],
            delivered_evidence=["a"],
            gold_evidence=["a"],
            k=3,
            answer_correct=True,
            abstention_expected=False,
            abstained=False,
            satisfied_constraints=1,
            total_constraints=2,
        ),
        compute_diagnostic_question_metrics(
            question_id="q2",
            selected_evidence=[],
            delivered_evidence=[],
            gold_evidence=["b"],
            k=3,
            answer_correct=False,
            abstention_expected=True,
            abstained=False,
        ),
    ]
    summary = summarize_diagnostics(metrics)
    assert summary.question_count == 2
    assert approx_equal(summary.delivery_exact_match_rate, 0.5)
    assert approx_equal(summary.selection_exact_match_rate, 0.5)
    # Only q1 states constraints, so the rate is over one question, not two.
    assert summary.constraint_question_count == 1
    assert approx_equal(summary.constraint_satisfaction_rate, 0.5)
    assert summary.critical_false_positive_count == 1
    assert approx_equal(summary.answer_correct_rate, 0.5)


def test_summary_refuses_an_empty_metric_set() -> None:
    with pytest.raises(ValueError):
        summarize_diagnostics([])
