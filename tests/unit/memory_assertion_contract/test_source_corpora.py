"""Absolute counts over the frozen corpora. Skipped when the archives are absent.

Every count here is preceded by a SHA-256 check on the archive. Asserting "7,565 frame
files" against an unverified file would only say something about whatever happened to be on
disk; pinned to a digest, it says something about PropBank 3.4.

These skip without the datasets rather than relaxing. The assertions that do run are
unchanged -- a corpus test that loosened its checks to survive a missing file would report
green while verifying nothing.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

import pytest

from fixtures.datasets import require_dataset
from memory_assertion_v1.sources.propbank import iter_roleset_records
from memory_assertion_v1.sources.schemaorg import iter_term_records
from memory_assertion_v1.sources.wordnet import iter_sense_records

# Digests measured on this host and recorded in artifacts/ontology-sources/source-freeze.json.
WORDNET_SHA256 = "cbda5ea6eef7f36a97a43d4a75f85e07fccbb4f23657d27b4ccbc93e2646ab59"
PROPBANK_SHA256 = "3a9d4d25d8f29b5f536452630e2dd83823ca230c45a3fabde785df21a21957dd"

WORDNET_SENSE_LINES = 206941
WORDNET_AWKWARD_LEMMAS = 1390

PROPBANK_FRAME_FILES = 7565
PROPBANK_PREDICATE_ELEMENTS = 9088
PROPBANK_DISTINCT_FILE_LEMMA_PAIRS = 9087
PROPBANK_ROLESET_OCCURRENCES = 11206
PROPBANK_UNIQUE_ROLESET_IDS = 11205
PROPBANK_ROLES = 28619

SCHEMAORG_GRAPH_NODES = 3219
# Raw `@type` counts over the whole graph, which is what source-freeze.json records.
SCHEMAORG_CLASS_NODES = 1010
SCHEMAORG_PROPERTY_NODES = 1676
# schema.org's *own* terms. The difference is entirely foreign references -- unece:, snomed:,
# fibo-*, gs1: and friends -- which appear as mapping targets and carry no rdfs:label. Every
# unlabelled node is foreign-prefixed and every schema:-prefixed node is labelled, so
# "labelled" and "is a schema.org term" coincide exactly.
SCHEMAORG_OWN_CLASSES = 933
SCHEMAORG_OWN_PROPERTIES = 1521
SCHEMAORG_ENUMERATION_MEMBERS = 533
SCHEMAORG_FOREIGN_CLASS_REFERENCES = SCHEMAORG_CLASS_NODES - SCHEMAORG_OWN_CLASSES
SCHEMAORG_FOREIGN_PROPERTY_REFERENCES = SCHEMAORG_PROPERTY_NODES - SCHEMAORG_OWN_PROPERTIES


def _verified(*parts: str, expected_sha256: str) -> Path:
    """Resolve a dataset path, skip if absent, and fail if it is not the pinned artifact."""
    path = require_dataset(*parts)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert digest == expected_sha256, f"{path} is not the pinned artifact: {digest}"
    return path


@pytest.fixture(scope="module")
def wordnet_archive() -> Path:
    return _verified(
        "ontology-sources", "wordnet-3.0-nltk.zip", expected_sha256=WORDNET_SHA256
    )


@pytest.fixture(scope="module")
def propbank_archive() -> Path:
    return _verified(
        "ontology-sources", "propbank-frames-3.4.0.tar.gz", expected_sha256=PROPBANK_SHA256
    )


@pytest.fixture(scope="module")
def schemaorg_document() -> Path:
    return require_dataset("ontology-sources", "schemaorg-30.0-current-https.jsonld")


def test_wordnet_sense_count(wordnet_archive: Path) -> None:
    records = list(iter_sense_records(wordnet_archive, WORDNET_SHA256))
    assert len(records) == WORDNET_SENSE_LINES


def test_wordnet_awkward_lemmas_all_parse(wordnet_archive: Path) -> None:
    """The 1,390 lemmas a constructed pattern would have rejected."""
    awkward = [
        record
        for record in iter_sense_records(wordnet_archive, WORDNET_SHA256)
        if record.lemma.startswith(".") or "'" in record.lemma or "/" in record.lemma
    ]
    assert len(awkward) == WORDNET_AWKWARD_LEMMAS
    assert all(record.namespaced_id.startswith("wn30:") for record in awkward)


def test_propbank_counts(propbank_archive: Path) -> None:
    """The corrected counts, including license.xml.

    The frozen record in artifacts/ontology-sources/source-freeze.json says 7,564 files,
    11,205 rolesets and 28,616 roles because ontology_sources/propbank.py drops license.xml
    by name. These are the real numbers.
    """
    records = list(iter_roleset_records(propbank_archive, PROPBANK_SHA256))
    files = {record.location.member_path for record in records}
    pairs = {(record.location.member_path, record.predicate_lemma) for record in records}
    roleset_ids = [record.roleset_id for record in records]

    assert len(files) == PROPBANK_FRAME_FILES
    assert len(pairs) == PROPBANK_DISTINCT_FILE_LEMMA_PAIRS
    assert len(records) == PROPBANK_ROLESET_OCCURRENCES
    assert len(set(roleset_ids)) == PROPBANK_UNIQUE_ROLESET_IDS
    assert sum(len(record.roles) for record in records) == PROPBANK_ROLES


def test_propbank_license_file_contributes_a_roleset(propbank_archive: Path) -> None:
    records = [
        record
        for record in iter_roleset_records(propbank_archive, PROPBANK_SHA256)
        if record.location.member_path == "frames/license.xml"
    ]
    assert [record.roleset_id for record in records] == ["license.01"]
    assert len(records[0].roles) == 3


def test_propbank_overhang_collision_is_real(propbank_archive: Path) -> None:
    """One roleset id, two files, two different signatures."""
    records = [
        record
        for record in iter_roleset_records(propbank_archive, PROPBANK_SHA256)
        if record.roleset_id == "overhang.01"
    ]
    assert len(records) == 2
    paths = sorted(record.location.member_path for record in records)
    assert paths == ["frames/hang.xml", "frames/overhang.xml"]
    assert len({len(record.roles) for record in records}) == 2
    assert len({record.location.identity(record.roleset_id) for record in records}) == 2


def test_propbank_duplicate_predicate_lemma_explains_the_element_gap(
    propbank_archive: Path,
) -> None:
    """frames/cap.xml declares `cap` twice: 9,088 elements, 9,087 distinct pairs."""
    records = [
        record
        for record in iter_roleset_records(propbank_archive, PROPBANK_SHA256)
        if record.location.member_path == "frames/cap.xml"
    ]
    assert {record.predicate_lemma for record in records} == {"cap"}
    assert {record.roleset_id for record in records} >= {"cap.01", "cap.02", "cap.03"}
    assert PROPBANK_PREDICATE_ELEMENTS - PROPBANK_DISTINCT_FILE_LEMMA_PAIRS == 1


def test_propbank_irregular_ids_are_present(propbank_archive: Path) -> None:
    """Real ids that do not fit `lemma.nn`."""
    ids = {
        record.roleset_id
        for record in iter_roleset_records(propbank_archive, PROPBANK_SHA256)
    }
    assert {"1500.01", "anticoagulate.101", "make.LV", "point.yy"} <= ids


def test_schemaorg_term_counts(schemaorg_document: Path) -> None:
    """schema.org's own terms, which is fewer than the raw `@type` counts.

    source-freeze.json records 1,010 classes and 1,676 properties by counting graph nodes.
    The parser yields 933 and 1,521, and the difference is not a parsing gap: the remaining
    nodes are foreign references -- `unece:Invoice`, `snomed:387713003`,
    `fibo-fnd-plc-adr:PostalAddress` -- that appear only as mapping targets. Both numbers are
    correct; they answer different questions, and this layer wants the terms schema.org
    actually defines.
    """
    digest = hashlib.sha256(schemaorg_document.read_bytes()).hexdigest()
    records = list(iter_term_records(schemaorg_document, digest))
    kinds = [record.term_kind for record in records]
    assert kinds.count("class") == SCHEMAORG_OWN_CLASSES
    assert kinds.count("property") == SCHEMAORG_OWN_PROPERTIES
    assert kinds.count("enumeration_member") == SCHEMAORG_ENUMERATION_MEMBERS


def test_schemaorg_skips_only_foreign_references(schemaorg_document: Path) -> None:
    """Every term the parser yields is schema.org's own, and nothing of its own is dropped.

    Asserted from both directions, because "933 classes" alone would not distinguish
    dropping 77 foreign nodes from dropping 77 arbitrary ones.
    """
    digest = hashlib.sha256(schemaorg_document.read_bytes()).hexdigest()
    records = list(iter_term_records(schemaorg_document, digest))
    prefixes = {record.term_id.split(":", 1)[0] for record in records}
    assert prefixes == {"schema"}

    document = json.loads(schemaorg_document.read_text(encoding="utf-8"))
    graph = cast("list[dict[str, Any]]", document["@graph"])
    assert len(graph) == SCHEMAORG_GRAPH_NODES
    unlabelled = [node for node in graph if not node.get("rdfs:label")]
    assert len(unlabelled) == (
        SCHEMAORG_FOREIGN_CLASS_REFERENCES + SCHEMAORG_FOREIGN_PROPERTY_REFERENCES
    )
    assert all(
        cast("str", node["@id"]).split(":", 1)[0] != "schema" for node in unlabelled
    )


def test_schemaorg_carries_no_wordnet_or_propbank_links(schemaorg_document: Path) -> None:
    """Why every cross-source alignment has to be authored.

    schema.org mentions neither corpus, so a crosswalk cannot be derived from it -- it can
    only be asserted, with a basis, and reviewed.
    """
    text = schemaorg_document.read_text(encoding="utf-8").lower()
    assert "wordnet" not in text
    assert "propbank" not in text
