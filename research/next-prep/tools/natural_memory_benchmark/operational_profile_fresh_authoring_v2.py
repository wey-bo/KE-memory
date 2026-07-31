"""Phase C hidden-v2 cases: new wording, new situations, new gold.

Required because attempt 1 failed on v1 and AGENTS.md forbids tuning against a
hidden set and then re-running it. Every sentence here is new; none is a
rephrasing of a v1 case, and in particular none reuses the conditional sentence
whose failure drove the modality repair. Reusing it would test the repair against
the example that produced it.

Coverage matches the frozen preregistration: for each L1 operator a correct
emission, a case that must be refused or abstained, a confusable case and a
boundary case; for L2 aggregation, a wrong summary, cross-turn coreference and a
critical false emission. Label confidence is carried per case, so the gate still
counts only fabrication and indisputable misses.

The conditional cases here deliberately use phrasings the repair was *not*
developed against, so v2 measures whether the fix generalizes rather than whether
it memorized.
"""

from __future__ import annotations

from typing import Any

from .operational_profile_fresh_authoring import (
    L1CaseBlueprint,
    L2CaseBlueprint,
)

DATASET_ID = "operational-profile-fresh-hidden-v2"

L1_BLUEPRINTS_V2: tuple[L1CaseBlueprint, ...] = (
    # --- prefer ---
    L1CaseBlueprint(
        knowledge_id="op2-l1-prefer-correct",
        coverage="correct_emission",
        canonical_operator="prefer",
        predicate_sense="preference_theme",
        kind="preference",
        user_text="Tea is preferred during long reviews.",
        agent_text="Recorded.",
        statement="Tea is preferred during long reviews.",
        subject="the speaker",
        predicate="prefer",
        object="tea",
        role_surfaces=(("theme", "Tea"),),
        expected_decision="emit_l1",
        label_confidence="indisputable",
        rationale="A durable preference stated plainly in the user's own words.",
    ),
    L1CaseBlueprint(
        knowledge_id="op2-l1-prefer-someone-else",
        coverage="must_refuse_or_abstain",
        canonical_operator="prefer",
        predicate_sense="preference_theme",
        kind="preference",
        user_text="My colleague says milk is preferred.",
        agent_text="Noted as hearsay.",
        statement="A colleague reports that milk is preferred.",
        subject="the colleague",
        predicate="prefer",
        object="milk",
        role_surfaces=(("theme", "milk"),),
        expected_decision="abstain",
        label_confidence="convention",
        rationale=(
            "Not recording this as the user's own preference is indisputable: the "
            "sentence attributes it to someone else. Which non-emission label "
            "applies is a convention, and a system that models third-party "
            "preferences would reasonably emit with a different subject."
        ),
    ),
    L1CaseBlueprint(
        knowledge_id="op2-l1-prefer-confusable",
        coverage="confusable_roles_or_entities",
        canonical_operator="prefer",
        predicate_sense="preference_theme",
        kind="preference",
        user_text="Rather than milk, coffee is preferred.",
        agent_text="Understood.",
        statement="Coffee is preferred rather than milk.",
        subject="the speaker",
        predicate="prefer",
        object="coffee",
        role_surfaces=(("theme", "coffee"),),
        expected_decision="emit_l1",
        label_confidence="indisputable",
        rationale=(
            "The rejected alternative appears first this time, so binding the "
            "leading entity would record the opposite preference."
        ),
    ),
    L1CaseBlueprint(
        knowledge_id="op2-l1-prefer-no-longer",
        coverage="boundary_modality_polarity_time_or_lifecycle",
        canonical_operator="prefer",
        predicate_sense="preference_theme",
        kind="preference",
        user_text="Tea is no longer preferred.",
        agent_text="Recorded.",
        statement="Tea is no longer preferred.",
        subject="the speaker",
        predicate="prefer",
        object="tea",
        role_surfaces=(("theme", "Tea"),),
        polarity="negative",
        expected_decision="emit_l1",
        label_confidence="indisputable",
        rationale=(
            "A withdrawn preference is a fact worth keeping and its polarity must "
            "be negative. 'No longer' rather than 'not', so the negation cue "
            "differs from the v1 case."
        ),
    ),
    # --- drink ---
    L1CaseBlueprint(
        knowledge_id="op2-l1-drink-correct",
        coverage="correct_emission",
        canonical_operator="drink",
        predicate_sense="consume_beverage",
        kind="event",
        user_text="Tea is drunk after every deployment.",
        agent_text="Logged.",
        statement="Tea is drunk after every deployment.",
        subject="the speaker",
        predicate="drink",
        object="tea",
        role_surfaces=(("theme", "Tea"),),
        expected_decision="emit_l1",
        label_confidence="indisputable",
        rationale="A recurring consumption event stated explicitly.",
    ),
    L1CaseBlueprint(
        knowledge_id="op2-l1-drink-conditional",
        coverage="must_refuse_or_abstain",
        canonical_operator="drink",
        predicate_sense="consume_beverage",
        kind="event",
        user_text="Whenever the kettle is free, tea is drunk at noon.",
        agent_text="I will note the dependency.",
        statement="Tea is drunk at noon whenever the kettle is free.",
        subject="the speaker",
        predicate="drink",
        object="tea",
        role_surfaces=(("theme", "tea"),),
        expected_decision="abstain",
        label_confidence="convention",
        rationale=(
            "Not recording this as an actual occurrence is indisputable: the "
            "drinking is contingent. The wording is 'whenever', which the modality "
            "repair was not developed against, so this measures whether the fix "
            "generalizes. Which non-emission label applies stays a convention."
        ),
    ),
    L1CaseBlueprint(
        knowledge_id="op2-l1-drink-confusable",
        coverage="confusable_roles_or_entities",
        canonical_operator="drink",
        predicate_sense="consume_beverage",
        kind="event",
        user_text="Coffee is drunk while milk is only stirred in.",
        agent_text="Noted.",
        statement="Coffee is drunk.",
        subject="the speaker",
        predicate="drink",
        object="coffee",
        role_surfaces=(("theme", "Coffee"),),
        expected_decision="emit_l1",
        label_confidence="indisputable",
        rationale=(
            "Two beverages appear and only coffee is drunk. Binding milk would "
            "record an event the sentence explicitly assigns a different verb."
        ),
    ),
    L1CaseBlueprint(
        knowledge_id="op2-l1-drink-dated",
        coverage="boundary_modality_polarity_time_or_lifecycle",
        canonical_operator="drink",
        predicate_sense="consume_beverage",
        kind="event",
        user_text="Tea has been drunk at noon since 2026-05-04.",
        agent_text="Recorded.",
        statement="Tea has been drunk at noon since 2026-05-04.",
        subject="the speaker",
        predicate="drink",
        object="tea",
        role_surfaces=(("theme", "Tea"),),
        valid_time="2026-05-04T00:00:00Z",
        expected_decision="emit_l1",
        label_confidence="indisputable",
        rationale=(
            "The start date is part of the fact, so valid_time must carry it. A "
            "different date and beverage from the v1 case."
        ),
    ),
    # --- add_ingredient ---
    L1CaseBlueprint(
        knowledge_id="op2-l1-add-correct",
        coverage="correct_emission",
        canonical_operator="add_ingredient",
        predicate_sense="add_ingredient",
        kind="event",
        user_text="Milk is added to the tea.",
        agent_text="Logged.",
        statement="Milk is added to the tea.",
        subject="the speaker",
        predicate="add",
        object="milk",
        role_surfaces=(("theme", "Milk"), ("destination", "tea")),
        expected_decision="emit_l1",
        label_confidence="indisputable",
        rationale="Both published roles are filled, with tea as the destination.",
    ),
    L1CaseBlueprint(
        knowledge_id="op2-l1-add-planned",
        coverage="must_refuse_or_abstain",
        canonical_operator="add_ingredient",
        predicate_sense="add_ingredient",
        kind="event",
        user_text="Milk will be added to the tea tomorrow.",
        agent_text="I will keep that in mind.",
        statement="Milk will be added to the tea tomorrow.",
        subject="the speaker",
        predicate="add",
        object="milk",
        role_surfaces=(("theme", "Milk"), ("destination", "tea")),
        expected_decision="abstain",
        label_confidence="convention",
        rationale=(
            "Not recording a future action as an occurrence is indisputable. This "
            "is a plan rather than the v1 request, so it probes the same boundary "
            "from a different direction. Which non-emission label applies, and "
            "whether planned facts belong in memory at all, stay open."
        ),
    ),
    L1CaseBlueprint(
        knowledge_id="op2-l1-add-confusable",
        coverage="confusable_roles_or_entities",
        canonical_operator="add_ingredient",
        predicate_sense="add_ingredient",
        kind="event",
        user_text="Into the milk, tea is added.",
        agent_text="Noted.",
        statement="Tea is added to the milk.",
        subject="the speaker",
        predicate="add",
        object="tea",
        role_surfaces=(("theme", "tea"), ("destination", "milk")),
        expected_decision="emit_l1",
        label_confidence="indisputable",
        rationale=(
            "The destination is stated before the theme, so following surface "
            "order would reverse the two roles."
        ),
    ),
    L1CaseBlueprint(
        knowledge_id="op2-l1-add-greeting",
        coverage="boundary_modality_polarity_time_or_lifecycle",
        canonical_operator="add_ingredient",
        predicate_sense="add_ingredient",
        kind="event",
        user_text="Good morning, anything new to add?",
        agent_text="Nothing new.",
        statement="The speaker opens the exchange.",
        subject="the speaker",
        predicate="add",
        object=None,
        role_surfaces=(("theme", "anything"),),
        expected_decision="no_memory",
        label_confidence="convention",
        rationale=(
            "Not emitting is indisputable: no ingredient is named, so any "
            "add_ingredient fact would be fabricated. The word 'add' appears, "
            "which is exactly the trap — a cue match is not a fact."
        ),
    ),
)

L2_BLUEPRINTS_V2: tuple[L2CaseBlueprint, ...] = (
    L2CaseBlueprint(
        knowledge_id="op2-l2-aggregate",
        coverage="multi_evidence_aggregation",
        turns=(
            ("Tea is preferred.", "Noted."),
            ("Tea is drunk after every deployment.", "Logged."),
        ),
        statement="Tea is the preferred beverage",
        subject="the speaker",
        predicate="prefer",
        object="tea",
        support_surface="Tea",
        expected_decision="emit_l2",
        label_confidence="indisputable",
        rationale=(
            "Two admitted facts about the same beverage jointly establish the "
            "preference profile."
        ),
    ),
    L2CaseBlueprint(
        knowledge_id="op2-l2-wrong-summary",
        coverage="wrong_summary",
        turns=(
            ("Tea is preferred.", "Noted."),
            ("Tea is drunk after every deployment.", "Logged."),
        ),
        statement="Milk is the preferred beverage",
        subject="the speaker",
        predicate="prefer",
        object="milk",
        support_surface="Milk",
        expected_decision="abstain",
        label_confidence="indisputable",
        rationale=(
            "The summary names a beverage no support mentions, so it must not be "
            "emitted merely because its shape is valid."
        ),
    ),
    L2CaseBlueprint(
        knowledge_id="op2-l2-coreference",
        coverage="cross_turn_coreference",
        turns=(
            ("Tea is preferred.", "Noted."),
            ("That one is drunk at noon.", "Logged."),
        ),
        statement="Tea is the preferred beverage",
        subject="the speaker",
        predicate="prefer",
        object="tea",
        support_surface="Tea",
        expected_decision="emit_l2",
        label_confidence="convention",
        rationale=(
            "If emitted, the entity must resolve to the L1 support rather than to "
            "a new entity for 'that one'. Whether to resolve the reference at all "
            "remains a judgement, so the decision is reported and the binding is "
            "gated."
        ),
    ),
    L2CaseBlueprint(
        knowledge_id="op2-l2-critical-false-emission",
        coverage="critical_false_emission",
        turns=(
            ("Tea is no longer preferred.", "Understood."),
            ("Coffee is drunk at noon.", "Logged."),
        ),
        statement="Tea is the preferred beverage",
        subject="the speaker",
        predicate="prefer",
        object="tea",
        support_surface="Tea",
        expected_decision="abstain",
        label_confidence="indisputable",
        rationale=(
            "The support withdraws the very preference the summary asserts. "
            "Emitting here is the critical false emission the gate holds at zero."
        ),
    ),
)


def coverage_report_v2() -> dict[str, Any]:
    """State v2's authored coverage for checking against the preregistration."""
    l1: dict[str, list[str]] = {}
    for item in L1_BLUEPRINTS_V2:
        l1.setdefault(item.canonical_operator, []).append(item.coverage)
    return {
        "dataset_id": DATASET_ID,
        "l1_by_operator": {key: sorted(value) for key, value in sorted(l1.items())},
        "l1_case_count": len(L1_BLUEPRINTS_V2),
        "l2_coverage": sorted(item.coverage for item in L2_BLUEPRINTS_V2),
        "l2_case_count": len(L2_BLUEPRINTS_V2),
        "l1_decision_counts": {
            decision: sum(
                1 for item in L1_BLUEPRINTS_V2 if item.expected_decision == decision
            )
            for decision in ("emit_l1", "abstain", "no_memory")
        },
        "l2_decision_counts": {
            decision: sum(
                1 for item in L2_BLUEPRINTS_V2 if item.expected_decision == decision
            )
            for decision in ("emit_l2", "abstain")
        },
    }
