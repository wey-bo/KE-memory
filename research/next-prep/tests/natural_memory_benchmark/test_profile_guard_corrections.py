"""profile guard 的六项修正：让资格迁移只在真正同一 profile 上成立。

首版 profile 身份把漂移变成了可检测的事实，但它本身还有六个可被绕过的地方：

1. `production-diagnostic-profile-v1` 这个名字仍暗示 production；实际范围是受控
   运行诊断，应命名为 `operational-diagnostic-profile-v1`。
2. L2 身份只记了 operator，没记 sense、abstraction method 与 closure pattern。
   这三项都会改变 L2 的语义空间，漏掉它们等于允许 L2 契约在同一哈希下改变。
3. profile 哈希不自校验：手工改一个字段仍能构造出"看起来合法"的 profile。
   而且必须绑定 L1 profile 哈希，否则 L1 变了 L2 侧察觉不到。
4. 抽取用的 profile 与查询执行用的 profile 混为一谈。两者可以不同（查询侧不做
   抽取），必须分开记录才能各自校验。
5. legacy v8 snapshot 没有 profile，必须显式标记 `unbound_legacy` 并禁止参与
   资格迁移，而不是被当成"恰好匹配"。
6. 精确迁移测试：伪造哈希、L2 sense 变化、legacy unbound 都必须被拒绝。
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


def test_profile_id_names_the_operational_diagnostic_scope() -> None:
    """名字里不得留下 production 暗示。"""
    profile = _profile()
    assert profile.profile_id == "operational-diagnostic-profile-v1"
    assert profile.scope == "diagnostic"


def test_l2_identity_carries_sense_method_and_closure() -> None:
    """L2 身份必须完整覆盖决定其语义空间的三项。"""
    profile = _profile()
    assert profile.l2_operator_senses == (
        ("prefer", "preference_theme"),
    )
    assert profile.l2_abstraction_methods == ("preference_aggregation",)
    assert profile.l2_closure_patterns == ("multi_evidence_set",)


def test_changing_only_the_l2_sense_changes_the_profile_hash() -> None:
    """只改 L2 sense 也必须改变 profile 哈希。

    这是首版最容易被绕过的一点：sense 不进哈希时，L2 可以换一套语义而 profile
    哈希不变，于是一份旧资格会被误认为覆盖了新语义。
    """
    from tools.natural_memory_benchmark.e2e_openai_producers import (
        build_extraction_profile_identity,
    )

    registry = build_diagnostic_ontology_registry()
    policy = build_diagnostic_production_policy(registry)
    baseline = build_extraction_profile_identity(
        registry=registry, policy=policy
    )

    renamed_rules = [
        item.model_copy(update={"predicate_sense": "preference_theme_v2"})
        if item.canonical_operator == "prefer"
        else item
        for item in registry.predicate_role_constraints
    ]
    shifted_registry = registry.model_copy(
        update={"predicate_role_constraints": renamed_rules}
    )
    shifted = build_extraction_profile_identity(
        registry=shifted_registry,
        policy=policy,
        validate_policy=False,
    )
    assert shifted.l2_operator_senses != baseline.l2_operator_senses
    assert shifted.profile_sha256 != baseline.profile_sha256


def test_profile_hash_self_verifies() -> None:
    """手工改写字段后，profile 必须拒绝被构造出来。"""
    from tools.natural_memory_benchmark.e2e_openai_producers import (
        ExtractionProfileIdentityV1,
    )

    profile = _profile()
    payload = profile.model_dump(mode="json")
    payload["scope"] = "production"
    with pytest.raises(ValueError, match="profile hash"):
        ExtractionProfileIdentityV1.model_validate(payload)


def test_profile_hash_binds_the_l1_profile_hash() -> None:
    """L1 侧变化必须改变整体 profile 哈希。"""
    profile = _profile()
    body = profile.hash_body()
    assert body["l1_vocabulary_sha256"] == profile.l1_vocabulary_sha256
    assert body["l2_vocabulary_sha256"] == profile.l2_vocabulary_sha256


def test_vocabularies_are_sorted_and_deduplicated() -> None:
    """词表必须排序去重，否则同一词表会得到不同哈希。"""
    profile = _profile()
    for vocabulary in (
        profile.l1_operator_senses,
        profile.l2_operator_senses,
        profile.l2_abstraction_methods,
        profile.l2_closure_patterns,
    ):
        listed = list(vocabulary)
        assert listed == sorted(listed), listed
        assert len(listed) == len(set(listed)), listed


def test_a_forged_hash_is_refused_on_transfer() -> None:
    """伪造哈希不得通过迁移检查。"""
    from tools.natural_memory_benchmark.e2e_openai_producers import (
        assert_qualification_transferable,
    )

    profile = _profile()
    forged = profile.model_construct(
        **{**profile.model_dump(), "profile_sha256": "0" * 64}
    )
    with pytest.raises(ValueError, match="profile"):
        assert_qualification_transferable(
            qualified_profile=forged, execution_profile=profile
        )


def test_legacy_unbound_snapshot_cannot_transfer_qualification() -> None:
    """没有 profile 的 legacy v8 snapshot 必须显式 unbound 且禁止迁移。"""
    from tools.natural_memory_benchmark.e2e_openai_producers import (
        UNBOUND_LEGACY_PROFILE,
        assert_qualification_transferable,
    )

    profile = _profile()
    assert UNBOUND_LEGACY_PROFILE.profile_id == "unbound_legacy"
    assert UNBOUND_LEGACY_PROFILE.scope == "unbound_legacy"
    with pytest.raises(ValueError, match="unbound"):
        assert_qualification_transferable(
            qualified_profile=UNBOUND_LEGACY_PROFILE,
            execution_profile=profile,
        )
    with pytest.raises(ValueError, match="unbound"):
        assert_qualification_transferable(
            qualified_profile=profile,
            execution_profile=UNBOUND_LEGACY_PROFILE,
        )


def test_snapshot_and_query_profiles_are_recorded_separately() -> None:
    """抽取 profile 与查询执行 profile 必须分开记录。

    查询侧不做抽取，两者可以不同；混为一个字段就无法分别校验，也无法表达
    "这次查询跑在一份由别的 profile 写出的记忆上"。
    """
    from tools.natural_memory_benchmark.e2e_openai_runtime import (
        OpenAIQueryOnlyReceiptV2,
    )

    fields = OpenAIQueryOnlyReceiptV2.model_fields
    assert "snapshot_extraction_profile" in fields
    assert "query_execution_profile" in fields
    assert "extraction_profile" not in fields
