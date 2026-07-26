from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
import hashlib
from pathlib import Path

import pytest
from pydantic import ValidationError

from ke_memory_demo.domain import (
    Exchange,
    IndividualRef,
    KnowledgeEquation,
    Message,
    MessageRole,
    MessageSpan,
    Modality,
    OperatorApplication,
    OperatorRef,
    Speaker,
    TemporalMetadata,
)
from ke_memory_demo.online.admission import AdmissionPolicy
from ke_memory_demo.online.keol_bridge import KEOLBundleCompiler
from ke_memory_demo.online.models import MemoryKind, MemoryNamespace
from ke_memory_demo.online.repository import (
    MemoryLinkWrite,
    MemoryWrite,
    SQLiteOnlineMemoryRepository,
    StoredMemory,
)
from ke_memory_demo.online.retrieval import (
    EmbeddingFallbackCandidate,
    OntologyMemoryRetriever,
    SymbolicMemoryQuery,
)


RECORDED_AT = datetime(2026, 7, 26, 13, 0, tzinfo=UTC)


class StubFallback:
    def __init__(self, memory_ids: tuple[str, ...]) -> None:
        self.memory_ids = memory_ids
        self.calls = 0

    async def search(
        self,
        query_text: str,
        candidates: Sequence[StoredMemory],
        limit: int,
    ) -> Sequence[EmbeddingFallbackCandidate]:
        self.calls += 1
        available = {item.memory_id for item in candidates}
        return tuple(
            EmbeddingFallbackCandidate(memory_id=memory_id, score=0.8)
            for memory_id in self.memory_ids[:limit]
            if memory_id in available
        )


@pytest.mark.asyncio
async def test_exact_symbolic_match_does_not_call_embedding_and_returns_evidence(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    namespace = _namespace()
    preference_id = _seed(
        repository,
        namespace,
        exchange_id="exchange-pref",
        text="I prefer concise answers.",
        modality=Modality.PREFERENCE,
        operator="prefers",
        value="concise answers",
    )
    fallback = StubFallback((preference_id,))
    retriever = OntologyMemoryRetriever(repository=repository, fallback=fallback)

    response = await retriever.search(
        namespace,
        SymbolicMemoryQuery(
            text="What response style does the user prefer?",
            operator_terms=("operator:prefers",),
            entity_terms=("individual:user",),
            memory_kinds=(MemoryKind.PREFERENCE,),
        ),
    )

    assert response.fallback_triggered is False
    assert response.slot_complete is True
    assert fallback.calls == 0
    assert [hit.memory_id for hit in response.hits] == [preference_id]
    assert response.hits[0].channels == ("symbolic",)
    assert response.hits[0].evidence[0]["quote"] == "I prefer concise answers."


@pytest.mark.asyncio
async def test_search_uses_current_revision_and_applies_time_filter(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    namespace = _namespace()
    old_id = _seed(
        repository,
        namespace,
        exchange_id="exchange-old",
        text="I prefer concise answers.",
        modality=Modality.PREFERENCE,
        operator="prefers",
        value="concise answers",
        temporal=TemporalMetadata(
            valid_from=datetime(2026, 7, 1, tzinfo=UTC),
            valid_to=datetime(2026, 7, 20, tzinfo=UTC),
        ),
    )
    replacement = _memory_write(
        namespace,
        message_id="message:correction",
        text="I prefer detailed answers.",
        modality=Modality.PREFERENCE,
        operator="prefers",
        value="detailed answers",
        temporal=TemporalMetadata(valid_from=datetime(2026, 7, 21, tzinfo=UTC)),
    )
    current = repository.correct_memory(
        namespace=namespace,
        memory_id=old_id,
        replacement=replacement,
        recorded_at=datetime(2026, 7, 21, 1, 0, tzinfo=UTC),
    )
    retriever = OntologyMemoryRetriever(repository=repository)

    response = await retriever.search(
        namespace,
        SymbolicMemoryQuery(
            text="Current answer preference",
            memory_kinds=(MemoryKind.PREFERENCE,),
            valid_at=datetime(2026, 7, 26, tzinfo=UTC),
        ),
    )
    before_current = await retriever.search(
        namespace,
        SymbolicMemoryQuery(
            text="Old answer preference",
            memory_kinds=(MemoryKind.PREFERENCE,),
            valid_at=datetime(2026, 7, 10, tzinfo=UTC),
        ),
    )

    assert [hit.memory_id for hit in response.hits] == [current.memory_id]
    assert old_id not in {hit.memory_id for hit in response.hits}
    assert before_current.hits == ()


@pytest.mark.asyncio
async def test_embedding_runs_only_for_declared_lexical_slot_and_keeps_structural_filters(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    namespace = _namespace()
    preference_id = _seed(
        repository,
        namespace,
        exchange_id="exchange-pref",
        text="I prefer concise answers.",
        modality=Modality.PREFERENCE,
        operator="prefers",
        value="concise answers",
    )
    _seed(
        repository,
        namespace,
        exchange_id="exchange-task",
        text="Deploy service alpha.",
        modality=Modality.PLAN,
        operator="deploys",
        value="service alpha",
    )
    fallback = StubFallback((preference_id,))
    retriever = OntologyMemoryRetriever(repository=repository, fallback=fallback)

    no_gap = await retriever.search(
        namespace,
        SymbolicMemoryQuery(text="unknown wording", operator_terms=("not-found",)),
    )
    with_gap = await retriever.search(
        namespace,
        SymbolicMemoryQuery(
            text="preferred brevity",
            operator_terms=("unresolved:preference-word",),
            memory_kinds=(MemoryKind.PREFERENCE,),
            unresolved_slots=("predicate",),
        ),
    )

    assert no_gap.hits == ()
    assert no_gap.fallback_triggered is False
    assert with_gap.fallback_triggered is True
    assert with_gap.slot_complete is True
    assert [hit.memory_id for hit in with_gap.hits] == [preference_id]
    assert with_gap.hits[0].channels == ("embedding_fallback",)
    assert fallback.calls == 1

    with pytest.raises(ValidationError):
        SymbolicMemoryQuery(text="bad gap", unresolved_slots=("time",))  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_warmup_context_groups_a_and_b_memories_with_conflict_evidence(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    namespace = _namespace()
    preference_id = _seed(
        repository,
        namespace,
        exchange_id="exchange-pref",
        text="I prefer concise answers.",
        modality=Modality.PREFERENCE,
        operator="prefers",
        value="concise answers",
    )
    task_id = _seed(
        repository,
        namespace,
        exchange_id="exchange-task",
        text="Deploy service alpha.",
        modality=Modality.PLAN,
        operator="deploys",
        value="service alpha",
    )
    state_id = _seed(
        repository,
        namespace,
        exchange_id="exchange-state",
        text="Deployment status is succeeded.",
        modality=Modality.FACT,
        operator="deployment_status",
        value="succeeded",
        speaker=Speaker.TOOL,
    )
    conflict_ids = _seed_conflict_pair(repository, namespace)
    retriever = OntologyMemoryRetriever(repository=repository)

    context = retriever.context(namespace, limit_per_section=10)

    assert [item.memory_id for item in context.preferences] == [preference_id]
    assert [item.memory_id for item in context.active_tasks] == [task_id]
    assert [item.memory_id for item in context.recent_states] == [state_id]
    assert {item.memory_id for item in context.conflicts} == set(conflict_ids)
    assert all(item.evidence for item in context.all_items())


def _repository(tmp_path: Path) -> SQLiteOnlineMemoryRepository:
    return SQLiteOnlineMemoryRepository(tmp_path / "online-memory.sqlite3")


def _namespace() -> MemoryNamespace:
    return MemoryNamespace(
        tenant_id="tenant-a",
        user_id="user-1",
        agent_id="assistant",
    )


def _seed(
    repository: SQLiteOnlineMemoryRepository,
    namespace: MemoryNamespace,
    *,
    exchange_id: str,
    text: str,
    modality: Modality,
    operator: str,
    value: str,
    temporal: TemporalMetadata | None = None,
    speaker: Speaker = Speaker.USER,
) -> str:
    message_id = f"message:{exchange_id}"
    memory = _memory_write(
        namespace,
        message_id=message_id,
        text=text,
        modality=modality,
        operator=operator,
        value=value,
        temporal=temporal,
        speaker=speaker,
    )
    exchange = Exchange(
        id=exchange_id,
        session_id="session-1",
        user=Message(
            id=message_id,
            role=MessageRole.USER,
            content=text,
            source_order=0,
        ),
        assistant=Message(
            id=f"message:{exchange_id}:assistant",
            role=MessageRole.ASSISTANT,
            content="Acknowledged.",
            source_order=1,
        ),
        global_ordinal=abs(hash(exchange_id)) % 1_000_000,
    )
    receipt = repository.write_turn(
        namespace=namespace,
        conversation_id="conversation-1",
        idempotency_key=f"key:{exchange_id}",
        exchange=exchange,
        memories=(memory,),
        recorded_at=RECORDED_AT,
    )
    return receipt.memory_ids[0]


def _seed_conflict_pair(
    repository: SQLiteOnlineMemoryRepository,
    namespace: MemoryNamespace,
) -> tuple[str, str]:
    first = _memory_write(
        namespace,
        message_id="message:conflict:user",
        text="The launch date is Monday.",
        modality=Modality.FACT,
        operator="launch_date",
        value="Monday",
    )
    second = _memory_write(
        namespace,
        message_id="message:conflict:assistant",
        text="The launch date is Tuesday.",
        modality=Modality.FACT,
        operator="launch_date",
        value="Tuesday",
    )
    first_id = repository.memory_id_for(namespace, first.equation.id)
    second_id = repository.memory_id_for(namespace, second.equation.id)
    exchange = Exchange(
        id="exchange-conflict",
        session_id="session-1",
        user=Message(
            id="message:conflict:user",
            role=MessageRole.USER,
            content="The launch date is Monday.",
            source_order=0,
        ),
        assistant=Message(
            id="message:conflict:assistant",
            role=MessageRole.ASSISTANT,
            content="The launch date is Tuesday.",
            source_order=1,
        ),
        global_ordinal=999_999,
    )
    repository.write_turn(
        namespace=namespace,
        conversation_id="conversation-1",
        idempotency_key="key:conflict",
        exchange=exchange,
        memories=(first, second),
        links=(
            MemoryLinkWrite(
                source_memory_id=first_id,
                target_memory_id=second_id,
                relation="conflicts_with",
            ),
            MemoryLinkWrite(
                source_memory_id=second_id,
                target_memory_id=first_id,
                relation="conflicts_with",
            ),
        ),
        recorded_at=RECORDED_AT,
    )
    return first_id, second_id


def _memory_write(
    namespace: MemoryNamespace,
    *,
    message_id: str,
    text: str,
    modality: Modality,
    operator: str,
    value: str,
    temporal: TemporalMetadata | None = None,
    speaker: Speaker = Speaker.USER,
) -> MemoryWrite:
    span = MessageSpan(
        message_id=message_id,
        start_char=0,
        end_char=len(text),
        text_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
    )
    equation = KnowledgeEquation.create(
        level="turn",
        lhs=OperatorApplication(
            operator=OperatorRef(term_id=f"operator:{operator}", label=operator),
            arguments=(IndividualRef(term_id="individual:user", label="user"),),
        ),
        rhs=IndividualRef(term_id=f"individual:{value}", label=value),
        gloss=f"{operator} {value}",
        modality=modality,
        polarity="positive",
        lifecycle="active",
        speaker=speaker,
        temporal=temporal or TemporalMetadata(),
        evidence_refs=(span,),
        confidence=0.95,
        produced_in_run_id="run:test",
        produced_in_stage="turn-ke-extracted",
    )
    assessment = AdmissionPolicy().assess(equation)
    bundle = KEOLBundleCompiler().compile(
        namespace=namespace,
        equation=equation,
        assessment=assessment,
        source_messages={message_id: text},
        recorded_at=RECORDED_AT,
    )
    return MemoryWrite(equation=equation, assessment=assessment, bundle=bundle)
