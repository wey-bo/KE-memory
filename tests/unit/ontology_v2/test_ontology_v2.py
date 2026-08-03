"""Tests for foundation ontology v2.

The properties worth enforcing are the ones a larger ontology makes easier to violate. At 132 items
it is no longer possible to eyeball whether every item was reviewed, whether the two layers stayed
separate, or whether a benchmark literal crept in, so each is checked.

The recovery context matters for one test in particular: this ontology was assembled from modules a
crashed build left behind, and the ledger initially covered only 20 of 132 items. An ontology whose
items nobody decided on is exactly what the decision requirement exists to catch, so
``test_every_item_has_a_decision`` is the test that caught it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import ValidationError

from ke_memory_demo.ontology_v2.decisions import build_decisions, build_provenance
from ke_memory_demo.ontology_v2.l1_content import build_o_l1
from ke_memory_demo.ontology_v2.l2_content import build_o_l2
from ke_memory_demo.ontology_v2.mapping_content import build_m_l1_to_l2
from ke_memory_demo.ontology_v2.models import (
    Disposition,
    FoundationOntologyV2,
    OntologyFreezeError,
)
from ke_memory_demo.ontology_v2.supersession import build_supersession

ARTIFACTS = Path(__file__).resolve().parents[3] / "artifacts" / "ontology-v2"
V1_ARTIFACTS = Path(__file__).resolve().parents[3] / "artifacts" / "ontology-v1"


def _ontology() -> FoundationOntologyV2:
    return FoundationOntologyV2(
        l1=build_o_l1(),
        l2=build_o_l2(),
        map=build_m_l1_to_l2(),
        ledger=build_decisions(),
        provenance=build_provenance(),
        supersession=build_supersession(),
    )


def test_the_ontology_assembles() -> None:
    """Assembly runs every cross-unit validator, so construction is the real gate."""
    ontology = _ontology()
    assert len(ontology.l1.items) > 0
    assert len(ontology.l2.items) > 0


def test_it_is_broader_than_the_v1_seed() -> None:
    """v2 exists to close a breadth gap, so the gap must actually have closed."""
    ontology = _ontology()
    v1_l1 = json.loads((V1_ARTIFACTS / "o_l1.json").read_text(encoding="utf-8"))
    v1_l2 = json.loads((V1_ARTIFACTS / "o_l2.json").read_text(encoding="utf-8"))
    assert len(ontology.l1.items) > len(v1_l1["items"])
    assert len(ontology.l2.items) > len(v1_l2["items"])


def test_six_independent_hashes_and_no_combined_one() -> None:
    """A single digest cannot say which unit moved."""
    hashes = _ontology().hashes()
    assert len(hashes) == 6
    assert len(set(hashes.values())) == 6
    assert all(len(digest) == 64 for digest in hashes.values())
    assert not any("combined" in key for key in hashes)


def test_each_hash_moves_only_for_its_own_unit() -> None:
    """The point of separate digests: re-freezing one unit must not disturb another."""
    ontology = _ontology()
    baseline = ontology.hashes()

    trimmed_l1 = ontology.l1.model_copy(update={"items": ontology.l1.items[:-1]})
    changed = ontology.model_copy(update={"l1": trimmed_l1}).hashes()

    assert changed["o_l1_sha256"] != baseline["o_l1_sha256"]
    assert changed["o_l2_sha256"] == baseline["o_l2_sha256"]
    assert changed["m_l1_to_l2_sha256"] == baseline["m_l1_to_l2_sha256"]


def test_the_layers_share_no_id_outside_the_map() -> None:
    ontology = _ontology()
    assert ontology.l1.item_ids & ontology.l2.item_ids == set()
    assert all(item_id.startswith("l1:") for item_id in ontology.l1.item_ids)
    assert all(item_id.startswith("l2:") for item_id in ontology.l2.item_ids)


def test_every_l2_item_is_derived_through_the_map() -> None:
    """The two layers do not share a vocabulary by default; derivation is explicit."""
    ontology = _ontology()
    assert ontology.map.mapped_l2_ids == ontology.l2.item_ids


def test_every_item_has_a_decision() -> None:
    """The test that caught the recovered build.

    The ledger initially covered 20 of 132 items, so 112 had entered a layer with no recorded
    review. At this size that cannot be spotted by reading.
    """
    ontology = _ontology()
    items = ontology.l1.item_ids | ontology.l2.item_ids
    assert items - ontology.ledger.accepted_ids() == set()


def test_the_ledger_records_refusals_not_only_acceptances() -> None:
    """A ledger of pure acceptances would imply nothing was ever turned away."""
    ledger = _ontology().ledger
    assert ledger.count(Disposition.REJECTED) > 0
    assert ledger.count(Disposition.ACCEPTED) > 0
    # Every refusal carries a reason; the model enforces it, and this pins the intent.
    for decision in ledger.decisions:
        if decision.disposition is not Disposition.ACCEPTED:
            assert len(decision.reason) >= 20
            assert decision.accepted_as is None


def test_resolved_v1_deferrals_are_named_and_unique() -> None:
    """"The source debt is paid" has to be a walkable list, not a claim."""
    ledger = _ontology().ledger
    resolved = ledger.resolved_v1_deferrals()
    assert resolved
    assert len(set(resolved)) == len(resolved)

    v1 = cast("dict[str, Any]", json.loads((V1_ARTIFACTS / "decisions.json").read_text(encoding="utf-8")))
    entries: list[dict[str, Any]] = []
    for value in v1.values():
        if isinstance(value, list):
            entries = cast("list[dict[str, Any]]", value)
            break
    v1_deferred = {
        str(entry["candidate"])
        for entry in entries
        if str(entry.get("disposition")) == "deferred"
    }
    # Every claim must correspond to something v1 actually deferred.
    assert set(resolved) <= v1_deferred


def test_an_unresolved_v1_deferral_is_still_recorded_as_deferred() -> None:
    """A deferral silently dropped reads as a gap that was closed."""
    ledger = _ontology().ledger
    resolved = set(ledger.resolved_v1_deferrals())
    v1 = cast("dict[str, Any]", json.loads((V1_ARTIFACTS / "decisions.json").read_text(encoding="utf-8")))
    entries: list[dict[str, Any]] = []
    for value in v1.values():
        if isinstance(value, list):
            entries = cast("list[dict[str, Any]]", value)
            break
    v1_deferred = {
        str(entry["candidate"])
        for entry in entries
        if str(entry.get("disposition")) == "deferred"
    }
    still_open = v1_deferred - resolved
    carried = {
        d.candidate for d in ledger.decisions if d.disposition is Disposition.DEFERRED
    }
    assert still_open <= carried


def test_no_individual_or_benchmark_literal_is_admitted() -> None:
    """A type-level ontology: no named entity, date literal or dataset token."""
    ontology = _ontology()
    forbidden = (
        "beam", "locomo", "longmemeval", "slice",
        "2024", "2025", "2026",
        "american", "united", "delta",
        "_id",
    )
    for item_id in ontology.l1.item_ids | ontology.l2.item_ids:
        lowered = item_id.lower()
        for token in forbidden:
            assert token not in lowered, f"{item_id} carries {token!r}"


def test_the_published_sources_are_recorded_as_consulted_with_evidence() -> None:
    """v1 had to record all three as unavailable; that is the difference v2 rests on."""
    provenance = _ontology().provenance
    consulted = {s.name: s for s in provenance.sources if s.consulted}
    for expected in ("WordNet 3.0", "PropBank 3.4.0", "schema.org 30.0"):
        assert expected in consulted, expected
        source = consulted[expected]
        # A consulted claim must be backed by bytes or a count, or it is unverifiable.
        assert source.content_sha256 or source.observed_units


def test_declined_imports_make_the_no_bulk_import_rule_checkable() -> None:
    """Without this list, restraint is indistinguishable from never having looked."""
    provenance = _ontology().provenance
    declined = " ".join(provenance.declined_imports).lower()
    assert "propbank" in declined
    assert "schema.org" in declined
    assert "wordnet" in declined
    # The specific rejection v1 made and v2 keeps.
    assert "restaurant" in declined


def test_coverage_gaps_are_still_recorded() -> None:
    """A shorter gap list obtained by lowering the bar would be worse than an honest one."""
    ledger = _ontology().ledger
    assert ledger.uncovered
    for gap in ledger.uncovered:
        assert len(gap.why_not_covered) >= 20
        assert gap.would_require


def test_the_artifacts_on_disk_match_the_built_ontology() -> None:
    """A citation must be about the bytes that were written."""
    if not (ARTIFACTS / "summary.json").is_file():
        pytest.skip("the v2 artifacts have not been built")
    summary = json.loads((ARTIFACTS / "summary.json").read_text(encoding="utf-8"))
    assert summary["hashes"] == _ontology().hashes()

    for filename, key in (
        ("o_l1.json", "o_l1_sha256"),
        ("o_l2.json", "o_l2_sha256"),
        ("m_l1_to_l2.json", "m_l1_to_l2_sha256"),
    ):
        document = json.loads((ARTIFACTS / filename).read_text(encoding="utf-8"))
        assert document["freeze"]["sha256"] == summary["hashes"][key]


def test_a_layer_sharing_an_id_with_the_other_fails_assembly() -> None:
    """The separation is enforced at construction, not merely documented.

    Constructed rather than copied: ``model_copy`` skips validators, so a copy-based version of this
    test passed while checking nothing.
    """
    ontology = _ontology()
    stolen = next(iter(ontology.l2.item_ids))
    l1_entry = ontology.l1.items[0]
    clashing = l1_entry.model_copy(
        update={"item": l1_entry.item.model_copy(update={"id": stolen})}
    )

    with pytest.raises((OntologyFreezeError, ValidationError)):
        FoundationOntologyV2(
            l1=type(ontology.l1)(
                version=ontology.l1.version,
                items=(clashing, *ontology.l1.items[1:]),
            ),
            l2=ontology.l2,
            map=ontology.map,
            ledger=ontology.ledger,
            provenance=ontology.provenance,
            supersession=ontology.supersession,
        )
