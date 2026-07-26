from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Annotated, Literal, Protocol, cast, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ke_memory_demo.core.json import JsonObject
from ke_memory_demo.domain import (
    ConceptRef,
    Expression,
    IndividualRef,
    Lifecycle,
    Modality,
    OperatorApplication,
    OperatorRef,
)

from .models import MemoryKind, MemoryNamespace
from .repository import SQLiteOnlineMemoryRepository, StoredMemory


NonEmptyString = Annotated[str, Field(min_length=1)]
PositiveLimit = Annotated[int, Field(ge=1, le=100)]
LexicalSlot = Literal["entity", "predicate"]


class _RetrievalRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SymbolicMemoryQuery(_RetrievalRecord):
    text: NonEmptyString
    operator_terms: tuple[NonEmptyString, ...] = ()
    entity_terms: tuple[NonEmptyString, ...] = ()
    memory_kinds: tuple[MemoryKind, ...] = ()
    modalities: tuple[Modality, ...] = ()
    valid_at: datetime | None = None
    include_conflicts: bool = False
    unresolved_slots: tuple[LexicalSlot, ...] = ()
    limit: PositiveLimit = 20

    @field_validator("text", mode="before")
    @classmethod
    def _normalize_text(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        if not normalized:
            raise ValueError("query text must not be blank")
        return normalized

    @field_validator("operator_terms", "entity_terms", mode="before")
    @classmethod
    def _normalize_terms(cls, value: object) -> object:
        if not isinstance(value, list | tuple):
            return value
        sequence = cast(Sequence[object], value)
        normalized: list[object] = [
            term.strip() if isinstance(term, str) else term for term in sequence
        ]
        return tuple(normalized)

    @model_validator(mode="after")
    def _validate_query(self) -> SymbolicMemoryQuery:
        _reject_duplicates(self.operator_terms, "operator terms")
        _reject_duplicates(self.entity_terms, "entity terms")
        _reject_duplicates(self.memory_kinds, "memory kinds")
        _reject_duplicates(self.modalities, "modalities")
        _reject_duplicates(self.unresolved_slots, "unresolved slots")
        if self.valid_at is not None and (
            self.valid_at.tzinfo is None or self.valid_at.utcoffset() is None
        ):
            raise ValueError("valid_at must be timezone-aware")
        return self


class EmbeddingFallbackCandidate(_RetrievalRecord):
    memory_id: NonEmptyString
    score: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


class MemorySearchHit(_RetrievalRecord):
    memory_id: NonEmptyString
    score: float
    memory_kind: MemoryKind
    modality: Modality
    lifecycle: Lifecycle
    gloss: NonEmptyString
    channels: tuple[NonEmptyString, ...]
    evidence: tuple[JsonObject, ...]
    conflict_memory_ids: tuple[NonEmptyString, ...] = ()


class MemorySearchResponse(_RetrievalRecord):
    hits: tuple[MemorySearchHit, ...] = ()
    slot_complete: bool
    fallback_triggered: bool
    unresolved_slots: tuple[LexicalSlot, ...] = ()


class ContextMemory(_RetrievalRecord):
    memory_id: NonEmptyString
    memory_kind: MemoryKind
    gloss: NonEmptyString
    lifecycle: Lifecycle
    evidence: tuple[JsonObject, ...]
    conflict_memory_ids: tuple[NonEmptyString, ...] = ()


class WarmupContext(_RetrievalRecord):
    active_tasks: tuple[ContextMemory, ...] = ()
    constraints: tuple[ContextMemory, ...] = ()
    preferences: tuple[ContextMemory, ...] = ()
    recent_states: tuple[ContextMemory, ...] = ()
    conflicts: tuple[ContextMemory, ...] = ()

    def all_items(self) -> tuple[ContextMemory, ...]:
        ordered = (
            *self.active_tasks,
            *self.constraints,
            *self.preferences,
            *self.recent_states,
            *self.conflicts,
        )
        seen: set[str] = set()
        unique: list[ContextMemory] = []
        for item in ordered:
            if item.memory_id in seen:
                continue
            seen.add(item.memory_id)
            unique.append(item)
        return tuple(unique)


@runtime_checkable
class EmbeddingFallback(Protocol):
    async def search(
        self,
        query_text: str,
        candidates: Sequence[StoredMemory],
        limit: int,
    ) -> Sequence[EmbeddingFallbackCandidate]: ...


class OntologyMemoryRetriever:
    def __init__(
        self,
        *,
        repository: SQLiteOnlineMemoryRepository,
        fallback: EmbeddingFallback | None = None,
    ) -> None:
        self._repository = repository
        self._fallback = fallback

    async def search(
        self,
        namespace: MemoryNamespace,
        query: SymbolicMemoryQuery,
    ) -> MemorySearchResponse:
        candidates = tuple(
            memory
            for memory in self._repository.list_current(namespace)
            if _matches_authoritative_filters(memory, query)
            and _matches_resolved_lexical_filters(memory, query)
        )
        symbolic = tuple(memory for memory in candidates if _matches_all_terms(memory, query))
        if symbolic:
            ranked = sorted(
                symbolic,
                key=lambda memory: (
                    -_symbolic_score(memory, query),
                    -memory.updated_at.timestamp(),
                    memory.memory_id,
                ),
            )[: query.limit]
            return MemorySearchResponse(
                hits=tuple(
                    self._hit(
                        namespace,
                        memory,
                        score=_symbolic_score(memory, query),
                        channel="symbolic",
                    )
                    for memory in ranked
                ),
                slot_complete=True,
                fallback_triggered=False,
                unresolved_slots=query.unresolved_slots,
            )

        if not query.unresolved_slots or self._fallback is None:
            return MemorySearchResponse(
                hits=(),
                slot_complete=False,
                fallback_triggered=False,
                unresolved_slots=query.unresolved_slots,
            )

        fallback_candidates = await self._fallback.search(
            query.text,
            candidates,
            query.limit,
        )
        by_id = {memory.memory_id: memory for memory in candidates}
        deduplicated: dict[str, EmbeddingFallbackCandidate] = {}
        for candidate in fallback_candidates:
            if candidate.memory_id not in by_id:
                continue
            previous = deduplicated.get(candidate.memory_id)
            if previous is None or candidate.score > previous.score:
                deduplicated[candidate.memory_id] = candidate
        ranked_fallback = sorted(
            deduplicated.values(),
            key=lambda candidate: (-candidate.score, candidate.memory_id),
        )[: query.limit]
        hits = tuple(
            self._hit(
                namespace,
                by_id[candidate.memory_id],
                score=candidate.score,
                channel="embedding_fallback",
            )
            for candidate in ranked_fallback
        )
        return MemorySearchResponse(
            hits=hits,
            slot_complete=bool(hits),
            fallback_triggered=True,
            unresolved_slots=query.unresolved_slots,
        )

    def context(
        self,
        namespace: MemoryNamespace,
        *,
        limit_per_section: int = 10,
    ) -> WarmupContext:
        if not 1 <= limit_per_section <= 100:
            raise ValueError("limit_per_section must be between 1 and 100")
        memories = self._repository.list_current(namespace)
        items = {
            memory.memory_id: self._context_item(namespace, memory)
            for memory in memories
        }
        items = {memory_id: item for memory_id, item in items.items() if item is not None}

        def section(kind: MemoryKind) -> tuple[ContextMemory, ...]:
            selected = [
                items[memory.memory_id]
                for memory in memories
                if memory.assessment.memory_kind is kind and memory.memory_id in items
            ]
            return tuple(selected[:limit_per_section])

        recent_states = sorted(
            (
                memory
                for memory in memories
                if memory.assessment.memory_kind is MemoryKind.STATE
                and memory.memory_id in items
            ),
            key=lambda memory: (-memory.updated_at.timestamp(), memory.memory_id),
        )
        conflict_items = [
            items[memory.memory_id]
            for memory in memories
            if memory.memory_id in items
            and (
                memory.equation.lifecycle is Lifecycle.CONTRADICTED
                or any(link.relation == "conflicts_with" for link in memory.links)
            )
        ]
        return WarmupContext(
            active_tasks=section(MemoryKind.TASK),
            constraints=section(MemoryKind.CONSTRAINT),
            preferences=section(MemoryKind.PREFERENCE),
            recent_states=tuple(
                items[memory.memory_id] for memory in recent_states[:limit_per_section]
            ),
            conflicts=tuple(conflict_items[:limit_per_section]),
        )

    def _hit(
        self,
        namespace: MemoryNamespace,
        memory: StoredMemory,
        *,
        score: float,
        channel: str,
    ) -> MemorySearchHit:
        return MemorySearchHit(
            memory_id=memory.memory_id,
            score=score,
            memory_kind=memory.assessment.memory_kind,
            modality=memory.equation.modality,
            lifecycle=memory.equation.lifecycle,
            gloss=memory.equation.gloss,
            channels=(channel,),
            evidence=self._repository.get_evidence(namespace, memory.memory_id),
            conflict_memory_ids=_conflict_ids(memory),
        )

    def _context_item(
        self,
        namespace: MemoryNamespace,
        memory: StoredMemory,
    ) -> ContextMemory | None:
        evidence = self._repository.get_evidence(namespace, memory.memory_id)
        if not evidence:
            return None
        return ContextMemory(
            memory_id=memory.memory_id,
            memory_kind=memory.assessment.memory_kind,
            gloss=memory.equation.gloss,
            lifecycle=memory.equation.lifecycle,
            evidence=evidence,
            conflict_memory_ids=_conflict_ids(memory),
        )


def _matches_authoritative_filters(
    memory: StoredMemory,
    query: SymbolicMemoryQuery,
) -> bool:
    if query.memory_kinds and memory.assessment.memory_kind not in query.memory_kinds:
        return False
    if query.modalities and memory.equation.modality not in query.modalities:
        return False
    has_conflict = memory.equation.lifecycle is Lifecycle.CONTRADICTED or any(
        link.relation == "conflicts_with" for link in memory.links
    )
    if has_conflict and not query.include_conflicts:
        return False
    if query.valid_at is not None:
        temporal = memory.equation.temporal
        if temporal.valid_from is not None and query.valid_at < temporal.valid_from:
            return False
        if temporal.valid_to is not None and query.valid_at > temporal.valid_to:
            return False
    return True


def _matches_resolved_lexical_filters(
    memory: StoredMemory,
    query: SymbolicMemoryQuery,
) -> bool:
    operators, entities = _expression_terms(memory)
    if "predicate" not in query.unresolved_slots and not _contains_all(
        operators, query.operator_terms
    ):
        return False
    if "entity" not in query.unresolved_slots and not _contains_all(
        entities, query.entity_terms
    ):
        return False
    return True


def _matches_all_terms(memory: StoredMemory, query: SymbolicMemoryQuery) -> bool:
    operators, entities = _expression_terms(memory)
    return _contains_all(operators, query.operator_terms) and _contains_all(
        entities, query.entity_terms
    )


def _symbolic_score(memory: StoredMemory, query: SymbolicMemoryQuery) -> float:
    operators, entities = _expression_terms(memory)
    operator_matches = sum(
        1 for term in query.operator_terms if _normalize(term) in operators
    )
    entity_matches = sum(1 for term in query.entity_terms if _normalize(term) in entities)
    return (
        1.0
        + 3.0 * operator_matches
        + 2.0 * entity_matches
        + memory.assessment.memory_utility
        + memory.assessment.epistemic_trust
    )


def _expression_terms(memory: StoredMemory) -> tuple[set[str], set[str]]:
    operators: set[str] = set()
    entities: set[str] = set()
    _collect_terms(memory.equation.lhs, operators, entities)
    _collect_terms(memory.equation.rhs, operators, entities)
    return operators, entities


def _collect_terms(
    expression: Expression,
    operators: set[str],
    entities: set[str],
) -> None:
    if isinstance(expression, OperatorApplication):
        operators.update(
            {_normalize(expression.operator.term_id), _normalize(expression.operator.label)}
        )
        for argument in expression.arguments:
            _collect_terms(argument, operators, entities)
        return
    if isinstance(expression, OperatorRef):
        operators.update({_normalize(expression.term_id), _normalize(expression.label)})
        return
    if isinstance(expression, ConceptRef | IndividualRef):
        entities.update({_normalize(expression.term_id), _normalize(expression.label)})
        return
    entities.add(_normalize(expression.assertion_id))


def _contains_all(available: set[str], requested: tuple[str, ...]) -> bool:
    return all(_normalize(item) in available for item in requested)


def _normalize(value: str) -> str:
    return " ".join(value.casefold().strip().split())


def _conflict_ids(memory: StoredMemory) -> tuple[str, ...]:
    return tuple(
        sorted(
            link.target_memory_id
            for link in memory.links
            if link.relation == "conflicts_with"
        )
    )


def _reject_duplicates(values: tuple[object, ...], label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"duplicate {label} are not allowed")
