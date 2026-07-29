from tools.ontology_memory_experiment.executors import execute_arm
from tools.ontology_memory_experiment.query import compile_query
from tools.ontology_memory_experiment.representations import build_representations


class RoleBiasedEncoder:
    model_metadata = {"provider": "test", "model_id": "role-biased", "dimension": 2}

    def encode(self, texts):
        return [[1.0, 0.0] if text.startswith("Who") or "wrong" in text else [0.8, 0.2] for text in texts]


def _records():
    return [
        {"record_id": "wrong", "source_turn_ids": ["T-wrong"], "surface_text": "wrong Avery approved invoice I-7", "entities": ["Avery", "invoice I-7"], "predicate": "approve", "roles": {"agent": "Blair", "object": "invoice I-7"}, "polarity": "positive", "modality": "asserted", "provenance_status": "user_reported", "valid_time": "2025-01-01", "quantity": 1, "relations": []},
        {"record_id": "right", "source_turn_ids": ["T-right"], "surface_text": "correct Avery approved invoice I-7", "entities": ["Avery", "invoice I-7"], "predicate": "approve", "roles": {"agent": "Avery", "object": "invoice I-7"}, "polarity": "positive", "modality": "asserted", "provenance_status": "user_reported", "valid_time": "2025-01-01", "quantity": 1, "relations": []},
    ]


def _plan():
    return {"entity_candidates": ["Avery", "invoice I-7"], "predicate": "approve", "role_constraints": {"agent": "Avery"}, "polarity": "positive", "modality": "asserted", "quantity": 1, "valid_time": "2025-01-01", "provenance_status": "user_reported", "conjunction_groups": [], "traversal_steps": [], "unresolved_slots": []}


def test_ranking_arm_can_surface_role_swapped_negative_but_symbolic_arm_filters_it():
    scenario = {"scenario_id": "fixture-exec", "question": "Who approved invoice I-7?"}

    ranked = execute_arm("B2", scenario, _records(), _plan(), RoleBiasedEncoder())
    symbolic = execute_arm("O+", scenario, _records(), _plan(), RoleBiasedEncoder())

    assert "T-wrong" in ranked["selected_evidence_turn_ids"]
    assert symbolic["selected_evidence_turn_ids"] == ["T-right"]
    assert symbolic["constraint_checks"]["roles"] is True


def test_ablation_and_dense_fallback_cannot_recover_or_override_explicit_role_constraint():
    scenario = {"scenario_id": "fixture-ablate", "question": "Who approved invoice I-7?"}
    ablated = [{**record, "roles": {}} for record in _records()]

    plan = {**_plan(), "unresolved_slots": ["role"]}
    result = execute_arm("O+E", scenario, ablated, plan, RoleBiasedEncoder())

    assert result["fallback_trigger"] is None
    assert result["selected_evidence_turn_ids"] == []
    assert result["rejected_fallback_candidates"] == []


def test_symbolic_execution_projects_answers_handles_supersession_and_returns_complete_path_evidence():
    scenario = {"scenario_id": "OME-S902", "question": "Which project is linked through both report and archive at Taipei?", "candidate_answer_budget": 8}
    records = [
        {"record_id": "old", "source_turn_ids": ["T1"], "surface_text": "report active", "entities": ["report"], "predicate": "active", "roles": {"value": "yes"}, "polarity": "positive", "relations": []},
        {"record_id": "new", "source_turn_ids": ["T2"], "surface_text": "report inactive", "entities": ["report"], "predicate": "active", "roles": {"value": "no"}, "polarity": "negative", "supersedes": ["old"], "relations": []},
        {"record_id": "link1", "source_turn_ids": ["T3"], "surface_text": "report linked Taipei archive", "entities": ["report", "Taipei", "archive"], "predicate": "link", "roles": {}, "relations": [{"subject": "report", "predicate": "link", "object": "Taipei"}, {"subject": "report", "predicate": "link", "object": "archive"}]},
        {"record_id": "link2", "source_turn_ids": ["T4"], "surface_text": "archive linked Taipei project-03", "entities": ["archive", "Taipei", "project-03"], "predicate": "link", "roles": {"project": "project-03"}, "relations": [{"subject": "archive", "predicate": "link", "object": "Taipei"}, {"subject": "archive", "predicate": "link", "object": "project-03"}]},
    ]
    status_plan = {"entity_candidates": ["report"], "predicate": "active", "polarity": "negative", "role_constraints": {}, "required_answer_slot": "value", "declared_unresolved_slots": []}
    path_plan = {"entity_candidates": ["report", "archive", "Taipei"], "predicate": "link", "role_constraints": {}, "conjunction_groups": [["report", "archive", "Taipei"]], "traversal_steps": [{"from": "archive", "relation": "link", "to": "project"}], "required_answer_slot": "project", "declared_unresolved_slots": []}

    status = execute_arm("O+", scenario, records, status_plan, RoleBiasedEncoder())
    path = execute_arm("O+", scenario, records, path_plan, RoleBiasedEncoder())

    assert status["predicted_answer"] == "no"
    assert status["selected_evidence_turn_ids"] == ["T2"]
    assert path["predicted_answer"] == "project-03"
    assert path["selected_evidence_turn_ids"] == ["T3", "T4"]


def test_fallback_can_recover_only_declared_predicate_gap_and_reenforces_role_constraint():
    scenario = {"scenario_id": "OME-S903", "question": "Which clerk approved?"}
    plan = {"entity_candidates": ["Avery"], "predicate": None, "role_constraints": {"agent": "clerk"}, "required_answer_slot": "agent", "declared_unresolved_slots": ["predicate"]}
    records = [{"record_id": "bad", "source_turn_ids": ["Tbad"], "surface_text": "wrong Avery approved", "entities": ["Avery"], "predicate": "approve", "roles": {"agent": "Blair"}, "relations": []}, {"record_id": "good", "source_turn_ids": ["Tgood"], "surface_text": "correct Avery approved", "entities": ["Avery"], "predicate": "approve", "roles": {"agent": "clerk"}, "relations": []}]

    result = execute_arm("O+E", scenario, records, plan, RoleBiasedEncoder())

    assert result["fallback_trigger"] == "uncovered_predicate"
    assert result["selected_evidence_turn_ids"] == ["Tgood"]
    assert result["predicted_answer"] == "clerk"


def test_ranking_uses_whitespace_token_budget_and_constraint_success_requires_one_complete_record():
    scenario = {"scenario_id": "OME-S904", "question": "approve", "candidate_answer_budget": 3}
    records = [
        {"record_id": "first", "source_turn_ids": ["T1"], "surface_text": "wrong Avery", "entities": ["Avery"], "predicate": "approve", "roles": {"agent": "Blair"}},
        {"record_id": "second", "source_turn_ids": ["T2"], "surface_text": "correct Avery", "entities": ["Avery"], "predicate": "approve", "roles": {"agent": "Avery"}},
    ]
    plan = {"entity_candidates": ["Avery"], "predicate": "approve", "role_constraints": {"agent": "Avery"}, "required_answer_slot": "agent", "declared_unresolved_slots": []}

    ranked = execute_arm("B0", scenario, records, plan, RoleBiasedEncoder())
    symbolic = execute_arm("O+", scenario, records, plan, RoleBiasedEncoder())

    assert len(ranked["selected_evidence_turn_ids"]) == 1
    assert symbolic["constraint_checks"]["complete_result"] is True


def test_ranking_arms_honor_explicit_evidence_token_budget_over_scenario_default():
    scenario = {"scenario_id": "OME-S908", "question": "approve", "candidate_answer_budget": 51}
    records = [
        {"record_id": "first", "source_turn_ids": ["T1"], "surface_text": "first record", "entities": []},
        {"record_id": "second", "source_turn_ids": ["T2"], "surface_text": "second record", "entities": []},
    ]
    plan = {"required_answer_slot": "value", "declared_unresolved_slots": []}

    result = execute_arm("B0", scenario, records, plan, RoleBiasedEncoder(), evidence_token_budget=2)

    assert result["selected_evidence_turn_ids"] == ["T1"]


def test_ranking_arms_extract_quantity_from_selected_raw_text_consistently():
    scenario = {"scenario_id": "OME-S905", "question": "How many archives should the clerk approve?", "candidate_answer_budget": 51}
    record = {
        "record_id": "quantity",
        "source_turn_ids": ["T-quantity"],
        "surface_text": "The current request says the clerk should approve exactly 7 archives.",
    }
    plan = {"required_answer_slot": "quantity", "declared_unresolved_slots": []}

    for arm in ("B0", "B1", "B2"):
        result = execute_arm(arm, scenario, [record], plan, RoleBiasedEncoder())
        assert result["predicted_answer"] == "7"
        assert result["abstained"] is False


def test_ranking_arms_extract_polarity_project_and_sense_without_structured_fields():
    cases = [
        (
            "polarity",
            "Current status is inactive after 2026-02-11.",
            {"required_answer_slot": "value", "declared_unresolved_slots": []},
            "no",
        ),
        (
            "project",
            "The archive links Taipei to project-03.",
            {"required_answer_slot": "project", "declared_unresolved_slots": []},
            "project-03",
        ),
        (
            "sense",
            "Ledger here means an account record, not a travel schedule.",
            {"required_answer_slot": "sense", "declared_unresolved_slots": []},
            "account record",
        ),
    ]
    for record_id, text, plan, expected in cases:
        scenario = {"scenario_id": f"OME-S906-{record_id}", "question": "answer", "candidate_answer_budget": 51}
        record = {"record_id": record_id, "source_turn_ids": [f"T-{record_id}"], "surface_text": text}
        for arm in ("B0", "B1", "B2"):
            result = execute_arm(arm, scenario, [record], plan, RoleBiasedEncoder())
            assert result["predicted_answer"] == expected
            assert result["abstained"] is False


def test_ranking_arms_abstain_on_explicit_unanswerable_text():
    scenario = {"scenario_id": "OME-S907", "question": "Who owns the contract?", "candidate_answer_budget": 51}
    record = {
        "record_id": "absence",
        "source_turn_ids": ["T-absence"],
        "surface_text": "No owner was named for the contract.",
    }
    plan = {"required_answer_slot": "owner", "answer_policy": "require_explicit_absence", "declared_unresolved_slots": []}

    for arm in ("B0", "B1", "B2"):
        result = execute_arm(arm, scenario, [record], plan, RoleBiasedEncoder())
        assert result["predicted_answer"] is None
        assert result["abstained"] is True


def test_automatic_temporal_compiler_returns_current_state_with_provenance_closure():
    scenario = {
        "scenario_id": "OME-S017",
        "question": "After the valid time end update, is the archive active after 2026-03-12?",
        "candidate_answer_budget": 51,
        "turns": [
            {"turn_id": "OME-S017-T01", "speaker": "user", "text": "On 2026-03-12, Avery reported that the archive was active in Boston."},
            {"turn_id": "OME-S017-T02", "speaker": "tool", "text": "Recorded status before the valid time end update: the archive was active."},
            {"turn_id": "OME-S017-T03", "speaker": "user", "text": "Correction: the prior status is superseded and the archive is not active after 2026-03-12."},
            {"turn_id": "OME-S017-T04", "speaker": "agent", "text": "Current status is inactive after 2026-03-12; retain the prior tool record only as provenance."},
            {"turn_id": "OME-S017-T05", "speaker": "tool", "text": "An obsolete record says the archive remains active after 2026-03-12."},
            {"turn_id": "OME-S017-T06", "speaker": "agent", "text": "The correction is recorded as a new active state rather than a supersession."},
        ],
    }

    records = build_representations(scenario, "automatic")
    plan = compile_query(scenario["question"], "automatic")
    result = execute_arm("O+", scenario, records, plan, RoleBiasedEncoder())

    assert result["predicted_answer"] == "no"
    assert result["selected_evidence_turn_ids"] == [
        "OME-S017-T02",
        "OME-S017-T03",
        "OME-S017-T04",
    ]
    assert result["constraint_checks"]["complete_result"] is True


def test_automatic_multihop_compiler_returns_exact_path_evidence():
    scenario = {
        "scenario_id": "OME-S031",
        "question": "For two way conjunction, which project is linked through both the report and archive at Taipei?",
        "candidate_answer_budget": 51,
        "turns": [
            {"turn_id": "OME-S031-T01", "speaker": "user", "text": "Gray linked the report to both Taipei and the archive for two way conjunction."},
            {"turn_id": "OME-S031-T02", "speaker": "agent", "text": "A similar report is linked only to Taipei; the archive is not part of that record."},
            {"turn_id": "OME-S031-T03", "speaker": "tool", "text": "The archive links Taipei to project-01."},
            {"turn_id": "OME-S031-T04", "speaker": "agent", "text": "The exact set is report, Taipei, archive, and project-01."},
            {"turn_id": "OME-S031-T05", "speaker": "tool", "text": "A separate archive links Taipei to project-31."},
        ],
    }

    records = build_representations(scenario, "automatic")
    plan = compile_query(scenario["question"], "automatic")
    result = execute_arm("O+", scenario, records, plan, RoleBiasedEncoder())

    assert result["predicted_answer"] == "project-01"
    assert result["selected_evidence_turn_ids"] == [
        "OME-S031-T01",
        "OME-S031-T03",
        "OME-S031-T04",
    ]
    assert result["constraint_checks"]["traversal"] is True
    assert result["constraint_checks"]["conjunction"] is True


def test_automatic_absence_compiler_rejects_late_owner_claim_and_preserves_context():
    scenario = {
        "scenario_id": "OME-S048",
        "question": "For ontology external term, who owns the contract in Zurich?",
        "candidate_answer_budget": 51,
        "turns": [
            {"turn_id": "OME-S048-T01", "speaker": "user", "text": "Harper called the contract a ledger while visiting Zurich."},
            {"turn_id": "OME-S048-T02", "speaker": "agent", "text": "For ontology external term, ledger here means an account record, not a travel schedule."},
            {"turn_id": "OME-S048-T03", "speaker": "user", "text": "The account record was reviewed, but no owner or external relation was named."},
            {"turn_id": "OME-S048-T04", "speaker": "agent", "text": "The available turns support only the accounting sense and an abstention where details are absent."},
            {"turn_id": "OME-S048-T05", "speaker": "tool", "text": "In another trip record, ledger denotes a travel schedule in Zurich."},
            {"turn_id": "OME-S048-T06", "speaker": "agent", "text": "Harper is listed as owner of the contract account in Zurich."},
        ],
    }

    records = build_representations(scenario, "automatic")
    plan = compile_query(scenario["question"], "automatic")
    result = execute_arm("O+", scenario, records, plan, RoleBiasedEncoder())

    assert result["predicted_answer"] is None
    assert result["abstained"] is True
    assert result["selected_evidence_turn_ids"] == [
        "OME-S048-T01",
        "OME-S048-T02",
        "OME-S048-T03",
        "OME-S048-T04",
    ]
