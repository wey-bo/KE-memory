"""Programmatic source fixtures, so the portable gate can exercise this layer without corpora.

The full corpora are 16 MB of frozen archives that a runner does not have. Tests that need
them skip, which means they cannot be the only coverage -- a skipped test proves nothing. These
fixtures are built in code and always run, so the parsers, channels, gate and determinism are
verified on every gate, and the corpus tests add absolute counts on top.

The fixtures deliberately reproduce the two corpus features that are easy to get wrong: a
PropBank id that collides across two files, and a frame file whose name suggests it is not a
frameset.
"""

from __future__ import annotations

import io
import json
import tarfile
import zipfile
from pathlib import Path

WORDNET_SENSE_LINES = (
    "create%2:36:00:: 01617192 1 0",
    "'hood%1:15:00:: 08641944 1 0",
    ".22%1:06:00:: 04502851 1 0",
    "person%1:03:00:: 07846 1 0",
    "make%2:36:00:: 01621555 3 0",
)
"""Five senses, including the two shapes a constructed pattern would reject.

`'hood` has a leading apostrophe and `.22` a leading dot -- 1,390 real lemmas look like this, so
a fixture without them would let a broken pattern pass.
"""

HANG_FRAME = """<?xml version="1.0" encoding="utf-8"?>
<frameset>
  <predicate lemma="hang">
    <roleset id="hang.01" name="suspend">
      <roles>
        <role descr="hanger" f="PAG" n="0"/>
        <role descr="thing hung" f="PPT" n="1"/>
      </roles>
    </roleset>
    <roleset id="overhang.01" name="project over, from hang.xml">
      <roles>
        <role descr="overhanging thing" f="PPT" n="0"/>
        <role descr="thing overhung" f="GOL" n="1"/>
        <role descr="extent" f="EXT" n="2"/>
      </roles>
    </roleset>
  </predicate>
</frameset>
"""

OVERHANG_FRAME = """<?xml version="1.0" encoding="utf-8"?>
<frameset>
  <predicate lemma="overhang">
    <roleset id="overhang.01" name="project over, from overhang.xml">
      <roles>
        <role descr="overhanging entity" f="PPT" n="0"/>
      </roles>
    </roleset>
  </predicate>
</frameset>
"""
"""`overhang.01` twice, with different arity and different names.

This is the real collision: keying by roleset id alone silently drops one of them, and the
whole reason a source record's identity is (artifact, member path, native id).
"""

LICENSE_FRAME = """<?xml version="1.0" encoding="utf-8"?>
<frameset>
  <predicate lemma="license">
    <roleset id="license.01" name="give legal rights to property">
      <roles>
        <role descr="granter" f="PAG" n="0"/>
        <role descr="thing licensed" f="PPT" n="1"/>
        <role descr="licensee" f="GOL" n="2"/>
      </roles>
    </roleset>
  </predicate>
</frameset>
"""
"""Named like a licence file, actually a frameset -- the entry a name filter would discard."""

ODD_ID_FRAME = """<?xml version="1.0" encoding="utf-8"?>
<frameset>
  <predicate lemma="make">
    <roleset id="make.LV" name="light verb">
      <roles><role descr="agent" f="PAG" n="0"/></roles>
    </roleset>
  </predicate>
  <predicate lemma="1500">
    <roleset id="1500.01" name="numeric predicate">
      <roles><role descr="value" f="PPT" n="0"/></roles>
    </roleset>
  </predicate>
</frameset>
"""
"""`make.LV` and `1500.01`: two of the 40 ids that are not `lemma.nn`."""

SCHEMA_ORG_GRAPH = {
    "@context": {"schema": "https://schema.org/"},
    "@graph": [
        {
            "@id": "schema:Person",
            "@type": "rdfs:Class",
            "rdfs:label": "Person",
            "rdfs:comment": "A person (alive, dead, undead, or fictional).",
            "rdfs:subClassOf": {"@id": "schema:Thing"},
        },
        {
            "@id": "schema:Thing",
            "@type": "rdfs:Class",
            "rdfs:label": "Thing",
            "rdfs:comment": "The most generic type of item.",
        },
        {
            "@id": "schema:archiveHeld",
            "@type": "rdf:Property",
            "rdfs:label": {"@language": "en", "@value": "archiveHeld"},
            "rdfs:comment": {"@language": "en", "@value": "Collection held by an archive."},
        },
        {
            "@id": "schema:Paperback",
            "@type": "schema:BookFormatType",
            "rdfs:label": "Paperback",
            "rdfs:comment": "A paperback book.",
        },
        {
            "@id": "schema:Certification",
            "@type": "rdfs:Class",
            "rdfs:label": "Certification",
            "owl:equivalentClass": [
                {"@id": "unece:SpecifiedCertificate"},
                {"@id": "gs1:CertificationDetails"},
            ],
        },
        {"@id": "unece:SpecifiedCertificate", "@type": "rdfs:Class"},
        {"@id": "snomed:387713003", "@type": "rdfs:Class"},
    ],
}
"""Covers every shape the real graph has: string and language-tagged labels, a single and a
list `subClassOf`, an enumeration member, a source-asserted equivalence whose targets are
foreign, and two unlabeled foreign stubs."""


def write_wordnet_archive(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as bundle:
        bundle.writestr("wordnet/index.sense", "\n".join(WORDNET_SENSE_LINES) + "\n")


def write_propbank_archive(path: Path) -> None:
    frames = {
        "hang.xml": HANG_FRAME,
        "overhang.xml": OVERHANG_FRAME,
        "license.xml": LICENSE_FRAME,
        "make.xml": ODD_ID_FRAME,
    }
    with tarfile.open(path, "w:gz") as bundle:
        for name, text in frames.items():
            payload = text.encode("utf-8")
            info = tarfile.TarInfo(f"propbank-frames-3.4.0/frames/{name}")
            info.size = len(payload)
            bundle.addfile(info, io.BytesIO(payload))


def write_schemaorg_document(path: Path) -> None:
    path.write_text(json.dumps(SCHEMA_ORG_GRAPH, ensure_ascii=False), encoding="utf-8")
