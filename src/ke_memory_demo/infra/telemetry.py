from __future__ import annotations

from collections.abc import Iterable
from typing import Annotated, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ke_memory_demo.core.json import JsonObject


MODEL_TRACE_ARTIFACT = "model_traces"

NonEmptyString = Annotated[str, Field(min_length=1)]
PositiveInt = Annotated[int, Field(ge=1)]
NonNegativeInt = Annotated[int, Field(ge=0)]
NonNegativeFloat = Annotated[float, Field(ge=0, allow_inf_nan=False)]


class _TelemetryRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class TraceContext(_TelemetryRecord):
    operation: NonEmptyString
    metadata: JsonObject = Field(default_factory=dict)


class UsageRecord(_TelemetryRecord):
    request_id: NonEmptyString | None
    model: NonEmptyString
    latency_seconds: NonNegativeFloat
    input_tokens: NonNegativeInt
    output_tokens: NonNegativeInt
    total_tokens: NonNegativeInt
    provider_cost: NonNegativeFloat | None = None


class ModelTrace(_TelemetryRecord):
    context: TraceContext
    transport_attempt: PositiveInt
    structured_request: PositiveInt
    latency_seconds: NonNegativeFloat
    request: JsonObject
    response: JsonObject | None
    error: JsonObject | None
    usage: UsageRecord | None

    @model_validator(mode="after")
    def _validate_outcome(self) -> ModelTrace:
        if self.response is None and self.error is None:
            raise ValueError("trace requires a response or an error")
        if self.usage is not None and self.response is None:
            raise ValueError("usage requires a provider response")
        return self


@runtime_checkable
class TraceRecorder(Protocol):
    def record(self, trace: ModelTrace) -> None: ...


class ArtifactRecordWriter(Protocol):
    def write(self, name: str, records: Iterable[object]) -> object: ...


class InMemoryTraceRecorder:
    def __init__(self) -> None:
        self._records: tuple[ModelTrace, ...] = ()

    @property
    def records(self) -> tuple[ModelTrace, ...]:
        return self._records

    @property
    def usage_records(self) -> tuple[UsageRecord, ...]:
        return tuple(trace.usage for trace in self._records if trace.usage is not None)

    def record(self, trace: ModelTrace) -> None:
        self._records = (*self._records, trace)


class ArtifactTraceRecorder:
    def __init__(
        self,
        writer: ArtifactRecordWriter,
        *,
        artifact_name: str = MODEL_TRACE_ARTIFACT,
    ) -> None:
        self._writer = writer
        self._artifact_name = artifact_name
        self._records: tuple[ModelTrace, ...] = ()

    @property
    def records(self) -> tuple[ModelTrace, ...]:
        return self._records

    @property
    def usage_records(self) -> tuple[UsageRecord, ...]:
        return tuple(trace.usage for trace in self._records if trace.usage is not None)

    def record(self, trace: ModelTrace) -> None:
        records = (*self._records, trace)
        self._writer.write(self._artifact_name, records)
        self._records = records
