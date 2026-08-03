"""The mapper v3 scorer.

``score`` is a pure function: gold records and mapping results in, a :class:`ScoringReport` out.
Nothing here imports a mapper module or reads an artifact -- the caller is responsible for loading
both inputs and handing over already-built objects, which is what keeps this module testable
against synthetic fixtures and unusable for anything but scoring.

The mapping result shape is defined structurally, as :class:`MappingResult`, rather than imported
from ``mapper_v3``. The real result type is expected to carry the same fields; if it drifts, that is
a contract to renegotiate explicitly, not something this module should discover by importing the
mapper and finding out.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Protocol, runtime_checkable

from ke_memory_demo.mapper_v3_validation.models import AnnotationRecord, Outcome

from .models import (
    MAPPING_OUTCOMES,
    UNRESOLVED_REASONS,
    CandidateRecall,
    Metric,
    MultiLabelSelection,
    NoMapBehaviour,
    OntologyGapSplit,
    ScoringError,
    ScoringReport,
    available_metric,
    unavailable_metric,
)


@runtime_checkable
class MappingResult(Protocol):
    """The structural contract a mapper v3 result must satisfy to be scoreable.

    Hardcoded from the fields the real result type is expected to carry:
    ``expression_id: str``, ``outcome`` in ``{"mapped", "ambiguous", "unresolved"}``,
    ``frames: tuple``, ``target_ids: tuple[str, ...]``, ``unresolved_reason`` in
    ``{"no_content_terms", "request_only_asserts_nothing", "no_admissible_evidence"}`` or ``None``,
    and ``constructions: tuple[str, ...]``. The invariant ``len(target_ids) == len(frames)`` is
    asserted by :func:`score`, not by this protocol, since a ``Protocol`` cannot express a
    cross-field constraint.

    Declared as read-only properties, rather than plain attributes, so a frozen dataclass or a
    frozen pydantic model -- both of which type their fields invariantly -- can satisfy this
    protocol without the field mutability mismatch a plain-attribute protocol would demand.
    """

    @property
    def expression_id(self) -> str: ...

    @property
    def outcome(self) -> str: ...

    @property
    def frames(self) -> tuple[object, ...]: ...

    @property
    def target_ids(self) -> tuple[str, ...]: ...

    @property
    def unresolved_reason(self) -> str | None: ...

    @property
    def constructions(self) -> tuple[str, ...]: ...


def _validate_result_shape(result: MappingResult) -> None:
    if result.outcome not in MAPPING_OUTCOMES:
        raise ScoringError(
            f"{result.expression_id} reports outcome {result.outcome!r}, which is not one of "
            f"{sorted(MAPPING_OUTCOMES)}"
        )
    if result.unresolved_reason is not None and result.unresolved_reason not in UNRESOLVED_REASONS:
        raise ScoringError(
            f"{result.expression_id} reports unresolved_reason {result.unresolved_reason!r}, "
            f"which is not one of {sorted(UNRESOLVED_REASONS)} or None"
        )
    if len(result.target_ids) != len(result.frames):
        raise ScoringError(
            f"{result.expression_id} has {len(result.target_ids)} target_ids but "
            f"{len(result.frames)} frames; the invariant len(target_ids) == len(frames) is "
            "violated"
        )


def _reject_population_mismatch(
    gold_records: Sequence[AnnotationRecord],
    mapping_results: Sequence[MappingResult],
) -> None:
    gold_ids = [record.expression_id for record in gold_records]
    result_ids = [result.expression_id for result in mapping_results]

    gold_id_set = set(gold_ids)
    result_id_set = set(result_ids)

    duplicates = sorted({rid for rid in result_ids if result_ids.count(rid) > 1})
    if duplicates:
        raise ScoringError(f"mapping_results contains duplicate expression_id(s): {duplicates}")

    unknown = sorted(result_id_set - gold_id_set)
    if unknown:
        raise ScoringError(f"mapping_results contains expression_id(s) absent from gold: {unknown}")

    missing = sorted(gold_id_set - result_id_set)
    if missing:
        raise ScoringError(f"gold contains expression_id(s) with no mapping result: {missing}")


def _reject_disallowed_targets(
    mapping_results: Sequence[MappingResult],
    allowed_target_ids: frozenset[str],
) -> None:
    offending: dict[str, tuple[str, ...]] = {}
    for result in mapping_results:
        bad = tuple(t for t in result.target_ids if t not in allowed_target_ids)
        if bad:
            offending[result.expression_id] = bad
    if offending:
        raise ScoringError(
            "mapping_results name target id(s) outside the allowed-id set: "
            f"{dict(sorted(offending.items()))}"
        )


def score(
    gold_records: Iterable[AnnotationRecord],
    mapping_results: Iterable[MappingResult],
    allowed_target_ids: frozenset[str],
) -> ScoringReport:
    """Score ``mapping_results`` against ``gold_records``.

    ``allowed_target_ids`` is the union of ids a mapping result may legally name (the combined v2 +
    v3 ontology, in the real round); any target id outside it is rejected rather than silently
    scored as wrong.

    Raises :class:`ScoringError` for every population mismatch and shape violation described in the
    module docstring, before computing a single metric.
    """
    gold_list = list(gold_records)
    result_list = list(mapping_results)

    _reject_population_mismatch(gold_list, result_list)
    for result in result_list:
        _validate_result_shape(result)
    _reject_disallowed_targets(result_list, allowed_target_ids)

    results_by_id: Mapping[str, MappingResult] = {r.expression_id: r for r in result_list}

    return ScoringReport(
        total_gold_records=len(gold_list),
        total_mapping_results=len(result_list),
        ontology_gap=_ontology_gap(gold_list),
        ontology_coverage=_ontology_coverage(gold_list),
        candidate_recall=_candidate_recall(gold_list, results_by_id),
        ranking_or_sense_accuracy=_ranking_or_sense_accuracy(gold_list, results_by_id),
        no_map_behaviour=_no_map_behaviour(gold_list, results_by_id),
        multi_label_selection=_multi_label_selection(gold_list, results_by_id),
        critical_false_mapping=_critical_false_mapping(gold_list, results_by_id),
        true_ambiguity_abstention=_true_ambiguity_abstention(gold_list, results_by_id),
    )


def _ontology_gap(gold_list: Sequence[AnnotationRecord]) -> OntologyGapSplit:
    gaps = tuple(sorted(r.expression_id for r in gold_list if r.outcome is Outcome.OUT_OF_SCOPE))
    return OntologyGapSplit(
        out_of_scope_count=len(gaps),
        out_of_scope_expression_ids=gaps,
    )


def _ontology_coverage(gold_list: Sequence[AnnotationRecord]) -> Metric:
    """Of gold, how many are expressible by the combined ontology (not out_of_scope).

    This measures the ontology, not the mapper: it is computed from gold labels alone and does not
    look at a single mapping result.
    """
    denominator = len(gold_list)
    numerator = sum(1 for r in gold_list if r.outcome is not Outcome.OUT_OF_SCOPE)
    if denominator == 0:
        return unavailable_metric("the gold set supplied to the scorer contains no records")
    return available_metric(numerator, denominator)


def _candidate_recall(
    gold_list: Sequence[AnnotationRecord],
    results_by_id: Mapping[str, MappingResult],
) -> CandidateRecall:
    """Recall over id-bearing gold only; out_of_scope and none records have no target ids to recall."""
    id_bearing = [r for r in gold_list if r.outcome in {Outcome.CONCEPT, Outcome.AMBIGUOUS}]

    micro_denominator = sum(len(r.target_ids) for r in id_bearing)
    micro_numerator = 0
    macro_denominator = len(id_bearing)
    macro_numerator = 0

    for record in id_bearing:
        result = results_by_id[record.expression_id]
        recalled = set(record.target_ids) & set(result.target_ids)
        micro_numerator += len(recalled)
        if recalled == set(record.target_ids):
            macro_numerator += 1

    micro = (
        unavailable_metric(
            "no gold record in this run is id-bearing (concept or ambiguous), so there are no "
            "gold target ids to recall"
        )
        if micro_denominator == 0
        else available_metric(micro_numerator, micro_denominator)
    )
    macro = (
        unavailable_metric("no gold record in this run is id-bearing (concept or ambiguous)")
        if macro_denominator == 0
        else available_metric(macro_numerator, macro_denominator)
    )
    return CandidateRecall(micro=micro, macro=macro)


def _ranking_or_sense_accuracy(
    gold_list: Sequence[AnnotationRecord],
    results_by_id: Mapping[str, MappingResult],
) -> Metric:
    """Among id-bearing gold where the mapper returned >=1 target, is the mapper's answer a subset
    of, or equal to, gold's targets.

    Restricted to expressions where the mapper returned something: an expression the mapper left
    unresolved has no ranking to judge, and belongs to :func:`_no_map_behaviour` instead.
    """
    eligible = [
        r
        for r in gold_list
        if r.outcome in {Outcome.CONCEPT, Outcome.AMBIGUOUS}
        and len(results_by_id[r.expression_id].target_ids) > 0
    ]
    denominator = len(eligible)
    if denominator == 0:
        return unavailable_metric(
            "no id-bearing gold record in this run has a mapping result that returned at least "
            "one target"
        )
    numerator = sum(
        1 for r in eligible if set(results_by_id[r.expression_id].target_ids) <= set(r.target_ids)
    )
    return available_metric(numerator, denominator)


def _no_map_behaviour(
    gold_list: Sequence[AnnotationRecord],
    results_by_id: Mapping[str, MappingResult],
) -> NoMapBehaviour:
    gold_none = [r for r in gold_list if r.outcome is Outcome.NONE]
    none_denominator = len(gold_none)
    correct_abstention = (
        unavailable_metric("no gold record in this run is labelled none")
        if none_denominator == 0
        else available_metric(
            sum(1 for r in gold_none if results_by_id[r.expression_id].outcome == "unresolved"),
            none_denominator,
        )
    )

    id_bearing = [r for r in gold_list if r.outcome in {Outcome.CONCEPT, Outcome.AMBIGUOUS}]
    missed_denominator = len(id_bearing)
    missed_content = (
        unavailable_metric("no gold record in this run is id-bearing (concept or ambiguous)")
        if missed_denominator == 0
        else available_metric(
            sum(1 for r in id_bearing if results_by_id[r.expression_id].outcome == "unresolved"),
            missed_denominator,
        )
    )
    return NoMapBehaviour(correct_abstention=correct_abstention, missed_content=missed_content)


def _multi_label_selection(
    gold_list: Sequence[AnnotationRecord],
    results_by_id: Mapping[str, MappingResult],
) -> MultiLabelSelection:
    multi = [r for r in gold_list if len(r.target_ids) > 1]
    denominator = len(multi)
    if denominator == 0:
        unavailable = unavailable_metric("no gold record in this run names more than one target id")
        return MultiLabelSelection(
            multi_label_selection=unavailable, incomplete_multi_label_selection=unavailable
        )
    hit = sum(1 for r in multi if len(results_by_id[r.expression_id].target_ids) > 1)
    return MultiLabelSelection(
        multi_label_selection=available_metric(hit, denominator),
        incomplete_multi_label_selection=available_metric(denominator - hit, denominator),
    )


def _critical_false_mapping(
    gold_list: Sequence[AnnotationRecord],
    results_by_id: Mapping[str, MappingResult],
) -> Metric:
    """Over gold labelled none or out_of_scope, how often the mapper nevertheless returned targets.

    The most important failure class this report carries: inventing structure where gold says there
    is none, whether because the content is not memory-worthy (none) or because the combined
    ontology cannot express it (out_of_scope).
    """
    population = [r for r in gold_list if r.outcome in {Outcome.NONE, Outcome.OUT_OF_SCOPE}]
    denominator = len(population)
    if denominator == 0:
        return unavailable_metric("no gold record in this run is labelled none or out_of_scope")
    numerator = sum(1 for r in population if len(results_by_id[r.expression_id].target_ids) > 0)
    return available_metric(numerator, denominator)


def _true_ambiguity_abstention(
    gold_list: Sequence[AnnotationRecord],
    results_by_id: Mapping[str, MappingResult],
) -> Metric:
    """Over gold labelled ambiguous, how often the mapper reported outcome "ambiguous".

    This round's gold is expected to contain zero ambiguous records, in which case this metric must
    report unavailable with a reason naming that fact -- never 0.0 (which would misread as "the
    mapper always resolved ambiguity wrongly") and never 1.0 (which would misread as perfect
    abstention that was never tested).
    """
    ambiguous = [r for r in gold_list if r.outcome is Outcome.AMBIGUOUS]
    denominator = len(ambiguous)
    if denominator == 0:
        return unavailable_metric(
            "the gold set contains no records labelled ambiguous, so true-ambiguity abstention "
            "was not exercised by this run"
        )
    numerator = sum(1 for r in ambiguous if results_by_id[r.expression_id].outcome == "ambiguous")
    return available_metric(numerator, denominator)
