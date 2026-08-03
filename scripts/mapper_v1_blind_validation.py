"""Mapper v1 blind validation, run once, with attribution across six classes.

Blind means the mapper receives an utterance and a speaker and nothing else. The gold is loaded in
this process, after the mapping records are produced, and it is never passed to the mapper.

Run once. There is no repair loop: an error keeps its raw output, and a second run after adjusting
the mapper would measure the adjustment. The metrics are reported separately for L1 and L2 because a
combined figure lets a strong layer conceal a weak one.

Attribution assigns every failure to one or more of six classes and never forces a single owner. The
distinction that matters most is between an ontology that lacks an item and a mapper that could not
find one that exists: those call for opposite fixes, and a single ``mis-mapping`` count cannot tell
them apart.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ke_memory_demo.mapper_v1.mapper import (
    Layer,
    MapperInput,
    MapperV1,
    MappingRecord,
    Resolution,
    assert_no_correction_gate,
    load_frozen_ontology,
)
from ke_memory_demo.mapper_v1.mapping_gold import (
    MAPPING_GOLD,
    ExpectedOutcome,
    MappingGoldCase,
    provenance,
    review_counts,
)

ONTOLOGY_DIR = Path("artifacts/ontology-v1")
MAPPER_SOURCE = Path("src/ke_memory_demo/mapper_v1/mapper.py")
REPORT = Path("artifacts/mapper-v1/blind-validation-report.json")
RAW = Path("artifacts/mapper-v1/raw-mapping-records.json")

# The six attribution classes. Ordered for reading only; no order implies priority.
ONTOLOGY_MISSING = "ontology_missing"
ONTOLOGY_DEFECT = "ontology_sense_alias_type_defect"
CANDIDATE_GENERATION = "mapper_candidate_generation"
RANKING = "mapper_ranking_disambiguation"
GENUINE_AMBIGUITY = "genuine_ambiguity"
ANNOTATION_DISAGREEMENT = "annotation_disagreement"


def _attribute(
    case: MappingGoldCase,
    record: MappingRecord,
) -> tuple[list[str], str]:
    """Assign one failure to every class its evidence admits.

    Where the evidence cannot separate two classes, both are returned. A confident single owner
    would be a guess dressed as a finding.
    """
    returned_ids = [c.ontology_id for c in record.candidates]
    top = record.top_ontology_id

    if case.outcome is ExpectedOutcome.UNRESOLVED:
        if record.resolution is Resolution.UNRESOLVED:
            return ([], "correct: declined as required")
        # The mapper fired where nothing should. If gold marked the case novel, the ontology gap is
        # the more likely story; otherwise the mapper over-fired.
        if case.novel:
            return (
                [ONTOLOGY_MISSING, RANKING],
                "fired on an expression the freeze recorded as uncovered; a partial match was "
                "ranked above declining",
            )
        return (
            [RANKING, ONTOLOGY_DEFECT],
            "fired where no item applies; either the ranking floor is too low or an alias is too "
            "broad",
        )

    if case.outcome is ExpectedOutcome.AMBIGUOUS_AMONG:
        if record.resolution is Resolution.AMBIGUOUS and set(case.expected_ids) & set(returned_ids):
            return ([], "correct: reported the ambiguity instead of picking one")
        if record.resolution is Resolution.MAPPED and top in case.expected_ids:
            return (
                [RANKING, GENUINE_AMBIGUITY],
                "collapsed a genuine ambiguity to a single answer; the choice was defensible but "
                "the ambiguity was not reported",
            )
        return (
            [CANDIDATE_GENERATION, GENUINE_AMBIGUITY],
            "did not surface the competing readings at all",
        )

    # ExpectedOutcome.MAPS_TO
    if top in case.expected_ids:
        return ([], "correct")
    if set(case.expected_ids) & set(returned_ids):
        return (
            [RANKING],
            "the correct item was generated but ranked below another candidate",
        )
    if record.resolution is Resolution.UNRESOLVED:
        return (
            [CANDIDATE_GENERATION, ONTOLOGY_DEFECT],
            "generated no candidate for an item that exists; either retrieval missed it or its "
            "aliases do not cover this phrasing",
        )
    if case.review.value == "double_review":
        return (
            [RANKING, ANNOTATION_DISAGREEMENT],
            "mapped to a different item on a case the reviewers themselves flagged as disputed",
        )
    return (
        [RANKING, ONTOLOGY_DEFECT],
        "mapped to the wrong existing item; either ranking or an over-broad alias",
    )


def _metrics(
    cases: tuple[MappingGoldCase, ...],
    records: dict[str, MappingRecord],
) -> dict[str, Any]:
    """Metrics for one layer. Every rate carries its denominator."""
    total = len(cases)
    if not total:
        return {"case_count": 0}

    positives = [c for c in cases if c.outcome is ExpectedOutcome.MAPS_TO]
    negatives = [c for c in cases if c.outcome is ExpectedOutcome.UNRESOLVED]

    resolved = sum(
        1 for c in cases if records[c.case_id].resolution is not Resolution.UNRESOLVED
    )
    correct_sense = sum(
        1
        for c in positives
        if records[c.case_id].top_ontology_id in c.expected_ids
    )
    mis_mapped = sum(
        1
        for c in positives
        if records[c.case_id].resolution is not Resolution.UNRESOLVED
        and records[c.case_id].top_ontology_id not in c.expected_ids
    )
    ambiguous = sum(
        1 for c in cases if records[c.case_id].resolution is Resolution.AMBIGUOUS
    )
    unresolved = sum(
        1 for c in cases if records[c.case_id].resolution is Resolution.UNRESOLVED
    )
    # A false merge collapses two distinct expected items into one answer; a false split reports
    # several where gold names exactly one.
    false_merge = sum(
        1
        for c in cases
        if len(c.expected_ids) > 1
        and records[c.case_id].resolution is Resolution.MAPPED
    )
    false_split = sum(
        1
        for c in positives
        if len(c.expected_ids) == 1
        and records[c.case_id].resolution is Resolution.AMBIGUOUS
    )
    false_positive = sum(
        1
        for c in negatives
        if records[c.case_id].resolution is not Resolution.UNRESOLVED
    )

    return {
        "case_count": total,
        "positive_cases": len(positives),
        "negative_cases": len(negatives),
        "coverage": resolved / total,
        "coverage_note": "fraction of cases where the mapper returned any candidate",
        "sense_accuracy": (correct_sense / len(positives)) if positives else None,
        "sense_accuracy_denominator": len(positives),
        "mis_mapping_rate": (mis_mapped / len(positives)) if positives else None,
        "ambiguity_rate": ambiguous / total,
        "unresolved_rate": unresolved / total,
        "false_merge": false_merge,
        "false_split": false_split,
        "false_positive_on_negatives": false_positive,
        "false_positive_denominator": len(negatives),
    }


def main() -> int:
    assert_no_correction_gate(MAPPER_SOURCE.read_text(encoding="utf-8"))

    ontology = load_frozen_ontology(ONTOLOGY_DIR)
    mapper = MapperV1(ontology)

    # Blind phase: the mapper sees an utterance and a speaker. Gold is not in scope here.
    records: dict[str, MappingRecord] = {}
    for case in MAPPING_GOLD:
        layer = Layer.L1 if case.layer == "l1" else Layer.L2
        records[case.case_id] = mapper.map_expression(
            MapperInput(
                expression_id=f"expr-{case.case_id.lower().replace('-', '')}",
                speaker="user",
                text=case.text,
            ),
            layer,
        )

    RAW.parent.mkdir(parents=True, exist_ok=True)
    RAW.write_text(
        json.dumps(
            {
                "note": (
                    "raw mapper output, preserved exactly as produced. No error here is corrected "
                    "downstream."
                ),
                "mapper_identity": mapper.identity,
                "records": {k: v.model_dump(mode="json") for k, v in records.items()},
            },
            indent=1,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    # Scoring phase: gold is consulted only now.
    attributions: list[dict[str, Any]] = []
    class_counts: dict[str, int] = {}
    for case in MAPPING_GOLD:
        classes, note = _attribute(case, records[case.case_id])
        for name in classes:
            class_counts[name] = class_counts.get(name, 0) + 1
        attributions.append(
            {
                "case_id": case.case_id,
                "layer": case.layer,
                "expected_outcome": str(case.outcome),
                "expected_ids": list(case.expected_ids),
                "observed_resolution": str(records[case.case_id].resolution),
                "observed_top": records[case.case_id].top_ontology_id,
                "correct": not classes,
                "possible_classes": sorted(classes),
                "note": note,
                "review": case.review.value,
            }
        )

    l1_cases = tuple(c for c in MAPPING_GOLD if c.layer == "l1")
    l2_cases = tuple(c for c in MAPPING_GOLD if c.layer == "l2")
    correct = sum(1 for a in attributions if a["correct"])

    report: dict[str, Any] = {
        "stage": "mapper-v1-blind-validation",
        "standing": "diagnostic",
        "run_discipline": (
            "one run. No repair loop, no post-hoc correction, and no second run after adjusting the "
            "mapper, which would measure the adjustment."
        ),
        "blindness": {
            "mapper_inputs": ["expression_id (opaque)", "speaker", "text"],
            "forbidden_and_absent": [
                "question",
                "gold",
                "split",
                "dataset name",
                "sample id",
            ],
            "enforced_by": (
                "MapperInput has no field for any of these and forbids extras; expression_id is "
                "rejected if it discloses dataset identity"
            ),
            "gold_consulted_after_mapping": True,
        },
        "mapper_identity": mapper.identity,
        "mapper_freeze_hash": mapper.freeze_hash(),
        "gold_provenance": provenance(),
        "review_counts": review_counts(),
        "overall": {
            "cases": len(MAPPING_GOLD),
            "correct": correct,
            "correct_rate": correct / len(MAPPING_GOLD),
        },
        "metrics_l1": _metrics(l1_cases, records),
        "metrics_l2": _metrics(l2_cases, records),
        "attribution": {
            "classes": [
                ONTOLOGY_MISSING,
                ONTOLOGY_DEFECT,
                CANDIDATE_GENERATION,
                RANKING,
                GENUINE_AMBIGUITY,
                ANNOTATION_DISAGREEMENT,
            ],
            "class_mentions": dict(sorted(class_counts.items())),
            "rule": (
                "a failure is assigned to every class its evidence admits; no single owner is "
                "forced. The mentions therefore sum above the failure count."
            ),
            "per_case": attributions,
        },
        "caveats": [
            "the mapper is lexical, so these figures bound a lexical mapper over a seed ontology "
            "and are not a production mapping capability",
            "18 authored cases is a small gold set; it detects gross behaviour, not fine accuracy",
            "the ontology is the seed freeze, and three external sources were unavailable when it "
            "was built, so an ontology_missing attribution may reflect that debt",
        ],
        "judge": "not called",
    }
    REPORT.write_text(json.dumps(report, indent=1, sort_keys=True), encoding="utf-8")

    print(f"mapper: {mapper.identity['mapper_id']} | hash {mapper.freeze_hash()[:16]}")
    print(f"gold cases: {len(MAPPING_GOLD)} (single {review_counts()['single_review']}, "
          f"double {review_counts()['double_review']})")
    print(f"correct: {correct}/{len(MAPPING_GOLD)}")
    for name, metrics in (("L1", report["metrics_l1"]), ("L2", report["metrics_l2"])):
        print(
            f"{name}: coverage={metrics['coverage']:.3f} "
            f"sense_acc={metrics['sense_accuracy']} "
            f"mis_map={metrics['mis_mapping_rate']} "
            f"ambig={metrics['ambiguity_rate']:.3f} "
            f"unres={metrics['unresolved_rate']:.3f} "
            f"merge={metrics['false_merge']} split={metrics['false_split']} "
            f"fp_neg={metrics['false_positive_on_negatives']}/"
            f"{metrics['false_positive_denominator']}"
        )
    print("attribution (no forced owner):")
    for name, count in report["attribution"]["class_mentions"].items():
        print(f"  {name:<38} {count}")
    print(f"raw records: {RAW}")
    print(f"report: {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
