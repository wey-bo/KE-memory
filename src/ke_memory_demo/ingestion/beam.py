from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Annotated, cast
from zipfile import BadZipFile, ZipFile

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from ke_memory_demo.core.ids import content_id
from ke_memory_demo.core.json import JsonObject, JsonValue
from ke_memory_demo.domain.conversation import Conversation, Exchange, Session

from .exchange_builder import SourceMessage, build_exchanges


BEAM_ARCHIVE_SHA256 = "690106a93ab88dac46e8fef1e84884acc889518424240f57a47428d3efbe6346"
PROBING_QUESTION_CATEGORIES = (
    "abstention",
    "contradiction_resolution",
    "event_ordering",
    "information_extraction",
    "instruction_following",
    "knowledge_update",
    "multi_session_reasoning",
    "preference_following",
    "summarization",
    "temporal_reasoning",
)


class BeamArchiveError(RuntimeError):
    """Raised when the fixed BEAM archive cannot be verified or decoded."""


class _BeamRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    role: Annotated[str, Field(min_length=1)]
    id: Annotated[int, Field(ge=0)] | Annotated[str, Field(min_length=1)]
    content: str
    time_anchor: Annotated[str, Field(min_length=1)] | None = None
    index: Annotated[int, Field(ge=0)] | Annotated[str, Field(min_length=1)] | None = None
    question_type: Annotated[str, Field(min_length=1)] | None = None


class _BeamBatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    batch_number: Annotated[int, Field(gt=0)]
    turns: Annotated[list[Annotated[list[_BeamRecord], Field(min_length=1)]], Field(min_length=1)]
    time_anchor: Annotated[str, Field(min_length=1)] | None


class _BeamTopic(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    id: Annotated[int, Field(ge=0)] | Annotated[str, Field(min_length=1)]
    category: Annotated[str, Field(min_length=1)]
    title: Annotated[str, Field(min_length=1)]
    theme: Annotated[str, Field(min_length=1)]
    subtopics: Annotated[list[Annotated[str, Field(min_length=1)]], Field(min_length=1)]


_BATCHES_ADAPTER = TypeAdapter(list[_BeamBatch])


def select_beam_directories(archive_sha: str) -> tuple[int, int, int]:
    """Select one directory from each preregistered BEAM topic stratum."""
    strata = {
        "formal": (1, 2, 3, 4, 5),
        "artifact": (6, 7, 8, 9, 10, 13, 14, 15),
        "human": (11, 12, 16, 17, 18, 19, 20),
    }
    selected: list[int] = []
    for name, directory_ids in strata.items():
        ranked = sorted(
            directory_ids,
            key=lambda directory_id: hashlib.sha256(
                f"ke-memory-demo:BEAM-100K:{archive_sha}:{name}:{directory_id}".encode()
            ).hexdigest(),
        )
        selected.append(ranked[0])
    return selected[0], selected[1], selected[2]


def load_beam_subset(zip_path: Path) -> list[Conversation]:
    """Verify and stream the fixed BEAM subset into immutable conversations."""
    archive_sha256 = _hash_archive(zip_path)
    if archive_sha256 != BEAM_ARCHIVE_SHA256:
        raise BeamArchiveError(
            f"BEAM archive SHA-256 mismatch: expected {BEAM_ARCHIVE_SHA256}, got {archive_sha256}"
        )

    try:
        with ZipFile(zip_path) as archive:
            return [
                _load_conversation(archive, archive_sha256, directory_id)
                for directory_id in select_beam_directories(archive_sha256)
            ]
    except BeamArchiveError:
        raise
    except BadZipFile as exc:
        raise BeamArchiveError(f"Invalid BEAM ZIP archive {zip_path}: {exc}") from exc
    except OSError as exc:
        raise BeamArchiveError(f"Unable to read BEAM ZIP archive {zip_path}: {exc}") from exc


def _hash_archive(path: Path) -> str:
    hasher = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                hasher.update(chunk)
    except OSError as exc:
        raise BeamArchiveError(f"Unable to hash BEAM archive {path}: {exc}") from exc
    return hasher.hexdigest()


def _load_conversation(
    archive: ZipFile,
    archive_sha256: str,
    directory_id: int,
) -> Conversation:
    prefix = f"BEAM-main/chats/100K/{directory_id}"
    chat_member = f"{prefix}/chat.json"
    topic_member = f"{prefix}/topic.json"
    questions_member = f"{prefix}/probing_questions/probing_questions.json"

    topic_value = _read_json_member(archive, topic_member)
    chat_value = _read_json_member(archive, chat_member)
    questions_value = _read_json_member(archive, questions_member)
    try:
        topic = _BeamTopic.model_validate(topic_value)
        batches = _BATCHES_ADAPTER.validate_python(chat_value, strict=True)
    except ValidationError as exc:
        raise BeamArchiveError(
            f"Malformed BEAM conversation schema in directory {directory_id}: {exc}"
        ) from exc
    if not batches:
        raise BeamArchiveError(f"BEAM directory {directory_id} contains no chat batches")

    batch_numbers = [batch.batch_number for batch in batches]
    if len(batch_numbers) != len(set(batch_numbers)):
        raise BeamArchiveError(f"BEAM directory {directory_id} has duplicate batch numbers")

    conversation_identity: JsonObject = {
        "archive_sha256": archive_sha256,
        "beam_directory_id": directory_id,
        "topic_id": topic.id,
    }
    conversation_id = content_id("conversation", conversation_identity)
    probing_questions = _flatten_probing_questions(questions_value, directory_id=directory_id)

    session_ids: list[str] = []
    session_metadata: list[JsonObject] = []
    source_messages: list[SourceMessage] = []
    source_global_ordinal = 0
    for batch in batches:
        session_identity: JsonObject = {
            **conversation_identity,
            "batch_number": batch.batch_number,
        }
        session_id = content_id("session", session_identity)
        session_ids.append(session_id)
        metadata = dict(session_identity)
        if batch.time_anchor is not None:
            metadata["time_anchor"] = batch.time_anchor
        session_metadata.append(metadata)

        for turn_group_index, turn_group in enumerate(batch.turns):
            for record in turn_group:
                time_anchor = (
                    record.time_anchor if record.time_anchor is not None else batch.time_anchor
                )
                source_messages.append(
                    SourceMessage(
                        id=record.id,
                        role=record.role,
                        content=record.content,
                        session_id=session_id,
                        archive_sha256=archive_sha256,
                        beam_directory_id=directory_id,
                        topic_id=topic.id,
                        batch_number=batch.batch_number,
                        turn_group_index=turn_group_index,
                        index=record.index,
                        question_type=record.question_type,
                        time_anchor=time_anchor,
                        source_global_ordinal=source_global_ordinal,
                    )
                )
                source_global_ordinal += 1

    exchanges = build_exchanges(source_messages)
    exchanges_by_session: dict[str, list[Exchange]] = {session_id: [] for session_id in session_ids}
    for exchange in exchanges:
        exchanges_by_session[exchange.session_id].append(exchange)

    try:
        sessions = tuple(
            Session(
                id=session_id,
                conversation_id=conversation_id,
                exchanges=tuple(exchanges_by_session[session_id]),
                source_metadata=metadata,
            )
            for session_id, metadata in zip(session_ids, session_metadata, strict=True)
        )
        return Conversation(
            id=conversation_id,
            sessions=sessions,
            probing_questions=probing_questions,
            source_metadata=conversation_identity,
        )
    except (KeyError, ValidationError) as exc:
        raise BeamArchiveError(
            f"Unable to assemble BEAM domain records for directory {directory_id}: {exc}"
        ) from exc


def _read_json_member(archive: ZipFile, member: str) -> JsonValue:
    try:
        with archive.open(member) as source:
            return cast(JsonValue, json.load(source))
    except KeyError as exc:
        raise BeamArchiveError(f"Missing required BEAM member: {member}") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise BeamArchiveError(f"Malformed JSON in BEAM member {member}: {exc}") from exc


def _flatten_probing_questions(
    value: JsonValue,
    *,
    directory_id: int,
) -> tuple[JsonObject, ...]:
    if not isinstance(value, dict):
        raise BeamArchiveError(f"BEAM directory {directory_id} probing questions must be an object")
    grouped = cast(dict[str, JsonValue], value)
    if len(grouped) != 10 or set(grouped) != set(PROBING_QUESTION_CATEGORIES):
        raise BeamArchiveError(
            f"BEAM directory {directory_id} must contain the ten fixed categories"
        )

    flattened: list[JsonObject] = []
    for category, category_value in grouped.items():
        if not isinstance(category_value, list) or len(category_value) != 2:
            raise BeamArchiveError(
                f"BEAM directory {directory_id} category {category!r} must contain "
                "exactly two questions"
            )
        questions = cast(list[JsonValue], category_value)
        for category_ordinal, question_value in enumerate(questions):
            if not isinstance(question_value, dict):
                raise BeamArchiveError(
                    f"BEAM directory {directory_id} category {category!r} has an invalid "
                    "question object"
                )
            question = cast(JsonObject, question_value)
            prompt = question.get("question")
            if not isinstance(prompt, str) or not prompt.strip():
                raise BeamArchiveError(
                    f"BEAM directory {directory_id} category {category!r} requires a "
                    "nonempty question"
                )
            rubric = question.get("rubric")
            if (
                not isinstance(rubric, list)
                or not rubric
                or any(not isinstance(item, str) or not item.strip() for item in rubric)
            ):
                raise BeamArchiveError(
                    f"BEAM directory {directory_id} category {category!r} requires a "
                    "nonempty rubric"
                )
            if "category" in question or "category_ordinal" in question:
                raise BeamArchiveError(
                    f"BEAM directory {directory_id} category {category!r} uses reserved "
                    "provenance fields"
                )
            flattened.append(
                {
                    **question,
                    "category": category,
                    "category_ordinal": category_ordinal,
                }
            )

    if len(flattened) != 20:
        raise BeamArchiveError(
            f"BEAM directory {directory_id} must contain exactly 20 probing questions"
        )
    return tuple(flattened)
