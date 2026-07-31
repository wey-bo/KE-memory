"""Phase C 向模型公开的契约必须与目标 profile 完全一致。

attempt 1 暴露的合同不一致：`public-l1.json` 声明 modality 为
``['actual', 'requested']``，而 operational-diagnostic-profile-v1 只授权
``actual``，prompt 又要求模型使用公开的 vocabulary。模型据此把"请下次加奶"读作
``requested``——忠于原文、并未声称事件已发生——却因 policy 只允许 ``actual``
而违门。

这不是模型缺陷，而是资格链自己的漂移：**同一个 profile hash 下跑着不同的
prompt 与 policy**，正是 profile guard 要防的假等价，只不过这次发生在 Phase C
自己身上。

因此 vocabulary 必须从冻结的 profile/policy 派生，禁止手写；actual-only 的
profile 下不得向 proposer 声明 requested 可用。
"""

from __future__ import annotations

import pytest

from tools.natural_memory_benchmark.e2e_openai_producers import (
    build_diagnostic_production_policy,
    build_extraction_profile_identity,
)
from tools.natural_memory_benchmark.l1_ontology_linking import (
    build_diagnostic_ontology_registry,
)


def _profile_and_policy():
    registry = build_diagnostic_ontology_registry()
    policy = build_diagnostic_production_policy(registry)
    profile = build_extraction_profile_identity(registry=registry, policy=policy)
    return registry, policy, profile


def test_vocabulary_is_derived_from_the_policy() -> None:
    """公开 vocabulary 必须由 policy 派生，而不是手写常量。"""
    from tools.natural_memory_benchmark.operational_profile_fresh_materialization import (
        build_allowed_vocabulary,
    )

    registry, policy, _profile = _profile_and_policy()
    vocabulary = build_allowed_vocabulary(registry=registry, policy=policy)
    assert vocabulary["modalities"] == [
        item.modality for item in policy.modality_time_policies
    ]
    assert vocabulary["polarities"] == sorted(policy.allowed_polarities)
    assert vocabulary["canonical_operators"] == sorted(
        {item.canonical_operator for item in policy.l1_operator_kind_bindings}
    )


def test_an_unauthorized_modality_is_never_offered() -> None:
    """actual-only 的 policy 下不得公开 requested。

    这是 attempt 1 的直接根因：模型用了被告知可用的取值。
    """
    from tools.natural_memory_benchmark.operational_profile_fresh_materialization import (
        build_allowed_vocabulary,
    )

    registry, policy, _profile = _profile_and_policy()
    vocabulary = build_allowed_vocabulary(registry=registry, policy=policy)
    authorized = {item.modality for item in policy.modality_time_policies}
    assert authorized == {"actual"}
    assert "requested" not in vocabulary["modalities"]
    assert set(vocabulary["modalities"]) == authorized


def test_published_vocabulary_drift_is_refused() -> None:
    """公开 vocabulary 与 policy 不一致时必须拒绝。"""
    from tools.natural_memory_benchmark.operational_profile_fresh_materialization import (
        assert_vocabulary_matches_policy,
    )

    registry, policy, _profile = _profile_and_policy()
    from tools.natural_memory_benchmark.operational_profile_fresh_materialization import (
        build_allowed_vocabulary,
    )

    # 从合法词表出发，只把 modality 改成 attempt 1 中出现的漂移取值，
    # 这样失败原因必然是 modality 而不是别的键。
    drifted = dict(build_allowed_vocabulary(registry=registry, policy=policy))
    drifted["modalities"] = ["actual", "requested"]
    with pytest.raises(ValueError, match="modalit"):
        assert_vocabulary_matches_policy(
            vocabulary=drifted, registry=registry, policy=policy
        )


def test_the_prompt_forbids_converting_to_actual() -> None:
    """prompt 必须写明：只支持 requested/planned/hypothetical 时应弃权。"""
    from tools.natural_memory_benchmark.operational_profile_fresh_runner import (
        build_l1_system_prompt,
    )

    registry, policy, _profile = _profile_and_policy()
    prompt = build_l1_system_prompt(registry=registry, policy=policy)
    lowered = prompt.casefold()
    assert "abstain" in lowered
    for word in ("requested", "planned", "hypothetical"):
        assert word in lowered, word
    assert "actual" in lowered


def test_the_prompt_only_names_authorized_modalities_as_usable() -> None:
    """prompt 公布的可用模态必须与 policy 一致。"""
    from tools.natural_memory_benchmark.operational_profile_fresh_runner import (
        build_l1_system_prompt,
        prompt_declared_modalities,
    )

    registry, policy, _profile = _profile_and_policy()
    prompt = build_l1_system_prompt(registry=registry, policy=policy)
    assert prompt_declared_modalities(prompt) == {"actual"}


def test_prompt_and_vocabulary_bind_the_profile_hash() -> None:
    """prompt、vocabulary 与 policy hash 必须与目标 profile 一致。

    否则又会出现"同 profile hash、不同 prompt/policy"的假等价。
    """
    from tools.natural_memory_benchmark.operational_profile_fresh_runner import (
        build_phase_c_contract_binding,
    )

    registry, policy, profile = _profile_and_policy()
    binding = build_phase_c_contract_binding(
        layer="l1", registry=registry, policy=policy
    )
    assert binding["profile_id"] == profile.profile_id
    assert binding["profile_sha256"] == profile.profile_sha256
    assert binding["policy_sha256"] == profile.policy_sha256
    assert binding["vocabulary_modalities"] == ["actual"]
    assert binding["prompt_sha256"]


def test_binding_refuses_a_mismatched_profile() -> None:
    """policy 与 profile 不一致时，绑定必须失败而不是静默通过。"""
    from tools.natural_memory_benchmark.operational_profile_fresh_runner import (
        build_phase_c_contract_binding,
    )

    registry, policy, _profile = _profile_and_policy()
    widened = policy.model_copy(
        update={
            "modality_time_policies": [
                *policy.modality_time_policies,
                policy.modality_time_policies[0].model_copy(
                    update={"modality": "requested"}
                ),
            ]
        }
    )
    binding = build_phase_c_contract_binding(
        layer="l1", registry=registry, policy=widened
    )
    # 扩了 policy 就必须得到不同的 policy hash 与不同的公开模态，
    # 这样"同 hash 不同 prompt"无法成立。
    assert binding["vocabulary_modalities"] == ["actual", "requested"]
    assert binding["policy_sha256"] != _profile_and_policy()[2].policy_sha256
