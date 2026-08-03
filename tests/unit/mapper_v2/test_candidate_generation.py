"""Tests for mapper v2 candidate generation.

Every test here corresponds to a defect found while building it on discovery data. The v1 attempt
failed because alias overlap cannot tell attesting a preference from using a word that appears in a
preference alias; these tests pin the four things that had to be true before structural evidence
worked at all.

None of them was derived from the frozen validation sample, which this line has not read.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ke_memory_demo.mapper_v2.candidate_generation import (
    EVIDENCE_WEIGHT,
    CandidateGenerator,
    EvidenceKind,
    build_ontology_entries,
)
from ke_memory_demo.mapper_v2.mapper_v2 import (
    ExpressionInput,
    MapperV2,
    MapperV2Error,
    Outcome,
)
from ke_memory_demo.mapper_v2.source_indices import (
    PROPBANK_SHA256,
    SCHEMAORG_SHA256,
    WORDNET_SHA256,
    build_source_indices,
)

ONTOLOGY_DIR = Path(__file__).resolve().parents[3] / "artifacts" / "ontology-v2"

requires_sources = pytest.mark.skipif(
    not Path("/public/home/wwb/datasets/ontology-sources/propbank-frames-3.4.0.tar.gz").is_file(),
    reason="the frozen ontology sources are not present",
)
requires_ontology = pytest.mark.skipif(
    not (ONTOLOGY_DIR / "o_l1.json").is_file(),
    reason="ontology v2 has not been built",
)


@pytest.fixture(scope="module")
def generator() -> CandidateGenerator:
    l1 = json.loads((ONTOLOGY_DIR / "o_l1.json").read_text(encoding="utf-8"))
    return CandidateGenerator(build_ontology_entries(l1["items"]), build_source_indices())


@requires_sources
def test_indices_are_built_from_the_frozen_bytes() -> None:
    """An index built from other bytes would let a PropBank citation point at unreviewed content."""
    indices = build_source_indices()
    assert indices.wordnet.source_sha256 == WORDNET_SHA256
    assert indices.propbank.source_sha256 == PROPBANK_SHA256
    assert indices.schemaorg.source_sha256 == SCHEMAORG_SHA256
    # Counts must match what the source freeze recorded, or the index read something else.
    assert len(indices.propbank.by_lemma) == 9087
    assert len(indices.propbank.by_roleset_id) == 11205


@requires_sources
def test_morphology_reaches_base_forms_the_ontology_never_lists() -> None:
    """v1 could not match inflected text at all, because aliases list base forms only."""
    wordnet = build_source_indices().wordnet
    assert wordnet.base_form("cancelled") == "cancel"
    assert wordnet.base_form("booked") == "book"
    assert wordnet.is_known("cancel")


@requires_sources
def test_propbank_supplies_argument_structure() -> None:
    """The signal alias matching lacked entirely."""
    propbank = build_source_indices().propbank
    rolesets = propbank.rolesets_for("cancel")
    assert rolesets
    assert rolesets[0].roleset_id.startswith("cancel.")
    assert rolesets[0].arity >= 1


def test_structural_evidence_outweighs_vocabulary_evidence() -> None:
    """The ordering is the correction over v1, so it is asserted rather than assumed."""
    assert EVIDENCE_WEIGHT[EvidenceKind.PREDICATE_ROLESET] > EVIDENCE_WEIGHT[
        EvidenceKind.ONTOLOGY_ALIAS
    ]
    assert EVIDENCE_WEIGHT[EvidenceKind.ONTOLOGY_ALIAS] > EVIDENCE_WEIGHT[
        EvidenceKind.LEXICAL_SENSE
    ]


@requires_sources
@requires_ontology
def test_backchannel_generates_nothing(generator: CandidateGenerator) -> None:
    """Defect one: a term found inside some phrase alias, plus a low-polysemy lemma, was enough.

    "Mm hmm right okay then" produced candidates because ``then`` appears in a multi-word alias and
    has three WordNet senses. Neither fact is evidence about this utterance.
    """
    assert generator.generate("Mm hmm right okay then") == ()


@requires_sources
@requires_ontology
def test_a_copula_is_not_structural_evidence(generator: CandidateGenerator) -> None:
    """Defect two: ``be.01`` is a real roleset, which made every copular sentence look structural.

    "The weather has been mild lately" matched three predicates through the copula alone.
    """
    assert generator.generate("The weather has been mild lately") == ()


@requires_sources
@requires_ontology
def test_a_phrase_alias_matches_only_as_a_phrase(generator: CandidateGenerator) -> None:
    """Defect three: indexing phrase aliases word by word.

    ``work`` reached ``l1:event.attempt_failed`` through the alias "didn't work", and a PropBank
    roleset for the bare verb then gave that match structural standing. The phrase is the evidence.
    """
    bare = generator.generate("I work as a paralegal downtown")
    assert all(c.ontology_id != "l1:event.attempt_failed" for c in bare)

    whole = generator.generate("It didn't work out")
    assert any(c.ontology_id == "l1:event.attempt_failed" for c in whole)


@requires_sources
@requires_ontology
def test_content_utterances_still_map(generator: CandidateGenerator) -> None:
    """The abstain path must not be bought by refusing everything."""
    expectations = {
        "Please cancel my flight reservation": "l1:predicate.change_arrangement",
        "I really like jazz records": "l1:predicate.hold_attitude",
    }
    for text, expected in expectations.items():
        candidates = generator.generate(text)
        assert candidates, text
        assert any(c.ontology_id == expected for c in candidates), text


@requires_sources
@requires_ontology
def test_every_offered_candidate_has_standalone_evidence(
    generator: CandidateGenerator,
) -> None:
    """Admissibility is what makes a no_map native rather than a downstream filter."""
    for text in (
        "I booked a table for Friday evening",
        "Mm hmm right okay then",
        "The weather has been mild lately",
    ):
        for candidate in generator.generate(text):
            assert candidate.is_admissible
            assert any(item.is_standalone for item in candidate.evidence)


@requires_sources
@requires_ontology
def test_the_mapper_input_cannot_carry_gold_or_dataset_identity() -> None:
    assert set(ExpressionInput.model_fields) == {"expression_id", "speaker", "text"}
    for leaking in ("locomo-1", "LONGMEMEVAL-x", "validation-3", "gold-2"):
        with pytest.raises(Exception, match="discloses dataset identity"):
            ExpressionInput(expression_id=leaking, speaker="user", text="hello")


@requires_sources
@requires_ontology
def test_a_no_map_carries_no_candidate() -> None:
    """The type refuses a no_map that kept a candidate, which would be a filtered mapping."""
    from ke_memory_demo.mapper_v2.mapper_v2 import MappingResult

    with pytest.raises(Exception, match="must carry no candidate"):
        MappingResult(
            expression_id="expr-1",
            outcome=Outcome.NO_MAP,
            candidates=({"ontology_id": "l1:x"},),
        )


@requires_sources
@requires_ontology
def test_the_mapper_reports_all_three_outcomes_natively() -> None:
    mapper = MapperV2(ONTOLOGY_DIR)
    no_map = mapper.map_expression(
        ExpressionInput(expression_id="expr-1", speaker="user", text="Mm hmm okay then")
    )
    assert no_map.outcome is Outcome.NO_MAP
    assert no_map.candidates == ()

    mapped = mapper.map_expression(
        ExpressionInput(
            expression_id="expr-2", speaker="user", text="Please cancel my flight reservation"
        )
    )
    assert mapped.outcome in {Outcome.MAPPED, Outcome.AMBIGUOUS}
    assert mapped.candidates


@requires_sources
@requires_ontology
def test_the_mapper_identity_binds_ontology_and_all_three_sources() -> None:
    """A result must be traceable to the exact ontology and source bytes behind it."""
    identity = MapperV2(ONTOLOGY_DIR).identity
    for key in (
        "o_l1_sha256",
        "o_l2_sha256",
        "wordnet_sha256",
        "propbank_sha256",
        "schemaorg_sha256",
    ):
        assert len(str(identity[key])) == 64, key


@requires_sources
@requires_ontology
def test_an_unknown_layer_is_refused() -> None:
    with pytest.raises(MapperV2Error, match="unknown layer"):
        MapperV2(ONTOLOGY_DIR).map_expression(
            ExpressionInput(expression_id="expr-1", speaker="user", text="hello"), "l3"
        )
