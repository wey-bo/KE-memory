"""Freeze the independent annotation gold for the natural-expression sample.

The artifact records three things a later reader cannot reconstruct: which sample digest was
annotated, what the per-outcome distribution is, and which coverage gaps the out_of_scope labels
found. The gap list is the deliverable that matters most -- it measures the ontology ceiling,
which no amount of mapper tuning can raise.

Every label is checked against the frozen ontology before anything is written, so a gold set
naming an id that O_L1 and O_L2 do not contain cannot reach disk to be scored against.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from ke_memory_demo.core.json import canonical_json
from ke_memory_demo.mapper_v2_validation.annotations import GAP_CATEGORIES, build_annotation_gold
from ke_memory_demo.mapper_v2_validation.loader import (
    GOLD_PATH,
    load_ontology_ids,
    sample_expression_ids,
)
from ke_memory_demo.mapper_v2_validation.models import Outcome

ROOT = Path(".")


def main() -> int:
    gold = build_annotation_gold()

    expected = sample_expression_ids(ROOT)
    labelled = gold.expression_ids()
    missing = sorted(expected - labelled)
    invented = sorted(labelled - expected)
    if missing or invented:
        raise SystemExit(
            f"gold does not cover the sample exactly: missing={missing[:6]} "
            f"invented={invented[:6]}"
        )

    ontology_ids = load_ontology_ids(ROOT)
    unknown = sorted(gold.named_ids() - ontology_ids)
    if unknown:
        raise SystemExit(
            f"labels name ids absent from ontology v2: {unknown[:6]}; a gold label that cites a "
            "nonexistent item scores every mapper wrong for the same reason"
        )

    counts = gold.counts_by_outcome()
    payload: dict[str, Any] = {
        "artifact": gold.artifact,
        "standing": "annotated_independently_of_any_mapper",
        "sample_sha256": gold.sample_sha256,
        "annotated_against_ontology": gold.annotated_against_ontology,
        "judge": gold.judge,
        "model_api_calls": gold.model_api_calls,
        "method": (
            "each expression was read against O_L1, O_L2 and M_L1_to_L2 and labelled with what a "
            "correct mapper should return. No mapper implementation, mapper output, discovery "
            "data or benchmark plan was consulted, and no model was called."
        ),
        "policies": {
            "stated_intention_counts": (
                "a first-person stated intention is memory-worthy even when thin; a bare question "
                "with no self-disclosure is meta-conversation and labelled none"
            ),
            "out_of_scope_is_about_the_principal_assertion": (
                "reserved for expressions whose main claim has no type in v2. Where the main "
                "clause is untyped but a second independent proposition is fully typed, the "
                "record is a concept and the gap is recorded in its note, so the ceiling is "
                "neither overstated nor flattered"
            ),
            "ambiguous_is_a_claim_about_the_text": (
                "ambiguous means the text underdetermines the choice between two or more "
                "defensible items, not that the annotator was unsure"
            ),
        },
        "counts_by_outcome": counts,
        "expression_count": len(gold.records),
        "second_opinion_count": gold.second_opinion_count(),
        "graded_review": (
            "everything was labelled once; novel cases, genuine ambiguity, L2 abstractions and "
            "cases the annotator found hard carry an adjudication note. Clear cases were not "
            "double-reviewed, which is the effort bound the task set"
        ),
        "distinct_ids_named": len(gold.named_ids()),
        "l2_labels_used": sorted(i for i in gold.named_ids() if i.startswith("l2:")),
        "gap_categories": GAP_CATEGORIES,
        "gaps": [
            {
                "expression_id": record.expression_id,
                "sense": record.sense,
                "would_require": record.would_require,
                "adjudication_note": record.adjudication_note,
            }
            for record in gold.gaps()
        ],
        "records": [record.model_dump(mode="json") for record in gold.records],
    }
    payload["gold_sha256"] = hashlib.sha256(canonical_json(payload)).hexdigest()

    output = ROOT / GOLD_PATH
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=1, sort_keys=True), encoding="utf-8")

    print(f"expressions labelled: {len(gold.records)}")
    for outcome in Outcome:
        print(f"  {outcome.value}: {counts[outcome.value]}")
    print(f"second opinions: {gold.second_opinion_count()}")
    print(f"gap categories: {len(GAP_CATEGORIES)}")
    print(f"distinct ontology ids named: {len(gold.named_ids())}")
    print(f"gold sha256: {payload['gold_sha256']}")
    print(f"artifact: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
