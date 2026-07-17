from __future__ import annotations

import hashlib
import math
from pathlib import Path

import pytest

from ke_memory_demo.core.json import canonical_json
from ke_memory_demo.domain import (
    Evidence,
    Exchange,
    MemorySystem,
    Message,
    MessageRole,
    RunScope,
)
from ke_memory_demo.infra.telemetry import UsageRecord
from ke_memory_demo.storage import ArtifactStore
from ke_memory_demo.systems import (
    EMBEDDING_READY_STAGE,
    KE_READY_STAGE,
    KEMemorySystem,
    KEMemorySystemError,
    PreparedRunState,
    StageReadiness,
    StoredExchange,
)


def _exchange() -> Exchange:
    return Exchange(
        id="exchange-1",
        session_id="session-1",
        user=Message(
            id="message-user-1",
            role=MessageRole.USER,
            content="What is the status?",
            source_order=0,
        ),
        assistant=Message(
            id="message-assistant-1",
            role=MessageRole.ASSISTANT,
            content="It is active.",
            source_order=1,
        ),
        global_ordinal=0,
    )


def _evidence() -> Evidence:
    return Evidence(
        evidence_id="evidence-1",
        text="It is active.",
        source_exchange_ids=("exchange-1",),
        source_message_ids=("message-assistant-1",),
        system_record_ids=("ke-1",),
        score=0.9,
        rank=1,
        channel="symbolic",
        metadata={},
        token_count=4,
    )


class _Stages:
    def __init__(self, readiness: StageReadiness | None = None) -> None:
        self.readiness = readiness or StageReadiness(
            stage=KE_READY_STAGE,
            successful=True,
            pending_count=0,
        )
        self.prepare_calls: list[tuple[RunScope, Path]] = []
        self.ingest_calls: list[tuple[RunScope, Exchange]] = []
        self.ready_calls: list[tuple[RunScope, str]] = []

    async def prepare(self, scope: RunScope, runtime_cache: Path) -> PreparedRunState:
        self.prepare_calls.append((scope, runtime_cache))
        (runtime_cache / "stage-state.bin").write_bytes(b"runtime")
        return PreparedRunState(metadata={"prepared": True})

    async def ingest(self, scope: RunScope, exchange: Exchange) -> StoredExchange:
        self.ingest_calls.append((scope, exchange))
        return StoredExchange(record_ids=("exchange-1", "ke-1"), metadata={"count": 1})

    async def await_ready(self, scope: RunScope, required_stage: str) -> StageReadiness:
        self.ready_calls.append((scope, required_stage))
        return self.readiness


class _Retrieval:
    def __init__(self) -> None:
        self.calls: list[tuple[RunScope, str, int]] = []

    async def retrieve(
        self,
        scope: RunScope,
        question: str,
        evidence_budget_tokens: int,
    ) -> tuple[Evidence, ...]:
        self.calls.append((scope, question, evidence_budget_tokens))
        return (_evidence(),)


class _Usage:
    def __init__(self) -> None:
        self.values: dict[RunScope, tuple[UsageRecord, ...]] = {}
        self.calls: list[RunScope] = []

    def usage_records(self, scope: RunScope) -> tuple[UsageRecord, ...]:
        self.calls.append(scope)
        return self.values.get(scope, ())


class _CharacterTokenCounter:
    def count(self, text: str) -> int:
        return len(text)


def make_system(tmp_path: Path, stages: _Stages) -> KEMemorySystem:
    return KEMemorySystem(
        ArtifactStore(tmp_path / "state"),
        stages,
        _Retrieval(),
        _Usage(),
        token_counter=_CharacterTokenCounter(),
    )


def _scope() -> RunScope:
    return RunScope(
        run_id="run-1",
        conversation_id="conversation-1",
        system_id="ke-memory",
    )


@pytest.mark.asyncio
async def test_ke_memory_system_maps_staged_operations_to_the_common_protocol(
    tmp_path: Path,
) -> None:
    stages = _Stages()
    retrieval = _Retrieval()
    usage = _Usage()
    system = KEMemorySystem(
        ArtifactStore(tmp_path / "state"),
        stages,
        retrieval,
        usage,
        token_counter=_CharacterTokenCounter(),
    )

    identity = await system.prepare(_scope())
    usage.values[_scope()] = (
        UsageRecord(
            request_id="request-1",
            model="gpt-5.4",
            latency_seconds=0.2,
            input_tokens=10,
            output_tokens=3,
            total_tokens=13,
        ),
        UsageRecord(
            request_id="request-2",
            model="gpt-5.4",
            latency_seconds=0.3,
            input_tokens=20,
            output_tokens=4,
            total_tokens=24,
        ),
    )
    exchange = _exchange()
    ingest = await system.ingest(exchange)
    readiness = await system.await_ready()
    evidence = await system.retrieve("status?", 1000)
    stats = await system.stats()

    assert isinstance(system, MemorySystem)
    assert identity.system_id == "ke-memory"
    assert identity.namespace == "run-1:conversation-1:ke-memory"
    assert len(stages.prepare_calls) == 1
    assert stages.prepare_calls[0][1].is_dir()
    assert stages.ingest_calls == [(_scope(), exchange)]
    assert ingest.source_content_hash == hashlib.sha256(canonical_json(exchange)).hexdigest()
    assert ingest.system_record_ids == ("exchange-1", "ke-1")
    assert readiness.ready
    assert stages.ready_calls == [(_scope(), KE_READY_STAGE)]
    assert evidence == (_evidence(),)
    assert retrieval.calls == [(_scope(), "status?", 1000)]
    assert stats.call_count == 2
    assert stats.input_tokens == 30
    assert stats.output_tokens == 7
    assert math.isclose(stats.total_latency_seconds, 0.5)
    assert stats.metadata["ke_ready"] is True
    assert "embedding_ready" not in stats.metadata
    assert usage.calls == [_scope()]


@pytest.mark.asyncio
async def test_ke_memory_system_requires_successful_ke_ready(tmp_path: Path) -> None:
    stages = _Stages(StageReadiness(stage=KE_READY_STAGE, successful=True, pending_count=0))
    system = make_system(tmp_path, stages)
    await system.prepare(_scope())
    receipt = await system.await_ready()
    assert receipt.ready
    assert stages.ready_calls == [(_scope(), KE_READY_STAGE)]
    assert KE_READY_STAGE == "ke-ready"
    assert EMBEDDING_READY_STAGE == "embedding-ready"


@pytest.mark.asyncio
async def test_ke_memory_system_rejects_retrieval_over_exact_serialized_budget(
    tmp_path: Path,
) -> None:
    class _OversizedRetrieval:
        async def retrieve(
            self,
            scope: RunScope,
            question: str,
            evidence_budget_tokens: int,
        ) -> tuple[Evidence, ...]:
            return (
                _evidence().model_copy(
                    update={"metadata": {"provenance": "p" * 200}, "token_count": 1}
                ),
            )

    system = KEMemorySystem(
        ArtifactStore(tmp_path / "state"),
        _Stages(),
        _OversizedRetrieval(),
        _Usage(),
        token_counter=_CharacterTokenCounter(),
    )
    await system.prepare(_scope())
    await system.await_ready()

    with pytest.raises(KEMemorySystemError, match="requested evidence budget"):
        await system.retrieve("status?", 100)


@pytest.mark.asyncio
async def test_reset_deletes_only_current_runtime_cache_not_canonical_or_other_cache(
    tmp_path: Path,
) -> None:
    store = ArtifactStore(tmp_path / "state")
    with store.stage_writer("run-1", "ingested") as writer:
        writer.write("exchanges", (_exchange(),))
    canonical = store.canonical_path("run-1", "ingested", "exchanges")
    canonical_bytes = canonical.read_bytes()
    other_cache = store.cache_path("other-runtime").parent
    store.layout.ensure_directory(other_cache)
    (other_cache / "keep.bin").write_bytes(b"keep")
    stages = _Stages()
    system = KEMemorySystem(
        store,
        stages,
        _Retrieval(),
        _Usage(),
        token_counter=_CharacterTokenCounter(),
    )
    await system.prepare(_scope())
    runtime_cache = stages.prepare_calls[0][1]

    receipt = await system.reset()

    assert receipt.reset
    assert receipt.deleted_record_count == 1
    assert not runtime_cache.exists()
    assert canonical.read_bytes() == canonical_bytes
    assert (other_cache / "keep.bin").read_bytes() == b"keep"


@pytest.mark.asyncio
async def test_reset_and_reprepare_cannot_leak_retrieval_or_usage_from_old_scope(
    tmp_path: Path,
) -> None:
    old_scope = _scope()
    new_scope = RunScope(
        run_id="run-2",
        conversation_id="conversation-2",
        system_id="ke-memory",
    )
    retrieval = _Retrieval()
    usage = _Usage()
    system = KEMemorySystem(
        ArtifactStore(tmp_path / "state"),
        _Stages(),
        retrieval,
        usage,
        token_counter=_CharacterTokenCounter(),
    )
    await system.prepare(old_scope)
    await system.await_ready()
    await system.retrieve("old question", 1000)
    usage.values[old_scope] = (
        UsageRecord(
            request_id="old-request",
            model="gpt-5.4",
            latency_seconds=1.0,
            input_tokens=100,
            output_tokens=10,
            total_tokens=110,
        ),
    )
    await system.reset()

    await system.prepare(new_scope)
    await system.await_ready()
    await system.retrieve("new question", 1000)
    usage.values[new_scope] = (
        UsageRecord(
            request_id="new-request",
            model="gpt-5.4",
            latency_seconds=0.2,
            input_tokens=7,
            output_tokens=3,
            total_tokens=10,
        ),
    )
    stats = await system.stats()

    assert retrieval.calls == [
        (old_scope, "old question", 1000),
        (new_scope, "new question", 1000),
    ]
    assert stats.call_count == 1
    assert stats.input_tokens == 7
    assert stats.output_tokens == 3
    assert usage.calls == [new_scope]
