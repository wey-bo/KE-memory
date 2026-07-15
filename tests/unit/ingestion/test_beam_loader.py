from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
from zipfile import BadZipFile, ZipFile

import pytest

import ke_memory_demo.ingestion.beam as beam_module
from ke_memory_demo.core.json import JsonObject, JsonValue
from ke_memory_demo.domain import Conversation
from ke_memory_demo.ingestion import BeamArchiveError, load_beam_subset


DIRECTORY_IDS = (4, 15, 17)


def _member(directory_id: int, relative_path: str) -> str:
    return f"BEAM-main/chats/100K/{directory_id}/{relative_path}"


def _topic(directory_id: int) -> JsonObject:
    return {
        "id": directory_id + 100,
        "category": "Synthetic",
        "title": f"Synthetic topic {directory_id}",
        "theme": "Loader boundary validation",
        "subtopics": ["Typed failures"],
    }


def _chat() -> list[JsonValue]:
    return [
        {
            "batch_number": 1,
            "turns": [
                [
                    {"role": "user", "id": 0, "content": "synthetic user"},
                    {"role": "assistant", "id": 1, "content": "synthetic assistant"},
                ]
            ],
            "time_anchor": None,
        }
    ]


def _questions() -> JsonObject:
    return {
        category: [
            {
                "question": f"{category} question {ordinal}",
                "rubric": [f"{category} criterion {ordinal}"],
            }
            for ordinal in range(2)
        ]
        for category in beam_module.PROBING_QUESTION_CATEGORIES
    }


def _json_bytes(value: JsonValue) -> bytes:
    return json.dumps(value, ensure_ascii=False).encode("utf-8")


def _archive_members() -> dict[str, bytes]:
    members: dict[str, bytes] = {}
    for directory_id in DIRECTORY_IDS:
        members[_member(directory_id, "chat.json")] = _json_bytes(_chat())
        members[_member(directory_id, "topic.json")] = _json_bytes(_topic(directory_id))
        members[_member(directory_id, "probing_questions/probing_questions.json")] = _json_bytes(
            _questions()
        )
    return members


def _write_synthetic_archive(
    path: Path,
    *,
    replacements: dict[str, bytes] | None = None,
    omitted: set[str] | None = None,
) -> None:
    members = _archive_members()
    members.update(replacements or {})
    for member in omitted or set():
        members.pop(member)
    with ZipFile(path, "w") as archive:
        for member, payload in members.items():
            archive.writestr(member, payload)


def _sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(64 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _load_synthetic_archive(
    path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> list[Conversation]:
    def fixed_directories(_archive_sha: str) -> tuple[int, int, int]:
        return DIRECTORY_IDS

    monkeypatch.setattr(beam_module, "BEAM_ARCHIVE_SHA256", _sha256(path))
    monkeypatch.setattr(beam_module, "select_beam_directories", fixed_directories)
    return load_beam_subset(path)


def test_loader_wraps_a_hash_verified_non_zip_as_a_typed_archive_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive_path = tmp_path / "malformed.zip"
    archive_path.write_bytes(b"not a ZIP archive")

    with pytest.raises(BeamArchiveError) as raised:
        _load_synthetic_archive(archive_path, monkeypatch)

    assert str(raised.value).startswith(f"Invalid BEAM ZIP archive {archive_path}:")
    assert isinstance(raised.value.__cause__, BadZipFile)


def test_loader_rejects_a_missing_approved_json_member(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive_path = tmp_path / "missing-member.zip"
    missing_member = _member(4, "topic.json")
    _write_synthetic_archive(archive_path, omitted={missing_member})

    with pytest.raises(
        BeamArchiveError,
        match=rf"^Missing required BEAM member: {re.escape(missing_member)}$",
    ):
        _load_synthetic_archive(archive_path, monkeypatch)


def test_loader_rejects_a_malformed_json_member(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive_path = tmp_path / "malformed-json.zip"
    malformed_member = _member(4, "chat.json")
    _write_synthetic_archive(
        archive_path,
        replacements={malformed_member: b'{"unterminated":'},
    )

    with pytest.raises(BeamArchiveError) as raised:
        _load_synthetic_archive(archive_path, monkeypatch)

    assert str(raised.value).startswith(f"Malformed JSON in BEAM member {malformed_member}:")


def test_loader_rejects_an_invalid_chat_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive_path = tmp_path / "invalid-chat.zip"
    _write_synthetic_archive(
        archive_path,
        replacements={_member(4, "chat.json"): _json_bytes({"batches": "not-a-list"})},
    )

    with pytest.raises(
        BeamArchiveError,
        match=r"^Malformed BEAM conversation schema in directory 4:",
    ):
        _load_synthetic_archive(archive_path, monkeypatch)


def test_loader_rejects_an_invalid_topic_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive_path = tmp_path / "invalid-topic.zip"
    invalid_topic = _topic(4)
    invalid_topic.pop("id")
    _write_synthetic_archive(
        archive_path,
        replacements={_member(4, "topic.json"): _json_bytes(invalid_topic)},
    )

    with pytest.raises(
        BeamArchiveError,
        match=r"^Malformed BEAM conversation schema in directory 4:",
    ):
        _load_synthetic_archive(archive_path, monkeypatch)


def test_loader_rejects_an_empty_chat_batch_list(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive_path = tmp_path / "empty-batches.zip"
    _write_synthetic_archive(
        archive_path,
        replacements={_member(4, "chat.json"): _json_bytes([])},
    )

    with pytest.raises(
        BeamArchiveError,
        match=r"^BEAM directory 4 contains no chat batches$",
    ):
        _load_synthetic_archive(archive_path, monkeypatch)


def test_loader_rejects_a_batch_with_no_turn_groups(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive_path = tmp_path / "empty-batch.zip"
    empty_batch: JsonValue = {
        "batch_number": 1,
        "turns": [],
        "time_anchor": None,
    }
    _write_synthetic_archive(
        archive_path,
        replacements={_member(4, "chat.json"): _json_bytes([empty_batch])},
    )

    with pytest.raises(
        BeamArchiveError,
        match=r"^Malformed BEAM conversation schema in directory 4:",
    ):
        _load_synthetic_archive(archive_path, monkeypatch)


def test_loader_rejects_duplicate_batch_numbers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive_path = tmp_path / "duplicate-batches.zip"
    duplicate_batches = _chat()
    duplicate_batches.append(deepcopy(duplicate_batches[0]))
    _write_synthetic_archive(
        archive_path,
        replacements={_member(4, "chat.json"): _json_bytes(duplicate_batches)},
    )

    with pytest.raises(
        BeamArchiveError,
        match=r"^BEAM directory 4 has duplicate batch numbers$",
    ):
        _load_synthetic_archive(archive_path, monkeypatch)
