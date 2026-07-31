"""scorer 必须真正执行冻结的 label_confidence 规则。

审计发现的缺陷：`classify_emission_outcome` 从不读取 `label_confidence`，把所有
非产出方向的分歧一律返回 `reported_mismatch`，scorer 再把它们全部计为
convention。于是 gold 要求一个 **indisputable** 的 emit_l1、模型错误 abstain 时，
仍会得到 `qualified=True`——而预注册明确要求 `missing_an_indisputable_fact` 必须
进硬门。

这不是评分口径偏松的问题，而是 scorer 不自校验：它声称执行的规则与它实际执行的
规则不一致。attempt 3 的实际分歧恰好只在 abstain/no_memory 之间，所以 0.9167
本身不必判失败，但资格记录必须在修正后重新评分。
"""

from __future__ import annotations

from tools.natural_memory_benchmark.e2e_openai_producers import (
    build_diagnostic_production_policy,
)
from tools.natural_memory_benchmark.l1_ontology_linking import (
    build_diagnostic_ontology_registry,
)
from tools.natural_memory_benchmark.operational_profile_fresh_authoring import (
    classify_emission_outcome,
)
from tools.natural_memory_benchmark.operational_profile_fresh_scoring import (
    score_layer,
)


def _policy():
    registry = build_diagnostic_ontology_registry()
    return build_diagnostic_production_policy(registry)


def test_missing_an_indisputable_fact_is_gated() -> None:
    """gold 要求 indisputable 产出而模型弃权，必须进硬门。"""
    outcome = classify_emission_outcome(
        expected_decision="emit_l1",
        observed_decision="abstain",
        observed_modality=None,
        policy=_policy(),
        label_confidence="indisputable",
    )
    assert outcome == "missing_an_indisputable_fact"


def test_declining_a_convention_emission_is_only_reported() -> None:
    """约定性"应产出"被弃权时只报告，不进硬门。"""
    outcome = classify_emission_outcome(
        expected_decision="emit_l2",
        observed_decision="abstain",
        observed_modality=None,
        policy=_policy(),
        label_confidence="convention",
    )
    assert outcome == "reported_mismatch"


def test_the_other_non_emission_label_stays_a_convention_disagreement() -> None:
    """abstain 与 no_memory 之间的分歧仍然只作观测。"""
    for confidence in ("indisputable", "convention"):
        outcome = classify_emission_outcome(
            expected_decision="no_memory",
            observed_decision="abstain",
            observed_modality=None,
            policy=_policy(),
            label_confidence=confidence,
        )
        assert outcome == "convention_disagreement", confidence


def test_an_indisputable_miss_fails_qualification() -> None:
    """这是审计实测过的场景：此前它错误地得到 qualified=True。"""
    report = score_layer(
        cases=[
            {
                "knowledge_id": "indisputable-fact-missed",
                "evidence_quote": "Tea is drunk after every deployment.",
                "expected_decision": "emit_l1",
                "label_confidence": "indisputable",
                "raw_decision": "abstain",
                "raw_modality": None,
            }
        ],
        policy=_policy(),
    )
    assert report["missing_indisputable_fact_count"] == 1
    assert report["convention_disagreement_count"] == 0
    assert report["raw_ready"] is False
    assert report["qualified"] is False


def test_a_convention_miss_still_qualifies() -> None:
    """约定分歧不得单独否决资格，否则修正会变成收紧口径。"""
    report = score_layer(
        cases=[
            {
                "knowledge_id": "question-label",
                "evidence_quote": "Should milk be added to the coffee?",
                "expected_decision": "no_memory",
                "label_confidence": "convention",
                "raw_decision": "abstain",
                "raw_modality": None,
            }
        ],
        policy=_policy(),
    )
    assert report["convention_disagreement_count"] == 1
    assert report["missing_indisputable_fact_count"] == 0
    assert report["qualified"] is True


def test_fabrication_still_gates_regardless_of_confidence() -> None:
    """编造事实无论确定度都必须进硬门，这条不得因修正而松动。"""
    for confidence in ("indisputable", "convention"):
        report = score_layer(
            cases=[
                {
                    "knowledge_id": "fabricated",
                    "evidence_quote": "Which beverage is preferred here?",
                    "expected_decision": "no_memory",
                    "label_confidence": confidence,
                    "raw_decision": "emit_l1",
                    "raw_modality": "actual",
                }
            ],
            policy=_policy(),
        )
        assert report["raw_semantic_false_emission_count"] == 1, confidence
        assert report["qualified"] is False, confidence


def test_the_scorer_reports_which_rules_it_enforces() -> None:
    """scorer 必须自述它执行的门控项，避免声称与实际再次脱节。"""
    report = score_layer(
        cases=[
            {
                "knowledge_id": "clean",
                "evidence_quote": "Tea is drunk after every deployment.",
                "expected_decision": "emit_l1",
                "label_confidence": "indisputable",
                "raw_decision": "emit_l1",
                "raw_modality": "actual",
            }
        ],
        policy=_policy(),
    )
    assert set(report["gated_outcomes"]) == {
        "raw_semantic_false_emission",
        "missing_an_indisputable_fact",
    }
    assert report["qualified"] is True
