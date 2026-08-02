"""The two layers share no vocabulary, and the map is the only crossing point.

The plan's ``freeze_rule`` says the layers do not share a vocabulary by default and every
shared or derived id must appear in M_L1_to_L2 explicitly. Both halves are tested: that no id
is shared, and that an attempt to reference across layers outside the map is rejected rather
than merely absent.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ke_memory_demo.ontology_v1 import (
    OntologyFreezeError,
    build_foundation_ontology,
    build_m_l1_to_l2,
    build_o_l1,
    build_o_l2,
)
from ke_memory_demo.ontology_v1.models import (
    L1_NAMESPACE,
    L2_NAMESPACE,
    DerivationEntry,
    DerivationKind,
    L1Item,
    L1ItemType,
    L2Item,
    L2ItemType,
    OntologyRoleKind,
    Provenance,
    Relation,
    RelationKind,
    SourceKind,
    OntologyItem,
)

# Pydantic wraps an exception raised inside a model validator in ValidationError, so a
# construction-time refusal surfaces as that rather than as OntologyFreezeError. The message
# is still the one the model raised, which is what these tests match on. Refusals raised by
# validate_against are called directly and stay OntologyFreezeError.
CONSTRUCTION_REFUSAL = ValidationError


def _bare_item(item_id: str, *, relations: tuple[Relation, ...] = ()) -> OntologyItem:
    return OntologyItem(
        id=item_id,
        sense="a sense long enough to satisfy the minimum length",
        role_kind=OntologyRoleKind.CONCEPT,
        relations=relations,
        provenance=(Provenance(source=SourceKind.AUTHORED_FOR_CLOSURE, evidence="test fixture"),),
    )


def test_the_layers_share_no_id() -> None:
    l1, l2 = build_o_l1(), build_o_l2()
    assert l1.item_ids & l2.item_ids == frozenset()
    assert all(item_id.startswith(L1_NAMESPACE) for item_id in l1.item_ids)
    assert all(item_id.startswith(L2_NAMESPACE) for item_id in l2.item_ids)


def test_a_cross_layer_relation_target_is_refused_by_the_namespace_check() -> None:
    """A typed reference field is caught by the id-prefix check, which fires first.

    This and the next test cover the two independent mechanisms. Namespacing catches an id in
    a field declared to hold one; the content scan catches an id anywhere else. Either alone
    would leave a gap, so both are exercised rather than assumed equivalent.
    """
    with pytest.raises(CONSTRUCTION_REFUSAL, match="must start with 'l2:'"):
        L2Item(
            item=_bare_item(
                "l2:abstraction.smuggled",
                relations=(
                    Relation(kind=RelationKind.AGGREGATES, target_id="l1:preference.affinity"),
                ),
            ),
            item_type=L2ItemType.ABSTRACTION_TYPE,
        )

    with pytest.raises(CONSTRUCTION_REFUSAL, match="must start with 'l1:'"):
        L1Item(
            item=_bare_item(
                "l1:state.leaky",
                relations=(Relation(kind=RelationKind.IS_A, target_id="l2:abstraction.task"),),
            ),
            item_type=L1ItemType.STATE_TYPE,
        )


def test_a_cross_layer_id_in_free_text_is_refused_by_the_content_scan() -> None:
    """The case a field-by-field check would miss: an id hidden in prose.

    The scan reads the whole serialized item, so there is no field an id can hide in. This is
    the half of the no-shared-vocabulary rule that cannot be enforced by typing alone.
    """
    with pytest.raises(CONSTRUCTION_REFUSAL, match="do not share a vocabulary"):
        L2Item(
            item=OntologyItem(
                id="l2:abstraction.smuggled_in_prose",
                sense="really just l1:preference.affinity under another name",
                role_kind=OntologyRoleKind.CONCEPT,
                provenance=(
                    Provenance(source=SourceKind.AUTHORED_FOR_CLOSURE, evidence="test fixture"),
                ),
            ),
            item_type=L2ItemType.ABSTRACTION_TYPE,
        )

    with pytest.raises(CONSTRUCTION_REFUSAL, match="do not share a vocabulary"):
        L1Item(
            item=OntologyItem(
                id="l1:state.leaky_in_prose",
                sense="the L1 counterpart of l2:abstraction.standing_condition",
                role_kind=OntologyRoleKind.CONCEPT,
                provenance=(
                    Provenance(source=SourceKind.AUTHORED_FOR_CLOSURE, evidence="test fixture"),
                ),
            ),
            item_type=L1ItemType.STATE_TYPE,
        )


def test_every_l2_abstraction_has_a_declared_derivation() -> None:
    """An abstraction with no derivation is what layer_gold.L2GoldAbstraction rejects too."""
    l2, mapping = build_o_l2(), build_m_l1_to_l2()
    abstractions = {
        entry.item.id
        for entry in l2.items
        if entry.item_type is L2ItemType.ABSTRACTION_TYPE
    }
    assert abstractions
    assert abstractions <= mapping.mapped_l2_ids


def test_the_map_is_rejected_when_it_cites_an_id_no_layer_contains() -> None:
    l1, l2, mapping = build_o_l1(), build_o_l2(), build_m_l1_to_l2()

    with_phantom = mapping.model_copy(
        update={
            "entries": (
                *mapping.entries,
                DerivationEntry(
                    map_id="m:zz.phantom",
                    kind=DerivationKind.IMPORT_AS,
                    l1_source_ids=("l1:role.does_not_exist",),
                    l2_target_id="l2:role.subject",
                    rule="cites a source that no layer contains",
                ),
            )
        }
    )
    with pytest.raises(OntologyFreezeError, match="absent from O_L1"):
        with_phantom.validate_against(l1, l2)


def test_a_stale_map_is_rejected_rather_than_silently_repointing_ids() -> None:
    l1, l2, mapping = build_o_l1(), build_o_l2(), build_m_l1_to_l2()
    stale = mapping.model_copy(update={"l1_version": "0.9.0"})
    with pytest.raises(OntologyFreezeError, match="stale map"):
        stale.validate_against(l1, l2)


def test_an_import_may_not_hide_an_aggregation() -> None:
    """An import naming several sources is an aggregation without an aggregation rule."""
    with pytest.raises(CONSTRUCTION_REFUSAL, match="it is an aggregation"):
        DerivationEntry(
            map_id="m:import.overloaded",
            kind=DerivationKind.IMPORT_AS,
            l1_source_ids=("l1:role.holder", "l1:role.theme"),
            l2_target_id="l2:role.subject",
            rule="claims to be an import while naming two sources",
        )


def test_a_map_edge_may_not_lower_an_abstractions_support_floor() -> None:
    l1, l2, mapping = build_o_l1(), build_o_l2(), build_m_l1_to_l2()
    habit_edge = next(e for e in mapping.entries if e.l2_target_id == "l2:abstraction.habit")
    weakened = mapping.model_copy(
        update={
            "entries": tuple(
                e.model_copy(update={"evidence_required": 1}) if e is habit_edge else e
                for e in mapping.entries
            )
        }
    )
    with pytest.raises(OntologyFreezeError, match="declares a minimum of 3"):
        weakened.validate_against(l1, l2)


def test_assembly_rejects_layers_that_overlap() -> None:
    ontology = build_foundation_ontology()
    assert ontology.l1.item_ids & ontology.l2.item_ids == frozenset()
