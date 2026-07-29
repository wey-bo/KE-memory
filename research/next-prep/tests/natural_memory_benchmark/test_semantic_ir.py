from __future__ import annotations

import pytest
from pydantic import ValidationError

from tools.natural_memory_benchmark.semantic_ir import (
    ClosureRecord,
    EvidenceSpan,
    L1MemoryUnit,
    L2MemoryUnit,
    Predicate,
    QuerySlotPlan,
    RoleBinding,
    SourceBinding,
    evaluate_closure,
    execute_query,
    fallback_allowed_for_closure,
)


def _evidence_span(evidence_id: str = "E1") -> EvidenceSpan:
    return EvidenceSpan(
        evidence_id=evidence_id,
        turn_id="turn-1",
        session_id="session-1",
        char_start=0,
        char_end=20,
        text="User led the migration project.",
    )


def _source_binding() -> SourceBinding:
    return SourceBinding(
        speaker="user",
        source_status="user_reported",
        evidence_spans=[_evidence_span()],
    )


def _l1_unit(unit_id: str = "l1-led-project", *, sense: str = "lead/manage", operator: str = "led_by") -> L1MemoryUnit:
    return L1MemoryUnit(
        unit_id=unit_id,
        kind="event",
        predicate=Predicate(surface="led", sense=sense, canonical_operator=operator),
        roles=[
            RoleBinding(role="ARG0", entity_id="user", role_name="agent"),
            RoleBinding(role="ARG1", entity_id="project-migration", role_name="theme"),
        ],
        source=_source_binding(),
    )


def _l1_event(
    unit_id: str,
    *,
    surface: str,
    sense: str,
    operator: str,
    evidence_id: str,
    lifecycle: str = "active",
    roles: list[RoleBinding] | None = None,
) -> L1MemoryUnit:
    return L1MemoryUnit(
        unit_id=unit_id,
        kind="event",
        predicate=Predicate(surface=surface, sense=sense, canonical_operator=operator),
        roles=roles
        or [
            RoleBinding(role="ARG0", entity_id="user", role_name="agent"),
            RoleBinding(role="ARG1", entity_id=unit_id.replace("l1-", ""), role_name="theme"),
        ],
        source=SourceBinding(
            speaker="user",
            source_status="user_reported",
            evidence_spans=[
                EvidenceSpan(
                    evidence_id=evidence_id,
                    turn_id=f"turn-{evidence_id}",
                    session_id="session-1",
                    char_start=0,
                    char_end=50,
                    text=f"Evidence for {unit_id}.",
                )
            ],
        ),
        lifecycle=lifecycle,  # type: ignore[arg-type]
    )


def test_l1_unit_requires_source_evidence_and_preserves_predicate_sense():
    unit = _l1_unit()

    assert unit.level == "L1"
    assert unit.predicate.surface == "led"
    assert unit.predicate.sense == "lead/manage"
    assert unit.predicate.canonical_operator == "led_by"
    assert unit.source.evidence_spans[0].evidence_id == "E1"

    with pytest.raises(ValidationError, match="evidence_spans"):
        L1MemoryUnit(
            unit_id="l1-no-evidence",
            kind="event",
            predicate=Predicate(surface="led", sense="lead/manage", canonical_operator="led_by"),
            roles=[RoleBinding(role="ARG0", entity_id="user", role_name="agent")],
            source=SourceBinding(speaker="user", source_status="user_reported", evidence_spans=[]),
        )


def test_l2_unit_requires_abstracts_closure_and_l1_provenance():
    unit = L2MemoryUnit(
        unit_id="l2-project-summary",
        kind="project",
        abstracts=["l1-led-project"],
        summary="User has led the migration project.",
        assertions=["ke-1"],
        closure_id="closure-projects",
        lifecycle="active",
        source_l1_units=["l1-led-project"],
        source_turns=["turn-1"],
        source_sessions=["session-1"],
    )

    assert unit.level == "L2"
    assert unit.abstracts == ["l1-led-project"]
    assert unit.source_l1_units == ["l1-led-project"]

    with pytest.raises(ValidationError, match="source_l1_units"):
        L2MemoryUnit(
            unit_id="l2-broken-summary",
            kind="project",
            abstracts=["l1-led-project"],
            summary="Broken summary.",
            assertions=["ke-1"],
            closure_id="closure-projects",
            lifecycle="active",
            source_l1_units=[],
            source_turns=["turn-1"],
            source_sessions=["session-1"],
        )


def test_ir_models_reject_extra_fields():
    with pytest.raises(ValidationError):
        Predicate(surface="led", sense="lead/manage", canonical_operator="led_by", unexpected=True)  # type: ignore[call-arg]


def test_query_slot_plan_and_closure_contracts_are_json_compatible():
    closure = ClosureRecord(
        closure_id="closure-projects",
        claim_or_query_id="query-projects",
        pattern="multi_evidence_set",
        required_units=[
            {"unit_id": "l1-led-project", "role": "evidence"},
            {"unit_id": "l1-leading-dashboard", "role": "evidence"},
        ],
    )
    plan = QuerySlotPlan(
        query_id="query-projects",
        intent="multi_evidence",
        target_level="both",
        predicate_sense="lead/manage",
        canonical_operator="led_by",
        required_closure_pattern="multi_evidence_set",
        closure_id="closure-projects",
    )

    closure_payload = closure.model_dump()
    plan_payload = plan.model_dump()

    assert closure_payload["schema_version"] == "semantic-ir-closure-v1"
    assert closure_payload["complete"] is False
    assert plan_payload["schema_version"] == "semantic-ir-query-plan-v1"
    assert plan_payload["fallback_allowed_reasons"] == [
        "unresolved_entity",
        "lexical_predicate_missing_link",
        "incomplete_evidence_slot",
    ]


def test_single_fact_closure_is_complete_when_required_unit_exists():
    closure = ClosureRecord(
        closure_id="closure-fact",
        claim_or_query_id="query-fact",
        pattern="single_fact",
        required_units=[{"unit_id": "l1-fact", "role": "evidence"}],
    )

    evaluated = evaluate_closure(closure, {"l1-fact"})

    assert evaluated.complete is True
    assert evaluated.missing_slots == []
    assert evaluated.reason == "closure complete"


def test_multi_evidence_closure_records_missing_required_units():
    closure = ClosureRecord(
        closure_id="closure-projects",
        claim_or_query_id="query-projects",
        pattern="multi_evidence_set",
        required_units=[
            {"unit_id": "l1-led-migration", "role": "evidence"},
            {"unit_id": "l1-leading-dashboard", "role": "evidence"},
        ],
    )

    evaluated = evaluate_closure(closure, {"l1-led-migration"})

    assert evaluated.complete is False
    assert [slot.unit_id for slot in evaluated.missing_slots] == ["l1-leading-dashboard"]
    assert evaluated.reason == "missing required closure slots"


def test_causal_answerability_requires_cause_effect_and_causal_link_roles():
    closure = ClosureRecord(
        closure_id="closure-feedback-cause",
        claim_or_query_id="query-feedback-cause",
        pattern="causal_answerability",
        required_units=[
            {"unit_id": "l1-feedback-observation", "role": "cause"},
            {"unit_id": "l1-ui-change", "role": "effect"},
        ],
    )

    evaluated = evaluate_closure(closure, {"l1-feedback-observation", "l1-ui-change"})

    assert evaluated.complete is False
    assert [(slot.unit_id, slot.role) for slot in evaluated.missing_slots] == [
        ("__missing_role__:causal_link", "causal_link")
    ]
    assert evaluated.reason == "missing causal answerability roles"


def test_fallback_allowed_only_for_lexical_or_evidence_candidate_gaps():
    allowed = ClosureRecord(
        closure_id="closure-allowed-fallback",
        claim_or_query_id="query-projects",
        pattern="single_fact",
        required_units=[{"unit_id": "l1-placeholder", "role": "evidence"}],
        missing_slots=[{"unit_id": "__missing__:predicate", "role": "lexical_predicate_missing_link"}],
    )
    blocked = ClosureRecord(
        closure_id="closure-blocked-fallback",
        claim_or_query_id="query-feedback-cause",
        pattern="causal_answerability",
        required_units=[{"unit_id": "l1-placeholder", "role": "evidence"}],
        missing_slots=[{"unit_id": "__missing_role__:causal_link", "role": "causal_link"}],
    )

    assert fallback_allowed_for_closure(allowed) is True
    assert fallback_allowed_for_closure(blocked) is False


def test_query_distinguishes_led_manage_from_led_to_cause():
    led_project = _l1_event(
        "l1-led-migration",
        surface="led",
        sense="lead/manage",
        operator="led_by",
        evidence_id="E-led-migration",
    )
    caused_change = _l1_event(
        "l1-feedback-led-to-change",
        surface="led to",
        sense="lead-to/cause",
        operator="caused_by",
        evidence_id="E-led-to-change",
    )
    plan = QuerySlotPlan(
        query_id="query-led-projects",
        intent="fact_lookup",
        target_level="L1",
        predicate_sense="lead/manage",
        canonical_operator="led_by",
    )

    result = execute_query(plan, [led_project, caused_change], [], [])

    assert result.matched_unit_ids == ["l1-led-migration"]
    assert result.required_evidence_ids == ["E-led-migration"]
    assert result.abstained is False


def test_query_matches_led_to_cause_when_causal_sense_is_requested():
    led_project = _l1_event(
        "l1-led-migration",
        surface="led",
        sense="lead/manage",
        operator="led_by",
        evidence_id="E-led-migration",
    )
    caused_change = _l1_event(
        "l1-feedback-led-to-change",
        surface="led to",
        sense="lead-to/cause",
        operator="caused_by",
        evidence_id="E-led-to-change",
    )
    plan = QuerySlotPlan(
        query_id="query-feedback-cause",
        intent="causal_how",
        target_level="L1",
        predicate_sense="lead-to/cause",
        canonical_operator="caused_by",
    )

    result = execute_query(plan, [led_project, caused_change], [], [])

    assert result.matched_unit_ids == ["l1-feedback-led-to-change"]
    assert result.required_evidence_ids == ["E-led-to-change"]
    assert result.abstained is False


def test_feedback_causal_answerability_abstains_without_causal_link_unit():
    feedback = _l1_event(
        "l1-feedback-observation",
        surface="feedback",
        sense="feedback-observation",
        operator="observed_by",
        evidence_id="E-feedback",
    )
    ui_change = _l1_event(
        "l1-ui-change",
        surface="improved",
        sense="change/improve",
        operator="changed_by",
        evidence_id="E-ui-change",
    )
    closure = ClosureRecord(
        closure_id="closure-feedback-cause",
        claim_or_query_id="query-feedback-cause",
        pattern="causal_answerability",
        required_units=[
            {"unit_id": "l1-feedback-observation", "role": "cause"},
            {"unit_id": "l1-ui-change", "role": "effect"},
        ],
    )
    plan = QuerySlotPlan(
        query_id="query-feedback-cause",
        intent="causal_how",
        target_level="L1",
        required_closure_pattern="causal_answerability",
        closure_id="closure-feedback-cause",
    )

    result = execute_query(plan, [feedback, ui_change], [], [closure])

    assert result.abstained is True
    assert result.closure_complete is False
    assert result.fallback_allowed is False
    assert result.missing_slots == ["__missing_role__:causal_link"]
    assert result.reason == "missing causal answerability roles"


def test_multi_session_query_requires_complete_evidence_closure():
    migration = _l1_event(
        "l1-led-migration",
        surface="led",
        sense="lead/manage",
        operator="led_by",
        evidence_id="E-led-migration",
    )
    dashboard = _l1_event(
        "l1-leading-dashboard",
        surface="leading",
        sense="lead/manage",
        operator="led_by",
        evidence_id="E-leading-dashboard",
    )
    closure = ClosureRecord(
        closure_id="closure-projects",
        claim_or_query_id="query-projects",
        pattern="multi_evidence_set",
        required_units=[
            {"unit_id": "l1-led-migration", "role": "evidence"},
            {"unit_id": "l1-leading-dashboard", "role": "evidence"},
        ],
    )
    plan = QuerySlotPlan(
        query_id="query-projects",
        intent="multi_evidence",
        target_level="both",
        predicate_sense="lead/manage",
        canonical_operator="led_by",
        required_closure_pattern="multi_evidence_set",
        closure_id="closure-projects",
    )

    result = execute_query(plan, [migration, dashboard], [], [closure])

    assert result.closure_complete is True
    assert result.matched_unit_ids == ["l1-led-migration", "l1-leading-dashboard"]
    assert result.required_evidence_ids == ["E-led-migration", "E-leading-dashboard"]
    assert result.abstained is False


def test_preference_current_query_returns_active_preference_not_superseded_one():
    old_pref = _l1_event(
        "l1-pref-old",
        surface="prefer",
        sense="prefer",
        operator="prefers",
        evidence_id="E-pref-old",
        lifecycle="superseded",
        roles=[RoleBinding(role="ARG0", entity_id="user", role_name="holder"), RoleBinding(role="ARG1", entity_id="tea", role_name="object")],
    )
    new_pref = _l1_event(
        "l1-pref-new",
        surface="prefer",
        sense="prefer",
        operator="prefers",
        evidence_id="E-pref-new",
        lifecycle="active",
        roles=[RoleBinding(role="ARG0", entity_id="user", role_name="holder"), RoleBinding(role="ARG1", entity_id="coffee", role_name="object")],
    )
    plan = QuerySlotPlan(
        query_id="query-current-preference",
        intent="preference_current",
        target_level="L1",
        canonical_operator="prefers",
        predicate_sense="prefer",
        lifecycle="active",
    )

    result = execute_query(plan, [old_pref, new_pref], [], [])

    assert result.matched_unit_ids == ["l1-pref-new"]
    assert result.required_evidence_ids == ["E-pref-new"]
    assert result.abstained is False
