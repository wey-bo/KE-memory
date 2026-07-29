from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from tools.ontology_memory_experiment.io import (
    load_distractor_document,
    load_gold_document,
    load_oracle_query_plan_document,
    load_oracle_representation_document,
    load_source_document,
    sha256_file,
    validate_document_links,
    write_json_immutable,
    write_manifest,
)
from tools.ontology_memory_experiment.models import (
    ArmResult,
    GoldScenario,
    MemoryRecord,
    QueryPlan,
    SourceScenario,
    SourceTurn,
)


def source_scenario() -> SourceScenario:
    return SourceScenario(
        scenario_id="OME-S001",
        language="en",
        turns=[
            SourceTurn(turn_id=f"OME-S001-T0{index}", speaker="user", text=f"English turn {index}.")
            for index in range(1, 5)
        ],
        question="Which record is current?",
        candidate_answer_budget=32,
    )


def test_source_scenario_requires_stable_id_and_four_to_eight_turns() -> None:
    scenario = source_scenario()
    assert scenario.scenario_id == "OME-S001"
    assert len(scenario.turns) == 4

    with pytest.raises(ValidationError):
        SourceScenario(
            scenario_id="bad",
            language="en",
            turns=[SourceTurn(turn_id="OME-S001-T01", speaker="user", text="Only one.")],
            question="Question?",
            candidate_answer_budget=32,
        )


def test_gold_requires_evidence_hard_negatives_and_exclusive_answer() -> None:
    gold = GoldScenario(
        scenario_id="OME-S001",
        family="roles_polarity_modality_quantity",
        origin="architecture_directed",
        primary_system="mem0",
        split="dev",
        competency="agent_role",
        answer={"kind": "value", "values": ["Avery"]},
        required_evidence_turn_ids=["OME-S001-T03"],
        hard_negative_turn_ids=["OME-S001-T01", "OME-S001-T02"],
        required_primitives=["role"],
        ablation_primitive="role",
        critical_constraints=["role_binding"],
        architecture_claim_ids=["CLAIM-MEM0-001"],
        proposed_ontology_remedy="typed roles",
        falsifier="Role ablation matches sufficient execution.",
    )
    assert gold.answer.kind == "value"

    with pytest.raises(ValidationError):
        GoldScenario(
            **gold.model_dump(exclude={"answer"}),
            answer={"kind": "unanswerable", "values": ["Avery"]},
        )


def test_representation_and_result_contracts_reject_unknown_fields() -> None:
    record = MemoryRecord(record_id="OME-S001-R01", source_turn_ids=["OME-S001-T01"], surface_text="Avery approved it.")
    plan = QueryPlan(required_answer_slot="status", declared_unresolved_slots=[])
    assert record.source_turn_ids == ["OME-S001-T01"]
    assert plan.required_answer_slot == "status"

    with pytest.raises(ValidationError):
        ArmResult(
            run_id="run-1",
            track="oracle",
            arm="O+",
            scenario_id="OME-S001",
            distractor_scale=0,
            selected_evidence_turn_ids=[],
            predicted_answer=None,
            status="ok",
            hidden_answer="forbidden",
        )


@pytest.mark.parametrize(
    ("required_answer_slot", "bound_field"),
    [
        ("quantity", {"quantity": "7"}),
        ("polarity", {"polarity": "negative"}),
        ("sense", {"role_constraints": {"sense": "account record"}}),
    ],
)
def test_query_plan_rejects_filters_that_bind_the_unknown_answer(
    required_answer_slot: str,
    bound_field: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        QueryPlan(required_answer_slot=required_answer_slot, **bound_field)


def test_query_plan_requires_a_variable_binding_for_a_traversal_answer() -> None:
    with pytest.raises(ValidationError):
        QueryPlan(
            required_answer_slot="project",
            traversal_steps=[
                {"source": "archive", "predicate": "resolves_to", "target": "project-03"},
            ],
        )

    plan = QueryPlan(
        required_answer_slot="project",
        traversal_steps=[
            {"source": "archive", "predicate": "resolves_to", "target_slot": "project"},
        ],
    )

    assert plan.traversal_steps[0].target_slot == "project"


def test_immutable_json_replay_and_manifest_hash_binding(tmp_path: Path) -> None:
    artifact = tmp_path / "source.json"
    write_json_immutable(artifact, {"schema_version": "v1", "items": ["x"]})
    first_hash = sha256_file(artifact)
    write_json_immutable(artifact, {"items": ["x"], "schema_version": "v1"})
    assert sha256_file(artifact) == first_hash

    with pytest.raises(FileExistsError):
        write_json_immutable(artifact, {"schema_version": "v1", "items": ["changed"]})

    manifest = write_manifest(tmp_path / "manifest.json", {"source": artifact})
    assert manifest["files"]["source"]["sha256"] == first_hash


def test_loaders_validate_separate_documents_and_source_evidence_links(tmp_path: Path) -> None:
    source_path = tmp_path / "source.json"
    gold_path = tmp_path / "gold.json"
    distractor_path = tmp_path / "distractors.json"
    write_json_immutable(source_path, {"schema_version": "ontology-memory-source-v1", "scenarios": [source_scenario().model_dump()]})
    write_json_immutable(gold_path, {"schema_version": "ontology-memory-gold-v1", "status": "frozen", "scenarios": [
        {"scenario_id": "OME-S001", "family": "roles_polarity_modality_quantity", "origin": "neutral", "primary_system": None,
             "split": "dev", "answer": {"kind": "value", "values": ["Avery"]}, "required_evidence_turn_ids": ["OME-S001-T03"],
             "hard_negative_turn_ids": ["OME-S001-T01", "OME-S001-T02"], "required_primitives": ["role"],
             "competency": "agent_role", "ablation_primitive": "role",
         "critical_constraints": ["role_binding"], "architecture_claim_ids": ["CLAIM-NEUTRAL-001"],
         "proposed_ontology_remedy": "typed roles", "falsifier": "Ablation matches execution."}
    ]})
    write_json_immutable(distractor_path, {"schema_version": "ontology-memory-distractors-v1", "records": []})

    source = load_source_document(source_path)
    gold = load_gold_document(gold_path)
    distractors = load_distractor_document(distractor_path)
    validate_document_links(source, gold, distractors)


def test_oracle_fixture_contract_is_source_hash_bound_and_gold_blind(tmp_path: Path) -> None:
    source_path = tmp_path / "source.json"
    oracle_records_path = tmp_path / "oracle-records.json"
    oracle_plans_path = tmp_path / "oracle-plans.json"
    write_json_immutable(source_path, {"schema_version": "ontology-memory-source-v1", "scenarios": [source_scenario().model_dump()]})
    source_hash = sha256_file(source_path)
    write_json_immutable(oracle_records_path, {
        "schema_version": "ontology-memory-oracle-representations-v1", "source_sha256": source_hash,
        "scenarios": [{"scenario_id": "OME-S001", "records": [{"record_id": "OME-S001-R01", "source_turn_ids": ["OME-S001-T01"], "surface_text": "Avery approved it."}],
                       "ablated_records": [{"record_id": "OME-S001-R01", "source_turn_ids": ["OME-S001-T01"], "surface_text": "Avery approved it."}]}],
    })
    write_json_immutable(oracle_plans_path, {
        "schema_version": "ontology-memory-oracle-query-plans-v1", "source_sha256": source_hash,
        "scenarios": [{"scenario_id": "OME-S001", "query_plan": {"required_answer_slot": "status", "declared_unresolved_slots": []}}],
    })
    records = load_oracle_representation_document(oracle_records_path)
    plans = load_oracle_query_plan_document(oracle_plans_path)
    assert records.source_sha256 == plans.source_sha256 == source_hash
    forbidden = {"answer", "required_evidence_turn_ids", "hard_negative_turn_ids", "family", "split", "primary_system", "ablation_primitive"}
    assert not (set(records.scenarios[0].model_dump()) & forbidden)
