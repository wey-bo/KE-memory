from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from email.utils import format_datetime
import json
from pathlib import Path
from typing import Literal, cast

import pytest
from openai.types.chat import ChatCompletion
from openai.types.chat.chat_completion import Choice
from openai.types.chat.chat_completion_message import ChatCompletionMessage
from openai.types.completion_usage import CompletionUsage
from pydantic import BaseModel, ValidationError, field_validator

from ke_memory_demo.infra.llm import (
    AuthenticationModelError,
    ContentPolicyModelError,
    InvariantModelError,
    ModelClientError,
    PermanentModelError,
    StructuredModelClient,
    StructuredOutputError,
    TransientModelError,
)
from ke_memory_demo.infra.retry import (
    MAX_TRANSPORT_ATTEMPTS,
    is_transient_transport_error,
    retry_delay_seconds,
)
from ke_memory_demo.infra.telemetry import (
    MODEL_TRACE_ARTIFACT,
    ArtifactTraceRecorder,
    InMemoryTraceRecorder,
    ModelTrace,
    TraceContext,
    UsageRecord,
)
from ke_memory_demo.settings import ModelSettings, load_settings
from ke_memory_demo.storage import ArtifactStore


class _Response:
    def __init__(self, headers: dict[str, str] | None = None) -> None:
        self.headers = headers or {}


class _StatusError(Exception):
    def __init__(
        self,
        status_code: int,
        headers: dict[str, str] | None = None,
        *,
        message: str | None = None,
    ) -> None:
        super().__init__(message or f"status {status_code}")
        self.status_code = status_code
        self.response = _Response(headers)


class ExampleOutput(BaseModel):
    value: int


class TextOutput(BaseModel):
    value: str


class UnsupportedSchemaOutput(BaseModel):
    callback: Callable[[], int]


class TypeErrorValidatorOutput(BaseModel):
    value: int

    @field_validator("value")
    @classmethod
    def _raise_type_error(cls, _value: int) -> int:
        raise TypeError("validator-type-secret")


def _completion(
    content: str | None,
    *,
    request_id: str | None = "request-1",
    completion_id: str | None = None,
    model: str = "provider-model",
    input_tokens: int = 10,
    output_tokens: int = 4,
    cost: float | None = None,
    finish_reason: Literal["stop", "length", "tool_calls", "content_filter", "function_call"] = (
        "stop"
    ),
    refusal: str | None = None,
) -> ChatCompletion:
    usage_values: dict[str, object] = {
        "prompt_tokens": input_tokens,
        "completion_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
    }
    if cost is not None:
        usage_values["cost"] = cost
    response = ChatCompletion(
        id=completion_id or f"chat-{request_id or 'without-http-request-id'}",
        choices=[
            Choice(
                finish_reason=finish_reason,
                index=0,
                logprobs=None,
                message=ChatCompletionMessage(
                    content=content,
                    refusal=refusal,
                    role="assistant",
                    annotations=[],
                ),
            )
        ],
        created=0,
        model=model,
        object="chat.completion",
        usage=CompletionUsage.model_validate(usage_values),
    )
    if request_id is not None:
        object.__setattr__(response, "_request_id", request_id)
    return response


class _FakeCompletions:
    def __init__(self, queued: list[object | Exception]) -> None:
        self.queued = queued
        self.calls: list[dict[str, object]] = []

    async def create(self, **kwargs: object) -> object:
        self.calls.append(dict(kwargs))
        if not self.queued:
            raise AssertionError("unexpected provider call")
        outcome = self.queued.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class _FakeChat:
    def __init__(self, completions: _FakeCompletions) -> None:
        self.completions = completions


class _FakeClient:
    def __init__(self, queued: list[object | Exception]) -> None:
        self.completions = _FakeCompletions(queued)
        self.chat = _FakeChat(self.completions)
        self.close_calls = 0

    async def close(self) -> None:
        self.close_calls += 1


class _Clock:
    def __init__(self, step: float = 0.25) -> None:
        self.current = 0.0
        self.step = step

    def __call__(self) -> float:
        value = self.current
        self.current += self.step
        return value


def _model_settings(
    *,
    model: str = "gpt-5.4",
    temperature: float = 0.0,
    max_output_tokens: int = 4096,
) -> ModelSettings:
    return ModelSettings(
        model=model,
        base_url="https://model.test.invalid/v1",
        api_key_env="TEST_MODEL_API_KEY",
        temperature=temperature,
        max_output_tokens=max_output_tokens,
    )


def _structured_client(
    queued: list[object | Exception],
    *,
    settings: ModelSettings | None = None,
    supports_json_schema: bool = True,
    known_secrets: set[str] | None = None,
) -> tuple[StructuredModelClient, _FakeClient, InMemoryTraceRecorder, list[float]]:
    fake = _FakeClient(queued)
    recorder = InMemoryTraceRecorder()
    delays: list[float] = []

    async def sleep(delay: float) -> None:
        delays.append(delay)

    client = StructuredModelClient(
        settings or _model_settings(),
        client=fake,
        supports_json_schema=supports_json_schema,
        trace_recorder=recorder,
        known_secrets=known_secrets or set(),
        sleep=sleep,
        clock=_Clock(),
    )
    return client, fake, recorder, delays


def _exception_graph(error: BaseException) -> tuple[BaseException, ...]:
    pending = [error]
    seen: set[int] = set()
    graph: list[BaseException] = []
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        graph.append(current)
        if current.__cause__ is not None:
            pending.append(current.__cause__)
        if current.__context__ is not None:
            pending.append(current.__context__)
    return tuple(graph)


def _assert_detached_secret_safe(error: ModelClientError, secret: str) -> None:
    graph = _exception_graph(error)
    assert graph == (error,)
    assert error.__cause__ is None
    assert error.__context__ is None
    assert all(secret not in str(item) and secret not in repr(item) for item in graph)


def _assert_secret_not_recoverable(value: object, secret: str) -> None:
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True)
    assert secret not in serialized
    assert json.dumps(secret, ensure_ascii=False)[1:-1] not in serialized
    assert json.dumps(secret, ensure_ascii=True)[1:-1] not in serialized

    def visit(item: object, depth: int = 0) -> None:
        assert depth < 8
        if isinstance(item, dict):
            mapping = cast(dict[object, object], item)
            for key, nested in mapping.items():
                visit(key, depth + 1)
                visit(nested, depth + 1)
            return
        if isinstance(item, list | tuple):
            sequence = cast(Sequence[object], item)
            for nested in sequence:
                visit(nested, depth + 1)
            return
        if not isinstance(item, str):
            return
        assert secret not in item
        assert json.dumps(secret, ensure_ascii=False)[1:-1] not in item
        assert json.dumps(secret, ensure_ascii=True)[1:-1] not in item
        try:
            decoded = json.loads(item)
        except (TypeError, ValueError):
            return
        if decoded != item:
            visit(decoded, depth + 1)

    visit(value)


class _SecretRepr:
    def __init__(self, secret: str) -> None:
        self._secret = secret

    def __repr__(self) -> str:
        return self._secret


class _ExplodingUsage:
    def __init__(self, secret: str) -> None:
        self._secret = secret

    @property
    def prompt_tokens(self) -> int:
        raise RuntimeError(self._secret)


class _ExplodingMessage:
    def __init__(self, secret: str) -> None:
        self._secret = secret

    @property
    def refusal(self) -> str | None:
        raise RuntimeError(self._secret)


class _FailingRecorder:
    def __init__(self, secret: str) -> None:
        self._secret = secret

    def record(self, trace: ModelTrace) -> None:
        del trace
        raise RuntimeError(self._secret)


@pytest.mark.parametrize(
    "error", [TimeoutError(), _StatusError(429), _StatusError(500), _StatusError(599)]
)
def test_only_retryable_transport_failures_are_transient(error: Exception) -> None:
    assert is_transient_transport_error(error)


@pytest.mark.parametrize("status_code", [400, 401, 403, 404])
def test_permanent_http_failures_are_not_transient(status_code: int) -> None:
    assert not is_transient_transport_error(_StatusError(status_code))


def test_retry_policy_has_four_total_attempts_and_exact_fallback_delays() -> None:
    error = _StatusError(500)

    assert MAX_TRANSPORT_ATTEMPTS == 4
    assert [retry_delay_seconds(error, ordinal, clock=lambda: 0.0) for ordinal in (1, 2, 3)] == [
        1.0,
        2.0,
        4.0,
    ]


def test_retry_after_seconds_overrides_fallback() -> None:
    error = _StatusError(429, {"rEtRy-AfTeR": "2.5"})

    assert retry_delay_seconds(error, 1, clock=lambda: 0.0) == 2.5


def test_retry_after_http_date_uses_injected_clock() -> None:
    now = datetime(2026, 7, 16, 12, 0, tzinfo=UTC)
    retry_at = datetime(2026, 7, 16, 12, 0, 9, tzinfo=UTC)
    error = _StatusError(503, {"Retry-After": format_datetime(retry_at, usegmt=True)})

    assert retry_delay_seconds(error, 2, clock=lambda: now.timestamp()) == 9.0


@pytest.mark.parametrize("value", ["", "not-a-delay", "-1", "nan", "inf"])
def test_invalid_retry_after_uses_fallback(value: str) -> None:
    error = _StatusError(503, {"Retry-After": value})

    assert retry_delay_seconds(error, 2, clock=lambda: 0.0) == 2.0


def _usage() -> UsageRecord:
    return UsageRecord(
        request_id="request-1",
        model="provider-model",
        latency_seconds=0.25,
        input_tokens=10,
        output_tokens=4,
        total_tokens=14,
        provider_cost=None,
    )


def _trace() -> ModelTrace:
    return ModelTrace(
        context=TraceContext(operation="extract", metadata={"conversation_id": "conversation-1"}),
        transport_attempt=1,
        structured_request=1,
        latency_seconds=0.25,
        request={"messages": [{"role": "user", "content": "safe"}]},
        response={"content": '{"value": 1}'},
        error=None,
        usage=_usage(),
    )


def test_usage_and_trace_records_are_frozen_and_forbid_extra_fields() -> None:
    usage = _usage()
    trace = _trace()

    with pytest.raises(ValidationError):
        usage.input_tokens = 11
    with pytest.raises(ValidationError):
        ModelTrace.model_validate({**trace.model_dump(), "unexpected": True})


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("latency_seconds", -0.1),
        ("latency_seconds", float("nan")),
        ("input_tokens", -1),
        ("provider_cost", float("inf")),
    ],
)
def test_usage_rejects_negative_or_non_finite_numbers(field: str, value: float) -> None:
    payload = _usage().model_dump()
    payload[field] = value

    with pytest.raises(ValidationError):
        UsageRecord.model_validate(payload)


def test_artifact_trace_recorder_uses_validated_temporary_stage_data(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path, registry={MODEL_TRACE_ARTIFACT: ModelTrace})
    trace = _trace()

    with store.stage_writer("run-1", "extract") as writer:
        recorder = ArtifactTraceRecorder(writer)
        recorder.record(trace)

        temporary = tmp_path / ".staging/run-1/extract/model_traces.jsonl"
        assert temporary.is_file()
        assert b"request-1" in temporary.read_bytes()
        assert not (tmp_path / "runs/run-1/extract").exists()

    assert list(store.read_jsonl("run-1", "extract", MODEL_TRACE_ARTIFACT, ModelTrace)) == [trace]


@pytest.mark.asyncio
async def test_schema_mode_uses_exact_kwargs_and_records_redacted_usage() -> None:
    secret = "known-secret"
    client, fake, recorder, delays = _structured_client(
        [
            _completion(
                f'{{"value":"prefix {secret} suffix"}}',
                request_id="provider-request-7",
                model="actual-provider-model",
                input_tokens=12,
                output_tokens=5,
                cost=0.003,
            )
        ],
        known_secrets={secret},
    )
    messages = [{"role": "user", "content": f"return JSON, credential={secret}"}]

    result = await client.complete(
        TextOutput,
        messages,
        TraceContext(operation="extract", metadata={"secret_note": secret}),
    )

    assert result == TextOutput(value=f"prefix {secret} suffix")
    assert messages == [{"role": "user", "content": f"return JSON, credential={secret}"}]
    assert delays == []
    assert len(fake.completions.calls) == 1
    request = fake.completions.calls[0]
    assert set(request) == {"model", "messages", "max_completion_tokens", "response_format"}
    assert request["model"] == "gpt-5.4"
    assert request["messages"] == messages
    assert request["max_completion_tokens"] == 4096
    assert "temperature" not in request
    response_format = cast(dict[str, object], request["response_format"])
    assert response_format["type"] == "json_schema"
    schema_config = cast(dict[str, object], response_format["json_schema"])
    assert schema_config["name"] == "TextOutput"
    assert schema_config["strict"] is True
    assert schema_config["schema"] == TextOutput.model_json_schema()

    assert len(recorder.records) == 1
    trace = recorder.records[0]
    assert trace.usage == UsageRecord(
        request_id="provider-request-7",
        model="actual-provider-model",
        latency_seconds=0.25,
        input_tokens=12,
        output_tokens=5,
        total_tokens=17,
        provider_cost=0.003,
    )
    assert secret not in trace.model_dump_json()
    assert "[REDACTED]" in trace.model_dump_json()


@pytest.mark.asyncio
async def test_trace_boundary_redacts_encoded_content_context_and_usage_identity() -> None:
    secret = 'trace"slash\\line\n\t雪'
    content = json.dumps({"value": secret}, ensure_ascii=True)
    client, _fake, recorder, _delays = _structured_client(
        [
            _completion(
                content,
                request_id=f"request::{secret}",
                model=f"model::{secret}",
            )
        ],
        known_secrets={secret},
    )

    result = await client.complete(
        TextOutput,
        [{"role": "user", "content": json.dumps({"credential": secret}, ensure_ascii=True)}],
        TraceContext(
            operation="extract",
            metadata={secret: json.dumps({"value": secret}, ensure_ascii=True)},
        ),
    )

    assert result.value == secret
    assert len(recorder.records) == 1
    _assert_secret_not_recoverable(recorder.records[0].model_dump(mode="json"), secret)


@pytest.mark.asyncio
async def test_repair_request_never_retransmits_decodable_known_secret() -> None:
    secret = 'repair"slash\\line\n\t雪'
    invalid = json.dumps({"value": "bad", "leak": secret}, ensure_ascii=True)
    client, fake, _recorder, _delays = _structured_client(
        [_completion(invalid), _completion('{"value":3}')],
        known_secrets={secret},
    )

    result = await client.complete(
        ExampleOutput,
        [{"role": "user", "content": "JSON"}],
        TraceContext(operation="extract"),
    )

    assert result.value == 3
    repair_messages = fake.completions.calls[1]["messages"]
    _assert_secret_not_recoverable(repair_messages, secret)


@pytest.mark.asyncio
async def test_artifact_trace_jsonl_contains_no_literal_or_decodable_secret(tmp_path: Path) -> None:
    secret = 'artifact"slash\\line\n\t雪'
    store = ArtifactStore(tmp_path, registry={MODEL_TRACE_ARTIFACT: ModelTrace})
    fake = _FakeClient(
        [
            _completion(
                json.dumps({"value": secret}, ensure_ascii=True),
                request_id=f"request::{secret}",
                model=f"model::{secret}",
            )
        ]
    )

    with store.stage_writer("run-1", "extract") as writer:
        client = StructuredModelClient(
            _model_settings(),
            client=fake,
            supports_json_schema=True,
            trace_recorder=ArtifactTraceRecorder(writer),
            known_secrets={secret},
            clock=_Clock(),
        )
        result = await client.complete(
            TextOutput,
            [{"role": "user", "content": json.dumps(secret, ensure_ascii=True)}],
            TraceContext(operation="extract", metadata={"encoded": json.dumps(secret)}),
        )
        assert result.value == secret

        payload = (tmp_path / ".staging/run-1/extract/model_traces.jsonl").read_text()
        assert secret not in payload
        _assert_secret_not_recoverable(json.loads(payload), secret)

    canonical = (tmp_path / "runs/run-1/extract/model_traces.jsonl").read_text()
    assert secret not in canonical
    _assert_secret_not_recoverable(json.loads(canonical), secret)


@pytest.mark.asyncio
async def test_json_object_mode_keeps_validation_and_configured_temperature() -> None:
    settings = _model_settings(
        model="deepseek-v4-pro",
        temperature=0.25,
        max_output_tokens=321,
    )
    client, fake, recorder, _delays = _structured_client(
        [_completion('{"value":3}')],
        settings=settings,
        supports_json_schema=False,
    )

    result = await client.complete(
        ExampleOutput,
        [{"role": "user", "content": "JSON please"}],
        TraceContext(operation="answer"),
    )

    assert result == ExampleOutput(value=3)
    request = fake.completions.calls[0]
    assert request["response_format"] == {"type": "json_object"}
    assert request["temperature"] == 0.25
    assert request["max_completion_tokens"] == 321
    assert len(recorder.usage_records) == 1


@pytest.mark.asyncio
async def test_usage_request_id_is_provider_http_request_id_not_completion_id() -> None:
    client, _fake, recorder, _delays = _structured_client(
        [
            _completion(
                '{"value":3}',
                request_id="http-request-17",
                completion_id="chat-completion-99",
            )
        ]
    )

    await client.complete(
        ExampleOutput,
        [{"role": "user", "content": "JSON"}],
        TraceContext(operation="extract"),
    )

    assert recorder.usage_records[0].request_id == "http-request-17"
    assert recorder.records[0].response is not None
    assert recorder.records[0].response["id"] == "chat-completion-99"


@pytest.mark.asyncio
async def test_usage_request_id_remains_none_when_http_request_id_is_absent() -> None:
    client, _fake, recorder, _delays = _structured_client(
        [
            _completion(
                '{"value":3}',
                request_id=None,
                completion_id="chat-completion-only",
            )
        ]
    )

    await client.complete(
        ExampleOutput,
        [{"role": "user", "content": "JSON"}],
        TraceContext(operation="extract"),
    )

    assert recorder.usage_records[0].request_id is None
    assert recorder.records[0].response is not None
    assert recorder.records[0].response["id"] == "chat-completion-only"


@pytest.mark.parametrize("model", ["gpt-5", "gpt-5.4-mini", "o1", "o1-preview", "o3-mini"])
@pytest.mark.asyncio
async def test_reasoning_model_prefixes_omit_temperature(model: str) -> None:
    client, fake, _recorder, _delays = _structured_client(
        [_completion('{"value":3}')],
        settings=_model_settings(model=model, temperature=0.7),
    )

    await client.complete(
        ExampleOutput,
        [{"role": "user", "content": "JSON"}],
        TraceContext(operation="extract"),
    )

    assert "temperature" not in fake.completions.calls[0]


@pytest.mark.asyncio
async def test_schema_error_gets_two_repairs_then_succeeds_and_accumulates_usage() -> None:
    client, fake, recorder, delays = _structured_client(
        [
            _completion('{"wrong":1}', request_id="request-1", input_tokens=5, output_tokens=2),
            _completion('{"value":"bad"}', request_id="request-2", input_tokens=7, output_tokens=3),
            _completion('{"value":3}', request_id="request-3", input_tokens=9, output_tokens=4),
        ]
    )

    result = await client.complete(
        ExampleOutput,
        [{"role": "user", "content": "return value"}],
        TraceContext(operation="extract"),
    )

    assert result.value == 3
    assert len(fake.completions.calls) == 3
    assert delays == []
    assert [len(cast(list[object], call["messages"])) for call in fake.completions.calls] == [
        1,
        3,
        5,
    ]
    assert [trace.structured_request for trace in recorder.records] == [1, 2, 3]
    assert [trace.transport_attempt for trace in recorder.records] == [1, 2, 3]
    assert sum(usage.input_tokens for usage in recorder.usage_records) == 21
    assert sum(usage.output_tokens for usage in recorder.usage_records) == 9
    assert all(
        call["response_format"] == fake.completions.calls[0]["response_format"]
        for call in fake.completions.calls
    )


@pytest.mark.asyncio
async def test_three_schema_failures_raise_structured_output_error() -> None:
    client, fake, recorder, _delays = _structured_client(
        [_completion("{}"), _completion("[]"), _completion('{"value":"bad"}')]
    )

    with pytest.raises(StructuredOutputError, match="schema"):
        await client.complete(
            ExampleOutput,
            [{"role": "user", "content": "return value"}],
            TraceContext(operation="extract"),
        )

    assert len(fake.completions.calls) == 3
    assert len(recorder.usage_records) == 3


@pytest.mark.asyncio
async def test_validator_type_error_is_traced_invariant_and_not_repaired() -> None:
    secret = "validator-type-secret"
    client, fake, recorder, delays = _structured_client(
        [_completion('{"value":3}'), _completion('{"value":4}')],
        known_secrets={secret},
    )

    with pytest.raises(InvariantModelError) as captured:
        await client.complete(
            TypeErrorValidatorOutput,
            [{"role": "user", "content": "JSON"}],
            TraceContext(operation="extract"),
        )

    assert len(fake.completions.calls) == 1
    assert len(fake.completions.queued) == 1
    assert delays == []
    assert len(recorder.records) == 1
    trace = recorder.records[0]
    assert trace.response is not None
    assert trace.usage is not None
    assert trace.error == {
        "type": "invariant",
        "message": "structured response validator failed",
    }
    _assert_detached_secret_safe(captured.value, secret)


@pytest.mark.asyncio
async def test_transient_failures_stop_at_four_calls_with_exact_delays_and_safe_errors() -> None:
    secret = "transport-secret"
    client, fake, recorder, delays = _structured_client(
        [
            _StatusError(500, message=f"first {secret}"),
            _StatusError(502, message=f"second {secret}"),
            _StatusError(503, message=f"third {secret}"),
            _StatusError(599, message=f"fourth {secret}"),
            _completion('{"value":3}'),
        ],
        known_secrets={secret},
    )

    with pytest.raises(TransientModelError) as captured:
        await client.complete(
            ExampleOutput,
            [{"role": "user", "content": secret}],
            TraceContext(operation="extract"),
        )

    assert len(fake.completions.calls) == 4
    assert len(fake.completions.queued) == 1
    assert delays == [1.0, 2.0, 4.0]
    assert [trace.transport_attempt for trace in recorder.records] == [1, 2, 3, 4]
    assert secret not in str(captured.value)
    assert secret not in "".join(trace.model_dump_json() for trace in recorder.records)
    _assert_detached_secret_safe(captured.value, secret)


@pytest.mark.asyncio
async def test_authentication_error_has_no_raw_provider_exception_graph() -> None:
    secret = "auth-graph-secret"
    client, _fake, _recorder, _delays = _structured_client(
        [_StatusError(401, message=secret)],
        known_secrets={secret},
    )

    with pytest.raises(AuthenticationModelError) as captured:
        await client.complete(
            ExampleOutput,
            [{"role": "user", "content": "JSON"}],
            TraceContext(operation="extract"),
        )

    _assert_detached_secret_safe(captured.value, secret)


@pytest.mark.asyncio
async def test_retry_after_is_honored_by_the_client() -> None:
    client, fake, _recorder, delays = _structured_client(
        [_StatusError(429, {"Retry-After": "2.5"}), _completion('{"value":3}')]
    )

    result = await client.complete(
        ExampleOutput,
        [{"role": "user", "content": "JSON"}],
        TraceContext(operation="extract"),
    )

    assert result.value == 3
    assert len(fake.completions.calls) == 2
    assert delays == [2.5]


@pytest.mark.asyncio
async def test_transport_and_repair_calls_share_one_four_call_budget() -> None:
    client, fake, recorder, delays = _structured_client(
        [
            _completion('{"wrong":1}', request_id="request-1"),
            _StatusError(500),
            _completion('{"value":"bad"}', request_id="request-3"),
            _StatusError(503),
            _completion('{"value":3}', request_id="request-5"),
        ]
    )

    with pytest.raises(TransientModelError):
        await client.complete(
            ExampleOutput,
            [{"role": "user", "content": "return value"}],
            TraceContext(operation="extract"),
        )

    assert len(fake.completions.calls) == 4
    assert len(fake.completions.queued) == 1
    assert delays == [1.0]
    assert [trace.structured_request for trace in recorder.records] == [1, 2, 2, 3]
    assert [trace.transport_attempt for trace in recorder.records] == [1, 2, 3, 4]
    assert len(recorder.usage_records) == 2


@pytest.mark.asyncio
async def test_schema_exhaustion_has_no_pydantic_exception_graph() -> None:
    secret = "schema-graph-secret"
    client, _fake, _recorder, _delays = _structured_client(
        [
            _completion(f'{{"value":"{secret}"}}'),
            _completion(f'{{"value":"{secret}"}}'),
            _completion(f'{{"value":"{secret}"}}'),
        ],
        known_secrets={secret},
    )

    with pytest.raises(StructuredOutputError) as captured:
        await client.complete(
            ExampleOutput,
            [{"role": "user", "content": "JSON"}],
            TraceContext(operation="extract"),
        )

    _assert_detached_secret_safe(captured.value, secret)


@pytest.mark.parametrize("status_code", [400, 401, 403, 404])
@pytest.mark.asyncio
async def test_permanent_transport_errors_are_not_retried(status_code: int) -> None:
    client, fake, recorder, delays = _structured_client([_StatusError(status_code)])

    with pytest.raises(PermanentModelError):
        await client.complete(
            ExampleOutput,
            [{"role": "user", "content": "JSON"}],
            TraceContext(operation="extract"),
        )

    assert len(fake.completions.calls) == 1
    assert delays == []
    assert len(recorder.records) == 1


@pytest.mark.asyncio
async def test_content_policy_response_is_a_typed_permanent_error() -> None:
    client, fake, recorder, delays = _structured_client(
        [_completion(None, finish_reason="content_filter", refusal="blocked")]
    )

    with pytest.raises(ContentPolicyModelError):
        await client.complete(
            ExampleOutput,
            [{"role": "user", "content": "JSON"}],
            TraceContext(operation="extract"),
        )

    assert len(fake.completions.calls) == 1
    assert delays == []
    assert recorder.records[0].error is not None


@pytest.mark.asyncio
async def test_zero_choices_is_traced_as_typed_invariant() -> None:
    response = _completion('{"value":3}')
    object.__setattr__(response, "choices", [])
    client, fake, recorder, delays = _structured_client([response])

    with pytest.raises(InvariantModelError, match="exactly one"):
        await client.complete(
            ExampleOutput,
            [{"role": "user", "content": "JSON"}],
            TraceContext(operation="extract"),
        )

    assert len(fake.completions.calls) == 1
    assert delays == []
    assert len(recorder.records) == 1
    assert recorder.records[0].response is not None
    assert recorder.records[0].usage is not None


@pytest.mark.asyncio
async def test_multiple_choices_rejects_dangerous_second_choice_as_invariant() -> None:
    response = _completion('{"value":3}')
    dangerous = _completion(
        None,
        finish_reason="content_filter",
        refusal="dangerous second choice",
    ).choices[0]
    object.__setattr__(response, "choices", [response.choices[0], dangerous])
    client, fake, recorder, delays = _structured_client([response])

    with pytest.raises(InvariantModelError, match="exactly one"):
        await client.complete(
            ExampleOutput,
            [{"role": "user", "content": "JSON"}],
            TraceContext(operation="extract"),
        )

    assert len(fake.completions.calls) == 1
    assert delays == []
    assert len(recorder.records) == 1
    assert recorder.records[0].response is not None
    assert len(cast(list[object], recorder.records[0].response["choices"])) == 2


@pytest.mark.asyncio
async def test_missing_usage_is_a_typed_invariant_error() -> None:
    response = _completion('{"value":3}')
    object.__setattr__(response, "usage", None)
    client, fake, recorder, delays = _structured_client([response])

    with pytest.raises(InvariantModelError, match="usage"):
        await client.complete(
            ExampleOutput,
            [{"role": "user", "content": "JSON"}],
            TraceContext(operation="extract"),
        )

    assert len(fake.completions.calls) == 1
    assert delays == []
    assert recorder.records[0].response is not None
    assert recorder.records[0].error is not None


@pytest.mark.asyncio
async def test_invalid_local_input_has_no_validation_exception_graph() -> None:
    secret = "input-graph-secret"
    client, fake, _recorder, _delays = _structured_client(
        [],
        known_secrets={secret},
    )

    with pytest.raises(InvariantModelError) as captured:
        await client.complete(
            ExampleOutput,
            [{"role": "user", "content": _SecretRepr(secret)}],
            TraceContext(operation="extract"),
        )

    assert fake.completions.calls == []
    _assert_detached_secret_safe(captured.value, secret)


@pytest.mark.asyncio
async def test_usage_parser_failure_has_no_raw_exception_graph() -> None:
    secret = "usage-graph-secret"
    response = _completion('{"value":3}')
    object.__setattr__(response, "usage", _ExplodingUsage(secret))
    client, _fake, _recorder, _delays = _structured_client(
        [response],
        known_secrets={secret},
    )

    with pytest.raises(InvariantModelError) as captured:
        await client.complete(
            ExampleOutput,
            [{"role": "user", "content": "JSON"}],
            TraceContext(operation="extract"),
        )

    _assert_detached_secret_safe(captured.value, secret)


@pytest.mark.asyncio
async def test_response_parser_failure_has_no_raw_exception_graph() -> None:
    secret = "response-graph-secret"
    response = _completion('{"value":3}')
    object.__setattr__(response.choices[0], "message", _ExplodingMessage(secret))
    client, _fake, _recorder, _delays = _structured_client(
        [response],
        known_secrets={secret},
    )

    with pytest.raises(InvariantModelError) as captured:
        await client.complete(
            ExampleOutput,
            [{"role": "user", "content": "JSON"}],
            TraceContext(operation="extract"),
        )

    _assert_detached_secret_safe(captured.value, secret)


@pytest.mark.asyncio
async def test_recorder_failure_has_no_raw_exception_graph() -> None:
    secret = "recorder-graph-secret"
    fake = _FakeClient([_completion('{"value":3}')])
    client = StructuredModelClient(
        _model_settings(),
        client=fake,
        supports_json_schema=True,
        trace_recorder=_FailingRecorder(secret),
        known_secrets={secret},
        clock=_Clock(),
    )

    with pytest.raises(InvariantModelError) as captured:
        await client.complete(
            ExampleOutput,
            [{"role": "user", "content": "JSON"}],
            TraceContext(operation="extract"),
        )

    _assert_detached_secret_safe(captured.value, secret)


@pytest.mark.asyncio
async def test_unrepresentable_json_schema_is_a_typed_invariant_without_provider_call() -> None:
    client, fake, recorder, delays = _structured_client([])

    with pytest.raises(InvariantModelError, match="schema") as captured:
        await client.complete(
            UnsupportedSchemaOutput,
            [{"role": "user", "content": "JSON"}],
            TraceContext(operation="extract"),
        )

    assert fake.completions.calls == []
    assert recorder.records == ()
    assert delays == []
    _assert_detached_secret_safe(captured.value, "schema-generation-secret")


def test_production_constructor_uses_work_secret_without_exposing_it(
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ke_memory_demo.infra import llm

    secret = "production-constructor-test-secret"
    captured: dict[str, object] = {}
    fake = _FakeClient([])

    def fake_async_openai(**kwargs: object) -> _FakeClient:
        captured.update(kwargs)
        return fake

    monkeypatch.setenv("KE_MEMORY_WORK_API_KEY", secret)
    monkeypatch.setattr(llm, "AsyncOpenAI", fake_async_openai)

    client = StructuredModelClient.from_app_settings(
        load_settings(project_root),
        supports_json_schema=True,
        trace_recorder=InMemoryTraceRecorder(),
    )

    assert captured == {
        "base_url": "https://api.penguinsaichat.dpdns.org/v1",
        "api_key": secret,
        "max_retries": 0,
    }
    assert secret not in repr(client)


@pytest.mark.asyncio
async def test_injected_client_is_caller_owned_and_close_is_idempotent() -> None:
    client, fake, _recorder, _delays = _structured_client([_completion('{"value":3}')])

    await client.aclose()
    await client.aclose()

    assert fake.close_calls == 0


@pytest.mark.asyncio
async def test_complete_after_close_is_detached_invariant_before_transport() -> None:
    secret = "closed-client-secret"
    client, fake, _recorder, _delays = _structured_client(
        [_completion('{"value":3}')],
        known_secrets={secret},
    )
    await client.aclose()

    with pytest.raises(InvariantModelError, match="closed") as captured:
        await client.complete(
            ExampleOutput,
            [{"role": "user", "content": secret}],
            TraceContext(operation="extract"),
        )

    assert fake.completions.calls == []
    _assert_detached_secret_safe(captured.value, secret)


@pytest.mark.asyncio
async def test_from_app_settings_owns_and_closes_client_once(
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ke_memory_demo.infra import llm

    fake = _FakeClient([])
    monkeypatch.setenv("KE_MEMORY_WORK_API_KEY", "owned-close-test-secret")

    def fake_async_openai(**_kwargs: object) -> _FakeClient:
        return fake

    monkeypatch.setattr(llm, "AsyncOpenAI", fake_async_openai)
    client = StructuredModelClient.from_app_settings(
        load_settings(project_root),
        supports_json_schema=True,
        trace_recorder=InMemoryTraceRecorder(),
    )

    await client.aclose()
    await client.aclose()

    assert fake.close_calls == 1


@pytest.mark.asyncio
async def test_owned_client_async_context_closes_on_exit(
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ke_memory_demo.infra import llm

    fake = _FakeClient([_completion('{"value":3}')])
    monkeypatch.setenv("KE_MEMORY_WORK_API_KEY", "owned-context-test-secret")

    def fake_async_openai(**_kwargs: object) -> _FakeClient:
        return fake

    monkeypatch.setattr(llm, "AsyncOpenAI", fake_async_openai)

    async with StructuredModelClient.from_app_settings(
        load_settings(project_root),
        supports_json_schema=True,
        trace_recorder=InMemoryTraceRecorder(),
    ) as client:
        result = await client.complete(
            ExampleOutput,
            [{"role": "user", "content": "JSON"}],
            TraceContext(operation="extract"),
        )
        assert result.value == 3
        assert fake.close_calls == 0

    assert fake.close_calls == 1
