"""Miniature but format-faithful stand-ins for the three source archives.

These exist so the parser tests do not depend on the ~16 MB archives outside the
repository. They are deliberately built in the *real* formats -- hexadecimal word counts in
the WordNet data lines, a nested ``predicate``/``roleset``/``role`` tree in the PropBank
XML, a flat ``@graph`` for schema.org -- because a fixture in a simplified format would
pass while the real parser broke.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
import tarfile
import zipfile

from ke_memory_demo.ontology_sources.models import SourceAcquisition

_LEXNAMES = "00\tadj.all\t3\n03\tnoun.Tops\t1\n29\tverb.possession\t2\n02\tadv.all\t4\n"

# Two synsets per part of speech. "  " prefixed lines are the copyright header the real
# files carry and the parser must skip.
_DATA_NOUN = (
    "  1 This software and database is being provided to you...\n"
    "00001740 03 n 01 entity 0 001 ~ 00001930 n 0000 | that which is perceived  \n"
    "00001930 03 n 02 physical_entity 0 thing 1 001 @ 00001740 n 0000 "
    "| an entity that has physical existence  \n"
)
_DATA_VERB = (
    "  1 header\n"
    "02260085 29 v 02 change_hands 0 change_owners 0 001 @ 02260362 v 0000 "
    "| be transferred to another owner  \n"
    "02260362 29 v 01 transfer 0 000 | cause to change ownership  \n"
)
_DATA_ADJ = (
    "  1 header\n"
    "00001740 00 a 01 able 0 001 & 00002098 a 0000 | having the necessary means  \n"
    "00002098 00 s 01 unable 0 000 | lacking the power to perform  \n"
)
_DATA_ADV = (
    "  1 header\n"
    "00001740 02 r 01 a_cappella 0 000 | without instrumental accompaniment  \n"
    "00002062 02 r 01 ad_libitum 0 000 | without advance preparation  \n"
)

_FRAME_XML = """<?xml version="1.0" encoding="utf-8"?>
<frameset>
  <predicate lemma="abandon">
    <roleset id="abandon.01" name="leave behind">
      <roles>
        <role descr="abandoner" f="PPT" n="0"/>
        <role descr="entity left behind" f="DIR" n="1"/>
      </roles>
    </roleset>
    <roleset id="abandon.02" name="give up">
      <roles>
        <role descr="giver" f="PAG" n="0"/>
      </roles>
    </roleset>
  </predicate>
</frameset>
"""

_SECOND_FRAME_XML = """<?xml version="1.0" encoding="utf-8"?>
<frameset>
  <predicate lemma="give">
    <roleset id="give.01" name="transfer">
      <roles>
        <role descr="giver" f="PAG" n="0"/>
        <role descr="thing given" f="PPT" n="1"/>
        <role descr="entity given to" f="GOL" n="2"/>
      </roles>
    </roleset>
  </predicate>
</frameset>
"""


def write_wordnet_archive(path: Path) -> None:
    """A four-file WordNet database holding eight synsets in total."""
    with zipfile.ZipFile(path, "w") as bundle:
        bundle.writestr("wordnet/lexnames", _LEXNAMES)
        bundle.writestr("wordnet/data.noun", _DATA_NOUN)
        bundle.writestr("wordnet/data.verb", _DATA_VERB)
        bundle.writestr("wordnet/data.adj", _DATA_ADJ)
        bundle.writestr("wordnet/data.adv", _DATA_ADV)


def write_propbank_archive(path: Path, *, frames: int = 2) -> None:
    """A frames tarball, including the ``license.xml`` the parser must not treat as a frame."""
    bodies = {"abandon.xml": _FRAME_XML, "give.xml": _SECOND_FRAME_XML}
    with tarfile.open(path, mode="w:gz") as bundle:
        for name, body in list(bodies.items())[:frames]:
            _add(bundle, f"propbank-frames-3.4.0/frames/{name}", body)
        _add(bundle, "propbank-frames-3.4.0/frames/license.xml", "<license/>")
        _add(bundle, "propbank-frames-3.4.0/README.md", "not a frame")


def write_schemaorg_document(path: Path, *, extra_classes: int = 0) -> None:
    """A flat JSON-LD graph with a class, a property and an enumeration member."""
    graph: list[dict[str, object]] = [
        {
            "@id": "schema:Thing",
            "@type": "rdfs:Class",
            "rdfs:label": "Thing",
            "rdfs:comment": "The most generic type of item.",
        },
        {
            "@id": "schema:Person",
            "@type": "rdfs:Class",
            "rdfs:label": "Person",
            "rdfs:comment": "A person (alive, dead, undead, or fictional).",
            "rdfs:subClassOf": {"@id": "schema:Thing"},
        },
        {
            "@id": "schema:name",
            "@type": "rdf:Property",
            "rdfs:label": "name",
            "rdfs:comment": "The name of the item.",
        },
        {
            "@id": "schema:Paperback",
            "@type": "schema:BookFormatType",
            "rdfs:label": "Paperback",
        },
    ]
    for index in range(extra_classes):
        graph.append(
            {
                "@id": f"schema:Extra{index}",
                "@type": "rdfs:Class",
                "rdfs:label": f"Extra{index}",
            }
        )
    path.write_text(json.dumps({"@graph": graph}), encoding="utf-8")


def acquisition(sha256: str = "0" * 64, *, raw_bytes: int = 1024) -> SourceAcquisition:
    """A stand-in acquisition record for tests that exercise parsing, not provenance."""
    return SourceAcquisition(
        url="https://api.github.com/repos/example/example/git/blobs/deadbeef",
        resolved_version="test-fixture",
        raw_sha256=sha256,
        raw_bytes=raw_bytes,
        raw_path="/tmp/fixture",
        licence="test",
        retrieved_at="2026-08-03",
    )


def _add(bundle: tarfile.TarFile, name: str, body: str) -> None:
    payload = body.encode("utf-8")
    info = tarfile.TarInfo(name=name)
    info.size = len(payload)
    bundle.addfile(info, io.BytesIO(payload))
