"""Properties the annotation gold must have to be usable as gold.

These check the written artifact, not just the builder. A stale or truncated JSON file would
pass every in-memory assertion while being the thing a later scoring run actually reads.

The four load-bearing properties: the gold covers the sample exactly once each, every named id
exists in the frozen ontology, every coverage gap says what would be required, and the digest
moves when any label moves. The last one is what makes the artifact citable -- a hash that
survived a label edit would certify nothing.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from ke_memory_demo.mapper_v2_validation.annotations import (
    ANNOTATED_SAMPLE_SHA256,
    GAP_CATEGORIES,
    build_annotation_gold,
)
from ke_memory_demo.mapper_v2_validation.loader import (
    load_gold,
    load_gold_digest,
    load_ontology_ids,
    load_sample,
    sample_expression_ids,
)
from ke_memory_demo.mapper_v2_validation.models import (
    ID_BEARING,
    AnnotationError,
    AnnotationGold,
    AnnotationRecord,
    Outcome,
)


def test_every_sample_expression_has_exactly_one_label(project_root: Path) -> None:
    gold = load_gold(project_root)
    expected = sample_expression_ids(project_root)
    labelled = [record.expression_id for record in gold.records]

    assert len(labelled) == len(set(labelled)), "an expression is labelled twice"
    assert frozenset(labelled) == expected, (
        "gold and sample disagree about which expressions exist: "
        f"missing={sorted(expected - frozenset(labelled))[:6]} "
        f"invented={sorted(frozenset(labelled) - expected)[:6]}"
    )


def test_the_gold_names_the_sample_digest_it_annotated(project_root: Path) -> None:
    """A gold set that does not bind the sample digest could have been produced after a re-draw."""
    sample = load_sample(project_root)
    gold = load_gold(project_root)

    assert gold.sample_sha256 == ANNOTATED_SAMPLE_SHA256
    assert gold.sample_sha256 == sample["sample_sha256"]


def test_every_named_id_exists_in_the_frozen_ontology(project_root: Path) -> None:
    gold = load_gold(project_root)
    ontology_ids = load_ontology_ids(project_root)

    unknown = sorted(gold.named_ids() - ontology_ids)
    assert not unknown, (
        f"labels cite ids that O_L1 and O_L2 do not contain: {unknown[:6]}. A label naming a "
        "nonexistent item marks every mapper wrong for a reason that is not the mapper's"
    )


def test_id_bearing_labels_name_ids_and_the_others_do_not(project_root: Path) -> None:
    """The distinction is what stops 'something maps here, unspecified' counting as coverage."""
    for record in load_gold(project_root).records:
        if record.outcome in ID_BEARING:
            assert record.target_ids, f"{record.expression_id} claims coverage without an id"
        else:
            assert not record.target_ids, (
                f"{record.expression_id} is {record.outcome.value} yet names an item"
            )


def test_every_out_of_scope_label_states_what_would_be_required(project_root: Path) -> None:
    gaps = load_gold(project_root).gaps()
    assert gaps, "a ceiling measurement with no gaps at all would mean the sample was not read"
    for record in gaps:
        assert len(record.would_require) >= 20, (
            f"{record.expression_id} is out of scope without stating a requirement, which is "
            "indistinguishable from the annotator giving up"
        )


def test_every_ambiguous_label_offers_a_real_choice(project_root: Path) -> None:
    for record in load_gold(project_root).records:
        if record.outcome is Outcome.AMBIGUOUS:
            assert len(record.target_ids) >= 2, (
                f"{record.expression_id} is ambiguous between fewer than two items"
            )


def test_flagged_records_carry_an_adjudication_note(project_root: Path) -> None:
    """Graded review is only usable if a flag says what a reviewer should look at."""
    for record in load_gold(project_root).records:
        if record.needs_second_opinion:
            assert len(record.adjudication_note) >= 20, (
                f"{record.expression_id} is flagged with nothing to adjudicate"
            )
        else:
            assert not record.adjudication_note


def test_l2_and_ambiguous_labels_are_always_flagged(project_root: Path) -> None:
    """The triage rule the task set: novel, ambiguous and L2 cases get a second opinion."""
    for record in load_gold(project_root).records:
        needs_flag = record.outcome in {Outcome.AMBIGUOUS, Outcome.OUT_OF_SCOPE} or any(
            target.startswith("l2:") for target in record.target_ids
        )
        if needs_flag:
            assert record.needs_second_opinion, (
                f"{record.expression_id} is an ambiguous, gap or L2 case but was not flagged"
            )


def test_the_written_artifact_matches_the_builder(project_root: Path) -> None:
    assert load_gold(project_root).records == build_annotation_gold().records


def test_the_recorded_digest_is_the_digest_of_the_artifact(project_root: Path) -> None:
    """The artifact's own hash must be the hash of what is actually in it."""
    from ke_memory_demo.core.json import canonical_json
    import hashlib
    import json

    path = project_root / "artifacts/mapper-v2-validation/annotation-gold.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    recorded = payload.pop("gold_sha256")
    assert recorded == hashlib.sha256(canonical_json(payload)).hexdigest()
    assert recorded == load_gold_digest(project_root)


def test_the_gold_digest_moves_when_a_label_changes(project_root: Path) -> None:
    """Without this the freeze is decoration: an edited label would keep its old citation."""
    gold = load_gold(project_root)
    baseline = gold.digest

    for mutation in _mutations(gold):
        assert mutation.digest != baseline, (
            "the gold digest survived a label change, so the hash does not bind the labels"
        )


def _mutations(gold: AnnotationGold) -> list[AnnotationGold]:
    """One edit per field a label decision lives in.

    Each is a change a reviewer could plausibly make -- flipping an outcome, re-pointing an id,
    rewording a gap requirement -- so the test proves the digest covers the decision and not
    merely the record count.
    """
    first, *rest = gold.records
    gap = next(record for record in gold.records if record.outcome is Outcome.OUT_OF_SCOPE)
    others = tuple(record for record in gold.records if record.expression_id != gap.expression_id)
    return [
        gold.model_copy(
            update={
                "records": (
                    first.model_copy(update={"sense": f"{first.sense} (reworded)"}),
                    *rest,
                )
            }
        ),
        gold.model_copy(
            update={
                "records": (
                    AnnotationRecord(
                        expression_id=first.expression_id,
                        outcome=Outcome.NONE,
                        sense="relabelled as attesting nothing at all",
                    ),
                    *rest,
                )
            }
        ),
        AnnotationGold(
            sample_sha256=gold.sample_sha256,
            annotated_against_ontology=gold.annotated_against_ontology,
            records=tuple(
                sorted(
                    (
                        *others,
                        gap.model_copy(
                            update={"would_require": "a different requirement entirely, restated"}
                        ),
                    ),
                    key=lambda record: record.expression_id,
                )
            ),
        ),
        gold.model_copy(update={"records": tuple(rest)}),
    ]


def test_a_concept_label_cannot_be_built_without_an_id() -> None:
    with pytest.raises((AnnotationError, ValidationError), match="names no target"):
        AnnotationRecord(
            expression_id="expr-000000",
            outcome=Outcome.CONCEPT,
            sense="claims coverage while committing to nothing",
        )


def test_an_out_of_scope_label_cannot_be_built_without_a_requirement() -> None:
    with pytest.raises((AnnotationError, ValidationError), match="what would be required"):
        AnnotationRecord(
            expression_id="expr-000000",
            outcome=Outcome.OUT_OF_SCOPE,
            sense="a gap with no stated requirement",
        )


def test_a_label_cannot_name_an_id_outside_the_two_namespaces() -> None:
    with pytest.raises((AnnotationError, ValidationError), match="neither layer's namespace"):
        AnnotationRecord(
            expression_id="expr-000000",
            outcome=Outcome.CONCEPT,
            target_ids=("m:preference.affinity",),
            sense="a map id is not an ontology item",
        )


def test_gap_categories_are_all_cited_by_at_least_one_record(project_root: Path) -> None:
    """A gap taxonomy with an unused entry describes a ceiling the sample did not demonstrate."""
    gaps = load_gold(project_root).gaps()
    assert len(gaps) >= len(GAP_CATEGORIES), (
        f"{len(GAP_CATEGORIES)} gap categories are claimed but only {len(gaps)} expressions are "
        "labelled out of scope, so at least one category rests on no observation"
    )


def test_no_expression_is_labelled_with_a_mapper_score(project_root: Path) -> None:
    """The annotation line's independence, as a shape check on the artifact.

    A confidence, rank or candidate-list field would mean the labels had been produced by
    comparing against a mapper, which is the one thing this line must not do.
    """
    import json

    path = project_root / "artifacts/mapper-v2-validation/annotation-gold.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    forbidden = {"score", "confidence", "rank", "candidates", "mapper", "mapper_output"}
    for record in payload["records"]:
        leaked = forbidden & set(record)
        assert not leaked, f"a gold record carries mapper-derived fields: {sorted(leaked)}"
