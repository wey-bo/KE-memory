"""Independent mapping gold, authored from the ontology rather than from evidence gold.

The provenance rule matters more than the size. Back-deriving mapping gold from the evidence gold
of a benchmark question would encode which units happen to answer that question, so a mapper would
be scored on question relevance rather than on mapping. Each case here was written by reading an
O_L1 or O_L2 item and composing an utterance that should evoke it, then recording what a correct
mapper must return — including the cases where the correct answer is "ambiguous" or "nothing".

Review load is graded, as required: a clear case carries ``single_review``, while novel, ambiguous,
L2 and disputed cases carry ``double_review`` and an adjudication note. That keeps the manual volume
bounded without pretending every case is equally settled.

Negative and ambiguous cases are deliberately included. A gold set containing only clean positives
cannot detect a mapper that maps everything to something.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

NonEmptyString = Annotated[str, Field(min_length=1)]


class ReviewLevel(StrEnum):
    SINGLE = "single_review"
    DOUBLE = "double_review"


class ExpectedOutcome(StrEnum):
    """What a correct mapper must do, including declining."""

    MAPS_TO = "maps_to"
    AMBIGUOUS_AMONG = "ambiguous_among"
    UNRESOLVED = "unresolved"


class _Record(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class MappingGoldCase(_Record):
    """One authored case. ``text`` is the input; everything else is the expectation."""

    case_id: NonEmptyString
    layer: str
    text: NonEmptyString
    outcome: ExpectedOutcome
    expected_ids: tuple[str, ...] = ()
    review: ReviewLevel = ReviewLevel.SINGLE
    rationale: NonEmptyString = "authored from the ontology item"
    adjudication: str = ""
    novel: bool = False


def _l1(
    case_id: str,
    text: str,
    outcome: ExpectedOutcome,
    expected: tuple[str, ...] = (),
    *,
    review: ReviewLevel = ReviewLevel.SINGLE,
    rationale: str = "authored from the ontology item",
    adjudication: str = "",
    novel: bool = False,
) -> MappingGoldCase:
    return MappingGoldCase(
        case_id=case_id,
        layer="l1",
        text=text,
        outcome=outcome,
        expected_ids=expected,
        review=review,
        rationale=rationale,
        adjudication=adjudication,
        novel=novel,
    )


def _l2(
    case_id: str,
    text: str,
    outcome: ExpectedOutcome,
    expected: tuple[str, ...] = (),
    *,
    rationale: str = "authored from the ontology item",
    adjudication: str = "",
    novel: bool = False,
) -> MappingGoldCase:
    # Every L2 case is double-reviewed: abstraction judgements were the least settled part of the
    # ontology freeze, so a single opinion is not enough to call one wrong.
    return MappingGoldCase(
        case_id=case_id,
        layer="l2",
        text=text,
        outcome=outcome,
        expected_ids=expected,
        review=ReviewLevel.DOUBLE,
        rationale=rationale,
        adjudication=adjudication or "L2 abstraction requires a second opinion by policy",
        novel=novel,
    )


MAPPING_GOLD: tuple[MappingGoldCase, ...] = (
    # ---- L1 predicates, clear positives -------------------------------------------------
    _l1(
        "L1-001",
        "I booked a table at the Italian place for Friday",
        ExpectedOutcome.MAPS_TO,
        ("l1:predicate.commit_to_arrangement",),
        rationale="'booked' is a declared alias of commit_to_arrangement",
    ),
    _l1(
        "L1-002",
        "Please cancel my flight reservation",
        ExpectedOutcome.MAPS_TO,
        ("l1:predicate.change_arrangement",),
        rationale="'cancel' is a declared alias of change_arrangement",
    ),
    _l1(
        "L1-003",
        "I really like jazz records",
        ExpectedOutcome.MAPS_TO,
        ("l1:predicate.hold_attitude",),
        rationale="'like' is a declared alias of hold_attitude",
    ),
    _l1(
        "L1-004",
        "I paid for the tickets yesterday",
        ExpectedOutcome.MAPS_TO,
        ("l1:predicate.transfer_value",),
        rationale="'paid' is a declared alias of transfer_value",
    ),
    _l1(
        "L1-005",
        "Can you look up the opening hours",
        ExpectedOutcome.MAPS_TO,
        ("l1:predicate.seek_information",),
        rationale="'look up' is a declared alias of seek_information",
    ),
    _l1(
        "L1-006",
        "I work as a paralegal downtown",
        ExpectedOutcome.MAPS_TO,
        ("l1:predicate.occupy_role",),
        rationale="'work as' is a declared alias of occupy_role",
    ),
    _l1(
        "L1-007",
        "We watched the new documentary last night",
        ExpectedOutcome.MAPS_TO,
        ("l1:predicate.consume_media", "l1:event.media_consumption"),
        review=ReviewLevel.DOUBLE,
        rationale="'watched' is an alias of both the predicate and the event type",
        adjudication=(
            "disputed: the utterance attests both a predicate and a completed event, so either id "
            "is defensible and the mapper is not penalised for choosing one"
        ),
    ),
    # ---- L1 events ----------------------------------------------------------------------
    _l1(
        "L1-008",
        "The payment failed and did not go through",
        ExpectedOutcome.MAPS_TO,
        ("l1:event.attempt_failed",),
        rationale="'failed' and 'did not go through' are both declared aliases",
    ),
    _l1(
        "L1-009",
        "They called off the meeting",
        ExpectedOutcome.MAPS_TO,
        ("l1:event.commitment_withdrawn",),
        rationale="'called off' is a declared alias of commitment_withdrawn",
    ),
    # ---- L1 preferences, where the sub-type distinction is the point --------------------
    _l1(
        "L1-010",
        "I would sooner take the train than fly",
        ExpectedOutcome.MAPS_TO,
        ("l1:preference.comparative",),
        review=ReviewLevel.DOUBLE,
        rationale="'would sooner' is an alias of the comparative sub-type specifically",
        adjudication=(
            "ambiguity risk: affinity also plausibly fires on a stated liking, so the comparative "
            "reading needs a second opinion"
        ),
    ),
    _l1(
        "L1-011",
        "Keep it to no more than fifty pounds",
        ExpectedOutcome.MAPS_TO,
        ("l1:preference.threshold",),
        rationale="'no more than' is a declared alias of the threshold sub-type",
    ),
    # ---- L1 ambiguous by construction ---------------------------------------------------
    _l1(
        "L1-012",
        "I want to change my booking",
        ExpectedOutcome.AMBIGUOUS_AMONG,
        ("l1:predicate.change_arrangement", "l1:predicate.commit_to_arrangement"),
        review=ReviewLevel.DOUBLE,
        rationale="'change' and 'booking' evoke two predicates with no disambiguating context",
        adjudication=(
            "genuine ambiguity: a correct mapper should report both rather than silently pick one"
        ),
    ),
    # ---- L1 negatives: nothing in the ontology should fire -----------------------------
    _l1(
        "L1-013",
        "The weather has been mild lately",
        ExpectedOutcome.UNRESOLVED,
        rationale="no ontology item covers meteorological small talk; a mapping here is a false positive",
    ),
    _l1(
        "L1-014",
        "Mm hmm, right, okay then",
        ExpectedOutcome.UNRESOLVED,
        rationale="backchannel with no propositional content; speech acts were rejected from v1",
    ),
    _l1(
        "L1-015",
        "If the price drops below thirty I will take it",
        ExpectedOutcome.UNRESOLVED,
        review=ReviewLevel.DOUBLE,
        rationale="conditional commitment is a recorded uncovered expression in the freeze",
        adjudication=(
            "novel: threshold fires on 'below thirty' but the conditional commitment itself has no "
            "id, so a partial mapping here understates a real gap"
        ),
        novel=True,
    ),
    # ---- L2 abstractions ---------------------------------------------------------------
    _l2(
        "L2-001",
        "I go running every Tuesday and Thursday without fail",
        ExpectedOutcome.MAPS_TO,
        ("l2:abstraction.habit",),
        rationale="repeated behaviour by one subject is what habit is defined for",
        adjudication=(
            "the habit item carries the weakest evidence in the freeze, so this case is a direct "
            "test of whether it earns its place"
        ),
    ),
    _l2(
        "L2-002",
        "I have been trying to finish the kitchen renovation for months",
        ExpectedOutcome.MAPS_TO,
        ("l2:abstraction.project",),
        rationale="a long-running multi-step undertaking is the project abstraction",
    ),
    _l2(
        "L2-003",
        "My sister has always been the one who organises these trips",
        ExpectedOutcome.UNRESOLVED,
        rationale="social relationship is the largest recorded O_L2 gap",
        adjudication="novel: deferred during the freeze because MSC mentions relationships without annotating them",
        novel=True,
    ),
)


def gold_by_layer(layer: str) -> tuple[MappingGoldCase, ...]:
    return tuple(case for case in MAPPING_GOLD if case.layer == layer)


def review_counts() -> dict[str, int]:
    counts = {level.value: 0 for level in ReviewLevel}
    for case in MAPPING_GOLD:
        counts[case.review.value] += 1
    return counts


def provenance() -> dict[str, object]:
    return {
        "authoring_rule": (
            "each case was written by reading an O_L1 or O_L2 item and composing an utterance that "
            "should evoke it. No case was derived from any benchmark question or evidence gold."
        ),
        "not_derived_from": [
            "benchmark questions",
            "evidence gold",
            "dataset identity",
            "sample ids",
        ],
        "case_count": len(MAPPING_GOLD),
        "review_counts": review_counts(),
        "negative_cases": sum(
            1 for case in MAPPING_GOLD if case.outcome is ExpectedOutcome.UNRESOLVED
        ),
        "ambiguous_cases": sum(
            1 for case in MAPPING_GOLD if case.outcome is ExpectedOutcome.AMBIGUOUS_AMONG
        ),
        "novel_cases": sum(1 for case in MAPPING_GOLD if case.novel),
        "why_negatives_matter": (
            "a gold set of clean positives cannot detect a mapper that maps everything to something"
        ),
    }
