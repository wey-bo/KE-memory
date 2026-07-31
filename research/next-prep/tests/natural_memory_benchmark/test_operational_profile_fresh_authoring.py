"""authoring 的数据必须真的满足预注册声明的覆盖，而不是自称满足。

预注册在数据之前冻结，因此这里的检查方向是固定的：拿冻结的覆盖要求去核对已写出
的用例，任一算子缺一类情形就必须失败。同时确认词汇没有越出窄域——评测期间扩词表
正是预注册要防的偏离。
"""

from __future__ import annotations

from tools.natural_memory_benchmark.operational_profile_fresh_authoring import (
    L1_BLUEPRINTS,
    L2_BLUEPRINTS,
    coverage_report,
)
from tools.natural_memory_benchmark.operational_profile_fresh_prereg import (
    PREREGISTERED_L1_OPERATOR_SENSES,
    PREREGISTERED_L2_OPERATOR_SENSES,
    REQUIRED_L1_COVERAGE,
    REQUIRED_L2_COVERAGE,
)


def test_every_l1_operator_covers_every_required_case() -> None:
    """三个算子各自四类情形齐全，缺一类即失败。"""
    report = coverage_report()
    expected_operators = {
        operator for operator, _sense in PREREGISTERED_L1_OPERATOR_SENSES
    }
    assert set(report["l1_by_operator"]) == expected_operators
    for operator, covered in report["l1_by_operator"].items():
        assert set(covered) == set(REQUIRED_L1_COVERAGE), (operator, covered)


def test_l2_covers_every_required_case() -> None:
    """L2 四类覆盖齐全，包含 critical false emission。"""
    report = coverage_report()
    assert set(report["l2_coverage"]) == set(REQUIRED_L2_COVERAGE)
    assert "critical_false_emission" in report["l2_coverage"]


def test_vocabulary_stays_inside_the_preregistered_scope() -> None:
    """authoring 不得引入窄域之外的 operator/sense。"""
    authored_l1 = {
        (item.canonical_operator, item.predicate_sense) for item in L1_BLUEPRINTS
    }
    authored_l2 = {
        (item.canonical_operator, item.predicate_sense) for item in L2_BLUEPRINTS
    }
    assert authored_l1 == set(PREREGISTERED_L1_OPERATOR_SENSES)
    assert authored_l2 == set(PREREGISTERED_L2_OPERATOR_SENSES)


def test_both_non_emission_outcomes_are_present() -> None:
    """abstain 与 no_memory 都必须出现：两者语义不同，不能只测一种。"""
    report = coverage_report()
    counts = report["l1_decision_counts"]
    assert counts["abstain"] >= 1
    assert counts["no_memory"] >= 1
    assert counts["emit_l1"] >= 1


def test_l2_has_both_verdicts() -> None:
    """L2 必须同时含应产出与应弃权，否则弃权能力无从检验。"""
    report = coverage_report()
    counts = report["l2_decision_counts"]
    assert counts["emit_l2"] >= 1
    assert counts["abstain"] >= 1


def test_every_case_states_why() -> None:
    """每例都要写明判定理由，评分失败时可直接对照作者意图。"""
    for item in (*L1_BLUEPRINTS, *L2_BLUEPRINTS):
        assert len(item.rationale) > 20, item.knowledge_id


def test_knowledge_ids_are_unique() -> None:
    """知识 id 必须唯一，否则用例会互相覆盖。"""
    ids = [item.knowledge_id for item in (*L1_BLUEPRINTS, *L2_BLUEPRINTS)]
    assert len(ids) == len(set(ids))


def test_role_surfaces_are_quoted_from_the_user_text() -> None:
    """角色表面必须逐字出现在用户原文里。

    这是 offset 校验的前提：若表面不在原文中，物化阶段只能靠编造来填。
    """
    for item in L1_BLUEPRINTS:
        for _role, surface in item.role_surfaces:
            assert surface.casefold() in item.user_text.casefold(), (
                item.knowledge_id,
                surface,
            )


def test_add_ingredient_cases_fill_both_published_roles() -> None:
    """add_ingredient 发布了两个角色，正确用例必须都填。"""
    for item in L1_BLUEPRINTS:
        if (
            item.canonical_operator == "add_ingredient"
            and item.expected_decision == "emit_l1"
        ):
            roles = {role for role, _surface in item.role_surfaces}
            assert roles == {"theme", "destination"}, item.knowledge_id
