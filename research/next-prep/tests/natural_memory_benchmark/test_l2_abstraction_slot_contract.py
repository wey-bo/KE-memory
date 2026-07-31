"""L2 只该判断“哪些 L1 该合并、抽象语义是什么”，其余由程序物化。

当前 L2 要求模型自行构造 supporting_l1_refs、source_turn_refs、
source_session_refs、evidence_bindings、closure.required_support_refs、
lifecycle、claim_ref 以及 claim 内的 local_entities/roles。这些全部可以从
admitted L1 支撑集确定性推导，却被当作语义质量来评分——这正是
structured_claim_accuracy 与 summary_accuracy 同时为 0 的位置。

fresh-v3 还暴露出一个契约缺陷：prompt 要求 summary 逐字复制公共
`untyped_candidate.statement`，而 gold 的 summary 多了一个句号，
scorer 又做精确字符串比较，因此照做必错。程序物化时必须让这两者一致。
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tools.natural_memory_benchmark.e2e_openai_producers import (
    L2AbstractionSlotProposalV1,
    build_diagnostic_production_policy,
    materialize_typed_l2_candidate,
)
from tools.natural_memory_benchmark.l1_ontology_linking import (
    build_diagnostic_ontology_registry,
)

from test_e2e_pipeline_smoke import (  # noqa: F401
    _L1Producer,
    _L2Producer,
    _QueryProducer,
    _turns,
)


def _admitted_l1():  # type: ignore[no-untyped-def]
    from tools.natural_memory_benchmark.e2e_pipeline import run_e2e_pipeline

    captured: list[object] = []
    delegate = _L2Producer()

    class _Recording:
        def produce(self, admitted_l1):  # type: ignore[no-untyped-def]
            captured.append(tuple(admitted_l1))
            return delegate.produce(admitted_l1)

    root = Path(tempfile.mkdtemp())
    run_e2e_pipeline(
        turns=_turns(),
        l1_producer=_L1Producer(),
        l2_producer=_Recording(),
        query_producer=_QueryProducer(),
        repository_path=root / "l2-slot-history.git",
        question="What beverage is preferred?",
    )
    assert captured
    return captured[0]


def _slots(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "kind": "preference_profile",
        "statement": "coffee is the preferred beverage",
        "predicate_surface": "prefer",
        "predicate_sense": "preference_theme",
        "canonical_operator": "prefer",
        "abstraction_method": "preference_aggregation",
        "modality": "actual",
        "polarity": "positive",
        "role_slots": [{"role": "theme", "support_entity_surface": "coffee"}],
    }
    payload.update(overrides)
    return payload


def _materialize(payload: dict[str, object], admitted=None):  # type: ignore[no-untyped-def]
    registry = build_diagnostic_ontology_registry()
    return materialize_typed_l2_candidate(
        slots=L2AbstractionSlotProposalV1.model_validate(payload),
        admitted_l1=admitted if admitted is not None else _admitted_l1(),
        registry=registry,
        policy=build_diagnostic_production_policy(registry),
    )


def test_program_supplies_support_and_closure_refs() -> None:
    """支撑集、闭包与来源引用都可从 admitted L1 推导。"""
    admitted = _admitted_l1()
    candidate = _materialize(_slots(), admitted)
    expected_refs = [item.candidate_ref for item in admitted]
    assert candidate.supporting_l1_refs == expected_refs
    assert candidate.closure.required_support_refs == expected_refs
    assert candidate.closure.optional_support_refs == []
    assert candidate.source_turn_refs == [item.turn_id for item in admitted]
    assert candidate.source_session_refs == sorted(
        {item.session_id for item in admitted}
    )
    assert candidate.lifecycle == "candidate"


def test_program_supplies_claim_refs_and_evidence_bindings() -> None:
    """claim_ref 与 evidence 绑定都是机械字段。"""
    admitted = _admitted_l1()
    candidate = _materialize(_slots(), admitted)
    assert [item.claim_ref for item in candidate.structured_claims] == ["claim-01"]
    claim = candidate.structured_claims[0]
    assert claim.supporting_l1_refs == [item.candidate_ref for item in admitted]
    bound = {item.evidence_id for item in candidate.evidence_bindings}
    assert bound == {
        span.evidence_id
        for item in admitted
        for span in item.revision.payload.source.evidence_spans
    }
    assert all(item.speaker == "user" for item in candidate.evidence_bindings)


def test_summary_is_the_statement_verbatim() -> None:
    """summary 必须与公共 statement 逐字一致，不额外加标点。

    fresh-v3 的 gold summary 比 statement 多一个句号，而 scorer 做精确比较，
    所以“照 prompt 复制”必然记零分。程序物化必须消除这个分歧。
    """
    candidate = _materialize(_slots(statement="coffee is the preferred beverage"))
    assert candidate.summary == "coffee is the preferred beverage"
    assert not candidate.summary.endswith(".")


def test_closure_pattern_follows_the_published_abstraction_map() -> None:
    """abstraction 决定 closure，模型不再自行选择。"""
    candidate = _materialize(_slots(abstraction_method="preference_aggregation"))
    assert candidate.abstraction.method == "preference_aggregation"
    assert candidate.closure.pattern == "multi_evidence_set"


def test_unauthorized_abstraction_fails_closed() -> None:
    """policy 未授权的抽象方法必须被拒绝。"""
    with pytest.raises(ValueError, match="abstraction"):
        _materialize(_slots(abstraction_method="state_summary"))


def test_unauthorized_polarity_fails_closed() -> None:
    """policy 的极性 allowlist 在物化阶段同样生效。

    诊断 policy 现在两种极性都授权，所以显式收窄成只允许 positive：否则没有
    未授权取值可试，这条保证会变成空测。
    """
    registry = build_diagnostic_ontology_registry()
    policy = build_diagnostic_production_policy(registry).model_copy(
        update={"allowed_polarities": ["positive"]}
    )
    with pytest.raises(ValueError, match="polarity"):
        materialize_typed_l2_candidate(
            slots=L2AbstractionSlotProposalV1.model_validate(
                _slots(polarity="negative")
            ),
            admitted_l1=_admitted_l1(),
            registry=registry,
            policy=policy,
        )


def test_role_surface_must_come_from_a_support() -> None:
    """claim 的实体表面必须来自某条 admitted L1 支撑。"""
    with pytest.raises(ValueError, match="support"):
        _materialize(
            _slots(
                role_slots=[
                    {"role": "theme", "support_entity_surface": "not-in-support"}
                ]
            )
        )


def test_two_memories_from_one_turn_yield_one_turn_ref() -> None:
    """同一轮的多条 L1 支撑只能贡献一个 source_turn_ref。

    L1 现在是每轮 0..N 元，所以两条 admitted L1 落在同一轮是可达输入。物化器
    若逐条追加 turn_id，就会产出重复引用，而 producer 的闭包检查比较的是去重
    列表，于是合法的多事实输入被判为 turn_closure_mismatch。
    """
    admitted = list(_admitted_l1())
    admitted[1] = admitted[1].model_copy(update={"turn_id": admitted[0].turn_id})
    candidate = _materialize(_slots(), tuple(admitted))
    assert candidate.source_turn_refs == [admitted[0].turn_id]


def test_role_surface_matches_support_regardless_of_case() -> None:
    """大小写不是语义区分，但物化出的表面必须逐字取自支撑。

    L1 的实体表面是从用户原文摘下来的，所以真实取值可能是 "Coffee"。producer
    下游每一处 grounding 检查都做 casefold 比较，物化器却精确匹配，于是模型
    给出 "coffee" 就会被判为 claim_roles_without_support——一个大小写造成的
    假拒绝。匹配放宽到大小写无关，但写入的表面仍取支撑的原样拼写。
    """
    admitted = _admitted_l1()
    support_surfaces = {
        entity.surface
        for item in admitted
        for entity in item.linked_candidate.typed_candidate.local_entities
    }
    assert len(support_surfaces) == 1, "夹具前提：支撑只有一个实体表面"
    actual = next(iter(support_surfaces))
    # 用与支撑相反的大小写提出请求，确保匹配不依赖拼写大小写。
    requested = actual.upper() if actual[0].islower() else actual.lower()
    assert requested != actual
    candidate = _materialize(
        _slots(role_slots=[{"role": "theme", "support_entity_surface": requested}]),
        admitted,
    )
    claim = candidate.structured_claims[0]
    # 写入的表面取支撑的原样拼写，而不是模型请求里的拼写。
    assert [item.surface for item in claim.local_entities] == [actual]


def test_slot_contract_excludes_mechanical_fields() -> None:
    """机械字段不得出现在模型契约里。"""
    fields = set(L2AbstractionSlotProposalV1.model_fields)
    for mechanical in (
        "supporting_l1_refs",
        "source_turn_refs",
        "source_session_refs",
        "evidence_bindings",
        "closure",
        "lifecycle",
        "structured_claims",
        "summary",
    ):
        assert mechanical not in fields, f"{mechanical} 应由程序物化"
