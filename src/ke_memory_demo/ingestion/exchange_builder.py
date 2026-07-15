from __future__ import annotations

from collections.abc import Iterable
from typing import Annotated, cast

from pydantic import BaseModel, ConfigDict, Field

from ke_memory_demo.core.ids import content_id
from ke_memory_demo.core.json import JsonObject
from ke_memory_demo.domain.conversation import (
    Exchange,
    Message,
    MessageRole,
    ToolEvent,
    ToolEventKind,
)


RawSourceId = Annotated[int, Field(ge=0)] | Annotated[str, Field(min_length=1)]
OptionalNonEmptyString = Annotated[str, Field(min_length=1)] | None
OptionalNonNegativeInt = Annotated[int, Field(ge=0)] | None
OptionalPositiveInt = Annotated[int, Field(gt=0)] | None
Sha256Hex = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class IngestionInvariantError(RuntimeError):
    """Raised when ordered source records cannot form valid exchanges."""


class SourceMessage(BaseModel):
    """Exact ingestion-only representation of one ordered source record."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    id: RawSourceId
    role: Annotated[str, Field(min_length=1)]
    content: str
    session_id: OptionalNonEmptyString = None
    archive_sha256: Sha256Hex | None = None
    beam_directory_id: OptionalPositiveInt = None
    topic_id: RawSourceId | None = None
    batch_number: OptionalPositiveInt = None
    turn_group_index: OptionalNonNegativeInt = None
    index: RawSourceId | None = None
    question_type: OptionalNonEmptyString = None
    time_anchor: OptionalNonEmptyString = None
    source_global_ordinal: OptionalNonNegativeInt = None


def build_exchanges(messages: Iterable[SourceMessage]) -> list[Exchange]:
    """Pair an ordered source iterable with one state-machine pass."""
    exchanges: list[Exchange] = []
    seen_source_ids: set[tuple[str, int | str]] = set()
    previous_ordinal: int | None = None
    default_session_id: str | None = None

    open_source_records: list[tuple[SourceMessage, int]] = []
    open_user: Message | None = None
    open_events: list[ToolEvent] = []
    open_session_id: str | None = None

    for source in messages:
        source_id_key = _source_id_key(source.id)
        if source_id_key in seen_source_ids:
            raise IngestionInvariantError(f"duplicate source ID: {source.id!r}")
        seen_source_ids.add(source_id_key)

        ordinal = _resolve_ordinal(source, previous_ordinal)
        previous_ordinal = ordinal
        ordered_payload = _ordered_source_payload(source, ordinal)
        session_id = source.session_id
        if session_id is None:
            if default_session_id is None:
                default_session_id = content_id("session", ordered_payload)
            session_id = default_session_id

        role = source.role
        if role == MessageRole.USER.value:
            if open_user is not None:
                raise IngestionInvariantError(
                    f"consecutive user record {source.id!r} before closing the current exchange"
                )
            open_user = _message_from_source(source, ordinal, MessageRole.USER)
            open_events = []
            open_source_records = [(source, ordinal)]
            open_session_id = session_id
            continue

        if role not in {
            MessageRole.ASSISTANT.value,
            ToolEventKind.TOOL_CALL.value,
            ToolEventKind.TOOL_RESULT.value,
        }:
            raise IngestionInvariantError(f"unsupported role {role!r} for source ID {source.id!r}")

        if open_user is None or open_session_id is None:
            label = "assistant" if role == MessageRole.ASSISTANT.value else "tool event"
            raise IngestionInvariantError(f"orphan {label} at source ID {source.id!r}")
        if session_id != open_session_id:
            raise IngestionInvariantError(
                "all records in an exchange must share the same session: "
                f"expected {open_session_id!r}, got {session_id!r}"
            )

        if role in {ToolEventKind.TOOL_CALL.value, ToolEventKind.TOOL_RESULT.value}:
            kind = ToolEventKind(role)
            open_events.append(_tool_event_from_source(source, ordinal, kind))
            open_source_records.append((source, ordinal))
            continue

        assistant = _message_from_source(source, ordinal, MessageRole.ASSISTANT)
        exchange_sources = [*open_source_records, (source, ordinal)]
        exchanges.append(
            Exchange(
                id=_exchange_id(exchange_sources),
                session_id=open_session_id,
                user=open_user,
                events=tuple(open_events),
                assistant=assistant,
                global_ordinal=open_source_records[0][1],
                source_metadata=_exchange_metadata(exchange_sources),
            )
        )
        open_source_records = []
        open_user = None
        open_events = []
        open_session_id = None

    if open_user is not None:
        raise IngestionInvariantError(
            f"unclosed exchange starting at source ID {open_source_records[0][0].id!r}"
        )
    return exchanges


def _source_id_key(source_id: int | str) -> tuple[str, int | str]:
    return ("integer" if isinstance(source_id, int) else "string", source_id)


def _resolve_ordinal(source: SourceMessage, previous: int | None) -> int:
    ordinal = source.source_global_ordinal
    if ordinal is None:
        ordinal = 0 if previous is None else previous + 1
    if previous is not None and ordinal <= previous:
        raise IngestionInvariantError(
            "source-global message ordinal must increase in input order: "
            f"{ordinal} follows {previous}"
        )
    return ordinal


def _ordered_source_payload(source: SourceMessage, ordinal: int) -> JsonObject:
    payload = cast(JsonObject, source.model_dump(mode="json"))
    payload["source_global_ordinal"] = ordinal
    return payload


def _beam_identity(source: SourceMessage) -> JsonObject | None:
    values = (
        source.archive_sha256,
        source.beam_directory_id,
        source.topic_id,
        source.batch_number,
        source.turn_group_index,
    )
    if not any(value is not None for value in values):
        return None
    if any(value is None for value in values):
        raise IngestionInvariantError(f"incomplete BEAM provenance for source ID {source.id!r}")
    return {
        "archive_sha256": source.archive_sha256,
        "beam_directory_id": source.beam_directory_id,
        "topic_id": source.topic_id,
        "batch_number": source.batch_number,
        "turn_group_index": source.turn_group_index,
        "raw_message_id": source.id,
    }


def _record_id(prefix: str, source: SourceMessage, ordinal: int) -> str:
    identity = _beam_identity(source)
    if identity is None:
        identity = _ordered_source_payload(source, ordinal)
    return content_id(prefix, identity)


def _message_from_source(
    source: SourceMessage,
    ordinal: int,
    role: MessageRole,
) -> Message:
    return Message(
        id=_record_id("message", source, ordinal),
        role=role,
        content=source.content,
        source_order=ordinal,
        source_metadata=_record_metadata(source, ordinal),
    )


def _tool_event_from_source(
    source: SourceMessage,
    ordinal: int,
    kind: ToolEventKind,
) -> ToolEvent:
    return ToolEvent(
        id=_record_id("tool_event", source, ordinal),
        kind=kind,
        content=source.content,
        source_order=ordinal,
        source_metadata=_record_metadata(source, ordinal),
    )


def _record_metadata(source: SourceMessage, ordinal: int) -> JsonObject:
    metadata: JsonObject = {
        "raw_message_id": source.id,
        "original_role": source.role,
        "source_global_message_ordinal": ordinal,
    }
    optional_fields: tuple[tuple[str, object], ...] = (
        ("archive_sha256", source.archive_sha256),
        ("beam_directory_id", source.beam_directory_id),
        ("topic_id", source.topic_id),
        ("batch_number", source.batch_number),
        ("turn_group_index", source.turn_group_index),
        ("original_index", source.index),
        ("question_type", source.question_type),
        ("time_anchor", source.time_anchor),
    )
    for key, value in optional_fields:
        if value is not None:
            metadata[key] = value
    return metadata


def _exchange_id(records: list[tuple[SourceMessage, int]]) -> str:
    beam_identities = [_beam_identity(source) for source, _ in records]
    if all(identity is not None for identity in beam_identities):
        first = cast(JsonObject, beam_identities[0])
        payload: JsonObject = {
            "archive_sha256": first["archive_sha256"],
            "beam_directory_id": first["beam_directory_id"],
            "topic_id": first["topic_id"],
            "batch_number": first["batch_number"],
            "turn_group_index": first["turn_group_index"],
            "raw_message_ids": [source.id for source, _ in records],
        }
    elif any(identity is not None for identity in beam_identities):
        raise IngestionInvariantError("exchange mixes BEAM and standalone provenance")
    else:
        payload = {
            "source_records": [
                _ordered_source_payload(source, ordinal) for source, ordinal in records
            ]
        }
    return content_id("exchange", payload)


def _exchange_metadata(records: list[tuple[SourceMessage, int]]) -> JsonObject:
    first_source, first_ordinal = records[0]
    metadata: JsonObject = {
        "raw_message_ids": [source.id for source, _ in records],
        "source_global_message_ordinal": first_ordinal,
    }
    applicable_fields: tuple[tuple[str, object], ...] = (
        ("archive_sha256", first_source.archive_sha256),
        ("beam_directory_id", first_source.beam_directory_id),
        ("topic_id", first_source.topic_id),
        ("batch_number", first_source.batch_number),
        ("turn_group_index", first_source.turn_group_index),
    )
    for key, value in applicable_fields:
        if value is not None:
            metadata[key] = value
    return metadata
