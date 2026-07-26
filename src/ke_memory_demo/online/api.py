from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
import os
from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from ke_memory_demo.domain import Exchange, KnowledgeEquation

from .admission import AdmissionPolicy
from .factory import OnlineRuntime, build_online_runtime
from .keol_bridge import KEOLBundleCompiler
from .models import AdmissionStatus, MemoryNamespace
from .repository import (
    IdempotencyConflict,
    MemoryNotFound,
    MemoryStateConflict,
    MemoryWrite,
)
from .retrieval import SymbolicMemoryQuery


class _ApiRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class TurnRequest(_ApiRecord):
    namespace: MemoryNamespace
    conversation_id: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)
    exchange: Exchange
    recorded_at: datetime


class SearchRequest(_ApiRecord):
    namespace: MemoryNamespace
    query: SymbolicMemoryQuery


class ContextRequest(_ApiRecord):
    namespace: MemoryNamespace
    limit_per_section: int = Field(default=10, ge=1, le=100)


class CorrectionRequest(_ApiRecord):
    namespace: MemoryNamespace
    memory_id: str = Field(min_length=1)
    replacement_equation: KnowledgeEquation
    source_messages: dict[str, str]
    recorded_at: datetime


def create_app(runtime: OnlineRuntime) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            await runtime.aclose()

    app = FastAPI(title="KE Ontology Memory", version="1.0.0", lifespan=lifespan)

    @app.exception_handler(MemoryNotFound)
    async def memory_not_found(_request: Request, error: MemoryNotFound) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(error.args[0])})

    @app.exception_handler(IdempotencyConflict)
    @app.exception_handler(MemoryStateConflict)
    async def state_conflict(_request: Request, error: Exception) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(error)})

    @app.exception_handler(ValueError)
    async def invalid_operation(_request: Request, error: ValueError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(error)})

    @app.get("/healthz")
    async def health() -> dict[str, object]:
        integrity = runtime.repository.integrity_check()
        return {
            "status": "ok" if integrity == ("ok",) else "degraded",
            "mode": runtime.mode,
            "extraction_ready": runtime.extraction_ready,
            "database_integrity": integrity[0] if integrity else "unknown",
        }

    @app.post("/v1/memory/turns")
    async def add_turn(request: TurnRequest) -> object:
        return await runtime.service.ingest_turn(
            namespace=request.namespace,
            conversation_id=request.conversation_id,
            idempotency_key=request.idempotency_key,
            exchange=request.exchange,
            recorded_at=request.recorded_at,
        )

    @app.post("/v1/memory/search")
    async def search(request: SearchRequest) -> object:
        return await runtime.retriever.search(request.namespace, request.query)

    @app.post("/v1/memory/context")
    async def context(request: ContextRequest) -> object:
        return runtime.retriever.context(
            request.namespace,
            limit_per_section=request.limit_per_section,
        )

    @app.post("/v1/memory/corrections")
    async def correct(request: CorrectionRequest) -> object:
        assessment = AdmissionPolicy().assess(request.replacement_equation)
        if assessment.status is not AdmissionStatus.ADMITTED:
            raise ValueError("replacement equation must pass durable-memory admission")
        bundle = KEOLBundleCompiler().compile(
            namespace=request.namespace,
            equation=request.replacement_equation,
            assessment=assessment,
            source_messages=request.source_messages,
            recorded_at=request.recorded_at,
        )
        return runtime.repository.correct_memory(
            namespace=request.namespace,
            memory_id=request.memory_id,
            replacement=MemoryWrite(
                equation=request.replacement_equation,
                assessment=assessment,
                bundle=bundle,
            ),
            recorded_at=request.recorded_at,
        )

    @app.get("/v1/memory/{memory_id}")
    async def get_memory(
        memory_id: str,
        tenant_id: str = Query(min_length=1),
        user_id: str = Query(min_length=1),
        agent_id: str = Query(min_length=1),
    ) -> object:
        memory = runtime.repository.get_memory(
            MemoryNamespace(
                tenant_id=tenant_id,
                user_id=user_id,
                agent_id=agent_id,
            ),
            memory_id,
        )
        if memory is None:
            raise MemoryNotFound(memory_id)
        return memory

    @app.delete("/v1/memory/{memory_id}")
    async def delete_memory(
        memory_id: str,
        recorded_at: datetime,
        tenant_id: str = Query(min_length=1),
        user_id: str = Query(min_length=1),
        agent_id: str = Query(min_length=1),
    ) -> object:
        return runtime.repository.tombstone_memory(
            namespace=MemoryNamespace(
                tenant_id=tenant_id,
                user_id=user_id,
                agent_id=agent_id,
            ),
            memory_id=memory_id,
            recorded_at=recorded_at,
        )

    return app


def main() -> None:
    import uvicorn

    root = Path(os.environ.get("KE_MEMORY_ROOT", Path.cwd()))
    runtime = build_online_runtime(root)
    uvicorn.run(create_app(runtime), host=runtime.host, port=runtime.port)
