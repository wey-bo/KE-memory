"""Strict data contracts for the AMR single-sentence pilot."""

from __future__ import annotations

from datetime import datetime
import hashlib
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator


SHA256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
SampleId = Annotated[str, Field(pattern=r"^AMR-S[0-9]{3}$")]
Route = Literal["A", "B", "C"]
Phenomenon = Literal[
    "event_roles",
    "time_quantity_condition",
    "negation_modality_intent",
    "causality_comparison_multiclause",
]


class PilotModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SourceCoordinate(PilotModel):
    dataset: Annotated[str, Field(min_length=1)]
    source_url: HttpUrl
    source_revision: Annotated[str, Field(min_length=1)]
    source_artifact_sha256: SHA256
    record_locator: Annotated[str, Field(min_length=1)]
    message_locator: Annotated[str, Field(min_length=1)]
    speaker: Literal["user", "agent"]


class SentenceSample(PilotModel):
    sample_id: SampleId
    candidate_id: Annotated[str, Field(min_length=1)]
    text: Annotated[str, Field(min_length=1)]
    language: Literal["en"]
    phenomenon: Phenomenon
    text_sha256: SHA256
    source_record_id: Annotated[str, Field(pattern=r"^SRC-[0-9]{3}$")]
    sentence_occurrence_index: Annotated[int, Field(ge=0)]
    source: SourceCoordinate

    @model_validator(mode="after")
    def require_matching_text_hash(self) -> SentenceSample:
        expected = hashlib.sha256(self.text.encode("utf-8")).hexdigest()
        if self.text_sha256 != expected:
            raise ValueError("text_sha256 does not match text")
        return self


class SourceRecord(PilotModel):
    source_record_id: Annotated[str, Field(pattern=r"^SRC-[0-9]{3}$")]
    candidate_id: Annotated[str, Field(min_length=1)]
    text: Annotated[str, Field(min_length=1)]
    text_sha256: SHA256
    source: SourceCoordinate

    @model_validator(mode="after")
    def require_matching_text_hash(self) -> SourceRecord:
        expected = hashlib.sha256(self.text.encode("utf-8")).hexdigest()
        if self.text_sha256 != expected:
            raise ValueError("text_sha256 does not match source record text")
        return self


class GoldItem(PilotModel):
    item_id: Annotated[str, Field(pattern=r"^AMR-S[0-9]{3}-G[0-9]{3}$")]
    statement: Annotated[str, Field(min_length=1)]
    importance: Literal["critical", "ordinary"]
    weight: Annotated[float, Field(gt=0)]
    evidence_quotes: Annotated[list[Annotated[str, Field(min_length=1)]], Field(min_length=1)]
    category: Literal[
        "event",
        "state",
        "role",
        "time",
        "quantity",
        "condition",
        "polarity",
        "modality",
        "causality",
        "comparison",
        "other",
    ]


class SemanticChecklist(PilotModel):
    sample_id: SampleId
    source_text_sha256: SHA256
    items: Annotated[list[GoldItem], Field(min_length=1)]
    forbidden_inferences: Annotated[list[Annotated[str, Field(min_length=1)]], Field(min_length=1)]

    @model_validator(mode="after")
    def validate_item_namespace(self) -> SemanticChecklist:
        item_ids = [item.item_id for item in self.items]
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("gold item IDs must be unique")
        prefix = f"{self.sample_id}-G"
        if any(not item_id.startswith(prefix) for item_id in item_ids):
            raise ValueError("gold item ID must use its sample namespace")
        return self


class GoldDraft(PilotModel):
    schema_version: Literal["amr-pilot-gold-draft-v1"]
    status: Literal["draft"]
    checklists: Annotated[list[SemanticChecklist], Field(min_length=1)]


class GoldApproval(PilotModel):
    schema_version: Literal["amr-pilot-gold-approval-v1"]
    status: Literal["approved"]
    gold_sha256: SHA256
    approved_by: Literal["user"]
    approved_at: datetime

    @field_validator("approved_at")
    @classmethod
    def require_approval_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("approved_at must include a timezone")
        return value


class MeasuredUsage(PilotModel):
    status: Literal["measured"]
    input_tokens: Annotated[int, Field(ge=0)]
    output_tokens: Annotated[int, Field(ge=0)]
    cost_usd: Annotated[float, Field(ge=0)]

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class UnavailableUsage(PilotModel):
    status: Literal["unavailable"]
    reason: Annotated[str, Field(min_length=1)]


Usage = Annotated[MeasuredUsage | UnavailableUsage, Field(discriminator="status")]


class AttemptSidecar(PilotModel):
    sample_id: SampleId
    route: Route
    run_id: Annotated[str, Field(pattern=r"^run-[0-9]{8}T[0-9]{6}Z$")]
    attempt: Literal[1, 2]
    previous_attempt_sha256: SHA256 | None
    model_id: Annotated[str, Field(min_length=1)]
    prompt_sha256: SHA256
    raw_output_sha256: SHA256
    started_at: datetime
    finished_at: datetime
    latency_ms: Annotated[int, Field(ge=0)] | None
    latency_status: Literal["measured", "unavailable"] = "measured"
    usage: Usage
    parse_status: Literal["valid", "invalid", "not_applicable"]
    parse_errors: list[Annotated[str, Field(min_length=1)]] = Field(default_factory=list)
    representation_gaps: list[Annotated[str, Field(min_length=1)]] = Field(default_factory=list)

    @field_validator("started_at", "finished_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timestamp must include a timezone")
        return value

    @model_validator(mode="after")
    def validate_attempt_chain(self) -> AttemptSidecar:
        if self.attempt == 1 and self.previous_attempt_sha256 is not None:
            raise ValueError("previous_attempt_sha256 must be null for attempt 1")
        if self.attempt == 2 and self.previous_attempt_sha256 is None:
            raise ValueError("previous_attempt_sha256 is required for attempt 2")
        if self.finished_at < self.started_at:
            raise ValueError("finished_at must not precede started_at")
        if self.latency_status == "measured" and self.latency_ms is None:
            raise ValueError("latency_ms is required when latency_status is measured")
        if self.latency_status == "unavailable" and self.latency_ms is not None:
            raise ValueError("latency_ms must be null when latency_status is unavailable")
        return self
