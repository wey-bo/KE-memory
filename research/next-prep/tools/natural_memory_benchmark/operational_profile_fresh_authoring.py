"""Author the Phase C fresh-hidden dataset for the operational diagnostic profile.

Writes ``public``, ``authority`` and ``gold`` for the narrow operational
vocabulary (L1 ``add_ingredient``/``drink``/``prefer``, L2 ``prefer``). None of
it derives from fresh-v3's 24/18 vocabulary or from the misnamed
``...codex-gpt-operational-v1`` directory, both of which the preregistration
forbids reusing.

The cases are new prose written against the preregistered coverage: for every L1
operator a correct emission, a case that must be refused or abstained, a case
whose roles or entities are confusable, and a boundary case for modality,
polarity, time or lifecycle. The L2 side covers multi-evidence aggregation, a
wrong summary, cross-turn coreference and a critical false emission.

The author writes gold; the proposer never sees it. That separation is the whole
independence argument here, so the caller verifies it with
``assert_gold_not_exposed`` before any model call.
"""

from __future__ import annotations

import hashlib
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


L1Coverage = Literal[
    "correct_emission",
    "must_refuse_or_abstain",
    "confusable_roles_or_entities",
    "boundary_modality_polarity_time_or_lifecycle",
]

#: 一个标签有多确定，决定它能不能当硬门。
#:
#: ``indisputable``：任何合理读者都会同意，且判错会写下与原文相反或原文没有的
#: 事实。这类才可以进 critical false emission 硬门。
#:
#: ``convention``：作者的合理约定，但真实场景里未必成立。典型例子是"疑问句算
#: no_memory 还是 abstain"——问句确实没陈述持久事实，可是把"依据不足"与"本来
#: 无事可记"划在哪一侧是约定而非事实。这类只作为观测记录，不得作为硬门，也
#: 不得据此把模型"改绿"：那只会让实现去拟合我的约定。
LabelConfidence = Literal["indisputable", "convention"]
L2Coverage = Literal[
    "multi_evidence_aggregation",
    "wrong_summary",
    "cross_turn_coreference",
    "critical_false_emission",
]


def opaque_ref(prefix: str, value: str) -> str:
    """Mirror the scorer's own ref derivation so ids line up exactly."""
    digest = hashlib.sha256(f"typed-extractor-l1-v1:{value}".encode()).hexdigest()
    return f"{prefix}-{digest[:16]}"


class L1CaseBlueprint(StrictModel):
    """One authored L1 case: the prose, the public candidate, and the verdict."""

    knowledge_id: str = Field(min_length=1)
    coverage: L1Coverage
    canonical_operator: Literal["add_ingredient", "drink", "prefer"]
    predicate_sense: str = Field(min_length=1)
    kind: Literal["event", "preference"]
    user_text: str = Field(min_length=1)
    agent_text: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    predicate: str = Field(min_length=1)
    object: str | None = None
    #: 角色 -> 表面。程序据此生成 typed 期望，作者不手写 typed candidate。
    role_surfaces: tuple[tuple[str, str], ...] = Field(min_length=1)
    modality: Literal["actual", "planned", "requested"] = "actual"
    polarity: Literal["positive", "negative"] = "positive"
    valid_time: str | None = None
    expected_decision: Literal["emit_l1", "abstain", "no_memory"]
    #: 这个标签是不容争议的，还是作者约定。只有前者能进硬门。
    label_confidence: LabelConfidence
    #: 为何如此判定。写在数据里，评分失败时能直接对照作者意图，而不是事后推测。
    rationale: str = Field(min_length=1)


class L2CaseBlueprint(StrictModel):
    """One authored L2 case over two or more supporting L1 units."""

    knowledge_id: str = Field(min_length=1)
    coverage: L2Coverage
    canonical_operator: Literal["prefer"] = "prefer"
    predicate_sense: Literal["preference_theme"] = "preference_theme"
    turns: tuple[tuple[str, str], ...] = Field(min_length=2)
    statement: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    predicate: str = Field(min_length=1)
    object: str | None = None
    support_surface: str = Field(min_length=1)
    abstraction_method: Literal["preference_aggregation"] = "preference_aggregation"
    closure_pattern: Literal["multi_evidence_set"] = "multi_evidence_set"
    expected_decision: Literal["emit_l2", "abstain"]
    #: 这个标签是不容争议的，还是作者约定。只有前者能进硬门。
    label_confidence: LabelConfidence
    rationale: str = Field(min_length=1)


#: L1 蓝图：三个算子各覆盖四类情形，共 12 例。
L1_BLUEPRINTS: tuple[L1CaseBlueprint, ...] = (
    # --- prefer ---
    L1CaseBlueprint(
        knowledge_id="op-l1-prefer-correct",
        coverage="correct_emission",
        canonical_operator="prefer",
        predicate_sense="preference_theme",
        kind="preference",
        user_text="Coffee is preferred for the morning shift.",
        agent_text="Recorded.",
        statement="Coffee is preferred for the morning shift.",
        subject="the speaker",
        predicate="prefer",
        object="coffee",
        role_surfaces=(("theme", "Coffee"),),
        expected_decision="emit_l1",
        label_confidence="indisputable",
        rationale="A plain durable preference stated by the user in their own words.",
    ),
    L1CaseBlueprint(
        knowledge_id="op-l1-prefer-question",
        coverage="must_refuse_or_abstain",
        canonical_operator="prefer",
        predicate_sense="preference_theme",
        kind="preference",
        user_text="Which beverage is preferred here?",
        agent_text="I do not have that on record.",
        statement="The speaker asks which beverage is preferred.",
        subject="the speaker",
        predicate="prefer",
        object="beverage",
        role_surfaces=(("theme", "beverage"),),
        expected_decision="no_memory",
        label_confidence="convention",
        rationale=(
            "Not emitting is indisputable: the user expressed no preference, so "
            "emitting one would invent it. Which non-emission label applies is a "
            "convention — a reader could argue a question is 'nothing durable to "
            "keep' (no_memory) or 'insufficient basis' (abstain). Only the refusal "
            "to emit is gated; the choice between the two labels is reported."
        ),
    ),
    L1CaseBlueprint(
        knowledge_id="op-l1-prefer-confusable",
        coverage="confusable_roles_or_entities",
        canonical_operator="prefer",
        predicate_sense="preference_theme",
        kind="preference",
        user_text="Tea is preferred over coffee.",
        agent_text="Noted.",
        statement="Tea is preferred over coffee.",
        subject="the speaker",
        predicate="prefer",
        object="tea",
        role_surfaces=(("theme", "Tea"),),
        expected_decision="emit_l1",
        label_confidence="indisputable",
        rationale=(
            "Two beverages appear and only the first fills the theme role. Binding "
            "coffee would record the opposite preference."
        ),
    ),
    L1CaseBlueprint(
        knowledge_id="op-l1-prefer-negated",
        coverage="boundary_modality_polarity_time_or_lifecycle",
        canonical_operator="prefer",
        predicate_sense="preference_theme",
        kind="preference",
        user_text="Coffee is not preferred anymore.",
        agent_text="Understood.",
        statement="Coffee is not preferred anymore.",
        subject="the speaker",
        predicate="prefer",
        object="coffee",
        role_surfaces=(("theme", "Coffee"),),
        polarity="negative",
        expected_decision="emit_l1",
        label_confidence="indisputable",
        rationale=(
            "A denied preference is a fact worth keeping, and its polarity must be "
            "negative rather than dropped or inverted."
        ),
    ),
    # --- drink ---
    L1CaseBlueprint(
        knowledge_id="op-l1-drink-correct",
        coverage="correct_emission",
        canonical_operator="drink",
        predicate_sense="consume_beverage",
        kind="event",
        user_text="Coffee is drunk every morning.",
        agent_text="Logged.",
        statement="Coffee is drunk every morning.",
        subject="the speaker",
        predicate="drink",
        object="coffee",
        role_surfaces=(("theme", "Coffee"),),
        expected_decision="emit_l1",
        label_confidence="indisputable",
        rationale="A recurring consumption event stated explicitly.",
    ),
    L1CaseBlueprint(
        knowledge_id="op-l1-drink-hypothetical",
        coverage="must_refuse_or_abstain",
        canonical_operator="drink",
        predicate_sense="consume_beverage",
        kind="event",
        user_text="If the machine is fixed, coffee would be drunk again.",
        agent_text="I will note the condition.",
        statement="Coffee would be drunk again if the machine is fixed.",
        subject="the speaker",
        predicate="drink",
        object="coffee",
        role_surfaces=(("theme", "coffee"),),
        expected_decision="abstain",
        label_confidence="convention",
        rationale=(
            "Not recording this as something that happened is indisputable: the "
            "event is conditional and the policy authorizes only actual modality. "
            "Which non-emission label applies is a convention — a reader could "
            "argue the conditional carries nothing durable at all. Only the refusal "
            "to emit an actual event is gated."
        ),
    ),
    L1CaseBlueprint(
        knowledge_id="op-l1-drink-confusable",
        coverage="confusable_roles_or_entities",
        canonical_operator="drink",
        predicate_sense="consume_beverage",
        kind="event",
        user_text="Milk is drunk, not coffee.",
        agent_text="Noted.",
        statement="Milk is drunk.",
        subject="the speaker",
        predicate="drink",
        object="milk",
        role_surfaces=(("theme", "Milk"),),
        expected_decision="emit_l1",
        label_confidence="indisputable",
        rationale=(
            "The negation attaches to coffee, not to the drinking of milk. Binding "
            "coffee, or marking the whole claim negative, would both be wrong."
        ),
    ),
    L1CaseBlueprint(
        knowledge_id="op-l1-drink-dated",
        coverage="boundary_modality_polarity_time_or_lifecycle",
        canonical_operator="drink",
        predicate_sense="consume_beverage",
        kind="event",
        user_text="Coffee has been drunk daily since 2026-03-01.",
        agent_text="Recorded.",
        statement="Coffee has been drunk daily since 2026-03-01.",
        subject="the speaker",
        predicate="drink",
        object="coffee",
        role_surfaces=(("theme", "Coffee"),),
        valid_time="2026-03-01T00:00:00Z",
        expected_decision="emit_l1",
        label_confidence="indisputable",
        rationale=(
            "The date is part of what the fact says, so valid_time must carry it "
            "rather than be discarded."
        ),
    ),
    # --- add_ingredient ---
    L1CaseBlueprint(
        knowledge_id="op-l1-add-correct",
        coverage="correct_emission",
        canonical_operator="add_ingredient",
        predicate_sense="add_ingredient",
        kind="event",
        user_text="Milk is added to the coffee.",
        agent_text="Logged.",
        statement="Milk is added to the coffee.",
        subject="the speaker",
        predicate="add",
        object="milk",
        role_surfaces=(("theme", "Milk"), ("destination", "coffee")),
        expected_decision="emit_l1",
        label_confidence="indisputable",
        rationale=(
            "Both published roles are filled: milk is the theme, coffee the "
            "destination."
        ),
    ),
    L1CaseBlueprint(
        knowledge_id="op-l1-add-requested",
        coverage="must_refuse_or_abstain",
        canonical_operator="add_ingredient",
        predicate_sense="add_ingredient",
        kind="event",
        user_text="Please add milk to the coffee next time.",
        agent_text="I will remember the request.",
        statement="The speaker requests milk be added to the coffee.",
        subject="the speaker",
        predicate="add",
        object="milk",
        role_surfaces=(("theme", "milk"), ("destination", "coffee")),
        modality="requested",
        expected_decision="abstain",
        label_confidence="convention",
        rationale=(
            "Not recording this as an occurrence is indisputable: nothing has been "
            "added yet, so an actual event would assert something false. Which "
            "non-emission label applies is a convention, and a system that keeps "
            "requests as requested-modality facts would reasonably emit instead — "
            "which is why only the refusal to assert an actual event is gated."
        ),
    ),
    L1CaseBlueprint(
        knowledge_id="op-l1-add-confusable",
        coverage="confusable_roles_or_entities",
        canonical_operator="add_ingredient",
        predicate_sense="add_ingredient",
        kind="event",
        user_text="Coffee is added to the milk.",
        agent_text="Noted.",
        statement="Coffee is added to the milk.",
        subject="the speaker",
        predicate="add",
        object="coffee",
        role_surfaces=(("theme", "Coffee"), ("destination", "milk")),
        expected_decision="emit_l1",
        label_confidence="indisputable",
        rationale=(
            "The same two entities as the correct case with the roles reversed. "
            "Reusing the earlier binding would record the wrong direction."
        ),
    ),
    L1CaseBlueprint(
        knowledge_id="op-l1-add-nothing-durable",
        coverage="boundary_modality_polarity_time_or_lifecycle",
        canonical_operator="add_ingredient",
        predicate_sense="add_ingredient",
        kind="event",
        user_text="Thanks, that is all for now.",
        agent_text="You are welcome.",
        statement="The speaker closes the exchange.",
        subject="the speaker",
        predicate="add",
        object=None,
        role_surfaces=(("theme", "that"),),
        expected_decision="no_memory",
        label_confidence="convention",
        rationale=(
            "Not emitting is indisputable: no ingredient is named, so any "
            "add_ingredient fact would be fabricated. Calling it no_memory rather "
            "than abstain is the convention — here the two readings are closest, "
            "since 'nothing to keep' and 'no basis' coincide."
        ),
    ),
)

#: L2 蓝图：四类覆盖各一例。
L2_BLUEPRINTS: tuple[L2CaseBlueprint, ...] = (
    L2CaseBlueprint(
        knowledge_id="op-l2-aggregate",
        coverage="multi_evidence_aggregation",
        turns=(
            ("Coffee is preferred.", "Noted."),
            ("Coffee is drunk every morning.", "Logged."),
        ),
        statement="Coffee is the preferred beverage",
        subject="the speaker",
        predicate="prefer",
        object="coffee",
        support_surface="Coffee",
        expected_decision="emit_l2",
        label_confidence="indisputable",
        rationale=(
            "Two admitted facts about the same beverage jointly establish the "
            "preference profile."
        ),
    ),
    L2CaseBlueprint(
        knowledge_id="op-l2-wrong-summary",
        coverage="wrong_summary",
        turns=(
            ("Coffee is preferred.", "Noted."),
            ("Coffee is drunk every morning.", "Logged."),
        ),
        statement="Tea is the preferred beverage",
        subject="the speaker",
        predicate="prefer",
        object="tea",
        support_surface="Tea",
        expected_decision="abstain",
        label_confidence="indisputable",
        rationale=(
            "The summary names a beverage no support mentions. It must not be "
            "emitted just because the shape is valid."
        ),
    ),
    L2CaseBlueprint(
        knowledge_id="op-l2-coreference",
        coverage="cross_turn_coreference",
        turns=(
            ("Coffee is preferred.", "Noted."),
            ("It is drunk every morning.", "Logged."),
        ),
        statement="Coffee is the preferred beverage",
        subject="the speaker",
        predicate="prefer",
        object="coffee",
        support_surface="Coffee",
        expected_decision="emit_l2",
        label_confidence="convention",
        rationale=(
            "If the abstraction is emitted, its entity must resolve to the L1 "
            "support rather than to a new entity for the pronoun. Whether to emit "
            "at all is the convention: resolving 'it' across turns is a judgement, "
            "and a system that declines to resolve pronouns would reasonably "
            "abstain. So the entity binding is gated, the decision is reported."
        ),
    ),
    L2CaseBlueprint(
        knowledge_id="op-l2-critical-false-emission",
        coverage="critical_false_emission",
        turns=(
            ("Coffee is not preferred.", "Understood."),
            ("Tea is drunk every morning.", "Logged."),
        ),
        statement="Coffee is the preferred beverage",
        subject="the speaker",
        predicate="prefer",
        object="coffee",
        support_surface="Coffee",
        expected_decision="abstain",
        label_confidence="indisputable",
        rationale=(
            "The support denies the very preference the summary asserts. Emitting "
            "here is the critical false emission the gate must hold at zero."
        ),
    ),
)


def classify_decision_outcome(
    *,
    expected_decision: str,
    observed_decision: str,
    label_confidence: LabelConfidence,
) -> Literal[
    "match",
    "gated_violation",
    "convention_disagreement",
    "reported_mismatch",
]:
    """Say what a decision mismatch actually is, before it reaches a gate.

    The existing scorer counts any emission against a non-emission gold as a
    critical false emission. That is right for "the model wrote a fact the text
    does not support", and wrong for "the model chose abstain where the author
    wrote no_memory" — the second is a disagreement about a convention, and
    gating on it would make the model conform to the author's taxonomy rather
    than to the evidence.

    So the split is by what the disagreement costs:

    * emitting where the author refused to emit is a ``gated_violation``
      regardless of label confidence: a fabricated fact is a real defect.
    * disagreeing only about *which* non-emission label applies is a
      ``convention_disagreement``, reported and never gated.
    * anything else on a convention label is reported, not gated.
    """
    if expected_decision == observed_decision:
        return "match"
    emitting = observed_decision in ("emit_l1", "emit_l2")
    expected_emitting = expected_decision in ("emit_l1", "emit_l2")
    if emitting and not expected_emitting:
        # 写下原文不支持的事实：无论标签确定度都是真实缺陷。
        return "gated_violation"
    if not emitting and not expected_emitting:
        # 两种非产出标签之间的分歧：这正是"疑问句算哪一类"这种约定问题。
        return "convention_disagreement"
    if label_confidence == "indisputable":
        return "gated_violation"
    return "reported_mismatch"


def classify_emission_outcome(
    *,
    expected_decision: str,
    observed_decision: str,
    observed_modality: str | None,
    policy: Any,
) -> Literal[
    "match",
    "raw_semantic_false_emission",
    "policy_scope_disagreement",
    "reported_mismatch",
]:
    """Classify an emission by what the model actually wrote.

    Comparing only "gold refused, model emitted" put two unlike errors under one
    number. Writing a conditional as ``actual`` asserts an occurrence the text
    does not — a real defect. Writing a request as ``requested`` reports the text
    faithfully and claims no occurrence; it conflicts with the diagnostic write
    scope, not with the evidence.

    Separating them loosens nothing. An unauthorized modality still fails
    admission and materialization, so it still cannot reach authoritative
    memory. What changes is how the failure is classified, not what may be
    written.
    """
    authorized = {item.modality for item in policy.modality_time_policies}
    if expected_decision == observed_decision:
        return "match"
    emitting = observed_decision in ("emit_l1", "emit_l2")
    expected_emitting = expected_decision in ("emit_l1", "emit_l2")
    if emitting and not expected_emitting:
        if observed_modality is not None and observed_modality not in authorized:
            # 未授权模态：模型没有声称事件已发生，落库仍会被拒。
            return "policy_scope_disagreement"
        return "raw_semantic_false_emission"
    return "reported_mismatch"


def label_confidence_report() -> dict[str, Any]:
    """Publish which labels are gated and which are only observed."""
    gated = [
        item.knowledge_id
        for item in (*L1_BLUEPRINTS, *L2_BLUEPRINTS)
        if item.label_confidence == "indisputable"
    ]
    convention = [
        item.knowledge_id
        for item in (*L1_BLUEPRINTS, *L2_BLUEPRINTS)
        if item.label_confidence == "convention"
    ]
    return {
        "indisputable_case_ids": sorted(gated),
        "convention_case_ids": sorted(convention),
        "indisputable_count": len(gated),
        "convention_count": len(convention),
        "gate_counts_only_indisputable_violations": True,
        "convention_labels_are_reported_not_gated": True,
    }


def coverage_report() -> dict[str, Any]:
    """State the authored coverage so the preregistered requirement is checkable."""
    l1: dict[str, list[str]] = {}
    for item in L1_BLUEPRINTS:
        l1.setdefault(item.canonical_operator, []).append(item.coverage)
    return {
        "l1_by_operator": {key: sorted(value) for key, value in sorted(l1.items())},
        "l1_case_count": len(L1_BLUEPRINTS),
        "l2_coverage": sorted(item.coverage for item in L2_BLUEPRINTS),
        "l2_case_count": len(L2_BLUEPRINTS),
        "l1_decision_counts": {
            decision: sum(
                1 for item in L1_BLUEPRINTS if item.expected_decision == decision
            )
            for decision in ("emit_l1", "abstain", "no_memory")
        },
        "l2_decision_counts": {
            decision: sum(
                1 for item in L2_BLUEPRINTS if item.expected_decision == decision
            )
            for decision in ("emit_l2", "abstain")
        },
    }
