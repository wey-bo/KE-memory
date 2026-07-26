from __future__ import annotations

from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator


NonEmptyString = Annotated[str, Field(min_length=1)]
Score = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


class AdmissionStatus(str, Enum):
    ADMITTED = "admitted"
    CANDIDATE = "candidate"
    REJECTED = "rejected"


class MemoryKind(str, Enum):
    FACT = "fact"
    PREFERENCE = "preference"
    TASK = "task"
    STATE = "state"
    CONSTRAINT = "constraint"
    PROCEDURE = "procedure"
    OTHER = "other"


class SourceStatus(str, Enum):
    USER_REPORTED = "user_reported"
    AGENT_GENERATED = "agent_generated"
    TOOL_OBSERVED = "tool_observed"
    DERIVED = "derived"


class _OnlineRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class MemoryNamespace(_OnlineRecord):
    tenant_id: NonEmptyString
    user_id: NonEmptyString
    agent_id: NonEmptyString

    @field_validator("tenant_id", "user_id", "agent_id", mode="before")
    @classmethod
    def _normalize_segment(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        if not normalized:
            raise ValueError("namespace segment must not be blank")
        return normalized


class AdmissionAssessment(_OnlineRecord):
    status: AdmissionStatus
    memory_kind: MemoryKind
    source_status: SourceStatus
    extraction_confidence: Score
    epistemic_trust: Score
    memory_utility: Score
    reasons: tuple[NonEmptyString, ...]
