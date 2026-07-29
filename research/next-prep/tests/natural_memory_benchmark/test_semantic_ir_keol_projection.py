from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tools.natural_memory_benchmark.semantic_ir import (
    ClosureRecord,
    EvidenceSpan,
    L1MemoryUnit,
    L2MemoryUnit,
    Predicate,
    RoleBinding,
    SourceBinding,
)
from tools.natural_memory_benchmark.semantic_ir_keol_projection import (
    project_semantic_ir_to_keol,
    project_semantic_ir_slice_suite_to_keol,
    project_semantic_ir_slice_suite_to_keol_file,
)


ROOT = Path("artifacts/natural-benchmark-slices")
SLICE_ID = "slice-v1"
RESULTS = ROOT / SLICE_ID / "symbolic-fallback-answerability-v2-fastembed-results.json"


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "tools.natural_memory_benchmark.cli", *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _source(evidence_id: str, text: str = "I led the migration project.") -> SourceBinding:
    return SourceBinding(
        speaker="user",
        source_status="user_reported",
        evidence_spans=[
            EvidenceSpan(
                evidence_id=evidence_id,
                turn_id=f"turn-{evidence_id}",
                session_id="session-1",
                char_start=0,
                char_end=len(text),
                text=text,
            )
        ],
    )


def _l1(unit_id: str, evidence_id: str, *, operator: str = "led_by", rhs: str = "project_alpha") -> L1MemoryUnit:
    return L1MemoryUnit(
        unit_id=unit_id,
        kind="event",
        predicate=Predicate(surface="led", sense="lead/manage", canonical_operator=operator),
        roles=[
            RoleBinding(role="ARG0", entity_id="user", role_name="leader"),
            RoleBinding(role="ARG1", entity_id=rhs, role_name="project"),
        ],
        source=_source(evidence_id),
        lifecycle="active",
    )


def test_l1_projection_preserves_operator_application_evidence_and_metadata():
    unit = _l1("l1-led-project", "E-led")

    projection = project_semantic_ir_to_keol(
        [unit],
        [],
        [],
        workflow_run_id="wf-test",
    )

    assert projection["schema_version"] == "semantic-ir-keol-projection-v2"
    assert len(projection["evidence"]) == 1
    assert projection["evidence"][0]["quote"] == "I led the migration project."
    assert projection["evidence"][0]["metadata"]["semantic_ir_evidence_id"] == "E-led"
    assert [operator["name"] for operator in projection["operators"]] == ["led_by"]
    assert {individual["name"] for individual in projection["individuals"]} >= {"user", "project_alpha"}

    assertion = projection["assertions"][0]
    assert assertion["lhs"]["term_type"] == "operator_application"
    assert assertion["lhs"]["operator_id"] == projection["operators"][0]["id"]
    assert assertion["rhs"]["term_type"] == "individual"
    assert assertion["evidence_ids"] == [projection["evidence"][0]["id"]]
    assert assertion["workflow_run_id"] == "wf-test"
    assert assertion["metadata"]["semantic_ir_unit_id"] == "l1-led-project"
    assert assertion["metadata"]["semantic_ir_level"] == "L1"
    assert assertion["metadata"]["predicate_sense"] == "lead/manage"
    assert assertion["metadata"]["source_status"] == "user_reported"
    assert assertion["metadata"]["lifecycle"] == "active"
    assert assertion["metadata"]["role_bindings"] == [
        {"entity_id": "user", "role": "ARG0", "role_name": "leader"},
        {"entity_id": "project_alpha", "role": "ARG1", "role_name": "project"},
    ]


def test_l2_and_closure_projection_keep_derived_assertion_provenance():
    first = _l1("l1-first", "E1", rhs="project_alpha")
    second = _l1("l1-second", "E2", rhs="project_beta")
    closure = ClosureRecord(
        closure_id="closure-projects",
        claim_or_query_id="query-projects",
        pattern="multi_evidence_set",
        required_units=[
            {"unit_id": "l1-first", "role": "evidence"},
            {"unit_id": "l1-second", "role": "evidence"},
        ],
        complete=True,
        reason="closure complete",
    )
    l2 = L2MemoryUnit(
        unit_id="l2-project-count",
        kind="project",
        abstracts=["l1-first", "l1-second"],
        summary="The user led two projects.",
        assertions=["count(led_projects_by_user)=2"],
        closure_id=closure.closure_id,
        lifecycle="active",
        source_l1_units=["l1-first", "l1-second"],
        source_turns=["turn-E1", "turn-E2"],
        source_sessions=["session-1"],
    )

    projection = project_semantic_ir_to_keol(
        [first, second],
        [l2],
        [closure],
        workflow_run_id="wf-test",
    )

    l1_assertion_ids = [
        assertion["id"]
        for assertion in projection["assertions"]
        if assertion["metadata"].get("semantic_ir_level") == "L1"
    ]
    l2_assertion = next(
        assertion for assertion in projection["assertions"] if assertion["metadata"].get("semantic_ir_level") == "L2"
    )
    closure_assertion = next(
        assertion for assertion in projection["assertions"] if assertion["metadata"].get("semantic_ir_level") == "closure"
    )

    assert set(l2_assertion["derived_from_assertion_ids"]) == set(l1_assertion_ids)
    assert l2_assertion["metadata"]["abstracts"] == ["l1-first", "l1-second"]
    assert l2_assertion["metadata"]["closure_id"] == "closure-projects"
    assert set(closure_assertion["derived_from_assertion_ids"]) == set(l1_assertion_ids)
    assert closure_assertion["metadata"]["required_units"] == [
        {"role": "evidence", "unit_id": "l1-first"},
        {"role": "evidence", "unit_id": "l1-second"},
    ]
    assert closure_assertion["metadata"]["complete"] is True
    assert {evidence["metadata"]["semantic_ir_evidence_id"] for evidence in projection["evidence"]} == {"E1", "E2"}


def test_cli_project_semantic_ir_slice_suite_to_keol_writes_projection(tmp_path):
    output_path = tmp_path / "semantic-ir-keol-projection.json"

    result = _run_cli(
        "project-semantic-ir-slice-to-keol",
        "--root",
        str(ROOT),
        "--slice-id",
        SLICE_ID,
        "--results",
        str(RESULTS),
        "--output",
        str(output_path),
        "--workflow-run-id",
        "wf-semantic-ir-slice-test",
    )

    assert "valid" in result.stdout
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "semantic-ir-keol-projection-v2"
    assert payload["metadata"]["scope"] == (
        "optional adapter contract only; no KEOL baseline mutation; no model extraction"
    )
    assert payload["metadata"]["case_count"] == 5
    assert len(payload["assertions"]) >= 5
    assert all(assertion["workflow_run_id"] == "wf-semantic-ir-slice-test" for assertion in payload["assertions"])


def test_direct_slice_projection_file_helper_writes_immutable_json(tmp_path):
    output_path = tmp_path / "projection.json"

    payload = project_semantic_ir_slice_suite_to_keol_file(
        ROOT,
        SLICE_ID,
        RESULTS,
        output_path,
        workflow_run_id="wf-direct-helper-test",
    )

    assert output_path.exists()
    assert payload["metadata"]["case_count"] == 5
    assert json.loads(output_path.read_text(encoding="utf-8"))["metadata"]["case_count"] == 5


def test_slice_projection_v2_materializes_closure_parity_and_uses_valid_statuses():
    projection = project_semantic_ir_slice_suite_to_keol(
        ROOT,
        SLICE_ID,
        RESULTS,
        workflow_run_id="wf-closure-parity-test",
    )

    closure_assertions = [
        assertion
        for assertion in projection["assertions"]
        if assertion["metadata"].get("semantic_ir_level") == "closure"
    ]
    assert projection["schema_version"] == "semantic-ir-keol-projection-v2"
    assert sum(1 for assertion in closure_assertions if assertion["metadata"]["complete"]) == 4
    assert sum(1 for assertion in closure_assertions if not assertion["metadata"]["complete"]) == 1
    assert {assertion["status"] for assertion in projection["assertions"]} <= {
        "active",
        "deprecated",
        "rejected",
    }
