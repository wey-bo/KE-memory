"""Combining channel verdicts into pair dispositions, and clustering promotable edges.

Three dispositions, not four: `promotable`, `rejected`, `quarantined`. The distinction that
matters is between "we can show these are not equivalent" and "we cannot show they are" --
collapsing those two would let an unproven candidate read as a refuted one.

Clustering is where traversal order becomes a correctness question. Given `A~B`, `B~C` and an
explicit `A≁C`, a greedy walk merges whichever pair it reaches first and produces a different
answer depending on iteration order. So a connected component containing any contradicted
pair is quarantined whole, and the result is independent of the order the edges arrive in.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from memory_assertion_v1.alignment.canonical_bytes import digest
from memory_assertion_v1.alignment.channels import ChannelResult
from memory_assertion_v1.alignment.evidence import CandidatePair, MemberKind, SourceRecordRef

NonEmptyString = Annotated[str, Field(min_length=1)]

Disposition = Literal["promotable", "rejected", "quarantined"]
AchievedEvidenceLevel = Literal[
    "source_asserted", "identity_level", "independently_verified", "lexical_only", "none"
]
QuarantineReasonCode = Literal[
    "channel_disagreement",
    "insufficient_evidence",
    "gate_failed",
    "conflicting_component",
]


class _DecisionRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class CombinedDecision(_DecisionRecord):
    """The authoritative final state of one candidate pair.

    Authoritative means: the quarantine summary and the metrics report are computed from
    these records, and never the other way round. A derived view that disagreed with this
    would be a bug in the view.
    """

    decision_id: NonEmptyString
    candidate_alignment_id: NonEmptyString
    member_kind: MemberKind
    members: tuple[SourceRecordRef, ...]
    disposition: Disposition
    achieved_evidence_level: AchievedEvidenceLevel
    quarantine_reason: QuarantineReasonCode | None = None
    channel_results: tuple[ChannelResult, ...]
    rationale: tuple[NonEmptyString, ...]

    def sort_key(self) -> tuple[str, str]:
        return (self.candidate_alignment_id, self.decision_id)


class ClusterDecision(_DecisionRecord):
    """The authoritative final state of one connected component of promotable edges.

    A cluster is derived from pair decisions rather than decided independently, so its
    disposition can only be as strong as its weakest edge.
    """

    projected_cluster_id: NonEmptyString
    member_kind: MemberKind
    members: tuple[SourceRecordRef, ...]
    edge_decision_ids: tuple[NonEmptyString, ...]
    disposition: Disposition
    quarantine_reason: QuarantineReasonCode | None = None
    rationale: tuple[NonEmptyString, ...]

    def sort_key(self) -> tuple[str, str]:
        return (self.member_kind, self.projected_cluster_id)


def _achieved_level(candidate: CandidatePair, disposition: Disposition) -> AchievedEvidenceLevel:
    """What level the pair actually reached, decided here rather than at assembly.

    `independently_verified` is reported only for a pair both channels accepted -- it names an
    outcome of the two-channel process, so a neutral input can never carry it.
    """
    if disposition != "promotable":
        kinds = {entry.evidence_kind for entry in candidate.evidence}
        if kinds and kinds <= {"lexical_match"}:
            return "lexical_only"
        return "none"
    supporting = {
        entry.evidence_kind for entry in candidate.evidence if entry.polarity == "supports"
    }
    if "source_asserted_link" in supporting:
        return "source_asserted"
    if "identity_link" in supporting:
        return "identity_level"
    return "independently_verified"


def decision_identity(
    candidate: CandidatePair,
    results: tuple[ChannelResult, ...],
    promotion_rule_version: str,
) -> str:
    """Identity from the candidate, its evidence, the rules, and both channel outcomes.

    Layered deliberately: the candidate id depends only on members and generation version, so
    re-running with different promotion rules produces a new *decision* about the same
    *candidate* rather than an unrelated pair.
    """
    return digest(
        {
            "candidate_alignment_id": candidate.candidate_alignment_id,
            "evidence_sha256": candidate.evidence_sha256,
            "promotion_rule_version": promotion_rule_version,
            "channels": [
                {
                    "channel_id": result.channel_id,
                    "implementation_sha256": result.implementation_sha256,
                    "verdict": result.verdict,
                }
                for result in sorted(results, key=lambda item: item.sort_key())
            ],
        }
    )


def combine(
    candidate: CandidatePair,
    results: tuple[ChannelResult, ...],
    promotion_rule_version: str,
) -> CombinedDecision:
    """Combine two channel verdicts into one disposition.

    Both channels must say `supports_equivalence` for a pair to be promotable, and the gate
    still runs afterwards. Disagreement is quarantine, not a tie broken by preference: two
    implementations reaching different conclusions is exactly the case a human should see.
    """
    verdicts = {result.verdict for result in results}
    ordered = tuple(sorted(results, key=lambda item: item.sort_key()))
    rationale: list[str] = []
    for result in ordered:
        rationale.extend(f"{result.channel_id}: {line}" for line in result.rationale)

    reason: QuarantineReasonCode | None = None
    if verdicts == {"supports_equivalence"}:
        disposition: Disposition = "promotable"
    elif verdicts == {"contradicts_equivalence"}:
        disposition = "rejected"
    elif len(verdicts) > 1:
        disposition = "quarantined"
        reason = "channel_disagreement"
        rationale.append(f"channels disagreed: {sorted(verdicts)}")
    else:
        disposition = "quarantined"
        reason = "insufficient_evidence"

    return CombinedDecision(
        decision_id=decision_identity(candidate, ordered, promotion_rule_version),
        candidate_alignment_id=candidate.candidate_alignment_id,
        member_kind=candidate.member_kind,
        members=(candidate.left, candidate.right),
        disposition=disposition,
        achieved_evidence_level=_achieved_level(candidate, disposition),
        quarantine_reason=reason,
        channel_results=ordered,
        rationale=tuple(rationale),
    )


def _component_id(member_kind: str, members: tuple[SourceRecordRef, ...]) -> str:
    return digest(
        {
            "member_kind": member_kind,
            "members": [member.model_dump(mode="json") for member in members],
        }
    )


def build_clusters(decisions: tuple[CombinedDecision, ...]) -> tuple[ClusterDecision, ...]:
    """Group promotable edges into components, quarantining any component with a conflict.

    Components are built over promotable *and* rejected edges together, then any component
    touched by a rejection is quarantined whole. Building only over promotable edges would
    reproduce the greedy bug: `A~B`, `B~C` would merge and the explicit `A≁C` would be
    discovered afterwards, if at all.
    """
    parent: dict[str, str] = {}

    def find(node: str) -> str:
        parent.setdefault(node, node)
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(left: str, right: str) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            if left_root < right_root:
                parent[right_root] = left_root
            else:
                parent[left_root] = right_root

    refs: dict[str, SourceRecordRef] = {}
    relevant = [
        decision for decision in decisions if decision.disposition in {"promotable", "rejected"}
    ]
    for decision in relevant:
        for member in decision.members:
            refs[member.label()] = member
        union(decision.members[0].label(), decision.members[1].label())

    grouped: dict[str, list[CombinedDecision]] = {}
    for decision in relevant:
        grouped.setdefault(find(decision.members[0].label()), []).append(decision)

    clusters: list[ClusterDecision] = []
    for root, edges in sorted(grouped.items()):
        member_labels = sorted({label for edge in edges for label in (
            edge.members[0].label(), edge.members[1].label()
        )})
        members = tuple(refs[label] for label in member_labels)
        kinds = {edge.member_kind for edge in edges}
        member_kind: MemberKind = "concept" if kinds == {"concept"} else "operator"
        rejected = [edge for edge in edges if edge.disposition == "rejected"]
        promotable = [edge for edge in edges if edge.disposition == "promotable"]

        rationale: list[str] = []
        if rejected:
            disposition: Disposition = "quarantined"
            reason: QuarantineReasonCode | None = "conflicting_component"
            rationale.append(
                f"component holds {len(rejected)} rejected edge(s); quarantined whole so the "
                "outcome does not depend on traversal order"
            )
        elif len(kinds) > 1:
            disposition = "quarantined"
            reason = "conflicting_component"
            rationale.append(f"component mixes member kinds: {sorted(kinds)}")
        else:
            disposition = "promotable"
            reason = None
            rationale.append(f"component of {len(promotable)} promotable edge(s)")

        clusters.append(
            ClusterDecision(
                projected_cluster_id=_component_id(member_kind, members),
                member_kind=member_kind,
                members=members,
                edge_decision_ids=tuple(sorted(edge.decision_id for edge in edges)),
                disposition=disposition,
                quarantine_reason=reason,
                rationale=tuple(rationale),
            )
        )
        _ = root
    return tuple(sorted(clusters, key=lambda cluster: cluster.sort_key()))
