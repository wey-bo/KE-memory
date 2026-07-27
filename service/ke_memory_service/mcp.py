from __future__ import annotations

from datetime import datetime
from typing import Protocol

from ke_memory_demo.domain import Exchange
from ke_memory_demo.online.models import MemoryNamespace
from ke_memory_demo.online.repository import StoredMemory
from ke_memory_demo.online.retrieval import (
    MemorySearchResponse,
    SymbolicMemoryQuery,
    WarmupContext,
)
from ke_memory_demo.online.service import OnlineIngestResult


class _IngestService(Protocol):
    async def ingest_turn(
        self,
        *,
        namespace: MemoryNamespace,
        conversation_id: str,
        idempotency_key: str,
        exchange: Exchange,
        recorded_at: datetime,
    ) -> OnlineIngestResult: ...


class _Retriever(Protocol):
    async def search(
        self,
        namespace: MemoryNamespace,
        query: SymbolicMemoryQuery,
    ) -> MemorySearchResponse: ...

    def context(
        self,
        namespace: MemoryNamespace,
        *,
        limit_per_section: int = 10,
    ) -> WarmupContext: ...


class _Repository(Protocol):
    def get_memory(
        self,
        namespace: MemoryNamespace,
        memory_id: str,
        *,
        include_deleted: bool = False,
    ) -> StoredMemory | None: ...

    def tombstone_memory(
        self,
        *,
        namespace: MemoryNamespace,
        memory_id: str,
        recorded_at: datetime,
    ) -> StoredMemory: ...


class MCPMemoryFacade:
    """SDK-neutral MCP operation facade over the validated memory application services."""

    def __init__(
        self,
        *,
        service: _IngestService,
        retriever: _Retriever,
        repository: _Repository,
    ) -> None:
        self._service = service
        self._retriever = retriever
        self._repository = repository

    async def memory_add(
        self,
        *,
        namespace: MemoryNamespace,
        conversation_id: str,
        idempotency_key: str,
        exchange: Exchange,
        recorded_at: datetime,
    ) -> OnlineIngestResult:
        return await self._service.ingest_turn(
            namespace=namespace,
            conversation_id=conversation_id,
            idempotency_key=idempotency_key,
            exchange=exchange,
            recorded_at=recorded_at,
        )

    async def memory_search(
        self,
        *,
        namespace: MemoryNamespace,
        query: SymbolicMemoryQuery,
    ) -> MemorySearchResponse:
        return await self._retriever.search(namespace, query)

    def memory_answer_context(
        self,
        *,
        namespace: MemoryNamespace,
        limit_per_section: int = 10,
    ) -> WarmupContext:
        return self._retriever.context(namespace, limit_per_section=limit_per_section)

    def memory_get(
        self,
        *,
        namespace: MemoryNamespace,
        memory_id: str,
    ) -> StoredMemory | None:
        return self._repository.get_memory(namespace, memory_id)

    def memory_forget(
        self,
        *,
        namespace: MemoryNamespace,
        memory_id: str,
        recorded_at: datetime,
    ) -> StoredMemory:
        return self._repository.tombstone_memory(
            namespace=namespace,
            memory_id=memory_id,
            recorded_at=recorded_at,
        )
