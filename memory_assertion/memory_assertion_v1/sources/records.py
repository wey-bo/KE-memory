"""Read-only records as the three frozen sources actually spell them.

These are the bottom of three layers, and the separation is load-bearing. A source record
says "this artifact contains this entry". A `LexicalizationCandidate` says "this surface
form could name something". A `SourceAttestation` says "this surface form came from
here". Collapsing them would mean deciding a `surface_relation` -- and that is the
canonical owner's decision, so it cannot be made before an owner exists.

Identity is a triple, not the source's own id. PropBank's `overhang.01` appears in both
`frames/hang.xml` and `frames/overhang.xml` with different senses and different
signatures, so keying by roleset id alone silently drops one of them. That collision is
also why the corpus holds 11,206 roleset occurrences but only 11,205 unique ids.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

NonEmptyString = Annotated[str, Field(min_length=1)]
Sha256Hex = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]

WORDNET_NAMESPACE = "wn30:"
PROPBANK_NAMESPACE = "pb3.4:"


class _SourceRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SourceLocation(_SourceRecord):
    """Where a record was read from, precisely enough to be re-read.

    The artifact digest is part of the location because "PropBank 3.4" is not a location:
    two archives claiming that version could differ, and a provenance record that cannot
    distinguish them is not auditable.
    """

    artifact_sha256: Sha256Hex
    member_path: NonEmptyString

    def identity(self, native_id: str) -> tuple[str, str, str]:
        """The triple that uniquely identifies a source record."""
        return (self.artifact_sha256, self.member_path, native_id)


class WordNetSenseRecord(_SourceRecord):
    """One sense from WordNet 3.0's `index.sense`.

    `sense_key` is WordNet's own key, taken verbatim -- `create%2:36:00::`, not a
    `lemma.pos.nn` string assembled here. 1,390 lemmas contain leading dots, apostrophes
    or slashes, so any pattern this implementation invented would reject real data. The
    source already has an authoritative identity; using it is both simpler and correct.
    """

    source_kind: Literal["wordnet"] = "wordnet"
    location: SourceLocation
    sense_key: NonEmptyString
    lemma: NonEmptyString
    synset_offset: NonEmptyString
    sense_number: Annotated[int, Field(ge=1)]

    @property
    def namespaced_id(self) -> str:
        return f"{WORDNET_NAMESPACE}{self.sense_key}"


class PropBankRoleRecord(_SourceRecord):
    """One numbered or modifier role within a roleset."""

    argument: NonEmptyString
    description: str = ""
    function: str = ""


class PropBankRolesetRecord(_SourceRecord):
    """One roleset from a PropBank 3.4 frame file.

    `roleset_id` is the XML's `id` verbatim. 40 of the 11,206 rolesets do not fit a
    `lemma.nn` shape -- `1500.01`, `anticoagulate.101`, `make.LV`, `point.yy` -- so
    validating the shape would discard real framesets.

    `predicate_lemma` is the containing predicate, kept separate because the roleset id is
    not reliably derivable from it and vice versa.
    """

    source_kind: Literal["propbank"] = "propbank"
    location: SourceLocation
    roleset_id: NonEmptyString
    predicate_lemma: NonEmptyString
    name: str = ""
    roles: tuple[PropBankRoleRecord, ...] = ()
    aliases: tuple[NonEmptyString, ...] = ()

    @property
    def namespaced_id(self) -> str:
        return f"{PROPBANK_NAMESPACE}{self.roleset_id}"


SchemaOrgTermKind = Literal["class", "property", "enumeration_member"]


class SchemaOrgTermRecord(_SourceRecord):
    """One class, property or enumeration member from the schema.org graph.

    schema.org carries no `sense_id` or `roleset_id` -- the profile's conditional matrix
    forbids both for `schema_org` -- so `term_id` is the graph's own `@id` and serves only
    as a provenance locator.
    """

    source_kind: Literal["schema_org"] = "schema_org"
    location: SourceLocation
    term_id: NonEmptyString
    label: NonEmptyString
    term_kind: SchemaOrgTermKind
    comment: str = ""
    parents: tuple[NonEmptyString, ...] = ()

    @property
    def namespaced_id(self) -> str:
        return self.term_id
