"""一条更正必须能取代它更正的那条事实。

Phase C 的验收覆盖 fact-update，但当前 production 无法表达它：

* L1 producer 的 create-active 闸门拒绝任何 lifecycle 关系；
* pipeline 传给 admission 的 `known_lifecycle_revisions` 恒为 `[]`，所以后一轮
  即使想取代前一轮的事实，目标也永远 unresolved。

于是"先说偏好咖啡，后来改口偏好茶"只能变成两条并列的 active 事实，记忆里同时
存在两个互相矛盾的当前偏好。这不是模型质量问题，而是能力缺口。

放开 supersession 不能变成模型可以随意声明取代关系：目标必须是本次运行中真实
存在且仍然 active 的候选，否则必须失败。
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tools.natural_memory_benchmark.e2e_openai_producers import (
    ModelBoundaryError,
    OpenAICompatibleL1BatchProducer,
    allocate_support_ref,
    build_diagnostic_production_policy,
)
from tools.natural_memory_benchmark.l1_ontology_linking import (
    build_diagnostic_ontology_registry,
)

from test_e2e_pipeline_smoke import (  # noqa: F401
    _chat_response,
    _QueryProducer,
    _slot_proposal,
    _SequencedOpener,
    _turns,
)


class _DecliningL2Producer:
    """两条互相取代的事实无法合成一条可靠抽象。"""

    def produce(self, admitted_l1):  # type: ignore[no-untyped-def]
        return []


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


def _corrected_turns():
    """先说偏好咖啡，第二轮改口偏好茶。"""
    turns = _turns()
    turns[0] = turns[0].model_copy(
        update={"user_text": "Coffee is preferred."}
    )
    turns[1] = turns[1].model_copy(
        update={"user_text": "Actually tea is preferred."}
    )
    return turns


def _correction_payload():
    first = _slot_proposal(
        "turn-0000000000000001",
        kind="preference",
        surface="prefer",
        sense="preference_theme",
        operator="prefer",
        entity_surface="Coffee",
        char_start=0,
    )
    second = _slot_proposal(
        "turn-0000000000000002",
        kind="preference",
        surface="prefer",
        sense="preference_theme",
        operator="prefer",
        entity_surface="tea",
        char_start=len("Actually "),
    )
    # 第二轮取代第一轮：模型判断这是一次更正，而不是并列的第二条偏好。
    second["slots"]["supersedes_turn_ids"] = ["turn-0000000000000001"]
    return {
        "schema_version": "production-l1-slot-batch-response-v1",
        "proposals": [first, second],
    }


def test_slot_contract_can_express_a_correction() -> None:
    """槽位契约必须能表达"这一轮取代了哪一轮"。"""
    from tools.natural_memory_benchmark.e2e_openai_producers import (
        L1SemanticSlotProposalV1,
    )

    assert "supersedes_turn_ids" in L1SemanticSlotProposalV1.model_fields, (
        "L1 槽位无法表达更正关系，Phase C 的 fact-update 覆盖不可达"
    )


def test_a_correction_supersedes_the_fact_it_corrects() -> None:
    """更正之后，被取代的事实不得再是 active。"""
    from tools.natural_memory_benchmark.e2e_pipeline import run_e2e_pipeline

    turns = _corrected_turns()
    root = Path(tempfile.mkdtemp())
    result = run_e2e_pipeline(
        turns=turns,
        l1_producer=_producer(_correction_payload()).produce(turns),
        l2_producer=_DecliningL2Producer(),
        query_producer=_QueryProducer(),
        repository_path=root / "correction-history.git",
        question="What beverage is preferred?",
    )
    lifecycle_by_unit = {
        item.unit_id: item.lifecycle for item in result.bundle.l1_units
    }
    assert len(lifecycle_by_unit) == 2, lifecycle_by_unit
    assert sorted(lifecycle_by_unit.values()) == ["active", "superseded"], (
        lifecycle_by_unit
    )
    assert result.snapshot.verification_status == "valid"


def test_a_correction_leaves_one_current_answer() -> None:
    """更正之后当前答案只有一个，而不是两个并列的矛盾偏好。"""
    from tools.natural_memory_benchmark.e2e_pipeline import run_e2e_pipeline

    turns = _corrected_turns()
    root = Path(tempfile.mkdtemp())
    result = run_e2e_pipeline(
        turns=turns,
        l1_producer=_producer(_correction_payload()).produce(turns),
        l2_producer=_DecliningL2Producer(),
        query_producer=_QueryProducer(),
        repository_path=root / "correction-answer-history.git",
        question="What beverage is preferred?",
    )
    # 编译器的 supersession policy 是 current_only，所以答案只应是茶。
    assert result.execution.answer_values == ("memory:TeaBeverage",), (
        result.execution.answer_values
    )


def test_superseding_an_unknown_fact_still_fails() -> None:
    """取代目标必须真实存在，否则模型可以凭空声明取代关系。"""
    payload = _correction_payload()
    payload["proposals"][1]["slots"]["supersedes_turn_ids"] = [
        "turn-0000000000000009"
    ]
    turns = _corrected_turns()
    with pytest.raises(ModelBoundaryError) as captured:
        _producer(payload).produce(turns)
    assert "validation_code=supersession_target_unknown" in str(captured.value)
    assert "credential-that-must-not-enter-artifacts" not in str(captured.value)


def test_a_turn_cannot_supersede_itself() -> None:
    """一轮不能取代自己，否则会产生自引用的 lifecycle 环。"""
    payload = _correction_payload()
    payload["proposals"][1]["slots"]["supersedes_turn_ids"] = [
        "turn-0000000000000002"
    ]
    turns = _corrected_turns()
    with pytest.raises(ModelBoundaryError) as captured:
        _producer(payload).produce(turns)
    assert "validation_code=supersession_self_reference" in str(captured.value)


def test_allocate_support_ref_is_the_supersession_target() -> None:
    """取代关系按轮次表达，程序负责换算成候选 ref。

    模型看得到的是轮次，看不到 candidate ref 的分配规则，所以契约用轮次表达，
    由程序换算——否则又把机械细节推回给了模型。
    """
    assert allocate_support_ref("turn-0000000000000001").startswith("support-")
