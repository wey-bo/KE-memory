from __future__ import annotations

from enum import StrEnum
from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ke_memory_demo.core.json import JsonObject
from ke_memory_demo.domain import Evidence
from ke_memory_demo.infra.telemetry import UsageRecord
from ke_memory_demo.retrieval import RetrievalTrace


class QuestionCategory(StrEnum):
    ABSTENTION = "abstention"
    CONTRADICTION_RESOLUTION = "contradiction_resolution"
    EVENT_ORDERING = "event_ordering"
    INFORMATION_EXTRACTION = "information_extraction"
    INSTRUCTION_FOLLOWING = "instruction_following"
    KNOWLEDGE_UPDATE = "knowledge_update"
    MULTI_SESSION_REASONING = "multi_session_reasoning"
    PREFERENCE_FOLLOWING = "preference_following"
    SUMMARIZATION = "summarization"
    TEMPORAL_REASONING = "temporal_reasoning"


OriginalAnswerField: TypeAlias = Literal[
    "ideal_answer",
    "ideal_response",
    "answer",
    "ideal_summary",
    "expected_compliance",
]


class ProbeQuestion(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    conversation_id: str
    category: QuestionCategory
    ordinal: int
    question: str
    ideal_answer: str
    original_answer_field: OriginalAnswerField
    rubric: tuple[str, ...]
    raw_metadata: JsonObject


class GoldSourceStatus(StrEnum):
    MAPPED = "mapped"
    UNMAPPABLE = "unmappable"


class GoldSourceMapping(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    question_id: str
    status: GoldSourceStatus
    source_numbers: tuple[int, ...] = ()
    source_exchange_ids: tuple[str, ...] = ()
    matched_paths: tuple[str, ...] = ()
    exclusion_reason: str | None = None


class RubricJudgement(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    rubric: str
    satisfied: bool
    reason: str


class JudgeResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    question_id: str
    rubric_items: tuple[RubricJudgement, ...]
    answer_score: float = Field(ge=0, le=1, allow_inf_nan=False)
    factual_error: bool
    unsupported_claim: bool
    abstention_correct: bool | None
    short_rationale: str
    usage: UsageRecord

    @model_validator(mode="after")
    def _score_is_derived(self) -> JudgeResult:
        if not self.rubric_items:
            raise ValueError("Judge result requires at least one rubric item")
        expected = sum(item.satisfied for item in self.rubric_items) / len(self.rubric_items)
        if self.answer_score != expected:
            raise ValueError("Judge answer score must be derived from rubric judgements")
        return self


class EvaluationStatus(StrEnum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"


class QuestionAnswer(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    question_id: str
    conversation_id: str
    evidence: tuple[Evidence, ...]
    answer: str
    citations: tuple[str, ...]
    retrieval_trace: RetrievalTrace
    usage: UsageRecord

    @model_validator(mode="after")
    def _validate_evidence_and_citations(self) -> QuestionAnswer:
        evidence_ids = tuple(item.evidence_id for item in self.evidence)
        if self.retrieval_trace.evidence_ids != evidence_ids:
            raise ValueError("question answer evidence does not match its retrieval trace")
        if len(self.citations) != len(set(self.citations)):
            raise ValueError("question answer citations must be duplicate-free")
        unoffered = set(self.citations).difference(evidence_ids)
        if unoffered:
            raise ValueError("question answer citation was not offered as evidence")
        return self


class EvaluationFailure(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    question_id: str
    stage: Literal["retrieve_answer", "judge"]
    error_type: str
    message: str


class QuestionExecution(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    answer: QuestionAnswer
    judgement: JudgeResult | None
    failure: EvaluationFailure | None

    @model_validator(mode="after")
    def _judge_outcome(self) -> QuestionExecution:
        if (self.judgement is None) == (self.failure is None):
            raise ValueError("question execution requires exactly one Judge outcome")
        return self


class EvaluationRun(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    manifest_hash: str
    status: EvaluationStatus
    answers: tuple[QuestionAnswer, ...]
    judgements: tuple[JudgeResult, ...]
    failures: tuple[EvaluationFailure, ...]

    @model_validator(mode="after")
    def _validate_outcome_ids(self) -> EvaluationRun:
        answer_ids = tuple(item.question_id for item in self.answers)
        judgement_ids = tuple(item.question_id for item in self.judgements)
        if len(answer_ids) != len(set(answer_ids)):
            raise ValueError("evaluation answers contain duplicate question IDs")
        if len(judgement_ids) != len(set(judgement_ids)):
            raise ValueError("evaluation Judgements contain duplicate question IDs")
        if self.status is EvaluationStatus.COMPLETE and (
            self.failures or answer_ids != judgement_ids
        ):
            raise ValueError("complete evaluation requires matching answers and Judgements")
        return self
