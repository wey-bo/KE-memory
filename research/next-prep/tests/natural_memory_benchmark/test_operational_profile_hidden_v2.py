"""hidden-v2 必须是真正的新数据，而不是 v1 的改写。

attempt 1 在 v1 上失败，修复后若回到 v1 重跑并宣称通过，就是对着已看过的 hidden
调参。所以 v2 的每一句都必须是新的，尤其不能复用那句驱动了 modality 修复的条件
句——用产生修复的例子去检验该修复，什么也证明不了。
"""

from __future__ import annotations

from tools.natural_memory_benchmark.operational_profile_fresh_authoring import (
    L1_BLUEPRINTS,
    L2_BLUEPRINTS,
)
from tools.natural_memory_benchmark.operational_profile_fresh_authoring_v2 import (
    DATASET_ID,
    L1_BLUEPRINTS_V2,
    L2_BLUEPRINTS_V2,
    coverage_report_v2,
)
from tools.natural_memory_benchmark.operational_profile_fresh_prereg import (
    PREREGISTERED_L1_OPERATOR_SENSES,
    PREREGISTERED_L2_OPERATOR_SENSES,
    REQUIRED_L1_COVERAGE,
    REQUIRED_L2_COVERAGE,
)


def test_v2_is_a_distinct_dataset() -> None:
    """v2 必须有自己的 dataset id，不得覆盖 v1。"""
    assert DATASET_ID == "operational-profile-fresh-hidden-v2"


def test_no_sentence_is_reused_from_v1() -> None:
    """v1 与 v2 不得共用任何一句原文。"""
    v1_texts = {item.user_text.casefold() for item in L1_BLUEPRINTS}
    v1_texts |= {
        user.casefold() for item in L2_BLUEPRINTS for user, _agent in item.turns
    }
    v2_texts = {item.user_text.casefold() for item in L1_BLUEPRINTS_V2}
    v2_texts |= {
        user.casefold() for item in L2_BLUEPRINTS_V2 for user, _agent in item.turns
    }
    overlap = v1_texts & v2_texts
    assert overlap == set(), overlap


def test_the_conditional_sentence_that_drove_the_repair_is_absent() -> None:
    """驱动 modality 修复的那句必须不在 v2 中。"""
    v2_texts = " ".join(item.user_text.casefold() for item in L1_BLUEPRINTS_V2)
    assert "machine is fixed" not in v2_texts
    assert "would be drunk again" not in v2_texts


def test_v2_conditional_uses_an_undeveloped_phrasing() -> None:
    """v2 的条件句措辞不得与修复期使用的 dev 措辞重合。

    修复是在 if/unless/provided/assuming/should/when/in case 上开发的；v2 用
    "whenever"，因此检验的是泛化而不是记忆。
    """
    conditional = next(
        item
        for item in L1_BLUEPRINTS_V2
        if item.knowledge_id == "op2-l1-drink-conditional"
    )
    assert "whenever" in conditional.user_text.casefold()


def test_v2_knowledge_ids_do_not_collide_with_v1() -> None:
    """知识 id 不得与 v1 冲突，否则冻结记录会互相覆盖。"""
    v1_ids = {item.knowledge_id for item in (*L1_BLUEPRINTS, *L2_BLUEPRINTS)}
    v2_ids = {item.knowledge_id for item in (*L1_BLUEPRINTS_V2, *L2_BLUEPRINTS_V2)}
    assert v1_ids & v2_ids == set()
    assert len(v2_ids) == len(L1_BLUEPRINTS_V2) + len(L2_BLUEPRINTS_V2)


def test_v2_meets_the_preregistered_coverage() -> None:
    """v2 必须满足冻结的覆盖要求，三算子各四类、L2 四类。"""
    report = coverage_report_v2()
    expected_operators = {
        operator for operator, _sense in PREREGISTERED_L1_OPERATOR_SENSES
    }
    assert set(report["l1_by_operator"]) == expected_operators
    for operator, covered in report["l1_by_operator"].items():
        assert set(covered) == set(REQUIRED_L1_COVERAGE), (operator, covered)
    assert set(report["l2_coverage"]) == set(REQUIRED_L2_COVERAGE)


def test_v2_stays_inside_the_narrow_vocabulary() -> None:
    """v2 不得引入窄域之外的 operator/sense。"""
    authored_l1 = {
        (item.canonical_operator, item.predicate_sense) for item in L1_BLUEPRINTS_V2
    }
    authored_l2 = {
        (item.canonical_operator, item.predicate_sense) for item in L2_BLUEPRINTS_V2
    }
    assert authored_l1 == set(PREREGISTERED_L1_OPERATOR_SENSES)
    assert authored_l2 == set(PREREGISTERED_L2_OPERATOR_SENSES)


def test_v2_has_both_non_emission_outcomes() -> None:
    """abstain 与 no_memory 都要出现。"""
    counts = coverage_report_v2()["l1_decision_counts"]
    assert counts["abstain"] >= 1
    assert counts["no_memory"] >= 1
    assert counts["emit_l1"] >= 1


def test_v2_role_surfaces_are_quoted_from_the_user_text() -> None:
    """角色表面必须逐字出现在原文里，这是 offset 校验的前提。"""
    for item in L1_BLUEPRINTS_V2:
        for _role, surface in item.role_surfaces:
            assert surface.casefold() in item.user_text.casefold(), (
                item.knowledge_id,
                surface,
            )


def test_v2_marks_label_confidence_on_every_case() -> None:
    """每例都要声明确定度，硬门只计不容争议的判断。"""
    for item in (*L1_BLUEPRINTS_V2, *L2_BLUEPRINTS_V2):
        assert item.label_confidence in ("indisputable", "convention"), (
            item.knowledge_id
        )
    convention = [
        item.knowledge_id
        for item in (*L1_BLUEPRINTS_V2, *L2_BLUEPRINTS_V2)
        if item.label_confidence == "convention"
    ]
    # 非产出标签的归属仍是约定，不得当作事实。
    assert "op2-l1-drink-conditional" in convention
    assert "op2-l1-add-planned" in convention
