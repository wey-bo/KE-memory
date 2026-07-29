from tools.ontology_memory_experiment.query import compile_query
from tools.ontology_memory_experiment.models import QueryPlan


def test_compile_query_extracts_explicit_negation_predicate_and_entity_without_scenario_specific_rules():
    plan = compile_query("Who did not approve invoice I-7?", "automatic")

    assert plan["predicate"] == "approve"
    assert plan["polarity"] == "negative"
    assert "invoice I-7" in plan["entity_candidates"]
    assert plan["required_answer_slot"] == "agent"


def test_compile_query_declares_unknown_structure_as_unresolved_instead_of_fabricating_a_constraint():
    plan = compile_query("Who handled the unusual document?", "automatic")

    assert "predicate" in plan["declared_unresolved_slots"]
    assert plan["role_constraints"] == {}


def test_compiled_plan_uses_the_public_query_plan_contract():
    plan = compile_query("Who did not approve invoice I-7?", "automatic")

    validated = QueryPlan.model_validate(plan)

    assert validated.declared_unresolved_slots == []


def test_query_compilation_covers_quantity_temporal_path_and_sense_questions_without_fixture_leakage():
    quantity = compile_query("How many archives should the clerk approve for Avery?", "automatic")
    temporal = compile_query("Is the archive active after 2026-03-11?", "automatic")
    path = compile_query("Which project is linked through both archive and archive at Boston?", "automatic")
    sense = compile_query("Which sense of archive is supported in Boston?", "automatic")

    assert quantity["required_answer_slot"] == "quantity"
    assert temporal["predicate"] == "active" and temporal["time_filter"] == "2026-03-11"
    assert path["conjunction_groups"] and path["traversal_steps"]
    assert sense["required_answer_slot"] == "sense"


def test_compile_query_handles_current_frozen_for_and_after_prefixes_without_scenario_rules():
    quantity = compile_query("For the agent role request, how many archives should the clerk approve for Avery?", "automatic")
    temporal = compile_query("After the correction update, is the permit active after 2026-05-14?", "automatic")
    sense = compile_query("For sense disambiguation, which sense of report is supported in Taipei?", "automatic")

    assert quantity["predicate"] == "approve" and quantity["required_answer_slot"] == "quantity"
    assert temporal["predicate"] == "active" and temporal["time_filter"] == "2026-05-14"
    assert sense["predicate"] == "sense_of" and sense["required_answer_slot"] == "sense"


def test_question_polarity_is_not_answer_value_leakage_for_yes_no_state_questions():
    """A question asking whether a state holds does not assert its answer."""
    plan = compile_query("Is the archive active after 2026-03-11?", "automatic")

    assert plan["required_answer_slot"] == "value"
    assert plan["polarity"] is None
    assert plan["time_filter"] == "2026-03-11"


def test_automatic_query_uses_generic_traversal_step_keys_and_binds_answer_slot():
    plan = compile_query(
        "Which project is linked through both the report and archive at Taipei?",
        "automatic",
    )

    assert plan["traversal_steps"]
    assert all(set(step) <= {"source", "predicate", "target", "target_slot"} for step in plan["traversal_steps"])
    assert any(step.get("target_slot") == "project" for step in plan["traversal_steps"])
    QueryPlan.model_validate(plan)


def test_automatic_query_does_not_use_answer_slot_as_role_constraint_or_synthetic_filter():
    for question in (
        "Who owns the contract in Zurich?",
        "Which sense of report is supported in Taipei?",
        "How many archives should the clerk approve for Avery?",
    ):
        plan = compile_query(question, "automatic")
        assert plan["required_answer_slot"] not in plan["role_constraints"]
        assert plan["quantity"] is None
        assert plan["polarity"] is None
