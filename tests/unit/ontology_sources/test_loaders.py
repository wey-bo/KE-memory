"""The three parsers read their real formats and count what is actually there."""

from __future__ import annotations

from pathlib import Path
import zipfile

import pytest

from ke_memory_demo.ontology_sources import (
    load_propbank,
    load_schemaorg,
    load_wordnet,
)
from ke_memory_demo.ontology_sources.propbank import PropBankParseError
from ke_memory_demo.ontology_sources.schemaorg import SchemaOrgParseError
from ke_memory_demo.ontology_sources.wordnet import WordNetParseError
from .fixtures import (
    acquisition,
    write_propbank_archive,
    write_schemaorg_document,
    write_wordnet_archive,
)


def test_wordnet_parses_every_part_of_speech(tmp_path: Path) -> None:
    archive = tmp_path / "wordnet.zip"
    write_wordnet_archive(archive)

    snapshot = load_wordnet(archive, acquisition())

    assert snapshot.synset_count_by_pos == {"n": 2, "v": 2, "a": 2, "r": 2}
    assert snapshot.total_synsets == 8
    assert snapshot.lexname_count == 4


def test_wordnet_reads_multi_word_synsets_and_hypernyms(tmp_path: Path) -> None:
    """The word count is hexadecimal and each word carries a lex_id that must be skipped."""
    archive = tmp_path / "wordnet.zip"
    write_wordnet_archive(archive)

    snapshot = load_wordnet(archive, acquisition())
    by_id = {synset.synset_id: synset for synset in snapshot.sample}

    physical = by_id["n#00001930"]
    assert physical.words == ("physical_entity", "thing")
    assert physical.hypernyms == ("n#00001740",)
    assert physical.gloss == "an entity that has physical existence"
    assert physical.lexname == "noun.Tops"

    # An adjective satellite keeps its own ss_type rather than being relabelled "a".
    assert by_id["a#00002098"].pos == "s"
    # "&" is a similar-to pointer, not a hypernym, so it must not be collected.
    assert by_id["a#00001740"].hypernyms == ()


def test_wordnet_rejects_a_file_with_no_synsets(tmp_path: Path) -> None:
    archive = tmp_path / "wordnet.zip"
    write_wordnet_archive(archive)
    _replace_member(archive, "wordnet/data.adv", "  1 only a licence header\n")

    with pytest.raises(WordNetParseError, match="yielded no synsets"):
        load_wordnet(archive, acquisition())


def test_propbank_counts_predicates_rolesets_and_roles(tmp_path: Path) -> None:
    archive = tmp_path / "frames.tar.gz"
    write_propbank_archive(archive)

    snapshot = load_propbank(archive, acquisition(), release="3.4.0")

    # license.xml and README.md are in the tarball but are not frames.
    assert snapshot.frame_file_count == 2
    assert snapshot.predicate_count == 2
    assert snapshot.roleset_count == 3
    assert snapshot.role_count == 6


def test_propbank_keeps_argument_numbers_and_descriptions(tmp_path: Path) -> None:
    archive = tmp_path / "frames.tar.gz"
    write_propbank_archive(archive)

    snapshot = load_propbank(archive, acquisition(), release="3.4.0")
    by_id = {roleset.roleset_id: roleset for roleset in snapshot.sample}

    assert by_id["abandon.01"].lemma == "abandon"
    assert by_id["abandon.01"].name == "leave behind"
    assert by_id["abandon.01"].role_numbers == ("0", "1")
    assert by_id["abandon.01"].role_descriptions == ("abandoner", "entity left behind")
    assert by_id["give.01"].role_numbers == ("0", "1", "2")


def test_propbank_rejects_an_archive_with_no_rolesets(tmp_path: Path) -> None:
    archive = tmp_path / "frames.tar.gz"
    write_propbank_archive(archive, frames=0)

    with pytest.raises(PropBankParseError, match="no rolesets"):
        load_propbank(archive, acquisition(), release="3.4.0")


def test_schemaorg_separates_classes_properties_and_enumeration_members(
    tmp_path: Path,
) -> None:
    document = tmp_path / "schemaorg.jsonld"
    write_schemaorg_document(document)

    snapshot = load_schemaorg(document, acquisition(), release="30.0")

    assert snapshot.graph_node_count == 4
    assert snapshot.class_count == 2
    assert snapshot.property_count == 1
    # Paperback is typed by a schema.org class, so it is an instance, not a class.
    assert snapshot.enumeration_member_count == 1


def test_schemaorg_keeps_the_class_hierarchy(tmp_path: Path) -> None:
    document = tmp_path / "schemaorg.jsonld"
    write_schemaorg_document(document)

    snapshot = load_schemaorg(document, acquisition(), release="30.0")
    by_id = {term.term_id: term for term in snapshot.sample}

    assert by_id["schema:Person"].supertypes == ("schema:Thing",)
    assert by_id["schema:Thing"].supertypes == ()
    assert by_id["schema:Person"].label == "Person"


def test_schemaorg_rejects_a_document_without_a_graph(tmp_path: Path) -> None:
    document = tmp_path / "schemaorg.jsonld"
    document.write_text('{"@context": {}}', encoding="utf-8")

    with pytest.raises(SchemaOrgParseError, match="no @graph"):
        load_schemaorg(document, acquisition(), release="30.0")


def test_schemaorg_rejects_a_graph_with_no_properties(tmp_path: Path) -> None:
    document = tmp_path / "schemaorg.jsonld"
    document.write_text(
        '{"@graph": [{"@id": "schema:Thing", "@type": "rdfs:Class"}]}', encoding="utf-8"
    )

    with pytest.raises(SchemaOrgParseError, match="0 properties"):
        load_schemaorg(document, acquisition(), release="30.0")


def _replace_member(archive: Path, member: str, body: str) -> None:
    """Rewrite one entry of a zip, since ZipFile cannot replace in place."""
    with zipfile.ZipFile(archive) as source:
        entries = {name: source.read(name) for name in source.namelist()}
    entries[member] = body.encode("utf-8")
    with zipfile.ZipFile(archive, "w") as target:
        for name, payload in entries.items():
            target.writestr(name, payload)
