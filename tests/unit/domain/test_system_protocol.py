from __future__ import annotations

import inspect
import math
from collections.abc import Sequence

import pytest
from pydantic import ValidationError

from ke_memory_demo.core.json import JsonObject, JsonValue
from ke_memory_demo.domain.conversation import Exchange, Message, MessageRole
from ke_memory_demo.domain.memory import Evidence
from ke_memory_demo.domain.systems import (
    AdapterIdentity,
    IngestReceipt,
    MemorySystem,
    ReadinessReceipt,
    ResetReceipt,
    RunScope,
    UsageAndLatency,
)


def _exchange() -> Exchange:
    return Exchange(
        id="exchange-1",
        session_id="session-1",
        user=Message(id="message-u", role=MessageRole.USER, content="question", source_order=0),
        assistant=Message(
            id="message-a", role=MessageRole.ASSISTANT, content="answer", source_order=1
        ),
        global_ordinal=0,
    )


def _evidence() -> Evidence:
    return Evidence(
        evidence_id="evidence-1",
        text="source text",
        source_exchange_ids=("exchange-1",),
        source_message_ids=("message-u",),
        system_record_ids=("record-1",),
        score=0.75,
        rank=1,
        channel="symbolic",
        metadata={"kind": "assertion"},
        token_count=3,
    )


class _FakeMemorySystem:
    system_id = "fake"

    async def prepare(self, scope: RunScope) -> AdapterIdentity:
        return AdapterIdentity(
            system_id=self.system_id,
            namespace=f"{scope.run_id}:{scope.conversation_id}",
            implementation="fake-adapter",
            version="1.0",
        )

    async def ingest(self, exchange: Exchange) -> IngestReceipt:
        return IngestReceipt(
            system_id=self.system_id,
            namespace="run-1:conversation-1",
            source_exchange_id=exchange.id,
            system_record_ids=("record-1",),
            source_content_hash="a" * 64,
        )

    async def await_ready(self) -> ReadinessReceipt:
        return ReadinessReceipt(
            system_id=self.system_id,
            namespace="run-1:conversation-1",
            ready=True,
            pending_count=0,
        )

    async def retrieve(self, question: str, evidence_budget_tokens: int) -> Sequence[Evidence]:
        del question, evidence_budget_tokens
        return (_evidence(),)

    async def stats(self) -> UsageAndLatency:
        return UsageAndLatency(
            system_id=self.system_id,
            namespace="run-1:conversation-1",
            call_count=1,
            input_tokens=3,
            output_tokens=0,
            total_latency_seconds=0.01,
        )

    async def reset(self) -> ResetReceipt:
        return ResetReceipt(
            system_id=self.system_id,
            namespace="run-1:conversation-1",
            reset=True,
            deleted_record_count=1,
        )


def test_run_scope_and_adapter_identity_are_immutable_and_non_empty() -> None:
    scope = RunScope(run_id="run-1", conversation_id="conversation-1", system_id="fake")
    identity = AdapterIdentity(
        system_id="fake",
        namespace="run-1:conversation-1",
        implementation="fake-adapter",
        version="1.0",
        metadata={"mode": "test"},
    )

    assert scope.system_id == identity.system_id
    with pytest.raises(ValidationError):
        scope.run_id = "changed"
    with pytest.raises(ValidationError):
        RunScope(run_id="", conversation_id="conversation-1", system_id="fake")
    with pytest.raises(ValidationError, match="extra_forbidden"):
        AdapterIdentity.model_validate({**identity.model_dump(), "unexpected": True})


def test_receipt_models_copy_metadata_and_convert_record_ids_to_tuples() -> None:
    nested: list[JsonValue] = ["initial"]
    metadata: JsonObject = {"events": nested}

    receipt = IngestReceipt.model_validate(
        {
            "system_id": "fake",
            "namespace": "run-1:conversation-1",
            "source_exchange_id": "exchange-1",
            "system_record_ids": ["record-1", "record-2"],
            "source_content_hash": "a" * 64,
            "metadata": metadata,
        }
    )
    nested.append("mutated")

    assert receipt.system_record_ids == ("record-1", "record-2")
    assert receipt.metadata == {"events": ["initial"]}
    with pytest.raises(ValidationError, match="duplicate"):
        IngestReceipt.model_validate(
            {**receipt.model_dump(), "system_record_ids": ["record-1", "record-1"]}
        )
    with pytest.raises(ValidationError):
        IngestReceipt.model_validate({**receipt.model_dump(), "source_content_hash": "A" * 64})


def test_ingest_receipt_allows_an_empty_system_record_id_tuple() -> None:
    receipt = IngestReceipt(
        system_id="fake",
        namespace="run-1:conversation-1",
        source_exchange_id="exchange-1",
        system_record_ids=(),
        source_content_hash="a" * 64,
    )

    assert receipt.system_record_ids == ()


def test_readiness_receipt_validates_pending_state() -> None:
    ready = ReadinessReceipt(
        system_id="fake",
        namespace="run-1:conversation-1",
        ready=True,
        pending_count=0,
    )
    pending = ReadinessReceipt(
        system_id="fake",
        namespace="run-1:conversation-1",
        ready=False,
        pending_count=2,
    )

    assert ready.ready
    assert pending.pending_count == 2
    with pytest.raises(ValidationError, match="pending_count"):
        ReadinessReceipt(
            system_id="fake",
            namespace="run-1:conversation-1",
            ready=True,
            pending_count=1,
        )


def test_usage_and_latency_validates_counts_cost_and_currency() -> None:
    usage = UsageAndLatency(
        system_id="fake",
        namespace="run-1:conversation-1",
        call_count=2,
        input_tokens=10,
        output_tokens=4,
        total_latency_seconds=0.25,
        provider_cost=0.002,
        currency="USD",
    )

    assert usage.input_tokens + usage.output_tokens == 14
    with pytest.raises(ValidationError):
        UsageAndLatency(
            system_id="fake",
            namespace="run-1:conversation-1",
            call_count=-1,
            input_tokens=0,
            output_tokens=0,
            total_latency_seconds=0,
        )
    with pytest.raises(ValidationError, match="currency"):
        UsageAndLatency(
            system_id="fake",
            namespace="run-1:conversation-1",
            call_count=0,
            input_tokens=0,
            output_tokens=0,
            total_latency_seconds=0,
            provider_cost=0.01,
        )


def test_reset_receipt_validates_deleted_record_count() -> None:
    receipt = ResetReceipt(
        system_id="fake",
        namespace="run-1:conversation-1",
        reset=True,
        deleted_record_count=2,
    )

    assert receipt.reset
    with pytest.raises(ValidationError):
        ResetReceipt(
            system_id="fake",
            namespace="run-1:conversation-1",
            reset=False,
            deleted_record_count=-1,
        )


def test_evidence_has_exact_fields_and_immutable_duplicate_free_id_tuples() -> None:
    evidence = Evidence.model_validate(
        {
            "evidence_id": "evidence-1",
            "text": "source text",
            "source_exchange_ids": ["exchange-1"],
            "source_message_ids": ["message-u"],
            "system_record_ids": ["record-1"],
            "score": 0.75,
            "rank": 1,
            "channel": "symbolic",
            "metadata": {},
            "token_count": 3,
        }
    )

    assert set(evidence.model_dump()) == {
        "evidence_id",
        "text",
        "source_exchange_ids",
        "source_message_ids",
        "system_record_ids",
        "score",
        "rank",
        "channel",
        "metadata",
        "token_count",
    }
    assert isinstance(evidence.source_exchange_ids, tuple)
    assert isinstance(evidence.source_message_ids, tuple)
    assert isinstance(evidence.system_record_ids, tuple)
    with pytest.raises(ValidationError, match="duplicate"):
        Evidence.model_validate(
            {**evidence.model_dump(), "source_exchange_ids": ["exchange-1", "exchange-1"]}
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [("score", math.nan), ("rank", 0), ("token_count", -1)],
)
def test_evidence_rejects_invalid_numeric_fields(field: str, value: float | int) -> None:
    dumped = _evidence().model_dump()

    with pytest.raises(ValidationError):
        Evidence.model_validate({**dumped, field: value})


def test_memory_system_is_runtime_checkable_with_exact_async_surface() -> None:
    adapter = _FakeMemorySystem()

    assert isinstance(adapter, MemorySystem)
    for method_name in ("prepare", "ingest", "await_ready", "retrieve", "stats", "reset"):
        assert inspect.iscoroutinefunction(getattr(MemorySystem, method_name))
    assert list(inspect.signature(MemorySystem.retrieve).parameters) == [
        "self",
        "question",
        "evidence_budget_tokens",
    ]


@pytest.mark.asyncio
async def test_structural_memory_system_returns_typed_protocol_models() -> None:
    adapter = _FakeMemorySystem()
    scope = RunScope(run_id="run-1", conversation_id="conversation-1", system_id="fake")

    identity = await adapter.prepare(scope)
    receipt = await adapter.ingest(_exchange())
    readiness = await adapter.await_ready()
    evidence = await adapter.retrieve("What happened?", 100)
    usage = await adapter.stats()
    reset = await adapter.reset()

    assert identity.namespace == "run-1:conversation-1"
    assert receipt.source_exchange_id == "exchange-1"
    assert readiness.ready
    assert evidence == (_evidence(),)
    assert usage.call_count == 1
    assert reset.deleted_record_count == 1
