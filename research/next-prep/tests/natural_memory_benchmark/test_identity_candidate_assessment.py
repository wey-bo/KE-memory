from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

from tools.natural_memory_benchmark.identity_candidate_assessment import (
    assess_identity_candidate_generation,
    render_identity_candidate_assessment_report,
    run_identity_candidate_assessment_file,
)
from tools.natural_memory_benchmark import identity_candidate_assessment as assessment_module
from tools.natural_memory_benchmark.identity_resolution import (
    build_identity_scenario_bundle,
)
from tools.natural_memory_benchmark.io import canonical_json_bytes, sha256_file


EXPERIMENT_ROOT = Path("artifacts/identity-memory-experiment")
FRESH_ROOT = EXPERIMENT_ROOT / "natural-v4-fresh"
RUN_ROOT = (
    FRESH_ROOT
    / "model-runs"
    / "run-20260728T031000Z-claude-sonnet-4-6-fresh-policy-v4-1"
)
PUBLIC_PATH = FRESH_ROOT / "public.json"
PROPOSALS_PATH = RUN_ROOT / "proposals.json"
SCORE_PATH = RUN_ROOT / "score.json"
GUARD_SCENARIO_ID = "ID-DEV-001-alias-shared-identifier"


def _guard_bundle():
    return build_identity_scenario_bundle(EXPERIMENT_ROOT, GUARD_SCENARIO_ID)


def _write_read_only_json(path: Path, payload: dict) -> None:
    path.write_bytes(canonical_json_bytes(payload))
    path.chmod(0o444)


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "tools.natural_memory_benchmark.cli", *args],
        check=True,
        capture_output=True,
        text=True,
    )


def test_candidate_queue_preserves_gate_separation_and_blocks_all_writes():
    queue, assessment = assess_identity_candidate_generation(
        PUBLIC_PATH,
        PROPOSALS_PATH,
        SCORE_PATH,
        guard_bundle=_guard_bundle(),
        guard_scenario_id=GUARD_SCENARIO_ID,
    )

    assert queue["schema_version"] == "identity-candidate-review-queue-v3"
    assert queue["case_count"] == 6
    assert Counter(item["disposition"] for item in queue["candidates"]) == {
        "eligible_for_manual_review": 4,
        "gate_abstained": 2,
    }
    assert len({item["candidate_id"] for item in queue["candidates"]}) == 6
    assert all(item["candidate_id"].startswith("identity-candidate-") for item in queue["candidates"])
    assert all(item["automatic_write_claims"] == {
        "aggregate": False,
        "closure": False,
        "identity_decision": False,
        "merge": False,
        "membership": False,
        "l2": False,
        "snapshot": False,
    } for item in queue["candidates"])

    assert assessment["status"] == "pass"
    assert assessment["raw_proposer_quality_ready"] is True
    assert assessment["deterministic_gate_safety_ready"] is True
    assert assessment["candidate_generation_integration_ready"] is False
    assert assessment["metrics"]["automatic_authoritative_write_count"] == 0
    assert assessment["metrics"]["blocked_authoritative_write_count"] == 4
    assert assessment["metrics"]["case_mapping_rate"] == 1.0
    assert assessment["metrics"]["mention_mapping_rate"] == 1.0
    assert assessment["state_guard"]["unchanged"] is True
    assert assessment["state_guard"]["before_fingerprint"] == assessment["state_guard"][
        "after_fingerprint"
    ]
    assert assessment["state_guard"]["before_counts"] == assessment["state_guard"][
        "after_counts"
    ]
    assert assessment["claim_boundary"] == {
        "automatic_aggregate_write_authorized": False,
        "automatic_closure_write_authorized": False,
        "automatic_identity_decision_write_authorized": False,
        "automatic_merge_write_authorized": False,
        "automatic_membership_write_authorized": False,
        "automatic_l2_write_authorized": False,
        "automatic_snapshot_write_authorized": False,
        "embedding_authority": False,
        "queue_authoritative": False,
        "longmemeval_status": "structured_l2_identity_unresolved",
    }


def test_assessment_rejects_failed_upstream_quality_gate(tmp_path):
    score = json.loads(SCORE_PATH.read_text(encoding="utf-8"))
    score["proposal_quality_ready"] = False
    score["status"] = "fail"
    changed_score = tmp_path / "score.json"
    _write_read_only_json(changed_score, score)

    with pytest.raises(ValueError, match="upstream proposal quality gate did not pass"):
        assess_identity_candidate_generation(
            PUBLIC_PATH,
            PROPOSALS_PATH,
            changed_score,
            guard_bundle=_guard_bundle(),
            guard_scenario_id=GUARD_SCENARIO_ID,
        )


def test_assessment_rejects_score_input_hash_mismatch(tmp_path):
    score = json.loads(SCORE_PATH.read_text(encoding="utf-8"))
    score["input_sha256"]["public"] = "0" * 64
    changed_score = tmp_path / "score.json"
    _write_read_only_json(changed_score, score)

    with pytest.raises(ValueError, match="score public input hash mismatch"):
        assess_identity_candidate_generation(
            PUBLIC_PATH,
            PROPOSALS_PATH,
            changed_score,
            guard_bundle=_guard_bundle(),
            guard_scenario_id=GUARD_SCENARIO_ID,
        )


def test_assessment_rejects_duplicate_public_case_ids(tmp_path):
    public = json.loads(PUBLIC_PATH.read_text(encoding="utf-8"))
    public["cases"].append(public["cases"][0])
    changed_public = tmp_path / "public.json"
    _write_read_only_json(changed_public, public)
    score = json.loads(SCORE_PATH.read_text(encoding="utf-8"))
    score["input_sha256"]["public"] = sha256_file(changed_public)
    changed_score = tmp_path / "score.json"
    _write_read_only_json(changed_score, score)

    with pytest.raises(ValueError, match="duplicate public case id"):
        assess_identity_candidate_generation(
            changed_public,
            PROPOSALS_PATH,
            changed_score,
            guard_bundle=_guard_bundle(),
            guard_scenario_id=GUARD_SCENARIO_ID,
        )


def test_assessment_rejects_duplicate_public_mention_ids(tmp_path):
    public = json.loads(PUBLIC_PATH.read_text(encoding="utf-8"))
    public["cases"][0]["mentions"].append(public["cases"][0]["mentions"][0])
    changed_public = tmp_path / "public.json"
    _write_read_only_json(changed_public, public)
    score = json.loads(SCORE_PATH.read_text(encoding="utf-8"))
    score["input_sha256"]["public"] = sha256_file(changed_public)
    changed_score = tmp_path / "score.json"
    _write_read_only_json(changed_score, score)

    with pytest.raises(ValueError, match="duplicate public mention id"):
        assess_identity_candidate_generation(
            changed_public,
            PROPOSALS_PATH,
            changed_score,
            guard_bundle=_guard_bundle(),
            guard_scenario_id=GUARD_SCENARIO_ID,
        )


def test_assessment_rejects_score_readiness_metric_contradiction(tmp_path):
    score = json.loads(SCORE_PATH.read_text(encoding="utf-8"))
    score["metrics"]["raw_action_accuracy"] = 0.0
    changed_score = tmp_path / "score.json"
    _write_read_only_json(changed_score, score)

    with pytest.raises(ValueError, match="score proposal quality metrics contradict readiness"):
        assess_identity_candidate_generation(
            PUBLIC_PATH,
            PROPOSALS_PATH,
            changed_score,
            guard_bundle=_guard_bundle(),
            guard_scenario_id=GUARD_SCENARIO_ID,
        )


def test_assessment_rejects_failed_score_validation_boundary(tmp_path):
    score = json.loads(SCORE_PATH.read_text(encoding="utf-8"))
    score["validation"]["source_validation_valid"] = False
    changed_score = tmp_path / "score.json"
    _write_read_only_json(changed_score, score)

    with pytest.raises(ValueError, match="score validation boundary did not pass"):
        assess_identity_candidate_generation(
            PUBLIC_PATH,
            PROPOSALS_PATH,
            changed_score,
            guard_bundle=_guard_bundle(),
            guard_scenario_id=GUARD_SCENARIO_ID,
        )


def test_assessment_rejects_cross_family_gated_action(tmp_path):
    score = json.loads(SCORE_PATH.read_text(encoding="utf-8"))
    score["gated_decisions"][0]["accepted_action"] = "include"
    changed_score = tmp_path / "score.json"
    _write_read_only_json(changed_score, score)

    with pytest.raises(ValueError, match="gated accepted action mismatch"):
        assess_identity_candidate_generation(
            PUBLIC_PATH,
            PROPOSALS_PATH,
            changed_score,
            guard_bundle=_guard_bundle(),
            guard_scenario_id=GUARD_SCENARIO_ID,
        )


def test_assessment_rejects_non_exact_gated_evidence(tmp_path):
    score = json.loads(SCORE_PATH.read_text(encoding="utf-8"))
    score["gated_decisions"][0]["required_evidence_exact"] = False
    changed_score = tmp_path / "score.json"
    _write_read_only_json(changed_score, score)

    with pytest.raises(ValueError, match="gated evidence is not exact"):
        assess_identity_candidate_generation(
            PUBLIC_PATH,
            PROPOSALS_PATH,
            changed_score,
            guard_bundle=_guard_bundle(),
            guard_scenario_id=GUARD_SCENARIO_ID,
        )


def test_state_guard_and_compatibility_report_all_authoritative_gaps():
    guard_bundle = _guard_bundle()
    before = guard_bundle.model_dump(mode="json")

    queue, assessment = assess_identity_candidate_generation(
        PUBLIC_PATH,
        PROPOSALS_PATH,
        SCORE_PATH,
        guard_bundle=guard_bundle,
        guard_scenario_id=GUARD_SCENARIO_ID,
    )

    assert guard_bundle.model_dump(mode="json") == before
    assert set(assessment["state_guard"]["before_counts"]) == {
        "entity_record_count",
        "identity_decision_count",
        "identity_closure_count",
        "identity_snapshot_count",
        "aggregate_claim_count",
        "membership_write_count",
        "l2_unit_count",
    }
    assert assessment["state_guard"]["before_counts"]["membership_write_count"] == 0
    assert assessment["metrics"]["existing_entity_binding_rate"] == 0.0
    assert assessment["metrics"]["l1_evidence_binding_rate"] == 0.0
    assert assessment["metrics"]["source_revision_binding_rate"] == 0.0
    assert assessment["metrics"]["authoritative_materialization_ready_count"] == 0

    non_abstain = [item for item in queue["candidates"] if item["gated_action"] != "abstain"]
    assert len(non_abstain) == 4
    for candidate in non_abstain:
        assert candidate["compatibility"]["authoritative_materialization_allowed"] is False
        assert "missing_existing_entity_bindings" in candidate["compatibility"]["gaps"]
        assert "missing_l1_evidence_bindings" in candidate["compatibility"]["gaps"]
        assert "missing_source_revision_bindings" in candidate["compatibility"]["gaps"]
        expected_terminal_gap = (
            "identity_evidence_closure_required"
            if candidate["relation_kind"] == "identity"
            else "membership_write_surface_unauthorized"
        )
        assert expected_terminal_gap in candidate["compatibility"]["gaps"]


def test_entity_binding_counts_subject_refs_without_treating_membership_actor_as_member():
    guard = _guard_bundle()
    template = guard.entity_records[0]
    guard = guard.model_copy(
        update={
            "entity_records": [
                *guard.entity_records,
                template.model_copy(update={"entity_id": "person:joanna"}),
                template.model_copy(update={"entity_id": "person:nate"}),
            ]
        }
    )

    queue, assessment = assess_identity_candidate_generation(
        PUBLIC_PATH,
        PROPOSALS_PATH,
        SCORE_PATH,
        guard_bundle=guard,
        guard_scenario_id=GUARD_SCENARIO_ID,
    )
    by_action = {item["gated_action"]: item for item in queue["candidates"]}

    merged = by_action["merge"]["compatibility"]
    assert merged["subject_ref_count"] == 2
    assert merged["bound_subject_ref_count"] == 2
    assert merged["existing_entity_record_ids"] == ["person:joanna"]

    included = by_action["include"]["compatibility"]
    assert included["subject_ref_count"] == 2
    assert included["bound_subject_ref_count"] == 1
    assert included["existing_entity_record_ids"] == ["person:nate"]
    assert assessment["metrics"]["existing_entity_binding_rate"] == 0.5


def test_evidence_chain_requires_l1_span_to_reference_unique_source_revision():
    public = json.loads(PUBLIC_PATH.read_text(encoding="utf-8"))
    mention = public["cases"][0]["mentions"][0]
    guard = _guard_bundle()
    source = guard.source_record_revisions[0].model_copy(
        update={"source_ref": mention["source_ref"]}
    )
    unit = guard.l1_units[0]
    span = unit.source.evidence_spans[0].model_copy(
        update={"source_revision_id": source.source_revision_id}
    )
    unit = unit.model_copy(
        update={
            "unit_id": mention["evidence_unit_id"],
            "source": unit.source.model_copy(update={"evidence_spans": [span]}),
        }
    )
    guard = guard.model_copy(
        update={"source_record_revisions": [source], "l1_units": [unit]}
    )

    queue, assessment = assess_identity_candidate_generation(
        PUBLIC_PATH,
        PROPOSALS_PATH,
        SCORE_PATH,
        guard_bundle=guard,
        guard_scenario_id=GUARD_SCENARIO_ID,
    )
    merged = next(
        item for item in queue["candidates"] if item["gated_action"] == "merge"
    )["compatibility"]
    assert merged["bound_l1_evidence_ref_count"] == 1
    assert merged["bound_source_revision_ref_count"] == 1
    assert merged["bound_evidence_chain_ref_count"] == 1
    assert assessment["metrics"]["evidence_chain_binding_rate"] == pytest.approx(1 / 9)

    ambiguous_source = source.model_copy(
        update={"source_revision_id": f"{source.source_revision_id}-ambiguous"}
    )
    ambiguous_guard = guard.model_copy(
        update={"source_record_revisions": [source, ambiguous_source]}
    )
    ambiguous_queue, _ = assess_identity_candidate_generation(
        PUBLIC_PATH,
        PROPOSALS_PATH,
        SCORE_PATH,
        guard_bundle=ambiguous_guard,
        guard_scenario_id=GUARD_SCENARIO_ID,
    )
    ambiguous = next(
        item
        for item in ambiguous_queue["candidates"]
        if item["gated_action"] == "merge"
    )["compatibility"]
    assert ambiguous["bound_source_revision_ref_count"] == 0
    assert ambiguous["bound_evidence_chain_ref_count"] == 0
    assert "ambiguous_source_revision_bindings" in ambiguous["gaps"]


def test_assessment_fails_closed_if_candidate_mapping_mutates_guard_bundle(monkeypatch):
    original = assessment_module._candidate_envelope

    def mutating_candidate_envelope(case, proposal, gated, guard_bundle):
        candidate = original(case, proposal, gated, guard_bundle)
        guard_bundle.l2_units.clear()
        return candidate

    monkeypatch.setattr(
        assessment_module,
        "_candidate_envelope",
        mutating_candidate_envelope,
    )

    with pytest.raises(ValueError, match="authoritative state mutation detected"):
        assess_identity_candidate_generation(
            PUBLIC_PATH,
            PROPOSALS_PATH,
            SCORE_PATH,
            guard_bundle=_guard_bundle(),
            guard_scenario_id=GUARD_SCENARIO_ID,
        )


def test_file_runner_is_immutable_read_only_and_reports_claim_boundaries(tmp_path):
    queue_path = tmp_path / "candidate-review-queue.json"
    assessment_path = tmp_path / "assessment.json"
    report_path = tmp_path / "report.md"

    first = run_identity_candidate_assessment_file(
        PUBLIC_PATH,
        PROPOSALS_PATH,
        SCORE_PATH,
        EXPERIMENT_ROOT,
        GUARD_SCENARIO_ID,
        queue_path,
        assessment_path,
        report_path,
    )
    second = run_identity_candidate_assessment_file(
        PUBLIC_PATH,
        PROPOSALS_PATH,
        SCORE_PATH,
        EXPERIMENT_ROOT,
        GUARD_SCENARIO_ID,
        queue_path,
        assessment_path,
        report_path,
    )

    assert first == second
    assert first["queue_sha256"] == sha256_file(queue_path)
    assert all(
        path.stat().st_mode & 0o777 == 0o444
        for path in (queue_path, assessment_path, report_path)
    )
    report = report_path.read_text(encoding="utf-8")
    assert report == render_identity_candidate_assessment_report(first)
    assert "Raw proposer quality: `pass`" in report
    assert "Deterministic gate safety: `pass`" in report
    assert "Candidate-generation integration ready: `false`" in report
    assert "Automatic authoritative writes: `0`" in report
    assert "Mutation guard: `unchanged`" in report
    assert "structured_l2_identity_unresolved" in report

    queue_path.chmod(0o644)
    queue_path.write_text("tampered\n", encoding="utf-8")
    queue_path.chmod(0o444)
    with pytest.raises(FileExistsError, match="immutable artifact differs"):
        run_identity_candidate_assessment_file(
            PUBLIC_PATH,
            PROPOSALS_PATH,
            SCORE_PATH,
            EXPERIMENT_ROOT,
            GUARD_SCENARIO_ID,
            queue_path,
            assessment_path,
            report_path,
        )


def test_file_runner_freezes_earlier_output_if_later_write_fails(tmp_path):
    queue_path = tmp_path / "candidate-review-queue.json"
    assessment_path = tmp_path / "assessment.json"
    report_path = tmp_path / "report.md"
    assessment_path.write_text("conflict\n", encoding="utf-8")
    assessment_path.chmod(0o444)

    with pytest.raises(FileExistsError, match="immutable artifact differs"):
        run_identity_candidate_assessment_file(
            PUBLIC_PATH,
            PROPOSALS_PATH,
            SCORE_PATH,
            EXPERIMENT_ROOT,
            GUARD_SCENARIO_ID,
            queue_path,
            assessment_path,
            report_path,
        )

    assert queue_path.stat().st_mode & 0o777 == 0o444


def test_cli_runs_candidate_generation_assessment(tmp_path):
    queue_path = tmp_path / "candidate-review-queue.json"
    assessment_path = tmp_path / "assessment.json"
    report_path = tmp_path / "report.md"

    result = _run_cli(
        "assess-identity-candidate-generation",
        "--public",
        str(PUBLIC_PATH),
        "--proposals",
        str(PROPOSALS_PATH),
        "--score",
        str(SCORE_PATH),
        "--experiment-root",
        str(EXPERIMENT_ROOT),
        "--guard-scenario-id",
        GUARD_SCENARIO_ID,
        "--queue",
        str(queue_path),
        "--output",
        str(assessment_path),
        "--report",
        str(report_path),
    )

    stdout = json.loads(result.stdout)
    assert stdout == {
        "automatic_authoritative_write_count": 0,
        "candidate_generation_integration_ready": False,
        "case_count": 6,
        "deterministic_gate_safety_ready": True,
        "raw_proposer_quality_ready": True,
        "status": "pass",
    }
    assert assessment_path.is_file()
    assert queue_path.is_file()
    assert report_path.is_file()
