"""Tests for the discovery data boundaries and the issue-ledger classification.

The classification tests exist because a first run of discovery reported 78 of 79 observations
as extraction failures, and a second reported 243 of 244. Both were classifier defects, not
findings: session-level gold references were compared against turn handles, so every correctly
resolved reference looked absent. A near-total concentration in one class is the signal that
the classifier is wrong, so these tests pin the resolution logic and the ambiguity discipline.
"""

from __future__ import annotations

import pytest

from ke_memory_demo.evaluation.channels import (
    BenchmarkQuestion,
    GoldLabels,
    PublicTurn,
)
from ke_memory_demo.evaluation.data_boundaries import (
    Split,
    SplitError,
    assert_held_out_untouched,
    plan_splits,
)
from ke_memory_demo.evaluation.issue_ledger import (
    CLASS_EVIDENCE_REQUIREMENT,
    IssueClass,
    IssueLedger,
    classify,
)


def _ids(count: int, prefix: str = "q") -> list[str]:
    return [f"{prefix}{index:04d}" for index in range(count)]


def test_splits_are_disjoint_and_exclude_retired_items() -> None:
    excluded = ["q0000", "q0001"]
    plan = plan_splits("corpus", _ids(100), excluded_question_ids=excluded)

    discovery = set(plan.ids_for(Split.DISCOVERY))
    validation = set(plan.ids_for(Split.VALIDATION))
    held_out = set(plan.ids_for(Split.HELD_OUT))

    assert discovery & validation == set()
    assert discovery & held_out == set()
    assert validation & held_out == set()
    assert len(discovery | validation | held_out) == 98
    # The retired slice must not reach any split.
    assert set(excluded) & (discovery | validation | held_out) == set()


def test_the_split_is_reproducible_and_order_independent() -> None:
    """A split that depends on file order cannot be audited later."""
    forward = plan_splits("corpus", _ids(60))
    shuffled = plan_splits("corpus", list(reversed(_ids(60))))
    assert forward.ids_for(Split.DISCOVERY) == shuffled.ids_for(Split.DISCOVERY)
    assert forward.ids_for(Split.HELD_OUT) == shuffled.ids_for(Split.HELD_OUT)


def test_a_different_salt_produces_a_different_split() -> None:
    """The salt is part of the frozen contract, so changing it must be visible."""
    base = plan_splits("corpus", _ids(60))
    other = plan_splits("corpus", _ids(60), salt="different-salt")
    assert base.ids_for(Split.DISCOVERY) != other.ids_for(Split.DISCOVERY)


def test_the_partition_must_leave_a_held_out_set() -> None:
    with pytest.raises(SplitError, match="non-empty held-out"):
        plan_splits("corpus", _ids(50), discovery_fraction=0.8, validation_fraction=0.3)


def test_held_out_inspection_is_caught_mechanically() -> None:
    """Not looking at held-out data must be a checked property, not an intention."""
    plan = plan_splits("corpus", _ids(100))
    assert_held_out_untouched(plan, plan.ids_for(Split.DISCOVERY))
    with pytest.raises(SplitError, match="held-out questions were inspected"):
        assert_held_out_untouched(plan, plan.ids_for(Split.HELD_OUT)[:1])


def _question() -> BenchmarkQuestion:
    return BenchmarkQuestion(
        question_id="q1", conversation_handle="c00000", question="where does the user live"
    )


def _turn(handle: str, text: str = "the user lives in berlin") -> PublicTurn:
    return PublicTurn(
        evidence_handle=handle, speaker="user", text=text, approximate_tokens=6
    )


def _label(refs: tuple[str, ...]) -> GoldLabels:
    return GoldLabels(question_id="q1", conversation_handle="c00000", evidence_refs=refs)


def test_a_session_level_gold_reference_resolves_through_published_membership() -> None:
    """The defect that produced 243 of 244 false extraction failures.

    Opaque handles share no prefix, so a session reference can only be resolved through the
    membership the loader publishes. Without it the reference looks absent and the question is
    misread as an extraction failure.
    """
    turns = [_turn("h00000"), _turn("h00001")]
    members = {"s00000": ["h00000", "h00001"]}

    # Selection matches the session's members exactly, so nothing is wrong.
    assert (
        classify(
            _question(),
            _label(("s00000",)),
            turns,
            ["h00000", "h00001"],
            context_limited=False,
            plan_terms=("berlin",),
            session_members=members,
        )
        is None
    )

    # Without membership the same input is misclassified, which is what happened.
    blind = classify(
        _question(),
        _label(("s00000",)),
        turns,
        ["h00000", "h00001"],
        context_limited=False,
        plan_terms=("berlin",),
        session_members=None,
    )
    assert blind is not None
    assert blind.issue_class is IssueClass.EXTRACTION_STRUCTURAL


def test_context_limit_takes_precedence_over_any_other_class() -> None:
    """No selection could have succeeded, so blaming retrieval would be wrong."""
    observation = classify(
        _question(),
        _label(("h00000",)),
        [_turn("h00000")],
        [],
        context_limited=True,
        plan_terms=(),
        session_members={},
    )
    assert observation is not None
    assert observation.issue_class is IssueClass.CONTEXT_COVERAGE


def test_expected_abstention_that_answered_is_semantic_not_retrieval() -> None:
    observation = classify(
        _question(),
        _label(()),
        [_turn("h00000")],
        ["h00000"],
        context_limited=False,
        plan_terms=("berlin",),
        session_members={},
    )
    assert observation is not None
    assert observation.issue_class is IssueClass.SEMANTIC_HANDLING


def test_selecting_nothing_is_ambiguous_with_an_ontology_gap() -> None:
    """Selecting nothing cannot distinguish a bad plan from an inexpressible question."""
    observation = classify(
        _question(),
        _label(("h00000",)),
        [_turn("h00000")],
        [],
        context_limited=False,
        plan_terms=("berlin",),
        session_members={},
    )
    assert observation is not None
    assert observation.issue_class is IssueClass.QUERY_COMPILER
    assert IssueClass.ONTOLOGY_GAP in observation.ambiguous_with
    assert observation.is_ambiguous


def test_a_superset_selection_is_a_precision_failure() -> None:
    observation = classify(
        _question(),
        _label(("h00000",)),
        [_turn("h00000"), _turn("h00001")],
        ["h00000", "h00001"],
        context_limited=False,
        plan_terms=("berlin",),
        session_members={},
    )
    assert observation is not None
    assert observation.issue_class is IssueClass.RETRIEVAL_RANKING


def test_a_partial_selection_is_a_closure_failure() -> None:
    observation = classify(
        _question(),
        _label(("h00000", "h00001")),
        [_turn("h00000"), _turn("h00001")],
        ["h00000"],
        context_limited=False,
        plan_terms=("berlin",),
        session_members={},
    )
    assert observation is not None
    assert observation.issue_class is IssueClass.EVIDENCE_CLOSURE
    assert IssueClass.RETRIEVAL_RANKING in observation.ambiguous_with


def test_no_class_may_be_assigned_without_a_stated_evidence_requirement() -> None:
    """Every class must be justifiable, or attribution is decoration."""
    assert set(CLASS_EVIDENCE_REQUIREMENT) == set(IssueClass)
    assert all(requirement.strip() for requirement in CLASS_EVIDENCE_REQUIREMENT.values())


def test_ontology_share_is_reported_so_over_attribution_is_visible() -> None:
    """A high ontology share warns about the classifier, not about the ontology."""
    observations = [
        classify(
            _question(),
            _label(("h00000",)),
            [_turn("h00000"), _turn("h00001")],
            ["h00000", "h00001"],
            context_limited=False,
            plan_terms=("berlin",),
            session_members={},
        )
    ]
    ledger = IssueLedger(
        corpus_id="c",
        split="discovery",
        observations=tuple(o for o in observations if o is not None),
    )
    assert ledger.ontology_share() == 0.0
    assert sum(ledger.counts().values()) == len(ledger.observations)
