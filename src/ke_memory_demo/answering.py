from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
from pathlib import Path
from typing import Annotated, Protocol, TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from ke_memory_demo.core.json import JsonObject, canonical_json
from ke_memory_demo.domain import Evidence
from ke_memory_demo.infra.llm import StructuredCompletion
from ke_memory_demo.infra.telemetry import TraceContext, UsageRecord
from ke_memory_demo.retrieval.evidence_payload import (
    model_evidence_payload,
    serialize_evidence_payload,
)
from ke_memory_demo.retrieval.tokens import TokenCounter


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


class ConfiguredAnswerClient(Protocol):
    @property
    def model_name(self) -> str: ...

    @property
    def max_output_tokens(self) -> int: ...

    async def complete_with_usage(
        self,
        model_type: type[ModelT],
        messages: Sequence[Mapping[str, object]],
        trace_context: TraceContext | Mapping[str, object],
    ) -> StructuredCompletion[ModelT]: ...


class AnswerService:
    def __init__(
        self,
        model: ConfiguredAnswerClient,
        *,
        token_counter: TokenCounter,
    ) -> None:
        if model.model_name != ANSWER_MODEL:
            raise AnswerInvariantError(f"answer client must use {ANSWER_MODEL}")
        if model.max_output_tokens != ANSWER_MAX_OUTPUT_TOKENS:
            raise AnswerInvariantError(
                f"answer client max output tokens must be {ANSWER_MAX_OUTPUT_TOKENS}"
            )
        self._model = model
        self._token_counter = token_counter
        self._prompt = _read_prompt()
        self.prompt_sha256 = hashlib.sha256(self._prompt.encode("utf-8")).hexdigest()

    async def answer(
        self,
        question: str,
        evidence: Sequence[Evidence],
    ) -> AnswerResult:
        if not question.strip():
            raise AnswerInvariantError("question must not be empty")
        packed = tuple(Evidence.model_validate(item.model_dump(mode="python")) for item in evidence)
        evidence_ids = tuple(item.evidence_id for item in packed)
        if len(evidence_ids) != len(set(evidence_ids)):
            raise AnswerInvariantError("packed evidence IDs must be unique")
        ordered = tuple(sorted(packed, key=lambda item: (item.rank, item.evidence_id)))
        evidence_tokens = self._count_evidence_tokens(ordered)
        if evidence_tokens > MAX_EVIDENCE_TOKENS:
            raise AnswerInvariantError(
                f"packed evidence exceeds the {MAX_EVIDENCE_TOKENS}-token hard limit"
            )
        payload: JsonObject = {
            "task": "answer_from_evidence",
            "question": question,
            "evidence": list(model_evidence_payload(ordered)),
        }
        messages = (
            {"role": "system", "content": self._prompt},
            {"role": "user", "content": canonical_json(payload).decode("utf-8")},
        )
        completion = await self._model.complete_with_usage(
            AnswerModelOutput,
            messages,
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
        output = _validated_output(completion.value)
        unoffered = sorted(set(output.citations).difference(evidence_ids))
        if unoffered:
            raise AnswerInvariantError(f"answer returned unoffered citation: {unoffered[0]}")
        return AnswerResult(
            answer=output.answer,
            citations=output.citations,
            usage=completion.usage,
        )

    def _count_evidence_tokens(self, evidence: Sequence[Evidence]) -> int:
        count = self._token_counter.count(serialize_evidence_payload(evidence))
        if isinstance(count, bool) or count < 0:
            raise AnswerInvariantError("token counter returned an invalid count")
        return count


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
