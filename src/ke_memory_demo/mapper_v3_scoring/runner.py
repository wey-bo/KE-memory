"""Orchestration that turns a scored report into a JSON-serialisable artifact dict.

``build_report_artifact`` takes an already-loaded :class:`AnnotationGold` and an already-built
sequence of mapping results -- it does not load anything from disk and does not know where either
came from. That is deliberate: this module is the seam between "someone else produced a gold object
and a mapper's results" and "here is the report", and it must stay usable with synthetic fixtures in
tests for exactly the same reason the scorer must.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Final, cast

from ke_memory_demo.core.json import JsonObject, canonical_json
from ke_memory_demo.mapper_v3_validation.models import AnnotationGold

from .models import ScoringReport
from .scorer import MappingResult, score

# Denominators stated in words, keyed by the report field they describe, so a reader of the artifact
# cannot misread which population a metric's rate is over by looking at the number alone.
METRICS_DEFINITIONS: Final[JsonObject] = {
    "ontology_coverage": (
        "denominator: every gold record in this run. numerator: gold records whose outcome is not "
        "out_of_scope. Measures the combined ontology's expressiveness, not the mapper -- computed "
        "from gold labels alone."
    ),
    "candidate_recall.micro": (
        "denominator: the total count of individual gold target ids across id-bearing "
        "(concept/ambiguous) gold records, summed one by one. numerator: how many of those "
        "individual ids appear in the corresponding mapping result's target_ids. out_of_scope and "
        "none records contribute no ids and are excluded."
    ),
    "candidate_recall.macro": (
        "denominator: the count of id-bearing (concept/ambiguous) gold records. numerator: how "
        "many of those records had every one of their gold target ids recalled by the mapping "
        "result (full per-expression recall, not partial credit)."
    ),
    "ranking_or_sense_accuracy": (
        "denominator: id-bearing (concept/ambiguous) gold records whose mapping result returned "
        "at least one target id. numerator: of those, how many had a mapping result whose "
        "target_ids were a subset of, or equal to, the gold target_ids. Expressions the mapper "
        "left unresolved are excluded from this denominator; they are covered by "
        "no_map_behaviour.missed_content instead."
    ),
    "no_map_behaviour.correct_abstention": (
        "denominator: gold records labelled none. numerator: how many of those the mapper reported "
        "as outcome unresolved."
    ),
    "no_map_behaviour.missed_content": (
        "denominator: id-bearing (concept/ambiguous) gold records. numerator: how many of those "
        "the mapper incorrectly reported as outcome unresolved, despite gold naming real content."
    ),
    "multi_label_selection.multi_label_selection": (
        "denominator: gold records naming more than one target id. numerator: how many of those "
        "the mapper answered with more than one target id."
    ),
    "multi_label_selection.incomplete_multi_label_selection": (
        "denominator: gold records naming more than one target id (same population as "
        "multi_label_selection). numerator: how many of those the mapper answered with one target "
        "id or none -- an incomplete multi-label answer, not a merge of distinct gold targets into "
        "a single wrong one."
    ),
    "critical_false_mapping": (
        "denominator: gold records labelled none or out_of_scope combined. numerator: how many of "
        "those the mapper nevertheless answered with one or more target ids. The most important "
        "failure class in this report: inventing structure where gold says there is none, whether "
        "because the content is not memory-worthy or because the combined ontology cannot express "
        "it."
    ),
    "true_ambiguity_abstention": (
        "denominator: gold records labelled ambiguous. numerator: how many of those the mapper "
        "reported as outcome ambiguous. This round's gold is expected to contain zero ambiguous "
        "records, in which case this metric reports unavailable rather than 0.0 or 1.0."
    ),
    "ontology_gap": (
        "not a rate: the explicit list of gold records labelled out_of_scope, which are removed "
        "from every recall and accuracy denominator above before it is computed."
    ),
}


def build_report(
    gold: AnnotationGold,
    mapping_results: Iterable[MappingResult],
    allowed_target_ids: frozenset[str],
) -> ScoringReport:
    """Score ``mapping_results`` against ``gold.records`` and return the validated report model."""
    return score(gold.records, mapping_results, allowed_target_ids)


def build_report_artifact(
    gold: AnnotationGold,
    mapping_results: Iterable[MappingResult],
    allowed_target_ids: frozenset[str],
) -> JsonObject:
    """Score ``mapping_results`` against ``gold.records`` and return a JSON-serialisable artifact.

    The artifact carries the report itself, the digest of the gold it was scored against (so the
    artifact can be checked against a specific gold version later), and ``metrics_definitions`` in
    words for every metric family.
    """
    report = build_report(gold, mapping_results, allowed_target_ids)
    payload = _normalize_json_object(report)
    return {
        "artifact": "mapper-v3 scoring report",
        "scored_against_gold_sha256": gold.digest,
        "report": payload,
        "metrics_definitions": dict(METRICS_DEFINITIONS),
    }


def _normalize_json_object(report: ScoringReport) -> JsonObject:
    return cast(JsonObject, json.loads(canonical_json(report)))
