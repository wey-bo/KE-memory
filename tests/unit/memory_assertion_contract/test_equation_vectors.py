"""KnowledgeEquation, asserted against every KE the shipped cases contain.

The 42 cases are materialised first, so the KEs reached here include the ones that only
exist after a patch is applied -- among them three cases whose patch targets a `/ke` path
precisely to make the equation invalid.
"""

from __future__ import annotations

from typing import Any, cast

from pydantic import ValidationError
import pytest

from memory_assertion_v1 import KnowledgeEquation

from .vectors import EXPECTED_CASE_COUNT, case_expectations, materialized_cases


def _equations() -> list[tuple[str, dict[str, Any], bool]]:
    """Every (case name, ke, expected_valid) triple across the materialised cases.

    A case name is suffixed when it carries more than one candidate, so a failure names
    the exact equation rather than only the case.
    """
    cases = materialized_cases()
    assert len(cases) == EXPECTED_CASE_COUNT, (
        f"expected {EXPECTED_CASE_COUNT} materialised cases, found {len(cases)}"
    )
    expectations = case_expectations()
    found: list[tuple[str, dict[str, Any], bool]] = []
    for name, document in cases.items():
        hypotheses = cast("list[dict[str, Any]]", document.get("hypotheses") or [])
        for hypothesis in hypotheses:
            candidates = cast(
                "list[dict[str, Any]]", hypothesis.get("candidate_assertions") or []
            )
            for index, candidate in enumerate(candidates):
                if "ke" not in candidate:
                    continue
                label = f"{name}#{index}" if index else name
                found.append((label, cast("dict[str, Any]", candidate["ke"]), expectations[name]))
    return found


_EQUATIONS = _equations()
_VALID_CASE_EQUATIONS = [(label, ke) for label, ke, valid in _EQUATIONS if valid]
_INVALID_CASE_EQUATIONS = [(label, ke) for label, ke, valid in _EQUATIONS if not valid]


def test_cases_yield_equations() -> None:
    """The extraction must actually find equations.

    Without this, a change that stopped finding KEs would empty both parametrized lists
    and the suite would report success for having tested nothing.
    """
    assert len(_EQUATIONS) >= 8
    assert _VALID_CASE_EQUATIONS
    assert _INVALID_CASE_EQUATIONS


@pytest.mark.parametrize(
    ("label", "ke"),
    _VALID_CASE_EQUATIONS,
    ids=[label for label, _ in _VALID_CASE_EQUATIONS],
)
def test_equations_from_valid_cases_construct(label: str, ke: dict[str, Any]) -> None:
    equation = KnowledgeEquation.model_validate(ke)
    assert equation.model_dump(mode="json") == ke, label


@pytest.mark.parametrize(
    ("label", "ke"),
    _INVALID_CASE_EQUATIONS,
    ids=[label for label, _ in _INVALID_CASE_EQUATIONS],
)
def test_equations_from_invalid_cases(label: str, ke: dict[str, Any]) -> None:
    """An invalid *case* does not imply a structurally invalid *equation*.

    Most negative cases are invalid for reasons this layer cannot see -- a wrong request
    hash, an unresolvable reference, a scope violation. Those are semantic-validator
    concerns, and their equations are well-formed. So the assertion is only that each one
    either constructs or raises, never that it must fail: claiming otherwise would be
    claiming this layer detects semantic defects. The cases that *must* fail structurally
    are named in test_structurally_invalid_cases_are_rejected.
    """
    try:
        equation = KnowledgeEquation.model_validate(ke)
    except ValidationError:
        return
    assert equation.model_dump(mode="json") == ke, label


# The three cases whose patch targets a `/ke` path, split by whether the defect they
# introduce is structural. Naming them individually is what turns "either constructs or
# raises" into a real assertion: without this, the models could stop rejecting anything
# and the parametrized test above would still pass.
_STRUCTURALLY_INVALID = (
    "invalid nested operator application argument",
    "invalid null typed value",
)
_SEMANTICALLY_INVALID = ("invalid self-referential candidate graph",)


def _equations_of(case_name: str) -> list[dict[str, Any]]:
    return [ke for label, ke, _ in _EQUATIONS if label.split("#")[0] == case_name]


@pytest.mark.parametrize("case_name", _STRUCTURALLY_INVALID)
def test_structurally_invalid_cases_are_rejected(case_name: str) -> None:
    equations = _equations_of(case_name)
    assert equations, f"{case_name} contributed no equation to assert on"
    for ke in equations:
        with pytest.raises(ValidationError):
            KnowledgeEquation.model_validate(ke)


@pytest.mark.parametrize("case_name", _SEMANTICALLY_INVALID)
def test_semantically_invalid_cases_still_construct(case_name: str) -> None:
    """A self-referential candidate graph is well-formed at this layer.

    Detecting the cycle needs the whole candidate table, which is the semantic
    validator's input, not an equation's. Asserting that it constructs here records the
    boundary as a property rather than leaving it to be inferred from an absence.
    """
    equations = _equations_of(case_name)
    assert equations, f"{case_name} contributed no equation to assert on"
    for ke in equations:
        assert KnowledgeEquation.model_validate(ke).model_dump(mode="json") == ke
