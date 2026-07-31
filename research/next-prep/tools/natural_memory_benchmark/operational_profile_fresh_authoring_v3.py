"""Phase C hidden-v3 cases: new sentences again, for attempt 3.

Needed because the prompt diagnosis replayed hidden-v2, which burns it for
qualification. Nothing here reuses a v1 or v2 sentence or knowledge id.

The habitual-conditional family is represented deliberately, because that is the
class attempt 2 failed on and the class the case-independence repair targets. The
wording is new — "each time", "any morning that", "on days when" — so attempt 3
measures whether the repair generalizes rather than whether it matched the two
phrasings already seen.

Coverage matches the frozen preregistration, and label confidence is carried per
case so the gate still counts only fabrication and indisputable misses.
"""

from __future__ import annotations

from typing import Any

from .operational_profile_fresh_authoring import (
    L1CaseBlueprint,
    L2CaseBlueprint,
)

DATASET_ID = "operational-profile-fresh-hidden-v3"

L1_BLUEPRINTS_V3: tuple[L1CaseBlueprint, ...] = (
    # --- prefer ---
    L1CaseBlueprint(
        knowledge_id="op3-l1-prefer-correct",
        coverage="correct_emission",
        canonical_operator="prefer",
        predicate_sense="preference_theme",
        kind="preference",
        user_text="Milk is preferred with breakfast.",
        agent_text="Recorded.",
        statement="Milk is preferred with breakfast.",
        subject="the speaker",
        predicate="prefer",
        object="milk",
        role_surfaces=(("theme", "Milk"),),
        expected_decision="emit_l1",
        label_confidence="indisputable",
        rationale="A durable preference stated plainly by the user.",
    ),
    L1CaseBlueprint(
        knowledge_id="op3-l1-prefer-hypothetical",
        coverage="must_refuse_or_abstain",
        canonical_operator="prefer",
        predicate_sense="preference_theme",
        kind="preference",
        user_text="On days when the tea runs out, coffee is preferred.",
        agent_text="I will note the dependency.",
        statement="Coffee is preferred on days when the tea runs out.",
        subject="the speaker",
        predicate="prefer",
        object="coffee",
        role_surfaces=(("theme", "coffee"),),
        expected_decision="abstain",
        label_confidence="convention",
        rationale=(
            "Not recording an unconditional preference is indisputable: it holds "
            "only on those days. The phrasing 'on days when' is new, so this tests "
            "whether the case-independence repair generalizes. Which non-emission "
            "label applies stays a convention."
        ),
    ),
    L1CaseBlueprint(
        knowledge_id="op3-l1-prefer-confusable",
        coverage="confusable_roles_or_entities",
        canonical_operator="prefer",
        predicate_sense="preference_theme",
        kind="preference",
        user_text="Coffee, not tea, is preferred.",
        agent_text="Understood.",
        statement="Coffee is preferred.",
        subject="the speaker",
        predicate="prefer",
        object="coffee",
        role_surfaces=(("theme", "Coffee"),),
        expected_decision="emit_l1",
        label_confidence="indisputable",
        rationale=(
            "The negation sits in an interposed clause and rejects tea, not the "
            "preference. Marking the whole claim negative, or binding tea, would "
            "each record something the sentence denies."
        ),
    ),
    L1CaseBlueprint(
        knowledge_id="op3-l1-prefer-dated",
        coverage="boundary_modality_polarity_time_or_lifecycle",
        canonical_operator="prefer",
        predicate_sense="preference_theme",
        kind="preference",
        user_text="Milk has been preferred since 2026-06-11.",
        agent_text="Recorded.",
        statement="Milk has been preferred since 2026-06-11.",
        subject="the speaker",
        predicate="prefer",
        object="milk",
        role_surfaces=(("theme", "Milk"),),
        valid_time="2026-06-11T00:00:00Z",
        expected_decision="emit_l1",
        label_confidence="indisputable",
        rationale=(
            "A dated preference rather than a dated event, so valid_time must "
            "carry the date on the preference path too."
        ),
    ),
    # --- drink ---
    L1CaseBlueprint(
        knowledge_id="op3-l1-drink-correct",
        coverage="correct_emission",
        canonical_operator="drink",
        predicate_sense="consume_beverage",
        kind="event",
        user_text="Milk is drunk before bed.",
        agent_text="Logged.",
        statement="Milk is drunk before bed.",
        subject="the speaker",
        predicate="drink",
        object="milk",
        role_surfaces=(("theme", "Milk"),),
        expected_decision="emit_l1",
        label_confidence="indisputable",
        rationale="A recurring consumption event stated explicitly.",
    ),
    L1CaseBlueprint(
        knowledge_id="op3-l1-drink-habitual-conditional",
        coverage="must_refuse_or_abstain",
        canonical_operator="drink",
        predicate_sense="consume_beverage",
        kind="event",
        user_text="Each time the machine is refilled, coffee is drunk at once.",
        agent_text="I will note the trigger.",
        statement="Coffee is drunk each time the machine is refilled.",
        subject="the speaker",
        predicate="drink",
        object="coffee",
        role_surfaces=(("theme", "coffee"),),
        expected_decision="abstain",
        label_confidence="convention",
        rationale=(
            "This is the exact class attempt 2 failed on: a habitual conditional "
            "reads like a routine fact. 'Each time' is a new phrasing, so an "
            "emission here would show the repair did not generalize."
        ),
    ),
    L1CaseBlueprint(
        knowledge_id="op3-l1-drink-confusable",
        coverage="confusable_roles_or_entities",
        canonical_operator="drink",
        predicate_sense="consume_beverage",
        kind="event",
        user_text="Before the tea arrives, coffee is drunk.",
        agent_text="Noted.",
        statement="Coffee is drunk.",
        subject="the speaker",
        predicate="drink",
        object="coffee",
        role_surfaces=(("theme", "coffee"),),
        expected_decision="emit_l1",
        label_confidence="indisputable",
        rationale=(
            "'Before' is temporal, not conditional, so the drinking is established. "
            "Refusing this would show the conditional guard over-reaching, and "
            "binding tea would pick the wrong entity."
        ),
    ),
    L1CaseBlueprint(
        knowledge_id="op3-l1-drink-negated",
        coverage="boundary_modality_polarity_time_or_lifecycle",
        canonical_operator="drink",
        predicate_sense="consume_beverage",
        kind="event",
        user_text="Coffee is never drunk after six.",
        agent_text="Recorded.",
        statement="Coffee is never drunk after six.",
        subject="the speaker",
        predicate="drink",
        object="coffee",
        role_surfaces=(("theme", "Coffee"),),
        polarity="negative",
        expected_decision="emit_l1",
        label_confidence="indisputable",
        rationale=(
            "A standing negative habit is a fact worth keeping, and 'never' must "
            "produce negative polarity rather than a dropped or inverted claim."
        ),
    ),
    # --- add_ingredient ---
    L1CaseBlueprint(
        knowledge_id="op3-l1-add-correct",
        coverage="correct_emission",
        canonical_operator="add_ingredient",
        predicate_sense="add_ingredient",
        kind="event",
        user_text="Milk is added to the coffee each morning.",
        agent_text="Logged.",
        statement="Milk is added to the coffee each morning.",
        subject="the speaker",
        predicate="add",
        object="milk",
        role_surfaces=(("theme", "Milk"), ("destination", "coffee")),
        expected_decision="emit_l1",
        label_confidence="indisputable",
        rationale=(
            "Both published roles are filled. 'Each morning' is a frequency, not a "
            "condition, so this must still be admitted."
        ),
    ),
    L1CaseBlueprint(
        knowledge_id="op3-l1-add-conditional",
        coverage="must_refuse_or_abstain",
        canonical_operator="add_ingredient",
        predicate_sense="add_ingredient",
        kind="event",
        user_text="Any morning that milk is left, it is added to the coffee.",
        agent_text="I will note the dependency.",
        statement="Milk is added to the coffee on any morning that milk is left.",
        subject="the speaker",
        predicate="add",
        object="milk",
        role_surfaces=(("theme", "milk"), ("destination", "coffee")),
        expected_decision="abstain",
        label_confidence="convention",
        rationale=(
            "'Any morning that' is a conditional in disguise, and a third new "
            "phrasing for the same class. Recording it as an occurrence asserts "
            "something conditional on milk being left."
        ),
    ),
    L1CaseBlueprint(
        knowledge_id="op3-l1-add-confusable",
        coverage="confusable_roles_or_entities",
        canonical_operator="add_ingredient",
        predicate_sense="add_ingredient",
        kind="event",
        user_text="The tea receives milk, not the other way around.",
        agent_text="Noted.",
        statement="Milk is added to the tea.",
        subject="the speaker",
        predicate="add",
        object="milk",
        role_surfaces=(("theme", "milk"), ("destination", "tea")),
        expected_decision="emit_l1",
        label_confidence="indisputable",
        rationale=(
            "The direction is stated by 'receives' rather than by word order, and "
            "the trailing clause warns against reversing it."
        ),
    ),
    L1CaseBlueprint(
        knowledge_id="op3-l1-add-question",
        coverage="boundary_modality_polarity_time_or_lifecycle",
        canonical_operator="add_ingredient",
        predicate_sense="add_ingredient",
        kind="event",
        user_text="Should milk be added to the coffee?",
        agent_text="That is up to you.",
        statement="The speaker asks whether milk should be added to the coffee.",
        subject="the speaker",
        predicate="add",
        object="milk",
        role_surfaces=(("theme", "milk"), ("destination", "coffee")),
        expected_decision="no_memory",
        label_confidence="convention",
        rationale=(
            "Not emitting is indisputable: a question asserts nothing. It opens "
            "with 'Should', which is also a conditional marker, so this checks that "
            "a question is not misread as a conditional statement."
        ),
    ),
)

L2_BLUEPRINTS_V3: tuple[L2CaseBlueprint, ...] = (
    L2CaseBlueprint(
        knowledge_id="op3-l2-aggregate",
        coverage="multi_evidence_aggregation",
        turns=(
            ("Milk is preferred.", "Noted."),
            ("Milk is drunk before bed.", "Logged."),
        ),
        statement="Milk is the preferred beverage",
        subject="the speaker",
        predicate="prefer",
        object="milk",
        support_surface="Milk",
        expected_decision="emit_l2",
        label_confidence="indisputable",
        rationale=(
            "Two admitted facts about the same beverage jointly establish the "
            "preference profile."
        ),
    ),
    L2CaseBlueprint(
        knowledge_id="op3-l2-wrong-summary",
        coverage="wrong_summary",
        turns=(
            ("Milk is preferred.", "Noted."),
            ("Milk is drunk before bed.", "Logged."),
        ),
        statement="Coffee is the preferred beverage",
        subject="the speaker",
        predicate="prefer",
        object="coffee",
        support_surface="Coffee",
        expected_decision="abstain",
        label_confidence="indisputable",
        rationale=(
            "The summary names a beverage no support mentions, so a valid shape is "
            "not sufficient reason to emit."
        ),
    ),
    L2CaseBlueprint(
        knowledge_id="op3-l2-coreference",
        coverage="cross_turn_coreference",
        turns=(
            ("Milk is preferred.", "Noted."),
            ("The same drink is taken before bed.", "Logged."),
        ),
        statement="Milk is the preferred beverage",
        subject="the speaker",
        predicate="prefer",
        object="milk",
        support_surface="Milk",
        expected_decision="emit_l2",
        label_confidence="convention",
        rationale=(
            "If emitted, the entity must resolve to the L1 support rather than to a "
            "new entity for 'the same one'. Whether to resolve at all remains a "
            "judgement, so the decision is reported and the binding is gated."
        ),
    ),
    L2CaseBlueprint(
        knowledge_id="op3-l2-critical-false-emission",
        coverage="critical_false_emission",
        turns=(
            ("Milk is never drunk before bed.", "Understood."),
            ("Coffee is drunk mid-afternoon.", "Logged."),
        ),
        statement="Milk is the preferred beverage",
        subject="the speaker",
        predicate="prefer",
        object="milk",
        support_surface="Milk",
        expected_decision="abstain",
        label_confidence="indisputable",
        rationale=(
            "The support denies the habit the summary builds on. Emitting here is "
            "the critical false emission the gate holds at zero."
        ),
    ),
)


def coverage_report_v3() -> dict[str, Any]:
    """State v3's authored coverage for checking against the preregistration."""
    l1: dict[str, list[str]] = {}
    for item in L1_BLUEPRINTS_V3:
        l1.setdefault(item.canonical_operator, []).append(item.coverage)
    return {
        "dataset_id": DATASET_ID,
        "l1_by_operator": {key: sorted(value) for key, value in sorted(l1.items())},
        "l1_case_count": len(L1_BLUEPRINTS_V3),
        "l2_coverage": sorted(item.coverage for item in L2_BLUEPRINTS_V3),
        "l2_case_count": len(L2_BLUEPRINTS_V3),
        "l1_decision_counts": {
            decision: sum(
                1 for item in L1_BLUEPRINTS_V3 if item.expected_decision == decision
            )
            for decision in ("emit_l1", "abstain", "no_memory")
        },
        "l2_decision_counts": {
            decision: sum(
                1 for item in L2_BLUEPRINTS_V3 if item.expected_decision == decision
            )
            for decision in ("emit_l2", "abstain")
        },
    }
