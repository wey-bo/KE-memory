from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
from pathlib import Path
from typing import Annotated, Protocol, TypeVar, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from ke_memory_demo.core.json import JsonObject, JsonValue, canonical_json
from ke_memory_demo.domain import Evidence
from ke_memory_demo.infra.telemetry import TraceContext, UsageRecord


ANSWER_MODEL = "gpt-5.4"
ANSWER_MAX_OUTPUT_TOKENS = 1024
MAX_EVIDENCE_TOKENS = 8192
_PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts/answer/system.md"

NonEmptyString = Annotated[str, Field(min_length=1)]
ModelT = TypeVar("ModelT", bound=BaseModel)


class AnswerInvariantError(ValueError):
    """Common answering inputs, outputs, or fixed configuration are invalid."""


class _AnswerRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class AnswerModelOutput(_AnswerRecord):
    answer: NonEmptyString
    citations: tuple[NonEmptyString, ...] = ()

    @model_validator(mode="after")
    def _validate_citations(self) -> AnswerModelOutput:
        if len(self.citations) != len(set(self.citations)):
            raise ValueError("duplicate answer citations are not allowed")
        return self


class AnswerResult(_AnswerRecord):
    answer: NonEmptyString
    citations: tuple[NonEmptyString, ...] = ()
    usage: UsageRecord


class AnswerUsageSource(Protocol):
    @property
    def usage_records(self) -> tuple[UsageRecord, ...]: ...


class ConfiguredAnswerClient(Protocol):
    @property
    def model_name(self) -> str: ...

    @property
    def max_output_tokens(self) -> int: ...

    async def complete(
        self,
        model_type: type[ModelT],
        messages: Sequence[Mapping[str, object]],
        trace_context: TraceContext | Mapping[str, object],
    ) -> ModelT: ...


class AnswerService:
    def __init__(
        self,
        model: ConfiguredAnswerClient,
        usage_source: AnswerUsageSource,
    ) -> None:
        if model.model_name != ANSWER_MODEL:
            raise AnswerInvariantError(f"answer client must use {ANSWER_MODEL}")
        if model.max_output_tokens != ANSWER_MAX_OUTPUT_TOKENS:
            raise AnswerInvariantError(
                f"answer client max output tokens must be {ANSWER_MAX_OUTPUT_TOKENS}"
            )
        self._model = model
        self._usage_source = usage_source
        self._prompt = _read_prompt()
        self.prompt_sha256 = hashlib.sha256(self._prompt.encode("utf-8")).hexdigest()

    async def answer(
        self,
        question: str,
        evidence: Sequence[Evidence],
    ) -> AnswerResult:
        if not question.strip():
            raise AnswerInvariantError("question must not be empty")
        packed = tuple(
            Evidence.model_validate(item.model_dump(mode="python")) for item in evidence
        )
        evidence_ids = tuple(item.evidence_id for item in packed)
        if len(evidence_ids) != len(set(evidence_ids)):
            raise AnswerInvariantError("packed evidence IDs must be unique")
        evidence_tokens = sum(item.token_count for item in packed)
        if evidence_tokens > MAX_EVIDENCE_TOKENS:
            raise AnswerInvariantError(
                f"packed evidence exceeds the {MAX_EVIDENCE_TOKENS}-token hard limit"
            )
        ordered = tuple(sorted(packed, key=lambda item: (item.rank, item.evidence_id)))
        payload: JsonObject = {
            "task": "answer_from_evidence",
            "question": question,
            "evidence": [cast(JsonValue, item.model_dump(mode="json")) for item in ordered],
        }
        usage_start = len(self._usage_source.usage_records)
        response = await self._model.complete(
            AnswerModelOutput,
            (
                {"role": "system", "content": self._prompt},
                {"role": "user", "content": canonical_json(payload).decode("utf-8")},
            ),
            TraceContext(
                operation="common-answer",
                metadata={
                    "model": ANSWER_MODEL,
                    "max_output_tokens": ANSWER_MAX_OUTPUT_TOKENS,
                    "prompt_sha256": self.prompt_sha256,
                    "question_sha256": hashlib.sha256(question.encode("utf-8")).hexdigest(),
                    "evidence_count": len(ordered),
                    "evidence_tokens": evidence_tokens,
                },
            ),
        )
        output = _validated_output(response)
        unoffered = sorted(set(output.citations).difference(evidence_ids))
        if unoffered:
            raise AnswerInvariantError(f"answer returned unoffered citation: {unoffered[0]}")
        new_usage = self._usage_source.usage_records[usage_start:]
        if not new_usage:
            raise AnswerInvariantError("answer model call produced no usage record")
        return AnswerResult(
            answer=output.answer,
            citations=output.citations,
            usage=_aggregate_usage(new_usage),
        )


def _read_prompt() -> str:
    try:
        return _PROMPT_PATH.read_text(encoding="utf-8")
    except OSError as error:
        raise AnswerInvariantError("required common answer prompt is unavailable") from error


def _validated_output(value: object) -> AnswerModelOutput:
    if not isinstance(value, BaseModel):
        raise AnswerInvariantError("answer model did not return a validated record")
    try:
        return AnswerModelOutput.model_validate(value.model_dump(mode="python"))
    except ValidationError as error:
        raise AnswerInvariantError("answer model output failed local schema validation") from error


def _aggregate_usage(records: Sequence[UsageRecord]) -> UsageRecord:
    invalid_model = next((item.model for item in records if item.model != ANSWER_MODEL), None)
    if invalid_model is not None:
        raise AnswerInvariantError(f"answer usage reported unexpected model: {invalid_model}")
    costs = tuple(item.provider_cost for item in records if item.provider_cost is not None)
    return UsageRecord(
        request_id=records[-1].request_id,
        model=ANSWER_MODEL,
        latency_seconds=sum(item.latency_seconds for item in records),
        input_tokens=sum(item.input_tokens for item in records),
        output_tokens=sum(item.output_tokens for item in records),
        total_tokens=sum(item.total_tokens for item in records),
        provider_cost=sum(costs) if costs else None,
    )
