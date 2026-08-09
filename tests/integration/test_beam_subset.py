from __future__ import annotations

import hashlib
import json
from pathlib import Path
import socket
from typing import cast
from zipfile import ZipFile

import pytest

from ke_memory_demo.core.json import JsonObject, JsonValue, canonical_json
from ke_memory_demo.domain import Conversation
from ke_memory_demo.ingestion import load_beam_subset, select_beam_directories

from fixtures.datasets import dataset_path, require_dataset


ARCHIVE_PATH = dataset_path("BEAM.zip")
ARCHIVE_SHA256 = "690106a93ab88dac46e8fef1e84884acc889518424240f57a47428d3efbe6346"
EXPECTED_DIRECTORIES = (4, 15, 17)
EXPECTED_SESSION_COUNTS = (3, 5, 5)
EXPECTED_EXCHANGE_COUNTS = (106, 136, 143)
EXPECTED_FIRST_USERS = {
    4: (
        "I'm trying to figure out what day it will be in a week from March 3, 2024, "
        "can you help me with that, like what's the date gonna be ->-> 1,1",
        "a05a1ee46662d35c8b76cf10d3de9cd62dc9126a522e98c675163d97dd0d6409",
        7,
        "1,1",
        "March-03-2024",
    ),
    15: (
        "I'm Darryl, and I'm kinda curious, what are some comfy sneaker options for daily wear, "
        "considering I'm 32 and always on the go, you know? ->-> 1,2",
        "ff687cb8aa87210e6657b66239de04fe3f9d02f8d252dff872cc9af7a323782b",
        20,
        "1,2",
        "March-12-2024",
    ),
    17: (
        "I'm kinda stressed about managing my time effectively, especially with my birthday "
        "coming up on March 15, 2024, and I'm turning 45, so I was wondering if you could help "
        "me create a schedule that balances my work as a TV/film producer with some self-care, "
        "you know, for my own well-being ->-> 1,1",
        "4155de901a4d75df0014a1fc4dd1ba4a0fc29683bebeece6eb729f46e82f8719",
        22,
        "1,1",
        "March-15-2024",
    ),
}
QUESTION_CATEGORIES = (
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


def _archive_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _directory_id(conversation: Conversation) -> int:
    return cast(int, conversation.source_metadata["beam_directory_id"])


def _expected_questions(archive: ZipFile, directory_id: int) -> tuple[JsonObject, ...]:
    member = f"BEAM-main/chats/100K/{directory_id}/probing_questions/probing_questions.json"
    with archive.open(member) as source:
        grouped = cast(dict[str, list[JsonObject]], json.load(source))
    return tuple(
        {**question, "category": category, "category_ordinal": ordinal}
        for category, questions in grouped.items()
        for ordinal, question in enumerate(questions)
    )


def _all_domain_ids(conversation: Conversation) -> list[str]:
    identifiers = [conversation.id]
    for session in conversation.sessions:
        identifiers.append(session.id)
        for exchange in session.exchanges:
            identifiers.extend((exchange.id, exchange.user.id, exchange.assistant.id))
            identifiers.extend(event.id for event in exchange.events)
    return identifiers


def _walk_json(value: JsonValue) -> list[JsonValue]:
    values = [value]
    if isinstance(value, dict):
        for nested in value.values():
            values.extend(_walk_json(nested))
    elif isinstance(value, list):
        for nested in value:
            values.extend(_walk_json(nested))
    return values


def test_fixed_beam_subset_is_normalized_exactly_without_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive_path = require_dataset("BEAM.zip")

    def deny_network(_socket: socket.socket, *_args: object, **_kwargs: object) -> None:
        raise AssertionError("BEAM normalization attempted network access")

    monkeypatch.setattr(socket.socket, "connect", deny_network)

    assert archive_path.stat().st_size == 728_569_926
    assert _archive_sha256(archive_path) == ARCHIVE_SHA256
    assert select_beam_directories(ARCHIVE_SHA256) == EXPECTED_DIRECTORIES

    conversations = load_beam_subset(archive_path)
    assert tuple(_directory_id(conversation) for conversation in conversations) == (
        EXPECTED_DIRECTORIES
    )
    assert tuple(len(conversation.sessions) for conversation in conversations) == (
        EXPECTED_SESSION_COUNTS
    )
    exchange_counts = tuple(
        sum(len(session.exchanges) for session in conversation.sessions)
        for conversation in conversations
    )
    assert exchange_counts == EXPECTED_EXCHANGE_COUNTS
    assert sum(exchange_counts) == 385
    assert [len(conversation.probing_questions) for conversation in conversations] == [20] * 3

    with ZipFile(archive_path) as archive:
        for conversation in conversations:
            directory_id = _directory_id(conversation)
            expected_content, expected_hash, topic_id, index, time_anchor = EXPECTED_FIRST_USERS[
                directory_id
            ]
            first_user = conversation.sessions[0].exchanges[0].user
            assert first_user.content == expected_content
            assert first_user.content_hash == expected_hash
            assert first_user.source_metadata == {
                "archive_sha256": ARCHIVE_SHA256,
                "beam_directory_id": directory_id,
                "topic_id": topic_id,
                "batch_number": 1,
                "turn_group_index": 0,
                "raw_message_id": 0,
                "original_index": index,
                "original_role": "user",
                "question_type": "main_question",
                "time_anchor": time_anchor,
                "source_global_message_ordinal": 0,
            }
            assert conversation.probing_questions == _expected_questions(archive, directory_id)

            identifiers = _all_domain_ids(conversation)
            assert len(identifiers) == len(set(identifiers))

            exchanges = [
                exchange for session in conversation.sessions for exchange in session.exchanges
            ]
            ordinals = [exchange.global_ordinal for exchange in exchanges]
            assert all(left < right for left, right in zip(ordinals, ordinals[1:]))
            assert all(
                exchange.global_ordinal
                == cast(int, exchange.user.source_metadata["source_global_message_ordinal"])
                for exchange in exchanges
            )

            question_texts = [
                cast(str, question["question"]) for question in conversation.probing_questions
            ]
            rendered_exchange_content = "\n".join(
                record.content
                for exchange in exchanges
                for record in (exchange.user, *exchange.events, exchange.assistant)
            )
            assert all(
                question_text not in rendered_exchange_content for question_text in question_texts
            )

            session_payload: JsonValue = [
                cast(JsonValue, session.model_dump(mode="json"))
                for session in conversation.sessions
            ]
            serialized_session_content = canonical_json(session_payload)
            session_values = _walk_json(session_payload)
            assert all(
                question not in session_values for question in conversation.probing_questions
            )
            assert all(
                canonical_json(question) not in serialized_session_content
                for question in conversation.probing_questions
            )
            assert [question["category"] for question in conversation.probing_questions] == [
                category for category in QUESTION_CATEGORIES for _ in range(2)
            ]

    assert conversations == load_beam_subset(archive_path)
    assert sum(len(conversation.probing_questions) for conversation in conversations) == 60
