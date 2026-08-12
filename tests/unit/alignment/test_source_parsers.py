"""Source parsers, against programmatic fixtures. These always run.

The corpus tests assert absolute counts and skip without the archives; these assert the
behaviours that are easy to break and need no corpus, so a runner still verifies them.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from memory_assertion_v1.sources.propbank import iter_roleset_records
from memory_assertion_v1.sources.schemaorg import iter_term_records
from memory_assertion_v1.sources.wordnet import (
    WordNetParseError,
    iter_sense_records,
    parse_index_sense_line,
)
from memory_assertion_v1.sources.records import SourceLocation

from .fixtures import (
    write_propbank_archive,
    write_schemaorg_document,
    write_wordnet_archive,
)

DIGEST = "b" * 64


def _location() -> SourceLocation:
    return SourceLocation(artifact_sha256=DIGEST, member_path="wordnet/index.sense")


def test_sense_keys_are_taken_verbatim(tmp_path: Path) -> None:
    """Keys with leading apostrophes and dots must survive.

    1,390 real lemmas look like this. A parser that assembled `lemma.pos.sense` from parts, or
    validated a pattern, would reject them -- which is why the sense key is used as WordNet
    spells it.
    """
    archive = tmp_path / "wordnet.zip"
    write_wordnet_archive(archive)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    records = list(iter_sense_records(archive, digest))

    keys = {record.sense_key for record in records}
    assert "'hood%1:15:00::" in keys
    assert ".22%1:06:00::" in keys
    assert {record.namespaced_id for record in records} >= {
        "wn30:'hood%1:15:00::",
        "wn30:.22%1:06:00::",
    }
    lemmas = {record.sense_key: record.lemma for record in records}
    assert lemmas["'hood%1:15:00::"] == "'hood"
    assert lemmas[".22%1:06:00::"] == ".22"


def test_malformed_sense_lines_raise() -> None:
    """A truncated corpus must fail, not silently become a smaller vocabulary."""
    with pytest.raises(WordNetParseError):
        parse_index_sense_line("only_two fields", _location())
    with pytest.raises(WordNetParseError):
        parse_index_sense_line("no_percent_sign 01617192 1", _location())
    with pytest.raises(WordNetParseError):
        parse_index_sense_line("create%2:36:00:: 01617192 0", _location())


def test_colliding_roleset_ids_are_both_kept(tmp_path: Path) -> None:
    """`overhang.01` exists twice with different arity; both records must survive.

    This is the collision that makes a source record's identity a triple. A parser keyed by
    roleset id would return one of these two, and which one would depend on iteration order.
    """
    archive = tmp_path / "propbank.tar.gz"
    write_propbank_archive(archive)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    records = list(iter_roleset_records(archive, digest))

    overhangs = [record for record in records if record.roleset_id == "overhang.01"]
    assert len(overhangs) == 2
    assert {record.location.member_path for record in overhangs} == {
        "frames/hang.xml",
        "frames/overhang.xml",
    }
    assert {len(record.roles) for record in overhangs} == {1, 3}
    identities = {record.location.identity(record.roleset_id) for record in overhangs}
    assert len(identities) == 2


def test_license_xml_is_read_as_a_frameset(tmp_path: Path) -> None:
    """A file named like a licence still holds a predicate.

    Filtering it by name is what made the frozen record report one roleset too few.
    """
    archive = tmp_path / "propbank.tar.gz"
    write_propbank_archive(archive)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    records = list(iter_roleset_records(archive, digest))

    licences = [record for record in records if record.location.member_path.endswith("license.xml")]
    assert [record.roleset_id for record in licences] == ["license.01"]
    assert len(licences[0].roles) == 3


def test_irregular_roleset_ids_are_accepted(tmp_path: Path) -> None:
    """`make.LV` and `1500.01` are real ids; 40 rolesets do not fit `lemma.nn`."""
    archive = tmp_path / "propbank.tar.gz"
    write_propbank_archive(archive)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    ids = {record.roleset_id for record in iter_roleset_records(archive, digest)}
    assert {"make.LV", "1500.01"} <= ids


def test_propbank_records_are_ordered_by_member_path(tmp_path: Path) -> None:
    """Iteration order must not depend on tar ordering, or counts stop being reproducible."""
    archive = tmp_path / "propbank.tar.gz"
    write_propbank_archive(archive)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    paths = [record.location.member_path for record in iter_roleset_records(archive, digest)]
    assert paths == sorted(paths)


def test_schemaorg_reads_both_label_shapes(tmp_path: Path) -> None:
    """Labels are usually strings and occasionally language-tagged objects.

    Seven of each in the real graph. Assuming the string form silently drops those terms.
    """
    document = tmp_path / "schemaorg.jsonld"
    write_schemaorg_document(document)
    digest = hashlib.sha256(document.read_bytes()).hexdigest()
    records = list(iter_term_records(document, digest))

    labels = {record.term_id: record.label for record in records}
    assert labels["schema:Person"] == "Person"
    assert labels["schema:archiveHeld"] == "archiveHeld"


def test_schemaorg_classifies_three_term_kinds(tmp_path: Path) -> None:
    """Classes, properties and enumeration members are distinguished by `@type`."""
    document = tmp_path / "schemaorg.jsonld"
    write_schemaorg_document(document)
    digest = hashlib.sha256(document.read_bytes()).hexdigest()
    kinds = {
        record.term_id: record.term_kind
        for record in iter_term_records(document, digest)
    }
    assert kinds["schema:Person"] == "class"
    assert kinds["schema:archiveHeld"] == "property"
    assert kinds["schema:Paperback"] == "enumeration_member"


def test_unlabeled_foreign_stubs_are_skipped(tmp_path: Path) -> None:
    """232 nodes in the real graph declare a type but no label.

    They exist so schema.org's `equivalentClass` assertions have a subject: `unece:`, `gs1:`,
    `snomed:`, `fibo-`. A term with no surface form yields no lexicalization candidate, so
    ingestion skips it -- and that is also why those assertions cannot bridge these corpora.
    """
    document = tmp_path / "schemaorg.jsonld"
    write_schemaorg_document(document)
    digest = hashlib.sha256(document.read_bytes()).hexdigest()
    ids = {record.term_id for record in iter_term_records(document, digest)}
    assert "unece:SpecifiedCertificate" not in ids
    assert "snomed:387713003" not in ids
    assert "schema:Certification" in ids


def test_schemaorg_reads_subclass_in_both_shapes(tmp_path: Path) -> None:
    """`rdfs:subClassOf` is a single object 888 times and a list 57 times."""
    document = tmp_path / "schemaorg.jsonld"
    write_schemaorg_document(document)
    digest = hashlib.sha256(document.read_bytes()).hexdigest()
    parents = {
        record.term_id: record.parents for record in iter_term_records(document, digest)
    }
    assert parents["schema:Person"] == ("schema:Thing",)
    assert parents["schema:Thing"] == ()
