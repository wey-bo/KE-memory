from __future__ import annotations

import asyncio
from collections.abc import Mapping
import hashlib
from types import SimpleNamespace
from typing import cast

import numpy as np
import pytest

from ke_memory_demo.domain import ConceptRef, Evidence, MessageSpan, OntologyRole
from ke_memory_demo.embedding import SearchHit
from ke_memory_demo.retrieval import (
    DisabledEmbeddingRetriever,
    EmbeddingRetriever,
    EvidenceCandidate,
    EvidenceFusion,
    InMemoryRetrievalTraceRecorder,
    KEMatchDecision,
    MatchRelation,
    QueryGroundingSpan,
    QueryKE,
    QuerySurfaceGrounding,
    RetrievalCoordinator,
    RetrievalInvariantError,
    SourceFragment,
)


class _SymbolicSpy:
    def __init__(self) -> None:
        self.received_fields: set[str] = set()
        self.query_ke = _query_ke("question")
        self.candidates = (SimpleNamespace(candidate_id="candidate-1"),)

    async def extract_query(self, question: str) -> QueryKE:
        assert question == "question"
        return self.query_ke

    async def retrieve(self, **inputs: object) -> tuple[object, ...]:
        self.received_fields = set(inputs)
        assert inputs == {"query_ke": self.query_ke}
        return self.candidates


class _EmbeddingSpy:
    def __init__(self) -> None:
        self.received_fields: set[str] = set()
        self.candidates = (object(),)

    async def retrieve(self, **inputs: object) -> tuple[object, ...]:
        self.received_fields = set(inputs)
        assert inputs == {"question": "question"}
        return self.candidates


class _MatcherSpy:
    def __init__(self) -> None:
        self.received_fields: set[str] = set()
        self.matches = (
            KEMatchDecision(
                candidate_id="candidate-1",
                match_type=MatchRelation.EXACT,
                confidence=1.0,
                reason="same status",
            ),
        )

    async def match(self, **inputs: object) -> tuple[object, ...]:
        self.received_fields = set(inputs)
        return self.matches


class _FusionSpy:
    def __init__(self) -> None:
        self.received: Mapping[str, object] = {}

    def fuse(self, **inputs: object) -> tuple[Evidence, ...]:
        self.received = inputs
        return (
            Evidence(
                evidence_id="evidence-1",
                text="evidence",
                score=1.0,
                rank=1,
                channel="fusion",
                token_count=1,
            ),
        )


def _query_ke(gloss: str) -> QueryKE:
    lhs = ConceptRef(term_id="term-project", label="project")
    rhs = ConceptRef(term_id="term-status", label="status")
    return QueryKE(
        lhs=lhs,
        rhs=rhs,
        gloss=gloss,
        surface_groundings=(
            QuerySurfaceGrounding(
                surface_form=lhs.label,
                role=OntologyRole.CONCEPT,
                grounding_span=QueryGroundingSpan(start_char=0, end_char=1),
            ),
            QuerySurfaceGrounding(
                surface_form=rhs.label,
                role=OntologyRole.CONCEPT,
                grounding_span=QueryGroundingSpan(start_char=1, end_char=2),
            ),
        ),
    )


@pytest.mark.asyncio
async def test_candidate_paths_meet_only_in_evidence_fusion() -> None:
    symbolic = _SymbolicSpy()
    embedding = _EmbeddingSpy()
    matcher = _MatcherSpy()
    fusion = _FusionSpy()

    result = await RetrievalCoordinator(symbolic, embedding, matcher, fusion).retrieve("question")

    assert [item.evidence_id for item in result] == ["evidence-1"]
    assert symbolic.received_fields == {"query_ke"}
    assert matcher.received_fields == {"query_ke", "symbolic_candidates"}
    assert embedding.received_fields == {"question"}
    assert set(fusion.received) == {
        "symbolic_candidates",
        "matches",
        "embedding_candidates",
        "budget",
    }
    assert fusion.received["symbolic_candidates"] is symbolic.candidates
    assert fusion.received["matches"] is matcher.matches
    assert fusion.received["embedding_candidates"] is embedding.candidates


@pytest.mark.asyncio
async def test_ke_only_coordinator_records_structured_trace() -> None:
    recorder = InMemoryRetrievalTraceRecorder()
    coordinator = RetrievalCoordinator(
        _SymbolicSpy(),
        DisabledEmbeddingRetriever(),
        _MatcherSpy(),
        _FusionSpy(),
        trace_recorder=recorder,
    )

    traced = await coordinator.retrieve_with_trace("question")

    [trace] = recorder.records
    assert trace is traced.trace
    assert trace.query_ke.gloss == "question"
    assert trace.symbolic_candidate_ids == ("candidate-1",)
    assert trace.matches[0].candidate_id == "candidate-1"
    assert trace.evidence_ids == tuple(item.evidence_id for item in traced.evidence)
    assert trace.embedding_candidate_count == 0


@pytest.mark.asyncio
async def test_concurrent_retrieval_keeps_each_trace_with_its_own_evidence() -> None:
    class ConcurrentSymbolic:
        async def extract_query(self, question: str) -> QueryKE:
            if question == "slow question":
                await asyncio.sleep(0.01)
            return _query_ke(question)

        async def retrieve(self, *, query_ke: QueryKE) -> tuple[SimpleNamespace, ...]:
            return (SimpleNamespace(candidate_id=f"candidate:{query_ke.gloss}"),)

    class ConcurrentMatcher:
        async def match(
            self,
            *,
            query_ke: QueryKE,
            symbolic_candidates: tuple[SimpleNamespace, ...],
        ) -> tuple[KEMatchDecision, ...]:
            del query_ke
            return (
                KEMatchDecision(
                    candidate_id=symbolic_candidates[0].candidate_id,
                    match_type=MatchRelation.EXACT,
                    confidence=1.0,
                    reason="same question",
                ),
            )

    class ConcurrentFusion:
        def fuse(self, **inputs: object) -> tuple[Evidence, ...]:
            symbolic = cast(tuple[object, ...], inputs["symbolic_candidates"])
            candidate = symbolic[0]
            assert isinstance(candidate, SimpleNamespace)
            return (
                Evidence(
                    evidence_id=f"evidence:{candidate.candidate_id}",
                    text="evidence",
                    score=1.0,
                    rank=1,
                    channel="fusion",
                    token_count=1,
                ),
            )

    recorder = InMemoryRetrievalTraceRecorder()
    coordinator = RetrievalCoordinator(
        ConcurrentSymbolic(),
        DisabledEmbeddingRetriever(),
        ConcurrentMatcher(),
        ConcurrentFusion(),
        trace_recorder=recorder,
    )

    slow, fast = await asyncio.gather(
        coordinator.retrieve_with_trace("slow question"),
        coordinator.retrieve_with_trace("fast question"),
    )

    for question, traced in (("slow question", slow), ("fast question", fast)):
        assert traced.trace.question_sha256 == hashlib.sha256(question.encode()).hexdigest()
        assert traced.trace.query_ke.gloss == question
        assert traced.trace.evidence_ids == tuple(item.evidence_id for item in traced.evidence)
    assert {trace.query_ke.gloss for trace in recorder.records} == {
        "slow question",
        "fast question",
    }


@pytest.mark.asyncio
async def test_disabled_embedding_returns_no_candidates_without_a_backend() -> None:
    from ke_memory_demo.retrieval import DisabledEmbeddingRetriever

    assert await DisabledEmbeddingRetriever().retrieve(question="status?") == ()


class _EmbeddingBackend:
    def __init__(self) -> None:
        self.questions: list[str] = []

    def embed_query(self, question: str) -> np.ndarray:
        self.questions.append(question)
        return np.asarray([1.0, 0.0], dtype=np.float32)


class _VectorIndex:
    def __init__(self, hits: list[SearchHit]) -> None:
        self.hits = hits
        self.searches: list[tuple[list[float], int]] = []

    def search(self, query: np.ndarray, *, limit: int) -> list[SearchHit]:
        self.searches.append((query.tolist(), limit))
        return self.hits


class _ClosureSource:
    def __init__(self, fragment: SourceFragment) -> None:
        self.fragment = fragment
        self.hits: list[str] = []

    def source_fragments_for_hit(self, hit: SearchHit) -> tuple[SourceFragment, ...]:
        self.hits.append(hit.document_id)
        return (self.fragment,)


class _UnitTokenCounter:
    def count(self, text: str) -> int:
        return 1


@pytest.mark.asyncio
async def test_embedding_retriever_uses_only_raw_question_and_closes_derived_hits() -> None:
    raw_text = "source status"
    span = MessageSpan(
        message_id="message-1",
        start_char=0,
        end_char=len(raw_text),
        text_hash="269a45266c8c3954f465f66159f665c93bfc5374c4b39ee057c442474009590f",
    )
    fragment = SourceFragment(
        fragment_id="fragment-1",
        text=raw_text,
        span=span,
        source_exchange_id="exchange-1",
        source_session_id="session-1",
    )
    hit = SearchHit(
        document_id="document-1",
        text="derived project status",
        score=0.8,
        source_exchange_ids=["exchange-1"],
        source_message_ids=["message-1"],
        source_ke_ids=["ke-1"],
        source_session_ids=["session-1"],
        metadata={"kind": "turn_ke", "source_id": "ke-1"},
    )
    backend = _EmbeddingBackend()
    index = _VectorIndex([hit])
    closure = _ClosureSource(fragment)

    [candidate] = await EmbeddingRetriever(
        backend,
        index,
        closure_source=closure,
        limit=7,
    ).retrieve(question="Raw Question")

    assert backend.questions == ["Raw Question"]
    assert index.searches == [([1.0, 0.0], 7)]
    assert closure.hits == ["document-1"]
    assert candidate.channel == "embedding"
    assert candidate.derived
    assert candidate.raw_closure == (fragment,)
    assert candidate.source_session_ids == ("session-1",)
    assert candidate.system_record_ids == ("ke-1",)


@pytest.mark.asyncio
async def test_raw_embedding_fragment_deduplicates_with_symbolic_closure_by_span() -> None:
    raw_text = "source status"
    span = MessageSpan(
        message_id="message-1",
        start_char=0,
        end_char=len(raw_text),
        text_hash="269a45266c8c3954f465f66159f665c93bfc5374c4b39ee057c442474009590f",
    )
    fragment = SourceFragment(
        fragment_id="fragment-1",
        text=raw_text,
        span=span,
        source_exchange_id="exchange-1",
        source_session_id="session-1",
    )
    hit = SearchHit(
        document_id="embedding-document-1",
        text="rendered exchange text",
        score=0.8,
        source_exchange_ids=["exchange-1"],
        source_message_ids=["message-1"],
        source_session_ids=["session-1"],
        metadata={"kind": "exchange", "source_id": "exchange-1"},
    )
    [embedding] = await EmbeddingRetriever(
        _EmbeddingBackend(),
        _VectorIndex([hit]),
        closure_source=_ClosureSource(fragment),
    ).retrieve(question="status?")
    symbolic = EvidenceCandidate(
        candidate_id="ke-1",
        text="derived status",
        score=0.9,
        channel="symbolic",
        source_exchange_ids=("exchange-1",),
        source_message_ids=("message-1",),
        source_session_ids=("session-1",),
        system_record_ids=("ke-1",),
        derived=True,
        raw_closure=(fragment,),
    )

    evidence = EvidenceFusion(_UnitTokenCounter(), budget=20).pack((symbolic, embedding))

    raw = [item for item in evidence if item.text == raw_text]
    assert len(raw) == 1
    assert raw[0].channel == "embedding|symbolic"
    assert raw[0].metadata["channels"] == ["embedding", "symbolic"]
    assert raw[0].metadata["embedding_document_id"] == "embedding-document-1"


@pytest.mark.parametrize(
    ("field", "value", "label"),
    [
        pytest.param("source_message_ids", [], "message", id="missing-message"),
        pytest.param("source_exchange_ids", ["exchange-other"], "exchange", id="exchange"),
        pytest.param("source_session_ids", ["session-other"], "session", id="session"),
    ],
)
@pytest.mark.asyncio
async def test_embedding_retriever_authenticates_fragment_provenance(
    field: str,
    value: list[str],
    label: str,
) -> None:
    raw_text = "source status"
    span = MessageSpan(
        message_id="message-1",
        start_char=0,
        end_char=len(raw_text),
        text_hash="269a45266c8c3954f465f66159f665c93bfc5374c4b39ee057c442474009590f",
    )
    fragment = SourceFragment(
        fragment_id="fragment-1",
        text=raw_text,
        span=span,
        source_exchange_id="exchange-1",
        source_session_id="session-1",
    )
    hit = SearchHit(
        document_id="embedding-document-1",
        text="rendered exchange text",
        score=0.8,
        source_exchange_ids=["exchange-1"],
        source_message_ids=["message-1"],
        source_session_ids=["session-1"],
        metadata={"kind": "exchange", "source_id": "exchange-1"},
    ).model_copy(update={field: value})

    with pytest.raises(RetrievalInvariantError, match=label):
        await EmbeddingRetriever(
            _EmbeddingBackend(),
            _VectorIndex([hit]),
            closure_source=_ClosureSource(fragment),
        ).retrieve(question="status?")
