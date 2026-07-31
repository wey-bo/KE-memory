"""资格结论只能迁移到同一个 extraction profile。

实测已确认 qualification 与 production 在**同一层**上词汇表零交集：

* L1：qualification 24 对 operator/sense，production 3 对，交集 0；
* L2：qualification 18 对，production 1 对，交集 0。

也就是说 fresh-v3 通过并不能推出 production 通过——两条链理解的是两套语义。
共享 prompt、producer、runner 只消除了工程重复，不能产生资格迁移。

这里先把这件事变成**可检测**的：给 extraction profile 一个显式身份（profile_id
加上词汇、policy 与 producer 契约的哈希），并要求资格结论迁移前两侧 profile 身份
必须一致。没有这层绑定，词表漂移只能靠人工比对发现，而这正是它此前一直没被发现
的原因。

注意 L1 与 L2 **跨层**零交集不是缺陷：L1 描述原子事实，L2 描述跨轮抽象，本就
不该共用同一组算子。所以这里比较的始终是同层 profile。
"""

from __future__ import annotations

import pytest

from tools.natural_memory_benchmark.e2e_openai_producers import (
    build_diagnostic_production_policy,
)
from tools.natural_memory_benchmark.l1_ontology_linking import (
    build_diagnostic_ontology_registry,
)


def _profile():
    from tools.natural_memory_benchmark.e2e_openai_producers import (
        build_extraction_profile_identity,
    )

    registry = build_diagnostic_ontology_registry()
    return build_extraction_profile_identity(
        registry=registry,
        policy=build_diagnostic_production_policy(registry),
    )


def test_profile_states_its_scope_honestly() -> None:
    """profile 必须自称 diagnostic，而不是冒充完整生产本体。

    当前 production 只有 3 个 L1 算子和 1 个 L2 算子，明确属于受控诊断范围。
    把它标成 production-ready 会让一份窄域资格被读成一般能力。
    """
    profile = _profile()
    assert profile.scope == "diagnostic"
    assert profile.profile_id == "operational-diagnostic-profile-v1"


def test_profile_records_the_layer_vocabularies_separately() -> None:
    """L1 与 L2 的词汇表必须分开记录。

    两层本就不该共用算子，所以合并成一个哈希会让跨层差异和同层漂移无法区分。
    """
    profile = _profile()
    assert profile.l1_operator_senses == (
        ("add_ingredient", "add_ingredient"),
        ("drink", "consume_beverage"),
        ("prefer", "preference_theme"),
    )
    assert profile.l2_operator_senses == (("prefer", "preference_theme"),)
    assert profile.l1_vocabulary_sha256 != profile.l2_vocabulary_sha256


def test_changing_the_vocabulary_changes_the_profile_hash() -> None:
    """词表变了 profile 哈希必须跟着变，否则漂移不可检测。"""
    registry = build_diagnostic_ontology_registry()
    policy = build_diagnostic_production_policy(registry)
    baseline = _profile()

    from tools.natural_memory_benchmark.e2e_openai_producers import (
        build_extraction_profile_identity,
    )

    # policy 与 registry 必须彼此覆盖，所以只删 policy 一侧会被正确拒绝；
    # 这里改一个仍然自洽的维度，验证哈希确实随词表/策略变化。
    widened = policy.model_copy(
        update={"allowed_polarities": ["positive"]}
    )
    changed = build_extraction_profile_identity(
        registry=registry, policy=widened
    )
    assert changed.policy_sha256 != baseline.policy_sha256
    assert changed.profile_sha256 != baseline.profile_sha256


def test_qualification_results_do_not_transfer_across_profiles() -> None:
    """profile 身份不一致时，资格迁移必须被拒绝。

    这是这层绑定存在的理由：fresh-v3 的 24/18 词表与 production 的 3/1 词表
    零交集，所以它的通过结论不得被当作 production 的通过结论。
    """
    from tools.natural_memory_benchmark.e2e_openai_producers import (
        assert_qualification_transferable,
    )

    profile = _profile()
    # 同一 profile 可以迁移。
    assert_qualification_transferable(
        qualified_profile=profile, execution_profile=profile
    )

    # profile 现在自校验哈希，所以伪造一份要绕过校验器才能构造出来——这正是
    # 迁移检查必须自己重算哈希的理由。
    foreign = profile.model_construct(
        **{
            **profile.model_dump(),
            "profile_id": "fresh-v3-qualification-profile",
            "profile_sha256": "0" * 64,
        }
    )
    with pytest.raises(ValueError, match="profile"):
        assert_qualification_transferable(
            qualified_profile=foreign, execution_profile=profile
        )


def test_the_measured_zero_overlap_is_stated_as_a_fact() -> None:
    """把实测的零交集固定下来，避免它再次被静默假定为已覆盖。

    这条测试不是要求交集为零，而是要求“当前交集为零”这一事实被显式记录：
    一旦有人让两侧收敛，这条测试会失败并提醒更新结论。
    """
    from tools.natural_memory_benchmark.e2e_openai_producers import (
        QUALIFICATION_PROFILE_L1_OPERATOR_SENSES,
        QUALIFICATION_PROFILE_L2_OPERATORS,
    )

    profile = _profile()
    l1_overlap = set(profile.l1_operator_senses) & set(
        QUALIFICATION_PROFILE_L1_OPERATOR_SENSES
    )
    l2_overlap = {
        operator for operator, _sense in profile.l2_operator_senses
    } & set(QUALIFICATION_PROFILE_L2_OPERATORS)
    assert l1_overlap == set(), l1_overlap
    assert l2_overlap == set(), l2_overlap
    assert len(QUALIFICATION_PROFILE_L1_OPERATOR_SENSES) == 24
    assert len(QUALIFICATION_PROFILE_L2_OPERATORS) == 18
