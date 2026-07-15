from __future__ import annotations

import hashlib
from enum import Enum
from typing import Annotated, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ke_memory_demo.core.json import JsonObject


NonEmptyString = Annotated[str, Field(min_length=1)]
NonNegativeInt = Annotated[int, Field(ge=0)]
Sha256Hex = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"


class ToolEventKind(str, Enum):
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"


class _ConversationRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class MessageSpan(_ConversationRecord):
    message_id: NonEmptyString
    start_char: NonNegativeInt
    end_char: NonNegativeInt
    text_hash: Sha256Hex

    @model_validator(mode="after")
    def _validate_non_empty_range(self) -> MessageSpan:
        if self.end_char <= self.start_char:
            raise ValueError("message span must be a non-empty [start_char, end_char) range")
        return self


class Message(_ConversationRecord):
    id: NonEmptyString
    role: MessageRole
    content: str
    source_order: NonNegativeInt
    source_metadata: JsonObject = Field(default_factory=dict)
    content_hash: Sha256Hex = ""

    @model_validator(mode="before")
    @classmethod
    def _compute_or_verify_content_hash(cls, data: object) -> object:
        return _content_record_with_hash(data)

    def validate_span(self, span: MessageSpan) -> None:
        if span.message_id != self.id:
            raise ValueError(f"span references a different message: {span.message_id}")
        if span.end_char > len(self.content):
            raise ValueError(
                f"span [{span.start_char}, {span.end_char}) is outside message {self.id}"
            )
        expected = _sha256_text(self.content[span.start_char : span.end_char])
        if span.text_hash != expected:
            raise ValueError(f"span text_hash does not match message {self.id}")


class ToolEvent(_ConversationRecord):
    id: NonEmptyString
    kind: ToolEventKind
    content: str
    source_order: NonNegativeInt
    source_metadata: JsonObject = Field(default_factory=dict)
    content_hash: Sha256Hex = ""

    @model_validator(mode="before")
    @classmethod
    def _compute_or_verify_content_hash(cls, data: object) -> object:
        return _content_record_with_hash(data)


class Exchange(_ConversationRecord):
    id: NonEmptyString
    session_id: NonEmptyString
    user: Message
    assistant: Message
    events: tuple[ToolEvent, ...] = ()
    global_ordinal: NonNegativeInt
    source_metadata: JsonObject = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_roles_and_order(self) -> Exchange:
        if self.user.role is not MessageRole.USER:
            raise ValueError("exchange user must have the user role")
        if self.assistant.role is not MessageRole.ASSISTANT:
            raise ValueError("exchange assistant must have the assistant role")

        ordered_records: tuple[Message | ToolEvent, ...] = (
            self.user,
            *self.events,
            self.assistant,
        )
        source_orders = tuple(record.source_order for record in ordered_records)
        if any(left >= right for left, right in zip(source_orders, source_orders[1:])):
            raise ValueError("exchange records must have strict source order")

        record_ids = tuple(record.id for record in ordered_records)
        _reject_duplicates(record_ids, "exchange record")
        return self


class Session(_ConversationRecord):
    id: NonEmptyString
    conversation_id: NonEmptyString
    exchanges: tuple[Exchange, ...] = ()
    source_metadata: JsonObject = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_exchanges(self) -> Session:
        for exchange in self.exchanges:
            if exchange.session_id != self.id:
                raise ValueError(
                    f"exchange {exchange.id} belongs to session {exchange.session_id}, not {self.id}"
                )
        ordinals = tuple(exchange.global_ordinal for exchange in self.exchanges)
        if any(left >= right for left, right in zip(ordinals, ordinals[1:])):
            raise ValueError("session exchanges must have strict ordinal order")
        _reject_duplicates(tuple(exchange.id for exchange in self.exchanges), "exchange")
        return self


class Conversation(_ConversationRecord):
    id: NonEmptyString
    sessions: tuple[Session, ...] = ()
    probing_questions: tuple[JsonObject, ...] = ()
    source_metadata: JsonObject = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_sessions(self) -> Conversation:
        for session in self.sessions:
            if session.conversation_id != self.id:
                raise ValueError(
                    f"session {session.id} belongs to conversation "
                    f"{session.conversation_id}, not {self.id}"
                )
        _reject_duplicates(tuple(session.id for session in self.sessions), "session")
        return self


def _sha256_text(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _content_record_with_hash(data: object) -> object:
    if not isinstance(data, dict):
        return data
    mapping = cast(dict[str, object], data)
    content = mapping.get("content")
    if not isinstance(content, str):
        return mapping

    expected = _sha256_text(content)
    supplied = mapping.get("content_hash")
    if supplied is None:
        return {**mapping, "content_hash": expected}
    if supplied != expected:
        raise ValueError("content_hash does not match the exact UTF-8 source content")
    return mapping


def _reject_duplicates(values: tuple[str, ...], label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"duplicate {label} IDs are not allowed")
