from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
from pathlib import Path
from typing import Protocol, TypeVar

from pydantic import BaseModel, ConfigDict, ValidationError

from ke_memory_demo.core.json import JsonObject, canonical_json
from ke_memory_demo.infra.llm import StructuredCompletion
from ke_memory_demo.infra.telemetry import TraceContext

from .models import JudgeResult, ProbeQuestion, QuestionAnswer, RubricJudgement


JUDGE_MODEL = "gpt-5.5"
JUDGE_MAX_OUTPUT_TOKENS = 2048
_PROMPT_PATH = Path(__file__).resolve().parents[3] / "prompts/judge/system.md"
ModelT = TypeVar("ModelT", bound=BaseModel)


class JudgeInvariantError(ValueError):
    """Judge configuration, input, or structured output violated the blind contract."""


class JudgeModelOutput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    rubric_items: tuple[RubricJudgement, ...]
    factual_error: bool
    unsupported_claim: bool
    abstention_correct: bool | None
    short_rationale: str


class ConfiguredJudgeClient(Protocol):
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


class JudgeService:
    def __init__(self, model: ConfiguredJudgeClient) -> None:
        if model.model_name != JUDGE_MODEL:
            raise JudgeInvariantError(f"Judge client must use {JUDGE_MODEL}")
        if model.max_output_tokens != JUDGE_MAX_OUTPUT_TOKENS:
            raise JudgeInvariantError(
                f"Judge client max output tokens must be {JUDGE_MAX_OUTPUT_TOKENS}"
            )
        self._model = model
        self._prompt = _read_prompt()
        self.prompt_sha256 = hashlib.sha256(self._prompt.encode("utf-8")).hexdigest()

    @property
    def model_name(self) -> str:
        return self._model.model_name

    def request_payload(
        self,
        question: ProbeQuestion,
        answer: QuestionAnswer,
    ) -> JsonObject:
        validated_question = ProbeQuestion.model_validate(question)
        validated_answer = QuestionAnswer.model_validate(answer)
        if validated_answer.question_id != validated_question.id:
            raise JudgeInvariantError("Judge question and candidate answer IDs do not match")
        if validated_answer.conversation_id != validated_question.conversation_id:
            raise JudgeInvariantError("Judge question and candidate Conversation IDs do not match")
        if not validated_question.rubric:
            raise JudgeInvariantError("Judge rubric must not be empty")
        return {
            "question": validated_question.question,
            "ideal_answer": validated_question.ideal_answer,
            "rubric": list(validated_question.rubric),
            "candidate_answer": validated_answer.answer,
        }

    async def judge(
        self,
        question: ProbeQuestion,
        answer: QuestionAnswer,
    ) -> JudgeResult:
        payload = self.request_payload(question, answer)
        completion = await self._model.complete_with_usage(
            JudgeModelOutput,
            (
                {"role": "system", "content": self._prompt},
                {"role": "user", "content": canonical_json(payload).decode("utf-8")},
            ),
            TraceContext(
                operation="independent-judge",
                metadata={
                    "question_id": question.id,
                    "model": self.model_name,
                    "prompt_sha256": self.prompt_sha256,
                    "rubric_count": len(question.rubric),
                },
            ),
        )
        output = _validated_output(completion.value)
        returned_rubric = tuple(item.rubric for item in output.rubric_items)
        if returned_rubric != question.rubric:
            raise JudgeInvariantError("Judge rubric text and order must match the offered rubric")
        satisfied = sum(item.satisfied for item in output.rubric_items)
        return JudgeResult(
            question_id=question.id,
            rubric_items=output.rubric_items,
            answer_score=satisfied / len(question.rubric),
            factual_error=output.factual_error,
            unsupported_claim=output.unsupported_claim,
            abstention_correct=output.abstention_correct,
            short_rationale=output.short_rationale,
            usage=completion.usage,
        )


def _read_prompt() -> str:
    try:
        return _PROMPT_PATH.read_text(encoding="utf-8")
    except OSError as error:
        raise JudgeInvariantError("required Judge prompt is unavailable") from error


def _validated_output(value: object) -> JudgeModelOutput:
    if not isinstance(value, BaseModel):
        raise JudgeInvariantError("Judge model did not return a validated record")
    try:
        return JudgeModelOutput.model_validate(value.model_dump(mode="python"))
    except ValidationError as error:
        raise JudgeInvariantError("Judge model output failed local schema validation") from error
