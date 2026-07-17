from __future__ import annotations

from enum import StrEnum
from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict

from ke_memory_demo.core.json import JsonObject


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
