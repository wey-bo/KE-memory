"""The production L1 contract must express what conversation actually contains.

Phase A's pipeline change let a turn yield zero, one, or several memories, but
the production model contract did not follow: `ProductionL1BatchResponseV1`
rejects duplicate `turn_id`s, `BoundL1CandidateProducer` keys proposals by turn
in a dict, and `_validate_candidate` raises "operational E2E requires emit_l1
for every turn". So the production path still cannot represent a turn with two
facts, nor a turn with none.

The contract also asks the model to echo `candidate_ref`, an identifier the
program allocated and already knows. That is mechanical work the model can only
get wrong, and it is scored as if it were semantic.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import pytest

from tools.natural_memory_benchmark.e2e_openai_producers import (
    ModelBoundaryError,
    OpenAICompatibleL1BatchProducer,
    ProductionL1BatchResponseV1,
    allocate_candidate_ref,
    allocate_support_ref,
    build_diagnostic_production_policy,
)
from tools.natural_memory_benchmark.l1_ontology_linking import (
    build_diagnostic_ontology_registry,
)

from test_e2e_pipeline_smoke import (  # noqa: F401
    _chat_response,
    _production_l1_payload,
    _production_l1_slot_payload,
    _SequencedOpener,
    _turns,
)


def _batch_producer(opener: Any) -> OpenAICompatibleL1BatchProducer:
    registry = build_diagnostic_ontology_registry()
    return OpenAICompatibleL1BatchProducer(
        registry=registry,
        policy=build_diagnostic_production_policy(registry),
        base_url="https://model.invalid/v1",
        api_key="credential-that-must-not-enter-artifacts",
        model="test-model-response",
        max_attempts=1,
        opener=opener,
    )


def _proposal_for(turn_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    for item in payload["proposals"]:
        if item["turn_id"] == turn_id:
            return json.loads(json.dumps(item))
    raise AssertionError(f"no proposal for {turn_id}")


def test_batch_response_accepts_two_proposals_for_one_turn() -> None:
    """A turn stating two facts must be representable in the response."""
    payload = _production_l1_payload()
    first = _proposal_for("turn-0000000000000001", payload)
    second = json.loads(json.dumps(first))
    second["candidate_ref"] = "support-00000000000000c1"
    payload["proposals"] = [
        first,
        second,
        _proposal_for("turn-0000000000000002", payload),
    ]
    response = ProductionL1BatchResponseV1.model_validate(payload)
    refs = [item.candidate_ref for item in response.proposals]
    assert len(refs) == len(set(refs)), "candidate refs must stay unique"
    per_turn = [
        item
        for item in response.proposals
        if item.turn_id == "turn-0000000000000001"
    ]
    assert len(per_turn) == 2


def test_batch_response_still_rejects_duplicate_candidate_refs() -> None:
    """Relaxing turn arity must not relax candidate identity."""
    payload = _production_l1_payload()
    first = _proposal_for("turn-0000000000000001", payload)
    payload["proposals"] = [first, json.loads(json.dumps(first))]
    with pytest.raises(ValueError, match="duplicate production L1 proposal"):
        ProductionL1BatchResponseV1.model_validate(payload)


def test_a_turn_may_carry_no_durable_memory() -> None:
    """A question or control utterance must be an accepted outcome."""
    payload = _production_l1_slot_payload()
    kept = _proposal_for("turn-0000000000000001", payload)
    empty = _proposal_for("turn-0000000000000002", payload)
    empty["decision"] = "no_memory"
    empty.pop("slots", None)
    payload["proposals"] = [kept, empty]
    opener = _SequencedOpener([_chat_response(payload)])
    bound = _batch_producer(opener).produce(_turns())
    inputs = _extraction_inputs()
    # The bound producer must report zero candidates rather than raising.
    assert bound.produce(inputs["turn-0000000000000002"]) == []
    assert len(bound.produce(inputs["turn-0000000000000001"])) == 1


def _extraction_inputs() -> dict[str, Any]:
    from tools.natural_memory_benchmark.e2e_pipeline import _make_source_inputs

    root = Path(tempfile.mkdtemp())
    _artifact, _sources, inputs = _make_source_inputs(
        _turns(),
        raw_artifact_path=root / "production-arity-probe.raw.json",
    )
    return inputs


def test_multiple_candidates_reach_the_pipeline_for_one_turn() -> None:
    """Two proposals on one turn must both be handed to the pipeline."""
    payload = _production_l1_slot_payload()
    first = _proposal_for("turn-0000000000000001", payload)
    second = json.loads(json.dumps(first))
    payload["proposals"] = [
        first,
        second,
        _proposal_for("turn-0000000000000002", payload),
    ]
    opener = _SequencedOpener([_chat_response(payload)])
    bound = _batch_producer(opener).produce(_turns())
    inputs = _extraction_inputs()
    produced = bound.produce(inputs["turn-0000000000000001"])
    assert len(produced) == 2
    assert {item.candidate_ref for item in produced} == {
        allocate_candidate_ref("turn-0000000000000001", 0),
        allocate_candidate_ref("turn-0000000000000001", 1),
    }
    # Ordinal 0 must keep the historical single-candidate value.
    assert allocate_candidate_ref("turn-0000000000000001", 0) == (
        allocate_support_ref("turn-0000000000000001")
    )


def test_model_response_need_not_echo_the_allocated_candidate_ref() -> None:
    """candidate_ref is program-allocated, so the model must not have to guess it."""
    payload = _production_l1_slot_payload()
    for item in payload["proposals"]:
        assert "candidate_ref" not in item
    opener = _SequencedOpener([_chat_response(payload)])
    try:
        bound = _batch_producer(opener).produce(_turns())
    except ModelBoundaryError as error:  # pragma: no cover - diagnostic aid
        pytest.fail(
            "the model should not need to reproduce a program-allocated "
            f"identifier: {error}"
        )
    inputs = _extraction_inputs()
    produced = bound.produce(inputs["turn-0000000000000001"])
    assert len(produced) == 1
    assert produced[0].candidate_ref.startswith("support-")
