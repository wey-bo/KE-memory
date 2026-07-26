from __future__ import annotations

from datetime import UTC, datetime
import hashlib
from pathlib import Path

from fastapi.testclient import TestClient

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
from ke_memory_demo.extraction import TurnExtractionResult
from ke_memory_demo.online.api import create_app
from ke_memory_demo.online.factory import OnlineRuntime
from ke_memory_demo.online.models import MemoryNamespace
from ke_memory_demo.online.repository import SQLiteOnlineMemoryRepository
from ke_memory_demo.online.retrieval import OntologyMemoryRetriever
from ke_memory_demo.online.service import OntologyMemoryService


RECORDED_AT = datetime(2026, 7, 26, 14, 0, tzinfo=UTC)


class PreferenceExtractor:
    async def extract(self, exchange: Exchange) -> TurnExtractionResult:
        equation = _equation(
            message_id=exchange.user.id,
            text=exchange.user.content,
            value="concise answers",
        )
        return TurnExtractionResult(
            exchange_id=exchange.id,
            knowledge_equations=(equation,),
        )


def test_http_api_supports_add_search_context_correction_get_delete_and_isolation(
    tmp_path: Path,
) -> None:
    repository = SQLiteOnlineMemoryRepository(tmp_path / "online-memory.sqlite3")
    runtime = OnlineRuntime(
        mode="test",
        repository=repository,
        service=OntologyMemoryService(
            repository=repository,
            extractor=PreferenceExtractor(),
        ),
        retriever=OntologyMemoryRetriever(repository=repository),
        extraction_ready=True,
    )
    namespace = _namespace()
    exchange = _exchange()

    with TestClient(create_app(runtime)) as client:
        health = client.get("/healthz")
        assert health.status_code == 200
        assert health.json() == {
            "status": "ok",
            "mode": "test",
            "extraction_ready": True,
            "database_integrity": "ok",
        }

        added = client.post(
            "/v1/memory/turns",
            json={
                "namespace": namespace.model_dump(mode="json"),
                "conversation_id": "conversation-1",
                "idempotency_key": "turn-1",
                "exchange": exchange.model_dump(mode="json"),
                "recorded_at": RECORDED_AT.isoformat(),
            },
        )
        assert added.status_code == 200
        memory_id = added.json()["admitted_memory_ids"][0]

        replay = client.post(
            "/v1/memory/turns",
            json={
                "namespace": namespace.model_dump(mode="json"),
                "conversation_id": "conversation-1",
                "idempotency_key": "turn-1",
                "exchange": exchange.model_dump(mode="json"),
                "recorded_at": RECORDED_AT.isoformat(),
            },
        )
        assert replay.status_code == 200
        assert replay.json()["replayed"] is True

        searched = client.post(
            "/v1/memory/search",
            json={
                "namespace": namespace.model_dump(mode="json"),
                "query": {
                    "text": "response preference",
                    "operator_terms": ["operator:prefers"],
                    "memory_kinds": ["preference"],
                },
            },
        )
        assert searched.status_code == 200
        assert searched.json()["hits"][0]["memory_id"] == memory_id

        context = client.post(
            "/v1/memory/context",
            json={
                "namespace": namespace.model_dump(mode="json"),
                "limit_per_section": 10,
            },
        )
        assert context.status_code == 200
        assert context.json()["preferences"][0]["memory_id"] == memory_id

        fetched = client.get(
            f"/v1/memory/{memory_id}",
            params=namespace.model_dump(mode="json"),
        )
        assert fetched.status_code == 200
        assert fetched.json()["memory_id"] == memory_id

        isolated = client.get(
            f"/v1/memory/{memory_id}",
            params={
                "tenant_id": "tenant-a",
                "user_id": "user-2",
                "agent_id": "assistant",
            },
        )
        assert isolated.status_code == 404

        correction_text = "I now prefer detailed answers."
        correction = _equation(
            message_id="message:correction",
            text=correction_text,
            value="detailed answers",
        )
        corrected = client.post(
            "/v1/memory/corrections",
            json={
                "namespace": namespace.model_dump(mode="json"),
                "memory_id": memory_id,
                "replacement_equation": correction.model_dump(mode="json"),
                "source_messages": {"message:correction": correction_text},
                "recorded_at": datetime(2026, 7, 26, 14, 5, tzinfo=UTC).isoformat(),
            },
        )
        assert corrected.status_code == 200
        replacement_id = corrected.json()["memory_id"]
        assert replacement_id != memory_id
        assert corrected.json()["links"][0]["relation"] == "supersedes"

        deleted = client.delete(
            f"/v1/memory/{replacement_id}",
            params={
                **namespace.model_dump(mode="json"),
                "recorded_at": datetime(2026, 7, 26, 14, 10, tzinfo=UTC).isoformat(),
            },
        )
        assert deleted.status_code == 200
        assert deleted.json()["tombstoned"] is True

        missing = client.get(
            f"/v1/memory/{replacement_id}",
            params=namespace.model_dump(mode="json"),
        )
        assert missing.status_code == 404

        invalid = client.post(
            "/v1/memory/turns",
            json={
                "namespace": namespace.model_dump(mode="json"),
                "conversation_id": "conversation-1",
                "exchange": exchange.model_dump(mode="json"),
                "recorded_at": RECORDED_AT.isoformat(),
            },
        )
        assert invalid.status_code == 422


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


def _equation(*, message_id: str, text: str, value: str) -> KnowledgeEquation:
    return KnowledgeEquation.create(
        level="turn",
        lhs=OperatorApplication(
            operator=OperatorRef(term_id="operator:prefers", label="prefers"),
            arguments=(IndividualRef(term_id="individual:user", label="user"),),
        ),
        rhs=IndividualRef(term_id=f"individual:{value}", label=value),
        gloss=f"The user prefers {value}.",
        modality=Modality.PREFERENCE,
        polarity="positive",
        lifecycle="active",
        speaker=Speaker.USER,
        evidence_refs=(
            MessageSpan(
                message_id=message_id,
                start_char=0,
                end_char=len(text),
                text_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            ),
        ),
        confidence=0.95,
        produced_in_run_id="run:test",
        produced_in_stage="turn-ke-extracted",
    )
