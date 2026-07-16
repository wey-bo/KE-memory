from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Sequence
from datetime import datetime
import hashlib
from typing import Annotated, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ke_memory_demo.domain import (
    AggregateNode,
    AssertionRef,
    AtomicExpression,
    Expression,
    KnowledgeEquation,
    Lifecycle,
    MessageSpan,
    OntologyBindingStatus,
    OperatorApplication,
    OperatorRef,
    TemporalMetadata,
)

from .query import QueryKE, QueryKEExtractor, RetrievalInvariantError


NonEmptyString = Annotated[str, Field(min_length=1)]


class SymbolicInvariantError(RetrievalInvariantError):
    """Symbolic lookup returned an invalid or dangling candidate."""


class SourceFragment(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    fragment_id: NonEmptyString
    text: str
    span: MessageSpan
    source_exchange_id: NonEmptyString
    source_session_id: NonEmptyString

    @model_validator(mode="after")
    def _validate_span(self) -> SourceFragment:
        if len(self.text) != self.span.end_char - self.span.start_char:
            raise ValueError("source fragment text length does not match its span")
        expected = hashlib.sha256(self.text.encode("utf-8")).hexdigest()
        if expected != self.span.text_hash:
            raise ValueError("source fragment text hash does not match its span")
        return self


class SymbolicCandidate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_id: NonEmptyString
    record_kind: Literal["knowledge_equation", "aggregate"]
    knowledge_equation: KnowledgeEquation | None = None
    aggregate: AggregateNode | None = None
    matched_fields: tuple[NonEmptyString, ...] = Field(min_length=1)
    source_fragments: tuple[SourceFragment, ...] = ()

    @model_validator(mode="after")
    def _validate_record(self) -> SymbolicCandidate:
        if self.matched_fields != tuple(sorted(set(self.matched_fields))):
            raise ValueError("symbolic matched fields must be sorted and duplicate-free")
        if self.record_kind == "knowledge_equation":
            if self.knowledge_equation is None or self.aggregate is not None:
                raise ValueError("knowledge-equation candidate requires exactly its KE record")
            if self.knowledge_equation.id != self.candidate_id:
                raise ValueError("knowledge-equation candidate ID does not match its record")
        else:
            if self.aggregate is None or self.knowledge_equation is not None:
                raise ValueError("aggregate candidate requires exactly its aggregate record")
            if self.aggregate.id != self.candidate_id:
                raise ValueError("aggregate candidate ID does not match its record")
        expected_spans = (
            self.knowledge_equation.evidence_refs
            if self.knowledge_equation is not None
            else self.aggregate.evidence_closure if self.aggregate is not None else ()
        )
        actual_spans = tuple(item.span for item in self.source_fragments)
        if actual_spans != expected_spans:
            raise ValueError("symbolic source fragments do not match the record evidence closure")
        return self


class SymbolicIndex(Protocol):
    def lookup_term_id(self, term_id: str, /) -> tuple[str, ...]: ...

    def lookup_unresolved_label(self, normalized_surface: str) -> tuple[str, ...]: ...

    def lookup_operator_id(self, operator_id: str) -> tuple[str, ...]: ...

    def lookup_lifecycle(self, lifecycle: Lifecycle | str) -> tuple[str, ...]: ...

    def lookup_temporal(
        self, start: datetime | None, end: datetime | None
    ) -> tuple[str, ...]: ...

    def lookup_aggregate_membership(self, member_ref: str) -> tuple[str, ...]: ...


class SymbolicRecordSource(Protocol):
    def get_knowledge_equation(self, record_id: str) -> KnowledgeEquation | None: ...

    def get_aggregate(self, record_id: str) -> AggregateNode | None: ...

    def resolve_span(self, span: MessageSpan) -> SourceFragment: ...


class SymbolicRetriever:
    def __init__(
        self,
        index: SymbolicIndex,
        records: SymbolicRecordSource,
        *,
        query_extractor: QueryKEExtractor | None = None,
        limit: int = 64,
    ) -> None:
        if isinstance(limit, bool) or limit <= 0:
            raise SymbolicInvariantError("symbolic candidate limit must be positive")
        self._index = index
        self._records = records
        self._query_extractor = query_extractor
        self._limit = limit

    async def extract_query(self, question: str) -> QueryKE:
        if self._query_extractor is None:
            raise SymbolicInvariantError("symbolic path has no query KE extractor")
        return await self._query_extractor.extract(question)

    async def retrieve(self, *, query_ke: QueryKE) -> tuple[SymbolicCandidate, ...]:
        query = QueryKE.model_validate(query_ke.model_dump(mode="python"))
        matched: dict[str, set[str]] = defaultdict(set)
        expressions = (*_expressions(query.lhs), *_expressions(query.rhs))
        term_ids = sorted({item.term_id for item in expressions if not isinstance(item, AssertionRef)})
        for term_id in term_ids:
            _add_matches(matched, self._index.lookup_term_id(term_id), f"term:{term_id}")
        operator_ids = sorted(
            {item.term_id for item in expressions if isinstance(item, OperatorRef)}
        )
        for operator_id in operator_ids:
            _add_matches(
                matched,
                self._index.lookup_operator_id(operator_id),
                f"operator:{operator_id}",
            )
        unresolved = sorted(
            {
                item.normalized_surface
                for item in query.ontology_bindings
                if item.status is not OntologyBindingStatus.RESOLVED
            }
        )
        for normalized in unresolved:
            _add_matches(
                matched,
                self._index.lookup_unresolved_label(normalized),
                f"unresolved:{normalized}",
            )
        for lifecycle in sorted(query.lifecycle, key=lambda item: item.value):
            _add_matches(
                matched,
                self._index.lookup_lifecycle(lifecycle),
                f"lifecycle:{lifecycle.value}",
            )
        if _has_temporal_constraint(query.temporal):
            start, end = _temporal_interval(query.temporal)
            _add_matches(matched, self._index.lookup_temporal(start, end), "temporal")

        assertion_refs = {
            item.assertion_id for item in expressions if isinstance(item, AssertionRef)
        }
        frontier = deque(sorted(set(matched).union(assertion_refs)))
        visited_members: set[str] = set()
        while frontier:
            member_ref = frontier.popleft()
            if member_ref in visited_members:
                continue
            visited_members.add(member_ref)
            aggregate_ids = self._index.lookup_aggregate_membership(member_ref)
            for aggregate_id in sorted(aggregate_ids):
                matched[aggregate_id].add(f"aggregate_member:{member_ref}")
                if aggregate_id not in visited_members:
                    frontier.append(aggregate_id)

        candidates = tuple(
            self._candidate(candidate_id, tuple(sorted(fields)))
            for candidate_id, fields in matched.items()
        )
        ordered = sorted(
            candidates,
            key=lambda item: (-len(item.matched_fields), item.candidate_id),
        )
        return tuple(ordered[: self._limit])

    def _candidate(
        self,
        candidate_id: str,
        matched_fields: tuple[str, ...],
    ) -> SymbolicCandidate:
        equation = self._records.get_knowledge_equation(candidate_id)
        aggregate = self._records.get_aggregate(candidate_id)
        if equation is not None and aggregate is not None:
            raise SymbolicInvariantError(
                f"symbolic candidate ID is ambiguous across record kinds: {candidate_id}"
            )
        if equation is not None:
            return SymbolicCandidate(
                candidate_id=candidate_id,
                record_kind="knowledge_equation",
                knowledge_equation=equation,
                matched_fields=matched_fields,
                source_fragments=self._source_fragments(equation.evidence_refs),
            )
        if aggregate is not None:
            return SymbolicCandidate(
                candidate_id=candidate_id,
                record_kind="aggregate",
                aggregate=aggregate,
                matched_fields=matched_fields,
                source_fragments=self._source_fragments(aggregate.evidence_closure),
            )
        raise SymbolicInvariantError(f"symbolic index returned dangling record ID: {candidate_id}")

    def _source_fragments(
        self,
        spans: Sequence[MessageSpan],
    ) -> tuple[SourceFragment, ...]:
        fragments: list[SourceFragment] = []
        for span in spans:
            fragment = self._records.resolve_span(span)
            validated = SourceFragment.model_validate(fragment.model_dump(mode="python"))
            if validated.span != span:
                raise SymbolicInvariantError(
                    f"source resolver returned the wrong span for {span.message_id}"
                )
            fragments.append(validated)
        return tuple(fragments)


def _add_matches(
    destination: dict[str, set[str]],
    candidate_ids: Sequence[str],
    feature: str,
) -> None:
    for candidate_id in candidate_ids:
        destination[candidate_id].add(feature)


def _expressions(expression: Expression) -> tuple[AtomicExpression, ...]:
    if isinstance(expression, OperatorApplication):
        return (
            expression.operator,
            *(item for argument in expression.arguments for item in _expressions(argument)),
        )
    return (expression,)


def _has_temporal_constraint(temporal: TemporalMetadata) -> bool:
    return any(
        value is not None
        for value in (
            temporal.mentioned_at,
            temporal.event_time,
            temporal.valid_from,
            temporal.valid_to,
        )
    )


def _temporal_interval(
    temporal: TemporalMetadata,
) -> tuple[datetime | None, datetime | None]:
    if temporal.valid_from is not None or temporal.valid_to is not None:
        return temporal.valid_from, temporal.valid_to
    point = temporal.event_time or temporal.mentioned_at
    return point, point
