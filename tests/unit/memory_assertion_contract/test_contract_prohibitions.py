"""The four prohibitions that separate memory-assertion/v1 from ke_contract_v1.

These are the differences that made the two contracts irreconcilable, so this file is the
regression net for the migration: if any of them stops holding, code written against the
superseded contract would start being accepted, and the repo would again carry two active
semantics.

Each test states the old shape and asserts it is rejected, rather than only asserting the
new shape works -- an accepting model and a model that ignores unknown fields look
identical from the positive side.
"""

from __future__ import annotations

from typing import Any

from pydantic import TypeAdapter, ValidationError
import pytest

from memory_assertion_v1 import KnowledgeEquation, LeafTerm, OperatorApplication

_LEAF: TypeAdapter[LeafTerm] = TypeAdapter(LeafTerm)

_OPERATOR = "operator_fe9dd6d99ebf"
_BOOLEAN_CONCEPT = "concept_b39c9a889cc6"
_QUANTITY_CONCEPT = "concept_b809c63d2ee0"


def _application(arguments: list[dict[str, Any]]) -> dict[str, Any]:
    return {"kind": "operator_application", "operator_id": _OPERATOR, "arguments": arguments}


def _individual(individual_id: str) -> dict[str, Any]:
    return {"kind": "individual_ref", "scope": "canonical", "individual_id": individual_id}


def _boolean_true() -> dict[str, Any]:
    return {"kind": "typed_value", "concept_id": _BOOLEAN_CONCEPT, "canonical_value": True}


def _well_formed() -> dict[str, Any]:
    return {"lhs": _application([_individual("model-gpt-4")]), "rhs": _boolean_true()}


def test_the_baseline_equation_is_accepted() -> None:
    """Guards the four negative tests below.

    If the baseline stopped constructing, every prohibition test would pass for the wrong
    reason -- rejection would prove nothing about the prohibition.
    """
    assert KnowledgeEquation.model_validate(_well_formed()).model_dump(mode="json") == (
        _well_formed()
    )


def test_nesting_an_application_in_arguments_is_rejected() -> None:
    """ke_contract_v1 made OperatorApplication recursive; here it is not a LeafTerm.

    Composition goes through an explicit assertion_ref instead, so every composed
    proposition is a named, referable thing rather than an anonymous subtree.
    """
    with pytest.raises(ValidationError):
        OperatorApplication.model_validate(_application([_application([])]))
    with pytest.raises(ValidationError):
        _LEAF.validate_python(_application([]))


def test_role_bound_arguments_are_rejected() -> None:
    """The old shape bound arguments to roles: `bindings` with a roleset-local role_id.

    Arguments are positional here and roles do not exist in this contract, so both the
    field name and the wrapper are unknown -- `extra="forbid"` is what makes that a
    failure rather than a silently dropped field.
    """
    with pytest.raises(ValidationError):
        OperatorApplication.model_validate(
            {
                "kind": "operator_application",
                "operator_id": _OPERATOR,
                "bindings": [{"role_id": "pb34:give.01#ARG0", "value": _individual("alice")}],
            }
        )
    with pytest.raises(ValidationError):
        OperatorApplication.model_validate(
            {
                "kind": "operator_application",
                "operator_id": _OPERATOR,
                "arguments": [{"role_id": "pb34:give.01#ARG0", "value": _individual("alice")}],
            }
        )


def test_assertion_scope_fields_are_rejected() -> None:
    """polarity, modality and temporal are forbidden keys in this profile.

    ke_contract_v1 carried an AssertionScope on every equation. Accepting them here would
    mean two contracts disagreeing about what an equation asserts, while both appearing to
    validate.
    """
    for field, value in (
        ("polarity", "positive"),
        ("modality", "actual"),
        ("temporal", {"event_time": None}),
        ("assertion_scope", {"polarity": "positive", "modality": "actual"}),
    ):
        with pytest.raises(ValidationError):
            KnowledgeEquation.model_validate({**_well_formed(), field: value})


def test_null_and_miscast_literals_are_rejected() -> None:
    """canonical_value's type excludes None, and the two literal objects are distinct.

    A quantity spelled with money's `amount` field is the shipped invalid vector; keeping
    the field names distinct is what makes it detectable at all.
    """
    with pytest.raises(ValidationError):
        _LEAF.validate_python(
            {"kind": "typed_value", "concept_id": _BOOLEAN_CONCEPT, "canonical_value": None}
        )
    with pytest.raises(ValidationError):
        _LEAF.validate_python(
            {
                "kind": "typed_value",
                "concept_id": _QUANTITY_CONCEPT,
                "canonical_value": {"amount": "3", "unit": "kg"},
            }
        )


def test_strict_scalars_keep_boolean_and_string_apart() -> None:
    """Without StrictBool/StrictStr, pydantic's union coercion rewrites the value.

    A boolean arriving as the string "True" would be a silent change to what is being
    asserted, so the boolean branch must not absorb strings and vice versa.
    """
    as_boolean = _LEAF.validate_python(_boolean_true())
    assert as_boolean.model_dump(mode="json")["canonical_value"] is True

    as_string = _LEAF.validate_python(
        {"kind": "typed_value", "concept_id": _BOOLEAN_CONCEPT, "canonical_value": "true"}
    )
    assert as_string.model_dump(mode="json")["canonical_value"] == "true"


def test_ontology_ids_must_be_hash_ids() -> None:
    """A Canonical Symbol is not an identity.

    `created_by` and `Boolean` are symbols; accepting them where a hash id belongs is the
    confusion the upstream id scheme exists to prevent.
    """
    with pytest.raises(ValidationError):
        OperatorApplication.model_validate(
            {"kind": "operator_application", "operator_id": "created_by", "arguments": []}
        )
    with pytest.raises(ValidationError):
        _LEAF.validate_python({"kind": "ontology_concept_ref", "concept_id": "Boolean"})


def test_models_are_frozen() -> None:
    """A term carries assertion identity, so mutating one would make "the same KE" hollow."""
    equation = KnowledgeEquation.model_validate(_well_formed())
    with pytest.raises(ValidationError):
        equation.lhs = _application([])  # type: ignore[misc] - frozen is the assertion
