"""Individuals and benchmark facts stay out, and every accepted item is properly formed.

The plan excludes ``benchmark facts`` and ``Individuals`` outright. These tests check the
exclusion the way it is implemented -- structurally -- rather than by scanning for suspicious
strings. The distinction matters: a denylist tells you the strings you thought of are absent,
while an absent field tells you the content is unrepresentable.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ke_memory_demo.ontology_v1 import (
    Disposition,
    build_foundation_ontology,
    build_o_l1,
    build_o_l2,
)
from ke_memory_demo.ontology_v1.models import (
    FORBIDDEN_CORPUS_TOKENS,
    OntologyRoleKind,
    Provenance,
    SourceKind,
    SourceSnapshot,
    OntologyItem,
)

# Fields that would let a type-level item carry an instance. None may exist on either item
# model. This is the exclusion mechanism, so it is asserted directly.
INSTANCE_BEARING_FIELDS = (
    "value",
    "values",
    "filler",
    "fillers",
    "example",
    "examples",
    "surface_form",
    "mention",
    "mentions",
    "instance",
    "instances",
    "individual",
    "evidence_handle",
    "question_id",
    "answer",
)


def test_no_item_model_has_a_field_that_could_hold_an_instance() -> None:
    """Individuals are excluded by having nowhere to put one.

    If this ever fails, the exclusion has stopped being structural and has become a matter of
    authors choosing not to populate a field that exists.
    """
    present = set(OntologyItem.model_fields)
    assert present.isdisjoint(INSTANCE_BEARING_FIELDS), (
        f"an item model gained a field that can carry an instance: "
        f"{sorted(present & set(INSTANCE_BEARING_FIELDS))}"
    )


def test_items_forbid_extra_fields_so_an_instance_cannot_be_attached() -> None:
    with pytest.raises(ValidationError):
        OntologyItem(
            id="l1:state.smuggler",
            sense="a sense long enough to satisfy the minimum length",
            role_kind=OntologyRoleKind.CONCEPT,
            provenance=(Provenance(source=SourceKind.AUTHORED_FOR_CLOSURE, evidence="fixture"),),
            observed_value="United Airlines",  # type: ignore[call-arg]
        )


def test_the_individual_role_is_not_representable() -> None:
    """domain.OntologyRole has 'individual'; OntologyRoleKind deliberately does not."""
    assert "individual" not in {kind.value for kind in OntologyRoleKind}


def test_no_item_names_an_evaluation_corpus() -> None:
    l1, l2 = build_o_l1(), build_o_l2()
    for unit in (l1.items, l2.items):
        for entry in unit:
            text = " ".join((entry.item.sense, *entry.item.aliases)).lower()
            leaked = sorted(token for token in FORBIDDEN_CORPUS_TOKENS if token in text)
            assert not leaked, f"{entry.item.id} names an evaluation corpus: {leaked}"


def test_an_item_naming_an_evaluation_corpus_is_refused() -> None:
    """The scan is enforced at construction, not only checked after the fact."""
    with pytest.raises(ValidationError, match="names an evaluation corpus"):
        OntologyItem(
            id="l1:state.leaky",
            sense="the shape longmemeval questions ask about most often",
            role_kind=OntologyRoleKind.CONCEPT,
            provenance=(Provenance(source=SourceKind.AUTHORED_FOR_CLOSURE, evidence="fixture"),),
        )


def test_every_accepted_item_has_a_stable_id_and_a_sense() -> None:
    ontology = build_foundation_ontology()
    for entry in (*ontology.l1.items, *ontology.l2.items):
        item = entry.item
        assert item.id and item.id == item.id.strip()
        assert ":" in item.id and "." in item.id
        assert len(item.sense) >= 12
        assert item.provenance, f"{item.id} has no provenance"
        assert all(p.evidence.strip() for p in item.provenance)


def test_every_item_in_a_layer_has_a_ledger_decision() -> None:
    """An item nobody decided on is an item that entered without review."""
    ontology = build_foundation_ontology()
    accepted = ontology.ledger.accepted_ids()
    assert (ontology.l1.item_ids | ontology.l2.item_ids) <= accepted


def test_rejections_and_deferrals_carry_reasons_and_no_item_id() -> None:
    """Rejections matter as much as acceptances, so an unexplained one is invalid."""
    ledger = build_foundation_ontology().ledger
    rejected = [d for d in ledger.decisions if d.disposition is Disposition.REJECTED]
    deferred = [d for d in ledger.decisions if d.disposition is Disposition.DEFERRED]

    assert rejected and deferred
    for decision in (*rejected, *deferred):
        assert decision.accepted_as is None
        assert len(decision.reason) >= 20


def test_uncovered_expressions_are_recorded_rather_than_papered_over() -> None:
    """A coverage gap may not be masked, so the list must be non-empty and substantive."""
    ledger = build_foundation_ontology().ledger
    assert ledger.uncovered
    for gap in ledger.uncovered:
        assert len(gap.why_not_covered) >= 20
        assert gap.would_require.strip()


def test_provenance_records_unconsulted_sources_honestly() -> None:
    """WordNet, PropBank and schema.org are named by the plan and were not available.

    Recording them as unconsulted is the alternative to authoring plausible entries and
    attributing them to a source that was never opened.
    """
    provenance = build_foundation_ontology().provenance
    unconsulted = set(provenance.unconsulted_names())
    assert {"WordNet", "PropBank", "schema.org"} <= unconsulted
    assert provenance.consulted_names()
    assert provenance.model_api_calls == 0
    assert "none" in provenance.judge_dependency.lower()


def test_a_source_cannot_claim_a_hash_while_marked_unconsulted() -> None:
    with pytest.raises(ValidationError, match="unconsulted but carries a content hash"):
        SourceSnapshot(
            name="WordNet",
            consulted=False,
            locator="unavailable",
            detail="claims a hash it cannot have",
            content_sha256="0" * 64,
        )


def test_a_consulted_source_must_show_evidence_it_was_read() -> None:
    with pytest.raises(ValidationError, match="unverifiable"):
        SourceSnapshot(
            name="a source asserted without evidence",
            consulted=True,
            locator="somewhere",
            detail="no count and no hash, so the claim cannot be checked",
        )
