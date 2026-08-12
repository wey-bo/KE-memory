"""Result-shape properties: nothing short-circuits, and the order is stable.

These are about the result as a whole rather than any individual rule. They are separate
because they are the properties a builder depends on, and because they can hold or break
independently of whether the twelve checks are right.

Parse failures belong here too. A validator that raised on the first malformed field would
report one problem and hide the rest, so a snapshot with a broken record *and* a broken
rule has to come back carrying both.
"""

from __future__ import annotations

from typing import Any

from memory_assertion_v1.ontology.snapshot import parse_snapshot
from memory_assertion_v1.ontology.validation import SnapshotValidationResult, validate_snapshot

from .snapshots import (
    BOOLEAN_ID,
    KNOWS_ID,
    PERSON_ID,
    ROBOT_ID,
    concepts_of,
    find_concept,
    find_operator,
    minimal_snapshot,
    mutate,
    operators_of,
    profile_of,
    shipped_snapshot,
)


def _validate(documents: list[dict[str, Any]]) -> SnapshotValidationResult:
    return validate_snapshot(parse_snapshot(documents))


def test_independent_defects_are_all_reported() -> None:
    """Four unrelated defects, four violations -- no check stops the ones after it.

    Chosen to land in different batches: a duplicate symbol, an unresolved parent, an
    asymmetric disjoint edge and a duplicate parameter name. If validation short-circuited
    anywhere, this set would come back short.
    """

    def edit(documents: list[dict[str, Any]]) -> None:
        find_concept(documents, ROBOT_ID)["canonical_name"] = "Person"
        find_concept(documents, ROBOT_ID)["parents"] = ["concept_ffff00000001"]
        profile_of(find_concept(documents, PERSON_ID))["disjoint_with"] = []
        profile_of(find_operator(documents, KNOWS_ID))["positional_parameters"] = [
            {"index": 0, "name": "same", "definition": "First."},
            {"index": 1, "name": "same", "definition": "Second."},
        ]

    result = _validate(mutate(minimal_snapshot(), edit))
    assert result.codes() == (
        "disjoint_asymmetric",
        "duplicate_concept_symbol",
        "positional_parameter_name_duplicate",
        "unresolved_concept_reference",
    )
    assert result.semantic_status == "invalid"


def test_a_parse_failure_does_not_hide_other_violations() -> None:
    """A malformed record becomes a violation, and the rest of the snapshot is still checked.

    This is why parsing collects instead of raising: the builder with a typo in one Concept
    still needs to hear about the unrelated defect in another.
    """

    def edit(documents: list[dict[str, Any]]) -> None:
        find_concept(documents, ROBOT_ID)["id"] = "not-a-hash-id"
        profile_of(find_operator(documents, KNOWS_ID))["positional_parameters"] = [
            {"index": 0, "name": "same", "definition": "First."},
            {"index": 1, "name": "same", "definition": "Second."},
        ]

    result = _validate(mutate(minimal_snapshot(), edit))
    codes = result.codes()
    assert "record_parse_failed" in codes
    assert "positional_parameter_name_duplicate" in codes
    assert result.semantic_status == "invalid"


def test_a_missing_profile_is_reported_rather_than_raising() -> None:
    """A Concept with no `memory_assertion` namespace cannot be checked, but must be named."""

    def edit(documents: list[dict[str, Any]]) -> None:
        find_concept(documents, ROBOT_ID)["supply"] = {}

    result = _validate(mutate(minimal_snapshot(), edit))
    assert "profile_missing" in result.codes()


def test_a_malformed_profile_is_reported_rather_than_raising() -> None:
    """The superseded contract's vocabulary lands here: unknown keys fail the closed model."""

    def edit(documents: list[dict[str, Any]]) -> None:
        profile_of(find_concept(documents, ROBOT_ID))["core_roles"] = ["core:role.agent"]

    result = _validate(mutate(minimal_snapshot(), edit))
    assert "profile_parse_failed" in result.codes()


def test_a_shard_mixing_artifact_kinds_is_rejected() -> None:
    """Upstream's mutually exclusive top level is what lets a shard be hashed alone."""

    def edit(documents: list[dict[str, Any]]) -> None:
        operators = operators_of(documents)
        concepts_shard = next(document for document in documents if "concepts" in document)
        concepts_shard["operators"] = list(operators)

    result = _validate(mutate(minimal_snapshot(), edit))
    assert "shard_mixes_artifact_kinds" in result.codes()


def test_a_missing_ontology_record_is_reported() -> None:
    def edit(documents: list[dict[str, Any]]) -> None:
        documents[:] = [document for document in documents if "ontology" not in document]

    result = _validate(mutate(minimal_snapshot(), edit))
    assert "ontology_record_missing" in result.codes()


def test_violation_order_is_independent_of_shard_order() -> None:
    """Same snapshot, same list -- so two build runs are diffable.

    Reversing the shards changes the order the records are parsed in, which is exactly the
    kind of incidental difference the sort exists to absorb.
    """

    def edit(documents: list[dict[str, Any]]) -> None:
        find_concept(documents, ROBOT_ID)["canonical_name"] = "Person"
        profile_of(find_concept(documents, PERSON_ID))["disjoint_with"] = []
        profile_of(find_operator(documents, KNOWS_ID))["positional_parameters"] = []

    documents = mutate(minimal_snapshot(), edit)
    forward = _validate(documents)
    reversed_result = _validate(list(reversed(documents)))
    assert forward.codes() == reversed_result.codes()
    assert [violation.sort_key() for violation in forward.violations] == [
        violation.sort_key() for violation in reversed_result.violations
    ]


def test_violation_order_is_independent_of_record_order() -> None:
    """Reordering records within a shard must not reorder the report either."""

    def edit(documents: list[dict[str, Any]]) -> None:
        profile_of(find_concept(documents, PERSON_ID))["disjoint_with"] = []
        profile_of(find_concept(documents, BOOLEAN_ID))["semantic_kind"] = "entity"

    documents = mutate(minimal_snapshot(), edit)
    forward = _validate(documents)

    def reverse_records(copied: list[dict[str, Any]]) -> None:
        concepts_of(copied).reverse()

    shuffled = mutate(documents, reverse_records)
    assert forward.codes() == _validate(shuffled).codes()


def test_the_result_is_sorted_by_code_then_subject() -> None:
    """The documented order, asserted directly rather than inferred from a comparison."""

    def edit(documents: list[dict[str, Any]]) -> None:
        for concept_id in (PERSON_ID, ROBOT_ID):
            profile_of(find_concept(documents, concept_id))["disjoint_with"] = [concept_id]

    result = _validate(mutate(minimal_snapshot(), edit))
    keys = [violation.sort_key() for violation in result.violations]
    assert keys == sorted(keys)


def test_the_shipped_fixture_and_the_minimal_snapshot_agree_on_cleanliness() -> None:
    """Both snapshots validate clean, so neither is carrying the other's assumptions."""
    for documents in (shipped_snapshot(), minimal_snapshot()):
        result = _validate(documents)
        assert result.violations == ()
        assert result.quarantine_reasons == ()
