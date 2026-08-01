"""predicate 三元组取自 registry，role slot 表面取自用户原文。

Phase D attempt 1 就卡在这个区分缺失上：模型选对了 sense 与 canonical operator，
却把 predicate surface 按原文变形成 "preferred"/"drunk"，而 registry 发布的是
"prefer"/"drink"。prompt 只说过 role slot 表面要逐字取自原文，没说 predicate
surface 的来源，所以照原文变形是合理读法。

修的是 prompt 的这处歧义，不是往 registry 里加 "preferred"/"drunk"——为迎合模型
输出而扩词表，就是把契约改成结果的形状。
"""

from __future__ import annotations

from tools.natural_memory_benchmark.e2e_openai_producers import (
    build_diagnostic_production_policy,
)
from tools.natural_memory_benchmark.l1_ontology_linking import (
    build_diagnostic_ontology_registry,
)


def _l1_prompt() -> str:
    """Read the prompt the live L1 producer actually sends.

    Reads the module constant rather than the function source. The prompt was
    extracted to a constant so the producer contract hash could stop moving with
    the code; reading source here would tie this test to the same brittleness.
    """
    from tools.natural_memory_benchmark.e2e_openai_producers import (
        _PRODUCTION_L1_SYSTEM_PROMPT,
    )

    return _PRODUCTION_L1_SYSTEM_PROMPT


def test_the_prompt_says_the_predicate_triple_comes_from_the_registry() -> None:
    """prompt 必须说明 predicate 三元组取自已发布元组。"""
    prompt = _l1_prompt()
    assert "copied verbatim from one published tuple" in prompt
    assert "predicate_role_constraints" in prompt


def test_the_prompt_forbids_inflecting_the_predicate_surface() -> None:
    """必须明确禁止按原文变形 predicate surface。"""
    prompt = _l1_prompt()
    assert "Do not inflect the predicate surface" in prompt


def test_the_prompt_keeps_the_two_surface_sources_distinct() -> None:
    """两种表面的来源必须被明确区分，否则歧义仍在。"""
    prompt = _l1_prompt()
    assert "role slot surfaces come from the" in prompt
    assert "predicate triple comes from the registry" in prompt


def test_the_registry_was_not_widened_to_fit_the_model() -> None:
    """registry 不得为迎合模型输出而新增变形词。"""
    registry = build_diagnostic_ontology_registry()
    surfaces = {
        item.predicate_surface for item in registry.predicate_role_constraints
    }
    assert surfaces == {"prefer", "drink", "add"}, surfaces
    for inflected in ("preferred", "drunk", "added", "drinks", "prefers"):
        assert inflected not in surfaces, inflected


def test_the_published_tuples_are_what_the_boundary_enforces() -> None:
    """边界校验用的正是这些已发布元组，两者不得各自漂移。"""
    registry = build_diagnostic_ontology_registry()
    policy = build_diagnostic_production_policy(registry)
    published = {
        (
            item.predicate_surface,
            item.predicate_sense,
            item.canonical_operator,
        )
        for item in registry.predicate_role_constraints
    }
    operators = {
        item.canonical_operator for item in policy.l1_operator_kind_bindings
    }
    assert {operator for _s, _sense, operator in published} == operators
    assert ("prefer", "preference_theme", "prefer") in published
    assert ("drink", "consume_beverage", "drink") in published
