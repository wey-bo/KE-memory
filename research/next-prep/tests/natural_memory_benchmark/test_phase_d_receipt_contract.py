"""Phase D 的 receipt 必须自证闭环，而不是只报一个答案。

现有 `OpenAIE2ERunReceiptV1` 只有三次模型调用、snapshot 与 answer。Phase D 要求
的证据比这多：写入计数、执行计划、matched facts、trace、replay equality、证据
闭包，以及与 Phase C 同一份 profile hash。缺了这些，一份"通过"的记录无法被独立
复核——读者只能相信结论。

profile 绑定尤其关键：Phase C 资格是在 80a2f472 上取得的，若 Phase D 跑在别的
profile 上，那份资格就不适用于它。
"""

from __future__ import annotations

import pytest

from tools.natural_memory_benchmark.e2e_pipeline import EvidenceBackedAnswerV1


def test_receipt_declares_the_phase_c_profile() -> None:
    """receipt 必须记录 extraction profile，且可与 Phase C 比对。"""
    from tools.natural_memory_benchmark.e2e_openai_runtime import (
        OpenAIE2ERunReceiptV2,
    )

    fields = OpenAIE2ERunReceiptV2.model_fields
    assert "extraction_profile" in fields
    assert "closure_kind" in fields


def test_receipt_carries_the_required_evidence() -> None:
    """调用数、写入数、plan、matched facts、trace、replay、闭包必须齐备。"""
    from tools.natural_memory_benchmark.e2e_openai_runtime import (
        OpenAIE2ERunReceiptV2,
    )

    fields = OpenAIE2ERunReceiptV2.model_fields
    for name in (
        "l1_producer_call_count",
        "l2_producer_call_count",
        "query_call_count",
        "automatic_memory_write_count",
        "observed_write_phases",
        "query_plan",
        "matched_fact_ids",
        "execution_trace",
        "deterministic_replay_verified",
        "evidence_closure",
        "byte_level_recovery_verified",
    ):
        assert name in fields, name


def test_write_counts_are_measured_not_declared() -> None:
    """写入计数必须是测量值，不能是 schema 常量。

    一个无法表达"发生了写入"的字段证明不了任何事——这正是 Phase A 已经修过的
    同一类缺陷，不能在 Phase D 重新引入。
    """
    from tools.natural_memory_benchmark.e2e_openai_runtime import (
        OpenAIE2ERunReceiptV2,
    )

    fields = OpenAIE2ERunReceiptV2.model_fields
    for name in (
        "l1_producer_call_count",
        "l2_producer_call_count",
        "query_call_count",
        "automatic_memory_write_count",
    ):
        assert "Literal" not in repr(fields[name].annotation), name


def test_evidence_closure_binds_answer_to_raw_turns() -> None:
    """证据闭包必须把答案一路绑回原始轮次修订。"""
    from tools.natural_memory_benchmark.e2e_openai_runtime import (
        EvidenceClosureReceiptV1,
    )

    fields = EvidenceClosureReceiptV1.model_fields
    for name in (
        "answer_values",
        "memory_unit_revision_ids",
        "evidence_span_ids",
        "raw_turn_revision_ids",
        "closure_complete",
    ):
        assert name in fields, name


def test_a_profile_mismatch_is_refused() -> None:
    """profile 与 Phase C 不一致时必须拒绝，而不是照样出具通过。"""
    from tools.natural_memory_benchmark.e2e_openai_producers import (
        UNBOUND_LEGACY_PROFILE,
        build_diagnostic_production_policy,
        build_extraction_profile_identity,
    )
    from tools.natural_memory_benchmark.e2e_openai_runtime import (
        assert_phase_d_profile_matches_qualification,
    )
    from tools.natural_memory_benchmark.l1_ontology_linking import (
        build_diagnostic_ontology_registry,
    )

    registry = build_diagnostic_ontology_registry()
    profile = build_extraction_profile_identity(
        registry=registry,
        policy=build_diagnostic_production_policy(registry),
    )
    # 同一 profile 可用。
    assert_phase_d_profile_matches_qualification(
        qualified_profile_sha256=profile.profile_sha256,
        execution_profile=profile,
    )
    with pytest.raises(ValueError, match="profile"):
        assert_phase_d_profile_matches_qualification(
            qualified_profile_sha256="0" * 64,
            execution_profile=profile,
        )
    # legacy 未绑定的 profile 不得用于 Phase D。
    with pytest.raises(ValueError, match="unbound"):
        assert_phase_d_profile_matches_qualification(
            qualified_profile_sha256=UNBOUND_LEGACY_PROFILE.profile_sha256,
            execution_profile=UNBOUND_LEGACY_PROFILE,
        )


def test_closure_kind_is_the_authorized_wording() -> None:
    """结论措辞只能是 controlled_automatic_e2e_closure。"""
    from tools.natural_memory_benchmark.e2e_openai_runtime import (
        OpenAIE2ERunReceiptV2,
    )

    annotation = repr(OpenAIE2ERunReceiptV2.model_fields["closure_kind"].annotation)
    assert "controlled_automatic_e2e_closure" in annotation
    for forbidden in ("production_ready", "benchmark_ready", "extraction_qualified"):
        assert forbidden not in annotation


def test_frozen_v1_receipts_still_load() -> None:
    """v1 receipt 必须仍可读：冻结记录不得因新增字段而失效。"""
    from tools.natural_memory_benchmark.e2e_openai_runtime import (
        OpenAIE2ERunReceiptV1,
        load_e2e_receipt,
    )

    payload = {
        "schema_version": "openai-e2e-run-receipt-v1",
        "workflow_run_id": "run-openai-e2e-legacy",
        "requested_model": "test-model",
        "model_calls": [
            {
                "stage": stage,
                "requested_model": "test-model",
                "response_model": "test-model",
                "request_sha256": "0" * 64,
                "response_sha256": "1" * 64,
                "attempts": 1,
            }
            for stage in ("l1", "l2", "query")
        ],
        "snapshot": {
            "repository_path": "/tmp/legacy.git",
            "checkpoint_id": "checkpoint-legacy",
            "git_commit": "a" * 40,
            "previous_git_commit": "b" * 40,
            "verification_status": "valid",
        },
        # 用真实模型构造 answer，避免夹具与实际契约不一致。
        "answer": EvidenceBackedAnswerV1(
            query_id="query-legacy",
            answer_values=("memory:CoffeeBeverage",),
            evidence_spans=(),
            closure_complete=True,
            abstained=False,
            authority_sha256="c" * 64,
        ).model_dump(mode="json"),
    }
    loaded = load_e2e_receipt(payload)
    assert isinstance(loaded, OpenAIE2ERunReceiptV1)
