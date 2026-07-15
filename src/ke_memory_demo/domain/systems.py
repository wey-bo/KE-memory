from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ke_memory_demo.core.json import JsonObject

from .conversation import Exchange
from .memory import Evidence


NonEmptyString = Annotated[str, Field(min_length=1)]
NonNegativeInt = Annotated[int, Field(ge=0)]
NonNegativeFloat = Annotated[float, Field(ge=0, allow_inf_nan=False)]
Sha256Hex = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class _SystemRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class RunScope(_SystemRecord):
    run_id: NonEmptyString
    conversation_id: NonEmptyString
    system_id: NonEmptyString


class AdapterIdentity(_SystemRecord):
    system_id: NonEmptyString
    namespace: NonEmptyString
    implementation: NonEmptyString
    version: NonEmptyString
    metadata: JsonObject = Field(default_factory=dict)


class IngestReceipt(_SystemRecord):
    system_id: NonEmptyString
    namespace: NonEmptyString
    source_exchange_id: NonEmptyString
    system_record_ids: tuple[NonEmptyString, ...]
    source_content_hash: Sha256Hex
    metadata: JsonObject = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_record_ids(self) -> IngestReceipt:
        _reject_duplicate_strings(self.system_record_ids, "system record IDs")
        return self


class ReadinessReceipt(_SystemRecord):
    system_id: NonEmptyString
    namespace: NonEmptyString
    ready: bool
    pending_count: NonNegativeInt
    metadata: JsonObject = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_ready_state(self) -> ReadinessReceipt:
        if self.ready and self.pending_count:
            raise ValueError("pending_count must be zero when ready is true")
        return self


class UsageAndLatency(_SystemRecord):
    system_id: NonEmptyString
    namespace: NonEmptyString
    call_count: NonNegativeInt
    input_tokens: NonNegativeInt
    output_tokens: NonNegativeInt
    total_latency_seconds: NonNegativeFloat
    provider_cost: NonNegativeFloat | None = None
    currency: NonEmptyString | None = None
    metadata: JsonObject = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_cost_currency_pair(self) -> UsageAndLatency:
        if (self.provider_cost is None) != (self.currency is None):
            raise ValueError("provider_cost and currency must either both be set or both be absent")
        return self


class ResetReceipt(_SystemRecord):
    system_id: NonEmptyString
    namespace: NonEmptyString
    reset: bool
    deleted_record_count: NonNegativeInt
    metadata: JsonObject = Field(default_factory=dict)


@runtime_checkable
class MemorySystem(Protocol):
    system_id: str

    async def prepare(self, scope: RunScope) -> AdapterIdentity: ...

    async def ingest(self, exchange: Exchange) -> IngestReceipt: ...

    async def await_ready(self) -> ReadinessReceipt: ...

    async def retrieve(self, question: str, evidence_budget_tokens: int) -> Sequence[Evidence]: ...

    async def stats(self) -> UsageAndLatency: ...

    async def reset(self) -> ResetReceipt: ...


def _reject_duplicate_strings(values: tuple[str, ...], label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"duplicate {label} are not allowed")
