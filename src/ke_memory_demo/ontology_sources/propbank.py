"""Parse PropBank frame files out of the release tarball.

The frames are one XML file per lemma, each holding one or more rolesets (predicate
senses) with numbered arguments. Reading straight from the tarball avoids unpacking 7.5k
small files onto a FUSE mount, where per-file overhead dominates.

The XML declares an external DTD over HTTP. ``ElementTree`` does not fetch external
entities, which is what we want here: the network is restricted and a validating parse
would add nothing -- the fields needed are attributes, not entity expansions.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
import tarfile
from xml.etree import ElementTree

from ke_memory_demo.ontology_sources.models import (
    PropBankRoleset,
    PropBankSnapshot,
    SourceAcquisition,
)

_SAMPLE_LIMIT = 12
# license.xml and README.txt sit in frames/ alongside the real frames; neither is a
# frameset, so they are excluded by name rather than by tolerating a failed parse.
_NON_FRAME_MEMBERS = frozenset({"license.xml"})


class PropBankParseError(ValueError):
    """A PropBank frame file was not a parseable frameset."""


def load_propbank(archive: Path, acquisition: SourceAcquisition, release: str) -> PropBankSnapshot:
    """Parse every roleset in the tarball and return a compact, counted snapshot."""
    frame_files = 0
    predicates = 0
    rolesets = 0
    roles = 0
    sample: list[PropBankRoleset] = []

    with tarfile.open(archive, mode="r:gz") as bundle:
        for member in bundle:
            if not _is_frame_member(member.name):
                continue
            handle = bundle.extractfile(member)
            if handle is None:
                continue
            frame_files += 1
            with handle:
                payload = handle.read()
            for predicate_rolesets in _parse_frameset(payload, member.name):
                predicates += 1
                for roleset in predicate_rolesets:
                    rolesets += 1
                    roles += len(roleset.role_numbers)
                    if len(sample) < _SAMPLE_LIMIT:
                        sample.append(roleset)

    if not rolesets:
        raise PropBankParseError(f"{archive} yielded no rolesets")

    return PropBankSnapshot(
        release=release,
        acquisition=acquisition,
        frame_file_count=frame_files,
        predicate_count=predicates,
        roleset_count=rolesets,
        role_count=roles,
        sample=tuple(sample),
    )


def _is_frame_member(name: str) -> bool:
    parts = name.split("/")
    if len(parts) < 2 or parts[-2] != "frames":
        return False
    leaf = parts[-1]
    return leaf.endswith(".xml") and leaf not in _NON_FRAME_MEMBERS


def _parse_frameset(payload: bytes, member: str) -> Iterator[list[PropBankRoleset]]:
    try:
        root = ElementTree.fromstring(payload)
    except ElementTree.ParseError as error:
        raise PropBankParseError(f"{member} is not well-formed XML: {error}") from error

    for predicate in root.iter("predicate"):
        lemma = predicate.get("lemma")
        if not lemma:
            raise PropBankParseError(f"{member} has a predicate without a lemma")
        yield [_parse_roleset(node, lemma, member) for node in predicate.iter("roleset")]


def _parse_roleset(
    node: ElementTree.Element, lemma: str, member: str
) -> PropBankRoleset:
    roleset_id = node.get("id")
    if not roleset_id:
        raise PropBankParseError(f"{member} has a roleset without an id")
    numbers: list[str] = []
    descriptions: list[str] = []
    for role in node.iter("role"):
        # "n" is the argument number; a role without one is malformed rather than a role
        # we can guess a number for.
        number = role.get("n")
        if number is None:
            raise PropBankParseError(f"{roleset_id} has a role without a number")
        numbers.append(number)
        descriptions.append(role.get("descr", ""))

    return PropBankRoleset(
        roleset_id=roleset_id,
        lemma=lemma,
        name=node.get("name", ""),
        role_numbers=tuple(numbers),
        role_descriptions=tuple(descriptions),
    )
