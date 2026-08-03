"""Candidate-generation indices built from the frozen sources.

Mapper v1 generated candidates by overlapping utterance terms with ontology alias strings. That was
shown not to work: five calibrations traded false mappings against false abstentions without ever
getting both right, because alias overlap cannot distinguish "this turn attests a preference" from
"this turn contains a word that appears in a preference alias".

The fix is different evidence, not a better threshold. Four indices, each contributing a distinct
kind of signal:

- **WordNet** supplies lemma and sense structure, so a term can be recognised as a verb sense rather
  than a string. It also supplies morphological variants, which alias lists never enumerate.
- **PropBank** supplies predicate rolesets. This is the signal alias matching lacked entirely: a
  roleset says a predicate takes an agent and a theme, so an utterance can be checked for
  predicate-argument shape rather than word presence.
- **schema.org** supplies type and property vocabulary for entity-like and attribute-like mentions.
- **Ontology v2** supplies its own aliases and type constraints, which remain the authority on what
  the target inventory actually is.

Each index is built from the raw archives whose hashes the source freeze recorded, and each carries
that hash, so a candidate can be traced to the bytes that produced it.
"""

from __future__ import annotations

import hashlib
import json
import re
import tarfile
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast
from xml.etree import ElementTree

SOURCE_DIR = Path("/public/home/wwb/datasets/ontology-sources")
WORDNET_ARCHIVE = SOURCE_DIR / "wordnet-3.0-nltk.zip"
PROPBANK_ARCHIVE = SOURCE_DIR / "propbank-frames-3.4.0.tar.gz"
SCHEMAORG_FILE = SOURCE_DIR / "schemaorg-30.0-current-https.jsonld"

# Recorded in artifacts/ontology-sources/source-freeze.json. Held here so an index that was built
# from different bytes cannot silently claim this provenance.
WORDNET_SHA256 = "cbda5ea6eef7f36a97a43d4a75f85e07fccbb4f23657d27b4ccbc93e2646ab59"
PROPBANK_SHA256 = "3a9d4d25d8f29b5f536452630e2dd83823ca230c45a3fabde785df21a21957dd"
SCHEMAORG_SHA256 = "4467fa19edcb1d7fb3c46c0adf3591b7f870c4a60b7838bdb61694fd02864cf6"

_WORD = re.compile(r"[a-z][a-z0-9]*")


class SourceIndexError(RuntimeError):
    """An index could not be built, or was built from unexpected bytes."""


def _verify(path: Path, expected: str) -> None:
    """Fail if the archive is not the one the freeze recorded.

    An index built from different bytes than the freeze names would let a citation about PropBank
    point at content nobody reviewed.
    """
    if not path.is_file():
        raise SourceIndexError(f"frozen source is missing: {path}")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != expected:
        raise SourceIndexError(
            f"{path.name} does not match the frozen hash: expected {expected[:16]}, "
            f"got {digest[:16]}"
        )


@dataclass(frozen=True)
class WordNetIndex:
    """Lemma to part-of-speech and sense count, plus morphological variants.

    Sense *count* rather than full glosses: a lemma carrying many senses is inherently ambiguous, and
    that is the signal the mapper needs. Loading every gloss would cost memory for information the
    mapper does not use.
    """

    source_sha256: str
    lemma_pos: dict[str, frozenset[str]] = field(default_factory=lambda: {})
    lemma_sense_count: dict[str, int] = field(default_factory=lambda: {})
    # Maps an inflected form back to its base, so "cancelled" reaches "cancel" without the ontology
    # having to list every inflection as an alias.
    morphology: dict[str, str] = field(default_factory=lambda: {})

    def is_known(self, lemma: str) -> bool:
        return lemma in self.lemma_pos

    def base_form(self, term: str) -> str:
        return self.morphology.get(term, term)

    def polysemy(self, lemma: str) -> int:
        return self.lemma_sense_count.get(lemma, 0)

    def has_pos(self, lemma: str, pos: str) -> bool:
        return pos in self.lemma_pos.get(lemma, frozenset())


@dataclass(frozen=True)
class PropBankRoleset:
    """One roleset: a predicate sense and the arguments it takes."""

    roleset_id: str
    predicate: str
    name: str
    roles: tuple[tuple[str, str], ...]

    @property
    def arity(self) -> int:
        return len(self.roles)


@dataclass(frozen=True)
class PropBankIndex:
    """Lemma to rolesets, which is the predicate-argument signal alias matching lacked."""

    source_sha256: str
    by_lemma: dict[str, tuple[PropBankRoleset, ...]] = field(default_factory=lambda: {})
    by_roleset_id: dict[str, PropBankRoleset] = field(default_factory=lambda: {})

    def rolesets_for(self, lemma: str) -> tuple[PropBankRoleset, ...]:
        return self.by_lemma.get(lemma, ())

    def is_predicate(self, lemma: str) -> bool:
        return lemma in self.by_lemma


@dataclass(frozen=True)
class SchemaOrgIndex:
    """Type and property names, lowercased and split, for entity and attribute mentions."""

    source_sha256: str
    types: dict[str, str] = field(default_factory=lambda: {})
    properties: dict[str, str] = field(default_factory=lambda: {})

    def type_for(self, term: str) -> str | None:
        return self.types.get(term)

    def property_for(self, term: str) -> str | None:
        return self.properties.get(term)


def build_wordnet_index() -> WordNetIndex:
    """Parse the WordNet index files for lemmas, parts of speech and sense counts."""
    _verify(WORDNET_ARCHIVE, WORDNET_SHA256)
    lemma_pos: dict[str, set[str]] = {}
    sense_count: dict[str, int] = {}
    morphology: dict[str, str] = {}

    with zipfile.ZipFile(WORDNET_ARCHIVE) as archive:
        for pos in ("noun", "verb", "adj", "adv"):
            name = f"wordnet/index.{pos}"
            if name not in archive.namelist():
                continue
            with archive.open(name) as handle:
                for raw in handle:
                    line = raw.decode("utf-8", errors="replace")
                    if line.startswith("  "):
                        # The licence header, which every WordNet index file carries.
                        continue
                    parts = line.split()
                    if len(parts) < 3:
                        continue
                    lemma = parts[0].replace("_", " ")
                    lemma_pos.setdefault(lemma, set()).add(pos)
                    try:
                        sense_count[lemma] = max(sense_count.get(lemma, 0), int(parts[2]))
                    except ValueError:
                        continue

        # Exception lists map irregular inflections to their base form.
        for pos in ("noun", "verb", "adj", "adv"):
            name = f"wordnet/{pos}.exc"
            if name not in archive.namelist():
                continue
            with archive.open(name) as handle:
                for raw in handle:
                    fields = raw.decode("utf-8", errors="replace").split()
                    if len(fields) >= 2:
                        morphology[fields[0]] = fields[1]

    # Regular inflections, derived rather than listed: the ontology cannot enumerate every form and a
    # mapper that only matches base forms misses most natural text.
    for lemma in list(lemma_pos):
        if " " in lemma:
            continue
        for suffix, base in (
            ("s", lemma),
            ("es", lemma),
            ("ed", lemma),
            ("d", lemma),
            ("ing", lemma),
        ):
            inflected = f"{lemma}{suffix}"
            morphology.setdefault(inflected, base)
        if lemma.endswith("e"):
            morphology.setdefault(f"{lemma[:-1]}ing", lemma)
        if lemma.endswith("y"):
            morphology.setdefault(f"{lemma[:-1]}ies", lemma)
            morphology.setdefault(f"{lemma[:-1]}ied", lemma)

    return WordNetIndex(
        source_sha256=WORDNET_SHA256,
        lemma_pos={k: frozenset(v) for k, v in lemma_pos.items()},
        lemma_sense_count=sense_count,
        morphology=morphology,
    )


def _propbank_members(archive: tarfile.TarFile) -> Iterator[tarfile.TarInfo]:
    for member in archive:
        if member.isfile() and member.name.endswith(".xml") and "/frames/" in member.name:
            yield member


def build_propbank_index() -> PropBankIndex:
    """Parse every frame file into rolesets keyed by lemma."""
    _verify(PROPBANK_ARCHIVE, PROPBANK_SHA256)
    by_lemma: dict[str, list[PropBankRoleset]] = {}
    by_id: dict[str, PropBankRoleset] = {}

    with tarfile.open(PROPBANK_ARCHIVE, "r:gz") as archive:
        for member in _propbank_members(archive):
            handle = archive.extractfile(member)
            if handle is None:
                continue
            try:
                tree = ElementTree.parse(handle)
            except ElementTree.ParseError:
                # A malformed frame file is skipped rather than aborting the index; the count in the
                # report then differs from the freeze count, which is the visible signal.
                continue
            for roleset in tree.getroot().iter("roleset"):
                roleset_id = str(roleset.get("id", ""))
                if not roleset_id:
                    continue
                predicate = roleset_id.split(".", 1)[0].replace("_", " ")
                roles = tuple(
                    (str(role.get("n", "")), str(role.get("descr", "")))
                    for role in roleset.iter("role")
                    if role.get("n")
                )
                entry = PropBankRoleset(
                    roleset_id=roleset_id,
                    predicate=predicate,
                    name=str(roleset.get("name", predicate)),
                    roles=roles,
                )
                by_lemma.setdefault(predicate, []).append(entry)
                by_id[roleset_id] = entry

    return PropBankIndex(
        source_sha256=PROPBANK_SHA256,
        by_lemma={k: tuple(v) for k, v in by_lemma.items()},
        by_roleset_id=by_id,
    )


def build_schemaorg_index() -> SchemaOrgIndex:
    """Parse the JSON-LD release into type and property names."""
    _verify(SCHEMAORG_FILE, SCHEMAORG_SHA256)
    document = cast("dict[str, Any]", json.loads(SCHEMAORG_FILE.read_text(encoding="utf-8")))
    graph = cast("list[Any]", document.get("@graph", []))
    types: dict[str, str] = {}
    properties: dict[str, str] = {}

    for node in graph:
        if not isinstance(node, dict):
            continue
        typed_node = cast("dict[str, Any]", node)
        node_id = str(typed_node.get("@id", ""))
        node_type: Any = typed_node.get("@type", "")
        label = str(typed_node.get("rdfs:label", "") or "")
        if not node_id or not label:
            continue
        # CamelCase to spaced words, so "PostalAddress" is reachable from "postal address".
        spaced = re.sub(r"(?<!^)(?=[A-Z])", " ", label).lower().strip()
        kinds: list[Any] = (
            cast("list[Any]", node_type) if isinstance(node_type, list) else [node_type]
        )
        if any("rdf:Property" in str(k) for k in kinds):
            properties[spaced] = node_id
        elif any("rdfs:Class" in str(k) for k in kinds):
            types[spaced] = node_id

    return SchemaOrgIndex(
        source_sha256=SCHEMAORG_SHA256, types=types, properties=properties
    )


@dataclass(frozen=True)
class SourceIndices:
    """The three external indices together, with their provenance."""

    wordnet: WordNetIndex
    propbank: PropBankIndex
    schemaorg: SchemaOrgIndex

    def provenance(self) -> dict[str, Any]:
        return {
            "wordnet": {
                "source_sha256": self.wordnet.source_sha256,
                "lemmas": len(self.wordnet.lemma_pos),
                "morphological_variants": len(self.wordnet.morphology),
            },
            "propbank": {
                "source_sha256": self.propbank.source_sha256,
                "predicates": len(self.propbank.by_lemma),
                "rolesets": len(self.propbank.by_roleset_id),
            },
            "schemaorg": {
                "source_sha256": self.schemaorg.source_sha256,
                "types": len(self.schemaorg.types),
                "properties": len(self.schemaorg.properties),
            },
        }


def build_source_indices() -> SourceIndices:
    return SourceIndices(
        wordnet=build_wordnet_index(),
        propbank=build_propbank_index(),
        schemaorg=build_schemaorg_index(),
    )


def content_terms(text: str) -> tuple[str, ...]:
    """Lowercased word tokens, order preserved.

    Order matters here in a way it did not for v1: predicate-argument checking needs to know what
    followed a predicate, which a set cannot express.
    """
    return tuple(_WORD.findall(text.lower()))
