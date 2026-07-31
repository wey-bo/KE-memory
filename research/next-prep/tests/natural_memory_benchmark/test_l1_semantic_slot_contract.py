"""The model should decide meaning; the program should build structure.

A production L1 proposal currently requires the model to emit a whole
`TypedL1Candidate`: contiguous `entity-NN` identifiers, role bindings that
cross-reference those identifiers, evidence bindings, derivation, lifecycle and
operation provenance. Only a few of those fields carry a semantic judgement. The
rest are mechanical, derivable from the public turn, and scored as if the model
had reasoned about them — which is how `role_or_local_entity_accuracy` could sit
at zero while the model was answering sensibly.

These tests pin the split: a semantic slot payload names the predicate, the
entity surfaces with their roles, modality, polarity and any time value, and the
program materializes everything else deterministically. Character offsets come
from the model but are verified against the raw text rather than trusted, so
substring matching stays a validator instead of becoming the parser.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tools.natural_memory_benchmark.e2e_openai_producers import (
    L1SemanticSlotProposalV1,
    build_diagnostic_production_policy,
    materialize_typed_l1_candidate,
)
from tools.natural_memory_benchmark.l1_ontology_linking import (
    build_diagnostic_ontology_registry,
)


def _slots(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "predicate_surface": "prefer",
        "predicate_sense": "preference_theme",
        "canonical_operator": "prefer",
        "kind": "preference",
        "modality": "actual",
        "polarity": "positive",
        "role_slots": [
            {
                "role": "theme",
                "surface": "coffee",
                "char_start": 0,
                "char_end": 6,
            }
        ],
        "event_time": None,
        "valid_time": None,
    }
    payload.update(overrides)
    return payload


def _materialize(payload: dict[str, object], user_text: str = "coffee is preferred."):
    registry = build_diagnostic_ontology_registry()
    return materialize_typed_l1_candidate(
        slots=L1SemanticSlotProposalV1.model_validate(payload),
        registry=registry,
        policy=build_diagnostic_production_policy(registry),
        user_text=user_text,
        evidence_id="evidence-turn-0000000000000001-user",
    )


def _two_role_slots(**overrides: object) -> dict[str, object]:
    """A two-role operator from the published catalog: add_ingredient."""
    payload = _slots(
        predicate_surface="add",
        predicate_sense="add_ingredient",
        canonical_operator="add_ingredient",
        kind="event",
        role_slots=[
            {"role": "theme", "surface": "milk", "char_start": 6, "char_end": 10},
            {
                "role": "destination",
                "surface": "coffee",
                "char_start": 14,
                "char_end": 20,
            },
        ],
    )
    payload.update(overrides)
    return payload


def test_program_assigns_entity_ids_and_wires_roles() -> None:
    """The model names surfaces and roles; the program owns the identifiers."""
    candidate = _materialize(
        _two_role_slots(),
        user_text="I add milk to coffee.",
    )
    assert [item.local_entity_id for item in candidate.local_entities] == [
        "entity-01",
        "entity-02",
    ]
    assert [item.surface for item in candidate.local_entities] == [
        "milk",
        "coffee",
    ]
    by_role = {item.role: item.local_entity_id for item in candidate.roles}
    assert by_role == {"theme": "entity-01", "destination": "entity-02"}


def test_program_reuses_one_entity_for_a_repeated_surface() -> None:
    """Two roles on the same surface must share one local entity."""
    candidate = _materialize(
        _two_role_slots(
            role_slots=[
                {
                    "role": "theme",
                    "surface": "coffee",
                    "char_start": 14,
                    "char_end": 20,
                },
                {
                    "role": "destination",
                    "surface": "coffee",
                    "char_start": 14,
                    "char_end": 20,
                },
            ]
        ),
        user_text="I add milk to coffee.",
    )
    assert len(candidate.local_entities) == 1
    assert {item.local_entity_id for item in candidate.roles} == {"entity-01"}


def test_program_supplies_evidence_derivation_lifecycle_and_provenance() -> None:
    """None of these are semantic judgements, so the model must not send them."""
    candidate = _materialize(_slots())
    assert [item.evidence_id for item in candidate.evidence_bindings] == [
        "evidence-turn-0000000000000001-user"
    ]
    assert candidate.evidence_bindings[0].speaker == "user"
    assert candidate.derivation.method == "explicit"
    assert candidate.derivation.basis is None
    assert candidate.derivation.evidence_ids == [
        "evidence-turn-0000000000000001-user"
    ]
    assert candidate.lifecycle.lifecycle == "active"
    assert candidate.lifecycle.replaces_candidate_refs == []
    assert candidate.operation_provenance.added_by_operation_refs == []
    fields = set(L1SemanticSlotProposalV1.model_fields)
    for mechanical in (
        "local_entities",
        "roles",
        "evidence_bindings",
        "derivation",
        "lifecycle",
        "operation_provenance",
        "condition_bindings",
        "scope_bindings",
    ):
        assert mechanical not in fields, (
            f"{mechanical} is program-determinable and must not be asked of "
            "the model"
        )


def test_offsets_are_verified_against_the_raw_text() -> None:
    """A surface that does not sit at the stated offsets must fail closed."""
    with pytest.raises(ValueError, match="offset"):
        _materialize(
            _slots(
                role_slots=[
                    {
                        "role": "theme",
                        "surface": "coffee",
                        "char_start": 3,
                        "char_end": 9,
                    }
                ]
            )
        )


def test_a_surface_absent_from_the_turn_fails_closed() -> None:
    """The program verifies grounding rather than inventing a span."""
    with pytest.raises(ValueError, match="offset"):
        _materialize(
            _slots(
                role_slots=[
                    {
                        "role": "theme",
                        "surface": "tea",
                        "char_start": 0,
                        "char_end": 3,
                    }
                ]
            )
        )


def test_role_must_come_from_the_public_operator_catalog() -> None:
    """Role labels stay semantic, so an unpublished role is refused."""
    with pytest.raises(ValueError, match="role"):
        _materialize(
            _slots(
                role_slots=[
                    {
                        "role": "not-a-published-role",
                        "surface": "coffee",
                        "char_start": 0,
                        "char_end": 6,
                    }
                ]
            )
        )


def test_kind_must_match_the_operator_policy() -> None:
    """Operator to kind is a published binding, so a mismatch is refused."""
    with pytest.raises(ValueError, match="kind"):
        _materialize(_slots(kind="event"))


def test_live_producer_asks_for_slots_and_materializes_structure() -> None:
    """The batch producer must send the slot schema and build structure itself."""
    import json
    import sys

    sys.path.insert(0, "tests/natural_memory_benchmark")
    from test_e2e_pipeline_smoke import (
        _chat_response,
        _SequencedOpener,
        _turns,
    )

    from tools.natural_memory_benchmark.e2e_openai_producers import (
        OpenAICompatibleL1BatchProducer,
    )
    from tools.natural_memory_benchmark.e2e_pipeline import _make_source_inputs

    registry = build_diagnostic_ontology_registry()
    slot_payload = {
        "schema_version": "production-l1-slot-batch-response-v1",
        "proposals": [
            {
                "turn_id": "turn-0000000000000001",
                "decision": "emit_l1",
                "slots": _slots(
                    role_slots=[
                        {
                            "role": "theme",
                            "surface": "Coffee",
                            "char_start": 0,
                            "char_end": 6,
                        }
                    ]
                ),
            },
            {
                "turn_id": "turn-0000000000000002",
                "decision": "no_memory",
            },
        ],
    }
    opener = _SequencedOpener([_chat_response(slot_payload)])
    producer = OpenAICompatibleL1BatchProducer(
        registry=registry,
        policy=build_diagnostic_production_policy(registry),
        base_url="https://model.invalid/v1",
        api_key="credential-that-must-not-enter-artifacts",
        model="test-model-response",
        max_attempts=1,
        opener=opener,
    )
    bound = producer.produce(_turns())

    sent = json.loads(opener.requests[0]["messages"][1]["content"])
    schema = json.dumps(sent["public_contract"]["response_schema"])
    assert "role_slots" in schema, "the model must be asked for semantic slots"
    assert "local_entity_id" not in schema, (
        "the model must no longer be asked to build local entity identifiers"
    )

    root = Path(tempfile.mkdtemp())
    _artifact, _sources, inputs = _make_source_inputs(
        _turns(), raw_artifact_path=root / "slot-live.raw.json"
    )
    produced = bound.produce(inputs["turn-0000000000000001"])
    assert len(produced) == 1
    candidate = produced[0].typed_candidate
    # Structure the model never sent, supplied by the program:
    assert [item.local_entity_id for item in candidate.local_entities] == [
        "entity-01"
    ]
    assert candidate.roles[0].local_entity_id == "entity-01"
    assert candidate.derivation.method == "explicit"
    assert candidate.lifecycle.lifecycle == "active"
    assert candidate.evidence_bindings[0].evidence_id == (
        "evidence-turn-0000000000000001-user"
    )
    # And the declining turn yields no candidate at all.
    assert bound.produce(inputs["turn-0000000000000002"]) == []


def test_batch_producer_requests_slots_not_typed_candidates() -> None:
    """The prompt the model actually receives must ask for the slot contract."""
    from tools.natural_memory_benchmark.e2e_openai_producers import (
        ProductionL1SlotBatchResponseV1,
    )

    schema = ProductionL1SlotBatchResponseV1.model_json_schema()
    rendered = str(schema)
    for mechanical in (
        "local_entity_id",
        "evidence_bindings",
        "operation_provenance",
        "replaces_candidate_refs",
    ):
        assert mechanical not in rendered, (
            f"the response schema still asks the model for {mechanical}"
        )
    for semantic in ("role_slots", "canonical_operator", "polarity"):
        assert semantic in rendered, f"the slot schema must still carry {semantic}"
