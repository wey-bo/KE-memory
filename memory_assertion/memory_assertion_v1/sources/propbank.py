"""PropBank 3.4 roleset records, read from the frame XML files.

Two facts about this corpus drive the design.

**`frames/license.xml` is a real frameset.** Despite the name it defines the predicate
"license" with roleset `license.01` and 3 roles. The existing
`ontology_sources/propbank.py` filters it out by name, which is why the frozen counts
record 11,205 rolesets instead of 11,206. This module reads every frame file and lets the
counts come out right.

**Roleset ids collide across files.** `overhang.01` appears in both `frames/hang.xml` and
`frames/overhang.xml` with different senses and signatures. So a record's identity is
`(artifact_sha256, member_path, roleset_id)` and callers must not key a dictionary by
roleset id alone -- that is exactly how one of the two would disappear.

Roleset ids are taken verbatim from the XML. 40 of them are not `lemma.nn`: `1500.01`,
`anticoagulate.101`, `make.LV`, `point.yy`.
"""

from __future__ import annotations

import tarfile
from collections.abc import Iterator
from pathlib import Path
from xml.etree import ElementTree

from memory_assertion_v1.sources.records import (
    PropBankRoleRecord,
    PropBankRolesetRecord,
    SourceLocation,
)

FRAMES_PREFIX = "frames/"


class PropBankParseError(ValueError):
    """A frame file is not shaped like a PropBank frameset."""


def parse_frame_document(
    payload: bytes, location: SourceLocation
) -> tuple[PropBankRolesetRecord, ...]:
    """Parse every roleset in one frame file.

    A frame file holds one or more `<predicate>` elements, each with one or more
    `<roleset>`. The predicate lemma is recorded per roleset because the roleset id is not
    reliably derivable from it -- `make.LV` belongs to predicate `make`, but `1500.01`
    belongs to `1500`, and neither relationship is a rule.
    """
    try:
        root = ElementTree.fromstring(payload)  # noqa: S314 - frozen local corpus, hash-verified
    except ElementTree.ParseError as error:
        raise PropBankParseError(f"{location.member_path}: {error}") from error
    if root.tag != "frameset":
        raise PropBankParseError(f"{location.member_path}: root is {root.tag!r}, not 'frameset'")

    records: list[PropBankRolesetRecord] = []
    for predicate in root.findall("predicate"):
        lemma = predicate.get("lemma")
        if not lemma:
            raise PropBankParseError(f"{location.member_path}: predicate without a lemma")
        for roleset in predicate.findall("roleset"):
            roleset_id = roleset.get("id")
            if not roleset_id:
                raise PropBankParseError(
                    f"{location.member_path}: roleset without an id under {lemma!r}"
                )
            roles = tuple(
                PropBankRoleRecord(
                    argument=role.get("n") or "",
                    description=role.get("descr") or "",
                    function=role.get("f") or "",
                )
                for role in roleset.findall("roles/role")
            )
            aliases = tuple(
                text.strip()
                for alias in roleset.findall("aliases/alias")
                if (text := alias.text or "").strip()
            )
            records.append(
                PropBankRolesetRecord(
                    location=location,
                    roleset_id=roleset_id,
                    predicate_lemma=lemma,
                    name=roleset.get("name") or "",
                    roles=roles,
                    aliases=aliases,
                )
            )
    return tuple(records)


def iter_roleset_records(
    archive: Path, artifact_sha256: str
) -> Iterator[PropBankRolesetRecord]:
    """Stream every roleset in the archive, including `license.xml`.

    Members are sorted so two runs over one archive yield the same order, which is what
    makes a count reproducible rather than dependent on tar ordering.
    """
    with tarfile.open(archive) as bundle:
        members = sorted(
            (
                member
                for member in bundle.getmembers()
                if member.isfile()
                and member.name.endswith(".xml")
                and f"/{FRAMES_PREFIX}" in member.name
            ),
            key=lambda member: member.name,
        )
        for member in members:
            stream = bundle.extractfile(member)
            if stream is None:
                continue
            payload = stream.read()
            member_path = member.name.split(f"/{FRAMES_PREFIX}", 1)[1]
            location = SourceLocation(
                artifact_sha256=artifact_sha256,
                member_path=f"{FRAMES_PREFIX}{member_path}",
            )
            yield from parse_frame_document(payload, location)
