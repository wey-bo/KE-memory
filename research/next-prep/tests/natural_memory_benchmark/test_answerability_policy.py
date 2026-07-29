from __future__ import annotations

from tools.natural_memory_benchmark.answerability_policy import assess_answerability


def test_causal_gate_blocks_topic_overlap_without_relation_detail():
    public_item = {
        "benchmark": "beam",
        "item_id": "I-causal-overlap",
        "question": "How did the user feedback influence the UI/UX improvements I made before the public launch?",
        "slice_group": "abstention",
    }
    evidence_units = [
        {
            "unit_id": "E-user-plan",
            "text": "I want to make sure the UI/UX is improved based on user feedback before the public launch.",
        },
        {
            "unit_id": "E-generic-review",
            "text": "Let's review the current implementation and suggest improvements for UI/UX and security.",
        },
    ]

    decision = assess_answerability(public_item, evidence_units)

    assert decision.answerable is False
    assert decision.decision == "blocked"
    assert decision.reason == "causal_relation_missing"
    assert decision.metadata()["answerability_policy"] == "causal_gate_v1"


def test_causal_gate_allows_explicit_feedback_to_change_relation():
    public_item = {
        "benchmark": "beam",
        "item_id": "I-causal-supported",
        "question": "How did the user feedback influence the UI/UX improvements before launch?",
        "slice_group": "knowledge_update",
    }
    evidence_units = [
        {
            "unit_id": "E-explicit-cause",
            "text": "User feedback showed that beta testers could not find checkout, so I simplified the checkout labels before launch.",
        }
    ]

    decision = assess_answerability(public_item, evidence_units)

    assert decision.answerable is True
    assert decision.decision == "supported"
    assert decision.reason == "causal_support_present"
    assert "explicit_causal_marker" in decision.supporting_cues


def test_non_causal_questions_do_not_use_causal_gate():
    public_item = {
        "benchmark": "locomo",
        "item_id": "I-fact",
        "question": "What status did Alice set for order 42?",
        "slice_group": "role_binding",
    }
    evidence_units = [
        {
            "unit_id": "E-alice-order",
            "text": "Alice set order 42 to shipped.",
        }
    ]

    decision = assess_answerability(public_item, evidence_units)

    assert decision.answerable is True
    assert decision.decision == "not_applicable"
    assert decision.reason == "not_causal_question"


def test_how_many_led_question_is_not_causal():
    public_item = {
        "benchmark": "longmemeval",
        "item_id": "I-led-projects",
        "question": "How many projects have I led or am currently leading?",
        "slice_group": "multi-session",
    }
    evidence_units = [
        {
            "unit_id": "E-project",
            "text": "I led the migration project and am currently leading the dashboard project.",
        }
    ]

    decision = assess_answerability(public_item, evidence_units)

    assert decision.answerable is True
    assert decision.decision == "not_applicable"
    assert decision.reason == "not_causal_question"
