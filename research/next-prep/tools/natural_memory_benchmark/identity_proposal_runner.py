from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .identity_proposal import (
    run_reference_identity_proposer,
    score_identity_proposal_payload,
)
from .io import write_json_immutable, write_text_immutable


def render_identity_proposal_report(payload: dict[str, Any]) -> str:
    metrics = payload["metrics"]
    gate_status = "pass" if payload["gate_safety_ready"] else "fail"
    proposal_status = "pass" if payload["proposal_quality_ready"] else "fail"
    return "\n".join(
        [
            "# Natural Identity and Membership Proposal v1 Report",
            "",
            f"- Run ID: `{payload['run_id']}`",
            f"- Cases: `{payload['case_count']}`",
            f"- Gate safety: `{gate_status}`",
            f"- Proposal quality: `{proposal_status}`",
            f"- Raw action accuracy: `{metrics['raw_action_accuracy']}`",
            f"- Gated action accuracy: `{metrics['gated_action_accuracy']}`",
            f"- Raw critical false merges: `{metrics['raw_critical_false_merge_count']}`",
            f"- Gated critical false merges: `{metrics['gated_critical_false_merge_count']}`",
            f"- Raw critical false memberships: `{metrics['raw_critical_false_membership_count']}`",
            f"- Gated critical false memberships: `{metrics['gated_critical_false_membership_count']}`",
            f"- Gate interventions: `{metrics['gate_intervention_count']}`",
            f"- Proposal evidence exact rate: `{metrics['proposal_evidence_exact_rate']}`",
            f"- Structural fallback count: `{metrics['structural_fallback_count']}`",
            "",
            "## Interpretation",
            "",
            "The reference proposer is not a model run. It is a deterministic, public-only gate stress test. Gate safety and proposal quality are independent decisions: a safe gate may pass while the proposer fails its quality threshold.",
            "",
            "This diagnostic does not modify the core memory skeleton. It adds no automatic merge path, does not change L1/L2 extraction, question processing, symbolic retrieval, or guarded embedding fallback, and does not establish product or external-system superiority.",
            "",
            "The frozen real LongMemEval result remains `structured_l2_identity_unresolved`; neither lexical overlap nor Extended-AMR edges are factual authority for resolving it.",
            "",
        ]
    )


def run_reference_identity_proposer_file(
    public_path: Path,
    output_path: Path,
    *,
    run_id: str,
) -> dict[str, Any]:
    payload = run_reference_identity_proposer(public_path, run_id=run_id)
    write_json_immutable(output_path, payload)
    return payload


def score_identity_proposals_file(
    root: Path,
    proposals_path: Path,
    output_path: Path,
    report_path: Path,
    *,
    workspace_root: Path | None = None,
) -> dict[str, Any]:
    proposals = json.loads(proposals_path.read_text(encoding="utf-8"))
    payload = score_identity_proposal_payload(
        root,
        proposals,
        workspace_root=workspace_root,
    )
    write_json_immutable(output_path, payload)
    write_text_immutable(report_path, render_identity_proposal_report(payload))
    return payload

