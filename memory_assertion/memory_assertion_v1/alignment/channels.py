"""The two promotion channels, and the isolation that makes their agreement mean something.

Channel one reads the neutral evidence and asks whether a sufficient basis for equivalence is
present. Channel two, independently, reconstructs that basis from the same neutral evidence
*and* actively looks for grounds against it. Both are required of channel two: a check that
only fails to find conflicts has shown that nothing contradicts equivalence, which is not the
same as having shown equivalence, and its checks would largely duplicate the gate's.

Isolation is structural rather than promised. `ChannelInput` carries no field for the other
channel's verdict, so neither implementation can read it -- there is nothing to read. Each
channel also records its own implementation identity and code digest, so a reviewer can tell
that two verdicts came from two implementations rather than one function called twice.

Both channels are deterministic rule implementations. No model is called. The cost is a
coverage ceiling -- only source-asserted and identity-level evidence can promote -- and that
ceiling is accepted: this layer's output is an auditable, byte-reproducible artifact, and a
model call would make the same input produce different bytes.
"""

from __future__ import annotations

import inspect
from typing import Annotated, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from memory_assertion_v1.alignment.canonical_bytes import digest_bytes
from memory_assertion_v1.alignment.evidence import (
    PROMOTING_EVIDENCE_KINDS,
    CandidatePair,
)

NonEmptyString = Annotated[str, Field(min_length=1)]

# Bumped when the promotion rules change. Part of decision identity, not candidate identity.
PROMOTION_RULE_VERSION = "alignment-promotion/1"

ChannelVerdict = Literal[
    "supports_equivalence", "contradicts_equivalence", "insufficient_evidence"
]


class _ChannelRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ChannelInput(_ChannelRecord):
    """What a channel is allowed to see.

    Note what is absent: no other channel's verdict, no disposition, no combiner output. The
    isolation the specification requires is expressed as a type that cannot carry those
    things, rather than as a rule an implementation is trusted to follow.
    """

    candidate: CandidatePair
    authorized_equivalence_rules: tuple[NonEmptyString, ...]


class ChannelResult(_ChannelRecord):
    """One channel's verdict, with the reasoning and the identity of what produced it."""

    channel_id: NonEmptyString
    implementation_sha256: NonEmptyString
    rule_version: NonEmptyString
    candidate_alignment_id: NonEmptyString
    verdict: ChannelVerdict
    rationale: tuple[NonEmptyString, ...]

    def sort_key(self) -> tuple[str, str]:
        return (self.candidate_alignment_id, self.channel_id)


class PromotionChannel(Protocol):
    """A channel: an identity plus a verdict function."""

    channel_id: str

    def judge(self, payload: ChannelInput) -> ChannelResult: ...


def _implementation_digest(*functions: object) -> str:
    """Digest the channel's own source text.

    Recorded so that "two channels agreed" is checkable rather than asserted: if both
    identities were ever to become the same digest, the second vote would be worthless and
    this makes that visible.
    """
    payload = "".join(inspect.getsource(function) for function in functions)  # type: ignore[arg-type]
    return digest_bytes(payload.encode("utf-8"))


class ProposalChannel:
    """Channel one: is a sufficient basis for equivalence present?

    Sufficiency is narrow by contract. A supporting entry must be `source_asserted_link` or
    `identity_link`, or the pair must match an authorized structured equivalence rule.
    Definitions, hierarchies and signatures are necessary context, never sufficient on their
    own -- so a candidate resting only on them is `insufficient_evidence`, not a rejection.
    """

    channel_id = "proposal/v1"

    def judge(self, payload: ChannelInput) -> ChannelResult:
        candidate = payload.candidate
        rationale: list[str] = []

        promoting = [
            entry
            for entry in candidate.evidence
            if entry.evidence_kind in PROMOTING_EVIDENCE_KINDS and entry.polarity == "supports"
        ]
        contradicting = candidate.contradictions()

        if contradicting:
            rationale.extend(
                f"contradicted by {entry.evidence_kind}: {entry.detail}"
                for entry in contradicting
            )
            verdict: ChannelVerdict = "contradicts_equivalence"
        elif promoting:
            rationale.extend(
                f"supported by {entry.evidence_kind}: {entry.detail}" for entry in promoting
            )
            verdict = "supports_equivalence"
        else:
            kinds = sorted({entry.evidence_kind for entry in candidate.evidence})
            rationale.append(
                "no source-asserted or identity-level support; "
                f"only {', '.join(kinds) or 'no evidence'}"
            )
            verdict = "insufficient_evidence"

        return ChannelResult(
            channel_id=self.channel_id,
            implementation_sha256=_implementation_digest(ProposalChannel.judge),
            rule_version=PROMOTION_RULE_VERSION,
            candidate_alignment_id=candidate.candidate_alignment_id,
            verdict=verdict,
            rationale=tuple(rationale),
        )


class VerificationChannel:
    """Channel two: independently rebuild the basis, and try to break it.

    Two obligations, both required. Positive sufficiency reconstructs the supporting chain
    from the neutral evidence without consulting channel one -- it must independently reach
    the conclusion that the chain exists and is of a promoting kind. Falsification then looks
    for anything pointing the other way, including evidence that is merely absent where it
    should be present.

    The asymmetry with channel one is real: this channel requires that a promoting entry be
    *corroborated* by at least one contextual entry (a definition, hierarchy or signature
    fact). An asserted link with no other evidence about the two records is thin enough that
    two independent readers should not both be satisfied by it.
    """

    channel_id = "verification/v1"

    def judge(self, payload: ChannelInput) -> ChannelResult:
        candidate = payload.candidate
        rationale: list[str] = []

        # Falsification first, so a contradiction cannot be outweighed by counting supports.
        contradicting = candidate.contradictions()
        if contradicting:
            rationale.extend(
                f"falsified by {entry.evidence_kind}: {entry.detail}"
                for entry in contradicting
            )
            return self._result(candidate, "contradicts_equivalence", rationale)

        # Positive sufficiency, rebuilt from the neutral evidence.
        chain = [
            entry
            for entry in candidate.evidence
            if entry.evidence_kind in PROMOTING_EVIDENCE_KINDS and entry.polarity == "supports"
        ]
        if not chain:
            rationale.append("no promoting evidence chain could be rebuilt independently")
            return self._result(candidate, "insufficient_evidence", rationale)

        corroboration = [
            entry
            for entry in candidate.evidence
            if entry.evidence_kind in {"definition", "hierarchy", "signature"}
            and entry.polarity in {"supports", "context_only"}
        ]
        if not corroboration:
            rationale.append(
                "promoting evidence is uncorroborated: no definition, hierarchy or "
                "signature entry describes either record"
            )
            return self._result(candidate, "insufficient_evidence", rationale)

        rationale.extend(
            f"rebuilt chain via {entry.evidence_kind}: {entry.detail}" for entry in chain
        )
        rationale.extend(
            f"corroborated by {entry.evidence_kind}: {entry.detail}"
            for entry in corroboration
        )
        return self._result(candidate, "supports_equivalence", rationale)

    def _result(
        self, candidate: CandidatePair, verdict: ChannelVerdict, rationale: list[str]
    ) -> ChannelResult:
        return ChannelResult(
            channel_id=self.channel_id,
            implementation_sha256=_implementation_digest(
                VerificationChannel.judge, VerificationChannel._result
            ),
            rule_version=PROMOTION_RULE_VERSION,
            candidate_alignment_id=candidate.candidate_alignment_id,
            verdict=verdict,
            rationale=tuple(rationale),
        )


def run_channel(
    channel: PromotionChannel,
    candidate: CandidatePair,
    authorized_equivalence_rules: tuple[str, ...],
) -> ChannelResult:
    """Run one channel over one candidate."""
    return channel.judge(
        ChannelInput(
            candidate=candidate,
            authorized_equivalence_rules=authorized_equivalence_rules,
        )
    )
