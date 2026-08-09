"""The five LeafTerms, asserted against the shipped leaf-term vectors.

Each of the 11 vectors is a case the specification already committed to, so a failure
here is a real disagreement between the models and the contract -- not a disagreement
with a test author.
"""

from __future__ import annotations

from typing import Any

from pydantic import TypeAdapter, ValidationError
import pytest

from memory_assertion_v1 import LeafTerm

from .vectors import EXPECTED_LEAF_TERM_COUNT, load_vectors

_ADAPTER: TypeAdapter[LeafTerm] = TypeAdapter(LeafTerm)


def _leaf_term_vectors() -> list[dict[str, Any]]:
    vectors = load_vectors()["leaf_term_examples"]
    assert len(vectors) == EXPECTED_LEAF_TERM_COUNT, (
        f"expected {EXPECTED_LEAF_TERM_COUNT} leaf-term vectors, found {len(vectors)}"
    )
    return list(vectors)


def _ids(vectors: list[dict[str, Any]]) -> list[str]:
    return [vector["name"] for vector in vectors]


_VECTORS = _leaf_term_vectors()
_VALID = [vector for vector in _VECTORS if vector["expected_valid"]]
_INVALID = [vector for vector in _VECTORS if not vector["expected_valid"]]


def test_vectors_cover_both_outcomes() -> None:
    """Both lists must be non-empty.

    A parametrized test over an empty list passes silently, so the split itself is
    asserted -- otherwise a vector file that lost all its negative cases would still look
    green.
    """
    assert len(_VALID) == 6
    assert len(_INVALID) == 5


@pytest.mark.parametrize("vector", _VALID, ids=_ids(_VALID))
def test_valid_leaf_terms_construct(vector: dict[str, Any]) -> None:
    term = _ADAPTER.validate_python(vector["term"])
    # Round-tripping is what makes this more than a smoke test: the model must preserve
    # the vector rather than merely accept it, or a dropped field would pass unnoticed.
    assert _ADAPTER.dump_python(term, mode="json", exclude_defaults=False) == vector["term"]


@pytest.mark.parametrize("vector", _INVALID, ids=_ids(_INVALID))
def test_invalid_leaf_terms_are_rejected(vector: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        _ADAPTER.validate_python(vector["term"])
