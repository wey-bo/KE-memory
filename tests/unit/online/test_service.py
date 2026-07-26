from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
import hashlib
from pathlib import Path

import pytest

from ke_memory_demo.domain import (
    Exchange,
    IndividualRef,
    KnowledgeEquation,
    Lifecycle,
    Message,
    MessageRole,
    MessageSpan,
    Modality,
    OperatorApplication,
    OperatorRef,
    Speaker,
    ToolEvent,
    ToolEventKind,
)
from ke_memory_demo.extraction import LifecycleResult, TurnExtractionResult
from ke_memory_demo.online.models import AdmissionStatus, MemoryNamespace, SourceStatus
from ke_memory_demo.online.repository import SQLiteOnlineMemoryRepository
from ke_memory_demo.online.service import OntologyMemoryService


RECORDED_AT = datetime(2026, 7, 26, 12, 0, tzinfo=UTC)


class FakeExtractor:
    def __init__(self, results: dict[str, tuple[KnowledgeEquation, ...]]) -> None:
        self._results = results

    async def extract(self, exchange: Exchange) -> TurnExtractionResult:
        return TurnExtractionResult(
            exchange_id=exchange.id,
            knowledge_equations=self._results[exchange.id],
        )


class UpdatingLifecycle:
    async def apply(
        self,
        existing: Sequence[KnowledgeEquation],
        new: Sequence[KnowledgeEquation],
    ) -> LifecycleResult:
        if not existing:
            return LifecycleResult(appended_revisions=tuple(new), current_records=tuple(new))
        old = existing[0]
        current = new[0]
        old_transition = _recreate(old, lifecycle=Lifecycle.SUPERSEDED)
        new_transition = _recreate(
            current,
            lifecycle=current.lifecycle,
            supersedes=(old.id,),
        )
        return LifecycleResult(
            appended_revisions=(old_transition, new_transition),
            current_records=(old_transition, new_transition),
        )


@pytest.mark.asyncio
async def test_service_preserves_raw_turn_and_persists_admitted_preference(tmp_path: Path) -> None:
    namespace = _namespace()
    exchange = _exchange("exchange-1", "I prefer concise answers.")
    equation = _equation(
        message_id=exchange.user.id,
        text=exchange.user.content,
        speaker=Speaker.USER,
        modality=Modality.PREFERENCE,
        operator="prefers",
        value="concise answers",
    )
    repository = _repository(tmp_path)
    service = OntologyMemoryService(
        repository=repository,
        extractor=FakeExtractor({exchange.id: (equation,)}),
    )

    result = await service.ingest_turn(
        namespace=namespace,
        conversation_id="conversation-1",
        idempotency_key="turn-1",
        exchange=exchange,
        recorded_at=RECORDED_AT,
    )

    assert len(result.admitted_memory_ids) == 1
    assert result.candidate_equation_ids == ()
    assert result.rejected_equation_ids == ()
    stored = repository.get_memory(namespace, result.admitted_memory_ids[0])
    assert stored is not None
    assert stored.assessment.memory_kind.value == "preference"
    assert stored.bundle.evidence[0]["quote"] == exchange.user.content

    raw = repository.get_raw_turn(namespace, exchange.id)
    assert [item["content"] for item in raw] == [
        exchange.user.content,
        exchange.assistant.content,
    ]
    assert repository.get_extractions(namespace, exchange.id)[0].equation == equation


@pytest.mark.asyncio
async def test_service_supersedes_previous_task_state_atomically(tmp_path: Path) -> None:
    namespace = _namespace()
    first_exchange = _exchange("exchange-1", "Deploy service alpha.")
    second_exchange = _exchange("exchange-2", "Deploy service beta.", ordinal=1)
    first = _equation(
        message_id=first_exchange.user.id,
        text=first_exchange.user.content,
        speaker=Speaker.USER,
        modality=Modality.PLAN,
        operator="deploys",
        value="service alpha",
    )
    second = _equation(
        message_id=second_exchange.user.id,
        text=second_exchange.user.content,
        speaker=Speaker.USER,
        modality=Modality.PLAN,
        operator="deploys",
        value="service beta",
    )
    repository = _repository(tmp_path)
    service = OntologyMemoryService(
        repository=repository,
        extractor=FakeExtractor(
            {
                first_exchange.id: (first,),
                second_exchange.id: (second,),
            }
        ),
        lifecycle=UpdatingLifecycle(),
    )

    first_result = await service.ingest_turn(
        namespace=namespace,
        conversation_id="conversation-1",
        idempotency_key="turn-1",
        exchange=first_exchange,
        recorded_at=RECORDED_AT,
    )
    second_result = await service.ingest_turn(
        namespace=namespace,
        conversation_id="conversation-1",
        idempotency_key="turn-2",
        exchange=second_exchange,
        recorded_at=datetime(2026, 7, 26, 12, 5, tzinfo=UTC),
    )

    current = repository.list_current(namespace)
    assert [item.memory_id for item in current] == [second_result.admitted_memory_ids[0]]
    assert current[0].links[0].relation == "supersedes"
    assert current[0].links[0].target_memory_id == first_result.admitted_memory_ids[0]
    old = repository.get_memory(
        namespace,
        first_result.admitted_memory_ids[0],
        include_deleted=True,
    )
    assert old is not None
    assert old.equation.lifecycle is Lifecycle.SUPERSEDED
    assert repository.foreign_key_check() == ()


@pytest.mark.asyncio
async def test_tool_observation_is_durable_but_agent_fact_remains_audited_candidate(
    tmp_path: Path,
) -> None:
    namespace = _namespace()
    exchange = _exchange_with_tool()
    tool = exchange.events[0]
    tool_fact = _equation(
        message_id=tool.id,
        text=tool.content,
        speaker=Speaker.TOOL,
        modality=Modality.FACT,
        operator="deployment_status",
        value="succeeded",
    )
    agent_fact = _equation(
        message_id=exchange.assistant.id,
        text=exchange.assistant.content,
        speaker=Speaker.ASSISTANT,
        modality=Modality.FACT,
        operator="located_in",
        value="Shanghai",
    )
    repository = _repository(tmp_path)
    service = OntologyMemoryService(
        repository=repository,
        extractor=FakeExtractor({exchange.id: (tool_fact, agent_fact)}),
    )

    result = await service.ingest_turn(
        namespace=namespace,
        conversation_id="conversation-1",
        idempotency_key="turn-tool",
        exchange=exchange,
        recorded_at=RECORDED_AT,
    )

    assert len(result.admitted_memory_ids) == 1
    assert result.candidate_equation_ids == (agent_fact.id,)
    stored = repository.get_memory(namespace, result.admitted_memory_ids[0])
    assert stored is not None
    assert stored.assessment.source_status is SourceStatus.TOOL_OBSERVED
    assert stored.assessment.epistemic_trust == 0.95

    assessments = repository.get_extractions(namespace, exchange.id)
    assert [item.assessment.status for item in assessments] == [
        AdmissionStatus.ADMITTED,
        AdmissionStatus.CANDIDATE,
    ]
    assert assessments[1].assessment.source_status is SourceStatus.AGENT_GENERATED
    assert repository.get_raw_turn(namespace, exchange.id)[1]["content"] == tool.content


@pytest.mark.asyncio
async def test_compilation_failure_leaves_no_partial_raw_turn(tmp_path: Path) -> None:
    namespace = _namespace()
    exchange = _exchange("exchange-1", "Remember this.")
    invalid = _equation(
        message_id="message:missing",
        text="missing evidence",
        speaker=Speaker.USER,
        modality=Modality.FACT,
        operator="remembers",
        value="this",
    )
    repository = _repository(tmp_path)
    service = OntologyMemoryService(
        repository=repository,
        extractor=FakeExtractor({exchange.id: (invalid,)}),
    )

    with pytest.raises(ValueError, match="missing source message"):
        await service.ingest_turn(
            namespace=namespace,
            conversation_id="conversation-1",
            idempotency_key="turn-fail",
            exchange=exchange,
            recorded_at=RECORDED_AT,
        )

    counts = repository.row_counts()
    assert counts["transactions"] == 0
    assert counts["turns"] == 0
    assert counts["raw_records"] == 0
    assert counts["extracted_equations"] == 0


def _repository(tmp_path: Path) -> SQLiteOnlineMemoryRepository:
    return SQLiteOnlineMemoryRepository(tmp_path / "online-memory.sqlite3")


def _namespace() -> MemoryNamespace:
    return MemoryNamespace(
        tenant_id="tenant-a",
        user_id="user-1",
        agent_id="assistant",
    )


def _exchange(exchange_id: str, user_text: str, *, ordinal: int = 0) -> Exchange:
    return Exchange(
        id=exchange_id,
        session_id="session-1",
        user=Message(
            id=f"message:{exchange_id}:user",
            role=MessageRole.USER,
            content=user_text,
            source_order=0,
        ),
        assistant=Message(
            id=f"message:{exchange_id}:assistant",
            role=MessageRole.ASSISTANT,
            content="Acknowledged.",
            source_order=1,
        ),
        global_ordinal=ordinal,
    )


def _exchange_with_tool() -> Exchange:
    return Exchange(
        id="exchange-tool",
        session_id="session-1",
        user=Message(
            id="message:tool:user",
            role=MessageRole.USER,
            content="Deploy the service.",
            source_order=0,
        ),
        events=(
            ToolEvent(
                id="tool-result:1",
                kind=ToolEventKind.TOOL_RESULT,
                content="Deployment status: succeeded.",
                source_order=1,
            ),
        ),
        assistant=Message(
            id="message:tool:assistant",
            role=MessageRole.ASSISTANT,
            content="The user is located in Shanghai.",
            source_order=2,
        ),
        global_ordinal=0,
    )


def _equation(
    *,
    message_id: str,
    text: str,
    speaker: Speaker,
    modality: Modality,
    operator: str,
    value: str,
) -> KnowledgeEquation:
    span = MessageSpan(
        message_id=message_id,
        start_char=0,
        end_char=len(text),
        text_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
    )
    return KnowledgeEquation.create(
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
        evidence_refs=(span,),
        confidence=0.95,
        produced_in_run_id="run:test",
        produced_in_stage="turn-ke-extracted",
    )


def _recreate(
    equation: KnowledgeEquation,
    *,
    lifecycle: Lifecycle,
    supersedes: tuple[str, ...] | None = None,
) -> KnowledgeEquation:
    return KnowledgeEquation.create(
        level=equation.level,
        lhs=equation.lhs,
        rhs=equation.rhs,
        gloss=equation.gloss,
        modality=equation.modality,
        polarity=equation.polarity,
        lifecycle=lifecycle,
        speaker=equation.speaker,
        temporal=equation.temporal,
        ontology_bindings=equation.ontology_bindings,
        evidence_refs=equation.evidence_refs,
        derived_from=equation.derived_from,
        contradicts=equation.contradicts,
        supersedes=supersedes if supersedes is not None else equation.supersedes,
        confidence=equation.confidence,
        produced_in_run_id="run:lifecycle",
        produced_in_stage="lifecycle-maintained",
    )
