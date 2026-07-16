from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
import inspect
import math
import re
import time
from types import TracebackType
from typing import Any, Protocol, TypeVar, cast

from openai import AsyncOpenAI
from pydantic import BaseModel, TypeAdapter, ValidationError

from ke_memory_demo.core.json import JsonObject, JsonValue
from ke_memory_demo.settings import AppSettings, ModelSettings

from .redaction import redact_text, redact_tree
from .retry import (
    MAX_TRANSPORT_ATTEMPTS,
    error_status_code,
    is_transient_transport_error,
    retry_delay_seconds,
)
from .telemetry import ModelTrace, TraceContext, TraceRecorder, UsageRecord


ModelT = TypeVar("ModelT", bound=BaseModel)
Sleep = Callable[[float], Awaitable[None]]
Clock = Callable[[], float]

_JSON_OBJECT: TypeAdapter[dict[str, JsonValue]] = TypeAdapter(dict[str, JsonValue])
_MESSAGE_LIST: TypeAdapter[list[JsonObject]] = TypeAdapter(list[JsonObject])
_SCHEMA_NAME = re.compile(r"[^A-Za-z0-9_-]+")
_NO_TEMPERATURE_PREFIXES = ("gpt-5", "o1", "o3")
_REPAIR_INSTRUCTION = (
    "The previous response did not satisfy the required JSON schema. "
    "Return only a corrected JSON object that satisfies the same schema."
)


class ModelClientError(RuntimeError):
    """Base class for secret-safe structured model failures."""


class TransientModelError(ModelClientError):
    """A retryable transport failure exhausted the shared attempt budget."""


class PermanentModelError(ModelClientError):
    """A request cannot succeed through transport retry."""


class AuthenticationModelError(PermanentModelError):
    """Provider authentication or authorization failed."""


class ModelNotFoundError(PermanentModelError):
    """The configured provider model does not exist."""


class ContentPolicyModelError(PermanentModelError):
    """The provider rejected or filtered the request for policy reasons."""


class InvariantModelError(PermanentModelError):
    """The provider response or local telemetry contract was malformed."""


class StructuredOutputError(PermanentModelError):
    """The provider exhausted schema repair or the shared call budget."""


class _CompletionEndpoint(Protocol):
    def create(self, **kwargs: Any) -> Awaitable[object]: ...


class _ChatEndpoint(Protocol):
    completions: _CompletionEndpoint


class _AsyncOpenAICompatible(Protocol):
    chat: _ChatEndpoint


class StructuredModelClient:
    def __init__(
        self,
        settings: ModelSettings,
        *,
        client: object,
        supports_json_schema: bool,
        trace_recorder: TraceRecorder,
        known_secrets: Iterable[str] = (),
        sleep: Sleep = asyncio.sleep,
        clock: Clock = time.time,
        _owns_client: bool = False,
    ) -> None:
        self._settings = settings
        self._client = cast(_AsyncOpenAICompatible, client)
        self._supports_json_schema = supports_json_schema
        self._trace_recorder = trace_recorder
        self._known_secrets = tuple(secret for secret in known_secrets if secret)
        self._sleep = sleep
        self._clock = clock
        self._owns_client = _owns_client
        self._closed = False

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(model={self._settings.model!r}, "
            f"supports_json_schema={self._supports_json_schema!r})"
        )

    @classmethod
    def from_app_settings(
        cls,
        settings: AppSettings,
        *,
        supports_json_schema: bool,
        trace_recorder: TraceRecorder,
        sleep: Sleep = asyncio.sleep,
        clock: Clock = time.time,
    ) -> StructuredModelClient:
        secret = settings.require_work_api_key()
        client = AsyncOpenAI(
            base_url=settings.work.base_url,
            api_key=secret,
            max_retries=0,
        )
        return cls(
            settings.work,
            client=client,
            supports_json_schema=supports_json_schema,
            trace_recorder=trace_recorder,
            known_secrets=(secret,),
            sleep=sleep,
            clock=clock,
            _owns_client=True,
        )

    async def __aenter__(self) -> StructuredModelClient:
        if self._closed:
            raise InvariantModelError("structured model client is closed")
        return self

    async def __aexit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc_value: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        if not self._owns_client:
            return

        terminal_error: ModelClientError | None = None
        try:
            close = getattr(self._client, "close", None)
            if not callable(close):
                raise InvariantModelError("owned model client does not provide async close")
            result = close()
            if not inspect.isawaitable(result):
                raise InvariantModelError("owned model client does not provide async close")
            await cast(Awaitable[object], result)
        except ModelClientError as error:
            terminal_error = self._detached_error(error)
        except Exception:
            terminal_error = InvariantModelError("owned model client close failed")

        if terminal_error is not None:
            raise terminal_error

    async def complete(
        self,
        model_type: type[ModelT],
        messages: Sequence[Mapping[str, object]],
        trace_context: TraceContext | Mapping[str, object],
    ) -> ModelT:
        terminal_error: ModelClientError | None = None
        try:
            return await self._complete(model_type, messages, trace_context)
        except ModelClientError as error:
            terminal_error = self._detached_error(error)
        except Exception:
            terminal_error = InvariantModelError("structured model client invariant failed")

        raise terminal_error

    async def _complete(
        self,
        model_type: type[ModelT],
        messages: Sequence[Mapping[str, object]],
        trace_context: TraceContext | Mapping[str, object],
    ) -> ModelT:
        if self._closed:
            raise InvariantModelError("structured model client is closed")
        request_messages = self._validated_messages(messages)
        context = self._redacted_context(trace_context)
        structured_request = 1
        repair_count = 0
        transport_attempt = 0
        transient_retry_ordinal = 0

        while transport_attempt < MAX_TRANSPORT_ATTEMPTS:
            transport_attempt += 1
            try:
                request = self._request_kwargs(model_type, request_messages)
            except Exception:
                raise InvariantModelError(
                    "structured output model does not provide a valid JSON schema"
                ) from None
            redacted_request = self._redacted_json_object(request)
            started_at = self._clock()
            try:
                response = await self._client.chat.completions.create(**request)
            except Exception as error:
                latency = self._elapsed_since(started_at)
                self._record_trace(
                    context=context,
                    transport_attempt=transport_attempt,
                    structured_request=structured_request,
                    latency_seconds=latency,
                    request=redacted_request,
                    response=None,
                    error=self._redacted_error(error),
                    usage=None,
                )
                if is_transient_transport_error(error):
                    if transport_attempt >= MAX_TRANSPORT_ATTEMPTS:
                        raise TransientModelError(
                            "transient model transport failed after four total attempts"
                        ) from None
                    transient_retry_ordinal += 1
                    delay = retry_delay_seconds(
                        error,
                        transient_retry_ordinal,
                        clock=self._clock,
                    )
                    await self._sleep(delay)
                    continue
                raise self._permanent_transport_error(error) from None

            latency = self._elapsed_since(started_at)
            response_tree = self._redacted_response(response)
            try:
                usage = self._usage_record(response, latency_seconds=latency)
            except InvariantModelError as error:
                self._record_trace(
                    context=context,
                    transport_attempt=transport_attempt,
                    structured_request=structured_request,
                    latency_seconds=latency,
                    request=redacted_request,
                    response=response_tree,
                    error={"type": "invariant", "message": str(error)},
                    usage=None,
                )
                raise error from None

            try:
                content = self._response_content(response)
            except PermanentModelError as error:
                error_type = "invariant" if isinstance(error, InvariantModelError) else "permanent"
                self._record_trace(
                    context=context,
                    transport_attempt=transport_attempt,
                    structured_request=structured_request,
                    latency_seconds=latency,
                    request=redacted_request,
                    response=response_tree,
                    error={"type": error_type, "message": str(error)},
                    usage=usage,
                )
                raise error from None

            try:
                result = model_type.model_validate_json(content)
            except ValidationError:
                self._record_trace(
                    context=context,
                    transport_attempt=transport_attempt,
                    structured_request=structured_request,
                    latency_seconds=latency,
                    request=redacted_request,
                    response=response_tree,
                    error={
                        "type": "schema_validation",
                        "message": "provider response did not satisfy the required schema",
                    },
                    usage=usage,
                )
                if repair_count >= 2 or transport_attempt >= MAX_TRANSPORT_ATTEMPTS:
                    raise StructuredOutputError(
                        "structured response failed schema validation within the allowed budget"
                    ) from None
                repair_count += 1
                structured_request += 1
                request_messages = self._repair_messages(request_messages, content)
                continue
            except Exception:
                self._record_trace(
                    context=context,
                    transport_attempt=transport_attempt,
                    structured_request=structured_request,
                    latency_seconds=latency,
                    request=redacted_request,
                    response=response_tree,
                    error={
                        "type": "invariant",
                        "message": "structured response validator failed",
                    },
                    usage=usage,
                )
                raise InvariantModelError("structured response validator failed") from None

            self._record_trace(
                context=context,
                transport_attempt=transport_attempt,
                structured_request=structured_request,
                latency_seconds=latency,
                request=redacted_request,
                response=response_tree,
                error=None,
                usage=usage,
            )
            return result

        raise InvariantModelError("shared model transport budget ended unexpectedly")

    def _request_kwargs(
        self,
        model_type: type[BaseModel],
        messages: list[JsonObject],
    ) -> dict[str, Any]:
        response_format: JsonObject
        if self._supports_json_schema:
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": _schema_name(model_type),
                    "strict": True,
                    "schema": cast(JsonObject, model_type.model_json_schema()),
                },
            }
        else:
            response_format = {"type": "json_object"}

        request: dict[str, Any] = {
            "model": self._settings.model,
            "messages": [dict(message) for message in messages],
            "max_completion_tokens": self._settings.max_output_tokens,
            "response_format": response_format,
        }
        if not self._settings.model.lower().startswith(_NO_TEMPERATURE_PREFIXES):
            request["temperature"] = self._settings.temperature
        return request

    def _validated_messages(self, messages: Sequence[Mapping[str, object]]) -> list[JsonObject]:
        try:
            validated = _MESSAGE_LIST.validate_python(list(messages))
            redacted = redact_tree(validated, known_secrets=self._known_secrets)
            return _MESSAGE_LIST.validate_python(redacted)
        except ValidationError:
            raise InvariantModelError("messages must contain JSON-compatible objects") from None

    def _redacted_context(
        self,
        context: TraceContext | Mapping[str, object],
    ) -> TraceContext:
        try:
            validated = (
                context
                if isinstance(context, TraceContext)
                else TraceContext.model_validate(context)
            )
            redacted = redact_tree(
                validated.model_dump(mode="json"),
                known_secrets=self._known_secrets,
            )
            return TraceContext.model_validate(redacted)
        except ValidationError:
            raise InvariantModelError("trace context is invalid") from None

    def _redacted_json_object(self, value: Mapping[str, object]) -> JsonObject:
        redacted = redact_tree(value, known_secrets=self._known_secrets)
        try:
            return _JSON_OBJECT.validate_python(redacted)
        except ValidationError:
            raise InvariantModelError("model request is not JSON-compatible") from None

    def _redacted_response(self, response: object) -> JsonObject:
        if isinstance(response, BaseModel):
            raw: object = response.model_dump(mode="json")
        else:
            model_dump = getattr(response, "model_dump", None)
            raw = model_dump(mode="json") if callable(model_dump) else response
        raw_mapping: Mapping[object, object] = (
            cast(Mapping[object, object], raw)
            if isinstance(raw, Mapping)
            else {"response_type": type(response).__name__}
        )
        redacted = redact_tree(raw_mapping, known_secrets=self._known_secrets)
        try:
            return _JSON_OBJECT.validate_python(redacted)
        except ValidationError:
            return {"response_type": type(response).__name__}

    def _redacted_error(self, error: Exception) -> JsonObject:
        payload: dict[str, object] = {
            "type": type(error).__name__,
            "message": redact_text(str(error), known_secrets=self._known_secrets),
        }
        status_code = error_status_code(error)
        if status_code is not None:
            payload["status_code"] = status_code
        return self._redacted_json_object(payload)

    def _usage_record(self, response: object, *, latency_seconds: float) -> UsageRecord:
        usage = getattr(response, "usage", None)
        if usage is None:
            raise InvariantModelError("provider response is missing token usage")

        model = getattr(response, "model", None)
        if not isinstance(model, str) or not model:
            raise InvariantModelError("provider response is missing the actual model")

        request_id = getattr(response, "_request_id", None)
        if not isinstance(request_id, str) or not request_id:
            request_id = None

        input_tokens = _required_token_count(usage, "prompt_tokens", "input_tokens")
        output_tokens = _required_token_count(usage, "completion_tokens", "output_tokens")
        total_tokens = _required_token_count(usage, "total_tokens")
        provider_cost = _provider_cost(usage, response)
        try:
            return UsageRecord(
                request_id=request_id,
                model=model,
                latency_seconds=latency_seconds,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                provider_cost=provider_cost,
            )
        except ValidationError:
            raise InvariantModelError("provider returned invalid usage data") from None

    def _response_content(self, response: object) -> str:
        choices = getattr(response, "choices", None)
        if not isinstance(choices, Sequence) or isinstance(choices, str | bytes):
            raise InvariantModelError("provider response must contain exactly one choice")
        choice_values = cast(Sequence[object], choices)
        if len(choice_values) != 1:
            raise InvariantModelError("provider response must contain exactly one choice")
        choice = choice_values[0]
        message = getattr(choice, "message", None)
        finish_reason = getattr(choice, "finish_reason", None)
        refusal = getattr(message, "refusal", None)
        if finish_reason == "content_filter" or (isinstance(refusal, str) and refusal):
            raise ContentPolicyModelError("provider rejected the structured request by policy")
        content = getattr(message, "content", None)
        if not isinstance(content, str):
            raise InvariantModelError("provider response is missing text content")
        return content

    def _repair_messages(self, messages: list[JsonObject], content: str) -> list[JsonObject]:
        safe_content = redact_text(content, known_secrets=self._known_secrets)
        return [
            *messages,
            {"role": "assistant", "content": safe_content},
            {"role": "user", "content": _REPAIR_INSTRUCTION},
        ]

    def _record_trace(
        self,
        *,
        context: TraceContext,
        transport_attempt: int,
        structured_request: int,
        latency_seconds: float,
        request: JsonObject,
        response: JsonObject | None,
        error: JsonObject | None,
        usage: UsageRecord | None,
    ) -> None:
        try:
            trace = ModelTrace(
                context=context,
                transport_attempt=transport_attempt,
                structured_request=structured_request,
                latency_seconds=latency_seconds,
                request=request,
                response=response,
                error=error,
                usage=usage,
            )
            redacted = redact_tree(
                trace.model_dump(mode="json"),
                known_secrets=self._known_secrets,
            )
            self._trace_recorder.record(ModelTrace.model_validate(redacted))
        except Exception:
            raise InvariantModelError("model trace recording failed") from None

    def _elapsed_since(self, started_at: float) -> float:
        elapsed = self._clock() - started_at
        if not math.isfinite(elapsed) or elapsed < 0:
            raise InvariantModelError("model client clock returned invalid latency")
        return elapsed

    @staticmethod
    def _permanent_transport_error(error: Exception) -> PermanentModelError:
        status_code = error_status_code(error)
        if _is_content_policy_error(error):
            return ContentPolicyModelError("provider rejected the structured request by policy")
        if status_code in (401, 403):
            return AuthenticationModelError("model provider authentication failed")
        if status_code == 404:
            return ModelNotFoundError("configured provider model was not found")
        if status_code is None:
            return InvariantModelError("model transport failed with an unexpected local error")
        return PermanentModelError("model provider rejected the request permanently")

    def _detached_error(self, error: ModelClientError) -> ModelClientError:
        return type(error)(redact_text(str(error), known_secrets=self._known_secrets))


def _schema_name(model_type: type[BaseModel]) -> str:
    candidate = _SCHEMA_NAME.sub("_", model_type.__name__).strip("_-")[:64]
    return candidate or "structured_output"


def _required_token_count(value: object, *names: str) -> int:
    for name in names:
        candidate = getattr(value, name, None)
        if isinstance(candidate, int) and not isinstance(candidate, bool) and candidate >= 0:
            return candidate
    raise InvariantModelError("provider response is missing valid token usage")


def _provider_cost(usage: object, response: object) -> float | None:
    candidate = getattr(usage, "cost", None)
    if candidate is None:
        candidate = getattr(response, "cost", None)
    if candidate is None:
        return None
    if isinstance(candidate, bool) or not isinstance(candidate, int | float):
        raise InvariantModelError("provider returned invalid cost data")
    cost = float(candidate)
    if not math.isfinite(cost) or cost < 0:
        raise InvariantModelError("provider returned invalid cost data")
    return cost


def _is_content_policy_error(error: Exception) -> bool:
    values = (
        getattr(error, "code", None),
        getattr(error, "type", None),
        getattr(error, "body", None),
    )
    text = " ".join(str(value).lower() for value in values if value is not None)
    return "content_policy" in text or "content filter" in text
