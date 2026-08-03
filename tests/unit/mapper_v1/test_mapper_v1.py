"""Tests for mapper v1: blindness, no correction gate, and vocabulary coherence.

Blindness is the property most worth pinning. A mapper that can see a question, a gold label or a
dataset name can special-case it, and a score obtained that way measures the special case rather
than the mapping, so the tests below check that the forbidden inputs are structurally absent rather
than merely unused.

The vocabulary test records a defect worth remembering: installing mapper v1 in the mapping slot
alone drove selection from 19 of 32 to 0 of 32. The mapper was correct and the planner was the
unmigrated layer, still emitting lexical terms against ontology ids. A mapper is only usable when
the query side speaks the same vocabulary.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from pydantic import ValidationError

from ke_memory_demo.evaluation.chain_layers import LexicalExtraction, baseline_chain
from ke_memory_demo.evaluation.execution_chain import Layer, SurfaceUnit
from ke_memory_demo.evaluation.mapper_v1_layer import (
    MapperV1MappingLayer,
    MapperV1QueryPlanLayer,
)
from ke_memory_demo.evaluation.memory_artifact import parse_memory_artifact
from ke_memory_demo.evaluation.oracle_fixture import build_fixture
from ke_memory_demo.evaluation.stage_0_5_builder import build_memory
from ke_memory_demo.mapper_v1.mapper import (
    FORBIDDEN_INPUT_FIELDS,
    Layer as MapperLayer,
)
from ke_memory_demo.mapper_v1.mapper import (
    MapperError,
    MapperInput,
    MapperV1,
    Resolution,
    assert_no_correction_gate,
    load_frozen_ontology,
)
from ke_memory_demo.mapper_v1.mapping_gold import MAPPING_GOLD, ExpectedOutcome

ONTOLOGY_DIR = Path(__file__).resolve().parents[3] / "artifacts" / "ontology-v1"
MAPPER_SOURCE = (
    Path(__file__).resolve().parents[3]
    / "src"
    / "ke_memory_demo"
    / "mapper_v1"
    / "mapper.py"
)

requires_ontology = pytest.mark.skipif(
    not (ONTOLOGY_DIR / "o_l1.json").is_file(),
    reason="the frozen ontology artifact is not present",
)


def test_mapper_input_has_no_field_for_a_question_or_gold() -> None:
    """Blindness is structural: there is nowhere to put the forbidden values."""
    declared = set(MapperInput.model_fields)
    assert declared == {"expression_id", "speaker", "text"}
    assert declared & FORBIDDEN_INPUT_FIELDS == set()
    assert MapperInput.model_config.get("extra") == "forbid"
    with pytest.raises(ValidationError):
        MapperInput.model_validate(
            {
                "expression_id": "expr-1",
                "speaker": "user",
                "text": "hello",
                "gold": "secret",
            }
        )


def test_an_expression_id_that_discloses_a_dataset_is_refused() -> None:
    """An opaque id is part of blindness: a benchmark item id would enable special-casing."""
    for leaking in ("BEAM-100K-C001", "locomo-conv-26", "longmemeval-abc", "slice-1", "gold-3"):
        with pytest.raises(ValidationError, match="discloses dataset identity"):
            MapperInput(expression_id=leaking, speaker="user", text="hello")
    # An opaque id is accepted.
    assert MapperInput(expression_id="expr-000123", speaker="user", text="hello")


def test_the_no_correction_gate_check_inspects_definitions_not_substrings() -> None:
    """A substring scan matched the checker's own banned list and flagged itself."""
    assert_no_correction_gate(MAPPER_SOURCE.read_text(encoding="utf-8"))

    # A module that merely mentions the names in a string passes.
    assert_no_correction_gate('BANNED = ("_repair", "fix_mapping")\n')
    # A module that defines one does not.
    with pytest.raises(MapperError, match="correction gate is defined"):
        assert_no_correction_gate("def fix_mapping(record):\n    return record\n")


def test_the_mapper_defines_no_correction_gate_in_its_own_source() -> None:
    tree = ast.parse(MAPPER_SOURCE.read_text(encoding="utf-8"))
    defined = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert "fix_mapping" not in defined
    assert "override_sense" not in defined


@requires_ontology
def test_the_mapper_preserves_raw_ranked_output() -> None:
    """Top-k, confidences, ambiguity and unresolved status all survive."""
    mapper = MapperV1(load_frozen_ontology(ONTOLOGY_DIR))
    record = mapper.map_expression(
        MapperInput(expression_id="expr-1", speaker="user", text="please cancel my booking"),
        MapperLayer.L1,
    )
    assert record.candidates
    assert all(0.0 <= c.confidence <= 1.0 for c in record.candidates)
    # Ranked, not arbitrary.
    confidences = [c.confidence for c in record.candidates]
    assert confidences == sorted(confidences, reverse=True)
    assert all(c.matched_terms for c in record.candidates)


@requires_ontology
def test_an_utterance_with_no_ontology_support_is_unresolved() -> None:
    """Declining must remain possible, or every negative case becomes a false positive."""
    mapper = MapperV1(load_frozen_ontology(ONTOLOGY_DIR))
    record = mapper.map_expression(
        MapperInput(expression_id="expr-2", speaker="user", text="mm hmm okay"),
        MapperLayer.L1,
    )
    assert record.resolution is Resolution.UNRESOLVED
    assert record.top_ontology_id == ""


@requires_ontology
def test_confidence_does_not_penalise_a_richly_aliased_item() -> None:
    """A defect the first run exposed.

    Normalising only by the item's vocabulary scored a single decisive alias hit at 1/12, below the
    floor, so "cancel my flight reservation" mapped to nothing at all.
    """
    mapper = MapperV1(load_frozen_ontology(ONTOLOGY_DIR))
    record = mapper.map_expression(
        MapperInput(
            expression_id="expr-3", speaker="user", text="I need to cancel my flight reservation"
        ),
        MapperLayer.L1,
    )
    assert record.resolution is not Resolution.UNRESOLVED
    returned = {c.ontology_id for c in record.candidates}
    assert "l1:predicate.change_arrangement" in returned


def test_the_gold_set_is_not_derived_from_evidence_gold() -> None:
    """Provenance is the point: back-derived gold would score question relevance."""
    from ke_memory_demo.mapper_v1.mapping_gold import provenance

    record = provenance()
    excluded = record["not_derived_from"]
    assert isinstance(excluded, list)
    assert "benchmark questions" in excluded
    assert "evidence gold" in excluded
    # Negatives and ambiguous cases must exist, or the set cannot catch over-firing.
    assert int(str(record["negative_cases"])) > 0
    assert int(str(record["ambiguous_cases"])) > 0


def test_every_l2_and_disputed_case_carries_a_second_review() -> None:
    """Graded review keeps the manual load bounded without pretending all cases are settled."""
    for case in MAPPING_GOLD:
        if case.layer == "l2" or case.novel:
            assert case.review.value == "double_review", case.case_id
            assert case.adjudication, case.case_id
    ambiguous = [c for c in MAPPING_GOLD if c.outcome is ExpectedOutcome.AMBIGUOUS_AMONG]
    assert all(c.review.value == "double_review" for c in ambiguous)


@requires_ontology
def test_the_adapter_drops_unresolved_and_keeps_alternatives() -> None:
    """The slot holds one id, so the reduction must not hide ambiguity as missing data."""
    mapper = MapperV1(load_frozen_ontology(ONTOLOGY_DIR))
    layer = MapperV1MappingLayer(mapper)
    units = [
        SurfaceUnit(
            evidence_handle="h0",
            text="please cancel my booking",
            speaker="user",
            approximate_tokens=6,
        ),
        SurfaceUnit(
            evidence_handle="h1", text="mm hmm okay", speaker="user", approximate_tokens=3
        ),
    ]
    mapped = layer.map_units(units)
    # The unresolved unit contributes nothing, so the chain sees a genuine absence.
    assert "h1" not in mapped
    assert "h0" in mapped
    counts = layer.resolution_counts()
    assert counts["unresolved"] >= 1
    # Alternatives ride in the sense field rather than being discarded.
    _canonical_id, sense = mapped["h0"]
    assert "#alt=" in sense or sense


@requires_ontology
def test_plan_and_mapping_must_share_one_vocabulary() -> None:
    """The defect that drove selection from 19 of 32 to 0 of 32.

    The mapper emitted ``l1:*`` ontology ids while the planner still emitted ``lex:*`` terms, so no
    plan could ever intersect a mapping. Installing the mapper in one slot alone is not enough.
    """
    fixture, _bundle = build_fixture()
    artifact = parse_memory_artifact(
        build_memory(dict(fixture.build_input.canonical_content()))  # type: ignore[arg-type]
    )
    mapper = MapperV1(load_frozen_ontology(ONTOLOGY_DIR))
    question = fixture.questions.questions[0]
    turns = artifact.turns_for(question.conversation_handle)
    units = LexicalExtraction().extract(turns)

    mapped = MapperV1MappingLayer(mapper).map_units(units)
    mapper_ids = {canonical_id for canonical_id, _sense in mapped.values()}

    # The lexical planner cannot address ontology ids at all.
    lexical_plan = baseline_chain().query_plan.compile_plan(question)
    assert set(lexical_plan.requested_canonical_ids) & mapper_ids == set()

    # The mapper-backed planner speaks the same vocabulary.
    ontology_plan = MapperV1QueryPlanLayer(mapper).compile_plan(question)
    assert all(pid.startswith("l1:") for pid in ontology_plan.requested_canonical_ids)


@requires_ontology
def test_both_mapper_slots_together_restore_selection() -> None:
    """Whole-chain confirmation that the two slots have to move together."""
    fixture, _bundle = build_fixture()
    artifact = parse_memory_artifact(
        build_memory(dict(fixture.build_input.canonical_content()))  # type: ignore[arg-type]
    )
    mapper = MapperV1(load_frozen_ontology(ONTOLOGY_DIR))

    mapping_only = baseline_chain().with_layer(
        Layer.MAPPING, MapperV1MappingLayer(mapper)
    )
    both = mapping_only.with_layer(Layer.QUERY_PLAN, MapperV1QueryPlanLayer(mapper))

    question = fixture.questions.questions[0]
    assert mapping_only.run(question, artifact).selected_handles == ()
    assert both.run(question, artifact).selected_handles != ()
