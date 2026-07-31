"""hidden-v3 必须与 v1、v2 都无重叠，且真正考察修复的泛化。

prompt 诊断阶段重放过 hidden-v2，因此 v2 已不能用于资格判定。v3 是 attempt 3 的
唯一合法输入。

关键要求：v3 的习惯性条件句必须使用**修复期未见过的措辞**。修复针对的是批次
上下文依赖，若 v3 只用 whenever/when，通过就可能只说明匹配了已见措辞。
"""

from __future__ import annotations

from tools.natural_memory_benchmark.operational_profile_fresh_authoring import (
    L1_BLUEPRINTS,
    L2_BLUEPRINTS,
)
from tools.natural_memory_benchmark.operational_profile_fresh_authoring_v2 import (
    L1_BLUEPRINTS_V2,
    L2_BLUEPRINTS_V2,
)
from tools.natural_memory_benchmark.operational_profile_fresh_authoring_v3 import (
    DATASET_ID,
    L1_BLUEPRINTS_V3,
    L2_BLUEPRINTS_V3,
    coverage_report_v3,
)
from tools.natural_memory_benchmark.operational_profile_fresh_prereg import (
    PREREGISTERED_L1_OPERATOR_SENSES,
    PREREGISTERED_L2_OPERATOR_SENSES,
    REQUIRED_L1_COVERAGE,
    REQUIRED_L2_COVERAGE,
)


def _texts(l1, l2) -> set[str]:
    texts = {item.user_text.casefold() for item in l1}
    texts |= {user.casefold() for item in l2 for user, _agent in item.turns}
    return texts


def test_v3_is_a_distinct_dataset() -> None:
    """v3 必须有自己的 dataset id。"""
    assert DATASET_ID == "operational-profile-fresh-hidden-v3"


def test_v3_shares_no_sentence_with_v1_or_v2() -> None:
    """v3 不得复用 v1 或 v2 的任何一句原文。"""
    earlier = _texts(L1_BLUEPRINTS, L2_BLUEPRINTS) | _texts(
        L1_BLUEPRINTS_V2, L2_BLUEPRINTS_V2
    )
    current = _texts(L1_BLUEPRINTS_V3, L2_BLUEPRINTS_V3)
    assert current & earlier == set(), current & earlier


def test_v3_shares_no_knowledge_id_with_v1_or_v2() -> None:
    """知识 id 不得冲突，否则冻结记录会互相覆盖。"""
    earlier = {
        item.knowledge_id
        for item in (*L1_BLUEPRINTS, *L2_BLUEPRINTS, *L1_BLUEPRINTS_V2, *L2_BLUEPRINTS_V2)
    }
    current = {item.knowledge_id for item in (*L1_BLUEPRINTS_V3, *L2_BLUEPRINTS_V3)}
    assert current & earlier == set()
    assert len(current) == len(L1_BLUEPRINTS_V3) + len(L2_BLUEPRINTS_V3)


def test_v3_conditionals_use_phrasings_the_repair_never_saw() -> None:
    """条件句措辞必须是修复期未使用过的，才能考察泛化。

    修复的 dev 集用的是 if/unless/provided/assuming/should/when/whenever/once/
    in case/as long as/so long as/supposing。v3 改用"each time"、
    "any morning that"、"on days when"。
    """
    developed_against = {
        "whenever",
        "unless",
        "provided",
        "assuming",
        "supposing",
        "in case",
        "as long as",
        "so long as",
    }
    conditional_ids = (
        "op3-l1-prefer-hypothetical",
        "op3-l1-drink-habitual-conditional",
        "op3-l1-add-conditional",
    )
    by_id = {item.knowledge_id: item for item in L1_BLUEPRINTS_V3}
    for knowledge_id in conditional_ids:
        text = by_id[knowledge_id].user_text.casefold()
        assert not any(marker in text for marker in developed_against), (
            knowledge_id,
            text,
        )
    assert "each time" in by_id["op3-l1-drink-habitual-conditional"].user_text.casefold()
    assert "any morning that" in by_id["op3-l1-add-conditional"].user_text.casefold()
    assert "on days when" in by_id["op3-l1-prefer-hypothetical"].user_text.casefold()


def test_v3_includes_a_temporal_case_the_guard_must_not_refuse() -> None:
    """必须含一个"看似条件、实为时间"的用例，防止守卫过度拦截。"""
    by_id = {item.knowledge_id: item for item in L1_BLUEPRINTS_V3}
    case = by_id["op3-l1-drink-confusable"]
    assert "before" in case.user_text.casefold()
    assert case.expected_decision == "emit_l1"


def test_v3_meets_the_preregistered_coverage() -> None:
    """三算子各四类、L2 四类，覆盖不得缺项。"""
    report = coverage_report_v3()
    expected = {operator for operator, _sense in PREREGISTERED_L1_OPERATOR_SENSES}
    assert set(report["l1_by_operator"]) == expected
    for operator, covered in report["l1_by_operator"].items():
        assert set(covered) == set(REQUIRED_L1_COVERAGE), (operator, covered)
    assert set(report["l2_coverage"]) == set(REQUIRED_L2_COVERAGE)


def test_v3_stays_inside_the_narrow_vocabulary() -> None:
    """不得引入窄域之外的 operator/sense。"""
    l1 = {
        (item.canonical_operator, item.predicate_sense) for item in L1_BLUEPRINTS_V3
    }
    l2 = {
        (item.canonical_operator, item.predicate_sense) for item in L2_BLUEPRINTS_V3
    }
    assert l1 == set(PREREGISTERED_L1_OPERATOR_SENSES)
    assert l2 == set(PREREGISTERED_L2_OPERATOR_SENSES)


def test_v3_has_both_non_emission_outcomes() -> None:
    """abstain 与 no_memory 都要出现。"""
    counts = coverage_report_v3()["l1_decision_counts"]
    assert counts["abstain"] >= 1
    assert counts["no_memory"] >= 1
    assert counts["emit_l1"] >= 1


def test_v3_role_surfaces_are_quoted_from_the_user_text() -> None:
    """角色表面必须逐字出现在原文中。"""
    for item in L1_BLUEPRINTS_V3:
        for _role, surface in item.role_surfaces:
            assert surface.casefold() in item.user_text.casefold(), (
                item.knowledge_id,
                surface,
            )


def test_v3_marks_label_confidence_on_every_case() -> None:
    """每例都要声明确定度；条件句归属仍是约定。"""
    for item in (*L1_BLUEPRINTS_V3, *L2_BLUEPRINTS_V3):
        assert item.label_confidence in ("indisputable", "convention"), (
            item.knowledge_id
        )
    convention = {
        item.knowledge_id
        for item in L1_BLUEPRINTS_V3
        if item.label_confidence == "convention"
    }
    assert "op3-l1-drink-habitual-conditional" in convention
