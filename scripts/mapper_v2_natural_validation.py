"""One-shot natural mapping validation. Consumes the frozen sample exactly once.

This is the measurement the whole sequence was built to reach, and it is spent on running. There is
no repair loop: if a number is poor, that is the result. Adjusting the mapper and re-running would
measure the adjustment, and the sample would no longer be a blind test of anything.

Seven metric families, reported separately for L1 and L2, because a single figure lets one hide
inside another. The most important separation is the first one:

``ontology ceiling``
    Does the correct target exist in the ontology at all? A mapper cannot be blamed for missing an
    item that was never admitted, and an ontology cannot be credited for a mapper's ranking.

``candidate recall``
    When the target does exist, does it reach top-k? This isolates generation from ranking.

``ranking and sense accuracy``
    Given recall, is the right item first?

``ambiguity and unresolved``
    Reported as rates with their denominators.

``no-map precision and recall``
    Split further: gold ``none`` means the ontology should not cover the expression, gold
    ``out_of_scope`` means it cannot. Both expect no_map, and conflating them would let a ceiling
    failure look like correct abstention.

``false mapping, false merge, false split``
    A false merge collapses distinct gold targets into one answer; a false split reports several
    where gold names one.

The L1/L2 asymmetry is carried into the report rather than smoothed over: gold names 231 L1 targets
against 5 L2, so L2 rates are printed with their denominator and must not be read as comparable.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

from ke_memory_demo.core.json import canonical_json
from ke_memory_demo.mapper_v2.mapper_v2 import ExpressionInput, MapperV2, Outcome

ONTOLOGY_DIR = Path("artifacts/ontology-v2")
SAMPLE = Path("artifacts/mapper-v2-validation/natural-expression-sample.json")
GOLD = Path("artifacts/mapper-v2-validation/annotation-gold.json")
RAW = Path("artifacts/mapper-v2-validation/raw-mapper-output.json")
REPORT = Path("artifacts/mapper-v2-validation/validation-report.json")

# Gold outcomes that expect the mapper to decline, kept distinct because they mean different things.
EXPECTS_NO_MAP = {"none", "out_of_scope"}


def _load(path: Path) -> dict[str, Any]:
    return cast("dict[str, Any]", json.loads(path.read_text(encoding="utf-8")))


def _metrics(
    layer: str,
    records: list[dict[str, Any]],
    ontology_ids: set[str],
) -> dict[str, Any]:
    """Metrics for one layer. Every rate carries the denominator it was computed over."""
    # Cases where gold names a target at this layer.
    positives = [
        r
        for r in records
        if r["gold_outcome"] in {"concept", "ambiguous"}
        and any(t.startswith(f"{layer}:") for t in r["gold_target_ids"])
    ]
    negatives = [r for r in records if r["gold_outcome"] in EXPECTS_NO_MAP]
    gold_none = [r for r in records if r["gold_outcome"] == "none"]
    gold_out_of_scope = [r for r in records if r["gold_outcome"] == "out_of_scope"]

    # Ceiling: of the gold targets at this layer, how many exist in the ontology at all.
    named = {t for r in positives for t in r["gold_target_ids"] if t.startswith(f"{layer}:")}
    present = {t for t in named if t in ontology_ids}

    in_topk = [
        r
        for r in positives
        if set(t for t in r["gold_target_ids"] if t.startswith(f"{layer}:"))
        & set(r["candidate_ids"])
    ]
    ranked_first = [r for r in in_topk if r["top_ontology_id"] in r["gold_target_ids"]]

    declined = [r for r in records if r["outcome"] == str(Outcome.NO_MAP)]
    declined_correctly = [r for r in declined if r["gold_outcome"] in EXPECTS_NO_MAP]
    false_mapping_on_none = [
        r for r in gold_none if r["outcome"] != str(Outcome.NO_MAP)
    ]
    false_mapping_on_out_of_scope = [
        r for r in gold_out_of_scope if r["outcome"] != str(Outcome.NO_MAP)
    ]

    multi_target = [r for r in positives if len(r["gold_target_ids"]) > 1]
    single_target = [r for r in positives if len(r["gold_target_ids"]) == 1]
    false_merge = [r for r in multi_target if r["outcome"] == str(Outcome.MAPPED)]
    false_split = [r for r in single_target if r["outcome"] == str(Outcome.AMBIGUOUS)]

    def rate(count: int, total: int) -> float | None:
        return round(count / total, 4) if total else None

    return {
        "layer": layer,
        "positive_cases": len(positives),
        "negative_cases": len(negatives),
        "ontology_ceiling": {
            "gold_targets_named": len(named),
            "gold_targets_present_in_ontology": len(present),
            "ceiling": rate(len(present), len(named)),
            "missing_targets": sorted(named - present),
            "reading": (
                "the share of gold targets the ontology contains. A mapper cannot recover what was "
                "never admitted, so this bounds every metric below it."
            ),
        },
        "candidate_recall": {
            "cases": len(positives),
            "target_in_top_k": len(in_topk),
            "recall": rate(len(in_topk), len(positives)),
            "reading": "when the target exists, does generation surface it at all",
        },
        "ranking_accuracy": {
            "cases_with_target_in_top_k": len(in_topk),
            "ranked_first": len(ranked_first),
            "accuracy": rate(len(ranked_first), len(in_topk)),
            "reading": "given recall, is the correct item first; isolates ranking from generation",
        },
        "end_to_end_correct": {
            "cases": len(positives),
            "correct": len(ranked_first),
            "rate": rate(len(ranked_first), len(positives)),
        },
        "ambiguity": {
            "ambiguous_results": sum(
                1 for r in records if r["outcome"] == str(Outcome.AMBIGUOUS)
            ),
            "rate_over_all_cases": rate(
                sum(1 for r in records if r["outcome"] == str(Outcome.AMBIGUOUS)),
                len(records),
            ),
        },
        "no_map": {
            "declined": len(declined),
            "declined_correctly": len(declined_correctly),
            "precision": rate(len(declined_correctly), len(declined)),
            "recall": rate(len(declined_correctly), len(negatives)),
            "false_mapping_on_gold_none": len(false_mapping_on_none),
            "false_mapping_on_gold_none_rate": rate(
                len(false_mapping_on_none), len(gold_none)
            ),
            "false_mapping_on_out_of_scope": len(false_mapping_on_out_of_scope),
            "false_mapping_on_out_of_scope_rate": rate(
                len(false_mapping_on_out_of_scope), len(gold_out_of_scope)
            ),
            "reading": (
                "gold none and out_of_scope both expect a decline but mean different things: none is "
                "content the ontology should not cover, out_of_scope is content it cannot. Mapping an "
                "out_of_scope expression is a ceiling failure wearing the costume of a false positive."
            ),
        },
        "merge_and_split": {
            "multi_target_cases": len(multi_target),
            "false_merge": len(false_merge),
            "single_target_cases": len(single_target),
            "false_split": len(false_split),
        },
    }


def main() -> int:
    sample = _load(SAMPLE)
    gold = _load(GOLD)

    if gold["sample_sha256"] != sample["sample_sha256"]:
        print("FAIL: the gold does not bind the frozen sample")
        return 1

    ontology_ids: set[str] = set()
    for filename in ("o_l1.json", "o_l2.json"):
        document = _load(ONTOLOGY_DIR / filename)
        for wrapper in cast("list[Any]", document["items"]):
            item = cast("dict[str, Any]", cast("dict[str, Any]", wrapper)["item"])
            ontology_ids.add(str(item["id"]))

    mapper = MapperV2(ONTOLOGY_DIR)
    gold_by_id = {
        str(r["expression_id"]): cast("dict[str, Any]", r)
        for r in cast("list[Any]", gold["records"])
    }

    raw_output: dict[str, Any] = {}
    per_layer: dict[str, list[dict[str, Any]]] = {"l1": [], "l2": []}

    for entry in cast("list[Any]", sample["expressions"]):
        expression = cast("dict[str, Any]", entry)
        expression_id = str(expression["expression_id"])
        label = gold_by_id.get(expression_id)
        if label is None:
            continue
        request = ExpressionInput(
            expression_id=expression_id,
            speaker=str(expression["speaker"]),
            text=str(expression["text"]),
        )
        for layer in ("l1", "l2"):
            result = mapper.map_expression(request, layer)
            # Raw output preserved exactly as produced: no error here is corrected downstream.
            raw_output.setdefault(expression_id, {})[layer] = result.model_dump(mode="json")
            per_layer[layer].append(
                {
                    "expression_id": expression_id,
                    "outcome": str(result.outcome),
                    "top_ontology_id": result.top_ontology_id,
                    "candidate_ids": [
                        str(cast("dict[str, Any]", c)["ontology_id"])
                        for c in result.candidates
                    ],
                    "competing": list(result.competing_ontology_ids),
                    "gold_outcome": str(label["outcome"]),
                    "gold_target_ids": [str(t) for t in label.get("target_ids", [])],
                    "needs_second_opinion": bool(label.get("needs_second_opinion", False)),
                }
            )

    RAW.parent.mkdir(parents=True, exist_ok=True)
    RAW.write_text(
        json.dumps(
            {
                "note": (
                    "raw mapper output for every expression at both layers, preserved as produced. "
                    "No result here was corrected, re-ranked or re-run."
                ),
                "mapper_identity": mapper.identity,
                "mapper_freeze_hash": mapper.freeze_hash(),
                "sample_sha256": sample["sample_sha256"],
                "gold_sha256": gold["gold_sha256"],
                "results": raw_output,
            },
            indent=1,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    report: dict[str, Any] = {
        "artifact": "one-shot natural mapping validation",
        "standing": "immutable_result",
        "run_discipline": (
            "one run over the frozen sample. No threshold was adjusted, no alias added, no output "
            "corrected, and the sample was not re-run. A second run after any change would measure "
            "the change."
        ),
        "inputs": {
            "sample_sha256": sample["sample_sha256"],
            "gold_sha256": gold["gold_sha256"],
            "mapper_freeze_hash": mapper.freeze_hash(),
            "mapper_identity": mapper.identity,
            "expressions": len(per_layer["l1"]),
        },
        "layer_paths": {
            "l1": "recognition from lexical and structural evidence",
            "l2": "derivation over attested L1 items through M_L1_to_L2",
            "why_reported_separately": (
                "the two layers take different paths, so one figure spanning both would describe "
                "neither"
            ),
        },
        "metrics_l1": _metrics("l1", per_layer["l1"], ontology_ids),
        "metrics_l2": _metrics("l2", per_layer["l2"], ontology_ids),
        "l2_denominator_warning": (
            "gold names 5 L2 targets against 231 L1 references, so every L2 rate rests on very few "
            "cases and must be read with its denominator rather than compared to L1"
        ),
        "graded_review": gold.get("graded_review"),
        "second_opinion_count": gold.get("second_opinion_count"),
        "gap_categories_from_annotation": gold.get("gap_categories"),
        "caveats": [
            "the mapper is lexical and structural over a recovered candidate ontology freeze, not a "
            "production mapping system",
            "120 expressions bound the resolution of every rate here",
            "an ontology_ceiling below 1.0 caps every metric beneath it, so a low end-to-end figure "
            "may be an ontology result rather than a mapper result",
        ],
        "judge": "not called",
    }
    report["report_sha256"] = hashlib.sha256(canonical_json(report)).hexdigest()
    REPORT.write_text(json.dumps(report, indent=1, sort_keys=True), encoding="utf-8")

    print(f"expressions: {report['inputs']['expressions']}")
    print(f"mapper: {mapper.freeze_hash()[:16]}")
    for name in ("metrics_l1", "metrics_l2"):
        m = report[name]
        ceiling = m["ontology_ceiling"]
        print(f"\n--- {m['layer'].upper()} ({m['positive_cases']} positive, {m['negative_cases']} negative)")
        print(
            f"  ontology ceiling   {ceiling['ceiling']} "
            f"({ceiling['gold_targets_present_in_ontology']}/{ceiling['gold_targets_named']})"
        )
        print(
            f"  candidate recall   {m['candidate_recall']['recall']} "
            f"({m['candidate_recall']['target_in_top_k']}/{m['candidate_recall']['cases']})"
        )
        print(
            f"  ranking accuracy   {m['ranking_accuracy']['accuracy']} "
            f"({m['ranking_accuracy']['ranked_first']}/"
            f"{m['ranking_accuracy']['cases_with_target_in_top_k']})"
        )
        print(f"  end to end         {m['end_to_end_correct']['rate']}")
        print(f"  ambiguity rate     {m['ambiguity']['rate_over_all_cases']}")
        nm = m["no_map"]
        print(
            f"  no-map precision   {nm['precision']} | recall {nm['recall']} "
            f"({nm['declined_correctly']}/{nm['declined']} declined correctly)"
        )
        print(
            f"  false map on none  {nm['false_mapping_on_gold_none']} "
            f"({nm['false_mapping_on_gold_none_rate']}) | "
            f"on out_of_scope {nm['false_mapping_on_out_of_scope']} "
            f"({nm['false_mapping_on_out_of_scope_rate']})"
        )
        ms = m["merge_and_split"]
        print(
            f"  false merge {ms['false_merge']}/{ms['multi_target_cases']} | "
            f"false split {ms['false_split']}/{ms['single_target_cases']}"
        )
    print(f"\nraw output: {RAW}")
    print(f"report: {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
