"""Every semantic check, proven by breaking the thing it checks.

A check that has never seen a failing snapshot has not been shown to work. So each rule
here gets a mutation that violates exactly it, and the assertion names the code that must
come back.

Two assertion styles, deliberately:

- **Isolated mutations** assert the exact violation set, usually one code. These are edits
  whose consequences do not spread.
- **Cascading mutations** assert the full, stable set. Deleting a Concept breaks every
  reference to it, and pretending otherwise would either weaken the assertion to "at
  least one violation" or make it brittle.

Both snapshots are covered. The independent one matters most: the harness this replaces
could only ever validate the shipped fixture, and a validator that quietly depended on it
would look identical from the outside.
"""

from __future__ import annotations

from typing import Any

from memory_assertion_v1.ontology.snapshot import parse_snapshot
from memory_assertion_v1.ontology.validation import SnapshotValidationResult, validate_snapshot

from .snapshots import (
    BELIEVES_ID,
    BOOLEAN_ID,
    KNOWS_ID,
    PERSON_ID,
    PROPOSITION_ID,
    ROBOT_ID,
    THING_ID,
    concepts_of,
    find_concept,
    find_operator,
    minimal_snapshot,
    mutate,
    profile_of,
    shipped_snapshot,
)


def _validate(documents: list[dict[str, Any]]) -> SnapshotValidationResult:
    return validate_snapshot(parse_snapshot(documents))


def test_shipped_fixture_is_valid_and_eligible() -> None:
    """The positive baseline: 13 Concepts, 4 Operators, nothing wrong."""
    snapshot = parse_snapshot(shipped_snapshot())
    assert len(snapshot.concepts) == 13
    assert len(snapshot.operators) == 4
    assert snapshot.parse_violations == []

    result = validate_snapshot(snapshot)
    assert result.semantic_status == "valid"
    assert result.provisioning_status == "eligible"
    assert result.violations == ()


def test_independent_snapshot_is_valid_and_eligible() -> None:
    """The validator does not depend on the shipped fixture.

    This snapshot is constructed in the test package and shares no id with the fixture, so
    passing here means the rules read the snapshot they were given.
    """
    result = _validate(minimal_snapshot())
    assert result.semantic_status == "valid"
    assert result.provisioning_status == "eligible"
    assert result.violations == ()


# --- Batch 1: identity and reference closure ---------------------------------------


def test_duplicate_concept_symbol_is_reported() -> None:
    def edit(documents: list[dict[str, Any]]) -> None:
        find_concept(documents, ROBOT_ID)["canonical_name"] = "Person"

    result = _validate(mutate(minimal_snapshot(), edit))
    assert result.codes() == ("duplicate_concept_symbol",)


def test_duplicate_operator_symbol_is_reported() -> None:
    def edit(documents: list[dict[str, Any]]) -> None:
        find_operator(documents, BELIEVES_ID)["canonical_name"] = "knows"

    result = _validate(mutate(minimal_snapshot(), edit))
    assert result.codes() == ("duplicate_operator_symbol",)


def test_duplicate_concept_id_is_reported() -> None:
    """A repeated id would otherwise overwrite silently in the id-keyed map."""

    def edit(documents: list[dict[str, Any]]) -> None:
        records = concepts_of(documents)
        clone = dict(records[0])
        clone["canonical_name"] = "Clone"
        records.append(clone)

    result = _validate(mutate(minimal_snapshot(), edit))
    assert result.codes() == ("duplicate_concept_id",)


def test_unresolved_parent_reference_is_reported() -> None:
    def edit(documents: list[dict[str, Any]]) -> None:
        find_concept(documents, PERSON_ID)["parents"] = ["concept_ffff00000009"]

    result = _validate(mutate(minimal_snapshot(), edit))
    assert result.codes() == ("unresolved_concept_reference",)


def test_self_parent_is_reported() -> None:
    def edit(documents: list[dict[str, Any]]) -> None:
        find_concept(documents, PERSON_ID)["parents"] = [PERSON_ID]

    result = _validate(mutate(minimal_snapshot(), edit))
    assert result.codes() == ("concept_self_parent",)


def test_inheritance_cycle_names_every_member() -> None:
    """Cascading: the cycle also makes the disjoint pair unsatisfiable.

    `Thing` inheriting `Person` puts `Robot` under `Person` too, so a Concept now inherits
    both sides of a pair declared disjoint. Asserting the whole set keeps that consequence
    visible instead of letting a narrower assertion hide it.
    """

    def edit(documents: list[dict[str, Any]]) -> None:
        find_concept(documents, THING_ID)["parents"] = [PERSON_ID]

    result = _validate(mutate(minimal_snapshot(), edit))
    assert result.codes() == (
        "concept_inheritance_cycle",
        "concept_inheritance_cycle",
        "disjoint_ancestor_conflict",
        "disjoint_ancestor_conflict",
        "disjoint_unsatisfiable_inheritance",
    )
    subjects = {violation.subject for violation in result.violations}
    assert {PERSON_ID, THING_ID} <= subjects


def test_operator_input_and_output_references_must_resolve() -> None:
    def edit(documents: list[dict[str, Any]]) -> None:
        operator = find_operator(documents, KNOWS_ID)
        operator["input_concepts"] = ["concept_ffff00000009", PERSON_ID]
        operator["output_concept"] = "concept_ffff00000008"

    result = _validate(mutate(minimal_snapshot(), edit))
    assert result.codes() == (
        "unresolved_concept_reference",
        "unresolved_concept_reference",
    )


def test_deleting_a_concept_reports_the_full_cascade() -> None:
    """Cascading: every reference to the removed Concept is named.

    Asserted as the complete set rather than "at least one", so a check that stopped
    reporting one of these would fail here.
    """

    def edit(documents: list[dict[str, Any]]) -> None:
        records = concepts_of(documents)
        records[:] = [record for record in records if record["id"] != PERSON_ID]

    result = _validate(mutate(minimal_snapshot(), edit))
    assert result.codes() == (
        "disjoint_unresolved",
        "unresolved_concept_reference",
        "unresolved_concept_reference",
        "unresolved_concept_reference",
    )


# --- Batch 1: deprecation chains ---------------------------------------------------


def test_replaced_by_requires_deprecation() -> None:
    def edit(documents: list[dict[str, Any]]) -> None:
        profile_of(find_concept(documents, ROBOT_ID))["replaced_by"] = PERSON_ID

    result = _validate(mutate(minimal_snapshot(), edit))
    assert result.codes() == ("replaced_by_without_deprecation",)


def test_replaced_by_self_is_reported() -> None:
    def edit(documents: list[dict[str, Any]]) -> None:
        profile = profile_of(find_concept(documents, ROBOT_ID))
        profile["deprecated"] = True
        profile["replaced_by"] = ROBOT_ID

    result = _validate(mutate(minimal_snapshot(), edit))
    assert result.codes() == ("replaced_by_self",)


def test_replaced_by_must_resolve() -> None:
    def edit(documents: list[dict[str, Any]]) -> None:
        profile = profile_of(find_concept(documents, ROBOT_ID))
        profile["deprecated"] = True
        profile["replaced_by"] = "concept_ffff00000007"

    result = _validate(mutate(minimal_snapshot(), edit))
    assert result.codes() == ("replaced_by_unresolved",)


def test_replacement_cycle_is_reported() -> None:
    """Two deprecated Concepts pointing at each other never reach a live identity."""

    def edit(documents: list[dict[str, Any]]) -> None:
        person = profile_of(find_concept(documents, PERSON_ID))
        robot = profile_of(find_concept(documents, ROBOT_ID))
        person["deprecated"] = True
        person["replaced_by"] = ROBOT_ID
        robot["deprecated"] = True
        robot["replaced_by"] = PERSON_ID

    result = _validate(mutate(minimal_snapshot(), edit))
    assert result.codes() == ("replaced_by_cycle", "replaced_by_cycle")


def test_replacement_chain_must_end_undeprecated() -> None:
    """A chain ending on a deprecated record leaves the consumer nowhere to go."""

    def edit(documents: list[dict[str, Any]]) -> None:
        robot = profile_of(find_concept(documents, ROBOT_ID))
        robot["deprecated"] = True
        robot["replaced_by"] = PERSON_ID
        profile_of(find_concept(documents, PERSON_ID))["deprecated"] = True

    result = _validate(mutate(minimal_snapshot(), edit))
    assert result.codes() == ("replaced_by_chain_ends_deprecated",)


# --- Batch 2: Concept semantics ----------------------------------------------------


def test_self_disjointness_is_reported() -> None:
    def edit(documents: list[dict[str, Any]]) -> None:
        profile_of(find_concept(documents, PERSON_ID))["disjoint_with"] = [PERSON_ID]

    result = _validate(mutate(minimal_snapshot(), edit))
    assert result.codes() == ("disjoint_asymmetric", "disjoint_self")


def test_asymmetric_disjointness_is_reported() -> None:
    """The reverse edge must be written, not inferred."""

    def edit(documents: list[dict[str, Any]]) -> None:
        profile_of(find_concept(documents, ROBOT_ID))["disjoint_with"] = []

    result = _validate(mutate(minimal_snapshot(), edit))
    assert result.codes() == ("disjoint_asymmetric",)


def test_disjointness_with_an_ancestor_is_reported() -> None:
    """Cascading: the explicit edge is symmetric, so both sides report the conflict."""

    def edit(documents: list[dict[str, Any]]) -> None:
        profile_of(find_concept(documents, PERSON_ID))["disjoint_with"] = [ROBOT_ID, THING_ID]
        profile_of(find_concept(documents, THING_ID))["disjoint_with"] = [PERSON_ID]

    result = _validate(mutate(minimal_snapshot(), edit))
    assert result.codes() == (
        "disjoint_ancestor_conflict",
        "disjoint_ancestor_conflict",
        "disjoint_unsatisfiable_inheritance",
    )


def test_inheriting_both_sides_of_a_disjoint_pair_is_unsatisfiable() -> None:
    """Derived from the closure: no instance of such a Concept could exist.

    The derived relation is used for validation only; nothing is written back into
    `disjoint_with`.
    """

    def edit(documents: list[dict[str, Any]]) -> None:
        concepts_of(documents).append(
            {
                "id": "concept_aaaa00000006",
                "canonical_name": "Android",
                "description": "Inherits from both sides.",
                "sources": ["sources/test/v1/manifest.json#/entities/x"],
                "created_at": "2026-08-09T00:00:00Z",
                "parents": [PERSON_ID, ROBOT_ID],
                "supply": {
                    "memory_assertion": {
                        "profile_version": "memory-assertion/v1",
                        "semantic_kind": "entity",
                        "lexicalizations": [],
                    }
                },
            }
        )

    result = _validate(mutate(minimal_snapshot(), edit))
    assert result.codes() == ("disjoint_unsatisfiable_inheritance",)
    assert result.violations[0].subject == "concept_aaaa00000006"


def test_literal_contract_is_required_for_literal_kinds() -> None:
    """Cascading: `believes` outputs Boolean, so losing the codec breaks its output rule too.

    Every mutation of the Boolean Concept has this shape -- the attitude operator's output
    must be a boolean-codec Concept, and there is only one of those in this snapshot.
    """

    def edit(documents: list[dict[str, Any]]) -> None:
        del profile_of(find_concept(documents, BOOLEAN_ID))["literal_value_contract"]

    result = _validate(mutate(minimal_snapshot(), edit))
    assert result.codes() == (
        "literal_contract_required",
        "proposition_operation_output_invalid",
    )


def test_literal_contract_is_forbidden_on_other_kinds() -> None:
    """A contract on an entity would imply entities have canonical literal spellings."""

    def edit(documents: list[dict[str, Any]]) -> None:
        profile_of(find_concept(documents, PERSON_ID))["literal_value_contract"] = {
            "codec_id": "ke-literal:boolean/v1",
            "canonical_json_kind": "boolean",
            "equality_mode": "canonical_json_identity",
            "accepts_null": False,
        }

    result = _validate(mutate(minimal_snapshot(), edit))
    assert result.codes() == ("literal_contract_forbidden",)


def test_codec_json_kind_must_match_the_codec() -> None:
    def edit(documents: list[dict[str, Any]]) -> None:
        contract = profile_of(find_concept(documents, BOOLEAN_ID))["literal_value_contract"]
        contract["canonical_json_kind"] = "string"

    result = _validate(mutate(minimal_snapshot(), edit))
    assert result.codes() == ("literal_codec_kind_mismatch",)


def test_unknown_codec_fails_to_parse_rather_than_passing() -> None:
    """The codec set is closed: an unknown id makes the snapshot invalid.

    Reported as a profile parse failure because the enum is closed in the model, which is
    the earliest place it can be caught.
    """

    def edit(documents: list[dict[str, Any]]) -> None:
        contract = profile_of(find_concept(documents, BOOLEAN_ID))["literal_value_contract"]
        contract["codec_id"] = "ke-literal:invented/v1"

    result = _validate(mutate(minimal_snapshot(), edit))
    assert "profile_parse_failed" in result.codes()
    assert result.semantic_status == "invalid"


def test_money_contract_needs_sorted_unique_currencies() -> None:
    """Cascading via Boolean: retyping the only boolean Concept breaks `believes`'s output."""

    def edit(documents: list[dict[str, Any]]) -> None:
        profile = profile_of(find_concept(documents, BOOLEAN_ID))
        profile["literal_value_contract"] = {
            "codec_id": "ke-literal:money/v1",
            "canonical_json_kind": "object",
            "equality_mode": "canonical_json_identity",
            "accepts_null": False,
            "currency_minor_units": [
                {"currency": "JPY", "minor_units": 0},
                {"currency": "CNY", "minor_units": 2},
                {"currency": "CNY", "minor_units": 2},
            ],
        }

    result = _validate(mutate(minimal_snapshot(), edit))
    assert result.codes() == (
        "currency_minor_units_duplicate",
        "currency_minor_units_unsorted",
        "proposition_operation_output_invalid",
    )


def test_quantity_contract_needs_a_canonical_unit() -> None:
    """Cascading via Boolean, same reason as the money case."""

    def edit(documents: list[dict[str, Any]]) -> None:
        profile = profile_of(find_concept(documents, BOOLEAN_ID))
        profile["literal_value_contract"] = {
            "codec_id": "ke-literal:quantity/v1",
            "canonical_json_kind": "object",
            "equality_mode": "canonical_json_identity",
            "accepts_null": False,
        }

    result = _validate(mutate(minimal_snapshot(), edit))
    assert result.codes() == (
        "proposition_operation_output_invalid",
        "quantity_contract_incomplete",
    )


# --- Batch 3: Operator signatures --------------------------------------------------


def test_positional_parameter_count_must_match_arity() -> None:
    def edit(documents: list[dict[str, Any]]) -> None:
        profile = profile_of(find_operator(documents, KNOWS_ID))
        profile["positional_parameters"] = [
            {"index": 0, "name": "only", "definition": "Only one."}
        ]

    result = _validate(mutate(minimal_snapshot(), edit))
    assert result.codes() == ("positional_parameter_count_mismatch",)


def test_positional_parameter_indexes_must_be_contiguous_in_order() -> None:
    def edit(documents: list[dict[str, Any]]) -> None:
        profile = profile_of(find_operator(documents, KNOWS_ID))
        profile["positional_parameters"] = [
            {"index": 1, "name": "b", "definition": "Second."},
            {"index": 0, "name": "a", "definition": "First."},
        ]

    result = _validate(mutate(minimal_snapshot(), edit))
    assert result.codes() == ("positional_parameter_index_broken",)


def test_positional_parameter_names_must_be_unique() -> None:
    def edit(documents: list[dict[str, Any]]) -> None:
        profile = profile_of(find_operator(documents, KNOWS_ID))
        profile["positional_parameters"] = [
            {"index": 0, "name": "same", "definition": "First."},
            {"index": 1, "name": "same", "definition": "Second."},
        ]

    result = _validate(mutate(minimal_snapshot(), edit))
    assert result.codes() == ("positional_parameter_name_duplicate",)


def test_none_forbids_proposition_inputs() -> None:
    def edit(documents: list[dict[str, Any]]) -> None:
        find_operator(documents, KNOWS_ID)["input_concepts"] = [PERSON_ID, PROPOSITION_ID]

    result = _validate(mutate(minimal_snapshot(), edit))
    assert result.codes() == ("proposition_operation_input_invalid",)


def test_attitude_needs_exactly_one_proposition_and_a_holder() -> None:
    def edit(documents: list[dict[str, Any]]) -> None:
        find_operator(documents, BELIEVES_ID)["input_concepts"] = [
            PROPOSITION_ID,
            PROPOSITION_ID,
        ]

    result = _validate(mutate(minimal_snapshot(), edit))
    assert result.codes() == (
        "proposition_operation_input_invalid",
        "proposition_operation_input_invalid",
    )
    details = sorted(violation.detail for violation in result.violations)
    assert "attitude needs at least one non-proposition holder input" in details


def test_attitude_must_output_a_boolean_codec_concept() -> None:
    def edit(documents: list[dict[str, Any]]) -> None:
        find_operator(documents, BELIEVES_ID)["output_concept"] = PERSON_ID

    result = _validate(mutate(minimal_snapshot(), edit))
    assert result.codes() == ("proposition_operation_output_invalid",)


def test_modifier_output_must_not_be_a_proposition() -> None:
    """One violation, not two: `modifier` forbids a Proposition output but does not require
    a boolean one. Only `attitude` and `relation` carry the boolean-codec requirement, which
    is why converting this operator to a modifier removes it.
    """

    def edit(documents: list[dict[str, Any]]) -> None:
        operator = find_operator(documents, BELIEVES_ID)
        operator["input_concepts"] = [PROPOSITION_ID]
        operator["output_concept"] = PROPOSITION_ID
        profile = profile_of(operator)
        profile["proposition_operation"] = "modifier"
        profile["positional_parameters"] = [
            {"index": 0, "name": "arg0", "definition": "The proposition."}
        ]

    result = _validate(mutate(minimal_snapshot(), edit))
    assert result.codes() == ("proposition_operation_output_invalid",)


def test_relation_needs_a_proposition_input() -> None:
    def edit(documents: list[dict[str, Any]]) -> None:
        profile_of(find_operator(documents, KNOWS_ID))["proposition_operation"] = "relation"

    result = _validate(mutate(minimal_snapshot(), edit))
    assert result.codes() == ("proposition_operation_input_invalid",)


def test_total_operators_must_not_carry_a_definedness_contract() -> None:
    def edit(documents: list[dict[str, Any]]) -> None:
        profile_of(find_operator(documents, KNOWS_ID))["definedness_contract"] = {
            "contract_id": "ke-definedness/v1",
            "required_input_indexes": [0],
            "failure_behavior": "reject_application",
        }

    result = _validate(mutate(minimal_snapshot(), edit))
    assert result.codes() == ("definedness_contract_forbidden",)
    assert result.provisioning_status == "eligible"
