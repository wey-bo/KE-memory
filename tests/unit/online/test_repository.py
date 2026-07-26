from __future__ import annotations

from datetime import UTC, datetime
import hashlib
from pathlib import Path
import sqlite3

import pytest

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
)
from ke_memory_demo.online.admission import AdmissionPolicy
from ke_memory_demo.online.keol_bridge import KEOLBundleCompiler
from ke_memory_demo.online.models import MemoryNamespace
from ke_memory_demo.online.repository import (
    IdempotencyConflict,
    MemoryWrite,
    SQLiteOnlineMemoryRepository,
)


RECORDED_AT = datetime(2026, 7, 26, 9, 0, tzinfo=UTC)


def test_repository_enables_wal_foreign_keys_and_integrity(tmp_path: Path) -> None:
    repository = _repository(tmp_path)

    assert repository.pragmas() == {"journal_mode": "wal", "foreign_keys": 1}
    assert repository.integrity_check() == ("ok",)
    assert repository.foreign_key_check() == ()


def test_turn_write_is_idempotent_and_rejects_changed_payload(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    namespace = _namespace()
    exchange = _exchange()
    memory = _memory_write(namespace, exchange.user.content)

    first = repository.write_turn(
        namespace=namespace,
        conversation_id="conversation-1",
        idempotency_key="turn-key-1",
        exchange=exchange,
        memories=(memory,),
        recorded_at=RECORDED_AT,
    )
    replay = repository.write_turn(
        namespace=namespace,
        conversation_id="conversation-1",
        idempotency_key="turn-key-1",
        exchange=exchange,
        memories=(memory,),
        recorded_at=RECORDED_AT,
    )

    assert replay.model_copy(update={"replayed": False}) == first
    assert replay.replayed is True
    assert repository.row_counts()["turns"] == 1
    assert repository.row_counts()["raw_records"] == 2
    assert repository.row_counts()["memory_heads"] == 1

    changed_exchange = exchange.model_copy(
        update={
            "assistant": Message(
                id="message:assistant-1",
                role=MessageRole.ASSISTANT,
                content="Changed response",
                source_order=1,
            )
        }
    )
    with pytest.raises(IdempotencyConflict, match="different payload"):
        repository.write_turn(
            namespace=namespace,
            conversation_id="conversation-1",
            idempotency_key="turn-key-1",
            exchange=changed_exchange,
            memories=(memory,),
            recorded_at=RECORDED_AT,
        )


def test_failed_memory_insert_rolls_back_raw_turn_and_transaction(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    with sqlite3.connect(repository.database_path) as connection:
        connection.execute(
            """
            CREATE TRIGGER fail_memory_insert
            BEFORE INSERT ON memory_revisions
            BEGIN
                SELECT RAISE(ABORT, 'forced memory failure');
            END
            """
        )

    exchange = _exchange()
    namespace = _namespace()
    with pytest.raises(sqlite3.IntegrityError, match="forced memory failure"):
        repository.write_turn(
            namespace=namespace,
            conversation_id="conversation-1",
            idempotency_key="turn-key-fail",
            exchange=exchange,
            memories=(_memory_write(namespace, exchange.user.content),),
            recorded_at=RECORDED_AT,
        )

    counts = repository.row_counts()
    assert counts["transactions"] == 0
    assert counts["turns"] == 0
    assert counts["raw_records"] == 0
    assert counts["memory_heads"] == 0
    assert counts["memory_revisions"] == 0


def test_namespace_isolation_applies_to_turns_memories_and_lookup(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    exchange = _exchange()
    first_namespace = _namespace()
    second_namespace = MemoryNamespace(
        tenant_id="tenant-a",
        user_id="user-2",
        agent_id="assistant",
    )

    first = repository.write_turn(
        namespace=first_namespace,
        conversation_id="conversation-1",
        idempotency_key="same-key",
        exchange=exchange,
        memories=(_memory_write(first_namespace, exchange.user.content),),
        recorded_at=RECORDED_AT,
    )
    second = repository.write_turn(
        namespace=second_namespace,
        conversation_id="conversation-1",
        idempotency_key="same-key",
        exchange=exchange,
        memories=(_memory_write(second_namespace, exchange.user.content),),
        recorded_at=RECORDED_AT,
    )

    assert first.memory_ids != second.memory_ids
    assert repository.get_memory(first_namespace, first.memory_ids[0]) is not None
    assert repository.get_memory(second_namespace, first.memory_ids[0]) is None
    assert [item.memory_id for item in repository.list_current(first_namespace)] == [
        first.memory_ids[0]
    ]
    assert [item.memory_id for item in repository.list_current(second_namespace)] == [
        second.memory_ids[0]
    ]


def test_correction_selects_new_current_revision_and_preserves_history(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    namespace = _namespace()
    exchange = _exchange()
    receipt = repository.write_turn(
        namespace=namespace,
        conversation_id="conversation-1",
        idempotency_key="turn-key-1",
        exchange=exchange,
        memories=(_memory_write(namespace, exchange.user.content),),
        recorded_at=RECORDED_AT,
    )
    old_memory_id = receipt.memory_ids[0]
    replacement = _memory_write(
        namespace,
        "I now prefer detailed answers.",
        message_id="message:correction-1",
        preference="detailed answers",
    )

    corrected = repository.correct_memory(
        namespace=namespace,
        memory_id=old_memory_id,
        replacement=replacement,
        recorded_at=datetime(2026, 7, 26, 10, 0, tzinfo=UTC),
    )

    assert corrected.current is True
    assert corrected.links[0].relation == "supersedes"
    assert corrected.links[0].target_memory_id == old_memory_id
    assert [item.memory_id for item in repository.list_current(namespace)] == [
        corrected.memory_id
    ]

    old = repository.get_memory(namespace, old_memory_id, include_deleted=True)
    assert old is not None
    assert old.current is False
    assert old.equation.lifecycle.value == "superseded"
    assert len(repository.list_revisions(namespace, old_memory_id)) == 2
    assert repository.foreign_key_check() == ()


def test_tombstone_hides_memory_but_preserves_audit_and_exact_evidence(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    namespace = _namespace()
    exchange = _exchange()
    receipt = repository.write_turn(
        namespace=namespace,
        conversation_id="conversation-1",
        idempotency_key="turn-key-1",
        exchange=exchange,
        memories=(_memory_write(namespace, exchange.user.content),),
        recorded_at=RECORDED_AT,
    )
    memory_id = receipt.memory_ids[0]

    evidence = repository.get_evidence(namespace, memory_id)
    assert len(evidence) == 1
    assert evidence[0]["quote"] == exchange.user.content

    repository.tombstone_memory(
        namespace=namespace,
        memory_id=memory_id,
        recorded_at=datetime(2026, 7, 26, 11, 0, tzinfo=UTC),
    )

    assert repository.get_memory(namespace, memory_id) is None
    deleted = repository.get_memory(namespace, memory_id, include_deleted=True)
    assert deleted is not None
    assert deleted.tombstoned is True
    assert deleted.equation.lifecycle.value == "retracted"
    assert repository.list_current(namespace) == ()
    assert repository.get_evidence(namespace, memory_id)[0]["quote"] == exchange.user.content


def _repository(tmp_path: Path) -> SQLiteOnlineMemoryRepository:
    return SQLiteOnlineMemoryRepository(tmp_path / "online-memory.sqlite3")


def _namespace() -> MemoryNamespace:
    return MemoryNamespace(
        tenant_id="tenant-a",
        user_id="user-1",
        agent_id="assistant",
    )


def _exchange() -> Exchange:
    return Exchange(
        id="exchange-1",
        session_id="session-1",
        user=Message(
            id="message:user-1",
            role=MessageRole.USER,
            content="I prefer concise answers.",
            source_order=0,
        ),
        assistant=Message(
            id="message:assistant-1",
            role=MessageRole.ASSISTANT,
            content="Understood.",
            source_order=1,
        ),
        global_ordinal=0,
    )


def _memory_write(
    namespace: MemoryNamespace,
    text: str,
    *,
    message_id: str = "message:user-1",
    preference: str = "concise answers",
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
            operator=OperatorRef(term_id="operator:prefers", label="prefers"),
            arguments=(IndividualRef(term_id="individual:user", label="user"),),
        ),
        rhs=IndividualRef(
            term_id=f"individual:{preference.replace(' ', '-')}",
            label=preference,
        ),
        gloss=f"The user prefers {preference}.",
        modality=Modality.PREFERENCE,
        polarity="positive",
        lifecycle="active",
        speaker=Speaker.USER,
        evidence_refs=(span,),
        confidence=0.92,
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
