from __future__ import annotations

from datetime import date
from enum import StrEnum
import hashlib
from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ke_memory_demo.core.json import JsonObject
from ke_memory_demo.domain import CoverageEntry, Evidence, KnowledgeEquation
from ke_memory_demo.infra.telemetry import UsageRecord
from ke_memory_demo.retrieval import RetrievalTrace


NonEmptyString = Annotated[str, Field(min_length=1)]
Sha256Hex = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
GitSha = Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
NonNegativeInt = Annotated[int, Field(ge=0)]
FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]


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

    manifest_hash: Sha256Hex
    expected_question_ids: tuple[NonEmptyString, ...]
    question_manifest_sha256: Sha256Hex
    ke_ready_snapshot_id: GitSha
    status: EvaluationStatus
    answers: tuple[QuestionAnswer, ...]
    judgements: tuple[JudgeResult, ...]
    failures: tuple[EvaluationFailure, ...]

    @model_validator(mode="after")
    def _validate_outcome_ids(self) -> EvaluationRun:
        expected_ids = self.expected_question_ids
        if not expected_ids:
            raise ValueError("expected question IDs must be nonempty")
        if expected_ids != tuple(sorted(expected_ids)):
            raise ValueError("expected question IDs must be sorted")
        if len(expected_ids) != len(set(expected_ids)):
            raise ValueError("expected question IDs must be unique")

        answer_ids = tuple(item.question_id for item in self.answers)
        judgement_ids = tuple(item.question_id for item in self.judgements)
        failure_ids = tuple(item.question_id for item in self.failures)
        if len(answer_ids) != len(set(answer_ids)):
            raise ValueError("evaluation answers contain duplicate question IDs")
        if len(judgement_ids) != len(set(judgement_ids)):
            raise ValueError("evaluation Judgements contain duplicate question IDs")
        if len(failure_ids) != len(set(failure_ids)):
            raise ValueError("evaluation failures contain duplicate question IDs")
        expected_set = set(expected_ids)
        for label, identifiers in (
            ("answers", answer_ids),
            ("Judgements", judgement_ids),
            ("failures", failure_ids),
        ):
            unknown = sorted(set(identifiers).difference(expected_set))
            if unknown:
                raise ValueError(f"evaluation {label} contain unknown question ID: {unknown[0]}")
        if self.status is EvaluationStatus.COMPLETE:
            if self.failures or answer_ids != expected_ids or judgement_ids != expected_ids:
                raise ValueError(
                    "complete evaluation requires the exact expected answers and Judgements"
                )
        return self


BaselineStatus: TypeAlias = Literal[
    "public_result",
    "not_reproduced",
    "not_found",
    "not_directly_comparable",
]


class BaselinePublicResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    system: Literal["mem0", "graphiti", "hindsight", "mempalace"]
    source_url: str
    source_commit: GitSha
    retrieved_on: date
    dataset: str
    split: str
    metric: str
    score: FiniteFloat | None = None
    statuses: tuple[BaselineStatus, ...]
    vendor_self_report: bool
    reproduction_artifacts: str
    notes: str

    @model_validator(mode="after")
    def _validate_public_record(self) -> BaselinePublicResult:
        if not self.source_url.startswith("https://"):
            raise ValueError("public baseline source URL must use HTTPS")
        if not self.statuses or len(self.statuses) != len(set(self.statuses)):
            raise ValueError("public baseline statuses must be nonempty and duplicate-free")
        if "not_found" in self.statuses and self.score is not None:
            raise ValueError("a not-found public baseline record cannot carry a score")
        if self.score is not None and "public_result" not in self.statuses:
            raise ValueError("a scored public baseline record must be marked public_result")
        if "not_found" not in self.statuses and "not_reproduced" not in self.statuses:
            raise ValueError("public baseline claims must remain explicitly not reproduced")
        return self


class QuestionMetrics(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    question_id: str
    conversation_id: str
    category: QuestionCategory
    answer_score: FiniteFloat
    satisfied_rubrics: NonNegativeInt
    rubric_count: NonNegativeInt
    factual_error: bool
    unsupported_claim: bool
    abstention_correct: bool | None
    source_recall: FiniteFloat | None
    complete_evidence: bool | None
    citation_valid: bool
    citation_traceable: bool
    source_session_count: NonNegativeInt
    used_aggregate: bool
    evidence_tokens: NonNegativeInt
    work_usage: UsageRecord
    judge_usage: UsageRecord


class AggregateMetrics(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    scope: str
    question_count: NonNegativeInt
    completed_question_count: NonNegativeInt
    scored_question_count: NonNegativeInt
    answer_score_sum: FiniteFloat
    answer_score_mean: FiniteFloat | None
    mapped_source_count: NonNegativeInt
    source_recall_sum: FiniteFloat
    source_recall_mean: FiniteFloat | None
    complete_evidence_count: NonNegativeInt
    citation_valid_count: NonNegativeInt
    citation_traceable_count: NonNegativeInt
    factual_error_count: NonNegativeInt
    unsupported_claim_count: NonNegativeInt

    @model_validator(mode="after")
    def _validate_completeness(self) -> AggregateMetrics:
        if not (self.scored_question_count <= self.completed_question_count <= self.question_count):
            raise ValueError("aggregate scored/completed counts exceed the expected denominator")
        if self.answer_score_mean is not None and (
            self.question_count == 0 or self.scored_question_count != self.question_count
        ):
            raise ValueError("aggregate answer mean requires the full expected denominator")
        return self


class OperationUsageMetrics(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    operation: str
    call_count: NonNegativeInt
    input_tokens: NonNegativeInt
    output_tokens: NonNegativeInt
    latency_seconds: FiniteFloat
    provider_cost: FiniteFloat | None


class TurnKEAuditCase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    audit_kind: Literal[
        "conversation_first",
        "tool_event",
        "unresolved",
        "lifecycle",
        "cross_session",
    ]
    conversation_id: str
    exchange_ids: tuple[str, ...]
    raw_records: tuple[JsonObject, ...]
    coverage: tuple[CoverageEntry, ...]
    knowledge_equations: tuple[KnowledgeEquation, ...]
    aggregate_ids: tuple[str, ...] = ()


class ReportDocument(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: Literal["report.md", "question_results.csv", "metrics.json"]
    media_type: str
    sha256: Sha256Hex
    content: str

    @model_validator(mode="after")
    def _validate_content_hash(self) -> ReportDocument:
        expected = hashlib.sha256(self.content.encode("utf-8")).hexdigest()
        if self.sha256 != expected:
            raise ValueError("report document SHA-256 does not match its UTF-8 content")
        return self
