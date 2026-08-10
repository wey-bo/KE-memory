"""Build-only objects that sit between a source record and a snapshot.

Nothing here may be written into a snapshot. The reason is a contract boundary, not
tidiness: a source record proves a surface form exists in a corpus, while a runtime
Lexicalization asserts that a *canonical owner* is named by that form with a particular
`surface_relation`. Until an owner exists there is no relation to state, so a candidate
that promoted itself would be inventing the one thing it cannot know.

The same applies to cross-source alignment. The three corpora carry no usable links
between each other -- PropBank's `lexlink`/`rolelink` reach only VerbNet and FrameNet,
and schema.org mentions neither WordNet nor PropBank -- so every alignment is an authored
assertion. `ExternalMappingProposal` therefore records who proposed what on which basis
and stays a build artifact for review.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from memory_assertion_v1.ontology.profile import (
    MappingRelation,
    SourceAttestation,
    SourceKind,
)
from memory_assertion_v1.sources.records import (
    PropBankRolesetRecord,
    SchemaOrgTermRecord,
    WordNetSenseRecord,
)

NonEmptyString = Annotated[str, Field(min_length=1)]


class _BuildRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class LexicalizationCandidate(_BuildRecord):
    """A surface form that could name something, with the evidence for it.

    Deliberately missing a `surface_relation` and a `disambiguation_status`. Both belong to
    the owner: whether "create" is an owner's canonical label or an equivalent expression
    depends on which owner, and no amount of corpus evidence decides it.

    `owner_hint` carries the source's own notion of what the form denotes -- a synset
    offset, a roleset id, a schema.org term id -- so a reviewer has somewhere to start. It
    is a hint, never an identity.
    """

    language: NonEmptyString
    surface_form: NonEmptyString
    source_kind: SourceKind
    owner_hint: NonEmptyString
    attestation: SourceAttestation


class ExternalMappingProposal(_BuildRecord):
    """A proposed mapping from a canonical owner to an external target, pending review.

    `basis` is required and free text on purpose: the three sources supply no crosswalk, so
    a proposal that could not say why it was made would be indistinguishable from a guess.
    `status` starts at `proposed` and only a named third-party reviewer may advance it,
    which is why `reviewed_by` is separate from whoever authored it.
    """

    owner_id: NonEmptyString
    relation: MappingRelation
    target: NonEmptyString
    basis: NonEmptyString
    authored_by: NonEmptyString
    status: Literal["proposed", "accepted", "rejected"] = "proposed"
    reviewed_by: NonEmptyString | None = None


def candidate_from_wordnet(
    record: WordNetSenseRecord, *, language: str = "en", provenance_ref: str
) -> LexicalizationCandidate:
    """Build a candidate from a WordNet sense.

    The attestation carries `sense_id` and no `roleset_id`, as the profile's conditional
    matrix requires for `wordnet`. Underscores become spaces because WordNet writes
    multi-word lemmas that way; nothing else about the form is touched -- no case folding,
    no punctuation stripping.
    """
    return LexicalizationCandidate(
        language=language,
        surface_form=record.lemma.replace("_", " "),
        source_kind="wordnet",
        owner_hint=record.synset_offset,
        attestation=SourceAttestation(
            source_kind="wordnet",
            lemma=record.lemma,
            sense_id=record.namespaced_id,
            provenance_refs=(provenance_ref,),
        ),
    )


def candidate_from_propbank(
    record: PropBankRolesetRecord, *, language: str = "en", provenance_ref: str
) -> LexicalizationCandidate:
    """Build a candidate from a PropBank roleset.

    The attestation carries `roleset_id` and no `sense_id`. `owner_hint` is the roleset id
    rather than the predicate lemma, because the roleset is what has a signature.
    """
    return LexicalizationCandidate(
        language=language,
        surface_form=record.predicate_lemma.replace("_", " "),
        source_kind="propbank",
        owner_hint=record.roleset_id,
        attestation=SourceAttestation(
            source_kind="propbank",
            lemma=record.predicate_lemma,
            roleset_id=record.namespaced_id,
            provenance_refs=(provenance_ref,),
        ),
    )


def candidate_from_schemaorg(
    record: SchemaOrgTermRecord, *, language: str = "en", provenance_ref: str
) -> LexicalizationCandidate:
    """Build a candidate from a schema.org term.

    Neither `sense_id` nor `roleset_id`: the matrix forbids both for `schema_org`, since the
    graph publishes no sense inventory to point at.
    """
    return LexicalizationCandidate(
        language=language,
        surface_form=record.label,
        source_kind="schema_org",
        owner_hint=record.term_id,
        attestation=SourceAttestation(
            source_kind="schema_org",
            lemma=record.label,
            provenance_refs=(provenance_ref,),
        ),
    )
