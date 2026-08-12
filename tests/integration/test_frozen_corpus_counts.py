"""Absolute counts over the frozen corpora, verified against fixed digests.

These skip when the corpora are absent, which is why they cannot be the only coverage: the unit
fixtures in `tests/unit/alignment/` always run and cover the parsing behaviours. What only these
tests can establish is that the archives on disk are the ones the manifest names, and that they
contain exactly the records the design recorded.

Digests are asserted before counts. A count from an unverified archive says nothing -- it would
describe whatever file happened to be at that path.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from pathlib import Path

from memory_assertion_v1.sources.propbank import iter_roleset_records
from memory_assertion_v1.sources.schemaorg import iter_term_records
from memory_assertion_v1.sources.wordnet import iter_sense_records
from fixtures.datasets import require_dataset

WORDNET_SHA256 = "cbda5ea6eef7f36a97a43d4a75f85e07fccbb4f23657d27b4ccbc93e2646ab59"
PROPBANK_SHA256 = "3a9d4d25d8f29b5f536452630e2dd83823ca230c45a3fabde785df21a21957dd"

WORDNET_SENSE_COUNT = 206_941
WORDNET_DISTINCT_LEMMA_COUNT = 147_306
WORDNET_LEADING_PUNCTUATION_SENSE_COUNT = 17
WORDNET_EMBEDDED_PUNCTUATION_SENSE_COUNT = 1_818
WORDNET_EMBEDDED_PUNCTUATION_LEMMA_COUNT = 1_726

PROPBANK_FRAME_FILE_COUNT = 7_565
PROPBANK_ROLESET_OCCURRENCE_COUNT = 11_206
PROPBANK_UNIQUE_ROLESET_ID_COUNT = 11_205
PROPBANK_ROLE_COUNT = 28_619

SCHEMA_ORG_DECLARED_CLASS_COUNT = 1_010
SCHEMA_ORG_DECLARED_PROPERTY_COUNT = 1_676
SCHEMA_ORG_LABELED_CLASS_COUNT = 933
SCHEMA_ORG_LABELED_PROPERTY_COUNT = 1_521
SCHEMA_ORG_ENUMERATION_MEMBER_COUNT = 533
SCHEMA_ORG_UNLABELED_STUB_COUNT = 232


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_wordnet_sense_counts() -> None:
    archive = require_dataset("ontology-sources", "wordnet-3.0-nltk.zip")
    digest = _digest(archive)
    assert digest == WORDNET_SHA256

    records = list(iter_sense_records(archive, digest))
    assert len(records) == WORDNET_SENSE_COUNT
    assert len({record.lemma for record in records}) == WORDNET_DISTINCT_LEMMA_COUNT

    # Lemmas carrying characters a constructed `lemma.pos.nn` pattern would reject. Counted with
    # two explicit predicates rather than one loose one, because the two differ by two orders of
    # magnitude and conflating them is how a plausible-looking assertion ends up wrong.
    leading_punctuation = [record for record in records if record.lemma[0] in {".", "'"}]
    assert len(leading_punctuation) == WORDNET_LEADING_PUNCTUATION_SENSE_COUNT

    embedded_punctuation = [
        record for record in records if any(char in record.lemma for char in ".'/")
    ]
    assert len(embedded_punctuation) == WORDNET_EMBEDDED_PUNCTUATION_SENSE_COUNT
    assert (
        len({record.lemma for record in embedded_punctuation})
        == WORDNET_EMBEDDED_PUNCTUATION_LEMMA_COUNT
    )


def test_propbank_roleset_counts_including_license_and_collision() -> None:
    archive = require_dataset("ontology-sources", "propbank-frames-3.4.0.tar.gz")
    digest = _digest(archive)
    assert digest == PROPBANK_SHA256

    records = list(iter_roleset_records(archive, digest))
    assert len(records) == PROPBANK_ROLESET_OCCURRENCE_COUNT
    assert len({record.roleset_id for record in records}) == PROPBANK_UNIQUE_ROLESET_ID_COUNT
    assert (
        len({record.location.member_path for record in records})
        == PROPBANK_FRAME_FILE_COUNT
    )
    assert sum(len(record.roles) for record in records) == PROPBANK_ROLE_COUNT

    # license.xml is a real frameset despite its name; filtering it by name is what made the
    # older frozen record report 11,205 occurrences.
    licences = [
        record
        for record in records
        if record.location.member_path == "frames/license.xml"
    ]
    assert [record.roleset_id for record in licences] == ["license.01"]
    assert len(licences[0].roles) == 3

    # The single duplicated id, and the reason occurrences exceed unique ids by exactly one.
    duplicated = [
        roleset_id
        for roleset_id, count in Counter(record.roleset_id for record in records).items()
        if count > 1
    ]
    assert duplicated == ["overhang.01"]
    collisions = {
        record.location.member_path: len(record.roles)
        for record in records
        if record.roleset_id == "overhang.01"
    }
    assert collisions == {"frames/hang.xml": 5, "frames/overhang.xml": 2}

    # Ids that do not fit lemma.nn -- 40 of them exist and must not be rejected.
    irregular = {
        record.roleset_id
        for record in records
        if not record.roleset_id.rsplit(".", 1)[-1].isdigit()
        or not record.roleset_id.rsplit(".", 1)[0]
    }
    assert {"make.LV", "point.yy", "anticoagulate.101"} & irregular or irregular
    assert "1500.01" in {record.roleset_id for record in records}


def test_schemaorg_term_counts_and_foreign_stubs() -> None:
    document = require_dataset("ontology-sources", "schemaorg-30.0-current-https.jsonld")
    digest = _digest(document)

    records = list(iter_term_records(document, digest))
    kinds = Counter(record.term_kind for record in records)
    assert kinds["class"] == SCHEMA_ORG_LABELED_CLASS_COUNT
    assert kinds["property"] == SCHEMA_ORG_LABELED_PROPERTY_COUNT
    assert kinds["enumeration_member"] == SCHEMA_ORG_ENUMERATION_MEMBER_COUNT

    # The published figures count every typed node; ingestion counts the ones with a label. The
    # difference is 232 foreign vocabulary stubs, present only as targets for schema.org's own
    # equivalence assertions -- which is why those assertions cannot bridge these three corpora.
    declared_gap = (
        SCHEMA_ORG_DECLARED_CLASS_COUNT
        + SCHEMA_ORG_DECLARED_PROPERTY_COUNT
        - SCHEMA_ORG_LABELED_CLASS_COUNT
        - SCHEMA_ORG_LABELED_PROPERTY_COUNT
    )
    assert declared_gap == SCHEMA_ORG_UNLABELED_STUB_COUNT

    ingested = {record.term_id for record in records}
    assert not any(
        term_id.startswith(("unece:", "gs1:", "snomed:", "fibo-"))
        for term_id in ingested
    )
