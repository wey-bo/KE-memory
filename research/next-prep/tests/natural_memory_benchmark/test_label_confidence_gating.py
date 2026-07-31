"""硬门只能建立在不容争议的判断上，作者约定只能被观测。

现有 scorer 把"gold 非产出而模型产出"一律计为 critical false emission。对"模型
写下了原文不支持的事实"这是对的；对"模型选了 abstain 而作者写的是 no_memory"
就不对了——后者是关于约定的分歧，把它当硬门会让实现去拟合作者的分类法，而不是
拟合证据。

"疑问句算 no_memory 还是 abstain"正是这类约定：真实场景里未必成立，因此不得
作为资格门，也不得据此把模型"改绿"。
"""

from __future__ import annotations

from tools.natural_memory_benchmark.operational_profile_fresh_authoring import (
    L1_BLUEPRINTS,
    L2_BLUEPRINTS,
    classify_decision_outcome,
    label_confidence_report,
)


def test_fabricating_a_fact_is_always_gated() -> None:
    """产出原文不支持的事实，无论标签确定度都必须进硬门。"""
    for confidence in ("indisputable", "convention"):
        assert (
            classify_decision_outcome(
                expected_decision="no_memory",
                observed_decision="emit_l1",
                label_confidence=confidence,
            )
            == "gated_violation"
        )
        assert (
            classify_decision_outcome(
                expected_decision="abstain",
                observed_decision="emit_l1",
                label_confidence=confidence,
            )
            == "gated_violation"
        )


def test_choosing_the_other_non_emission_label_is_not_gated() -> None:
    """abstain 与 no_memory 之间的分歧只作观测，不进硬门。

    这是用户指出的问题：两种非产出标签的归属是约定，真实场景可能另有合理答案。
    """
    assert (
        classify_decision_outcome(
            expected_decision="no_memory",
            observed_decision="abstain",
            label_confidence="convention",
        )
        == "convention_disagreement"
    )
    assert (
        classify_decision_outcome(
            expected_decision="abstain",
            observed_decision="no_memory",
            label_confidence="convention",
        )
        == "convention_disagreement"
    )


def test_missing_an_indisputable_fact_is_gated() -> None:
    """该产出却不产出，且标签不容争议时，仍必须进硬门。"""
    assert (
        classify_decision_outcome(
            expected_decision="emit_l1",
            observed_decision="abstain",
            label_confidence="indisputable",
        )
        == "gated_violation"
    )


def test_declining_a_convention_emission_is_only_reported() -> None:
    """约定性的"应产出"若模型选择弃权，只报告不作硬门。

    跨轮回指是否该解析是判断问题，拒绝解析代词的系统合理地会弃权。
    """
    assert (
        classify_decision_outcome(
            expected_decision="emit_l2",
            observed_decision="abstain",
            label_confidence="convention",
        )
        == "reported_mismatch"
    )


def test_a_match_is_a_match() -> None:
    """一致时不得报成分歧，否则这套分类会把正确答案判成问题。"""
    for confidence in ("indisputable", "convention"):
        assert (
            classify_decision_outcome(
                expected_decision="emit_l1",
                observed_decision="emit_l1",
                label_confidence=confidence,
            )
            == "match"
        )


def test_every_case_declares_its_label_confidence() -> None:
    """每个用例都必须声明确定度，不得默认成硬门。"""
    for item in (*L1_BLUEPRINTS, *L2_BLUEPRINTS):
        assert item.label_confidence in ("indisputable", "convention"), (
            item.knowledge_id
        )


def test_the_disputable_non_emission_labels_are_marked_convention() -> None:
    """把"问句/条件句/请求句归哪一类"标为约定，而不是当成事实。"""
    by_id = {
        item.knowledge_id: item for item in (*L1_BLUEPRINTS, *L2_BLUEPRINTS)
    }
    for knowledge_id in (
        "op-l1-prefer-question",
        "op-l1-drink-hypothetical",
        "op-l1-add-requested",
        "op-l1-add-nothing-durable",
    ):
        assert by_id[knowledge_id].label_confidence == "convention", knowledge_id


def test_fabrication_cases_stay_indisputable() -> None:
    """"写下原文相反或原文没有的事实"必须保持为硬门用例。"""
    by_id = {
        item.knowledge_id: item for item in (*L1_BLUEPRINTS, *L2_BLUEPRINTS)
    }
    for knowledge_id in (
        "op-l1-prefer-confusable",
        "op-l1-drink-confusable",
        "op-l1-add-confusable",
        "op-l2-wrong-summary",
        "op-l2-critical-false-emission",
    ):
        assert by_id[knowledge_id].label_confidence == "indisputable", knowledge_id


def test_report_states_what_is_gated() -> None:
    """报告必须写明哪些进门、哪些只观测，避免事后重新解释。"""
    report = label_confidence_report()
    assert report["gate_counts_only_indisputable_violations"] is True
    assert report["convention_labels_are_reported_not_gated"] is True
    assert report["indisputable_count"] + report["convention_count"] == len(
        L1_BLUEPRINTS
    ) + len(L2_BLUEPRINTS)
    assert report["convention_count"] >= 1
    assert "op-l1-prefer-question" in report["convention_case_ids"]
