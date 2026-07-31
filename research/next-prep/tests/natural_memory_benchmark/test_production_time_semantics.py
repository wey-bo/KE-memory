"""一条带时间的事实必须能带着时间落库。

Phase C 的验收覆盖 time，但当前 production policy 只发布 `actual` 一种模态，
且 event_time 与 valid_time 都是 `forbidden`。于是"Coffee has been preferred
since 2026-03-01."这类输入只能丢掉时间写入，或者干脆失败——时间维度在
production 中不可达，而这与模型质量无关。

放开时间不能变成模型可以随便声明时间：policy 仍然决定哪种模态允许哪个时间
字段，声明了未授权的时间必须失败。
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
    _production_l1_slot_payload,
    _SequencedOpener,
    _turns,
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


def _dated_turns():
    turns = _turns()
    turns[0] = turns[0].model_copy(
        update={"user_text": "Coffee has been preferred since 2026-03-01."}
    )
    return turns


def test_policy_permits_a_valid_time_for_actual_facts() -> None:
    """policy 必须允许 actual 事实携带 valid_time。"""
    registry = build_diagnostic_ontology_registry()
    policy = build_diagnostic_production_policy(registry)
    actual = next(
        item for item in policy.modality_time_policies if item.modality == "actual"
    )
    assert actual.valid_time_policy != "forbidden", (
        "actual 事实的 valid_time 被禁止，Phase C 的 time 覆盖不可达"
    )


def test_a_dated_fact_keeps_its_time_through_the_pipeline() -> None:
    """带时间的事实必须带着 valid_time 写进权威记忆。"""
    import tempfile
    from pathlib import Path

    from tools.natural_memory_benchmark.e2e_pipeline import run_e2e_pipeline

    from test_e2e_pipeline_smoke import _QueryProducer

    turns = _dated_turns()
    payload = _production_l1_slot_payload()
    # admission 要求可解析且带时区的时间戳，裸日期会以
    # time_binding_unresolved 被拒——这条约束是对的，时间必须是明确的时刻。
    payload["proposals"][0]["slots"]["valid_time"] = "2026-03-01T00:00:00Z"

    class _DecliningL2Producer:
        def produce(self, admitted_l1):  # type: ignore[no-untyped-def]
            return []

    root = Path(tempfile.mkdtemp())
    result = run_e2e_pipeline(
        turns=turns,
        l1_producer=_producer(payload).produce(turns),
        l2_producer=_DecliningL2Producer(),
        query_producer=_QueryProducer(),
        repository_path=root / "dated-history.git",
        question="What beverage is preferred?",
    )
    valid_times = {item.time.valid_time for item in result.bundle.l1_units}
    assert "2026-03-01T00:00:00Z" in valid_times, valid_times
    assert result.snapshot.verification_status == "valid"


def test_an_unauthorized_time_field_still_fails() -> None:
    """放开 valid_time 不得让 event_time 也随之免检。

    policy 仍然把 actual 的 event_time 标为 forbidden，声明它必须失败，否则
    时间就成了模型可以随意填写的自由字段。
    """
    registry = build_diagnostic_ontology_registry()
    policy = build_diagnostic_production_policy(registry)
    actual = next(
        item for item in policy.modality_time_policies if item.modality == "actual"
    )
    assert actual.event_time_policy == "forbidden"

    payload = _production_l1_slot_payload()
    payload["proposals"][0]["slots"]["event_time"] = "2026-03-01"
    with pytest.raises(ModelBoundaryError) as captured:
        _producer(payload).produce(_turns())
    assert "validation_code=forbidden_time" in str(captured.value)
    assert "credential-that-must-not-enter-artifacts" not in str(captured.value)
