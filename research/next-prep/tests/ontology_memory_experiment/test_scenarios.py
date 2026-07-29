from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from tools.ontology_memory_experiment.scenarios import (
    ablation_field,
    distractor_marker,
    generate_experiment_documents,
    generate_v3_experiment_documents,
    generate_v4_experiment_documents,
    generate_v5_experiment_documents,
    project_oracle_answer,
)
from tools.ontology_memory_experiment.executors import execute_arm
from tools.ontology_memory_experiment.query import compile_query
from tools.ontology_memory_experiment.representations import build_representations


class _UnusedEncoder:
    model_metadata = {"provider": "test", "model_id": "unused", "dimension": 0}

    def encode(self, texts):
        raise AssertionError("O+ oracle execution must not call the dense encoder")


class _FallbackProbeEncoder:
    model_metadata = {"provider": "test", "model_id": "fallback-probe", "dimension": 2}

    def encode(self, texts):
        return [[1.0, 0.0] if "project-91" in text or "which project" in text.lower() else [0.0, 1.0] for text in texts]


class _DistractorBiasedProbeEncoder:
    model_metadata = {"provider": "test", "model_id": "distractor-biased-fallback", "dimension": 2}

    def encode(self, texts):
        return [[1.0, 0.0] if "project-97" in text or "which project" in text.lower() else [0.9, 0.1] for text in texts]


FORBIDDEN_PUBLIC_FIELDS = {"family", "split", "primary_system", "answer", "required_primitives", "gold"}


def canonical_hash(value: object) -> str:
    return hashlib.sha256((json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()).hexdigest()


def test_generator_produces_frozen_60_scenario_distribution() -> None:
    source, gold, distractors = generate_experiment_documents()
    scenarios = source["scenarios"]
    gold_scenarios = gold["scenarios"]

    assert len(scenarios) == len(gold_scenarios) == 60
    assert len({item["scenario_id"] for item in scenarios}) == 60
    assert Counter(item["family"] for item in gold_scenarios) == {
        "roles_polarity_modality_quantity": 15,
        "temporal_updates_conflicts_provenance": 15,
        "conjunction_exact_set_multihop": 15,
        "synonymy_sense_external_unanswerable": 15,
    }
    assert Counter(item["origin"] for item in gold_scenarios) == {"architecture_directed": 40, "neutral": 20}
    assert Counter(item["primary_system"] for item in gold_scenarios if item["primary_system"]) == {
        "mem0": 10,
        "graphiti": 10,
        "hindsight": 10,
        "mempalace": 10,
    }
    assert Counter(item["split"] for item in gold_scenarios) == {"dev": 12, "hidden": 48}
    assert Counter(item["family"] for item in gold_scenarios if item["split"] == "dev") == {
        "roles_polarity_modality_quantity": 3,
        "temporal_updates_conflicts_provenance": 3,
        "conjunction_exact_set_multihop": 3,
        "synonymy_sense_external_unanswerable": 3,
    }
    assert len(distractors["records"]) == 33_000


def test_each_scenario_has_closed_evidence_and_hard_negative_contract() -> None:
    source, gold, _ = generate_experiment_documents()
    source_by_id = {item["scenario_id"]: item for item in source["scenarios"]}
    for item in gold["scenarios"]:
        turns = source_by_id[item["scenario_id"]]["turns"]
        turn_ids = {turn["turn_id"] for turn in turns}
        assert 4 <= len(turns) <= 8
        assert item["required_evidence_turn_ids"] and set(item["required_evidence_turn_ids"]) <= turn_ids
        assert 2 <= len(item["hard_negative_turn_ids"]) <= 4
        assert set(item["hard_negative_turn_ids"]) <= turn_ids
        assert item["required_primitives"]
        assert item["proposed_ontology_remedy"]
        assert item["falsifier"]
        answer = item["answer"]
        assert (answer["kind"] == "unanswerable") == (answer["values"] == [])


def test_source_and_distractors_are_gold_blind_and_deterministic() -> None:
    first = generate_experiment_documents()
    second = generate_experiment_documents()
    assert [canonical_hash(value) for value in first] == [canonical_hash(value) for value in second]

    source, _, distractors = first
    for scenario in source["scenarios"]:
        assert not (set(scenario) & FORBIDDEN_PUBLIC_FIELDS)
    for record in distractors["records"]:
        assert not (set(record) & FORBIDDEN_PUBLIC_FIELDS)
    assert Counter(record["distractor_scale"] for record in distractors["records"]) == {50: 3_000, 500: 30_000}


def test_gold_evidence_is_complete_and_disjoint_from_structural_hard_negatives() -> None:
    source, gold, _, oracle_records, _ = generate_experiment_documents(include_oracle=True)
    turns_by_scenario = {
        scenario["scenario_id"]: {turn["turn_id"]: turn["text"] for turn in scenario["turns"]}
        for scenario in source["scenarios"]
    }
    expected_evidence_offsets = {
        "roles_polarity_modality_quantity": {4},
        "temporal_updates_conflicts_provenance": {2, 3, 4},
        "conjunction_exact_set_multihop": {1, 3, 4},
        "synonymy_sense_external_unanswerable": {1, 2, 3, 4},
    }
    records_by_scenario = {
        fixture["scenario_id"]: {record["source_turn_ids"][0]: record for record in fixture["records"]}
        for fixture in oracle_records["scenarios"]
    }
    for scenario in gold["scenarios"]:
        evidence = set(scenario["required_evidence_turn_ids"])
        negatives = set(scenario["hard_negative_turn_ids"])
        assert evidence.isdisjoint(negatives)
        offsets = {int(turn_id[-2:]) for turn_id in evidence}
        assert offsets == expected_evidence_offsets[scenario["family"]]
        texts = turns_by_scenario[scenario["scenario_id"]]
        assert all("wrong alternative" not in texts[turn_id].lower() for turn_id in negatives)
        assert all(texts[turn_id].strip() for turn_id in negatives)
        assert all(
            records_by_scenario[scenario["scenario_id"]][turn_id]["lifecycle_status"] in {"obsolete", "rejected"}
            for turn_id in negatives
        )
        assert all(
            records_by_scenario[scenario["scenario_id"]][turn_id]["lifecycle_status"] not in {"obsolete", "rejected"}
            for turn_id in evidence
        )


def test_competencies_cover_each_family_and_use_reusable_audit_claim_ids() -> None:
    _, gold, _ = generate_experiment_documents()
    by_family: dict[str, list[dict[str, object]]] = {}
    for scenario in gold["scenarios"]:
        by_family.setdefault(scenario["family"], []).append(scenario)
        assert scenario["ablation_primitive"] in scenario["required_primitives"]
    for family, scenarios in by_family.items():
        assert len({scenario["competency"] for scenario in scenarios}) == 15, family
    assert {claim_id for scenario in gold["scenarios"] for claim_id in scenario["architecture_claim_ids"]} <= {
        "CLAIM-MEM0-001",
        "CLAIM-GRAPHITI-001",
        "CLAIM-HINDSIGHT-001",
        "CLAIM-MEMPALACE-001",
        "RISK-MEM0-001",
        "RISK-GRAPHITI-001",
        "RISK-HINDSIGHT-001",
        "RISK-MEMPALACE-001",
        "CLASS-ABLATION-001",
    }


def test_distractors_change_multiple_structural_dimensions_per_competency() -> None:
    _, gold, distractors = generate_experiment_documents()
    primitive_by_scenario = {scenario["scenario_id"]: scenario["ablation_primitive"] for scenario in gold["scenarios"]}
    samples: dict[str, set[str]] = {}
    for record in distractors["records"]:
        if record["distractor_scale"] == 50:
            samples.setdefault(record["scenario_id"], set()).add(record["text"].split(";", 1)[0])
    assert all(len(variants) >= 3 for variants in samples.values())
    for scenario_id, primitive in primitive_by_scenario.items():
        marker = distractor_marker(primitive)
        assert marker
        assert all(marker not in text.lower() for text in samples[scenario_id])
        assert all("wrong alternative" not in text.lower() for text in samples[scenario_id])


def test_required_evidence_fits_a_computed_shared_candidate_budget() -> None:
    source, gold, _ = generate_experiment_documents()
    budgets = {scenario["candidate_answer_budget"] for scenario in source["scenarios"]}
    assert len(budgets) == 1
    budget = next(iter(budgets))
    required_costs = []
    source_by_id = {scenario["scenario_id"]: scenario for scenario in source["scenarios"]}
    for expected in gold["scenarios"]:
        scenario = source_by_id[expected["scenario_id"]]
        text_by_id = {turn["turn_id"]: turn["text"] for turn in scenario["turns"]}
        cost = sum(len(text_by_id[turn_id].split()) for turn_id in expected["required_evidence_turn_ids"])
        required_costs.append(cost)
        assert cost <= budget
    assert budget == max(required_costs)
    assert budget > 32


def test_source_templates_are_gold_blind_and_hidden_wording_is_held_out_by_family() -> None:
    source, gold, _ = generate_experiment_documents()
    gold_by_id = {scenario["scenario_id"]: scenario for scenario in gold["scenarios"]}
    forbidden_text = {
        "required_evidence_turn_ids", "hard_negative_turn_ids", "required_primitives",
        "ablation_primitive", "architecture_claim_ids", "primary_system", "mem0", "graphiti",
        "hindsight", "mempalace", "wrong alternative", "OME-S",
    }
    for scenario in source["scenarios"]:
        public_text = " ".join([scenario["question"], *(turn["text"] for turn in scenario["turns"])])
        lowered = public_text.lower()
        assert not re.search(r"\banswer\b", lowered)
        assert not any(token in lowered for token in forbidden_text)

    def normalize_template(text: str, scenario: dict[str, object]) -> str:
        replacements = {
            "Avery": "PERSON", "Blair": "PERSON", "Casey": "PERSON", "Devon": "PERSON",
            "Emery": "PERSON", "Flynn": "PERSON", "Gray": "PERSON", "Harper": "PERSON",
            "archive": "OBJECT", "invoice": "OBJECT", "permit": "OBJECT", "tablet": "OBJECT",
            "shipment": "OBJECT", "calendar": "OBJECT", "report": "OBJECT", "contract": "OBJECT",
            "Boston": "LOCATION", "Dublin": "LOCATION", "Lisbon": "LOCATION", "Oslo": "LOCATION",
            "Reno": "LOCATION", "Seoul": "LOCATION", "Taipei": "LOCATION", "Zurich": "LOCATION",
            str(scenario["competency"]).replace("_", " "): "COMPETENCY",
        }
        result = text
        for old, new in replacements.items():
            result = result.replace(old, new)
        return " ".join(result.lower().split())

    by_family: dict[str, dict[str, list[str]]] = {}
    for scenario in source["scenarios"]:
        expected = gold_by_id[scenario["scenario_id"]]
        family = expected["family"]
        split = expected["split"]
        template = " || ".join(normalize_template(turn["text"], expected) for turn in scenario["turns"])
        by_family.setdefault(family, {}).setdefault(split, []).append(template)
    for variants in by_family.values():
        assert variants["dev"] and variants["hidden"]
        assert set(variants["dev"]).isdisjoint(variants["hidden"])


def test_oracle_fixtures_are_source_hash_bound_and_gold_blind() -> None:
    source, gold, _, oracle_records, oracle_plans = generate_experiment_documents(include_oracle=True)
    assert oracle_records["source_sha256"] == oracle_plans["source_sha256"] == canonical_hash(source)
    forbidden = {"answer", "required_evidence_turn_ids", "hard_negative_turn_ids", "family", "split", "primary_system", "ablation_primitive"}
    for scenario in oracle_records["scenarios"] + oracle_plans["scenarios"]:
        assert not (set(scenario) & forbidden)
    assert len(oracle_records["scenarios"]) == len(oracle_plans["scenarios"]) == len(gold["scenarios"])


def test_oracle_records_are_per_turn_traceable_and_encode_actual_semantics() -> None:
    source, gold, _, oracle_records, _ = generate_experiment_documents(include_oracle=True)
    source_by_id = {scenario["scenario_id"]: scenario for scenario in source["scenarios"]}
    gold_by_id = {scenario["scenario_id"]: scenario for scenario in gold["scenarios"]}
    for fixture in oracle_records["scenarios"]:
        scenario_id = fixture["scenario_id"]
        assert all(scenario_id not in record["entities"] for record in fixture["records"])
        record_turn_ids = {turn_id for record in fixture["records"] for turn_id in record["source_turn_ids"]}
        assert record_turn_ids == {turn["turn_id"] for turn in source_by_id[scenario_id]["turns"]}
        assert all(len(record["source_turn_ids"]) == 1 for record in fixture["records"])
        evidence = set(gold_by_id[scenario_id]["required_evidence_turn_ids"])
        negatives = set(gold_by_id[scenario_id]["hard_negative_turn_ids"])
        assert evidence <= record_turn_ids and negatives <= record_turn_ids
        assert any(record["predicate"] for record in fixture["records"])
        assert any(record["roles"] or record["relations"] for record in fixture["records"])
        assert any(record["polarity"] or record["modality"] or record["quantity"] or record["valid_time"] or record["provenance_status"] for record in fixture["records"])


def test_oracle_hard_negatives_faithfully_encode_their_surface_claims() -> None:
    source, gold, _, oracle_records, _ = generate_experiment_documents(include_oracle=True)
    source_by_id = {item["scenario_id"]: item for item in source["scenarios"]}
    gold_by_id = {item["scenario_id"]: item for item in gold["scenarios"]}
    for fixture in oracle_records["scenarios"]:
        scenario_id = fixture["scenario_id"]
        text_by_turn = {turn["turn_id"]: turn["text"] for turn in source_by_id[scenario_id]["turns"]}
        record_by_turn = {record["source_turn_ids"][0]: record for record in fixture["records"]}
        for turn_id in gold_by_id[scenario_id]["hard_negative_turn_ids"]:
            record = record_by_turn[turn_id]
            text = text_by_turn[turn_id].lower()
            if "obsolete" in text:
                assert record["lifecycle_status"] == "obsolete"
            elif "wrong alternative" in text:
                assert record["lifecycle_status"] == "rejected"

    first_role_fixture = oracle_records["scenarios"][0]
    role_records = {record["source_turn_ids"][0][-3:]: record for record in first_role_fixture["records"]}
    assert role_records["T02"]["roles"]["agent"] == "receiver"
    assert role_records["T05"]["roles"] == {
        "agent": "different clerk",
        "beneficiary": "another person",
        "object": "archive",
    }


def test_oracle_plans_vary_by_competency_and_project_gold_answers_without_gold_fields() -> None:
    source, gold, _, oracle_records, oracle_plans = generate_experiment_documents(include_oracle=True)
    source_ids = {scenario["scenario_id"] for scenario in source["scenarios"]}
    gold_by_id = {scenario["scenario_id"]: scenario for scenario in gold["scenarios"]}
    records_by_id = {scenario["scenario_id"]: scenario["records"] for scenario in oracle_records["scenarios"]}
    signatures = set()
    for fixture in oracle_plans["scenarios"]:
        scenario_id = fixture["scenario_id"]
        plan = fixture["query_plan"]
        assert scenario_id in source_ids
        assert scenario_id not in plan["entity_candidates"]
        assert plan["predicate"] or plan["traversal_steps"]
        signatures.add((plan["predicate"], plan["required_answer_slot"], tuple(sorted(plan["role_constraints"].items()))))
        answer = gold_by_id[scenario_id]["answer"]
        answer_slot = plan["required_answer_slot"]
        assert answer_slot != "abstention"
        if answer_slot == "quantity":
            assert plan["quantity"] is None
        if answer_slot == "polarity":
            assert plan["polarity"] is None
        assert answer_slot not in plan["role_constraints"]
        assert answer["values"] == [] or all(
            value not in {step.get("target") for step in plan["traversal_steps"]}
            for value in answer["values"]
        )
        selected = [record for record in records_by_id[scenario_id] if record["source_turn_ids"][0] in gold_by_id[scenario_id]["required_evidence_turn_ids"]]
        assert project_oracle_answer(selected, plan) == answer
    assert len(signatures) >= 15


def test_oracle_o_plus_recovers_exact_gold_evidence_and_answer_for_all_generated_scenarios() -> None:
    source, gold, _, oracle_records, oracle_plans = generate_experiment_documents(include_oracle=True)
    records_by_id = {item["scenario_id"]: item["records"] for item in oracle_records["scenarios"]}
    plans_by_id = {item["scenario_id"]: item["query_plan"] for item in oracle_plans["scenarios"]}

    exact_evidence = 0
    correct_answers = 0
    failures = []
    for scenario, expected in zip(source["scenarios"], gold["scenarios"], strict=True):
        scenario_id = scenario["scenario_id"]
        result = execute_arm(
            "O+",
            scenario,
            records_by_id[scenario_id],
            plans_by_id[scenario_id],
            _UnusedEncoder(),
        )
        evidence_ok = set(result["selected_evidence_turn_ids"]) == set(expected["required_evidence_turn_ids"])
        expected_answer = None if expected["answer"]["kind"] == "unanswerable" else expected["answer"]["values"][0]
        answer_ok = (
            result["predicted_answer"] == expected_answer
            and result["abstained"] is (expected["answer"]["kind"] == "unanswerable")
        )
        exact_evidence += int(evidence_ok)
        correct_answers += int(answer_ok)
        if not evidence_ok or not answer_ok:
            failures.append(
                {
                    "scenario_id": scenario_id,
                    "selected": result["selected_evidence_turn_ids"],
                    "expected_evidence": expected["required_evidence_turn_ids"],
                    "predicted_answer": result["predicted_answer"],
                    "expected_answer": expected_answer,
                    "abstained": result["abstained"],
                }
            )

    assert exact_evidence == 60, failures
    assert correct_answers == 60, failures


def test_oracle_o_minus_cannot_reconstruct_an_ablated_role_or_traversal() -> None:
    source, gold, _, oracle_records, oracle_plans = generate_experiment_documents(include_oracle=True)
    source_by_id = {item["scenario_id"]: item for item in source["scenarios"]}
    gold_by_id = {item["scenario_id"]: item for item in gold["scenarios"]}
    records_by_id = {item["scenario_id"]: item for item in oracle_records["scenarios"]}
    plans_by_id = {item["scenario_id"]: item["query_plan"] for item in oracle_plans["scenarios"]}

    by_primitive: dict[str, list[tuple[bool, bool]]] = {}
    for expected in gold["scenarios"]:
        scenario_id = expected["scenario_id"]
        fixture = records_by_id[scenario_id]
        o_plus = execute_arm(
            "O+", source_by_id[scenario_id], fixture["records"], plans_by_id[scenario_id], _UnusedEncoder()
        )
        o_minus = execute_arm(
            "O-", source_by_id[scenario_id], fixture["ablated_records"], plans_by_id[scenario_id], _UnusedEncoder()
        )
        expected_answer = None if expected["answer"]["kind"] == "unanswerable" else expected["answer"]["values"][0]
        answer_is_abstention = expected["answer"]["kind"] == "unanswerable"
        assert set(o_plus["selected_evidence_turn_ids"]) == set(expected["required_evidence_turn_ids"])
        assert o_plus["predicted_answer"] == expected_answer
        assert o_plus["abstained"] is answer_is_abstention
        by_primitive.setdefault(expected["ablation_primitive"], []).append(
            (
                set(o_minus["selected_evidence_turn_ids"]) != set(expected["required_evidence_turn_ids"]),
                not (
                    o_minus["predicted_answer"] == expected_answer
                    and o_minus["abstained"] is answer_is_abstention
                ),
            )
        )

    assert all(any(evidence_worse or answer_worse for evidence_worse, answer_worse in values) for values in by_primitive.values())


def test_oracle_ablation_changes_only_the_gold_selected_primitive_without_exposing_it() -> None:
    _, gold, _, oracle_records, _ = generate_experiment_documents(include_oracle=True)
    gold_by_id = {scenario["scenario_id"]: scenario for scenario in gold["scenarios"]}
    forbidden = {"ablation_primitive", "required_primitives", "answer", "family", "split", "primary_system"}
    for fixture in oracle_records["scenarios"]:
        assert not (set(fixture) & forbidden)
        expected_field = ablation_field(gold_by_id[fixture["scenario_id"]]["ablation_primitive"])
        differences = set()
        for record, ablated in zip(fixture["records"], fixture["ablated_records"], strict=True):
            differences.update(key for key in record if record[key] != ablated[key])
        assert differences == {expected_field}


def test_oracle_fixtures_include_typed_distractors_for_each_scale() -> None:
    source, _, distractors, oracle_records, _ = generate_experiment_documents(include_oracle=True)
    source_ids = {scenario["scenario_id"] for scenario in source["scenarios"]}
    distractors_by_key = {}
    for record in distractors["records"]:
        distractors_by_key.setdefault((record["scenario_id"], str(record["distractor_scale"])), []).append(record)

    for fixture in oracle_records["scenarios"]:
        assert fixture["scenario_id"] in source_ids
        typed = fixture["distractor_records"]
        assert set(typed) == {"50", "500"}
        for scale, records in typed.items():
            assert len(records) == len(distractors_by_key[(fixture["scenario_id"], scale)])
            assert all(record["source_turn_ids"] == [record["record_id"]] for record in records)
            assert any(record["predicate"] or record["roles"] or record["relations"] for record in records)


def test_gold_architecture_links_exist_in_audit_ledgers_and_include_directed_risks() -> None:
    _, gold, _ = generate_experiment_documents()
    root = Path(__file__).resolve().parents[2]
    matrix = json.loads((root / "artifacts/ontology-memory-experiment/architecture-audit/capability-matrix.json").read_text(encoding="utf-8"))
    risks = json.loads((root / "artifacts/ontology-memory-experiment/architecture-audit/gap-hypothesis-ledger.json").read_text(encoding="utf-8"))
    existing_ids = {item["claim_id"] for item in matrix["claims"]} | {
        item["hypothesis_id"] for item in risks["hypotheses"]
    }
    for scenario in gold["scenarios"]:
        claim_ids = set(scenario["architecture_claim_ids"])
        assert claim_ids <= existing_ids
        if scenario["origin"] == "architecture_directed":
            system = scenario["primary_system"].upper()
            assert f"RISK-{system}-001" in claim_ids
        else:
            assert claim_ids == {"CLASS-ABLATION-001"}


def test_v3_generator_adds_fallback_probes_without_changing_v2_default() -> None:
    v2_source, v2_gold, v2_distractors = generate_experiment_documents()
    v3_source, v3_gold, v3_distractors = generate_v3_experiment_documents()

    assert len(v2_source["scenarios"]) == len(v2_gold["scenarios"]) == 60
    assert len(v3_source["scenarios"]) == len(v3_gold["scenarios"]) == 64
    assert len(v3_distractors["records"]) == len(v2_distractors["records"]) + 2_200

    probes = [item for item in v3_gold["scenarios"] if "fallback_probe" in item["competency"]]
    assert Counter(item["split"] for item in probes) == {"dev": 1, "hidden": 3}
    assert {item["family"] for item in probes} == {"synonymy_sense_external_unanswerable"}
    assert all(item["architecture_claim_ids"] == ["CLASS-ABLATION-001"] for item in probes)


def test_v4_generator_adds_fresh_hidden_variants_without_changing_v3_default() -> None:
    v3_source, v3_gold, v3_distractors = generate_v3_experiment_documents()
    v4_source, v4_gold, v4_distractors = generate_v4_experiment_documents()

    assert len(v3_source["scenarios"]) == len(v3_gold["scenarios"]) == 64
    assert len(v4_source["scenarios"]) == len(v4_gold["scenarios"]) == 64
    assert len(v4_distractors["records"]) == len(v3_distractors["records"])
    assert canonical_hash(v4_source) != canonical_hash(v3_source)
    assert canonical_hash(v4_gold) != canonical_hash(v3_gold)
    assert v4_source["scenarios"][12]["turns"][0]["text"] != v3_source["scenarios"][12]["turns"][0]["text"]

    probes = [item for item in v4_gold["scenarios"] if "fallback_probe" in item["competency"]]
    assert Counter(item["split"] for item in probes) == {"dev": 1, "hidden": 3}
    assert {item["family"] for item in probes} == {"synonymy_sense_external_unanswerable"}
    source_by_id = {item["scenario_id"]: item for item in v4_source["scenarios"]}
    assert all("designat" in source_by_id[item["scenario_id"]]["question"].lower() for item in probes)
    assert all(item["architecture_claim_ids"] == ["CLASS-ABLATION-001"] for item in probes)


def test_v5_generator_adds_fresh_hidden_variants_without_changing_v4_default() -> None:
    v4_source, v4_gold, v4_distractors = generate_v4_experiment_documents()
    v5_source, v5_gold, v5_distractors = generate_v5_experiment_documents()

    assert len(v5_source["scenarios"]) == len(v5_gold["scenarios"]) == 64
    assert len(v5_distractors["records"]) == len(v4_distractors["records"])
    assert canonical_hash(v5_source) != canonical_hash(v4_source)
    assert canonical_hash(v5_gold) != canonical_hash(v4_gold)

    v4_hidden_text = " ".join(
        turn["text"]
        for scenario, gold in zip(v4_source["scenarios"], v4_gold["scenarios"], strict=True)
        if gold["split"] == "hidden"
        for turn in scenario["turns"]
    )
    v5_hidden_text = " ".join(
        turn["text"]
        for scenario, gold in zip(v5_source["scenarios"], v5_gold["scenarios"], strict=True)
        if gold["split"] == "hidden"
        for turn in scenario["turns"]
    )
    assert "supposed to approve" in v5_hidden_text
    assert "exact set comprises" in v5_hidden_text
    assert " routes " in v5_hidden_text
    assert v5_hidden_text != v4_hidden_text

    probes = [item for item in v5_gold["scenarios"] if "fallback_probe" in item["competency"]]
    assert Counter(item["split"] for item in probes) == {"dev": 1, "hidden": 3}
    assert all("fallback_probe_route" in item["competency"] for item in probes)
    source_by_id = {item["scenario_id"]: item for item in v5_source["scenarios"]}
    assert all(" route " in source_by_id[item["scenario_id"]]["question"].lower() for item in probes)


def test_v3_fallback_probe_requires_o_plus_e_and_preserves_evidence_closure() -> None:
    source, gold, _, _, _ = generate_v3_experiment_documents(include_oracle=True)
    probe_gold = next(item for item in gold["scenarios"] if item["competency"] == "fallback_probe_uncovered_predicate_dev")
    scenario = next(item for item in source["scenarios"] if item["scenario_id"] == probe_gold["scenario_id"])

    records = build_representations(scenario, "automatic")
    plan = compile_query(scenario["question"], "automatic")
    symbolic = execute_arm("O+", scenario, records, plan, _FallbackProbeEncoder())
    fallback = execute_arm("O+E", scenario, records, plan, _FallbackProbeEncoder())

    assert plan["predicate"] == "points_to_project"
    assert plan["declared_unresolved_slots"] == ["predicate"]
    assert symbolic["selected_evidence_turn_ids"] == []
    assert symbolic["predicted_answer"] is None
    assert fallback["fallback"]["triggered"] is True
    assert fallback["fallback_reason"] == "uncovered_predicate"
    assert fallback["predicted_answer"] == "project-91"
    assert fallback["selected_evidence_turn_ids"] == probe_gold["required_evidence_turn_ids"]


def test_v4_fallback_probe_requires_o_plus_e_and_preserves_evidence_closure() -> None:
    source, gold, _, _, _ = generate_v4_experiment_documents(include_oracle=True)
    probe_gold = next(item for item in gold["scenarios"] if item["competency"] == "fallback_probe_designate_dev")
    scenario = next(item for item in source["scenarios"] if item["scenario_id"] == probe_gold["scenario_id"])

    records = build_representations(scenario, "automatic")
    plan = compile_query(scenario["question"], "automatic")
    symbolic = execute_arm("O+", scenario, records, plan, _FallbackProbeEncoder())
    fallback = execute_arm("O+E", scenario, records, plan, _FallbackProbeEncoder())

    assert "designat" in scenario["question"].lower()
    assert plan["predicate"] == "points_to_project"
    assert plan["declared_unresolved_slots"] == ["predicate"]
    assert symbolic["selected_evidence_turn_ids"] == []
    assert symbolic["predicted_answer"] is None
    assert fallback["fallback"]["triggered"] is True
    assert fallback["fallback_reason"] == "uncovered_predicate"
    assert fallback["predicted_answer"] == "project-101"
    assert fallback["selected_evidence_turn_ids"] == probe_gold["required_evidence_turn_ids"]


def test_v5_fallback_probe_requires_o_plus_e_and_preserves_evidence_closure() -> None:
    source, gold, _, _, _ = generate_v5_experiment_documents(include_oracle=True)
    probe_gold = next(item for item in gold["scenarios"] if item["competency"] == "fallback_probe_route_dev")
    scenario = next(item for item in source["scenarios"] if item["scenario_id"] == probe_gold["scenario_id"])

    records = build_representations(scenario, "automatic")
    plan = compile_query(scenario["question"], "automatic")
    symbolic = execute_arm("O+", scenario, records, plan, _FallbackProbeEncoder())
    fallback = execute_arm("O+E", scenario, records, plan, _FallbackProbeEncoder())

    assert " route " in scenario["question"].lower()
    assert plan["predicate"] == "points_to_project"
    assert plan["declared_unresolved_slots"] == ["predicate"]
    assert symbolic["selected_evidence_turn_ids"] == []
    assert symbolic["predicted_answer"] is None
    assert fallback["fallback"]["triggered"] is True
    assert fallback["fallback_reason"] == "uncovered_predicate"
    assert fallback["predicted_answer"] == "project-111"
    assert fallback["selected_evidence_turn_ids"] == probe_gold["required_evidence_turn_ids"]


def test_v3_fallback_probe_rejects_structurally_wrong_distractors() -> None:
    source, gold, distractors, _, _ = generate_v3_experiment_documents(include_oracle=True)
    probe_gold = next(item for item in gold["scenarios"] if item["competency"] == "fallback_probe_uncovered_predicate_dev")
    scenario = next(item for item in source["scenarios"] if item["scenario_id"] == probe_gold["scenario_id"])
    selected_distractors = [
        item
        for item in distractors["records"]
        if item["scenario_id"] == scenario["scenario_id"] and item["distractor_scale"] == 50
    ]

    records = build_representations(scenario, "automatic")
    distractor_records = build_representations(
        {
            "scenario_id": scenario["scenario_id"],
            "turns": [
                {"turn_id": item["record_id"], "speaker": "tool", "text": item["text"]}
                for item in selected_distractors
            ],
        },
        "automatic",
    )
    plan = compile_query(scenario["question"], "automatic")
    fallback = execute_arm(
        "O+E",
        scenario,
        records,
        plan,
        _DistractorBiasedProbeEncoder(),
        distractors=distractor_records,
    )

    assert fallback["predicted_answer"] == "project-91"
    assert fallback["selected_evidence_turn_ids"] == probe_gold["required_evidence_turn_ids"]
    assert fallback["rejected_fallback_candidates"]


def test_automatic_multihop_accepts_connected_and_exact_set_contains_wording() -> None:
    scenario = {
        "scenario_id": "OME-DEV-ALT-MULTIHOP",
        "language": "en",
        "question": "Which project is linked through both the invoice and archive at Dublin?",
        "candidate_answer_budget": 64,
        "turns": [
            {
                "turn_id": "OME-DEV-ALT-MULTIHOP-T01",
                "speaker": "user",
                "text": "Blair connected the invoice to both Dublin and the archive.",
            },
            {
                "turn_id": "OME-DEV-ALT-MULTIHOP-T02",
                "speaker": "agent",
                "text": "A similar invoice links only to Dublin; the archive is not part of that record.",
            },
            {
                "turn_id": "OME-DEV-ALT-MULTIHOP-T03",
                "speaker": "tool",
                "text": "The archive links Dublin to project-04.",
            },
            {
                "turn_id": "OME-DEV-ALT-MULTIHOP-T04",
                "speaker": "agent",
                "text": "Taken together, the exact set contains invoice, Dublin, archive, and project-04.",
            },
            {
                "turn_id": "OME-DEV-ALT-MULTIHOP-T05",
                "speaker": "tool",
                "text": "A separate archive links Dublin to project-34.",
            },
        ],
    }

    records = build_representations(scenario, "automatic")
    plan = compile_query(scenario["question"], "automatic")
    result = execute_arm("O+", scenario, records, plan, _UnusedEncoder())

    assert result["predicted_answer"] == "project-04"
    assert result["selected_evidence_turn_ids"] == [
        "OME-DEV-ALT-MULTIHOP-T01",
        "OME-DEV-ALT-MULTIHOP-T03",
        "OME-DEV-ALT-MULTIHOP-T04",
    ]
    assert "OME-DEV-ALT-MULTIHOP-T02" not in result["selected_evidence_turn_ids"]
    assert "OME-DEV-ALT-MULTIHOP-T05" not in result["selected_evidence_turn_ids"]


def test_automatic_expected_quantity_uses_standing_instruction_not_initial_request() -> None:
    scenario = {
        "scenario_id": "OME-DEV-ALT-EXPECTED-QUANTITY",
        "language": "en",
        "question": "How many tablets is the clerk expected to approve for Devon?",
        "candidate_answer_budget": 64,
        "turns": [
            {
                "turn_id": "OME-DEV-ALT-EXPECTED-QUANTITY-T01",
                "speaker": "user",
                "text": "Devon requested that the clerk approve exactly 5 tablets.",
            },
            {
                "turn_id": "OME-DEV-ALT-EXPECTED-QUANTITY-T02",
                "speaker": "agent",
                "text": "The receiver approved 6 tablets, and the clerk was not that approver.",
            },
            {
                "turn_id": "OME-DEV-ALT-EXPECTED-QUANTITY-T03",
                "speaker": "user",
                "text": "For Devon, the clerk may review exactly 5 tablets.",
            },
            {
                "turn_id": "OME-DEV-ALT-EXPECTED-QUANTITY-T04",
                "speaker": "agent",
                "text": "The standing instruction says the clerk should approve exactly 5 tablets for Devon.",
            },
            {
                "turn_id": "OME-DEV-ALT-EXPECTED-QUANTITY-T05",
                "speaker": "tool",
                "text": "Another clerk approved 6 tablets for another person.",
            },
        ],
    }

    records = build_representations(scenario, "automatic")
    plan = compile_query(scenario["question"], "automatic")
    result = execute_arm("O+", scenario, records, plan, _UnusedEncoder())

    assert plan["modality"] == "planned"
    assert result["predicted_answer"] == "5"
    assert result["selected_evidence_turn_ids"] == ["OME-DEV-ALT-EXPECTED-QUANTITY-T04"]


def test_automatic_multihop_accepts_shared_by_both_and_exact_set_includes_wording() -> None:
    scenario = {
        "scenario_id": "OME-DEV-ALT-SHARED-MULTIHOP",
        "language": "en",
        "question": "Which project is shared by both the invoice and archive at Dublin?",
        "candidate_answer_budget": 64,
        "turns": [
            {
                "turn_id": "OME-DEV-ALT-SHARED-MULTIHOP-T01",
                "speaker": "user",
                "text": "For set exclusion, Blair linked the invoice to Dublin and the archive.",
            },
            {
                "turn_id": "OME-DEV-ALT-SHARED-MULTIHOP-T02",
                "speaker": "agent",
                "text": "A similar invoice is linked only to Dublin; the archive is not part of this record.",
            },
            {
                "turn_id": "OME-DEV-ALT-SHARED-MULTIHOP-T03",
                "speaker": "tool",
                "text": "The archive links Dublin to project-04.",
            },
            {
                "turn_id": "OME-DEV-ALT-SHARED-MULTIHOP-T04",
                "speaker": "agent",
                "text": "The exact set includes invoice, Dublin, archive, and project-04.",
            },
            {
                "turn_id": "OME-DEV-ALT-SHARED-MULTIHOP-T05",
                "speaker": "tool",
                "text": "A separate archive links Dublin to project-34.",
            },
        ],
    }

    records = build_representations(scenario, "automatic")
    plan = compile_query(scenario["question"], "automatic")
    result = execute_arm("O+", scenario, records, plan, _UnusedEncoder())

    assert result["predicted_answer"] == "project-04"
    assert result["selected_evidence_turn_ids"] == [
        "OME-DEV-ALT-SHARED-MULTIHOP-T01",
        "OME-DEV-ALT-SHARED-MULTIHOP-T03",
        "OME-DEV-ALT-SHARED-MULTIHOP-T04",
    ]
    assert "OME-DEV-ALT-SHARED-MULTIHOP-T02" not in result["selected_evidence_turn_ids"]
    assert "OME-DEV-ALT-SHARED-MULTIHOP-T05" not in result["selected_evidence_turn_ids"]


def test_automatic_multihop_accepts_connects_both_and_exact_set_comprises_wording() -> None:
    scenario = {
        "scenario_id": "OME-DEV-ALT-CONNECTS-MULTIHOP",
        "language": "en",
        "question": "Which project connects both the invoice and archive at Dublin?",
        "candidate_answer_budget": 64,
        "turns": [
            {
                "turn_id": "OME-DEV-ALT-CONNECTS-MULTIHOP-T01",
                "speaker": "user",
                "text": "For set exclusion, Blair linked the invoice to Dublin and archive.",
            },
            {
                "turn_id": "OME-DEV-ALT-CONNECTS-MULTIHOP-T02",
                "speaker": "agent",
                "text": "A similar invoice is linked only to Dublin; the archive is not part of this record.",
            },
            {
                "turn_id": "OME-DEV-ALT-CONNECTS-MULTIHOP-T03",
                "speaker": "tool",
                "text": "The archive links Dublin to project-04.",
            },
            {
                "turn_id": "OME-DEV-ALT-CONNECTS-MULTIHOP-T04",
                "speaker": "agent",
                "text": "The exact set comprises invoice, Dublin, archive, and project-04.",
            },
            {
                "turn_id": "OME-DEV-ALT-CONNECTS-MULTIHOP-T05",
                "speaker": "tool",
                "text": "A separate archive links Dublin to project-34.",
            },
        ],
    }

    records = build_representations(scenario, "automatic")
    plan = compile_query(scenario["question"], "automatic")
    result = execute_arm("O+", scenario, records, plan, _UnusedEncoder())

    assert result["predicted_answer"] == "project-04"
    assert result["selected_evidence_turn_ids"] == [
        "OME-DEV-ALT-CONNECTS-MULTIHOP-T01",
        "OME-DEV-ALT-CONNECTS-MULTIHOP-T03",
        "OME-DEV-ALT-CONNECTS-MULTIHOP-T04",
    ]


def test_automatic_temporal_closure_keeps_before_update_provenance_turn() -> None:
    scenario = {
        "scenario_id": "OME-DEV-ALT-TEMPORAL",
        "language": "en",
        "question": "After the valid time start update, is the permit active after 2026-05-14?",
        "candidate_answer_budget": 64,
        "turns": [
            {
                "turn_id": "OME-DEV-ALT-TEMPORAL-T01",
                "speaker": "user",
                "text": "On 2026-05-14, Blair reported that the permit was active in Oslo.",
            },
            {
                "turn_id": "OME-DEV-ALT-TEMPORAL-T02",
                "speaker": "tool",
                "text": "Before the valid time start update, the log recorded the permit as active.",
            },
            {
                "turn_id": "OME-DEV-ALT-TEMPORAL-T03",
                "speaker": "user",
                "text": "A correction superseded that entry: the permit is not active after 2026-05-14.",
            },
            {
                "turn_id": "OME-DEV-ALT-TEMPORAL-T04",
                "speaker": "agent",
                "text": "Following the correction, the current status is inactive after 2026-05-14; the earlier tool entry remains provenance.",
            },
            {
                "turn_id": "OME-DEV-ALT-TEMPORAL-T05",
                "speaker": "tool",
                "text": "An archived record lists the permit as active after 2026-05-14.",
            },
        ],
    }

    records = build_representations(scenario, "automatic")
    plan = compile_query(scenario["question"], "automatic")
    result = execute_arm("O+", scenario, records, plan, _UnusedEncoder())

    assert result["predicted_answer"] == "no"
    assert result["selected_evidence_turn_ids"] == [
        "OME-DEV-ALT-TEMPORAL-T02",
        "OME-DEV-ALT-TEMPORAL-T03",
        "OME-DEV-ALT-TEMPORAL-T04",
    ]
    assert "OME-DEV-ALT-TEMPORAL-T01" not in result["selected_evidence_turn_ids"]
    assert "OME-DEV-ALT-TEMPORAL-T05" not in result["selected_evidence_turn_ids"]


def test_automatic_sense_query_handles_used_ledger_and_denotes_wording() -> None:
    scenario = {
        "scenario_id": "OME-DEV-ALT-SENSE",
        "language": "en",
        "question": "Which sense of report is supported in Seoul?",
        "candidate_answer_budget": 64,
        "turns": [
            {
                "turn_id": "OME-DEV-ALT-SENSE-T01",
                "speaker": "user",
                "text": "While in Seoul, Casey used ledger for the report.",
            },
            {
                "turn_id": "OME-DEV-ALT-SENSE-T02",
                "speaker": "agent",
                "text": "In this context, ledger denotes an account record rather than a travel schedule.",
            },
            {
                "turn_id": "OME-DEV-ALT-SENSE-T03",
                "speaker": "user",
                "text": "The account record was reviewed, but no owner or external relation was named.",
            },
            {
                "turn_id": "OME-DEV-ALT-SENSE-T04",
                "speaker": "agent",
                "text": "The evidence supports the accounting sense only; the missing details remain unresolved.",
            },
            {
                "turn_id": "OME-DEV-ALT-SENSE-T05",
                "speaker": "tool",
                "text": "In another trip record, ledger denotes a travel schedule in Seoul.",
            },
        ],
    }

    records = build_representations(scenario, "automatic")
    plan = compile_query(scenario["question"], "automatic")
    result = execute_arm("O+", scenario, records, plan, _UnusedEncoder())

    assert result["predicted_answer"] == "account record"
    assert result["selected_evidence_turn_ids"] == [
        "OME-DEV-ALT-SENSE-T01",
        "OME-DEV-ALT-SENSE-T02",
        "OME-DEV-ALT-SENSE-T03",
        "OME-DEV-ALT-SENSE-T04",
    ]
    assert "OME-DEV-ALT-SENSE-T05" not in result["selected_evidence_turn_ids"]


def test_automatic_owner_query_uses_explicit_absence_over_later_owner_claim() -> None:
    scenario = {
        "scenario_id": "OME-DEV-ALT-OWNER",
        "language": "en",
        "question": "Who owns the report in Seoul?",
        "candidate_answer_budget": 64,
        "turns": [
            {
                "turn_id": "OME-DEV-ALT-OWNER-T01",
                "speaker": "user",
                "text": "While in Seoul, Casey used ledger for the report.",
            },
            {
                "turn_id": "OME-DEV-ALT-OWNER-T02",
                "speaker": "agent",
                "text": "In this context, ledger denotes an account record rather than a travel schedule.",
            },
            {
                "turn_id": "OME-DEV-ALT-OWNER-T03",
                "speaker": "user",
                "text": "The account record was reviewed, but no owner or external relation was named.",
            },
            {
                "turn_id": "OME-DEV-ALT-OWNER-T04",
                "speaker": "agent",
                "text": "The evidence supports the accounting sense only; the missing details remain unresolved.",
            },
            {
                "turn_id": "OME-DEV-ALT-OWNER-T05",
                "speaker": "tool",
                "text": "In another trip record, ledger denotes a travel schedule in Seoul.",
            },
            {
                "turn_id": "OME-DEV-ALT-OWNER-T06",
                "speaker": "agent",
                "text": "Casey is listed as owner of the report account in Seoul.",
            },
        ],
    }

    records = build_representations(scenario, "automatic")
    plan = compile_query(scenario["question"], "automatic")
    result = execute_arm("O+", scenario, records, plan, _UnusedEncoder())

    assert result["predicted_answer"] is None
    assert result["abstained"] is True
    assert result["selected_evidence_turn_ids"] == [
        "OME-DEV-ALT-OWNER-T01",
        "OME-DEV-ALT-OWNER-T02",
        "OME-DEV-ALT-OWNER-T03",
        "OME-DEV-ALT-OWNER-T04",
    ]
    assert "OME-DEV-ALT-OWNER-T06" not in result["selected_evidence_turn_ids"]
