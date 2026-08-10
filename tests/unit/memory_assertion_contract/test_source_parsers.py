"""The three source parsers, on fixtures that always run.

No dataset required. Each fixture carries a shape the real corpora contain and a naive
parser would mishandle, so these tests fail on a defect rather than only on a missing file.
The absolute corpus counts live in test_source_corpora.py and skip without the archives.
"""

from __future__ import annotations

import unicodedata

import pytest

from memory_assertion_v1.ontology.profile import Lexicalization, SourceAttestation
from memory_assertion_v1.sources.candidates import (
    ExternalMappingProposal,
    candidate_from_propbank,
    candidate_from_schemaorg,
    candidate_from_wordnet,
)
from memory_assertion_v1.sources.lexicon import (
    build_owner_index,
    index_key,
    normalize_surface_form,
)
from memory_assertion_v1.sources.propbank import PropBankParseError, parse_frame_document
from memory_assertion_v1.sources.records import SourceLocation
from memory_assertion_v1.sources.schemaorg import parse_graph
from memory_assertion_v1.sources.wordnet import WordNetParseError, parse_index_sense_line

from .source_fixtures import (
    FAKE_SHA256,
    PROPBANK_HANG,
    PROPBANK_IRREGULAR_IDS,
    PROPBANK_LICENSE,
    PROPBANK_OVERHANG,
    PROPBANK_TWO_PREDICATES_ONE_LEMMA,
    SCHEMAORG_GRAPH,
    WORDNET_INDEX_SENSE,
)


def _location(member_path: str) -> SourceLocation:
    return SourceLocation(artifact_sha256=FAKE_SHA256, member_path=member_path)


# --- WordNet ----------------------------------------------------------------------


def test_sense_keys_with_awkward_lemmas_parse() -> None:
    """Leading apostrophes and dots are real WordNet lemmas, not corruption.

    1,390 senses look like this. A constructed `lemma.pos.nn` pattern would reject every
    one of them, which is why the sense key is taken verbatim.
    """
    location = _location("wordnet/index.sense")
    records = [
        parse_index_sense_line(line, location)
        for line in WORDNET_INDEX_SENSE.strip().splitlines()
    ]
    by_lemma = {record.lemma: record for record in records}
    assert set(by_lemma) == {"'hood", "'s_gravenhage", ".22", "create", "dog"}
    assert by_lemma["'hood"].sense_key == "'hood%1:15:00::"
    assert by_lemma[".22"].namespaced_id == "wn30:.22%1:06:00::"


def test_the_namespace_prefix_is_required_on_the_id() -> None:
    """`create.v.01` without a version namespace must not be mistaken for WordNet 3.0."""
    record = parse_index_sense_line(
        "create%2:36:00:: 01617192 1 5", _location("wordnet/index.sense")
    )
    assert record.namespaced_id == "wn30:create%2:36:00::"
    assert record.namespaced_id.startswith("wn30:")


def test_the_same_lemma_can_carry_several_senses() -> None:
    location = _location("wordnet/index.sense")
    records = [
        parse_index_sense_line(line, location)
        for line in WORDNET_INDEX_SENSE.strip().splitlines()
        if line.startswith("create%")
    ]
    assert [record.sense_number for record in records] == [1, 3]
    assert len({record.sense_key for record in records}) == 2


def test_a_malformed_sense_line_raises() -> None:
    """A frozen corpus with a broken line is not the corpus it claims to be."""
    location = _location("wordnet/index.sense")
    with pytest.raises(WordNetParseError):
        parse_index_sense_line("no_percent_sign 01617192 1", location)
    with pytest.raises(WordNetParseError):
        parse_index_sense_line("create%2:36:00:: 01617192", location)


# --- PropBank ---------------------------------------------------------------------


def test_license_xml_is_a_real_frameset() -> None:
    """Its name is misleading; dropping it undercounts the corpus.

    The existing ontology_sources/propbank.py filters this file out by name, which is the
    whole reason the frozen record says 11,205 rolesets instead of 11,206.
    """
    records = parse_frame_document(PROPBANK_LICENSE, _location("frames/license.xml"))
    assert len(records) == 1
    assert records[0].roleset_id == "license.01"
    assert records[0].predicate_lemma == "license"
    assert len(records[0].roles) == 3
    assert records[0].namespaced_id == "pb3.4:license.01"


def test_irregular_roleset_ids_are_kept_verbatim() -> None:
    """40 real rolesets do not fit `lemma.nn`; validating the shape would discard them."""
    records = parse_frame_document(PROPBANK_IRREGULAR_IDS, _location("frames/irregular.xml"))
    assert [record.roleset_id for record in records] == [
        "1500.01",
        "anticoagulate.101",
        "make.LV",
        "point.yy",
    ]


def test_one_file_may_hold_two_predicates_with_the_same_lemma() -> None:
    """This is why the corpus has 9,088 predicate elements but 9,087 distinct (file, lemma).

    frames/cap.xml really does declare `cap` twice, splitting cap.01/cap.02 from cap.03.
    """
    records = parse_frame_document(
        PROPBANK_TWO_PREDICATES_ONE_LEMMA, _location("frames/cap.xml")
    )
    assert [record.roleset_id for record in records] == ["cap.01", "cap.02", "cap.03"]
    assert {record.predicate_lemma for record in records} == {"cap"}


def test_the_overhang_collision_is_distinguished_by_location() -> None:
    """`overhang.01` exists twice with different signatures, so the id alone is not identity.

    Keying a dictionary by roleset id would silently drop one of these two -- which is the
    difference between 11,206 occurrences and 11,205 unique ids.
    """
    from_hang = parse_frame_document(PROPBANK_HANG, _location("frames/hang.xml"))[0]
    from_overhang = parse_frame_document(
        PROPBANK_OVERHANG, _location("frames/overhang.xml")
    )[0]

    assert from_hang.roleset_id == from_overhang.roleset_id == "overhang.01"
    assert len(from_hang.roles) == 5
    assert len(from_overhang.roles) == 2
    hang_identity = from_hang.location.identity(from_hang.roleset_id)
    overhang_identity = from_overhang.location.identity(from_overhang.roleset_id)
    assert hang_identity != overhang_identity
    # The triple is what a builder may key on; the roleset id alone would collapse these two.
    assert len({hang_identity, overhang_identity}) == 2


def test_a_non_frameset_document_raises() -> None:
    with pytest.raises(PropBankParseError):
        parse_frame_document(b"<other><predicate/></other>", _location("frames/x.xml"))
    with pytest.raises(PropBankParseError):
        parse_frame_document(b"<frameset><predicate/></frameset>", _location("frames/x.xml"))


# --- schema.org -------------------------------------------------------------------


def test_all_three_term_kinds_are_distinguished() -> None:
    """Enumeration members are typed by their own enumeration, not by a shared type."""
    records = parse_graph(SCHEMAORG_GRAPH, _location("schemaorg.jsonld"))
    kinds = {record.term_id: record.term_kind for record in records}
    assert kinds["schema:Person"] == "class"
    assert kinds["schema:archiveHeld"] == "property"
    assert kinds["schema:Paperback"] == "enumeration_member"


def test_language_tagged_labels_are_read() -> None:
    """7 labels and 7 comments are objects rather than strings; assuming strings drops them."""
    records = {
        record.term_id: record for record in parse_graph(SCHEMAORG_GRAPH, _location("s.jsonld"))
    }
    assert records["schema:archiveHeld"].label == "archiveHeld"
    assert records["schema:archiveHeld"].comment == "Collection held by an archive."


def test_list_valued_parents_are_read() -> None:
    """57 classes have more than one subClassOf."""
    records = {
        record.term_id: record for record in parse_graph(SCHEMAORG_GRAPH, _location("s.jsonld"))
    }
    assert records["schema:MedicalClinic"].parents == (
        "schema:MedicalBusiness",
        "schema:MedicalOrganization",
    )
    assert records["schema:Person"].parents == ("schema:Thing",)


def test_nodes_without_a_label_are_skipped_not_fatal() -> None:
    """The graph legitimately contains structural nodes that name no term."""
    records = parse_graph(SCHEMAORG_GRAPH, _location("schemaorg.jsonld"))
    assert all(record.label for record in records)
    assert "schema:StructuralNodeWithoutALabel" not in {
        record.term_id for record in records
    }


# --- Candidates and attestations --------------------------------------------------


def test_wordnet_candidates_carry_a_sense_id_and_no_roleset_id() -> None:
    """Section 6.2's conditional matrix, per source kind."""
    record = parse_index_sense_line(
        "create%2:36:00:: 01617192 1 5", _location("wordnet/index.sense")
    )
    candidate = candidate_from_wordnet(record, provenance_ref="resources/wordnet/3.0#create")
    assert candidate.attestation.sense_id == "wn30:create%2:36:00::"
    assert candidate.attestation.roleset_id is None
    assert candidate.surface_form == "create"


def test_propbank_candidates_carry_a_roleset_id_and_no_sense_id() -> None:
    record = parse_frame_document(PROPBANK_LICENSE, _location("frames/license.xml"))[0]
    candidate = candidate_from_propbank(record, provenance_ref="resources/propbank/3.4#l")
    assert candidate.attestation.roleset_id == "pb3.4:license.01"
    assert candidate.attestation.sense_id is None


def test_schemaorg_candidates_carry_neither() -> None:
    """schema.org publishes no sense inventory, so both fields are forbidden for it."""
    record = parse_graph(SCHEMAORG_GRAPH, _location("s.jsonld"))[0]
    candidate = candidate_from_schemaorg(record, provenance_ref="resources/schemaorg/30.0#p")
    assert candidate.attestation.sense_id is None
    assert candidate.attestation.roleset_id is None


def test_a_candidate_has_no_surface_relation_to_offer() -> None:
    """The relation belongs to the owner, so a candidate cannot pre-empt it.

    Asserted on the model itself: if a `surface_relation` field were ever added here, the
    build layer would have started deciding something only the owner may decide.
    """
    record = parse_index_sense_line("dog%1:05:00:: 02084071 1 42", _location("w/index.sense"))
    candidate = candidate_from_wordnet(record, provenance_ref="resources/wordnet/3.0#dog")
    assert not hasattr(candidate, "surface_relation")
    assert not hasattr(candidate, "disambiguation_status")


def test_multiword_lemmas_become_spaced_surface_forms() -> None:
    """WordNet writes multi-word lemmas with underscores; nothing else is altered."""
    record = parse_index_sense_line(
        "'s_gravenhage%1:15:00:: 08950407 1 0", _location("w/index.sense")
    )
    candidate = candidate_from_wordnet(record, provenance_ref="resources/wordnet/3.0#g")
    assert candidate.surface_form == "'s gravenhage"
    assert candidate.attestation.lemma == "'s_gravenhage"


def test_a_mapping_proposal_starts_unreviewed() -> None:
    """The three corpora carry no crosswalk, so every alignment is authored and needs review."""
    proposal = ExternalMappingProposal(
        owner_id="concept_aaaa00000001",
        relation="exact",
        target="wn30:dog%1:05:00::",
        basis="Manual reading of the synset gloss.",
        authored_by="builder",
    )
    assert proposal.status == "proposed"
    assert proposal.reviewed_by is None


# --- The derived index ------------------------------------------------------------


def test_the_index_applies_nfc_and_nothing_else() -> None:
    """Two steps only: language verbatim, surface form under NFC."""
    decomposed = "café"
    composed = "café"
    assert decomposed != composed
    assert normalize_surface_form(decomposed) == composed
    assert index_key("fr", decomposed) == index_key("fr", composed)


def test_the_index_folds_neither_case_nor_whitespace() -> None:
    """`Person` and `person` are different Concepts, not spelling variants."""
    assert index_key("en", "Person") != index_key("en", "person")
    assert index_key("en", "ice cream") != index_key("en", "ice  cream")
    assert index_key("en", "ice cream") != index_key("en", "icecream")
    assert index_key("en", "dog.") != index_key("en", "dog")


def test_language_tags_are_kept_as_the_snapshot_spells_them() -> None:
    assert index_key("zh-CN", "创建") != index_key("zh", "创建")
    assert index_key("EN", "create") != index_key("en", "create")


def test_one_key_may_resolve_to_several_owners() -> None:
    """`resolved` does not promise global unambiguity, so the index keeps every owner."""
    lexicalization = Lexicalization(
        language="en",
        surface_form="create",
        surface_relation="canonical_label",
        disambiguation_status="resolved",
        source_attestations=(
            SourceAttestation(
                source_kind="human",
                lemma="create",
                provenance_refs=("sources/test#create",),
            ),
        ),
    )
    index = build_owner_index(
        [
            ("operator_bbbb00000001", [lexicalization]),
            ("operator_bbbb00000002", [lexicalization]),
        ]
    )
    assert index[index_key("en", "create")] == (
        "operator_bbbb00000001",
        "operator_bbbb00000002",
    )


def test_nfc_equivalent_forms_share_one_index_entry() -> None:
    """Composed and decomposed spellings of one word are one key, not two owners' worth."""
    def lexicalization(surface_form: str) -> Lexicalization:
        return Lexicalization(
            language="fr",
            surface_form=surface_form,
            surface_relation="canonical_label",
            disambiguation_status="resolved",
            source_attestations=(
                SourceAttestation(
                    source_kind="human",
                    lemma=surface_form,
                    provenance_refs=("sources/test#cafe",),
                ),
            ),
        )

    index = build_owner_index(
        [
            ("concept_aaaa00000001", [lexicalization("café")]),
            ("concept_aaaa00000002", [lexicalization("café")]),
        ]
    )
    assert len(index) == 1
    key = index_key("fr", "café")
    assert index[key] == ("concept_aaaa00000001", "concept_aaaa00000002")
    assert unicodedata.is_normalized("NFC", key[1])
