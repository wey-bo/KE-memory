from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import pytest

from ke_memory_demo.domain import Exchange
from ke_memory_demo.online.models import MemoryNamespace
from ke_memory_demo.online.repository import StoredMemory
from ke_memory_demo.online.retrieval import (
    MemorySearchResponse,
    SymbolicMemoryQuery,
    WarmupContext,
)
from ke_memory_demo.online.service import OnlineIngestResult
from ke_memory_service.mcp import MCPMemoryFacade


class _Service:
    def __init__(self) -> None:
        self.called = False

    async def ingest_turn(self, **_kwargs: object) -> OnlineIngestResult:
        self.called = True
        return OnlineIngestResult(transaction_id="transaction-1", replayed=False)


class _Retriever:
    async def search(
        self,
        _namespace: MemoryNamespace,
        _query: SymbolicMemoryQuery,
    ) -> MemorySearchResponse:
        return MemorySearchResponse(slot_complete=False, fallback_triggered=False)

    def context(
        self,
        _namespace: MemoryNamespace,
        *,
        limit_per_section: int = 10,
    ) -> WarmupContext:
        assert limit_per_section == 3
        return WarmupContext()


class _Repository:
    def get_memory(
        self,
        _namespace: MemoryNamespace,
        _memory_id: str,
        *,
        include_deleted: bool = False,
    ) -> StoredMemory | None:
        assert not include_deleted
        return None

    def tombstone_memory(self, **_kwargs: object) -> StoredMemory:
        return cast(StoredMemory, object())


@pytest.mark.asyncio
async def test_mcp_facade_delegates_without_bypassing_namespace() -> None:
    service = _Service()
    facade = MCPMemoryFacade(
        service=service,
        retriever=_Retriever(),
        repository=_Repository(),
    )
    namespace = MemoryNamespace(tenant_id="tenant-a", user_id="user-1", agent_id="agent-1")
    exchange = cast(Exchange, object())

    result = await facade.memory_add(
        namespace=namespace,
        conversation_id="conversation-1",
        idempotency_key="turn-1",
        exchange=exchange,
        recorded_at=datetime(2026, 7, 27, tzinfo=UTC),
    )
    search = await facade.memory_search(
        namespace=namespace,
        query=SymbolicMemoryQuery(text="preference"),
    )
    context = facade.memory_answer_context(namespace=namespace, limit_per_section=3)

    assert service.called
    assert result.transaction_id == "transaction-1"
    assert not search.hits
    assert not context.all_items()
    assert facade.memory_get(namespace=namespace, memory_id="missing") is None

