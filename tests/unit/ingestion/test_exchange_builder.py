from __future__ import annotations

from collections.abc import Iterator
from copy import deepcopy
from pathlib import Path
from typing import cast

import pytest
from pydantic import ValidationError

from ke_memory_demo.core.json import JsonObject, JsonValue
from ke_memory_demo.ingestion import (
    BeamArchiveError,
    IngestionInvariantError,
    SourceMessage,
    build_exchanges,
    load_beam_subset,
    select_beam_directories,
)
from ke_memory_demo.ingestion.beam import (
    _flatten_probing_questions,  # pyright: ignore[reportPrivateUsage]
)


ARCHIVE_SHA256 = "690106a93ab88dac46e8fef1e84884acc889518424240f57a47428d3efbe6346"
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


def _source(
    source_id: int | str,
    role: str,
    content: str,
    *,
    session_id: str | None = None,
    source_global_ordinal: int | None = None,
) -> SourceMessage:
    return SourceMessage(
        id=source_id,
        role=role,
        content=content,
        session_id=session_id,
        source_global_ordinal=source_global_ordinal,
    )


def _beam_source(
    source_id: int,
    role: str,
    content: str,
    source_global_ordinal: int,
    *,
    session_id: str = "session:beam",
) -> SourceMessage:
    return SourceMessage(
        id=source_id,
        role=role,
        content=content,
        session_id=session_id,
        archive_sha256=ARCHIVE_SHA256,
        beam_directory_id=4,
        topic_id=7,
        batch_number=1,
        turn_group_index=0,
        index="1,1" if role == "user" else None,
        question_type="main_question" if role == "user" else None,
        time_anchor="March-03-2024" if role == "user" else None,
        source_global_ordinal=source_global_ordinal,
    )


def _valid_questions() -> JsonObject:
    return {
        category: [
            {
                "question": f"{category} question {ordinal}",
                "rubric": [f"criterion {ordinal}"],
                "original": {"ordinal": ordinal},
            }
            for ordinal in range(2)
        ]
        for category in QUESTION_CATEGORIES
    }


def test_source_message_is_immutable_extra_forbidding_and_preserves_raw_id_type() -> None:
    integer_id = SourceMessage(id=7, role="user", content="  raw text\n")
    string_id = SourceMessage(id="7", role="user", content="  raw text\n")

    assert integer_id.id == 7
    assert type(integer_id.id) is int
    assert string_id.id == "7"
    assert integer_id.content == "  raw text\n"
    with pytest.raises(ValidationError, match="frozen"):
        integer_id.content = "changed"
    with pytest.raises(ValidationError, match="extra"):
        SourceMessage.model_validate(
            {"id": 7, "role": "user", "content": "text", "unexpected": True}
        )


def test_two_pairs_inside_one_beam_turn_become_two_exchanges() -> None:
    source = [
        SourceMessage(id=0, role="user", content="u1"),
        SourceMessage(id=1, role="assistant", content="a1"),
        SourceMessage(id=2, role="user", content="u2"),
        SourceMessage(id=3, role="assistant", content="a2"),
    ]

    exchanges = build_exchanges(source)

    assert [(exchange.user.content, exchange.assistant.content) for exchange in exchanges] == [
        ("u1", "a1"),
        ("u2", "a2"),
    ]


def test_tool_events_attach_in_source_order_without_closing_exchange() -> None:
    source = [
        SourceMessage(id=0, role="user", content="run it"),
        SourceMessage(id=1, role="tool_call", content='{"name":"run"}'),
        SourceMessage(id=2, role="tool_result", content='{"ok":true}'),
        SourceMessage(id=3, role="assistant", content="done"),
    ]

    [exchange] = build_exchanges(source)

    assert [event.kind.value for event in exchange.events] == ["tool_call", "tool_result"]
    assert [event.content for event in exchange.events] == [
        '{"name":"run"}',
        '{"ok":true}',
    ]
    assert [
        exchange.user.source_order,
        *(event.source_order for event in exchange.events),
        exchange.assistant.source_order,
    ] == [0, 1, 2, 3]


def test_build_exchanges_consumes_the_input_iterable_exactly_once() -> None:
    class SinglePassMessages:
        def __init__(self) -> None:
            self.iterations = 0

        def __iter__(self) -> Iterator[SourceMessage]:
            self.iterations += 1
            if self.iterations > 1:
                raise AssertionError("messages iterable was scanned more than once")
            yield _source(0, "user", "question")
            yield _source(1, "assistant", "answer")

    messages = SinglePassMessages()

    [exchange] = build_exchanges(messages)

    assert messages.iterations == 1
    assert exchange.user.content == "question"


def test_explicit_source_ordinals_and_session_transitions_are_preserved() -> None:
    source = [
        _source(0, "user", "u1", session_id="session-1", source_global_ordinal=8),
        _source(1, "assistant", "a1", session_id="session-1", source_global_ordinal=9),
        _source(2, "user", "u2", session_id="session-2", source_global_ordinal=14),
        _source(3, "assistant", "a2", session_id="session-2", source_global_ordinal=15),
    ]

    exchanges = build_exchanges(source)

    assert [exchange.session_id for exchange in exchanges] == ["session-1", "session-2"]
    assert [exchange.global_ordinal for exchange in exchanges] == [8, 14]
    assert [exchanges[0].user.source_order, exchanges[0].assistant.source_order] == [8, 9]


def test_beam_provenance_populates_record_metadata_without_changing_raw_content() -> None:
    source = [
        _beam_source(10, "user", "  exact user\n", 20),
        _beam_source(11, "assistant", "exact assistant", 21),
    ]

    [exchange] = build_exchanges(source)

    assert exchange.user.content == "  exact user\n"
    assert exchange.user.source_metadata == {
        "archive_sha256": ARCHIVE_SHA256,
        "beam_directory_id": 4,
        "topic_id": 7,
        "batch_number": 1,
        "turn_group_index": 0,
        "raw_message_id": 10,
        "original_index": "1,1",
        "original_role": "user",
        "question_type": "main_question",
        "time_anchor": "March-03-2024",
        "source_global_message_ordinal": 20,
    }
    assert exchange.assistant.source_metadata == {
        "archive_sha256": ARCHIVE_SHA256,
        "beam_directory_id": 4,
        "topic_id": 7,
        "batch_number": 1,
        "turn_group_index": 0,
        "raw_message_id": 11,
        "original_role": "assistant",
        "source_global_message_ordinal": 21,
    }
    assert exchange.source_metadata == {
        "archive_sha256": ARCHIVE_SHA256,
        "beam_directory_id": 4,
        "topic_id": 7,
        "batch_number": 1,
        "turn_group_index": 0,
        "raw_message_ids": [10, 11],
        "source_global_message_ordinal": 20,
    }


def test_beam_ids_use_provenance_while_standalone_ids_use_the_full_record() -> None:
    original_beam = build_exchanges(
        [_beam_source(0, "user", "original", 0), _beam_source(1, "assistant", "answer", 1)]
    )[0]
    edited_beam = build_exchanges(
        [_beam_source(0, "user", "edited", 0), _beam_source(1, "assistant", "different", 1)]
    )[0]
    original_standalone = build_exchanges(
        [_source(0, "user", "original"), _source(1, "assistant", "answer")]
    )[0]
    edited_standalone = build_exchanges(
        [_source(0, "user", "edited"), _source(1, "assistant", "answer")]
    )[0]

    assert original_beam.id == edited_beam.id
    assert original_beam.user.id == edited_beam.user.id
    assert original_beam.assistant.id == edited_beam.assistant.id
    assert original_standalone.id != edited_standalone.id
    assert original_standalone.user.id != edited_standalone.user.id


@pytest.mark.parametrize(
    ("source", "error"),
    [
        ([_source(0, "assistant", "orphan")], "orphan assistant"),
        ([_source(0, "tool_call", "orphan")], "orphan tool event"),
        ([_source(0, "tool_result", "orphan")], "orphan tool event"),
        (
            [_source(0, "user", "first"), _source(1, "user", "second")],
            "consecutive user",
        ),
        ([_source(0, "user", "unclosed")], "unclosed exchange"),
        (
            [_source(0, "user", "unclosed"), _source(1, "tool_call", "call")],
            "unclosed exchange",
        ),
        ([_source(0, "system", "unsupported")], "unsupported role"),
        (
            [
                _source(0, "user", "u"),
                _source(1, "assistant", "a"),
                _source(0, "user", "duplicate"),
            ],
            "duplicate source ID",
        ),
    ],
)
def test_invalid_state_transitions_raise_typed_failures(
    source: list[SourceMessage], error: str
) -> None:
    with pytest.raises(IngestionInvariantError, match=error):
        build_exchanges(source)


@pytest.mark.parametrize("role", ["assistant", "tool_call", "tool_result"])
def test_every_record_in_an_exchange_must_share_the_user_session(role: str) -> None:
    source = [
        _source(0, "user", "u", session_id="session-1"),
        _source(1, role, "different session", session_id="session-2"),
    ]
    if role != "assistant":
        source.append(_source(2, "assistant", "a", session_id="session-1"))

    with pytest.raises(IngestionInvariantError, match="same session"):
        build_exchanges(source)


def test_explicit_source_ordinals_must_follow_input_order() -> None:
    source = [
        _source(0, "user", "u", source_global_ordinal=4),
        _source(1, "assistant", "a", source_global_ordinal=3),
    ]

    with pytest.raises(IngestionInvariantError, match="source-global message ordinal"):
        build_exchanges(source)


def test_partial_beam_identity_provenance_is_rejected() -> None:
    source = [
        SourceMessage(
            id=0,
            role="user",
            content="u",
            archive_sha256=ARCHIVE_SHA256,
        ),
        _source(1, "assistant", "a"),
    ]

    with pytest.raises(IngestionInvariantError, match="incomplete BEAM provenance"):
        build_exchanges(source)


def test_selection_rule_returns_the_frozen_stratified_directories() -> None:
    assert select_beam_directories(ARCHIVE_SHA256) == (4, 15, 17)


def test_loader_rejects_a_wrong_hash_before_attempting_zip_normalization(tmp_path: Path) -> None:
    invalid_zip = tmp_path / "wrong.zip"
    invalid_zip.write_bytes(b"this is deliberately not a zip archive")

    with pytest.raises(BeamArchiveError, match="SHA-256 mismatch"):
        load_beam_subset(invalid_zip)


def test_loader_wraps_an_unreadable_archive_as_a_typed_failure(tmp_path: Path) -> None:
    missing = tmp_path / "missing.zip"

    with pytest.raises(BeamArchiveError, match="Unable to hash BEAM archive"):
        load_beam_subset(missing)


def test_probing_questions_flatten_in_category_insertion_order_and_preserve_values() -> None:
    questions = _valid_questions()
    original = deepcopy(questions)

    flattened = _flatten_probing_questions(questions, directory_id=4)

    assert len(flattened) == 20
    assert [question["category"] for question in flattened] == [
        category for category in QUESTION_CATEGORIES for _ in range(2)
    ]
    assert [question["category_ordinal"] for question in flattened] == [0, 1] * 10
    assert questions == original
    assert flattened[0] == {
        **cast(JsonObject, cast(list[JsonValue], questions["abstention"])[0]),
        "category": "abstention",
        "category_ordinal": 0,
    }


def test_probing_question_validation_rejects_every_malformed_contract_shape() -> None:
    wrong_categories = _valid_questions()
    wrong_categories.pop("temporal_reasoning")
    wrong_count = _valid_questions()
    wrong_count["abstention"] = cast(
        JsonValue, [cast(list[JsonValue], wrong_count["abstention"])[0]]
    )
    non_object = _valid_questions()
    non_object["abstention"] = cast(JsonValue, ["not-an-object", "also-not-an-object"])
    empty_question = _valid_questions()
    cast(JsonObject, cast(list[JsonValue], empty_question["abstention"])[0])["question"] = ""
    empty_rubric = _valid_questions()
    cast(JsonObject, cast(list[JsonValue], empty_rubric["abstention"])[0])["rubric"] = []
    reserved_provenance = _valid_questions()
    cast(JsonObject, cast(list[JsonValue], reserved_provenance["abstention"])[0])["category"] = (
        "source-value"
    )

    invalid_values: tuple[tuple[JsonValue, str], ...] = (
        (wrong_categories, "ten fixed categories"),
        (wrong_count, "exactly two questions"),
        (non_object, "question object"),
        (empty_question, "nonempty question"),
        (empty_rubric, "nonempty rubric"),
        (reserved_provenance, "reserved provenance"),
    )
    for value, error in invalid_values:
        with pytest.raises(BeamArchiveError, match=error):
            _flatten_probing_questions(value, directory_id=4)
