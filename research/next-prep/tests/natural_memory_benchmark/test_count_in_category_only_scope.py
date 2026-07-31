"""A count over category-only memory must be answerable or honestly refused.

`compile_natural_query` sets `identity_resolution_required` whenever the answer
kind is `count`, and the executor abstains unless every answer value is
`resolved`. The production path builds no identity snapshot, so every entity is
`unresolved` and a count can only ever abstain. That makes the Phase D count
scenario unreachable for a reason that has nothing to do with the model.

Counting distinct category-level values does not actually need identity
resolution: the values are ontology concept identifiers, not coreferent
individuals. Identity resolution is required when a count must not double-count
two surfaces naming the same individual. So the requirement belongs to the
distinctness policy, not to the answer kind.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from tools.natural_memory_benchmark.e2e_pipeline import (
    build_compiler_registry,
    run_e2e_pipeline,
)
from tools.natural_memory_benchmark.l1_ontology_linking import (
    build_diagnostic_ontology_registry,
)
from tools.natural_memory_benchmark.query_compiler_v2 import (
    QueryContextV1,
    compile_natural_query,
)
from tools.natural_memory_benchmark.query_execution_snapshot_adapter import (
    GitMemoryViewRefV1,
    execute_authoritative_query,
)

from test_e2e_pipeline_smoke import (  # noqa: F401
    _L1Producer,
    _L2Producer,
    _QueryProducer,
    _turns,
)


class _CountQueryProducer(_QueryProducer):
    """Asks how many beverages are preferred, over category-level values."""

    def produce(self, request):  # type: ignore[no-untyped-def]
        draft = super().produce(request)
        answer = draft.answer.model_copy(
            update={"kind": "count", "distinct_by": "value"}
        )
        return draft.model_copy(update={"answer": answer})


def _seeded():
    root = Path(tempfile.mkdtemp())
    repository = root / "count-scope-history.git"
    result = run_e2e_pipeline(
        turns=_turns(),
        l1_producer=_L1Producer(),
        l2_producer=_L2Producer(),
        query_producer=_QueryProducer(),
        repository_path=repository,
        question="What beverage is preferred?",
    )
    return repository, result


def _memory_view(repository: Path, result) -> GitMemoryViewRefV1:  # type: ignore[no-untyped-def]
    """Read the real epoch identity rather than fabricating one."""
    from tools.natural_memory_benchmark.git_memory_history import (
        GitMemoryHistoryRepository,
    )

    history = GitMemoryHistoryRepository(repository)
    metadata = history.read_repository_metadata(commit=result.snapshot.git_commit)
    return GitMemoryViewRefV1(
        workspace_id=metadata.workspace_id,
        repository_epoch_id=metadata.repository_epoch_id,
        checkpoint_id=result.snapshot.checkpoint_id,
        git_commit=result.snapshot.git_commit,
    )


def _execute_count(distinct_by: str = "value"):
    repository, result = _seeded()
    registry = build_compiler_registry(build_diagnostic_ontology_registry())
    context = QueryContextV1(
        query_id="query-e2e-1",
        raw_query="How many beverages are preferred?",
        query_time="2026-07-31T00:00:00Z",
        current_user_entity_id=None,
        memory_view=_memory_view(repository, result),
        ontology_revision=registry.ontology_revision,
        identity_revision=registry.identity_revision,
        compiler_policy_revision="e2e-query-policy-v1",
    )

    class _Producer(_CountQueryProducer):
        def produce(self, request):  # type: ignore[no-untyped-def]
            draft = super().produce(request)
            answer = draft.answer.model_copy(update={"distinct_by": distinct_by})
            return draft.model_copy(update={"answer": answer})

    compilation = compile_natural_query(
        question="How many beverages are preferred?",
        context=context,
        registry=registry,
        producer=_Producer(),
    )
    assert compilation.plan is not None, compilation.blocked_reasons
    execution = execute_authoritative_query(
        repository_path=repository,
        bundle=result.bundle,
        bundle_history_artifact=result.snapshot.bundle_history_artifact,
        turn_bundles=list(result.turn_bundles),
        registry=registry,
        plan=compilation.plan,
    )
    return compilation.plan, execution


def test_count_is_currently_unanswerable_in_category_only_scope() -> None:
    """记录 Phase D count 当前不可达这一事实。

    `compile_natural_query` 对任何 count 都要求 `canonical_identity` 去重策略，
    并因此要求 identity resolution，而 production 不构建 identity snapshot，
    所以 count 只能弃权。这不是模型质量问题。

    修复方案尚待裁决：为 category-only 作用域提供真实的 identity snapshot，
    或改变 compiler 契约（后者会使已冻结的 dev-qualification gold 失效）。
    在裁决前，本测试固定当前行为，避免留下一个假失败。
    """
    registry = build_compiler_registry(build_diagnostic_ontology_registry())
    repository, result = _seeded()
    context = QueryContextV1(
        query_id="query-e2e-1",
        raw_query="How many beverages are preferred?",
        query_time="2026-07-31T00:00:00Z",
        current_user_entity_id=None,
        memory_view=_memory_view(repository, result),
        ontology_revision=registry.ontology_revision,
        identity_revision=registry.identity_revision,
        compiler_policy_revision="e2e-query-policy-v1",
    )
    value_scoped = compile_natural_query(
        question="How many beverages are preferred?",
        context=context,
        registry=registry,
        producer=_CountQueryProducer(),
    )
    # 一个 value-distinct 的 count 在编译阶段即被拒绝。
    assert value_scoped.plan is None
    assert "count_requires_canonical_identity" in value_scoped.blocked_reasons


def test_counting_canonical_identities_still_requires_resolution() -> None:
    """Counting individuals must keep demanding resolved identity."""
    plan, execution = _execute_count(distinct_by="canonical_identity")
    assert plan.answer.identity_resolution_required is True
    assert execution.abstained is True
    assert execution.evaluation.reason == "answer_identity_unresolved"
