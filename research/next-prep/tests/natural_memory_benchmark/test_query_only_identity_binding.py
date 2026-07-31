"""query-only 也必须绑定它恢复出来的那份 identity snapshot。

pipeline 现在提交带 identity 的 bundle，query-only 却仍然用不绑定 snapshot 的
registry 编译并构建执行快照。于是恢复出来的实体被报告为 unresolved，一个
count 只能弃权——Phase D 要求 fact / count / abstain 落在同一份记忆上，而
query-only 是 Phase A 已经通过的那条入口，两边必须看到同一份 identity。
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from tools.natural_memory_benchmark.e2e_openai_runtime import (
    recover_authoritative_checkpoint,
)
from tools.natural_memory_benchmark.e2e_pipeline import (
    build_compiler_registry,
    run_e2e_pipeline,
)
from tools.natural_memory_benchmark.identity_resolution import (
    IdentityAwareMemoryBundleV4,
)
from tools.natural_memory_benchmark.l1_ontology_linking import (
    build_diagnostic_ontology_registry,
)
from tools.natural_memory_benchmark.query_execution_snapshot_adapter import (
    build_query_execution_snapshot,
)

from test_e2e_pipeline_smoke import (  # noqa: F401
    _chat_response,
    _L1Producer,
    _L2Producer,
    _QueryProducer,
    _SequencedOpener,
    _turns,
)


def _seeded():
    root = Path(tempfile.mkdtemp())
    repository = root / "query-only-identity-history.git"
    result = run_e2e_pipeline(
        turns=_turns(),
        l1_producer=_L1Producer(),
        l2_producer=_L2Producer(),
        query_producer=_QueryProducer(),
        repository_path=repository,
        question="What beverage is preferred?",
    )
    return repository, result


def test_recovery_reads_back_the_identity_the_pipeline_committed() -> None:
    """恢复出来的 bundle 必须仍然带着提交时的 identity。"""
    repository, result = _seeded()
    recovered = recover_authoritative_checkpoint(
        repository_path=repository,
        expected_git_commit=result.snapshot.git_commit,
        expected_checkpoint_id=result.snapshot.checkpoint_id,
    )
    assert isinstance(recovered.bundle, IdentityAwareMemoryBundleV4)
    assert (
        recovered.bundle.identity_snapshots
        == result.bundle.identity_snapshots
    )


def test_query_only_entry_answers_a_count() -> None:
    """count 必须能走通真实的 query-only 入口。

    这是 Phase D 的要求：fact 与 count 在同一条已通过的入口上作答，而不是靠
    测试自行绑定 snapshot。入口若不绑定恢复出的 snapshot，实体会是 unresolved，
    执行器以 answer_identity_unresolved 弃权。
    """
    import json

    from tools.natural_memory_benchmark.e2e_openai_runtime import (
        run_openai_query_only,
    )
    from tools.natural_memory_benchmark.query_compiler_v2 import (
        QueryDraftRequestV1,
    )

    repository, result = _seeded()

    class _CountProducer(_QueryProducer):
        def produce(self, request):  # type: ignore[no-untyped-def]
            draft = super().produce(request)
            answer = draft.answer.model_copy(
                update={"kind": "count", "distinct_by": "canonical_identity"}
            )
            return draft.model_copy(update={"answer": answer})

    payload = (
        _CountProducer()
        .produce(
            QueryDraftRequestV1(
                query_id="query-e2e-1",
                raw_query="How many beverages are preferred?",
                query_time="2026-07-31T00:00:00Z",
                compiler_policy_revision="e2e-query-policy-v1",
            )
        )
        .model_dump(mode="json")
    )

    outcome = run_openai_query_only(
        question="How many beverages are preferred?",
        query_time="2026-07-31T00:00:00Z",
        repository_path=repository,
        expected_git_commit=result.snapshot.git_commit,
        expected_checkpoint_id=result.snapshot.checkpoint_id,
        result_path=repository.with_name("count-query-only-result.json"),
        base_url="https://model.invalid/v1",
        api_key="credential-that-must-not-enter-artifacts",
        model="test-model-response",
        timeout_seconds=37,
        max_attempts=1,
        opener=_SequencedOpener([_chat_response(payload)]),
    )
    execution = outcome.pipeline.execution
    assert execution.evaluation.abstained is False, execution.evaluation.reason
    assert execution.evaluation.count_value == 1
    assert execution.closure_complete is True
    # 入口自己的 replay 相等检查也必须在 count 路径上成立。
    assert outcome.pipeline.deterministic_replay == execution
    # 凭据不得进入产物。
    written = json.loads(
        repository.with_name("count-query-only-result.json").read_text("utf-8")
    )
    assert "credential-that-must-not-enter-artifacts" not in json.dumps(written)


def test_recovered_snapshot_reports_resolved_identity() -> None:
    """绑定恢复出的 snapshot 后，实体必须被报告为 resolved。

    这是 count 在 query-only 入口可作答的前置条件：执行器要求每个答案值都
    `resolved`，否则以 answer_identity_unresolved 弃权。
    """
    repository, result = _seeded()
    recovered = recover_authoritative_checkpoint(
        repository_path=repository,
        expected_git_commit=result.snapshot.git_commit,
        expected_checkpoint_id=result.snapshot.checkpoint_id,
    )
    identity_snapshot = recovered.bundle.identity_snapshots[0]
    registry = build_compiler_registry(
        build_diagnostic_ontology_registry(),
        identity_snapshot=identity_snapshot,
    )
    snapshot = build_query_execution_snapshot(
        repository_path=repository,
        bundle=recovered.bundle,
        bundle_history_artifact=recovered.bundle_history_artifact,
        turn_bundles=list(recovered.turn_bundles),
        registry=registry,
        identity_snapshot_id=identity_snapshot.snapshot_id,
    )
    assert snapshot.identity_snapshot_id == identity_snapshot.snapshot_id
    assert set(snapshot.identity_status.values()) == {"resolved"}, (
        snapshot.identity_status
    )
