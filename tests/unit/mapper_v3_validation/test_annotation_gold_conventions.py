"""What the v3 gold's own conventions commit to, checked against the labels themselves.

These are not architecture tests. They assert that the annotation followed the rules its docstring
states, because a convention nobody checks is a convention the next 40 records will drift from.

The one that matters most is the last: ``ambiguous`` is empty, and the tests pin that as a fact
about this round rather than treating it as a defect to be corrected. Adding ambiguous records now,
after the labels have been read against the ontology and after a mapper exists, would manufacture a
denominator for a metric that has no evidence behind it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ke_memory_demo.mapper_v3_validation.annotations import build_annotation_gold
from ke_memory_demo.mapper_v3_validation.loader import (
    load_combined_ontology_ids,
    load_v3_added_ids,
    mapping_set_expression_ids,
)
from ke_memory_demo.mapper_v3_validation.models import ID_BEARING, AnnotationGold, Outcome

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]

# The three records that name a role id, and why each is allowed to. The no-roles convention holds
# everywhere else, so an unlisted fourth would be drift rather than a judgement.
ROLE_NAMING_RECORDS = {
    "fx-000056": "l1:role.quantity",
    "fx-000093": "l1:role.duration",
    "fx-000102": "l1:role.duration",
    "fx-000139": "l1:role.beneficiary",
    "fx-000143": "l1:role.quantity",
}


@pytest.fixture(scope="module")
def gold() -> AnnotationGold:
    return build_annotation_gold()


def test_gold_covers_the_fresh_set_exactly(gold: AnnotationGold) -> None:
    assert gold.expression_ids() == mapping_set_expression_ids(REPOSITORY_ROOT)
    assert len(gold.records) == 160


def test_every_named_id_exists_in_the_combined_ontology(gold: AnnotationGold) -> None:
    unknown = sorted(gold.named_ids() - load_combined_ontology_ids(REPOSITORY_ROOT))
    assert unknown == [], (
        f"labels cite items no frozen unit contains: {unknown}; such a label scores every mapper "
        "wrong for the same reason"
    )


def test_qualifier_dimensions_are_never_named(gold: AnnotationGold) -> None:
    """A dimension names the axis; the value items are what an expression attests."""
    dimensions = sorted(i for i in gold.named_ids() if i.startswith("l1:qualifier."))
    assert dimensions == []


def test_roles_are_named_only_where_the_slot_is_the_attestation(gold: AnnotationGold) -> None:
    naming = {
        record.expression_id: sorted(t for t in record.target_ids if ":role." in t)
        for record in gold.records
        if any(":role." in t for t in record.target_ids)
    }
    assert sorted(naming) == sorted(ROLE_NAMING_RECORDS), (
        "the set of records naming a role id changed; the no-roles convention keeps every count "
        f"from carrying a constant, so a new one needs its own justification: {naming}"
    )
    for expression_id, expected in ROLE_NAMING_RECORDS.items():
        assert expected in naming[expression_id]


def test_out_of_scope_records_state_what_would_be_required(gold: AnnotationGold) -> None:
    gaps = gold.gaps()
    assert len(gaps) == 5
    for record in gaps:
        assert len(record.would_require) >= 20
        assert record.needs_second_opinion


def test_non_id_bearing_records_name_nothing(gold: AnnotationGold) -> None:
    for record in gold.records:
        if record.outcome not in ID_BEARING:
            assert record.target_ids == ()


def test_v3_absorption_is_recorded_per_item(gold: AnnotationGold) -> None:
    absorbed = gold.v3_absorption_by_item()
    assert set(absorbed) <= load_v3_added_ids(REPOSITORY_ROOT)
    # Six of the seven non-role v3 additions earned labels. The counts are pinned so a later edit
    # cannot quietly change what v3 is credited with.
    assert absorbed == {
        "l1:event.activity_occurrence": 24,
        "l1:predicate.hold_belief": 9,
        "l1:predicate.hold_value": 8,
        "l1:state.capability": 4,
        "l1:state.ongoing_pursuit": 39,
        "l2:abstraction.pursuit_profile": 5,
    }


def test_value_commitment_is_unattested_on_the_fresh_set(gold: AnnotationGold) -> None:
    """A v3 addition the fresh corpus never licensed. Recorded, not repaired.

    ``l2:abstraction.value_commitment`` was admitted to O_v3 because the earlier sample's
    out_of_scope labels showed no way to hold a subject's own value ranking. Its derivation rule
    m3-001 requires two of hold_value, hold_belief and ongoing_pursuit to support one commitment.
    On these 160 expressions the individual L1 items appear (8 and 9 times) but never converge on a
    single commitment, so the L2 item is never attested.

    This is the third kind of finding the round has to keep separate from the other two: not an
    ontology gap and not a mapper failure, but an addition the fresh evidence does not license.
    """
    assert "l2:abstraction.value_commitment" not in gold.v3_absorption_by_item()
    assert [
        r.expression_id for r in gold.records if "l2:abstraction.value_commitment" in r.target_ids
    ] == []


def test_role_additions_are_unlisted_by_convention(gold: AnnotationGold) -> None:
    """v3 added three roles; the no-roles convention means their absence is expected, not a gap."""
    added_roles = {i for i in load_v3_added_ids(REPOSITORY_ROOT) if ":role." in i}
    assert added_roles == {
        "l1:role.participant",
        "l1:role.proposition_content",
        "l1:role.topic",
    }
    assert added_roles.isdisjoint(gold.named_ids())


def test_the_gold_contains_no_ambiguous_records(gold: AnnotationGold) -> None:
    """Pinned as a fact about this round, and as the reason one metric is unavailable."""
    assert gold.counts_by_outcome()["ambiguous"] == 0
    assert all(record.outcome is not Outcome.AMBIGUOUS for record in gold.records)


def test_flagged_records_all_carry_an_adjudication_note(gold: AnnotationGold) -> None:
    flagged = [r for r in gold.records if r.needs_second_opinion]
    assert len(flagged) == 131
    for record in flagged:
        assert len(record.adjudication_note) >= 20


def test_digest_is_order_independent(gold: AnnotationGold) -> None:
    """Records are sorted before hashing, so the digest cannot depend on annotation order."""
    reshuffled = AnnotationGold(
        annotated_set_sha256=gold.annotated_set_sha256,
        annotated_against_ontology=gold.annotated_against_ontology,
        records=tuple(sorted(gold.records, key=lambda r: r.expression_id)),
    )
    assert reshuffled.digest == gold.digest
