"""L2 必须能够拒绝作答，并且必须执行 production policy。

外部审计指出三处缺口，这里逐项固定为可执行断言：

* L2 响应契约没有 decision 字段，pipeline 又强制恰好产出一条
  L2，因此 Phase C 的 abstention 指标无法在 production 等价重放。
* L1 producer 执行 `allowed_polarities`，L2 producer 不执行，所以 L2 可以提出
  policy 未授权的极性。
* L1 把 `abstain` 与 `no_memory` 都折叠成空列表，两种语义不同的结果在
  production 中不可区分。
"""

from __future__ import annotations

import json

import pytest

from tools.natural_memory_benchmark.e2e_openai_producers import (
    ModelBoundaryError,
    OpenAICompatibleL2Producer,
    ProductionL2SlotResponseV1,
    build_diagnostic_production_policy,
)
from tools.natural_memory_benchmark.l1_ontology_linking import (
    build_diagnostic_ontology_registry,
)

from test_e2e_pipeline_smoke import (  # noqa: F401
    _chat_response,
    _production_l2_payload,
    _SequencedOpener,
)


def test_l2_response_can_decline_to_emit() -> None:
    """一次没有可靠抽象的 L2 请求必须能表达“不产出”。"""
    fields = ProductionL2SlotResponseV1.model_fields
    assert "decision" in fields, (
        "L2 缺少 decision 字段，无法表达 abstain，"
        "Phase C 的 abstention 指标无法在 production 重放"
    )
    declined = ProductionL2SlotResponseV1.model_validate(
        {
            "schema_version": "production-l2-slot-response-v1",
            "decision": "abstain",
        }
    )
    assert declined.slots is None
    assert declined.decision == "abstain"


def test_l2_emission_still_requires_a_candidate() -> None:
    """放开弃权不能让“声称产出但没有内容”通过。"""
    with pytest.raises(ValueError):
        ProductionL2SlotResponseV1.model_validate(
            {
                "schema_version": "production-l2-slot-response-v1",
                "decision": "emit_l2",
            }
        )


def test_l2_declining_yields_no_proposal() -> None:
    """弃权时 producer 必须返回空列表，而不是抛错或伪造一条。"""
    registry = build_diagnostic_ontology_registry()
    payload = {
        "schema_version": "production-l2-slot-response-v1",
        "decision": "abstain",
    }
    producer = OpenAICompatibleL2Producer(
        registry=registry,
        policy=build_diagnostic_production_policy(registry),
        base_url="https://model.invalid/v1",
        api_key="credential-that-must-not-enter-artifacts",
        model="test-model-response",
        max_attempts=1,
        opener=_SequencedOpener([_chat_response(payload)]),
    )
    assert producer.produce(_admitted_l1_stub()) == []


def test_pipeline_records_an_l2_abstention_instead_of_failing() -> None:
    """L2 弃权时 pipeline 必须完成并记录，而不是抛错。"""
    import tempfile
    from pathlib import Path

    from test_e2e_pipeline_smoke import (
        _L1Producer,
        _QueryProducer,
        _turns,
    )

    from tools.natural_memory_benchmark.e2e_pipeline import run_e2e_pipeline

    class _DecliningL2Producer:
        def produce(self, admitted_l1):  # type: ignore[no-untyped-def]
            return []

    root = Path(tempfile.mkdtemp())
    result = run_e2e_pipeline(
        turns=_turns(),
        l1_producer=_L1Producer(),
        l2_producer=_DecliningL2Producer(),
        query_producer=_QueryProducer(),
        repository_path=root / "l2-abstain-history.git",
        question="What beverage is preferred?",
    )
    # L1 记忆仍然被物化并提交，只是没有 L2 抽象。
    assert len(result.bundle.l1_units) == 2
    assert result.bundle.l2_units == []
    assert result.bundle.closure_specs == []
    assert result.snapshot.verification_status == "valid"


def test_l2_polarity_must_be_authorized_by_policy() -> None:
    """L2 极性必须受 policy allowlist 约束，与 L1 同等。"""
    registry = build_diagnostic_ontology_registry()
    policy = build_diagnostic_production_policy(registry)
    assert policy.allowed_polarities == ["positive"]
    payload = json.loads(json.dumps(_production_l2_payload()))
    payload["slots"]["polarity"] = "negative"
    producer = OpenAICompatibleL2Producer(
        registry=registry,
        policy=policy,
        base_url="https://model.invalid/v1",
        api_key="credential-that-must-not-enter-artifacts",
        model="test-model-response",
        max_attempts=1,
        opener=_SequencedOpener([_chat_response(payload)]),
    )
    with pytest.raises(ModelBoundaryError) as captured:
        producer.produce(_admitted_l1_stub())
    assert "validation_code=polarity_not_authorized" in str(captured.value)


def _admitted_l1_stub():  # type: ignore[no-untyped-def]
    """用真实 pipeline 产出的 admitted L1 记录作为 L2 输入。

    `EndToEndResultV1` 不暴露 admitted L1，所以在 pipeline 运行过程中由一个
    记录型 L2 producer 捕获，避免自行伪造 admission 结果。
    """
    import tempfile
    from pathlib import Path

    from test_e2e_pipeline_smoke import (
        _L1Producer,
        _L2Producer,
        _QueryProducer,
        _turns,
    )

    from tools.natural_memory_benchmark.e2e_pipeline import run_e2e_pipeline

    captured: list[object] = []
    delegate = _L2Producer()

    class _RecordingL2Producer:
        def produce(self, admitted_l1):  # type: ignore[no-untyped-def]
            captured.append(tuple(admitted_l1))
            return delegate.produce(admitted_l1)

    root = Path(tempfile.mkdtemp())
    run_e2e_pipeline(
        turns=_turns(),
        l1_producer=_L1Producer(),
        l2_producer=_RecordingL2Producer(),
        query_producer=_QueryProducer(),
        repository_path=root / "l2-policy-history.git",
        question="What beverage is preferred?",
    )
    assert captured, "pipeline 未把 admitted L1 交给 L2 producer"
    return captured[0]
