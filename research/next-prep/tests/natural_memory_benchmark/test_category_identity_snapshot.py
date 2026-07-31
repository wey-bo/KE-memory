"""category-only 作用域也必须有真实的 identity snapshot。

`compile_natural_query` 对任何 count 都要求 `canonical_identity` 去重，执行器则
要求每个答案值都是 `resolved`。production 不构建 identity snapshot，于是
`identity_status` 恒为 unresolved，count 只能弃权——Phase D 的 count 场景因此
不可达，且原因与模型质量无关。

category-only 的实体就是本体概念标识符，彼此天然区分：没有两个表面指向同一个
个体需要合并。所以正确做法不是放宽 count 的契约，而是把这一事实如实表达成一份
可重建、可审计的 identity snapshot：每个概念自成一个 canonical group，
`keep_distinct` 决策记录它们互不相同，证据闭包回指真实的 L1 单元与来源修订。

这样 compiler 契约不变，已冻结的 dev-qualification gold 也不受影响。
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from tools.natural_memory_benchmark.e2e_pipeline import (
    build_compiler_registry,
    run_e2e_pipeline,
)
from tools.natural_memory_benchmark.identity_resolution import (
    IdentityAwareMemoryBundleV4,
    assess_identity_bundle_integrity,
    build_identity_snapshot,
)
from tools.natural_memory_benchmark.l1_ontology_linking import (
    build_diagnostic_ontology_registry,
)
from tools.natural_memory_benchmark.query_execution_snapshot_adapter import (
    build_query_execution_snapshot,
)

from test_e2e_pipeline_smoke import (  # noqa: F401
    _L1Producer,
    _L2Producer,
    _QueryProducer,
    _turns,
)


def _seeded():
    root = Path(tempfile.mkdtemp())
    repository = root / "category-identity-history.git"
    result = run_e2e_pipeline(
        turns=_turns(),
        l1_producer=_L1Producer(),
        l2_producer=_L2Producer(),
        query_producer=_QueryProducer(),
        repository_path=repository,
        question="What beverage is preferred?",
    )
    return repository, result


def test_category_scope_promotes_to_an_identity_aware_bundle() -> None:
    """category-only bundle 可以升级成带 identity 的 bundle 且完整性有效。"""
    from tools.natural_memory_benchmark.e2e_pipeline import (
        promote_to_category_identity_bundle,
    )

    _repository, result = _seeded()
    promoted = promote_to_category_identity_bundle(
        bundle=result.bundle,
        ontology=build_diagnostic_ontology_registry(),
    )
    assert isinstance(promoted, IdentityAwareMemoryBundleV4)
    report = assess_identity_bundle_integrity(promoted)
    assert report.valid, report.errors
    # 原有的记忆内容不被改动。
    assert promoted.bundle_id == result.bundle.bundle_id
    assert promoted.l1_units == result.bundle.l1_units
    assert promoted.l2_units == result.bundle.l2_units
    assert promoted.unit_revisions == result.bundle.unit_revisions


def test_each_category_entity_is_its_own_canonical_group() -> None:
    """category 实体彼此天然区分，各自成为一个 canonical group。"""
    from tools.natural_memory_benchmark.e2e_pipeline import (
        promote_to_category_identity_bundle,
    )

    _repository, result = _seeded()
    promoted = promote_to_category_identity_bundle(
        bundle=result.bundle,
        ontology=build_diagnostic_ontology_registry(),
    )
    assert len(promoted.identity_snapshots) == 1
    snapshot = promoted.identity_snapshots[0]
    assert snapshot.unresolved_groups == []
    for group in snapshot.groups:
        assert group.member_entity_ids == [group.canonical_entity_id]
    # snapshot 必须可由 builder 精确重建，否则完整性校验会判定为 stale。
    rebuilt = build_identity_snapshot(
        promoted,
        scoped_entity_ids=snapshot.scoped_entity_ids,
        policy_version=snapshot.policy_version,
    )
    assert rebuilt == snapshot


def test_execution_snapshot_reports_resolved_identity() -> None:
    """升级后执行快照必须把 category 实体报告为 resolved。"""
    from tools.natural_memory_benchmark.e2e_pipeline import (
        promote_to_category_identity_bundle,
    )

    from tools.natural_memory_benchmark.e2e_pipeline import (
        commit_authoritative_snapshot,
    )

    _repository, result = _seeded()
    ontology = build_diagnostic_ontology_registry()
    promoted = promote_to_category_identity_bundle(
        bundle=result.bundle,
        ontology=ontology,
    )
    # 升级必须发生在提交之前，否则 Git 中的 artifact 与 bundle 不一致。
    promoted_repository = Path(tempfile.mkdtemp()) / "promoted-history.git"
    committed = commit_authoritative_snapshot(
        repository_path=promoted_repository,
        bundle=promoted,
        turn_bundles=list(result.turn_bundles),
        transaction_time="2026-07-31T00:00:30Z",
    )
    registry = build_compiler_registry(
        ontology, identity_snapshot=promoted.identity_snapshots[0]
    )
    snapshot = build_query_execution_snapshot(
        repository_path=promoted_repository,
        bundle=promoted,
        bundle_history_artifact=committed.bundle_history_artifact,
        turn_bundles=list(result.turn_bundles),
        registry=registry,
        identity_snapshot_id=promoted.identity_snapshots[0].snapshot_id,
    )
    assert snapshot.identity_snapshot_id == (
        promoted.identity_snapshots[0].snapshot_id
    )
    assert set(snapshot.identity_status.values()) == {"resolved"}, (
        snapshot.identity_status
    )
