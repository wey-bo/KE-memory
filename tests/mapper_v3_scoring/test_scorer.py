"""Tests for mapper_v3_scoring, against synthetic fixtures only.

No fixture here reads artifacts/mapper-v3-validation/, mapper_v3_validation/annotations.py or
mapper_v3/. Gold records are built directly through :class:`AnnotationRecord`; mapping results are
a small local dataclass satisfying the scorer's structural :class:`MappingResult` protocol.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from ke_memory_demo.mapper_v3_scoring.models import (
    MAPPING_OUTCOMES,
    UNRESOLVED_REASONS,
    Availability,
    ScoringError,
)
from ke_memory_demo.mapper_v3_scoring.runner import build_report
from ke_memory_demo.mapper_v3_scoring.scorer import score
from ke_memory_demo.mapper_v3_validation.models import AnnotationGold, AnnotationRecord, Outcome

ALLOWED_IDS = frozenset(
    {
        "l1:event.communicative_act",
        "l1:predicate.hold_belief",
        "l1:state.capability",
        "l2:abstraction.pursuit_profile",
    }
)


@dataclass(frozen=True)
class FakeMappingResult:
    """A synthetic stand-in for the real mapper v3 result, satisfying the scorer's protocol."""

    expression_id: str
    outcome: str
    frames: tuple[object, ...] = ()
    target_ids: tuple[str, ...] = ()
    unresolved_reason: str | None = None
    constructions: tuple[str, ...] = ()


def concept(expression_id: str, *target_ids: str) -> AnnotationRecord:
    return AnnotationRecord(
        expression_id=expression_id,
        outcome=Outcome.CONCEPT,
        target_ids=tuple(sorted(target_ids)),
        sense="a synthetic gold sense for testing",
    )


def ambiguous(expression_id: str, *target_ids: str) -> AnnotationRecord:
    return AnnotationRecord(
        expression_id=expression_id,
        outcome=Outcome.AMBIGUOUS,
        target_ids=tuple(sorted(target_ids)),
        sense="a synthetic ambiguous gold sense for testing",
    )


def none_record(expression_id: str) -> AnnotationRecord:
    return AnnotationRecord(
        expression_id=expression_id,
        outcome=Outcome.NONE,
        sense="a synthetic backchannel sense for testing",
    )


def out_of_scope(expression_id: str) -> AnnotationRecord:
    return AnnotationRecord(
        expression_id=expression_id,
        outcome=Outcome.OUT_OF_SCOPE,
        sense="a synthetic gap sense for testing",
        would_require="a fifth ontology layer this test invents for coverage only",
    )


def mapped(expression_id: str, *target_ids: str) -> FakeMappingResult:
    return FakeMappingResult(
        expression_id=expression_id,
        outcome="mapped",
        frames=tuple(range(len(target_ids))),
        target_ids=target_ids,
    )


def unresolved(expression_id: str, reason: str = "no_admissible_evidence") -> FakeMappingResult:
    return FakeMappingResult(
        expression_id=expression_id,
        outcome="unresolved",
        unresolved_reason=reason,
    )


def ambiguous_result(expression_id: str, *target_ids: str) -> FakeMappingResult:
    return FakeMappingResult(
        expression_id=expression_id,
        outcome="ambiguous",
        frames=tuple(range(len(target_ids))),
        target_ids=target_ids,
    )


# ---------------------------------------------------------------------------
# Rejection paths
# ---------------------------------------------------------------------------


def test_rejects_a_result_whose_expression_id_is_missing_from_gold() -> None:
    gold = [concept("e1", "l1:event.communicative_act")]
    results = [mapped("e1", "l1:event.communicative_act"), mapped("e-not-in-gold")]

    with pytest.raises(ScoringError, match="e-not-in-gold"):
        score(gold, results, ALLOWED_IDS)


def test_rejects_a_gold_record_with_no_corresponding_result() -> None:
    gold = [concept("e1", "l1:event.communicative_act"), concept("e2", "l1:state.capability")]
    results = [mapped("e1", "l1:event.communicative_act")]

    with pytest.raises(ScoringError, match="e2"):
        score(gold, results, ALLOWED_IDS)


def test_rejects_duplicate_expression_ids_in_results() -> None:
    gold = [concept("e1", "l1:event.communicative_act")]
    results = [
        mapped("e1", "l1:event.communicative_act"),
        mapped("e1", "l1:event.communicative_act"),
    ]

    with pytest.raises(ScoringError, match="e1"):
        score(gold, results, ALLOWED_IDS)


def test_rejects_a_target_id_outside_the_allowed_set() -> None:
    gold = [concept("e1", "l1:event.communicative_act")]
    results = [mapped("e1", "l1:event.communicative_act", "l1:not_an_allowed_id")]

    with pytest.raises(ScoringError, match="l1:not_an_allowed_id"):
        score(gold, results, ALLOWED_IDS)


def test_rejects_an_unknown_outcome_string() -> None:
    gold = [concept("e1", "l1:event.communicative_act")]
    results = [FakeMappingResult(expression_id="e1", outcome="definitely_mapped")]

    with pytest.raises(ScoringError, match="definitely_mapped"):
        score(gold, results, ALLOWED_IDS)


def test_rejects_an_unknown_unresolved_reason() -> None:
    gold = [none_record("e1")]
    results = [
        FakeMappingResult(expression_id="e1", outcome="unresolved", unresolved_reason="because")
    ]

    with pytest.raises(ScoringError, match="because"):
        score(gold, results, ALLOWED_IDS)


def test_rejects_a_target_ids_frames_length_mismatch() -> None:
    gold = [concept("e1", "l1:event.communicative_act")]
    results = [
        FakeMappingResult(
            expression_id="e1",
            outcome="mapped",
            frames=(),
            target_ids=("l1:event.communicative_act",),
        )
    ]

    with pytest.raises(ScoringError, match="e1"):
        score(gold, results, ALLOWED_IDS)


# ---------------------------------------------------------------------------
# Zero-denominator unavailable path
# ---------------------------------------------------------------------------


def test_true_ambiguity_abstention_is_unavailable_not_zero_when_gold_has_no_ambiguous_records() -> (
    None
):
    gold = [concept("e1", "l1:event.communicative_act"), none_record("e2")]
    results = [mapped("e1", "l1:event.communicative_act"), unresolved("e2", "no_content_terms")]

    report = score(gold, results, ALLOWED_IDS)

    metric = report.true_ambiguity_abstention
    assert metric.availability is Availability.UNAVAILABLE
    assert metric.value is None
    assert metric.value != 0.0
    assert metric.denominator == 0
    assert metric.unavailable_reason
    assert "ambiguous" in metric.unavailable_reason


def test_candidate_recall_is_unavailable_when_no_gold_is_id_bearing() -> None:
    gold = [none_record("e1"), out_of_scope("e2")]
    results = [
        unresolved("e1", "no_content_terms"),
        FakeMappingResult(
            expression_id="e2", outcome="unresolved", unresolved_reason="no_admissible_evidence"
        ),
    ]

    report = score(gold, results, ALLOWED_IDS)

    assert report.candidate_recall.micro.availability is Availability.UNAVAILABLE
    assert report.candidate_recall.micro.value is None
    assert report.candidate_recall.macro.availability is Availability.UNAVAILABLE
    assert report.candidate_recall.macro.value is None


def test_multi_label_selection_is_unavailable_when_no_gold_record_has_multiple_targets() -> None:
    gold = [concept("e1", "l1:event.communicative_act")]
    results = [mapped("e1", "l1:event.communicative_act")]

    report = score(gold, results, ALLOWED_IDS)

    assert report.multi_label_selection.multi_label_selection.availability is (
        Availability.UNAVAILABLE
    )
    assert report.multi_label_selection.multi_label_selection.value is None
    assert report.multi_label_selection.incomplete_multi_label_selection.value is None


# ---------------------------------------------------------------------------
# Mapper returns a superset of gold
# ---------------------------------------------------------------------------


def test_mapper_returning_a_superset_of_gold_fails_ranking_but_still_counts_recall() -> None:
    gold = [concept("e1", "l1:event.communicative_act")]
    results = [mapped("e1", "l1:event.communicative_act", "l1:state.capability")]

    report = score(gold, results, ALLOWED_IDS)

    # The gold id was recalled.
    assert report.candidate_recall.micro.numerator == 1
    assert report.candidate_recall.micro.denominator == 1
    # But the mapper's answer is not a subset of gold's (it has an extra id), so ranking fails.
    assert report.ranking_or_sense_accuracy.numerator == 0
    assert report.ranking_or_sense_accuracy.denominator == 1


# ---------------------------------------------------------------------------
# out_of_scope with targets returned: critical_false_mapping, not candidate_recall
# ---------------------------------------------------------------------------


def test_out_of_scope_with_targets_lands_in_critical_false_mapping_not_candidate_recall() -> None:
    gold = [out_of_scope("e1"), concept("e2", "l1:state.capability")]
    results = [
        mapped("e1", "l1:predicate.hold_belief"),
        mapped("e2", "l1:state.capability"),
    ]

    report = score(gold, results, ALLOWED_IDS)

    assert report.critical_false_mapping.numerator == 1
    assert report.critical_false_mapping.denominator == 1

    # candidate_recall's denominator is only over id-bearing gold (e2); the out_of_scope
    # expression contributes no gold target ids and must not appear in this denominator at all.
    assert report.candidate_recall.micro.denominator == 1
    assert report.candidate_recall.micro.numerator == 1
    assert report.candidate_recall.macro.denominator == 1

    assert report.ontology_gap.out_of_scope_count == 1
    assert report.ontology_gap.out_of_scope_expression_ids == ("e1",)


def test_none_with_targets_also_counts_as_critical_false_mapping() -> None:
    gold = [none_record("e1")]
    results = [mapped("e1", "l1:state.capability")]

    report = score(gold, results, ALLOWED_IDS)

    assert report.critical_false_mapping.numerator == 1
    assert report.critical_false_mapping.denominator == 1
    assert report.no_map_behaviour.correct_abstention.numerator == 0
    assert report.no_map_behaviour.correct_abstention.denominator == 1


# ---------------------------------------------------------------------------
# Perfect-score case
# ---------------------------------------------------------------------------


def test_perfect_score_case() -> None:
    gold = [
        concept("e1", "l1:event.communicative_act"),
        concept("e2", "l1:state.capability", "l2:abstraction.pursuit_profile"),
        none_record("e3"),
        out_of_scope("e4"),
    ]
    results = [
        mapped("e1", "l1:event.communicative_act"),
        mapped("e2", "l1:state.capability", "l2:abstraction.pursuit_profile"),
        unresolved("e3", "no_content_terms"),
        unresolved("e4", "no_admissible_evidence"),
    ]

    report = score(gold, results, ALLOWED_IDS)

    assert report.ontology_coverage.numerator == 3
    assert report.ontology_coverage.denominator == 4
    assert report.candidate_recall.micro.numerator == report.candidate_recall.micro.denominator == 3
    assert report.candidate_recall.macro.numerator == report.candidate_recall.macro.denominator == 2
    assert report.ranking_or_sense_accuracy.value == 1.0
    assert report.no_map_behaviour.correct_abstention.value == 1.0
    # missed_content's numerator counts misses (id-bearing gold the mapper wrongly left
    # unresolved); a perfect mapper resolves both, so the miss rate is 0.0.
    assert report.no_map_behaviour.missed_content.value == 0.0
    assert report.multi_label_selection.multi_label_selection.value == 1.0
    assert report.critical_false_mapping.numerator == 0
    assert report.critical_false_mapping.denominator == 2


# ---------------------------------------------------------------------------
# All-abstain case
# ---------------------------------------------------------------------------


def test_all_abstain_case() -> None:
    gold = [
        concept("e1", "l1:event.communicative_act"),
        concept("e2", "l1:state.capability", "l2:abstraction.pursuit_profile"),
        none_record("e3"),
        out_of_scope("e4"),
    ]
    results = [unresolved(record.expression_id, "no_admissible_evidence") for record in gold]

    report = score(gold, results, ALLOWED_IDS)

    assert report.candidate_recall.micro.numerator == 0
    assert report.candidate_recall.micro.denominator == 3
    assert report.candidate_recall.macro.numerator == 0
    assert report.candidate_recall.macro.denominator == 2
    assert report.ranking_or_sense_accuracy.availability is Availability.UNAVAILABLE
    assert report.ranking_or_sense_accuracy.value is None
    assert report.no_map_behaviour.correct_abstention.value == 1.0
    # Both id-bearing gold records were left unresolved by an all-abstain mapper: both are misses.
    assert report.no_map_behaviour.missed_content.numerator == 2
    assert report.no_map_behaviour.missed_content.denominator == 2
    assert report.multi_label_selection.multi_label_selection.numerator == 0
    assert report.multi_label_selection.incomplete_multi_label_selection.numerator == 1
    assert report.critical_false_mapping.numerator == 0
    assert report.critical_false_mapping.denominator == 2


# ---------------------------------------------------------------------------
# ontology_coverage is computed from gold alone
# ---------------------------------------------------------------------------


def test_ontology_coverage_ignores_the_mapper_entirely() -> None:
    gold = [concept("e1", "l1:event.communicative_act"), out_of_scope("e2")]
    # Even a mapper that gets everything wrong cannot move ontology_coverage.
    results = [unresolved("e1", "no_admissible_evidence"), mapped("e2", "l1:state.capability")]

    report = score(gold, results, ALLOWED_IDS)

    assert report.ontology_coverage.numerator == 1
    assert report.ontology_coverage.denominator == 2


# ---------------------------------------------------------------------------
# build_report wiring (runner) round trip via AnnotationGold
# ---------------------------------------------------------------------------


def test_build_report_scores_an_annotation_gold_object() -> None:
    gold = AnnotationGold(
        annotated_set_sha256="0" * 64,
        annotated_against_ontology="synthetic-test-ontology",
        records=(concept("e1", "l1:event.communicative_act"),),
    )
    results = [mapped("e1", "l1:event.communicative_act")]

    report = build_report(gold, results, ALLOWED_IDS)

    assert report.total_gold_records == 1
    assert report.total_mapping_results == 1
    assert report.candidate_recall.micro.value == 1.0


# ---------------------------------------------------------------------------
# The two vocabularies must agree
# ---------------------------------------------------------------------------


def test_the_scorer_and_the_mapper_spell_the_outcomes_identically() -> None:
    """The gap that let the first execution attempt fail with zero semantic output.

    The scorer keeps its own copy of the outcome and abstention vocabularies rather than importing
    the mapper's enums, because importing them would give the scorer a path to the mapper it
    scores. The cost of that isolation is that the two copies can drift, and they did: two of the
    three abstention reasons were transcribed from a paraphrase of the contract instead of from the
    enum, so every real abstention was rejected as malformed.

    Every synthetic fixture in this file passed throughout, because they all used the scorer's own
    spelling. Only a test that reaches for the mapper's enum can catch this, which is why this one
    test is allowed the import the rest of the module refuses -- it asserts agreement and never
    scores anything.
    """
    from ke_memory_demo.mapper_v3.mapper_v3 import Outcome as MapperOutcome
    from ke_memory_demo.mapper_v3.mapper_v3 import UnresolvedReason

    assert {member.value for member in MapperOutcome} == set(MAPPING_OUTCOMES)
    assert {member.value for member in UnresolvedReason} == set(UNRESOLVED_REASONS)
