"""The end-to-end build: sources in, deterministic audit bundle out.

Order follows the specification's build sequence: fix the manifest, normalise and parse, build
neutral evidence, run both channels, combine, cluster, gate, then write.

Two things are deliberately absent from the bundle. There is no build timestamp anywhere in it
-- a field excluded from a hash still changes the file's bytes, so time lives in a separate run
receipt that the comparison ignores. And there is no Canonical ID: this layer decides what
*could* be promoted and leaves identity allocation to the stage that owns a seed registry.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from memory_assertion_v1.alignment.canonical_bytes import canonical_bytes, digest
from memory_assertion_v1.alignment.channels import (
    PROMOTION_RULE_VERSION,
    ProposalChannel,
    VerificationChannel,
    run_channel,
)
from memory_assertion_v1.alignment.decisions import (
    ClusterDecision,
    CombinedDecision,
    build_clusters,
    combine,
)
from memory_assertion_v1.alignment.evidence import (
    CANDIDATE_GENERATION_VERSION,
    CandidatePair,
)
from memory_assertion_v1.alignment.gate import GateResult, ProjectedNode, check_all
from memory_assertion_v1.alignment.reports import (
    AlignmentMetrics,
    IngestionCounts,
    QuarantineSummary,
    build_metrics,
    summarize_quarantine,
)
from memory_assertion_v1.alignment.source_manifest import SourceManifest

NonEmptyString = Annotated[str, Field(min_length=1)]

BUNDLE_SCHEMA_VERSION = "alignment-bundle/1"

# The empty set is the operative fact of this round. No structured equivalence rule has been
# authorized, and the two evidence classes that could promote without one are absent between
# these three sources -- so zero promotable clusters is a derivation from stated premises, not
# a shortfall.
AUTHORIZED_EQUIVALENCE_RULES: tuple[str, ...] = ()


class PromotionBundle(BaseModel):
    """The content-addressed input the next stage consumes.

    Carries what identity allocation needs -- cluster kind, ordered source refs, the qualifying
    edges, the projected signature and hierarchy, and the digests of the evidence and gate that
    justified it -- and deliberately no Canonical ID.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    bundle_schema_version: Literal["alignment-bundle/1"] = BUNDLE_SCHEMA_VERSION
    source_manifest_sha256: NonEmptyString
    candidate_generation_version: NonEmptyString
    promotion_rule_version: NonEmptyString
    authorized_equivalence_rules: tuple[NonEmptyString, ...]
    clusters: tuple[dict[str, Any], ...]


class BuildResult(BaseModel):
    """Everything one build produced, before it is written to disk."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    manifest: SourceManifest
    decisions: tuple[CombinedDecision, ...]
    clusters: tuple[ClusterDecision, ...]
    gate_results: tuple[GateResult, ...]
    bundle: PromotionBundle
    quarantine: QuarantineSummary
    metrics: AlignmentMetrics


def run_alignment(
    manifest: SourceManifest,
    candidates: Iterable[CandidatePair],
    nodes: dict[str, ProjectedNode],
    ingestion: IngestionCounts,
    *,
    authorized_equivalence_rules: tuple[str, ...] = AUTHORIZED_EQUIVALENCE_RULES,
    reproducibility: Literal["verified", "unknown"] = "unknown",
) -> BuildResult:
    """Run both channels over every candidate, then cluster and gate.

    Candidates are sorted by their alignment id before anything reads them, so the decision
    order -- and therefore the bytes of every artifact downstream -- does not depend on the
    order candidate generation happened to emit.
    """
    proposal = ProposalChannel()
    verification = VerificationChannel()

    ordered = sorted(candidates, key=lambda candidate: candidate.candidate_alignment_id)
    decisions = tuple(
        combine(
            candidate,
            (
                run_channel(proposal, candidate, authorized_equivalence_rules),
                run_channel(verification, candidate, authorized_equivalence_rules),
            ),
            PROMOTION_RULE_VERSION,
        )
        for candidate in ordered
    )
    clusters = build_clusters(decisions)
    gate_results = check_all(clusters, nodes)

    passed = {result.projected_cluster_id for result in gate_results if result.passed}
    gate_failure_codes = tuple(
        failure.code for result in gate_results for failure in result.failures
    )

    bundle_clusters = tuple(
        {
            "projected_cluster_id": cluster.projected_cluster_id,
            "member_kind": cluster.member_kind,
            "source_refs": [member.model_dump(mode="json") for member in cluster.members],
            "qualifying_edge_decision_ids": list(cluster.edge_decision_ids),
            "projected_signature": sorted(
                {
                    part
                    for member in cluster.members
                    if (node := nodes.get(member.label())) is not None
                    for part in node.signature
                }
            ),
            "projected_parents": sorted(
                {
                    parent
                    for member in cluster.members
                    if (node := nodes.get(member.label())) is not None
                    for parent in node.parents
                }
            ),
        }
        for cluster in clusters
        if cluster.disposition == "promotable" and cluster.projected_cluster_id in passed
    )

    bundle = PromotionBundle(
        source_manifest_sha256=manifest.manifest_sha256(),
        candidate_generation_version=CANDIDATE_GENERATION_VERSION,
        promotion_rule_version=PROMOTION_RULE_VERSION,
        authorized_equivalence_rules=authorized_equivalence_rules,
        clusters=bundle_clusters,
    )

    return BuildResult(
        manifest=manifest,
        decisions=decisions,
        clusters=clusters,
        gate_results=gate_results,
        bundle=bundle,
        quarantine=summarize_quarantine(decisions, clusters),
        metrics=build_metrics(
            decisions,
            clusters,
            ingestion,
            gate_failure_codes,
            reproducibility=reproducibility,
        ),
    )


def _write(path: Path, payload: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = canonical_bytes(payload)
    path.write_bytes(data)
    return digest(payload)


def write_bundle(result: BuildResult, root: Path) -> dict[str, str]:
    """Write every deterministic artifact and return path -> digest.

    The build manifest is written last and records the digests of everything else, which is why
    it cannot contain its own: the hash graph points one way only.
    """
    written: dict[str, str] = {}
    layout: tuple[tuple[str, Any], ...] = (
        ("source-manifest.json", result.manifest.model_dump(mode="json")),
        (
            "rules/alignment-rules.v1.json",
            {
                "candidate_generation_version": CANDIDATE_GENERATION_VERSION,
                "promotion_rule_version": PROMOTION_RULE_VERSION,
                "authorized_equivalence_rules": list(
                    result.bundle.authorized_equivalence_rules
                ),
            },
        ),
        (
            "decisions/combined-decisions.json",
            [decision.model_dump(mode="json") for decision in result.decisions],
        ),
        (
            "decisions/cluster-decisions.json",
            [cluster.model_dump(mode="json") for cluster in result.clusters],
        ),
        (
            "decisions/gate-results.json",
            [gate.model_dump(mode="json") for gate in result.gate_results],
        ),
        ("promotion-bundle.json", result.bundle.model_dump(mode="json")),
        ("build-audit/quarantine-summary.json", result.quarantine.model_dump(mode="json")),
        ("build-audit/alignment-metrics.json", result.metrics.model_dump(mode="json")),
    )
    for relative, payload in layout:
        written[relative] = _write(root / relative, payload)

    build_manifest = {
        "bundle_schema_version": BUNDLE_SCHEMA_VERSION,
        "candidate_generation_version": CANDIDATE_GENERATION_VERSION,
        "promotion_rule_version": PROMOTION_RULE_VERSION,
        "channel_implementations": sorted(
            {
                f"{result_item.channel_id}@{result_item.implementation_sha256}"
                for decision in result.decisions
                for result_item in decision.channel_results
            }
        ),
        "artifacts": [
            {"path": relative, "sha256": written[relative]}
            for relative in sorted(written)
        ],
    }
    written["build-audit/build-manifest.json"] = _write(
        root / "build-audit/build-manifest.json", build_manifest
    )
    return written


def write_run_receipt(root: Path, *, started_at: str, dataset_root: str) -> None:
    """Write the non-deterministic run record, excluded from every comparison.

    Separate file rather than a field, because reproducibility is checked by comparing bytes: a
    timestamp inside a bundle artifact would break that comparison even if no hash covered it.
    """
    (root / "run-receipt.json").write_text(
        json.dumps(
            {"started_at": started_at, "dataset_root": dataset_root},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
