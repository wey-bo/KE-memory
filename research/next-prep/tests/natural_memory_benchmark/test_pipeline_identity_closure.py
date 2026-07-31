"""pipeline 自己就要产出带 identity 的记忆，Phase D 才能在同一 snapshot 上作答。

`promote_to_category_identity_bundle` 已经存在，但只在测试里被显式调用：
`run_e2e_pipeline` 仍然提交没有 identity 的 V3 bundle，并且用不绑定 snapshot 的
registry 编译。于是 Phase D 的 fact / count / abstain 三类问题无法落在同一份
记忆与同一份 registry 上——fact 能答，count 只能弃权，原因与模型质量无关。

升级必须发生在提交之前：提交后再升级会让 Git 中的 artifact 与 bundle 不一致。
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from tools.natural_memory_benchmark.e2e_pipeline import run_e2e_pipeline
from tools.natural_memory_benchmark.identity_resolution import (
    IdentityAwareMemoryBundleV4,
    assess_identity_bundle_integrity,
)

from test_e2e_pipeline_smoke import (  # noqa: F401
    _L1Producer,
    _L2Producer,
    _QueryProducer,
    _turns,
)


def _run(question: str = "What beverage is preferred?"):
    root = Path(tempfile.mkdtemp())
    return run_e2e_pipeline(
        turns=_turns(),
        l1_producer=_L1Producer(),
        l2_producer=_L2Producer(),
        query_producer=_QueryProducer(),
        repository_path=root / "identity-closure-history.git",
        question=question,
    )


def test_pipeline_commits_an_identity_aware_bundle() -> None:
    """pipeline 提交的 bundle 必须自带 identity，且完整性有效。"""
    result = _run()
    assert isinstance(result.bundle, IdentityAwareMemoryBundleV4), (
        "pipeline 仍在提交没有 identity 的 bundle，Phase D 的 count 不可达"
    )
    report = assess_identity_bundle_integrity(result.bundle)
    assert report.valid, report.errors
    assert len(result.bundle.identity_snapshots) == 1
    assert result.snapshot.verification_status == "valid"


def test_pipeline_registry_binds_the_committed_snapshot() -> None:
    """编译用的 registry 必须绑定被提交的那一份 snapshot。

    若 registry 绑定的是另一份 snapshot（或没有绑定），实体会被报告为
    unresolved，count 只能弃权，而这与模型无关。
    """
    result = _run()
    snapshot = result.bundle.identity_snapshots[0]
    assert result.compilation.plan is not None
    # plan 与执行权威都必须指向被提交的那一份 snapshot；执行器在两者不一致时会
    # 以 identity_snapshot_mismatch 弃权，所以这里同时钉住两侧。
    assert result.compilation.plan.identity_snapshot_id == snapshot.snapshot_id
    assert result.execution.authority.identity_snapshot_id == snapshot.snapshot_id
    assert result.execution.authority.identity_input_fingerprint == (
        snapshot.input_fingerprint
    )
    assert result.execution.evaluation.abstained is False, (
        result.execution.evaluation.reason
    )


def test_count_is_answerable_on_the_committed_snapshot() -> None:
    """count 必须能在 pipeline 自己提交的那份记忆上作答。

    这是 Phase D 的前置条件：fact 与 count 落在同一份 bundle、同一份 snapshot、
    同一份 registry 上，不需要测试自行升级或另建 registry。
    """
    from tools.natural_memory_benchmark.query_compiler_v2 import (
        QueryContextV1,
        compile_natural_query,
    )
    from tools.natural_memory_benchmark.query_execution_snapshot_adapter import (
        execute_authoritative_query,
    )

    result = _run()
    snapshot = result.bundle.identity_snapshots[0]
    registry = _registry_of(result)
    plan = result.compilation.plan
    assert plan is not None

    class _CountProducer(_QueryProducer):
        def produce(self, request):  # type: ignore[no-untyped-def]
            draft = super().produce(request)
            answer = draft.answer.model_copy(
                update={"kind": "count", "distinct_by": "canonical_identity"}
            )
            return draft.model_copy(update={"answer": answer})

    context = QueryContextV1(
        query_id="query-e2e-1",
        raw_query="How many beverages are preferred?",
        query_time="2026-07-31T00:01:00Z",
        current_user_entity_id=None,
        memory_view=plan.memory_view,
        ontology_revision=registry.ontology_revision,
        identity_revision=registry.identity_revision,
        compiler_policy_revision="e2e-query-policy-v1",
    )
    compilation = compile_natural_query(
        question="How many beverages are preferred?",
        context=context,
        registry=registry,
        producer=_CountProducer(),
    )
    assert compilation.plan is not None, compilation.blocked_reasons
    assert compilation.plan.answer.identity_resolution_required is True
    execution = execute_authoritative_query(
        repository_path=result.snapshot.repository_path,
        bundle=result.bundle,
        bundle_history_artifact=result.snapshot.bundle_history_artifact,
        turn_bundles=list(result.turn_bundles),
        registry=registry,
        plan=compilation.plan,
        identity_snapshot_id=snapshot.snapshot_id,
    )
    assert execution.evaluation.abstained is False, execution.evaluation.reason
    assert execution.evaluation.count_value == 1
    assert execution.evaluation.closure_complete is True


def test_a_memory_with_nothing_in_it_is_not_given_an_identity() -> None:
    """一轮都没有产出记忆时不得硬造 snapshot。

    空记忆没有实体可解析，为它编一份 identity snapshot 会是在陈述不存在的
    事实；升级必须跳过，而 pipeline 仍要正常完成——这正是 Phase C 的
    no-memory 场景。
    """
    from tools.natural_memory_benchmark.authoritative_memory import (
        MemoryRepresentationBundleV3,
    )

    class _AbstainingL1Producer:
        def produce(self, value):  # type: ignore[no-untyped-def]
            return []

        def non_emission_reason(self, turn_id: str) -> str:
            return "abstain"

    class _DecliningL2Producer:
        def produce(self, admitted_l1):  # type: ignore[no-untyped-def]
            return []

    root = Path(tempfile.mkdtemp())
    result = run_e2e_pipeline(
        turns=_turns(),
        l1_producer=_AbstainingL1Producer(),
        l2_producer=_DecliningL2Producer(),
        query_producer=_QueryProducer(),
        repository_path=root / "empty-identity-history.git",
        question="What beverage is preferred?",
    )
    assert result.bundle.l1_units == []
    assert not isinstance(result.bundle, IdentityAwareMemoryBundleV4)
    assert isinstance(result.bundle, MemoryRepresentationBundleV3)
    assert result.execution.authority.identity_snapshot_id is None
    assert result.snapshot.verification_status == "valid"


def _registry_of(result):  # type: ignore[no-untyped-def]
    """重建 pipeline 自己用过的 registry，绑定它提交的那份 snapshot。"""
    from tools.natural_memory_benchmark.e2e_pipeline import build_compiler_registry
    from tools.natural_memory_benchmark.l1_ontology_linking import (
        build_diagnostic_ontology_registry,
    )

    return build_compiler_registry(
        build_diagnostic_ontology_registry(),
        identity_snapshot=result.bundle.identity_snapshots[0],
    )


def test_fact_answer_is_unchanged_by_the_identity_upgrade() -> None:
    """加入 identity 不得改变原本可答的 fact 结论。"""
    result = _run()
    assert result.execution.answer_values == ("memory:CoffeeBeverage",)
    assert result.answer.fallback_triggered is False
    assert {span.text for span in result.answer.evidence_spans} == {
        "Coffee is preferred.",
        "Coffee is drunk regularly.",
    }
