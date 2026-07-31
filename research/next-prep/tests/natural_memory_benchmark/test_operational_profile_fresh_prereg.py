"""Phase C 预注册必须在数据存在之前就把边界钉死。

这些测试守的是"事后不能重新解释"：覆盖要求、职责隔离、失败协议与结论边界都在
预注册里，而不是等分数出来再补叙。最关键的一条是 gold 泄漏检查必须真的会拒绝
——如果 proposer 能读到 gold，绿色分数什么也不证明，而这种失败在分数里看不出来。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.natural_memory_benchmark.operational_profile_fresh_prereg import (
    PREREGISTERED_L1_OPERATOR_SENSES,
    PREREGISTERED_L2_OPERATOR_SENSES,
    REQUIRED_L1_COVERAGE,
    REQUIRED_L2_COVERAGE,
    OperationalProfileFreshPreregistrationV1,
    assert_gold_not_exposed,
    build_operational_profile_fresh_preregistration,
)

WORKSPACE = Path(__file__).resolve().parents[2]


def _prereg():
    return build_operational_profile_fresh_preregistration(
        workspace_root=WORKSPACE,
        dataset_id="operational-profile-fresh-hidden-v1",
        frozen_at="2026-07-31T00:00:00Z",
    )


def test_preregistration_binds_the_operational_profile() -> None:
    """预注册必须绑定实际会用的 profile 哈希，而不是自报一个名字。"""
    from tools.natural_memory_benchmark.e2e_openai_producers import (
        build_diagnostic_production_policy,
        build_extraction_profile_identity,
    )
    from tools.natural_memory_benchmark.l1_ontology_linking import (
        build_diagnostic_ontology_registry,
    )

    registry = build_diagnostic_ontology_registry()
    profile = build_extraction_profile_identity(
        registry=registry,
        policy=build_diagnostic_production_policy(registry),
    )
    prereg = _prereg()
    assert prereg.profile_id == "operational-diagnostic-profile-v1"
    assert prereg.profile_sha256 == profile.profile_sha256
    assert prereg.policy_sha256 == profile.policy_sha256
    assert prereg.ontology_registry_sha256 == profile.ontology_registry_sha256


def test_preregistration_fixes_the_narrow_scope() -> None:
    """窄域范围写死在预注册里，评测期间扩词表会成为可检测偏离。"""
    prereg = _prereg()
    assert prereg.l1_operator_senses == PREREGISTERED_L1_OPERATOR_SENSES
    assert prereg.l2_operator_senses == PREREGISTERED_L2_OPERATOR_SENSES
    assert len(prereg.l1_operator_senses) == 3
    assert len(prereg.l2_operator_senses) == 1


def test_preregistration_states_required_coverage() -> None:
    """覆盖要求必须先于数据固定，否则可以按已有数据反推覆盖声明。"""
    prereg = _prereg()
    assert prereg.required_l1_coverage == REQUIRED_L1_COVERAGE
    assert prereg.required_l2_coverage == REQUIRED_L2_COVERAGE
    assert "must_refuse_or_abstain" in prereg.required_l1_coverage
    assert "critical_false_emission" in prereg.required_l2_coverage


def test_preregistration_records_role_separation() -> None:
    """proposer 不得读 authority/gold，这一点必须是记录在案的约束。"""
    prereg = _prereg()
    roles = prereg.role_separation
    assert roles.proposer_reads == ("public",)
    assert roles.proposer_may_read_authority_or_gold is False
    assert "gold" not in roles.proposer_reads
    assert "gold" in roles.scorer_reads
    assert "gold" in roles.author_writes


def test_preregistration_forbids_reusing_the_misnamed_dataset() -> None:
    """那个名字带 operational 但实际是 fresh-v3 hidden 提案的目录不得复用。"""
    prereg = _prereg()
    assert (
        "typed-extractor-v3-fresh-hidden-v1-codex-gpt-operational-v1"
        in prereg.forbidden_input_reuse
    )
    assert "typed-extractor-v3-fresh-hidden-v1" in prereg.forbidden_input_reuse


def test_preregistration_fixes_the_failure_protocol() -> None:
    """失败只能走 RCA 循环，不能靠改 gold 或扩词表修绿。"""
    prereg = _prereg()
    policy = prereg.execution_policy
    assert policy.requests_per_layer == 1
    assert policy.retry_same_attempt is False
    assert policy.authoritative_writes is False
    assert policy.failure_protocol[0] == "freeze"
    assert "root_cause_analysis" in policy.failure_protocol
    for forbidden in ("edit_gold", "widen_vocabulary", "change_scoring_rules"):
        assert forbidden in policy.forbidden_repairs


def test_preregistration_fixes_the_conclusion_boundary() -> None:
    """通过后只能是窄域结论，且不改变 fresh-v3 的状态。"""
    prereg = _prereg()
    boundary = prereg.conclusion_boundary
    assert boundary.qualified_status == "operational_diagnostic_profile_qualified"
    assert boundary.implies_fresh_v3_qualified is False
    assert boundary.implies_general_extraction_qualified is False
    assert boundary.implies_production_ready is False
    assert boundary.implies_benchmark_ready is False
    assert boundary.fresh_v3_status_unchanged == "not_qualified"


def test_preregistration_hash_self_verifies() -> None:
    """改写预注册字段后必须无法构造出来。"""
    prereg = _prereg()
    payload = prereg.model_dump(mode="json")
    payload["dataset_id"] = "something-else"
    with pytest.raises(ValueError, match="preregistration hash"):
        OperationalProfileFreshPreregistrationV1.model_validate(payload)


def test_gold_inside_a_proposer_directory_is_refused(tmp_path: Path) -> None:
    """gold 落在 proposer 可读目录内必须被拒绝。"""
    public_dir = tmp_path / "public"
    public_dir.mkdir()
    gold = public_dir / "gold-l1.json"
    gold.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="proposer-readable"):
        assert_gold_not_exposed(
            gold_paths=(gold,),
            proposer_readable_paths=(public_dir,),
            prompt_text="no gold here",
            environment={},
        )


def test_gold_named_in_the_prompt_is_refused(tmp_path: Path) -> None:
    """prompt 里提到 gold 文件名同样必须被拒绝。"""
    gold = tmp_path / "gold-l1.json"
    gold.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="prompt"):
        assert_gold_not_exposed(
            gold_paths=(gold,),
            proposer_readable_paths=(tmp_path / "public",),
            prompt_text="please consult gold-l1.json",
            environment={},
        )


def test_gold_named_in_the_environment_is_refused(tmp_path: Path) -> None:
    """环境变量泄漏 gold 路径必须被拒绝。"""
    gold = tmp_path / "gold-l2.json"
    gold.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="environment"):
        assert_gold_not_exposed(
            gold_paths=(gold,),
            proposer_readable_paths=(tmp_path / "public",),
            prompt_text="clean",
            environment={"KE_MEM_HINT": "/somewhere/gold-l2.json"},
        )


def test_a_clean_separation_is_accepted(tmp_path: Path) -> None:
    """隔离正确时不得误报，否则这道检查会被绕过去。"""
    public_dir = tmp_path / "public"
    public_dir.mkdir()
    private_dir = tmp_path / "private"
    private_dir.mkdir()
    gold = private_dir / "gold-l1.json"
    gold.write_text("{}", encoding="utf-8")
    assert_gold_not_exposed(
        gold_paths=(gold,),
        proposer_readable_paths=(public_dir,),
        prompt_text="only public cases are provided",
        environment={"OPENAI_MODEL": "some-model"},
    )
