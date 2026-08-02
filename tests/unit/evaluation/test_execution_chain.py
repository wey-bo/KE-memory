"""Tests for the real execution chain and artifact consumption.

Two properties are load-bearing here, and both were previously claimed without being true:

The chain consumes the builder artifact. An earlier version recorded ``memory_artifact_sha256``
while no stage read the artifact, so the chain was disconnected in the middle and every downstream
number rested on raw turns.

A substitution is locatable. Per-layer output hashes make "only the target layer changed" a
checked property rather than an assertion about intent.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ke_memory_demo.evaluation.chain_layers import (
    LAYER_FOR_ORACLE,
    GoldAbstractionLayer,
    GoldExtractionLayer,
    GoldMappingLayer,
    GoldQueryPlanLayer,
    GoldRetrievalLayer,
    baseline_chain,
)
from ke_memory_demo.evaluation.execution_chain import (
    ChainError,
    Layer,
    assert_artifact_read_by_every_layer,
    assert_only_target_and_downstream_changed,
    changed_layers,
    downstream_of,
)
from ke_memory_demo.evaluation.memory_artifact import (
    MemoryArtifactError,
    artifact_turn_count,
    assert_artifact_consumed,
    parse_memory_artifact,
    turn_digest,
)
from ke_memory_demo.evaluation.oracle_fixture import build_fixture
from ke_memory_demo.evaluation.stage_0_5_builder import (
    BUILDER_ID,
    turn_content_digest,
    build_memory,
)


def _fixture_artifact():
    fixture, bundle = build_fixture()
    payload = build_memory(dict(fixture.build_input.canonical_content()))  # type: ignore[arg-type]
    return fixture, bundle, parse_memory_artifact(payload)


def test_the_builder_emits_an_artifact_a_consumer_can_read() -> None:
    """The earlier builder returned counts, which nothing downstream could consume."""
    _fixture, _bundle, artifact = _fixture_artifact()
    assert artifact.builder_id == BUILDER_ID
    assert artifact_turn_count(artifact) > 0
    # Handles, session membership and per-turn digests are what make it consumable.
    conversation = artifact.conversations[0]
    assert conversation.session_handles
    assert artifact.members_of(conversation.session_handles[0])
    assert all(len(t.content_sha256) == 64 for t in conversation.turns)


def test_the_sandbox_builder_digest_matches_the_shared_formula() -> None:
    """The builder cannot import the package, so the duplicate formula needs pinning."""
    assert turn_content_digest("user", "hello") == turn_digest("user", "hello")


def test_consumption_is_provable_not_assertable() -> None:
    _fixture, _bundle, artifact = _fixture_artifact()
    assert_artifact_consumed(artifact, artifact.content_digest())
    with pytest.raises(MemoryArtifactError, match="recording a hash is not consumption"):
        assert_artifact_consumed(artifact, "0" * 64)


def test_every_layer_records_the_artifact_it_read() -> None:
    fixture, _bundle, artifact = _fixture_artifact()
    result = baseline_chain().run(fixture.questions.questions[0], artifact)
    assert_artifact_read_by_every_layer(result)
    # Nine stages are declared; the chain traces the eight it executes.
    assert {trace.layer for trace in result.traces} == set(Layer) - {Layer.BUILD_INPUT}
    assert all(trace.artifact_sha256 == artifact.content_digest() for trace in result.traces)


def test_a_layer_that_read_a_different_artifact_is_rejected() -> None:
    fixture, _bundle, artifact = _fixture_artifact()
    result = baseline_chain().run(fixture.questions.questions[0], artifact)
    tampered = result.traces[0].model_copy(update={"artifact_sha256": "0" * 64})
    forged = result.__class__(
        question_id=result.question_id,
        selected_handles=result.selected_handles,
        delivered_handles=result.delivered_handles,
        answer_text=result.answer_text,
        abstained=result.abstained,
        traces=(tampered, *result.traces[1:]),
        artifact_sha256=result.artifact_sha256,
    )
    with pytest.raises(ChainError, match="did not read the consumed artifact"):
        assert_artifact_read_by_every_layer(forged)


def test_each_oracle_changes_its_own_layer_and_nothing_upstream() -> None:
    fixture, bundle, artifact = _fixture_artifact()
    chain = baseline_chain()

    for oracle, layer in LAYER_FOR_ORACLE.items():
        for question in fixture.questions.questions:
            layer_gold = bundle.for_question(question.question_id)
            assert layer_gold is not None
            if oracle == "gold_evidence_selection":
                label = fixture.gold.label_for(question.question_id)
                assert label is not None
                replacement: object = GoldRetrievalLayer(label.evidence_refs)
            elif oracle == "gold_extraction":
                replacement = GoldExtractionLayer(layer_gold)
            elif oracle == "gold_memory_mapping":
                replacement = GoldMappingLayer(layer_gold)
            elif oracle == "gold_l2_abstraction":
                replacement = GoldAbstractionLayer(layer_gold)
            else:
                replacement = GoldQueryPlanLayer(layer_gold)

            baseline = chain.run(question, artifact)
            substituted = chain.with_layer(layer, replacement).run(question, artifact)
            changed = changed_layers(baseline, substituted)
            # The positive half: a substitution that changes nothing substituted nothing.
            assert layer in changed, f"{oracle} did not change {layer}"
            assert_only_target_and_downstream_changed(layer, changed)


def test_a_plan_substitution_may_not_disturb_earlier_layers() -> None:
    """Ordering is a real constraint: a plan cannot alter extraction or mapping."""
    allowed = downstream_of(Layer.QUERY_PLAN)
    assert Layer.EXTRACTION not in allowed
    assert Layer.MAPPING not in allowed
    assert Layer.RETRIEVAL in allowed
    with pytest.raises(ChainError, match="cannot influence"):
        assert_only_target_and_downstream_changed(
            Layer.QUERY_PLAN, frozenset({Layer.QUERY_PLAN, Layer.EXTRACTION})
        )


def test_the_gold_retrieval_oracle_is_exact_on_the_fixture() -> None:
    """The falsifiability check: a perfect retrieval layer must score perfectly."""
    fixture, _bundle, artifact = _fixture_artifact()
    chain = baseline_chain()
    for question in fixture.questions.questions:
        label = fixture.gold.label_for(question.question_id)
        assert label is not None
        substituted = chain.with_layer(
            Layer.RETRIEVAL, GoldRetrievalLayer(label.evidence_refs)
        )
        result = substituted.run(question, artifact)
        assert set(result.selected_handles) == set(label.evidence_refs)


def test_mapping_ignores_numeric_tokens() -> None:
    """A real defect the traced chain exposed.

    Taking the alphabetically first term let digits win, so nearly every unit mapped to something
    like ``lex:000`` and no question could ever overlap the mapping.
    """
    from ke_memory_demo.evaluation.chain_layers import LexicalMapping, SurfaceUnit

    unit = SurfaceUnit(
        evidence_handle="h0",
        text="000 111 deployment finished on Friday",
        speaker="user",
        approximate_tokens=8,
    )
    mapped = LexicalMapping().map_units([unit])
    canonical_id, senses = mapped["h0"]
    assert not canonical_id.removeprefix("lex:").isdigit()
    assert "deployment" in senses


def test_the_rehearsal_script_checks_the_four_acceptance_properties() -> None:
    """Stage 3 acceptance is about instruments, so the checks must be present in the script."""
    script = (
        Path(__file__).resolve().parents[3] / "scripts" / "stage_3_rehearsal.py"
    ).read_text(encoding="utf-8")
    assert "assert_artifact_read_by_every_layer" in script
    assert "assert_only_target_and_downstream_changed" in script
    assert "_assert_no_gold_in_chain" in script
    assert "never fresh hidden again" in script
    # No quality threshold may creep in.
    assert "no model-quality pass line" in script
