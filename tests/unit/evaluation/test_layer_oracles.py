"""Oracle substitution must be effective, single-layer, and honestly gated.

A review rejected an earlier version for three reasons this file covers:

- four layers reused the question's final evidence set as their "gold", which injects
  question relevance rather than substituting the layer
- the L2 abstraction was computed and then never consumed, so substituting it changed the
  trace and nothing that was scored
- the effectiveness assertion only forbade *unrelated* change, so a substitution that
  changed nothing at all passed and was reported as executed
"""

from __future__ import annotations

import pytest

from ke_memory_demo.evaluation.arms import turns_by_conversation
from ke_memory_demo.evaluation.layer_gold import LayerGold, LayerGoldBundle, LayerGoldError
from ke_memory_demo.evaluation.layer_oracles import (
    ALL_ORACLE_LAYERS,
    LAYER_FIELD,
    OracleError,
    OracleLayer,
    assert_single_layer_substitution,
    assert_substitution_is_effective,
    available_layers,
    changed_stages,
    substitute,
)
from ke_memory_demo.evaluation.oracle_fixture import build_fixture
from ke_memory_demo.evaluation.pipeline_stages import baseline_pipeline


def test_every_layer_substitution_changes_its_own_stage() -> None:
    """The positive half of the guarantee: a substitution must actually substitute."""
    fixture, bundle = build_fixture()
    base = baseline_pipeline()
    turns = turns_by_conversation(fixture.build_input)

    for layer in ALL_ORACLE_LAYERS:
        for question in fixture.questions.questions:
            available = turns[question.conversation_handle]
            baseline_trace = base.run(question, available)
            if layer is OracleLayer.GOLD_EVIDENCE_SELECTION:
                pipeline = substitute(
                    base, layer, gold=fixture.gold, question_id=question.question_id
                )
            else:
                pipeline = substitute(
                    base, layer, layer_gold=bundle.for_question(question.question_id)
                )
            changed = changed_stages(baseline_trace, pipeline.run(question, available))
            assert LAYER_FIELD[layer] in changed
            assert_substitution_is_effective(layer, changed)


def test_an_inert_substitution_is_rejected() -> None:
    """A layer whose output did not change cannot be reported as substituted."""
    with pytest.raises(OracleError, match="did not change"):
        assert_substitution_is_effective(OracleLayer.GOLD_L2_ABSTRACTION, frozenset())


def test_an_upstream_change_is_rejected() -> None:
    """A plan substitution cannot alter extraction, which precedes it."""
    with pytest.raises(OracleError, match="upstream"):
        assert_substitution_is_effective(
            OracleLayer.GOLD_QUERY_PLAN, frozenset({"query_plan", "extraction"})
        )


def test_l2_abstraction_reaches_the_scored_selection() -> None:
    """The specific defect: L2 was computed and discarded.

    Substituting the plan alone selects nothing, because the fixture L2 never produces the
    canonical abstraction the gold plan asks for. Adding gold L2 makes the selection correct,
    which is only possible if the L2 output feeds selection.
    """
    fixture, bundle = build_fixture()
    base = baseline_pipeline()
    question = fixture.questions.questions[0]
    available = turns_by_conversation(fixture.build_input)[question.conversation_handle]
    layer_gold = bundle.for_question(question.question_id)
    label = fixture.gold.label_for(question.question_id)
    assert label is not None
    gold_refs = set(label.evidence_refs)

    plan_only = substitute(base, OracleLayer.GOLD_QUERY_PLAN, layer_gold=layer_gold)
    assert set(plan_only.run(question, available).selected_handles) != gold_refs

    plan_and_l2 = substitute(
        plan_only, OracleLayer.GOLD_L2_ABSTRACTION, layer_gold=layer_gold
    )
    assert set(plan_and_l2.run(question, available).selected_handles) == gold_refs


def test_a_layer_without_its_own_gold_cannot_be_substituted() -> None:
    """Refusing is the point: falling back would reinterpret another layer's annotation."""
    empty = LayerGold(question_id="q1")
    base = baseline_pipeline()
    for layer in ALL_ORACLE_LAYERS:
        if layer is OracleLayer.GOLD_EVIDENCE_SELECTION:
            continue
        with pytest.raises(LayerGoldError, match="absent|requires"):
            substitute(base, layer, layer_gold=empty)


def test_available_layers_reports_only_layers_with_real_gold() -> None:
    """The slice has no per-layer gold, so only evidence selection may be reported."""
    fixture, bundle = build_fixture()
    assert set(available_layers(bundle, gold=fixture.gold)) == set(ALL_ORACLE_LAYERS)

    # A bundle with no per-layer annotation, which is the regression slice's situation.
    bare = LayerGoldBundle(fixture_id="bare", entries=(LayerGold(question_id="q1"),))
    assert available_layers(bare, gold=fixture.gold) == (
        OracleLayer.GOLD_EVIDENCE_SELECTION,
    )
    assert available_layers(None, gold=None) == ()


def test_partial_layer_coverage_does_not_count_as_coverage() -> None:
    """Partial coverage would let some questions silently use the baseline stage."""
    fixture, bundle = build_fixture()
    partial = LayerGoldBundle(
        fixture_id="partial",
        entries=(bundle.entries[0], LayerGold(question_id="fx-q2")),
    )
    assert partial.covers("extraction") is False
    assert OracleLayer.GOLD_EXTRACTION not in available_layers(partial, gold=fixture.gold)


def test_multi_layer_substitution_is_refused() -> None:
    assert_single_layer_substitution([OracleLayer.GOLD_QUERY_PLAN])
    with pytest.raises(OracleError, match="at most one layer"):
        assert_single_layer_substitution(
            [OracleLayer.GOLD_QUERY_PLAN, OracleLayer.GOLD_EVIDENCE_SELECTION]
        )
