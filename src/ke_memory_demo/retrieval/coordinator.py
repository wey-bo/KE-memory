from __future__ import annotations

from collections.abc import Sequence
import hashlib
from typing import Annotated, Protocol, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ke_memory_demo.domain import Evidence

from .fusion import EvidenceCandidate
from .matcher import KEMatchDecision
from .query import QueryKE, RetrievalInvariantError
from .symbolic import SymbolicCandidate


MAX_EVIDENCE_TOKENS = 8192
NonEmptyString = Annotated[str, Field(min_length=1)]
Sha256Hex = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class RetrievalTrace(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    question_sha256: Sha256Hex
    query_ke: QueryKE
    symbolic_candidate_ids: tuple[NonEmptyString, ...]
    matches: tuple[KEMatchDecision, ...]
    embedding_candidate_count: Annotated[int, Field(ge=0)]
    evidence_ids: tuple[NonEmptyString, ...]

    @model_validator(mode="after")
    def _duplicate_free_ids(self) -> RetrievalTrace:
        if len(self.symbolic_candidate_ids) != len(set(self.symbolic_candidate_ids)):
            raise ValueError("retrieval trace symbolic candidate IDs must be duplicate-free")
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("retrieval trace evidence IDs must be duplicate-free")
        return self


class TracedRetrieval(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    evidence: tuple[Evidence, ...]
    trace: RetrievalTrace

    @model_validator(mode="after")
    def _trace_matches_evidence(self) -> TracedRetrieval:
        evidence_ids = tuple(item.evidence_id for item in self.evidence)
        if self.trace.evidence_ids != evidence_ids:
            raise ValueError("retrieval trace evidence IDs do not match returned evidence")
        return self


class RetrievalTraceRecorder(Protocol):
    def record(self, trace: RetrievalTrace) -> None: ...


class InMemoryRetrievalTraceRecorder:
    def __init__(self) -> None:
        self._records: tuple[RetrievalTrace, ...] = ()

    @property
    def records(self) -> tuple[RetrievalTrace, ...]:
        return self._records

    def record(self, trace: RetrievalTrace) -> None:
        validated = RetrievalTrace.model_validate(trace)
        self._records = (*self._records, validated)


class _SymbolicPath(Protocol):
    async def extract_query(self, question: str) -> QueryKE: ...

    async def retrieve(self, *, query_ke: QueryKE) -> Sequence[SymbolicCandidate]: ...


class _EmbeddingPath(Protocol):
    async def retrieve(self, *, question: str) -> Sequence[EvidenceCandidate]: ...


class _Matcher(Protocol):
    async def match(
        self,
        *,
        query_ke: QueryKE,
        symbolic_candidates: Sequence[SymbolicCandidate],
    ) -> Sequence[KEMatchDecision]: ...


class _Fusion(Protocol):
    def fuse(
        self,
        *,
        symbolic_candidates: Sequence[SymbolicCandidate],
        matches: Sequence[KEMatchDecision],
        embedding_candidates: Sequence[EvidenceCandidate],
        budget: int,
    ) -> Sequence[Evidence]: ...


class RetrievalCoordinator:
    def __init__(
        self,
        symbolic: object,
        embedding: object,
        matcher: object,
        fusion: object,
        *,
        trace_recorder: RetrievalTraceRecorder | None = None,
    ) -> None:
        self._symbolic = cast(_SymbolicPath, symbolic)
        self._embedding = cast(_EmbeddingPath, embedding)
        self._matcher = cast(_Matcher, matcher)
        self._fusion = cast(_Fusion, fusion)
        self._trace_recorder = trace_recorder or InMemoryRetrievalTraceRecorder()

    async def retrieve(
        self,
        question: str,
        evidence_budget_tokens: int = MAX_EVIDENCE_TOKENS,
    ) -> Sequence[Evidence]:
        return (await self.retrieve_with_trace(question, evidence_budget_tokens)).evidence

    async def retrieve_with_trace(
        self,
        question: str,
        evidence_budget_tokens: int = MAX_EVIDENCE_TOKENS,
    ) -> TracedRetrieval:
        _validate_request(question, evidence_budget_tokens)
        query_ke = await self._symbolic.extract_query(question)
        symbolic = tuple(await self._symbolic.retrieve(query_ke=query_ke))
        matches = tuple(
            await self._matcher.match(
                query_ke=query_ke,
                symbolic_candidates=symbolic,
            )
        )
        embedding = tuple(await self._embedding.retrieve(question=question))
        evidence = tuple(
            self._fusion.fuse(
                symbolic_candidates=symbolic,
                matches=matches,
                embedding_candidates=embedding,
                budget=evidence_budget_tokens,
            )
        )
        trace = RetrievalTrace(
            question_sha256=hashlib.sha256(question.encode("utf-8")).hexdigest(),
            query_ke=query_ke,
            symbolic_candidate_ids=tuple(item.candidate_id for item in symbolic),
            matches=matches,
            embedding_candidate_count=len(embedding),
            evidence_ids=tuple(item.evidence_id for item in evidence),
        )
        traced = TracedRetrieval(evidence=evidence, trace=trace)
        self._trace_recorder.record(traced.trace)
        return traced


def _validate_request(question: str, evidence_budget_tokens: int) -> None:
    if not question.strip():
        raise RetrievalInvariantError("question must not be empty")
    if (
        isinstance(evidence_budget_tokens, bool)
        or evidence_budget_tokens <= 0
        or evidence_budget_tokens > MAX_EVIDENCE_TOKENS
    ):
        raise RetrievalInvariantError(
            f"evidence budget must be between 1 and {MAX_EVIDENCE_TOKENS} tokens"
        )
