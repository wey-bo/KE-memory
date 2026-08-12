"""Channels, combiner, clustering and gate.

The assertions worth reading here are the negative ones. A promotion layer that accepted
nothing would pass a suite that only checked "nothing was promoted", so several tests
construct evidence strong enough to promote and then confirm that removing one property is
what blocks it.
"""

from __future__ import annotations

import itertools

import pytest

from memory_assertion_v1.alignment.channels import (
    PROMOTION_RULE_VERSION,
    ProposalChannel,
    VerificationChannel,
    run_channel,
)
from memory_assertion_v1.alignment.decisions import build_clusters, combine
from memory_assertion_v1.alignment.evidence import (
    CandidatePair,
    EvidenceEntry,
    SourceRecordRef,
    lexical_evidence,
    make_candidate,
)
from memory_assertion_v1.alignment.gate import ProjectedNode, check_cluster

DIGEST = "a" * 64


def ref(native_id: str, source: str = "wordnet") -> SourceRecordRef:
    return SourceRecordRef(
        source=source, artifact_sha256=DIGEST, member_path="m", native_id=native_id
    )


def entry(kind: str, polarity: str, detail: str = "d") -> EvidenceEntry:
    return EvidenceEntry(evidence_kind=kind, polarity=polarity, detail=detail)  # type: ignore[arg-type]


def promoting_evidence() -> tuple[EvidenceEntry, ...]:
    """The minimum that can promote: an identity link plus corroboration."""
    return (
        entry("identity_link", "supports", "sense keys linked"),
        entry("definition", "context_only", "definitions agree"),
    )


def decide(candidate: CandidatePair):
    results = (
        run_channel(ProposalChannel(), candidate, ()),
        run_channel(VerificationChannel(), candidate, ()),
    )
    return combine(candidate, results, PROMOTION_RULE_VERSION)


def test_identity_link_with_corroboration_is_promotable() -> None:
    """The positive baseline, without which every negative test proves nothing."""
    decision = decide(make_candidate(ref("A"), ref("B"), "concept", promoting_evidence()))
    assert decision.disposition == "promotable"
    assert decision.achieved_evidence_level == "identity_level"


def test_lexical_match_alone_never_promotes() -> None:
    """A shared surface form is context, whatever else accompanies it.

    78% of the WordNet/PropBank lemma overlap is polysemous on at least one side, so promoting
    on a shared lemma would merge senses that are not the same sense.
    """
    decision = decide(
        make_candidate(
            ref("A"),
            ref("B"),
            "concept",
            (lexical_evidence("create"), entry("definition", "context_only")),
        )
    )
    assert decision.disposition == "quarantined"
    assert decision.quarantine_reason == "insufficient_evidence"
    assert decision.achieved_evidence_level == "none"


def test_uncorroborated_promoting_evidence_is_quarantined() -> None:
    """Channel two requires corroboration, so the two votes are not one vote twice.

    An identity link with nothing else known about either record is thin enough that two
    independent readers should not both be satisfied -- and this is where the channels differ.
    """
    candidate = make_candidate(
        ref("A"), ref("B"), "concept", (entry("identity_link", "supports"),)
    )
    proposal = run_channel(ProposalChannel(), candidate, ())
    verification = run_channel(VerificationChannel(), candidate, ())
    assert proposal.verdict == "supports_equivalence"
    assert verification.verdict == "insufficient_evidence"

    decision = combine(candidate, (proposal, verification), PROMOTION_RULE_VERSION)
    assert decision.disposition == "quarantined"
    assert decision.quarantine_reason == "channel_disagreement"


def test_contradicting_evidence_is_rejected_not_quarantined() -> None:
    """"Shown not equivalent" and "not shown equivalent" must stay distinguishable."""
    decision = decide(
        make_candidate(
            ref("A"),
            ref("B"),
            "concept",
            (entry("identity_link", "contradicts", "explicitly not equivalent"),),
        )
    )
    assert decision.disposition == "rejected"
    assert decision.quarantine_reason is None


def test_channels_have_distinct_implementations() -> None:
    """Two identical implementations would make the second vote worthless."""
    candidate = make_candidate(ref("A"), ref("B"), "concept", promoting_evidence())
    proposal = run_channel(ProposalChannel(), candidate, ())
    verification = run_channel(VerificationChannel(), candidate, ())
    assert proposal.channel_id != verification.channel_id
    assert proposal.implementation_sha256 != verification.implementation_sha256


def test_channel_input_cannot_carry_the_other_verdict() -> None:
    """Isolation is structural: there is no field to read, so it cannot be read."""
    from memory_assertion_v1.alignment.channels import ChannelInput

    fields = set(ChannelInput.model_fields)
    assert fields == {"candidate", "authorized_equivalence_rules"}
    assert not any("verdict" in name or "disposition" in name for name in fields)


def test_candidate_identity_ignores_promotion_rules() -> None:
    """Changing promotion rules must produce a new decision about the same candidate.

    If the candidate id moved too, longitudinal audit across rule versions would break: the
    same pair would look like a different pair.
    """
    candidate = make_candidate(ref("A"), ref("B"), "concept", promoting_evidence())
    first = combine(
        candidate,
        (
            run_channel(ProposalChannel(), candidate, ()),
            run_channel(VerificationChannel(), candidate, ()),
        ),
        "alignment-promotion/1",
    )
    second = combine(
        candidate,
        (
            run_channel(ProposalChannel(), candidate, ()),
            run_channel(VerificationChannel(), candidate, ()),
        ),
        "alignment-promotion/2",
    )
    assert first.candidate_alignment_id == second.candidate_alignment_id
    assert first.decision_id != second.decision_id


def test_member_order_does_not_change_candidate_identity() -> None:
    """A pair has one spelling regardless of which side was discovered first."""
    forward = make_candidate(ref("A"), ref("B"), "concept", promoting_evidence())
    reverse = make_candidate(ref("B"), ref("A"), "concept", promoting_evidence())
    assert forward.candidate_alignment_id == reverse.candidate_alignment_id


@pytest.mark.parametrize("ordering", list(itertools.permutations(range(3))))
def test_conflict_triangle_quarantines_the_whole_component(ordering: tuple[int, ...]) -> None:
    """`A~B`, `B~C`, `A≁C`: the component quarantines whole, in every edge order.

    A greedy walk would merge whichever supported pair it reached first and discover the
    contradiction afterwards, so the answer would depend on iteration order. Parametrising over
    all six orderings is the point of the test.
    """
    a, b, c = ref("A"), ref("B"), ref("C")
    pairs = [
        make_candidate(a, b, "concept", promoting_evidence()),
        make_candidate(b, c, "concept", promoting_evidence()),
        make_candidate(
            a, c, "concept", (entry("identity_link", "contradicts", "not equivalent"),)
        ),
    ]
    decisions = tuple(decide(pairs[index]) for index in ordering)
    clusters = build_clusters(decisions)

    assert len(clusters) == 1
    cluster = clusters[0]
    assert cluster.disposition == "quarantined"
    assert cluster.quarantine_reason == "conflicting_component"
    assert {member.native_id for member in cluster.members} == {"A", "B", "C"}


def test_promotable_edges_without_conflict_form_a_cluster() -> None:
    """The positive case for clustering, so the triangle test is not vacuous."""
    a, b, c = ref("A"), ref("B"), ref("C")
    decisions = (
        decide(make_candidate(a, b, "concept", promoting_evidence())),
        decide(make_candidate(b, c, "concept", promoting_evidence())),
    )
    clusters = build_clusters(decisions)
    assert len(clusters) == 1
    assert clusters[0].disposition == "promotable"
    assert len(clusters[0].members) == 3


def _cluster_of(*refs: SourceRecordRef):
    decisions = tuple(
        decide(make_candidate(left, right, "concept", promoting_evidence()))
        for left, right in itertools.pairwise(refs)
    )
    return build_clusters(decisions)[0]


def test_gate_passes_a_clean_projection() -> None:
    left, right = ref("X"), ref("Y")
    cluster = _cluster_of(left, right)
    nodes = {
        left.label(): ProjectedNode(ref=left, member_kind="concept"),
        right.label(): ProjectedNode(ref=right, member_kind="concept"),
    }
    assert check_cluster(cluster, nodes).passed


@pytest.mark.parametrize(
    ("code", "left_kwargs", "right_kwargs"),
    [
        ("parent_cycle", {"parents": ("wordnet:m#Y",)}, {}),
        ("disjoint_straddle", {"disjoint_with": ("wordnet:m#Y",)}, {}),
        (
            "signature_collision",
            {"member_kind": "operator", "signature": ("c1",)},
            {"member_kind": "operator", "signature": ("c2",)},
        ),
        (
            "codec_not_closed",
            {"codec_id": "ke-literal:boolean/v1"},
            {"codec_id": "ke-literal:text-nfc/v1"},
        ),
        ("version_not_closed", {"source_version": "3.0"}, {"source_version": "3.1"}),
        ("kind_not_closed", {"member_kind": "concept"}, {"member_kind": "operator"}),
    ],
)
def test_gate_rejects_each_inadmissible_projection(
    code: str, left_kwargs: dict[str, object], right_kwargs: dict[str, object]
) -> None:
    """Each projected-merge defect must fire its own code.

    Injection rather than inspection: a gate whose checks were never triggered would pass the
    clean case and prove nothing about the rest.
    """
    left, right = ref("X"), ref("Y")
    cluster = _cluster_of(left, right)
    nodes = {
        left.label(): ProjectedNode(
            ref=left, **{"member_kind": "concept", **left_kwargs}  # type: ignore[arg-type]
        ),
        right.label(): ProjectedNode(
            ref=right, **{"member_kind": "concept", **right_kwargs}  # type: ignore[arg-type]
        ),
    }
    result = check_cluster(cluster, nodes)
    assert not result.passed
    assert code in {failure.code for failure in result.failures}
