"""Phase C 必须执行与 production 同一份 modality grounding，且分开计数。

attempt 2 暴露的第一个原因：modality 守卫在 `_validate_candidate`（producer
边界），而 Phase C 直接对模型原始提案评分，从不经过那个边界。实测
`_conditions_the_claim` 对该句返回 True，提案却照样通过——因为这条路径上没有
任何代码调用它。修复 3 的回归测试跑的是 producer，全绿却与被检验的路径无关。

补齐守卫时必须同时守住第二件事：**gate 拦截不得掩盖 raw 错误**。模型自己判错、
被程序拦下，与模型判对，是两回事。Phase C 要测的正是 raw 质量，所以两者必须
分别计数、分别报告，通过条件是 raw 全绿**且** gate intervention 为零。
"""

from __future__ import annotations

from tools.natural_memory_benchmark.e2e_openai_producers import (
    build_diagnostic_production_policy,
)
from tools.natural_memory_benchmark.l1_ontology_linking import (
    build_diagnostic_ontology_registry,
)


def _policy():
    registry = build_diagnostic_ontology_registry()
    return registry, build_diagnostic_production_policy(registry)


def test_the_gated_path_uses_the_same_grounding_as_production() -> None:
    """Phase C 的闸门必须复用 production 的实现，而不是另写一份。"""
    from tools.natural_memory_benchmark.operational_profile_fresh_scoring import (
        MODALITY_GROUNDING_IMPLEMENTATION,
    )
    from tools.natural_memory_benchmark.e2e_openai_producers import (
        _conditions_the_claim,
    )

    assert MODALITY_GROUNDING_IMPLEMENTATION is _conditions_the_claim


def test_a_conditional_emission_is_gated_on_the_phase_c_path() -> None:
    """attempt 2 中通过的那句，现在必须在 Phase C 路径上被拦下。"""
    from tools.natural_memory_benchmark.operational_profile_fresh_scoring import (
        apply_gate,
    )

    _registry, policy = _policy()
    outcome = apply_gate(
        evidence_quote="Whenever the kettle is free, tea is drunk at noon.",
        raw_decision="emit_l1",
        raw_modality="actual",
        policy=policy,
    )
    assert outcome.raw_decision == "emit_l1"
    assert outcome.gated_decision == "abstain"
    assert outcome.gate_intervened is True
    assert outcome.gate_reason == "modality_not_grounded"


def test_a_grounded_emission_passes_untouched() -> None:
    """合法产出不得被闸门改动，否则会造出假拦截。"""
    from tools.natural_memory_benchmark.operational_profile_fresh_scoring import (
        apply_gate,
    )

    _registry, policy = _policy()
    outcome = apply_gate(
        evidence_quote="Tea is drunk after every deployment.",
        raw_decision="emit_l1",
        raw_modality="actual",
        policy=policy,
    )
    assert outcome.gated_decision == "emit_l1"
    assert outcome.gate_intervened is False
    assert outcome.gate_reason is None


def test_an_unauthorized_modality_is_gated_but_not_a_fabrication() -> None:
    """未授权模态要被拦下，但仍归为 policy scope 分歧而非编造。"""
    from tools.natural_memory_benchmark.operational_profile_fresh_scoring import (
        apply_gate,
    )

    _registry, policy = _policy()
    outcome = apply_gate(
        evidence_quote="Milk will be added to the tea tomorrow.",
        raw_decision="emit_l1",
        raw_modality="planned",
        policy=policy,
    )
    assert outcome.gated_decision == "abstain"
    assert outcome.gate_intervened is True
    assert outcome.gate_reason == "modality_not_authorized"


def test_raw_and_gated_results_are_reported_separately() -> None:
    """raw 与 gated 必须分开计数：gate 拦截不得掩盖 raw 错误。"""
    from tools.natural_memory_benchmark.operational_profile_fresh_scoring import (
        score_layer,
    )

    _registry, policy = _policy()
    cases = [
        {
            "knowledge_id": "grounded-emit",
            "evidence_quote": "Tea is drunk after every deployment.",
            "expected_decision": "emit_l1",
            "label_confidence": "indisputable",
            "raw_decision": "emit_l1",
            "raw_modality": "actual",
        },
        {
            # 模型判错、被程序拦下：gated 看起来正确，raw 仍是错的。
            "knowledge_id": "conditional-emit",
            "evidence_quote": "Whenever the kettle is free, tea is drunk at noon.",
            "expected_decision": "abstain",
            "label_confidence": "convention",
            "raw_decision": "emit_l1",
            "raw_modality": "actual",
        },
    ]
    report = score_layer(cases=cases, policy=policy)

    assert report["gated_decision_accuracy"] == 1.0
    assert report["raw_decision_accuracy"] == 0.5
    assert report["raw_semantic_false_emission_count"] == 1
    assert report["gate_intervention_count"] == 1
    # 通过必须同时要求 raw 全绿与零拦截。
    assert report["raw_ready"] is False
    assert report["qualified"] is False


def test_qualification_requires_both_raw_green_and_zero_intervention() -> None:
    """raw 全绿且零拦截才算通过。"""
    from tools.natural_memory_benchmark.operational_profile_fresh_scoring import (
        score_layer,
    )

    _registry, policy = _policy()
    clean = [
        {
            "knowledge_id": "grounded-emit",
            "evidence_quote": "Tea is drunk after every deployment.",
            "expected_decision": "emit_l1",
            "label_confidence": "indisputable",
            "raw_decision": "emit_l1",
            "raw_modality": "actual",
        },
        {
            "knowledge_id": "model-abstained-itself",
            "evidence_quote": "Whenever the kettle is free, tea is drunk at noon.",
            "expected_decision": "abstain",
            "label_confidence": "convention",
            "raw_decision": "abstain",
            "raw_modality": None,
        },
    ]
    report = score_layer(cases=clean, policy=policy)
    assert report["raw_decision_accuracy"] == 1.0
    assert report["gate_intervention_count"] == 0
    assert report["raw_semantic_false_emission_count"] == 0
    assert report["raw_ready"] is True
    assert report["qualified"] is True


def test_a_convention_disagreement_alone_does_not_fail_qualification() -> None:
    """约定标签分歧不得单独否决资格，但必须出现在报告里。"""
    from tools.natural_memory_benchmark.operational_profile_fresh_scoring import (
        score_layer,
    )

    _registry, policy = _policy()
    cases = [
        {
            "knowledge_id": "question",
            "evidence_quote": "Which beverage is preferred here?",
            "expected_decision": "no_memory",
            "label_confidence": "convention",
            "raw_decision": "abstain",
            "raw_modality": None,
        }
    ]
    report = score_layer(cases=cases, policy=policy)
    assert report["convention_disagreement_count"] == 1
    assert report["raw_semantic_false_emission_count"] == 0
    assert report["gate_intervention_count"] == 0
    assert report["qualified"] is True
