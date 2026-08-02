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
from ke_memory_demo.request_contract import (
    RequestBudget,
    RequestBuildError,
    answer_arm_budget,
    build_answer_request,
    enforce_budget,
)
from ke_memory_demo.retrieval.evidence_payload import serialize_evidence_payload
from ke_memory_demo.retrieval.tokens import TokenCounter


ANSWER_MODEL = "deepseek-v4-flash"
# The answer client runs with thinking disabled, so this budget covers visible output
# only. Measured on 2026-08-02, a multi-hop supersession answer used 193 completion
# tokens with no reasoning tokens, so this leaves ample headroom and a truncated
# answer signals a real defect rather than an under-provisioned budget.
ANSWER_MAX_OUTPUT_TOKENS = 1024
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
        budget: RequestBudget | None = None,
    ) -> None:
        """Take the budget explicitly.

        An 8192-token module constant used to live here, unreachable from any contract, while the
        freeze published a different number. The budget is now injected and carries its arm
        identity, so a mismatch between contract and execution is visible rather than latent.
        """
        if model.model_name != ANSWER_MODEL:
            raise AnswerInvariantError(f"answer client must use {ANSWER_MODEL}")
        if model.max_output_tokens != ANSWER_MAX_OUTPUT_TOKENS:
            raise AnswerInvariantError(
                f"answer client max output tokens must be {ANSWER_MAX_OUTPUT_TOKENS}"
            )
        self._model = model
        self._token_counter = token_counter
        self._budget = budget if budget is not None else answer_arm_budget()
        self._prompt = _read_prompt()
        self.prompt_sha256 = hashlib.sha256(self._prompt.encode("utf-8")).hexdigest()

    @property
    def model_name(self) -> str:
        return self._model.model_name

    @property
    def budget(self) -> RequestBudget:
        """The budget in force, so a caller and an audit can read the same number."""
        return self._budget

    def request_payload(
        self,
        question: str,
        evidence: Sequence[Evidence],
    ) -> JsonObject:
        """Build the request through the shared contract.

        Delegating rather than constructing the dict here is what makes the frozen contract
        binding: four rounds of contract work hashed a shape this method did not send, and the
        hashes constrained nothing as a result.
        """
        ordered, _evidence_tokens = self._prepare_evidence(question, evidence)
        return build_answer_request(question, ordered)

    async def answer(
        self,
        question: str,
        evidence: Sequence[Evidence],
    ) -> AnswerResult:
        ordered, evidence_tokens = self._prepare_evidence(question, evidence)
        evidence_ids = tuple(item.evidence_id for item in ordered)
        payload = self.request_payload(question, ordered)
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

    def _prepare_evidence(
        self,
        question: str,
        evidence: Sequence[Evidence],
    ) -> tuple[tuple[Evidence, ...], int]:
        if not question.strip():
            raise AnswerInvariantError("question must not be empty")
        packed = tuple(Evidence.model_validate(item.model_dump(mode="python")) for item in evidence)
        evidence_ids = tuple(item.evidence_id for item in packed)
        if len(evidence_ids) != len(set(evidence_ids)):
            raise AnswerInvariantError("packed evidence IDs must be unique")
        ordered = tuple(sorted(packed, key=lambda item: (item.rank, item.evidence_id)))
        evidence_tokens = self._count_evidence_tokens(ordered)
        # Enforcement goes through the shared contract, over the whole serialized request rather
        # than an evidence-only count. A private threshold here would be a second, unbound
        # policy that no freeze could constrain.
        try:
            enforce_budget(question, ordered, self._budget)
        except RequestBuildError as error:
            raise AnswerInvariantError(str(error)) from error
        return ordered, evidence_tokens

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
