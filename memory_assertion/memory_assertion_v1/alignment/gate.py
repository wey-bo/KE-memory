"""The projected-merge gate: check the graph the merge would produce, not the records.

The distinction is the whole point. Checking two source records against each other says
nothing about what happens when a cluster collapses them into one node -- a merge can be
locally reasonable and still put a cycle in the hierarchy, or land one node on both sides of a
disjointness, or make two operators indistinguishable. So the gate builds the projected graph
first, substituting a temporary cluster identity for its members, and checks that.

Temporary is literal: `projected_cluster_id` is an audit identity derived from members and
rule versions. No Canonical ID is minted here, and the gate validates only source and audit
ids. Canonical id form belongs to the stage that allocates them.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from memory_assertion_v1.alignment.decisions import ClusterDecision
from memory_assertion_v1.alignment.evidence import SourceRecordRef

NonEmptyString = Annotated[str, Field(min_length=1)]

GateFailureCode = Literal[
    "parent_cycle",
    "disjoint_straddle",
    "signature_collision",
    "kind_not_closed",
    "codec_not_closed",
    "version_not_closed",
]


class _GateRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ProjectedNode(_GateRecord):
    """One source record's projected properties, as the gate needs them.

    Deliberately a flat projection rather than the source record itself: the gate reasons about
    hierarchy, disjointness, signature and codec, and giving it the full record would invite
    checks that belong to the ontology validator.
    """

    ref: SourceRecordRef
    member_kind: Literal["concept", "operator"]
    parents: tuple[NonEmptyString, ...] = ()
    disjoint_with: tuple[NonEmptyString, ...] = ()
    signature: tuple[NonEmptyString, ...] = ()
    codec_id: NonEmptyString | None = None
    source_version: NonEmptyString | None = None

    def label(self) -> str:
        return self.ref.label()


class GateFailure(_GateRecord):
    code: GateFailureCode
    subject: NonEmptyString
    detail: NonEmptyString

    def sort_key(self) -> tuple[str, str, str]:
        return (self.code, self.subject, self.detail)


class GateResult(_GateRecord):
    """Whether the projected merge is admissible, and every reason it is not."""

    projected_cluster_id: NonEmptyString
    passed: bool
    failures: tuple[GateFailure, ...]


def _projection(
    cluster: ClusterDecision, nodes: dict[str, ProjectedNode]
) -> tuple[dict[str, str], set[str]]:
    """Map every member label to the cluster id that replaces it."""
    collapsed = {member.label() for member in cluster.members}
    mapping = {label: cluster.projected_cluster_id for label in collapsed}
    return mapping, collapsed


def check_cluster(
    cluster: ClusterDecision,
    nodes: dict[str, ProjectedNode],
) -> GateResult:
    """Check the graph that would exist if this cluster's members were one node.

    Every failure is collected rather than returning on the first, for the same reason the
    ontology validator collects: a builder needs the whole picture of why a merge is
    inadmissible, not its first symptom.
    """
    failures: list[GateFailure] = []
    mapping, collapsed = _projection(cluster, nodes)
    members = [nodes[label] for label in sorted(collapsed) if label in nodes]
    missing = sorted(label for label in collapsed if label not in nodes)
    for label in missing:
        failures.append(
            GateFailure(
                code="kind_not_closed",
                subject=cluster.projected_cluster_id,
                detail=f"no projected node for member {label}",
            )
        )
    if not members:
        return GateResult(
            projected_cluster_id=cluster.projected_cluster_id,
            passed=False,
            failures=tuple(sorted(failures, key=lambda item: item.sort_key())),
        )

    kinds = {member.member_kind for member in members}
    if len(kinds) > 1:
        failures.append(
            GateFailure(
                code="kind_not_closed",
                subject=cluster.projected_cluster_id,
                detail=f"members span kinds {sorted(kinds)}",
            )
        )

    # Parent cycle: a member's ancestor is inside the cluster, so collapsing makes the node
    # its own ancestor.
    for member in members:
        for parent in member.parents:
            if mapping.get(parent, parent) == cluster.projected_cluster_id:
                failures.append(
                    GateFailure(
                        code="parent_cycle",
                        subject=cluster.projected_cluster_id,
                        detail=f"{member.label()} inherits from cluster member {parent}",
                    )
                )

    # Disjoint straddle: the cluster would be disjoint from itself, or from a node it also
    # inherits from after projection.
    projected_disjoint = {
        mapping.get(target, target) for member in members for target in member.disjoint_with
    }
    if cluster.projected_cluster_id in projected_disjoint:
        failures.append(
            GateFailure(
                code="disjoint_straddle",
                subject=cluster.projected_cluster_id,
                detail="cluster members are declared disjoint from each other",
            )
        )
    projected_parents = {
        mapping.get(parent, parent) for member in members for parent in member.parents
    }
    for shared in sorted(projected_disjoint & projected_parents):
        failures.append(
            GateFailure(
                code="disjoint_straddle",
                subject=cluster.projected_cluster_id,
                detail=f"cluster would both inherit from and be disjoint from {shared}",
            )
        )

    # Signature uniqueness: operators in one cluster must agree, or the merged operator has no
    # single signature.
    signatures = {
        tuple(mapping.get(part, part) for part in member.signature)
        for member in members
        if member.member_kind == "operator"
    }
    if len(signatures) > 1:
        failures.append(
            GateFailure(
                code="signature_collision",
                subject=cluster.projected_cluster_id,
                detail=f"members carry {len(signatures)} distinct projected signatures",
            )
        )

    codecs = {member.codec_id for member in members if member.codec_id is not None}
    if len(codecs) > 1:
        failures.append(
            GateFailure(
                code="codec_not_closed",
                subject=cluster.projected_cluster_id,
                detail=f"members carry codecs {sorted(codecs)}",
            )
        )

    versions = {
        member.source_version for member in members if member.source_version is not None
    }
    if len(versions) > 1:
        failures.append(
            GateFailure(
                code="version_not_closed",
                subject=cluster.projected_cluster_id,
                detail=f"members span source versions {sorted(versions)}",
            )
        )

    return GateResult(
        projected_cluster_id=cluster.projected_cluster_id,
        passed=not failures,
        failures=tuple(sorted(failures, key=lambda item: item.sort_key())),
    )


def check_all(
    clusters: tuple[ClusterDecision, ...], nodes: dict[str, ProjectedNode]
) -> tuple[GateResult, ...]:
    """Gate every cluster, including those already quarantined.

    Quarantined clusters are checked too: a component that failed for one reason may also be
    structurally inadmissible, and recording both keeps the audit complete rather than
    stopping at the first disqualification.
    """
    return tuple(
        sorted(
            (check_cluster(cluster, nodes) for cluster in clusters),
            key=lambda result: result.projected_cluster_id,
        )
    )
