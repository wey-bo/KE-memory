from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from tools.natural_memory_benchmark.identity_proposal import (
    IdentityProposalRecord,
    apply_identity_proposal_gate,
    freeze_natural_identity_slice,
    run_reference_identity_proposer,
    score_identity_proposal_payload,
    validate_natural_identity_slice,
)


SOURCE_CONFIG = Path(
    "artifacts/identity-memory-experiment/natural-v1/source-cases.json"
)
WORKSPACE_ROOT = Path(".")


def _freeze(tmp_path: Path) -> Path:
    output_root = tmp_path / "natural-v1"
    freeze_natural_identity_slice(
        SOURCE_CONFIG,
        output_root,
        workspace_root=WORKSPACE_ROOT,
    )
    return output_root


def test_freeze_separates_public_authority_and_gold_and_is_deterministic(tmp_path):
    root = _freeze(tmp_path)
    first = {
        name: (root / name).read_bytes()
        for name in ("public.json", "authority.json", "gold.json", "manifest.json")
    }
    freeze_natural_identity_slice(
        SOURCE_CONFIG,
        root,
        workspace_root=WORKSPACE_ROOT,
    )
    second = {name: (root / name).read_bytes() for name in first}

    assert first == second
    public = json.loads(first["public.json"])
    authority = json.loads(first["authority.json"])
    gold = json.loads(first["gold.json"])
    manifest = json.loads(first["manifest.json"])

    assert len(public["cases"]) == 12
    assert manifest["case_count"] == 12
    assert manifest["dev_count"] == 6
    assert manifest["hidden_count"] == 6
    assert all("authority" not in case and "gold" not in case for case in public["cases"])
    assert all("expected_action" not in case for case in authority["cases"])
    assert all("shared_trusted_identifiers" not in case for case in gold["items"])


def test_source_validation_rejects_quote_and_actor_tampering(tmp_path):
    payload = json.loads(SOURCE_CONFIG.read_text(encoding="utf-8"))
    payload["cases"][0]["mentions"][0]["quote"] = "not present in the source"
    bad_quote = tmp_path / "bad-quote.json"
    bad_quote.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="quote mismatch"):
        freeze_natural_identity_slice(
            bad_quote,
            tmp_path / "quote-out",
            workspace_root=WORKSPACE_ROOT,
        )

    payload = json.loads(SOURCE_CONFIG.read_text(encoding="utf-8"))
    payload["cases"][0]["mentions"][0]["source_actor_id"] = "person:melanie"
    bad_actor = tmp_path / "bad-actor.json"
    bad_actor.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="actor mismatch"):
        freeze_natural_identity_slice(
            bad_actor,
            tmp_path / "actor-out",
            workspace_root=WORKSPACE_ROOT,
        )


def test_proposal_contract_rejects_wrong_action_family_and_missing_evidence():
    with pytest.raises(ValidationError, match="identity proposal action"):
        IdentityProposalRecord(
            case_id="case-1",
            relation_kind="identity",
            action="include",
            confidence=0.9,
            evidence_mention_ids=["m1"],
            reason_code="bad-family",
            proposer_id="test",
            proposer_version="1",
            run_id="run-1",
        )

    with pytest.raises(ValidationError, match="non-abstain proposal requires evidence"):
        IdentityProposalRecord(
            case_id="case-1",
            relation_kind="identity",
            action="merge",
            confidence=0.9,
            evidence_mention_ids=[],
            reason_code="missing-evidence",
            proposer_id="test",
            proposer_version="1",
            run_id="run-1",
        )


def test_gate_blocks_unsupported_merge_and_subject_mismatch_include(tmp_path):
    root = _freeze(tmp_path)
    public = json.loads((root / "public.json").read_text(encoding="utf-8"))
    authority = json.loads((root / "authority.json").read_text(encoding="utf-8"))
    cases = {item["case_id"]: item for item in public["cases"]}
    rules = {item["case_id"]: item for item in authority["cases"]}

    project_case = cases["NIM-HIDDEN-003-longmemeval-project-identity-unresolved"]
    unsafe_merge = IdentityProposalRecord(
        case_id=project_case["case_id"],
        relation_kind="identity",
        action="merge",
        confidence=0.99,
        evidence_mention_ids=[item["mention_id"] for item in project_case["mentions"]],
        reason_code="lexical-project-overlap",
        proposer_id="test",
        proposer_version="1",
        run_id="run-test",
    )
    blocked_merge = apply_identity_proposal_gate(
        project_case,
        rules[project_case["case_id"]],
        unsafe_merge,
    )
    assert blocked_merge.accepted_action == "abstain"
    assert blocked_merge.gate_reason == "merge_not_authorized"

    mismatch_case = cases["NIM-HIDDEN-005-caroline-self-care-mismatch"]
    unsafe_include = IdentityProposalRecord(
        case_id=mismatch_case["case_id"],
        relation_kind="membership",
        action="include",
        confidence=0.99,
        evidence_mention_ids=[mismatch_case["mentions"][0]["mention_id"]],
        reason_code="topic-overlap",
        proposer_id="test",
        proposer_version="1",
        run_id="run-test",
    )
    blocked_include = apply_identity_proposal_gate(
        mismatch_case,
        rules[mismatch_case["case_id"]],
        unsafe_include,
    )
    assert blocked_include.accepted_action == "abstain"
    assert blocked_include.gate_reason == "membership_subject_mismatch"


def test_reference_proposer_is_public_only_and_deterministic(tmp_path):
    root = _freeze(tmp_path)
    public_path = root / "public.json"
    first = run_reference_identity_proposer(public_path, run_id="run-reference-v1")
    second = run_reference_identity_proposer(public_path, run_id="run-reference-v1")

    assert first == second
    assert first["case_count"] == 12
    assert all(item["run_id"] == "run-reference-v1" for item in first["proposals"])
    assert not (tmp_path / "gold.json").exists()


def test_score_separates_gate_safety_from_proposer_quality(tmp_path):
    root = _freeze(tmp_path)
    proposals = run_reference_identity_proposer(
        root / "public.json",
        run_id="run-reference-score-v1",
    )
    score = score_identity_proposal_payload(
        root,
        proposals,
        workspace_root=WORKSPACE_ROOT,
    )

    assert score["status"] == "pass"
    assert score["gate_safety_ready"] is True
    assert score["proposal_quality_ready"] is False
    assert score["case_count"] == 12
    assert score["metrics"]["gated_action_accuracy"] == 1.0
    assert score["metrics"]["gated_critical_false_merge_count"] == 0
    assert score["metrics"]["gated_critical_false_membership_count"] == 0
    assert score["metrics"]["gated_abstention_correctness"] == 1.0
    assert score["metrics"]["proposal_evidence_exact_rate"] == 1.0
    assert score["metrics"]["gate_intervention_count"] == 2
    assert score["metrics"]["raw_critical_false_merge_count"] == 1
    assert score["regressions"]["v5_hash_preserved"] is True
    assert score["regressions"]["v5_longmemeval_abstention_preserved"] is True


def test_validate_slice_rejects_public_gold_leakage(tmp_path):
    root = _freeze(tmp_path)
    public = json.loads((root / "public.json").read_text(encoding="utf-8"))
    public["cases"][0]["expected_action"] = "merge"
    (root / "public.json").write_text(json.dumps(public), encoding="utf-8")

    with pytest.raises(ValueError, match="public case leaks restricted field"):
        validate_natural_identity_slice(root, workspace_root=WORKSPACE_ROOT)
