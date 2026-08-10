"""Fixtures for the three source parsers.

Small, inline fixtures so the parser tests run everywhere -- including on a runner with no
corpus. They are not samples of the real files; each one is built to carry a specific
awkward case the real corpora contain, so a parser that only handles the easy shape fails
here rather than in production.

The full-corpus counts live in a separate module and skip without the datasets. The split
matters: parser behaviour is always verified, and only the absolute counts depend on having
16 MB of frozen archives present.
"""

from __future__ import annotations

FAKE_SHA256 = "0" * 64

# Real lines from WordNet 3.0's index.sense, including three of the 1,390 whose lemmas
# carry a leading dot or an apostrophe. Any invented `lemma.pos.nn` pattern rejects these.
WORDNET_INDEX_SENSE = """\
'hood%1:15:00:: 08641944 1 0
's_gravenhage%1:15:00:: 08950407 1 0
.22%1:06:00:: 04502851 1 0
create%2:36:00:: 01617192 1 5
create%2:41:00:: 01640855 3 2
dog%1:05:00:: 02084071 1 42
"""

# One frameset with two predicates sharing a lemma -- the shape that makes frames/cap.xml
# hold 2 predicate elements for 1 distinct lemma.
PROPBANK_TWO_PREDICATES_ONE_LEMMA = b"""<?xml version="1.0" encoding="utf-8"?>
<frameset>
  <predicate lemma="cap">
    <roleset id="cap.01" name="put a cap on">
      <aliases><alias pos="v">cap</alias></aliases>
      <roles>
        <role descr="capper" f="PAG" n="0"/>
        <role descr="thing capped" f="PPT" n="1"/>
      </roles>
    </roleset>
    <roleset id="cap.02" name="set an upper limit">
      <roles><role descr="limiter" f="PAG" n="0"/></roles>
    </roleset>
  </predicate>
  <predicate lemma="cap">
    <roleset id="cap.03" name="surpass">
      <roles><role descr="surpasser" f="PAG" n="0"/></roles>
    </roleset>
  </predicate>
</frameset>
"""

# license.xml really is a frameset for the predicate "license", not a licence file. A
# name-based filter drops it and undercounts the corpus by one roleset and three roles.
PROPBANK_LICENSE = b"""<?xml version="1.0" encoding="utf-8"?>
<frameset>
  <predicate lemma="license">
    <roleset id="license.01" name="give legal rights to property">
      <aliases>
        <alias pos="v">license</alias>
        <alias pos="n">licensing</alias>
      </aliases>
      <roles>
        <role descr="granter of license" f="PAG" n="0"/>
        <role descr="thing licensed" f="PPT" n="1"/>
        <role descr="licensee" f="GOL" n="2"/>
      </roles>
    </roleset>
  </predicate>
</frameset>
"""

# Roleset ids that do not fit a `lemma.nn` shape. All four are real: 40 of the corpus's
# 11,206 rolesets look like this.
PROPBANK_IRREGULAR_IDS = b"""<?xml version="1.0" encoding="utf-8"?>
<frameset>
  <predicate lemma="1500">
    <roleset id="1500.01" name="numeric predicate"/>
  </predicate>
  <predicate lemma="anticoagulate">
    <roleset id="anticoagulate.101" name="three digit sense"/>
  </predicate>
  <predicate lemma="make">
    <roleset id="make.LV" name="light verb"/>
  </predicate>
  <predicate lemma="point">
    <roleset id="point.yy" name="non numeric suffix"/>
  </predicate>
</frameset>
"""

# The two halves of the overhang.01 collision, as they appear in different files.
PROPBANK_HANG = b"""<?xml version="1.0" encoding="utf-8"?>
<frameset>
  <predicate lemma="overhang">
    <roleset id="overhang.01" name="hang over">
      <roles>
        <role descr="thing hanging" f="PPT" n="0"/>
        <role descr="thing hung over" f="GOL" n="1"/>
        <role descr="extent" f="EXT" n="2"/>
        <role descr="direction" f="DIR" n="3"/>
        <role descr="location" f="LOC" n="4"/>
      </roles>
    </roleset>
  </predicate>
</frameset>
"""

PROPBANK_OVERHANG = b"""<?xml version="1.0" encoding="utf-8"?>
<frameset>
  <predicate lemma="overhang">
    <roleset id="overhang.01" name="project outward over">
      <roles>
        <role descr="projecting thing" f="PPT" n="0"/>
        <role descr="thing projected over" f="GOL" n="1"/>
      </roles>
    </roleset>
  </predicate>
</frameset>
"""

# A graph carrying all three term kinds, plus the language-tagged label and list-valued
# subClassOf that 7 and 57 real nodes respectively use.
SCHEMAORG_GRAPH = b"""{
  "@context": {"rdfs": "http://www.w3.org/2000/01/rdf-schema#"},
  "@graph": [
    {
      "@id": "schema:Person",
      "@type": "rdfs:Class",
      "rdfs:label": "Person",
      "rdfs:comment": "A person (alive, dead, undead, or fictional).",
      "rdfs:subClassOf": {"@id": "schema:Thing"}
    },
    {
      "@id": "schema:MedicalClinic",
      "@type": "rdfs:Class",
      "rdfs:label": "MedicalClinic",
      "rdfs:subClassOf": [
        {"@id": "schema:MedicalBusiness"},
        {"@id": "schema:MedicalOrganization"}
      ]
    },
    {
      "@id": "schema:archiveHeld",
      "@type": "rdf:Property",
      "rdfs:label": {"@language": "en", "@value": "archiveHeld"},
      "rdfs:comment": {"@language": "en", "@value": "Collection held by an archive."},
      "rdfs:subPropertyOf": {"@id": "schema:about"}
    },
    {
      "@id": "schema:Paperback",
      "@type": "schema:BookFormatType",
      "rdfs:label": "Paperback",
      "rdfs:comment": "A flexible, lightweight book."
    },
    {
      "@id": "schema:StructuralNodeWithoutALabel",
      "@type": "rdfs:Class"
    }
  ]
}
"""
