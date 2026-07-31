"""一句条件句不得被记成已经发生的事实。

attempt 1 的真实缺陷：原文 "If the machine is fixed, coffee would be drunk
again"，提案以 ``modality=actual`` 产出。这断言了原文没有说的事情——在任何标签
分类法下都是错的，与 requested 那一例性质不同。

这里在**新的 dev 数据**上复现该错误，并且修的是通用的条件/模态识别，不为那句
hidden 原文写特例。同时必须守住反面：带条件词的句子并非一律不可记录，
"Coffee is preferred, if that matters" 里的条件并不作用于偏好本身，把它一并
拒掉会造出新的假拒绝。
"""

from __future__ import annotations

import pytest

from tools.natural_memory_benchmark.e2e_openai_producers import (
    ModelBoundaryError,
    OpenAICompatibleL1BatchProducer,
    build_diagnostic_production_policy,
)
from tools.natural_memory_benchmark.l1_ontology_linking import (
    build_diagnostic_ontology_registry,
)

from test_e2e_pipeline_smoke import (  # noqa: F401
    _chat_response,
    _SequencedOpener,
    _slot_proposal,
    _turns,
)

#: 新的 dev 用例：条件句的多种措辞，都不得被记成 actual。
#: 这些句子与 hidden 的 "If the machine is fixed..." 不同，用于证明修复是通用的。
CONDITIONAL_DEV_CASES = (
    "If the kettle works, tea is drunk in the evening.",
    "Tea is drunk in the evening if the kettle works.",
    "Unless the shop closes, coffee is drunk after lunch.",
    "Coffee is drunk after lunch provided the shop is open.",
    "Should the meeting end early, tea is drunk on the terrace.",
    "When the delivery arrives, milk is added to the coffee.",
    "Assuming the grinder is fixed, coffee is drunk every morning.",
    "In case the tap runs dry, milk is added to the coffee.",
)

#: 反面用例：出现条件词，但条件并不作用于所陈述的事实本身。
NON_CONDITIONAL_DEV_CASES = (
    "Coffee is preferred, if that matters.",
    "Tea is drunk in the evening, in case you were wondering.",
)


def _producer(payload):  # type: ignore[no-untyped-def]
    registry = build_diagnostic_ontology_registry()
    return OpenAICompatibleL1BatchProducer(
        registry=registry,
        policy=build_diagnostic_production_policy(registry),
        base_url="https://model.invalid/v1",
        api_key="credential-that-must-not-enter-artifacts",
        model="test-model-response",
        max_attempts=1,
        opener=_SequencedOpener([_chat_response(payload)]),
    )


#: 注册表公布的谓词表面与 canonical operator 并不同名，必须按公布值填。
_PREDICATE_SURFACE = {
    "add_ingredient": "add",
    "drink": "drink",
    "prefer": "prefer",
}


def _role_slots(user_text: str, operator: str, surface: str) -> list[dict]:
    """Fill every role the operator publishes, quoting the user's own words."""
    pairs = [("theme", surface)]
    if operator == "add_ingredient":
        # add_ingredient 公布 theme 与 destination 两个角色，必须都填。
        pairs.append(("destination", "coffee"))
    slots = []
    for role, value in pairs:
        index = user_text.casefold().find(value.casefold())
        assert index >= 0, (user_text, value)
        quoted = user_text[index : index + len(value)]
        slots.append(
            {
                "role": role,
                "surface": quoted,
                "char_start": index,
                "char_end": index + len(quoted),
            }
        )
    return slots


def _payload_for(user_text: str, *, surface: str, operator: str, sense: str, kind: str):
    """One emit_l1 proposal claiming actual modality for the given sentence."""
    turns = _turns()
    turns[0] = turns[0].model_copy(update={"user_text": user_text})
    payload = {
        "schema_version": "production-l1-slot-batch-response-v1",
        "proposals": [
            {
                "turn_id": "turn-0000000000000001",
                "decision": "emit_l1",
                "slots": {
                    "predicate_surface": _PREDICATE_SURFACE[operator],
                    "predicate_sense": sense,
                    "canonical_operator": operator,
                    "kind": kind,
                    "modality": "actual",
                    "polarity": "positive",
                    "role_slots": _role_slots(user_text, operator, surface),
                    "event_time": None,
                    "valid_time": None,
                },
            },
            _slot_proposal(
                "turn-0000000000000002",
                kind="event",
                surface="drink",
                sense="consume_beverage",
                operator="drink",
            ),
        ],
    }
    return turns, payload


@pytest.mark.parametrize("user_text", CONDITIONAL_DEV_CASES)
def test_a_conditional_cannot_be_recorded_as_actual(user_text: str) -> None:
    """条件句以 actual 产出必须失败，覆盖多种措辞。"""
    surface = "Tea" if "tea is drunk" in user_text.casefold() else (
        "milk" if "milk is added" in user_text.casefold() else "coffee"
    )
    if surface.casefold() not in user_text.casefold():
        pytest.skip("surface not present")
    # 用原文中实际出现的大小写形式。
    index = user_text.casefold().find(surface.casefold())
    surface = user_text[index : index + len(surface)]
    operator, sense, kind = (
        ("add_ingredient", "add_ingredient", "event")
        if "added" in user_text
        else ("drink", "consume_beverage", "event")
    )
    turns, payload = _payload_for(
        user_text, surface=surface, operator=operator, sense=sense, kind=kind
    )
    with pytest.raises(ModelBoundaryError) as captured:
        _producer(payload).produce(turns)
    message = str(captured.value)
    assert "validation_code=modality_not_grounded" in message, message
    assert "credential-that-must-not-enter-artifacts" not in message


@pytest.mark.parametrize("user_text", NON_CONDITIONAL_DEV_CASES)
def test_an_incidental_conditional_word_still_admits_the_fact(
    user_text: str,
) -> None:
    """条件词不作用于事实本身时不得误拒，否则会造出新的假拒绝。"""
    operator, sense, kind = (
        ("prefer", "preference_theme", "preference")
        if "preferred" in user_text
        else ("drink", "consume_beverage", "event")
    )
    surface = "Coffee" if "Coffee" in user_text else "Tea"
    turns, payload = _payload_for(
        user_text, surface=surface, operator=operator, sense=sense, kind=kind
    )
    bound = _producer(payload).produce(turns)
    assert bound is not None


def test_the_repair_is_not_a_special_case_for_the_hidden_sentence() -> None:
    """修复必须是通用的，而不是针对 hidden 原文的特例。"""
    from tools.natural_memory_benchmark import e2e_openai_producers as module

    source = module.__file__
    assert source is not None
    text = open(source, encoding="utf-8").read()
    for fragment in ("machine is fixed", "would be drunk again"):
        assert fragment not in text, fragment
