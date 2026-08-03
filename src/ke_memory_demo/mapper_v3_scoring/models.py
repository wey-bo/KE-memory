"""Frozen report models for mapper v3 scoring.

The one rule every model here exists to enforce: a metric with nothing to measure must say so, not
lie by reporting zero. ``Metric.value`` is ``None`` whenever ``denominator`` is ``0``, and the model
carries an ``availability`` flag plus a mandatory, non-empty ``unavailable_reason`` in that case. A
metric that collapsed an empty denominator to ``0.0`` would be indistinguishable from a metric that
measured total failure, and those are not the same finding.

``numerator``, ``denominator`` and ``completed`` are all plain ints so a reader can recompute
``value`` themselves rather than trusting a float that might have been rounded, hand-edited, or
computed from a different population than the one named.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Final

from pydantic import BaseModel, ConfigDict, Field, model_validator

NonEmptyString = Annotated[str, Field(min_length=1)]


class ScoringError(ValueError):
    """A metric, or the report containing it, was built with data that contradicts its own claim."""


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Availability(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


class Metric(_Frozen):
    """One numerator/denominator measurement, with its own honesty check built in.

    ``completed`` is the number of records in the metric's population for which the scorer actually
    reached a decision. In this design every gold record is paired with exactly one mapping result
    (the scorer rejects any mismatch before a report is built), so ``completed`` equals
    ``denominator`` for every metric here: nothing in the eligible population is ever skipped. The
    field is still carried on every metric, rather than only where it could differ, so a reader never
    has to wonder whether an omission means "not applicable" or "not measured".
    """

    numerator: int = Field(ge=0)
    denominator: int = Field(ge=0)
    completed: int = Field(ge=0)
    value: float | None
    availability: Availability
    unavailable_reason: str | None = None

    @model_validator(mode="after")
    def _validate(self) -> Metric:
        if self.numerator > self.denominator:
            raise ScoringError(
                f"numerator {self.numerator} exceeds denominator {self.denominator}; a metric "
                "cannot count more decisions than the population it was computed over"
            )
        if self.completed > self.denominator:
            raise ScoringError(
                f"completed {self.completed} exceeds denominator {self.denominator}; completed "
                "counts a subset of the population, not an addition to it"
            )
        if self.denominator == 0:
            if self.availability is not Availability.UNAVAILABLE:
                raise ScoringError(
                    "a metric with denominator 0 must be marked unavailable, not available; an "
                    "empty population has no rate to report"
                )
            if self.value is not None:
                raise ScoringError(
                    f"a metric with denominator 0 reported value={self.value!r} instead of None; "
                    "this is exactly the empty-denominator-as-zero failure this model forbids"
                )
            if not self.unavailable_reason:
                raise ScoringError(
                    "a metric with denominator 0 must carry a non-empty unavailable_reason "
                    "stating why its population is empty"
                )
        else:
            if self.availability is not Availability.AVAILABLE:
                raise ScoringError(
                    f"a metric with denominator {self.denominator} must be marked available, not "
                    "unavailable"
                )
            if self.unavailable_reason is not None:
                raise ScoringError(
                    "an available metric must not carry an unavailable_reason; the field is only "
                    "meaningful when there is nothing to measure"
                )
            expected = self.numerator / self.denominator
            if self.value is None:
                raise ScoringError(
                    f"a metric with denominator {self.denominator} must report a numeric value, "
                    "not None"
                )
            if abs(self.value - expected) > 1e-9:
                raise ScoringError(
                    f"value {self.value!r} does not equal numerator/denominator "
                    f"({self.numerator}/{self.denominator} = {expected!r})"
                )
        return self


def available_metric(numerator: int, denominator: int, *, completed: int | None = None) -> Metric:
    """Build a :class:`Metric` for a non-empty population, computing ``value`` from the counts.

    ``completed`` defaults to ``denominator``, the only value it can take while every gold record is
    paired with exactly one mapping result.
    """
    if denominator <= 0:
        raise ScoringError(
            "available_metric requires a positive denominator; use unavailable_metric for an "
            "empty population"
        )
    resolved_completed = denominator if completed is None else completed
    return Metric(
        numerator=numerator,
        denominator=denominator,
        completed=resolved_completed,
        value=numerator / denominator,
        availability=Availability.AVAILABLE,
        unavailable_reason=None,
    )


def unavailable_metric(reason: str) -> Metric:
    """Build a :class:`Metric` for an empty population. ``reason`` must say why it is empty."""
    if not reason:
        raise ScoringError("unavailable_metric requires a non-empty reason")
    return Metric(
        numerator=0,
        denominator=0,
        completed=0,
        value=None,
        availability=Availability.UNAVAILABLE,
        unavailable_reason=reason,
    )


class OntologyGapSplit(_Frozen):
    """The explicit split between what the ontology cannot express and what the mapper missed.

    ``out_of_scope_expression_ids`` names every gold record the combined ontology cannot represent.
    These are excluded from :attr:`ScoringReport.candidate_recall_micro`,
    :attr:`ScoringReport.candidate_recall_macro` and :attr:`ScoringReport.ranking_or_sense_accuracy`
    by construction: an expression the ontology cannot express can never count against the mapper's
    recall, because there was nothing correct for the mapper to find.
    """

    out_of_scope_count: int = Field(ge=0)
    out_of_scope_expression_ids: tuple[NonEmptyString, ...]
    reading: NonEmptyString = (
        "expressions labelled out_of_scope are removed from every recall and accuracy denominator "
        "before it is computed; a gap in the combined ontology is not a mapper failure and must "
        "never be counted as one"
    )

    @model_validator(mode="after")
    def _validate(self) -> OntologyGapSplit:
        if len(set(self.out_of_scope_expression_ids)) != len(self.out_of_scope_expression_ids):
            raise ScoringError("out_of_scope_expression_ids contains a duplicate")
        if len(self.out_of_scope_expression_ids) != self.out_of_scope_count:
            raise ScoringError(
                f"out_of_scope_count={self.out_of_scope_count} does not match the "
                f"{len(self.out_of_scope_expression_ids)} listed ids"
            )
        return self


class NoMapBehaviour(_Frozen):
    """Correct abstention on gold ``none``, and its converse: missed content."""

    correct_abstention: Metric
    missed_content: Metric


class MultiLabelSelection(_Frozen):
    """Whether the mapper returns multiple targets when gold names more than one.

    ``incomplete_multi_label_selection`` names the shortfall deliberately: the mapper returning too
    few targets for a multi-target gold record is an incompleteness, not a merge of distinct things
    into one, and the two failure modes should not share a name.
    """

    multi_label_selection: Metric
    incomplete_multi_label_selection: Metric


class CandidateRecall(_Frozen):
    """Recall over id-bearing gold, reported both by individual id (micro) and by expression (macro)."""

    micro: Metric
    macro: Metric
    reading: NonEmptyString = (
        "micro sums over every gold target id across id-bearing expressions; macro counts an "
        "expression as a hit only when the mapper recalled every one of its gold target ids. Both "
        "exclude out_of_scope expressions, which have no gold target ids to recall"
    )


class ScoringReport(_Frozen):
    """The full mapper v3 scoring report.

    Every metric family is a :class:`Metric` or a small group of them, never a bare float, so
    ``availability`` and ``unavailable_reason`` travel with every rate a reader might otherwise
    misread as measured.
    """

    total_gold_records: int = Field(ge=0)
    total_mapping_results: int = Field(ge=0)
    ontology_gap: OntologyGapSplit
    ontology_coverage: Metric
    candidate_recall: CandidateRecall
    ranking_or_sense_accuracy: Metric
    no_map_behaviour: NoMapBehaviour
    multi_label_selection: MultiLabelSelection
    critical_false_mapping: Metric
    true_ambiguity_abstention: Metric

    @model_validator(mode="after")
    def _validate(self) -> ScoringReport:
        if self.total_gold_records != self.total_mapping_results:
            raise ScoringError(
                f"total_gold_records={self.total_gold_records} does not match "
                f"total_mapping_results={self.total_mapping_results}; the scorer must reject any "
                "mismatch before a report is built, so this indicates a report constructed "
                "outside the scorer"
            )
        return self


# The three outcomes a mapping result may report, held here as the structural contract's vocabulary
# rather than imported from the real mapper.
MAPPING_OUTCOMES: Final[frozenset[str]] = frozenset({"mapped", "ambiguous", "unresolved"})
UNRESOLVED_REASONS: Final[frozenset[str]] = frozenset(
    {"no_content", "request_only", "no_admissible_evidence"}
)
