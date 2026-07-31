"""硬门必须看模型实际写了什么模态，而不只看它是否产出。

attempt 1 的 requested 例被计成 fabrication，因为判定只比较"gold 非产出 / 模型
产出"。但该提案写的是 ``modality=requested`` —— 忠于"请下次加奶"，并未声称事件
已发生。把它与"把条件句写成 actual"归为一类，等于用同一个数字掩盖两种完全不同
的错误。

区分之后仍然不放松任何东西：
* 写 ``actual`` 而原文不支持 → 硬门失败；
* 忠实写 ``requested``/``planned``/``hypothetical`` → policy scope 分歧，只报告；
* 但 admission 与 materialization 必须继续拒绝 requested，也就是它照样进不了
  权威记忆。这不是降低标准，而是让判定执行 manifest 里已经冻结的规则。
"""

from __future__ import annotations

import pytest

from tools.natural_memory_benchmark.e2e_openai_producers import (
    build_diagnostic_production_policy,
)
from tools.natural_memory_benchmark.l1_ontology_linking import (
    build_diagnostic_ontology_registry,
)


def _policy():
    registry = build_diagnostic_ontology_registry()
    return registry, build_diagnostic_production_policy(registry)


def test_actual_emission_against_non_emission_gold_is_a_fabrication() -> None:
    """把原文不支持的事情写成 actual，仍然是硬门失败。"""
    from tools.natural_memory_benchmark.operational_profile_fresh_authoring import (
        classify_emission_outcome,
    )

    _registry, policy = _policy()
    assert (
        classify_emission_outcome(
            expected_decision="abstain",
            observed_decision="emit_l1",
            observed_modality="actual",
            policy=policy,
        )
        == "raw_semantic_false_emission"
    )


def test_a_faithful_requested_emission_is_a_policy_scope_disagreement() -> None:
    """忠实写 requested 不得记作 fabrication。"""
    from tools.natural_memory_benchmark.operational_profile_fresh_authoring import (
        classify_emission_outcome,
    )

    _registry, policy = _policy()
    assert (
        classify_emission_outcome(
            expected_decision="abstain",
            observed_decision="emit_l1",
            observed_modality="requested",
            policy=policy,
        )
        == "policy_scope_disagreement"
    )


def test_other_unauthorized_modalities_are_also_scope_disagreements() -> None:
    """planned / hypothetical 同理：它们没有声称事件已发生。"""
    from tools.natural_memory_benchmark.operational_profile_fresh_authoring import (
        classify_emission_outcome,
    )

    _registry, policy = _policy()
    for modality in ("planned", "hypothetical", "recommended"):
        assert (
            classify_emission_outcome(
                expected_decision="abstain",
                observed_decision="emit_l1",
                observed_modality=modality,
                policy=policy,
            )
            == "policy_scope_disagreement"
        )


def test_an_authorized_emission_matching_gold_is_a_match() -> None:
    """gold 要求产出且模型以授权模态产出时，不得报成问题。"""
    from tools.natural_memory_benchmark.operational_profile_fresh_authoring import (
        classify_emission_outcome,
    )

    _registry, policy = _policy()
    assert (
        classify_emission_outcome(
            expected_decision="emit_l1",
            observed_decision="emit_l1",
            observed_modality="actual",
            policy=policy,
        )
        == "match"
    )


def test_scope_disagreement_still_never_enters_authoritative_memory() -> None:
    """policy scope 分歧不进硬门，但也绝不能被写入权威记忆。

    这是这次区分不构成放松的关键：判定改的是"如何归类失败"，不是"允许写入什么"。
    """
    _registry, policy = _policy()
    authorized = {item.modality for item in policy.modality_time_policies}
    assert authorized == {"actual"}
    assert "requested" not in authorized

    # 物化器仍必须拒绝 requested。
    from tools.natural_memory_benchmark.e2e_openai_producers import (
        L1SemanticSlotProposalV1,
        materialize_typed_l1_candidate,
    )

    registry, policy = _policy()
    slots = L1SemanticSlotProposalV1.model_validate(
        {
            "predicate_surface": "add",
            "predicate_sense": "add_ingredient",
            "canonical_operator": "add_ingredient",
            "kind": "event",
            "modality": "requested",
            "polarity": "positive",
            "role_slots": [
                {"role": "theme", "surface": "milk", "char_start": 4, "char_end": 8},
                {
                    "role": "destination",
                    "surface": "coffee",
                    "char_start": 16,
                    "char_end": 22,
                },
            ],
        }
    )
    candidate = materialize_typed_l1_candidate(
        slots=slots,
        registry=registry,
        policy=policy,
        user_text="Add milk to the coffee please",
        evidence_id="evidence-x",
    )
    from tools.natural_memory_benchmark.e2e_openai_producers import _validate_time

    # 未授权模态在时间/模态校验处失败，因此写不进权威记忆。
    with pytest.raises(ValueError, match="modality"):
        _validate_time(candidate=candidate, policy=policy)


def test_the_frozen_manifest_rule_is_what_gets_enforced() -> None:
    """manifest 已声明 convention 不进硬门；判定必须执行该规则。"""
    from tools.natural_memory_benchmark.operational_profile_fresh_authoring import (
        label_confidence_report,
    )

    report = label_confidence_report()
    assert report["convention_labels_are_reported_not_gated"] is True
    assert report["gate_counts_only_indisputable_violations"] is True
