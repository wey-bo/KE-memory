"""Neutral evidence assembly: candidate pairs and the evidence for and against them.

Neutral is the operative word. This stage assembles every relevant evidence entry and takes
no position on whether a candidate should be promoted. Both channels then read the same
package independently.

The reason is selection bias. If channel two received the evidence channel one had already
filtered, its "independent" verdict would be conditioned on channel one's choices, and two
agreeing votes would not be two pieces of information. So the package is built once, before
either channel runs, and neither may add to it.

This stage also may not stamp `independently_verified` on anything: that level describes what
two channels concluded, not what an input looks like. Neutral evidence carries an
`evidence_kind` (what sort of fact it is) and a `polarity` (which way it points); the level a
candidate actually achieved is decided later, by the combiner.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from memory_assertion_v1.alignment.canonical_bytes import digest, normalize_text

NonEmptyString = Annotated[str, Field(min_length=1)]
Sha256Hex = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]

# Bumped when candidate generation changes which pairs are produced. Part of
# candidate_alignment_id so a pair keeps its identity across promotion-rule changes but not
# across a change in what counts as a candidate.
CANDIDATE_GENERATION_VERSION = "alignment-candidates/1"

EvidenceKind = Literal[
    "source_asserted_link",
    "identity_link",
    "definition",
    "hierarchy",
    "signature",
    "lexical_match",
]
Polarity = Literal["supports", "contradicts", "context_only"]
MemberKind = Literal["concept", "operator"]

# Only these two kinds can promote on their own. Everything else generates candidates and
# supplies context; `lexical_match` can never promote, however many entries agree.
PROMOTING_EVIDENCE_KINDS: frozenset[str] = frozenset({"source_asserted_link", "identity_link"})


class _EvidenceRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SourceRecordRef(_EvidenceRecord):
    """A source record, identified by the triple that survives id collisions.

    `native_id` alone is not enough: PropBank's `overhang.01` exists in two frame files with
    different signatures, so a reference that named only the roleset id would be ambiguous.
    """

    source: NonEmptyString
    artifact_sha256: Sha256Hex
    member_path: NonEmptyString
    native_id: NonEmptyString

    def sort_key(self) -> tuple[str, str, str, str]:
        return (self.source, self.artifact_sha256, self.member_path, self.native_id)

    def label(self) -> str:
        return f"{self.source}:{self.member_path}#{self.native_id}"


class EvidenceEntry(_EvidenceRecord):
    """One fact about a candidate pair, with its kind and direction.

    `detail` records what was actually observed -- the shared ancestor, the matching lemma,
    the asserted link's target -- so a reviewer can re-check the entry rather than trusting
    its classification.
    """

    evidence_kind: EvidenceKind
    polarity: Polarity
    detail: NonEmptyString

    def sort_key(self) -> tuple[str, str, str]:
        return (self.evidence_kind, self.polarity, self.detail)


class CandidatePair(_EvidenceRecord):
    """Two source records that might denote the same thing, and everything known about it.

    Atomic and binary on purpose. Clusters are derived later from promotable edges, so a
    reviewer always has a pair-level decision to examine rather than a merged group whose
    internal justification has been lost.

    `member_kind` is part of the pair because a Concept candidate and an Operator candidate
    are checked against different rules, and a pair spanning the two kinds is not a candidate
    at all.
    """

    left: SourceRecordRef
    right: SourceRecordRef
    member_kind: MemberKind
    evidence: tuple[EvidenceEntry, ...]

    @property
    def candidate_alignment_id(self) -> str:
        """Identity from the members and the candidate-generation version only.

        Deliberately independent of evidence and promotion rules: changing how promotion is
        decided must not turn a pair into a different pair, or longitudinal audit across rule
        versions becomes impossible.
        """
        return digest(
            {
                "candidate_generation_version": CANDIDATE_GENERATION_VERSION,
                "member_kind": self.member_kind,
                "members": [
                    member.model_dump(mode="json")
                    for member in sorted((self.left, self.right), key=lambda m: m.sort_key())
                ],
            }
        )

    @property
    def evidence_sha256(self) -> str:
        """Digest of the evidence set, used by decision identity."""
        return digest([entry.model_dump(mode="json") for entry in self.evidence])

    def has_promoting_evidence(self) -> bool:
        """Whether any entry is of a kind that may promote on its own.

        Read by both channels, which is safe: it reports a property of the neutral evidence,
        not a verdict about it.
        """
        return any(
            entry.evidence_kind in PROMOTING_EVIDENCE_KINDS and entry.polarity == "supports"
            for entry in self.evidence
        )

    def contradictions(self) -> tuple[EvidenceEntry, ...]:
        return tuple(entry for entry in self.evidence if entry.polarity == "contradicts")


def make_candidate(
    left: SourceRecordRef,
    right: SourceRecordRef,
    member_kind: MemberKind,
    evidence: tuple[EvidenceEntry, ...],
) -> CandidatePair:
    """Build a candidate with its members and evidence in stable order.

    Members are sorted so that a pair has one spelling regardless of which side was
    discovered first; evidence likewise, since the set is semantically unordered.
    """
    ordered = sorted((left, right), key=lambda member: member.sort_key())
    return CandidatePair(
        left=ordered[0],
        right=ordered[1],
        member_kind=member_kind,
        evidence=tuple(sorted(evidence, key=lambda entry: entry.sort_key())),
    )


def lexical_evidence(surface_form: str) -> EvidenceEntry:
    """A shared surface form -- context only, never grounds for promotion.

    Recorded rather than discarded because it is why the pair became a candidate at all, and a
    reviewer needs to see the reason even when it carries no weight.
    """
    return EvidenceEntry(
        evidence_kind="lexical_match",
        polarity="context_only",
        detail=f"shared NFC surface form: {normalize_text(surface_form)}",
    )
