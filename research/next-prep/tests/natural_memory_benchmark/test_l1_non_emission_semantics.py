"""`abstain` 与 `no_memory` 是两种不同结论，不能折叠成同一个空结果。

`no_memory` 表示这一轮确实没有值得留存的事实（例如一个提问）。
`abstain` 表示这一轮可能有事实，但依据不足以安全落库。

Phase C 的 abstention 指标区分这两者，`TurnBundleRevision` 也已经为
`no_memory_reason` 留了位置。production 把两者都变成空列表，于是下游无法
区分，Phase C 的指标也无法在 production 等价重放。
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from tools.natural_memory_benchmark.e2e_openai_producers import (
    OpenAICompatibleL1BatchProducer,
    build_diagnostic_production_policy,
)
from tools.natural_memory_benchmark.e2e_pipeline import (
    _make_source_inputs,
    run_e2e_pipeline,
)
from tools.natural_memory_benchmark.l1_ontology_linking import (
    build_diagnostic_ontology_registry,
)

from test_e2e_pipeline_smoke import (  # noqa: F401
    _chat_response,
    _L2Producer,
    _production_l1_slot_payload,
    _QueryProducer,
    _SequencedOpener,
    _turns,
)


def _bound_producer(decision: str):  # type: ignore[no-untyped-def]
    payload = _production_l1_slot_payload()
    second = payload["proposals"][1]
    second["decision"] = decision
    second.pop("slots", None)
    registry = build_diagnostic_ontology_registry()
    producer = OpenAICompatibleL1BatchProducer(
        registry=registry,
        policy=build_diagnostic_production_policy(registry),
        base_url="https://model.invalid/v1",
        api_key="credential-that-must-not-enter-artifacts",
        model="test-model-response",
        max_attempts=1,
        opener=_SequencedOpener([_chat_response(payload)]),
    )
    return producer.produce(_turns())


def _extraction_inputs():  # type: ignore[no-untyped-def]
    root = Path(tempfile.mkdtemp())
    _artifact, _sources, inputs = _make_source_inputs(
        _turns(), raw_artifact_path=root / "non-emission.raw.json"
    )
    return inputs


def test_no_memory_and_abstain_are_distinguishable() -> None:
    """两种非产出结论必须能被下游分辨。"""
    inputs = _extraction_inputs()
    turn = inputs["turn-0000000000000002"]

    no_memory = _bound_producer("no_memory")
    abstained = _bound_producer("abstain")

    assert no_memory.produce(turn) == []
    assert abstained.produce(turn) == []
    assert no_memory.non_emission_reason("turn-0000000000000002") == "no_memory"
    assert abstained.non_emission_reason("turn-0000000000000002") == "abstain"
    # 产出记忆的轮次没有非产出结论。
    assert no_memory.non_emission_reason("turn-0000000000000001") is None


def test_turn_bundle_records_which_non_emission_occurred() -> None:
    """turn bundle 的 no_memory_reason 必须说明是哪一种结论。"""

    class _AbstainingL1Producer:
        def produce(self, value):  # type: ignore[no-untyped-def]
            return []

        def non_emission_reason(self, turn_id: str) -> str:
            return "abstain"

    class _DecliningL2Producer:
        """没有任何 admitted L1 时，L2 也只能弃权。"""

        def produce(self, admitted_l1):  # type: ignore[no-untyped-def]
            return []

    root = Path(tempfile.mkdtemp())
    result = run_e2e_pipeline(
        turns=_turns(),
        l1_producer=_AbstainingL1Producer(),
        l2_producer=_DecliningL2Producer(),
        query_producer=_QueryProducer(),
        repository_path=root / "abstain-bundle-history.git",
        question="What beverage is preferred?",
    )
    reasons = {item.turn_id: item.no_memory_reason for item in result.turn_bundles}
    assert set(reasons.values()) == {"abstain"}, reasons
