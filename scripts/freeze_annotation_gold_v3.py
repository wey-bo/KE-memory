"""Freeze the v3 annotation gold for the fresh 160-expression mapping set.

Every check the v2 freeze ran is repeated here against the *combined* id inventory, plus three
this round needs and the previous one did not:

- ``ambiguous`` came out empty. That is recorded as a named evaluation limitation rather than left
  for a reader to notice from the distribution, because a scorer that computes an abstention rate
  over an empty denominator would report a number where there is no evidence.
- The v3 additions each label rests on are counted, so "v3 helped" is a figure in the artifact
  rather than an inference from id prefixes at scoring time.
- The ontology gaps the annotation surfaced are recorded as *accounted* rather than fixed. The
  round forbids touching a frozen unit, so the deliverable is an accounting entry, not a patch.

The gold digest is computed over the payload *without* the digest field, so re-running this script
on unchanged labels reproduces it exactly.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Final

from ke_memory_demo.core.json import canonical_json
from ke_memory_demo.mapper_v3_validation.annotations import GAP_CATEGORIES, build_annotation_gold
from ke_memory_demo.mapper_v3_validation.loader import (
    GOLD_PATH,
    load_combined_ontology_ids,
    load_v3_added_ids,
    mapping_set_digest,
    mapping_set_expression_ids,
)
from ke_memory_demo.mapper_v3_validation.models import Outcome

ROOT = Path(".")

# Written by the annotator, before any mapper was run against this set. Recorded in the artifact so
# the limitation travels with the gold instead of living in a review thread.
KNOWN_ONTOLOGY_GAPS: Final[tuple[dict[str, str], ...]] = (
    {
        "gap": "habit_derivation_bound_to_media_consumption",
        "unit": "M_L1_to_L2 (v2)",
        "observed_at": "fx-000120, fx-000148",
        "detail": (
            "m:abstraction.habit names l1:event.media_consumption and l1:predicate.consume_media "
            "among its sources, but l2:abstraction.habit's sense is general. A weekly gym "
            "schedule and a weekly language class are uncontroversial habits that cannot reach "
            "the item through its own derivation rule, so the item's sense is wider than the "
            "rule that admits it"
        ),
        "disposition": "accounted, not fixed; this round forbids modifying a frozen unit",
    },
    {
        "gap": "kinship_lacks_collateral_descent",
        "unit": "O_L2 (v2)",
        "observed_at": "fx-000121",
        "detail": (
            "l2:relation.* offers kin_descent (direct, asymmetric) and kin_lateral (same "
            "generation, symmetric). A niece is collateral descent and fits neither, so the tie "
            "was labelled l2:abstraction.relationship with no relation kind"
        ),
        "disposition": "accounted, not fixed; this round forbids modifying a frozen unit",
    },
    {
        "gap": "circumstance_cannot_say_medical",
        "unit": "O_L1 (v2)",
        "observed_at": "fx-000066, fx-000124, fx-000156",
        "detail": (
            "l1:state.circumstance will hold a named diagnosis, so a label exists, but it cannot "
            "record that the condition is medical. A memory carrying only that label cannot "
            "answer a question about the subject's health, which is why the earlier turn was "
            "labelled a gap even though an item was technically available"
        ),
        "disposition": "accounted, not fixed; this round forbids modifying a frozen unit",
    },
)

# A finding of a different kind from the three above, kept separate on purpose. It is neither an
# ontology gap nor a mapper failure, so folding it into either list would misfile it.
UNATTESTED_V3_ADDITIONS: Final[tuple[dict[str, str], ...]] = (
    {
        "item": "l2:abstraction.value_commitment",
        "kind": "addition_the_fresh_evidence_does_not_license",
        "detail": (
            "admitted to O_v3 because the earlier sample's out_of_scope labels showed no way to "
            "hold a subject's own value ranking. Its derivation m3-001 requires two of "
            "l1:predicate.hold_value, l1:predicate.hold_belief and l1:state.ongoing_pursuit to "
            "support one commitment. Across these 160 expressions hold_value appears 8 times and "
            "hold_belief 9, but never converging on a single commitment, so the L2 item is "
            "attested zero times"
        ),
        "not_evidence_of": (
            "neither that the item is wrong nor that the mapper failed; the fresh corpus simply "
            "never crossed its two-source threshold"
        ),
        "disposition": (
            "recorded as speculative on this corpus; the item is left in place and the threshold "
            "is left unlowered, since lowering it to earn a label would be tuning the ontology to "
            "the evaluation set"
        ),
    },
)


def main() -> int:
    gold = build_annotation_gold()

    expected = mapping_set_expression_ids(ROOT)
    labelled = gold.expression_ids()
    missing = sorted(expected - labelled)
    invented = sorted(labelled - expected)
    if missing or invented:
        raise SystemExit(
            f"gold does not cover the fresh set exactly: missing={missing[:6]} "
            f"invented={invented[:6]}"
        )
    if len(gold.records) != len(expected):
        raise SystemExit(
            f"gold holds {len(gold.records)} records for {len(expected)} expressions; the model "
            "rejects duplicates, so a mismatch here means the set itself changed"
        )

    recorded_set_digest = mapping_set_digest(ROOT)
    if gold.annotated_set_sha256 != recorded_set_digest:
        raise SystemExit(
            f"gold was annotated against {gold.annotated_set_sha256} but the set on disk records "
            f"{recorded_set_digest}; a gold bound to a different draw cannot be scored against "
            "this one"
        )

    ontology_ids = load_combined_ontology_ids(ROOT)
    unknown = sorted(gold.named_ids() - ontology_ids)
    if unknown:
        raise SystemExit(
            f"labels name ids absent from ontology v2 + v3: {unknown[:6]}; a gold label citing a "
            "nonexistent item scores every mapper wrong for the same reason"
        )

    counts = gold.counts_by_outcome()
    v3_added = load_v3_added_ids(ROOT)
    payload = _build_payload(gold, counts, ontology_ids, v3_added, recorded_set_digest)
    payload["gold_sha256"] = hashlib.sha256(canonical_json(payload)).hexdigest()

    output = ROOT / GOLD_PATH
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=1, sort_keys=True), encoding="utf-8")

    print(f"expressions labelled: {len(gold.records)}")
    for outcome in Outcome:
        print(f"  {outcome.value}: {counts[outcome.value]}")
    print(f"second opinions: {gold.second_opinion_count()}")
    print(f"distinct ontology ids named: {len(gold.named_ids())}")
    print(f"labels resting on a v3 addition: {len(gold.v3_absorbed_records())}")
    print(f"known ontology gaps accounted: {len(KNOWN_ONTOLOGY_GAPS)}")
    print(f"gold sha256: {payload['gold_sha256']}")
    print(f"in-memory digest: {gold.digest}")
    print(f"artifact: {output}")
    return 0


def _build_payload(
    gold: Any,
    counts: dict[str, int],
    ontology_ids: frozenset[str],
    v3_added: frozenset[str],
    recorded_set_digest: str,
) -> dict[str, Any]:
    """Assemble everything a later reader needs, with the digest field left to the caller."""
    return {
        "artifact": gold.artifact,
        "standing": "annotated_without_running_any_mapper",
        "annotated_set_sha256": gold.annotated_set_sha256,
        "set_digest_on_disk": recorded_set_digest,
        "annotated_against_ontology": gold.annotated_against_ontology,
        "judge": gold.judge,
        "model_api_calls": gold.model_api_calls,
        "method": (
            "each expression was read against O_v2 and the O_v3 additions and labelled with what a "
            "correct mapper should return. No mapper output was consulted for any record and no "
            "model or judge was called."
        ),
        "isolation_limit": {
            "claim": "no mapper output informed any label",
            "evidence_strength": "procedural_declaration_not_artifact_proof",
            "detail": (
                "the first 120 labels and the last 40 were written after mapper v3 already "
                "existed in the same working tree, so the independence of the annotation line "
                "cannot be demonstrated from timestamps. What can be shown is that the "
                "annotation package imports no mapper module and that the mapper package "
                "references neither the set nor the gold. The stronger claim -- that the "
                "annotator did not read mapper output -- is a procedural declaration"
            ),
        },
        "evaluation_limits": {
            "true_ambiguity_abstention": {
                "status": "unavailable",
                "reason": (
                    "the gold contains zero ambiguous records, so the population over which a "
                    "mapper's abstention on genuine ambiguity would be measured is empty. Any "
                    "scorer reporting a rate here is reporting a number with no evidence behind it"
                ),
                "why_empty": (
                    "borderline expressions were resolved either as multi-target concepts naming "
                    "every defensible item, or by withholding the unsupported label. Neither "
                    "route produces an ambiguous record, so the absence is a consequence of the "
                    "annotation convention rather than of the corpus"
                ),
                "not_backfilled": (
                    "ambiguous records were not manufactured after the fact to give the metric a "
                    "denominator"
                ),
            }
        },
        "policies": {
            "qualifier_dimensions_not_listed": (
                "l1:qualifier.* names an axis, not a value on it; the value items are what an "
                "expression attests"
            ),
            "roles_not_listed_except_when_attested": (
                "a role is a slot every frame of its kind requires, so listing roles would add a "
                "constant to every record. Three records name one: fx-000056 and fx-000143 for a "
                "stated count, fx-000139 for the beneficiary the whole selection is for"
            ),
            "out_of_scope_is_about_the_principal_assertion": (
                "reserved for expressions whose main claim has no type in v2 or v3. Where the main "
                "clause is untyped but a second proposition is fully typed, the record is a "
                "concept and the gap is recorded in its note"
            ),
            "ambiguous_is_a_claim_about_the_text": (
                "ambiguous means the text underdetermines the choice between two or more "
                "defensible items, not that the annotator was unsure. It was never invoked"
            ),
            "third_party_bearers": (
                "a label is withheld when the attested state belongs to another party and the "
                "subject is only reporting it; where the tie itself is the content, the "
                "relationship items carry it"
            ),
        },
        "counts_by_outcome": counts,
        "expression_count": len(gold.records),
        "second_opinion_count": gold.second_opinion_count(),
        "targets_per_expression": gold.targets_per_expression(),
        "multi_target_count": len(gold.multi_target_records()),
        "graded_review": (
            "everything was labelled once; v3 additions, L2 abstractions, ambiguity, gaps and "
            "cases the annotator found hard carry an adjudication note"
        ),
        "distinct_ids_named": len(gold.named_ids()),
        "ontology_ids_available": len(ontology_ids),
        "ids_never_named": sorted(ontology_ids - gold.named_ids()),
        "l2_labels_used": sorted(i for i in gold.named_ids() if i.startswith("l2:")),
        "v3_additions_available": sorted(v3_added),
        "v3_absorption_by_item": gold.v3_absorption_by_item(),
        "records_resting_on_v3": len(gold.v3_absorbed_records()),
        "gap_categories": list(GAP_CATEGORIES),
        "gaps": [
            {
                "expression_id": record.expression_id,
                "sense": record.sense,
                "would_require": record.would_require,
                "adjudication_note": record.adjudication_note,
            }
            for record in gold.gaps()
        ],
        "known_ontology_gaps_accounted": list(KNOWN_ONTOLOGY_GAPS),
        "unattested_v3_additions": list(UNATTESTED_V3_ADDITIONS),
        "records": [record.model_dump(mode="json") for record in gold.records],
    }


if __name__ == "__main__":
    raise SystemExit(main())
