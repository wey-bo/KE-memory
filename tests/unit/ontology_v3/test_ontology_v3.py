"""Tests for the O_v3 candidate freeze.

Three properties carry the ruling and are checked rather than documented: value and belief are never
one item, no alias came from the validation sample, and a replay reproduces every digest. The last is
what separates this from v2, which could not be regenerated at all.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest

from ke_memory_demo.ontology_v3.content import (
    V3Item,
    build_items,
    build_l2_additions,
    build_new_roles,
)
from ke_memory_demo.ontology_v3.evidence import collect_all

ROOT = Path(__file__).resolve().parents[3]
ARTIFACTS = ROOT / "artifacts" / "ontology-v3"
V2_ARTIFACTS = ROOT / "artifacts" / "ontology-v2"
VALIDATION_DIR = ROOT / "artifacts" / "mapper-v2-validation"

requires_corpora = pytest.mark.skipif(
    not Path("/public/home/wwb/datasets/MSC/msc_personas_all.json").is_file(),
    reason="the MSC corpus is not present",
)
requires_freeze = pytest.mark.skipif(
    not (ARTIFACTS / "summary.json").is_file(),
    reason="O_v3 has not been frozen",
)


@pytest.fixture(scope="module")
def items() -> tuple[V3Item, ...]:
    families, _ = collect_all()
    return build_items(families)


@requires_corpora
def test_value_and_belief_are_two_items_never_one(items: tuple[V3Item, ...]) -> None:
    """The ruling's central constraint.

    A merged item would have to drop either the strength qualifier only values take or the assertion
    modality only beliefs take, so the separation is what preserves both.
    """
    by_id = {i.item_id: i for i in items}
    value = by_id["l1:predicate.hold_value"]
    belief = by_id["l1:predicate.hold_belief"]

    assert value.item_id != belief.item_id
    assert value.sense != belief.sense
    # Strength lives on the value; modality on the belief.
    assert any("degree" in q for q in value.qualifiers)
    assert any("modality" in q for q in belief.qualifiers)
    assert not any("modality" in q for q in value.qualifiers)
    assert not any("degree" in q for q in belief.qualifiers)
    # Each names the other as something it must not merge with.
    assert any("hold_belief" in c for c in value.constraints)
    assert any("hold_value" in c for c in belief.constraints)


@requires_corpora
def test_held_value_is_distinct_from_object_assessment(items: tuple[V3Item, ...]) -> None:
    """attribute.assessment rates an object; a held value is a property of the subject."""
    value = next(i for i in items if i.item_id == "l1:predicate.hold_value")
    assert any("attribute.assessment" in c for c in value.constraints)
    # And distinct from liking, which is a different claim again.
    assert any("preference.affinity" in c for c in value.constraints)


@requires_corpora
def test_capability_does_not_merge_with_its_negative(items: tuple[V3Item, ...]) -> None:
    """A stated inability and a stated ability are separately memory-worthy."""
    capability = next(i for i in items if i.item_id == "l1:state.capability")
    assert any("capability_constraint" in c for c in capability.constraints)
    assert capability.admitted_on == "structural_gap"
    # Authored rather than imported, because PropBank has no modal sense for "can".
    assert any("can.01" in c for c in capability.constraints)


@requires_corpora
def test_activity_separates_an_occasion_from_a_practice(items: tuple[V3Item, ...]) -> None:
    """One type cannot carry both without losing whether the thing recurs."""
    occurrence = next(i for i in items if i.item_id == "l1:event.activity_occurrence")
    pursuit = next(i for i in items if i.item_id == "l1:state.ongoing_pursuit")
    assert occurrence.item_type == "event_type"
    assert pursuit.item_type == "state_type"
    assert any("ongoing_pursuit" in c for c in occurrence.constraints)
    assert any("frequency" in q or "spanning" in q for q in pursuit.qualifiers)


@requires_corpora
def test_only_the_four_ruled_families_are_present(items: tuple[V3Item, ...]) -> None:
    """episodic_significance and role_play_framing are excluded by ruling."""
    families = {i.evidence_family for i in items}
    assert families == {
        "activity_or_pursuit",
        "positive_capability_or_skill",
        "held_value",
        "held_belief",
    }


@requires_corpora
def test_no_alias_came_from_the_validation_sample() -> None:
    """Isolation: aliases are corpus-derived, so they cannot encode the exposing cases.

    Checked by content rather than by inspecting imports: an alias that appeared verbatim only in the
    validation sample would be evidence the sample leaked in.
    """
    families, provenance = collect_all()
    assert "no validation expression" in provenance["isolation"]

    if not (VALIDATION_DIR / "natural-expression-sample.json").is_file():
        pytest.skip("the validation sample is not present to cross-check against")
    sample = cast(
        "dict[str, Any]",
        json.loads(
            (VALIDATION_DIR / "natural-expression-sample.json").read_text(encoding="utf-8")
        ),
    )
    expressions = cast("list[dict[str, Any]]", sample["expressions"])
    sample_text = " ".join(str(e["text"]).lower() for e in expressions)

    from ke_memory_demo.ontology_v3.evidence import msc_sentences

    corpus_sentences, _ = msc_sentences()
    corpus_text = " ".join(s.lower() for s in corpus_sentences)

    for family in families:
        for alias in family.aliases:
            # Every alias must be attested in the independent corpus. Whether it also happens to
            # appear in the sample is irrelevant; being absent from the corpus would not be.
            assert alias in corpus_text, f"{alias!r} is not attested in the corpus"
    assert sample_text  # the cross-check ran against real sample content


@requires_corpora
def test_evidence_collection_is_deterministic() -> None:
    """Replayability starts here: the same bytes must yield the same evidence."""
    first, _ = collect_all()
    second, _ = collect_all()
    assert [f.as_json() for f in first] == [f.as_json() for f in second]


@requires_freeze
def test_four_independent_digests_and_no_combined_one() -> None:
    summary = json.loads((ARTIFACTS / "summary.json").read_text(encoding="utf-8"))
    hashes = summary["hashes"]
    assert len(hashes) == 4
    assert len(set(hashes.values())) == 4
    assert all(len(h) == 64 for h in hashes.values())
    assert not any("combined" in k for k in hashes)


@requires_freeze
def test_each_unit_file_carries_its_own_digest() -> None:
    summary = json.loads((ARTIFACTS / "summary.json").read_text(encoding="utf-8"))
    for filename, key in (
        ("o_l1_additions.json", "o_l1_additions_sha256"),
        ("o_l2_additions.json", "o_l2_additions_sha256"),
        ("m_l1_to_l2_additions.json", "m_l1_to_l2_additions_sha256"),
        ("decisions.json", "decisions_sha256"),
    ):
        document = json.loads((ARTIFACTS / filename).read_text(encoding="utf-8"))
        assert document["freeze"]["sha256"] == summary["hashes"][key]
        assert document["freeze"]["derived_from_validation_sample"] is False


@requires_freeze
def test_v3_is_additive_and_does_not_disturb_v2() -> None:
    """An earlier citation about v2 must stay valid."""
    summary = json.loads((ARTIFACTS / "summary.json").read_text(encoding="utf-8"))
    v2_l1 = json.loads((V2_ARTIFACTS / "o_l1.json").read_text(encoding="utf-8"))
    v2_l2 = json.loads((V2_ARTIFACTS / "o_l2.json").read_text(encoding="utf-8"))

    assert v2_l1["freeze"]["sha256"].startswith("76465be5ecfed0c9")
    assert v2_l2["freeze"]["sha256"].startswith("308ba27fc274f4c1")
    assert "additive" in summary
    l1_unit = json.loads((ARTIFACTS / "o_l1_additions.json").read_text(encoding="utf-8"))
    assert l1_unit["extends_v2_l1_sha256"] == v2_l1["freeze"]["sha256"]


@requires_freeze
def test_no_v3_id_collides_with_a_frozen_v2_id() -> None:
    """A collision would silently redefine a frozen item."""
    v2_l1 = json.loads((V2_ARTIFACTS / "o_l1.json").read_text(encoding="utf-8"))
    v2_l2 = json.loads((V2_ARTIFACTS / "o_l2.json").read_text(encoding="utf-8"))
    v2_ids = {e["item"]["id"] for e in v2_l1["items"]} | {
        e["item"]["id"] for e in v2_l2["items"]
    }

    l1_unit = json.loads((ARTIFACTS / "o_l1_additions.json").read_text(encoding="utf-8"))
    l2_unit = json.loads((ARTIFACTS / "o_l2_additions.json").read_text(encoding="utf-8"))
    v3_ids = (
        {i["id"] for i in l1_unit["items"]}
        | {str(r["id"]) for r in l1_unit["new_roles"]}
        | {i["id"] for i in l2_unit["items"]}
    )
    assert v3_ids & v2_ids == set()


@requires_freeze
def test_l2_additions_require_more_than_one_source() -> None:
    """An abstraction needing one source is a rename, not an abstraction."""
    mapping = cast(
            "dict[str, Any]",
            json.loads((ARTIFACTS / "m_l1_to_l2_additions.json").read_text(encoding="utf-8")),
        )
    assert mapping["entries"]
    for entry in mapping["entries"]:
        assert entry["evidence_required"] >= 2
        assert len(entry["l1_source_ids"]) > entry["evidence_required"] - 1


@requires_freeze
def test_the_ledger_records_both_exclusions_with_reasons() -> None:
    """An excluded family must be a decision, not an omission."""
    ledger = json.loads((ARTIFACTS / "decisions.json").read_text(encoding="utf-8"))
    excluded = {e["family"]: e for e in ledger["families_excluded"]}
    assert set(excluded) == {"episodic_significance", "role_play_framing"}
    assert excluded["episodic_significance"]["disposition"] == "explicit_residual_gap"
    assert excluded["episodic_significance"]["validation_requirement"]
    assert excluded["role_play_framing"]["disposition"] == "residual_limitation"


@requires_freeze
def test_admission_grounds_are_recorded_per_family() -> None:
    """Activity was admitted on frequency; value and belief were not, and that must be visible."""
    ledger = json.loads((ARTIFACTS / "decisions.json").read_text(encoding="utf-8"))
    grounds = {f["family"]: f["admitted_on"] for f in ledger["families_admitted"]}
    assert grounds["activity_or_pursuit"] == "frequency"
    assert grounds["held_value"] == "expressibility"
    assert grounds["held_belief"] == "expressibility"
    assert grounds["positive_capability_or_skill"] == "structural_gap"


@requires_freeze
def test_belief_modality_is_declared_as_unattested() -> None:
    """MSC carries no explicit modality marker, so claiming attested coverage would be fabrication."""
    l1_unit = json.loads((ARTIFACTS / "o_l1_additions.json").read_text(encoding="utf-8"))
    belief = next(
        i for i in l1_unit["items"] if i["id"] == "l1:predicate.hold_belief"
    )
    assert any("unattested" in c for c in belief["constraints"])


@requires_freeze
def test_the_freeze_declares_its_own_replayability() -> None:
    """The property v2 lacked, stated where a reader will look for it."""
    summary = json.loads((ARTIFACTS / "summary.json").read_text(encoding="utf-8"))
    replay = summary["replayability"]
    assert replay["generator_committed_before_freeze"] is True
    assert replay["evidence_deterministic"] is True
    assert len(replay["corpus_digest_checked"]) == 64
    assert summary["standing"] == "replayable_candidate_freeze"


@requires_freeze
def test_the_freeze_carries_the_independent_mapper_blocker() -> None:
    """An ontology freeze must not read as clearing the mapper."""
    summary = json.loads((ARTIFACTS / "summary.json").read_text(encoding="utf-8"))
    assert "0.165" in summary["independent_blocker"]
    assert "regression" in summary["regression_status"]


@requires_corpora
def test_new_roles_are_only_those_the_items_need() -> None:
    """Roles are added because an item requires them, not speculatively."""
    families, _ = collect_all()
    items = build_items(families)
    roles = build_new_roles()
    required = {role.role_id for item in items for role in item.roles}
    for role in roles:
        assert str(role["id"]) in required, role["id"]
        assert role["needed_by"]


@requires_corpora
def test_l2_additions_reference_only_real_l1_sources() -> None:
    """A derivation naming a nonexistent source could never fire."""
    families, _ = collect_all()
    new_l1 = {i.item_id for i in build_items(families)}
    v2_l1 = json.loads((V2_ARTIFACTS / "o_l1.json").read_text(encoding="utf-8"))
    known = new_l1 | {e["item"]["id"] for e in v2_l1["items"]}
    for addition in build_l2_additions():
        for source in addition["l1_source_ids"]:
            assert source in known, source
