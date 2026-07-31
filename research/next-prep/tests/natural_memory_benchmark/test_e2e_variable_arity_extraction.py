"""A turn may carry zero, one, or several durable memories.

The pipeline required exactly one L1 proposal per turn and exactly one L2
proposal per run. Real conversation does not work that way: a question or a
control utterance should produce no memory at all, and a single turn can state
several independent facts. Forcing 1:1 causes both silent omission and
unauthorized emission, and `TurnBundleRevision` already models the
zero-extraction case (`extraction_state="complete"` with a `no_memory_reason`
and no L1 units), so the restriction lives only in the pipeline.
"""

from __future__ import annotations

from pathlib import Path

from tools.natural_memory_benchmark.e2e_pipeline import (
    ProposedL1CandidateV1,
    RawTurnV1,
    TurnExtractionInputV1,
    run_e2e_pipeline,
)

from test_e2e_pipeline_smoke import (  # noqa: F401
    SUPPORT_HABIT,
    SUPPORT_PREFERENCE,
    _L1Producer,
    _L2Producer,
    _QueryProducer,
    _turns,
    _typed_l1,
)


SUPPORT_SECOND_FACT = "support-00000000000000c1"


class _NoMemoryL1Producer:
    """Emits nothing for a turn that states no durable fact."""

    def __init__(self) -> None:
        self.seen: list[str] = []

    def produce(
        self, value: TurnExtractionInputV1
    ) -> list[ProposedL1CandidateV1]:
        self.seen.append(value.turn.turn_id)
        if value.turn.turn_index == 0:
            return [
                ProposedL1CandidateV1(
                    candidate_ref=SUPPORT_PREFERENCE,
                    typed_candidate=_typed_l1(
                        value,
                        predicate_surface="prefer",
                        predicate_sense="preference_theme",
                        canonical_operator="prefer",
                        entity_surface="coffee",
                    ),
                )
            ]
        return []


class _MultiFactL1Producer:
    """Emits two independent candidates for a single turn."""

    def produce(
        self, value: TurnExtractionInputV1
    ) -> list[ProposedL1CandidateV1]:
        if value.turn.turn_index == 0:
            return [
                ProposedL1CandidateV1(
                    candidate_ref=SUPPORT_PREFERENCE,
                    typed_candidate=_typed_l1(
                        value,
                        predicate_surface="prefer",
                        predicate_sense="preference_theme",
                        canonical_operator="prefer",
                        entity_surface="coffee",
                    ),
                ),
                ProposedL1CandidateV1(
                    candidate_ref=SUPPORT_SECOND_FACT,
                    typed_candidate=_typed_l1(
                        value,
                        predicate_surface="drink",
                        predicate_sense="consume_beverage",
                        canonical_operator="drink",
                        entity_surface="coffee",
                    ),
                ),
            ]
        return [
            ProposedL1CandidateV1(
                candidate_ref=SUPPORT_HABIT,
                typed_candidate=_typed_l1(
                    value,
                    predicate_surface="drink",
                    predicate_sense="consume_beverage",
                    canonical_operator="drink",
                    entity_surface="coffee",
                ),
            )
        ]


def _question_turns() -> list[RawTurnV1]:
    turns = _turns()
    # The second turn asks a question; it carries no durable fact.
    asked = turns[1].model_dump(mode="json")
    asked["user_text"] = "Which beverage did I say I prefer?"
    asked["assistant_text"] = "You said coffee."
    return [turns[0], RawTurnV1.model_validate(asked)]


def test_turn_without_durable_fact_records_no_memory(tmp_path: Path) -> None:
    producer = _NoMemoryL1Producer()
    result = run_e2e_pipeline(
        turns=_question_turns(),
        l1_producer=producer,
        l2_producer=_L2Producer(),
        query_producer=_QueryProducer(),
        repository_path=tmp_path / "no-memory-history.git",
        question="What beverage is preferred?",
    )
    assert producer.seen == ["turn-0000000000000001", "turn-0000000000000002"]
    bundles = {item.turn_id: item for item in result.turn_bundles}
    empty = bundles["turn-0000000000000002"]
    assert empty.extraction_state == "complete"
    assert empty.l1_unit_revision_ids == []
    assert empty.no_memory_reason is not None
    # The turn is still durably recorded, so the raw text stays recoverable.
    assert len(empty.source_records) == 2
    populated = bundles["turn-0000000000000001"]
    assert len(populated.l1_unit_revision_ids) == 1
    assert populated.no_memory_reason is None
    assert len(result.bundle.l1_units) == 1


def test_single_turn_may_yield_several_memories(tmp_path: Path) -> None:
    result = run_e2e_pipeline(
        turns=_turns(),
        l1_producer=_MultiFactL1Producer(),
        l2_producer=_L2Producer(),
        query_producer=_QueryProducer(),
        repository_path=tmp_path / "multi-fact-history.git",
        question="What beverage is preferred?",
    )
    bundles = {item.turn_id: item for item in result.turn_bundles}
    assert len(bundles["turn-0000000000000001"].l1_unit_revision_ids) == 2
    assert len(bundles["turn-0000000000000002"].l1_unit_revision_ids) == 1
    assert len(result.bundle.l1_units) == 3
    revision_ids = {item.revision_id for item in result.bundle.unit_revisions}
    for bundle in result.turn_bundles:
        assert set(bundle.l1_unit_revision_ids).issubset(revision_ids)


def test_every_turn_is_recorded_even_when_it_yields_no_memory(
    tmp_path: Path,
) -> None:
    """Zero candidates is an outcome, not a licence to skip the turn."""
    producer = _NoMemoryL1Producer()
    result = run_e2e_pipeline(
        turns=_question_turns(),
        l1_producer=producer,
        l2_producer=_L2Producer(),
        query_producer=_QueryProducer(),
        repository_path=tmp_path / "recorded-history.git",
        question="What beverage is preferred?",
    )
    assert len(result.turn_bundles) == len(_question_turns())
    for bundle in result.turn_bundles:
        assert bundle.extraction_state == "complete"
        assert bundle.extractor_id is not None
        # Either L1 units or an explicit no-memory reason, never neither.
        assert bool(bundle.l1_unit_revision_ids) != (
            bundle.no_memory_reason is not None
        )
    # Raw turns stay addressable regardless of extraction outcome.
    recorded = {
        ref.source_revision_id
        for bundle in result.turn_bundles
        for ref in bundle.source_records
    }
    assert recorded == {
        item.source_revision_id for item in result.bundle.source_record_revisions
    }
