"""Properties the three freeze units must have, tested by breaking them.

Each test here fails for a reason the plan names, not because a count changed. Item counts are
deliberately absent: scale is not a pass condition, so asserting "67 items" would turn every
honest addition into a failure and every honest removal into a pass.

What is asserted instead is that the guarantees survive mutation. A hash that moves when its
own content changes is only half the property; the other half is that it does *not* move when
another unit changes, and that is what makes five hashes better than one.
"""

from __future__ import annotations

from ke_memory_demo.ontology_v1 import (
    build_foundation_ontology,
    build_m_l1_to_l2,
    build_o_l1,
    build_o_l2,
)
from ke_memory_demo.ontology_v1.models import L1Freeze, L2Freeze


def _with_edited_first_sense(unit: L1Freeze | L2Freeze) -> L1Freeze | L2Freeze:
    """Rewrite the first item's sense to something no item already says.

    An earlier version of this test flipped a boolean flag on the first item, which happened
    to already hold that value; the mutation was a no-op and the test passed for the wrong
    reason. Editing a free-text field to a novel string cannot silently be a no-op.
    """
    first = unit.items[0]
    edited = first.model_copy(
        update={"item": first.item.model_copy(update={"sense": "a deliberately altered sense"})}
    )
    return unit.model_copy(update={"items": (edited, *unit.items[1:])})


def test_each_unit_hash_moves_when_its_own_content_changes() -> None:
    l1, l2, mapping = build_o_l1(), build_o_l2(), build_m_l1_to_l2()

    assert _with_edited_first_sense(l1).digest != l1.digest
    assert _with_edited_first_sense(l2).digest != l2.digest

    edited_map = mapping.model_copy(
        update={
            "entries": (
                mapping.entries[0].model_copy(update={"rule": "a materially different rule"}),
                *mapping.entries[1:],
            )
        }
    )
    assert edited_map.digest != mapping.digest


def test_a_units_hash_is_unaffected_by_the_other_units() -> None:
    """The reason there are five hashes instead of one.

    A combined digest would move all three citations when only O_L2 changed, which is what
    Stage 1A rejected for the evaluation contracts.
    """
    ontology = build_foundation_ontology()
    before = ontology.hashes()

    edited_l2 = _with_edited_first_sense(ontology.l2)

    assert edited_l2.digest != before["o_l2_sha256"]
    assert ontology.l1.digest == before["o_l1_sha256"]
    assert ontology.map.digest == before["m_l1_to_l2_sha256"]
    assert ontology.ledger.digest == before["decisions_sha256"]


def test_the_ledger_and_provenance_are_hashed_separately_too() -> None:
    """Recording a new rejection must not appear to invalidate O_L1."""
    ontology = build_foundation_ontology()
    before = ontology.hashes()

    ledger = ontology.ledger
    edited = ledger.model_copy(
        update={
            "decisions": (
                ledger.decisions[0].model_copy(
                    update={"reason": "a revised rationale of adequate length for the model"}
                ),
                *ledger.decisions[1:],
            )
        }
    )

    assert edited.digest != before["decisions_sha256"]
    assert ontology.l1.digest == before["o_l1_sha256"]
    assert ontology.l2.digest == before["o_l2_sha256"]


def test_digests_are_stable_across_rebuilds() -> None:
    """A freeze that is not reproducible is not a freeze."""
    assert build_foundation_ontology().hashes() == build_foundation_ontology().hashes()


def test_reordering_items_cannot_change_a_digest() -> None:
    """Sorted ids are enforced, so the digest is a function of content and not of authoring order."""
    l1 = build_o_l1()
    assert [entry.item.id for entry in l1.items] == sorted(entry.item.id for entry in l1.items)
    assert build_o_l1().digest == l1.digest
