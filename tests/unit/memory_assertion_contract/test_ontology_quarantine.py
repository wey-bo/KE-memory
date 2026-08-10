"""Quarantine, and its independence from semantic validity.

Three properties are asserted here, because getting any one of them wrong would make the
result misleading rather than merely incomplete:

1. A `partial` operator quarantines the snapshot even when nothing is semantically wrong.
   v1 ships no content-addressed registry of definedness predicates, so provisioning has to
   refuse rather than warn.
2. Quarantine does not skip that operator's own structural checks. A partial operator with a
   malformed `required_input_indexes` has two problems and must report both -- the second
   one matters the moment v1 gains a registry.
3. Every partial operator is reported, not just the first. A builder removing one and
   re-running should not discover a second.
"""

from __future__ import annotations

from typing import Any

from memory_assertion_v1.ontology.snapshot import parse_snapshot
from memory_assertion_v1.ontology.validation import SnapshotValidationResult, validate_snapshot

from .snapshots import (
    BELIEVES_ID,
    KNOWS_ID,
    find_operator,
    minimal_snapshot,
    mutate,
    profile_of,
)


def _validate(documents: list[dict[str, Any]]) -> SnapshotValidationResult:
    return validate_snapshot(parse_snapshot(documents))


def _make_partial(
    documents: list[dict[str, Any]],
    operator_id: str,
    *,
    required_input_indexes: list[int] | None = None,
    with_contract: bool = True,
) -> None:
    profile = profile_of(find_operator(documents, operator_id))
    profile["function_semantics"] = {
        "purity": "pure",
        "deterministic": True,
        "partiality": "partial",
    }
    if with_contract:
        profile["definedness_contract"] = {
            "contract_id": "ke-definedness/v1",
            "required_input_indexes": (
                [0] if required_input_indexes is None else required_input_indexes
            ),
            "failure_behavior": "reject_application",
        }


def test_a_well_formed_partial_operator_is_valid_but_quarantined() -> None:
    """The two status dimensions are independent.

    Nothing is wrong with this snapshot; v1 simply cannot deliver it.
    """

    def edit(documents: list[dict[str, Any]]) -> None:
        _make_partial(documents, KNOWS_ID)

    result = _validate(mutate(minimal_snapshot(), edit))
    assert result.semantic_status == "valid"
    assert result.violations == ()
    assert result.provisioning_status == "quarantined"
    assert len(result.quarantine_reasons) == 1
    assert result.quarantine_reasons[0].subject == KNOWS_ID
    assert result.quarantine_reasons[0].code == "partial_operator_unsupported"


def test_partial_without_a_definedness_contract_is_both_invalid_and_quarantined() -> None:
    def edit(documents: list[dict[str, Any]]) -> None:
        _make_partial(documents, KNOWS_ID, with_contract=False)

    result = _validate(mutate(minimal_snapshot(), edit))
    assert result.codes() == ("definedness_contract_required",)
    assert result.semantic_status == "invalid"
    assert result.provisioning_status == "quarantined"


def test_quarantine_does_not_skip_required_input_index_checks() -> None:
    """The structural checks run even though the snapshot is already unprovisionable."""

    def edit(documents: list[dict[str, Any]]) -> None:
        _make_partial(documents, KNOWS_ID, required_input_indexes=[])

    result = _validate(mutate(minimal_snapshot(), edit))
    assert result.codes() == ("required_input_indexes_empty",)
    assert result.provisioning_status == "quarantined"


def test_duplicate_and_out_of_range_required_indexes_are_both_reported() -> None:
    """`knows` has arity 2, so index 5 is out of range and 0 is repeated."""

    def edit(documents: list[dict[str, Any]]) -> None:
        _make_partial(documents, KNOWS_ID, required_input_indexes=[0, 0, 5])

    result = _validate(mutate(minimal_snapshot(), edit))
    assert result.codes() == (
        "required_input_indexes_duplicate",
        "required_input_indexes_out_of_range",
    )
    assert result.provisioning_status == "quarantined"


def test_every_partial_operator_is_reported() -> None:
    """Both, not just the first -- otherwise removing one reveals another."""

    def edit(documents: list[dict[str, Any]]) -> None:
        _make_partial(documents, KNOWS_ID)
        _make_partial(documents, BELIEVES_ID)

    result = _validate(mutate(minimal_snapshot(), edit))
    assert result.provisioning_status == "quarantined"
    subjects = [reason.subject for reason in result.quarantine_reasons]
    assert subjects == sorted([KNOWS_ID, BELIEVES_ID])


def test_quarantine_reasons_are_sorted_reproducibly() -> None:
    """Same snapshot, same order -- a build result has to be diffable."""

    def edit(documents: list[dict[str, Any]]) -> None:
        _make_partial(documents, BELIEVES_ID)
        _make_partial(documents, KNOWS_ID)

    documents = mutate(minimal_snapshot(), edit)
    first = _validate(documents)
    second = _validate(list(reversed(documents)))
    assert [reason.sort_key() for reason in first.quarantine_reasons] == [
        reason.sort_key() for reason in second.quarantine_reasons
    ]
