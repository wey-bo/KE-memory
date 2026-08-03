"""Frozen models for third-party ontology sources acquired at pinned versions.

A prior review recorded WordNet, PropBank and schema.org as ``unconsulted`` because the
host could not reach them. The debt was not "no ontology data" but "no *evidence* about
where the data came from", so every model here carries acquisition provenance beside the
parsed content: the exact URL, the resolved commit or release, and a SHA-256 over the raw
downloaded bytes.

Two design choices follow from that:

- :class:`SourceAcquisition` distinguishes ``acquired`` from ``unavailable`` as a tagged
  state rather than as "empty content". An empty item list is otherwise indistinguishable
  from a source that parsed to nothing, and the review specifically forbids a silent empty.
  :class:`UnavailableSource` therefore requires the commands tried and their failure modes;
  an honest failure is representable, an invented synset id is not.
- Each snapshot hashes *itself* and nothing else. There is no combined digest over all
  three sources, for the same reason ontology v1 refused one: a single hash says something
  moved without saying which source moved, so a citation about WordNet would be invalidated
  by a schema.org release.
"""

from __future__ import annotations

from enum import StrEnum
import hashlib
from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from ke_memory_demo.core.json import canonical_json

NonEmptyString = Annotated[str, Field(min_length=1)]

# The digest is taken over the snapshot's canonical JSON with this key removed, so a
# snapshot can carry its own hash without the hash covering itself.
_FREEZE_KEY: Final[str] = "freeze"

HASH_SCOPE: Final[str] = (
    "SHA-256 over the canonical JSON of this source snapshot alone, excluding this freeze "
    "block; a change to another ontology source cannot move this digest"
)


class SourceName(StrEnum):
    """The three sources the review requires acquired and frozen."""

    WORDNET = "wordnet"
    PROPBANK = "propbank"
    SCHEMAORG = "schemaorg"


class FrozenModel(BaseModel):
    """Immutable, closed model. Unknown keys are a parse bug, not a field to keep."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class SourceAcquisition(FrozenModel):
    """Where the bytes came from and how to prove it is the same bytes.

    ``raw_path`` is an absolute path outside the repository. The raw archives are tens of
    megabytes and the constraint is to keep them out of git, so the manifest references
    them by path plus digest instead of vendoring them.
    """

    status: Literal["acquired"] = "acquired"
    url: NonEmptyString
    # Resolved to an immutable identifier: a git commit, a blob sha, or a release tag.
    # A branch name is not acceptable here because it moves.
    resolved_version: NonEmptyString
    raw_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    raw_bytes: Annotated[int, Field(gt=0)]
    raw_path: NonEmptyString
    licence: NonEmptyString
    retrieved_at: NonEmptyString


class UnavailableSource(FrozenModel):
    """A source that genuinely could not be obtained, with the evidence of trying.

    The commands are required and non-empty: "unavailable" without a reproducible failure
    is indistinguishable from "not attempted", which is the state the review rejected.
    """

    status: Literal["unavailable"] = "unavailable"
    source: SourceName
    url: NonEmptyString
    commands_tried: Annotated[tuple[NonEmptyString, ...], Field(min_length=1)]
    failure_mode: NonEmptyString


class WordNetSynset(FrozenModel):
    """One synset from a WordNet ``data.<pos>`` file."""

    # Offsets are per-part-of-speech, so the id is qualified; a bare offset collides.
    synset_id: NonEmptyString
    offset: NonEmptyString
    pos: NonEmptyString
    lexname: NonEmptyString
    words: tuple[NonEmptyString, ...]
    gloss: str
    hypernyms: tuple[NonEmptyString, ...]


class WordNetSnapshot(FrozenModel):
    """Parsed WordNet 3.0 content plus its acquisition record."""

    source: Literal[SourceName.WORDNET] = SourceName.WORDNET
    release: NonEmptyString
    acquisition: SourceAcquisition
    synset_count_by_pos: dict[str, int]
    lexname_count: int
    # A sample rather than all 117k synsets: the artifact is a compact, reviewable snapshot
    # and the counts above are the load-bearing evidence that the parse really ran.
    sample: tuple[WordNetSynset, ...]

    @property
    def total_synsets(self) -> int:
        return sum(self.synset_count_by_pos.values())


class PropBankRoleset(FrozenModel):
    """One roleset (a predicate sense) with its numbered arguments."""

    roleset_id: NonEmptyString
    lemma: NonEmptyString
    name: str
    # ``n`` attribute of each role: "0", "1", "m" ... kept as text because PropBank uses
    # non-numeric values for modifiers.
    role_numbers: tuple[str, ...]
    role_descriptions: tuple[str, ...]


class PropBankSnapshot(FrozenModel):
    """Parsed PropBank frame content plus its acquisition record."""

    source: Literal[SourceName.PROPBANK] = SourceName.PROPBANK
    release: NonEmptyString
    acquisition: SourceAcquisition
    frame_file_count: int
    predicate_count: int
    roleset_count: int
    role_count: int
    sample: tuple[PropBankRoleset, ...]


class SchemaOrgTerm(FrozenModel):
    """One schema.org class or property."""

    term_id: NonEmptyString
    label: NonEmptyString
    # "rdfs:Class" or "rdf:Property"; enumeration members carry their own type and are
    # counted separately.
    term_type: NonEmptyString
    supertypes: tuple[NonEmptyString, ...]
    comment: str


class SchemaOrgSnapshot(FrozenModel):
    """Parsed schema.org vocabulary plus its acquisition record."""

    source: Literal[SourceName.SCHEMAORG] = SourceName.SCHEMAORG
    release: NonEmptyString
    acquisition: SourceAcquisition
    graph_node_count: int
    class_count: int
    property_count: int
    enumeration_member_count: int
    sample: tuple[SchemaOrgTerm, ...]


def snapshot_sha256(snapshot: BaseModel) -> str:
    """Digest a snapshot's canonical JSON, excluding any freeze block it already carries.

    Excluding the freeze block keeps the digest reproducible from a written artifact: read
    the file, drop ``freeze``, re-hash, and the value must match what the file claims.
    """
    payload = snapshot.model_dump(mode="json")
    payload.pop(_FREEZE_KEY, None)
    return hashlib.sha256(canonical_json(payload)).hexdigest()
