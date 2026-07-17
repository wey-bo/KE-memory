from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from typing import cast

import pytest

import ke_memory_demo.retrieval.fusion as fusion_module
import ke_memory_demo.retrieval.tokens as token_module
from ke_memory_demo.domain import (
    ConceptRef,
    KnowledgeEquation,
    Lifecycle,
    MessageSpan,
    Modality,
    Polarity,
    Speaker,
    TemporalMetadata,
)
from ke_memory_demo.retrieval import (
    EvidenceBudgetError,
    EvidenceCandidate,
    EvidenceFusion,
    FusionInvariantError,
    KEMatchDecision,
    MatchRelation,
    O200KTokenCounter,
    SourceFragment,
    SymbolicCandidate,
    serialize_evidence_payload,
)


class _WordTokenCounter:
    def count(self, text: str) -> int:
        return len(text.split())


class _CharacterTokenCounter:
    def __init__(self) -> None:
        self.inputs: list[str] = []

    def count(self, text: str) -> int:
        self.inputs.append(text)
        return len(text)


class _CollectionCostCounter:
    def count(self, text: str) -> int:
        if not text.startswith("["):
            return 1
        payload = cast(list[dict[str, object]], json.loads(text))
        costs = {"greedy trap": 3, "alternative": 4, "complement": 1}
        return sum(costs[str(item["text"])] for item in payload)


def _candidate(
    candidate_id: str,
    text: str,
    *,
    score: float,
    conflict_side: str,
) -> EvidenceCandidate:
    return EvidenceCandidate(
        candidate_id=candidate_id,
        text=text,
        score=score,
        channel="matched",
        metadata={"conflict_side": conflict_side},
    )


def test_fusion_keeps_both_conflict_sides_under_budget() -> None:
    candidates = (
        _candidate(
            "new-state",
            "new state is now active and confirmed today",
            score=0.99,
            conflict_side="second",
        ),
        _candidate(
            "near-duplicate-new-state",
            "another high scoring result about only the new state",
            score=0.98,
            conflict_side="second",
        ),
        _candidate(
            "old-state",
            "old state was previously active before the change",
            score=0.25,
            conflict_side="first",
        ),
    )

    evidence = EvidenceFusion(_WordTokenCounter(), budget=20).pack(candidates)

    conflict_sides = tuple(item.metadata["conflict_side"] for item in evidence)
    assert all(isinstance(item, str) for item in conflict_sides)
    assert set(conflict_sides) == {"first", "second"}
    assert _WordTokenCounter().count(serialize_evidence_payload(evidence)) <= 20


def test_fusion_rejects_required_evidence_when_serialized_metadata_exceeds_budget() -> None:
    counter = _CharacterTokenCounter()
    candidate = EvidenceCandidate(
        candidate_id="candidate-1",
        text="x",
        score=1.0,
        channel="symbolic",
        source_exchange_ids=("exchange-1",),
        source_message_ids=("message-1",),
        system_record_ids=("ke-1",),
        metadata={"conflict_side": "first", "provenance": "p" * 200},
    )

    with pytest.raises(EvidenceBudgetError, match="does not fit"):
        EvidenceFusion(counter, budget=100).pack((candidate,))

    assert any(value.startswith("[") and "provenance" in value for value in counter.inputs)


def test_fuse_uses_constructor_budget_when_call_budget_is_omitted() -> None:
    candidate = EvidenceCandidate(
        candidate_id="candidate-1",
        text="x",
        score=1.0,
        channel="embedding",
        metadata={"conflict_side": "first", "provenance": "p" * 200},
    )

    with pytest.raises(EvidenceBudgetError, match="does not fit"):
        EvidenceFusion(_CharacterTokenCounter(), budget=100).fuse(
            symbolic_candidates=(),
            matches=(),
            embedding_candidates=(candidate,),
        )


def test_fusion_backtracks_when_greedy_mandatory_choice_blocks_a_feasible_pack() -> None:
    candidates = (
        EvidenceCandidate(
            candidate_id="greedy-trap",
            text="greedy trap",
            score=0.9,
            channel="symbolic",
            metadata={"conflict_side": "first", "time_point": "old"},
        ),
        EvidenceCandidate(
            candidate_id="alternative",
            text="alternative",
            score=0.8,
            channel="symbolic",
            metadata={"conflict_side": "first", "time_point": "new"},
        ),
        EvidenceCandidate(
            candidate_id="complement",
            text="complement",
            score=0.7,
            channel="symbolic",
            metadata={"time_point": "old"},
        ),
    )

    evidence = EvidenceFusion(_CollectionCostCounter(), budget=5).pack(candidates)

    assert {item.text for item in evidence} == {"alternative", "complement"}
    assert _CollectionCostCounter().count(serialize_evidence_payload(evidence)) == 5


def test_fusion_reports_search_limit_exhaustion_as_an_invariant_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(fusion_module, "MAX_MANDATORY_SEARCH_STATES", 1)
    candidates = (
        _candidate("first", "first", score=0.9, conflict_side="first"),
        _candidate("second", "second", score=0.8, conflict_side="second"),
    )

    with pytest.raises(FusionInvariantError, match="search limit exhausted"):
        EvidenceFusion(_WordTokenCounter(), budget=20).pack(candidates)


def _span(message_id: str, text: str) -> MessageSpan:
    return MessageSpan(
        message_id=message_id,
        start_char=0,
        end_char=len(text),
        text_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
    )


def test_fusion_deduplicates_spans_retains_channels_and_adds_raw_closure() -> None:
    raw_text = "the original source text"
    span = _span("message-1", raw_text)
    fragment = SourceFragment(
        fragment_id="fragment-1",
        text=raw_text,
        span=span,
        source_exchange_id="exchange-1",
        source_session_id="session-1",
    )
    derived = EvidenceCandidate(
        candidate_id="aggregate-1",
        text="derived summary",
        score=0.9,
        channel="symbolic",
        source_exchange_ids=("exchange-1",),
        source_message_ids=("message-1",),
        source_session_ids=("session-1",),
        system_record_ids=("aggregate-1",),
        derived=True,
        raw_closure=(fragment,),
        metadata={"aggregate_depth": 1},
    )
    embedding_duplicate = EvidenceCandidate(
        candidate_id="embedding-1",
        text=raw_text,
        score=0.8,
        channel="embedding",
        source_exchange_ids=("exchange-1",),
        source_message_ids=("message-1",),
        source_session_ids=("session-1",),
        message_span=span,
    )

    evidence = EvidenceFusion(_WordTokenCounter(), budget=20).pack((derived, embedding_duplicate))

    assert [item.text for item in evidence].count(raw_text) == 1
    raw = next(item for item in evidence if item.text == raw_text)
    assert raw.metadata["channels"] == ["embedding", "symbolic"]
    assert raw.channel == "embedding|symbolic"
    assert any(item.metadata.get("closure_for") == "aggregate-1" for item in evidence)
    assert _WordTokenCounter().count(serialize_evidence_payload(evidence)) <= 20


def test_fusion_preserves_required_time_points_and_session_diversity_deterministically() -> None:
    candidates = (
        EvidenceCandidate(
            candidate_id="recent-duplicate",
            text="recent duplicate detail",
            score=0.99,
            channel="embedding",
            source_session_ids=("session-2",),
            metadata={"time_point": "recent"},
        ),
        EvidenceCandidate(
            candidate_id="older",
            text="older source detail",
            score=0.2,
            channel="symbolic",
            source_session_ids=("session-1",),
            metadata={"time_point": "older"},
        ),
        EvidenceCandidate(
            candidate_id="recent",
            text="recent source detail",
            score=0.3,
            channel="symbolic",
            source_session_ids=("session-2",),
            metadata={"time_point": "recent"},
        ),
    )
    fusion = EvidenceFusion(_WordTokenCounter(), budget=6)

    first = fusion.pack(candidates)
    second = fusion.pack(tuple(reversed(candidates)))

    assert first == second
    time_points = tuple(item.metadata["time_point"] for item in first)
    assert all(isinstance(item, str) for item in time_points)
    assert set(time_points) == {"older", "recent"}
    session_values = tuple(item.metadata["source_session_ids"] for item in first)
    assert all(isinstance(item, list) for item in session_values)
    sessions = {
        session
        for values in session_values
        if isinstance(values, list)
        for session in values
        if isinstance(session, str)
    }
    assert sessions == {"session-1", "session-2"}
    assert _WordTokenCounter().count(serialize_evidence_payload(first)) <= 6


class _FakeEncoding:
    name = "o200k_base"

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    def encode(self, text: str, *, disallowed_special: tuple[str, ...]) -> list[int]:
        self.calls.append((text, disallowed_special))
        return [10, 20]


def test_fusion_uses_o200k_base_and_rejects_a_budget_above_the_hard_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested: list[str] = []
    encoding = _FakeEncoding()

    def get_encoding(name: str) -> _FakeEncoding:
        requested.append(name)
        return encoding

    monkeypatch.setattr(token_module.tiktoken, "get_encoding", get_encoding)
    counter = O200KTokenCounter()

    assert requested == ["o200k_base"]
    assert counter.encoding_name == "o200k_base"
    assert counter.count("hello world") == 2
    assert encoding.calls == [("hello world", ())]
    with pytest.raises(FusionInvariantError, match="8192"):
        EvidenceFusion(counter, budget=8193)


def test_fuse_converts_only_matched_symbolic_candidates_and_keeps_embedding_channel() -> None:
    raw_text = "project status is active"
    span = _span("message-1", raw_text)
    equation = KnowledgeEquation.create(
        level="turn",
        lhs=ConceptRef(term_id="term-project", label="project"),
        rhs=ConceptRef(term_id="term-active", label="active"),
        gloss="project active",
        modality=Modality.FACT,
        polarity=Polarity.POSITIVE,
        lifecycle=Lifecycle.ACTIVE,
        speaker=Speaker.USER,
        temporal=TemporalMetadata(event_time=datetime(2025, 1, 2, tzinfo=UTC)),
        evidence_refs=(span,),
        produced_in_run_id="run-memory",
        produced_in_stage="turn-ke-extracted",
    )
    symbolic = SymbolicCandidate(
        candidate_id=equation.id,
        record_kind="knowledge_equation",
        knowledge_equation=equation,
        matched_fields=("term:term-project",),
        source_fragments=(
            SourceFragment(
                fragment_id="fragment-1",
                text=raw_text,
                span=span,
                source_exchange_id="exchange-1",
                source_session_id="session-1",
            ),
        ),
    )
    embedding = EvidenceCandidate(
        candidate_id="embedding-1",
        text="embedding context",
        score=0.7,
        channel="embedding",
    )

    evidence = EvidenceFusion(_WordTokenCounter(), budget=20).fuse(
        symbolic_candidates=(symbolic,),
        matches=(
            KEMatchDecision(
                candidate_id=equation.id,
                match_type=MatchRelation.TEMPORAL_PRECEDES,
                confidence=0.9,
                reason="same status",
            ),
        ),
        embedding_candidates=(embedding,),
        budget=20,
    )

    assert {item.channel for item in evidence} >= {"embedding", "symbolic"}
    summary = next(item for item in evidence if item.text == equation.gloss)
    assert summary.metadata["match_type"] == "temporal_precedes"
    assert summary.metadata["lifecycle"] == "active"
    assert summary.metadata["time_point"] == "2025-01-02T00:00:00Z"
    assert any(item.metadata.get("closure_for") == equation.id for item in evidence)


def test_fuse_labels_each_contradicting_symbolic_record_as_a_required_side() -> None:
    raw_text = "old project status"
    span = _span("message-old", raw_text)
    equation = KnowledgeEquation.create(
        level="turn",
        lhs=ConceptRef(term_id="term-project", label="project"),
        rhs=ConceptRef(term_id="term-old", label="old status"),
        gloss="old project status",
        modality=Modality.FACT,
        polarity=Polarity.POSITIVE,
        lifecycle=Lifecycle.CONTRADICTED,
        speaker=Speaker.USER,
        evidence_refs=(span,),
        produced_in_run_id="run-memory",
        produced_in_stage="lifecycle-maintained",
    )
    symbolic = SymbolicCandidate(
        candidate_id=equation.id,
        record_kind="knowledge_equation",
        knowledge_equation=equation,
        matched_fields=("term:term-project",),
        source_fragments=(
            SourceFragment(
                fragment_id="fragment-old",
                text=raw_text,
                span=span,
                source_exchange_id="exchange-old",
                source_session_id="session-1",
            ),
        ),
    )

    evidence = EvidenceFusion(_WordTokenCounter(), budget=20).fuse(
        symbolic_candidates=(symbolic,),
        matches=(
            KEMatchDecision(
                candidate_id=equation.id,
                match_type=MatchRelation.CONTRADICTS,
                confidence=0.8,
                reason="opposing status",
            ),
        ),
        embedding_candidates=(),
        budget=20,
    )

    summary = next(item for item in evidence if item.text == equation.gloss)
    assert summary.metadata["conflict_side"] == equation.id
