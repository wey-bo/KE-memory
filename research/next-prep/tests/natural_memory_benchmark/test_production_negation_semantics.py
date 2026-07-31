"""一句否定必须能被如实记录，而不是无论如何都失败。

Phase C 的验收覆盖 negation，但当前 production policy 只授权 positive：

* 提 `polarity="negative"` 会被 `allowed_polarities` 拒绝；
* 提 `polarity="positive"` 又会被 `_has_explicit_negation` 拒绝。

于是"Coffee is not preferred."这类输入无论模型怎么判断都写不进去。这不是安全，
而是能力缺口：一条被否定的事实与一条不存在的事实是两回事，前者是应当记住的
内容。同时，放开 negative 不能放松 grounding——把一句肯定标成 negative 仍然
必须失败，否则极性就变成了模型可以随意声明的自由字段。
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
    _slot_proposal,
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


def _negated_turns():
    turns = _turns()
    turns[0] = turns[0].model_copy(
        update={"user_text": "Coffee is not preferred."}
    )
    return turns


def test_policy_authorizes_negative_polarity() -> None:
    """policy 必须授权 negative，否则否定内容根本无法落库。"""
    registry = build_diagnostic_ontology_registry()
    policy = build_diagnostic_production_policy(registry)
    assert "negative" in policy.allowed_polarities, (
        "production policy 只授权 positive，Phase C 的 negation 覆盖不可达"
    )


def test_a_negated_statement_is_recorded_as_negative() -> None:
    """否定句必须以 negative 极性被记录下来。"""
    turns = _negated_turns()
    payload = _production_l1_slot_payload()
    slots = payload["proposals"][0]["slots"]
    slots["polarity"] = "negative"
    # "Coffee" 在这句话里仍然位于开头。
    assert turns[0].user_text.startswith("Coffee")

    bound = _producer(payload).produce(turns)
    from tools.natural_memory_benchmark.e2e_pipeline import _make_source_inputs

    import tempfile
    from pathlib import Path

    root = Path(tempfile.mkdtemp())
    _artifact, _sources, inputs = _make_source_inputs(
        turns, raw_artifact_path=root / "negation.raw.json"
    )
    proposals = bound.produce(inputs["turn-0000000000000001"])
    assert len(proposals) == 1
    assert proposals[0].typed_candidate.polarity == "negative"


def test_a_negated_fact_survives_the_whole_pipeline() -> None:
    """否定事实必须一路写进权威记忆，而不是只在 producer 边界通过。

    Phase C 的 negation 覆盖要求的是落库结果：admission policy 也必须接受
    negative，否则 producer 放行之后 pipeline 仍会拒绝。
    """
    import tempfile
    from pathlib import Path

    from tools.natural_memory_benchmark.e2e_pipeline import run_e2e_pipeline

    from test_e2e_pipeline_smoke import _QueryProducer

    turns = _negated_turns()
    payload = _production_l1_slot_payload()
    payload["proposals"][0]["slots"]["polarity"] = "negative"
    # pipeline 逐轮调用 produce(extraction_input)，所以先把批量提案绑定好。
    l1_producer = _producer(payload).produce(turns)

    class _DecliningL2Producer:
        """否定事实与第二轮的肯定事实无法合成一条可靠抽象。"""

        def produce(self, admitted_l1):  # type: ignore[no-untyped-def]
            return []

    root = Path(tempfile.mkdtemp())
    result = run_e2e_pipeline(
        turns=turns,
        l1_producer=l1_producer,
        l2_producer=_DecliningL2Producer(),
        query_producer=_QueryProducer(),
        repository_path=root / "negation-history.git",
        question="What beverage is preferred?",
    )
    polarities = {item.polarity for item in result.bundle.l1_units}
    assert "negative" in polarities, polarities
    assert result.snapshot.verification_status == "valid"


def test_calling_a_positive_statement_negative_still_fails() -> None:
    """放开 negative 不得让极性变成模型可随意声明的自由字段。

    原文没有否定词却标成 negative，必须失败：否则一条肯定事实会被写成它的
    反面，而这正是 critical false emission。
    """
    payload = _production_l1_slot_payload()
    payload["proposals"][0]["slots"]["polarity"] = "negative"
    # 原文是肯定的 "Coffee is preferred."，校验在批量产出时即失败。
    with pytest.raises(ModelBoundaryError) as captured:
        _producer(payload).produce(_turns())
    assert "validation_code=polarity_not_grounded" in str(captured.value)
    assert "credential-that-must-not-enter-artifacts" not in str(captured.value)
