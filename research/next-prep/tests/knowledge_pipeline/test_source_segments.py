from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from knowledge_pipeline.source import TurnUnit
from knowledge_pipeline.source_segments import SOURCE_SEGMENTS_VERSION, load_source_segments


def _units() -> tuple[TurnUnit, ...]:
    return (
        TurnUnit(
            candidate_id="candidate-a",
            candidate_index=0,
            turn_index=0,
            source="synthetic",
            user="save it",
            agent="[工具结果] preference saved. I recommend tea.",
            user_pointer="/candidates/0/turns/0/user",
            agent_pointer="/candidates/0/turns/0/agent",
        ),
        TurnUnit(
            candidate_id="candidate-a",
            candidate_index=0,
            turn_index=1,
            source="synthetic",
            user="thanks",
            agent="You are welcome.",
            user_pointer="/candidates/0/turns/1/user",
            agent_pointer="/candidates/0/turns/1/agent",
        ),
    )


def _entry(**overrides: object) -> dict[str, object]:
    agent = _units()[0].agent
    value: dict[str, object] = {
        "candidate_id": "candidate-a",
        "turn_index": 0,
        "agent_sha256": hashlib.sha256(agent.encode("utf-8")).hexdigest(),
        "tool_results": [{
            "quote": "preference saved.",
            "occurrence_index": 0,
            "marker_occurrence_index": 0,
        }],
    }
    value.update(overrides)
    return value


def _write(path: Path, turns: list[dict[str, object]], version: object = SOURCE_SEGMENTS_VERSION) -> None:
    path.write_text(json.dumps({"version": version, "turns": turns}, ensure_ascii=False), encoding="utf-8")


def test_load_source_segments_resolves_explicit_non_heuristic_spans(tmp_path: Path) -> None:
    path = tmp_path / "source-segments.json"
    _write(path, [_entry()])

    loaded = load_source_segments(path, _units())
    span = loaded.for_turn("candidate-a", 0)[0]

    assert loaded.version == "source-segments-v1"
    assert loaded.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert span.quote == "preference saved."
    assert span.marker_occurrence_index == 0
    assert _units()[0].agent[span.start : span.end] == "preference saved."
    assert "I recommend tea." not in _units()[0].agent[span.start : span.end]
    assert loaded.for_turn("candidate-a", 1) == ()


@pytest.mark.parametrize(
    ("turns", "version", "message"),
    [
        ([], SOURCE_SEGMENTS_VERSION, "missing|marker"),
        ([_entry(candidate_id="candidate-b")], SOURCE_SEGMENTS_VERSION, "candidate|coordinate"),
        ([_entry(turn_index=1)], SOURCE_SEGMENTS_VERSION, "marker|entry"),
        ([_entry(agent_sha256="0" * 64)], SOURCE_SEGMENTS_VERSION, "SHA256"),
        ([_entry(tool_results=[])], SOURCE_SEGMENTS_VERSION, "tool_results"),
        ([_entry(tool_results=[{"quote": "missing", "occurrence_index": 0, "marker_occurrence_index": 0}])], SOURCE_SEGMENTS_VERSION, "quote occurrence"),
        ([_entry(tool_results=[{"quote": "[工具结果]", "occurrence_index": 0, "marker_occurrence_index": 0}])], SOURCE_SEGMENTS_VERSION, "marker"),
        (
            [_entry(tool_results=[
                {"quote": "preference saved.", "occurrence_index": 0, "marker_occurrence_index": 0},
                {"quote": "saved.", "occurrence_index": 0, "marker_occurrence_index": 0},
            ])],
            SOURCE_SEGMENTS_VERSION,
            "overlap",
        ),
        ([_entry(), _entry()], SOURCE_SEGMENTS_VERSION, "duplicate"),
        ([_entry()], "wrong-version", "version"),
    ],
)
def test_load_source_segments_rejects_missing_stale_or_ambiguous_annotations(
    tmp_path: Path, turns: list[dict[str, object]], version: object, message: str
) -> None:
    path = tmp_path / "source-segments.json"
    _write(path, turns, version)

    with pytest.raises(ValueError, match=message):
        load_source_segments(path, _units())


def test_load_source_segments_rejects_entry_for_markerless_agent(tmp_path: Path) -> None:
    path = tmp_path / "source-segments.json"
    markerless = _units()[1]
    extra = {
        "candidate_id": markerless.candidate_id,
        "turn_index": markerless.turn_index,
        "agent_sha256": hashlib.sha256(markerless.agent.encode("utf-8")).hexdigest(),
        "tool_results": [{"quote": "welcome", "occurrence_index": 0, "marker_occurrence_index": 0}],
    }
    _write(path, [_entry(), extra])

    with pytest.raises(ValueError, match="marker|must not"):
        load_source_segments(path, _units())


@pytest.mark.parametrize(
    ("quote", "marker_index", "message"),
    [
        ("I recommend tea.", 0, "first character|later|start"),
        ("preference saved.", 1, "marker.*index|coverage|0"),
    ],
)
def test_load_source_segments_rejects_later_prose_or_wrong_marker_index(
    tmp_path: Path, quote: str, marker_index: int, message: str
) -> None:
    path = tmp_path / "source-segments.json"
    _write(path, [_entry(tool_results=[{
        "quote": quote,
        "occurrence_index": 0,
        "marker_occurrence_index": marker_index,
    }])])

    with pytest.raises(ValueError, match=message):
        load_source_segments(path, _units())


def test_load_source_segments_rejects_pre_result_tool_call_span(tmp_path: Path) -> None:
    unit = TurnUnit(
        candidate_id="candidate-a", candidate_index=0, turn_index=0, source="synthetic",
        user="save", agent="[工具调用] save() [工具结果] saved.",
        user_pointer="/candidates/0/turns/0/user", agent_pointer="/candidates/0/turns/0/agent",
    )
    path = tmp_path / "source-segments.json"
    entry = {
        "candidate_id": unit.candidate_id,
        "turn_index": 0,
        "agent_sha256": hashlib.sha256(unit.agent.encode("utf-8")).hexdigest(),
        "tool_results": [{"quote": "save()", "occurrence_index": 0, "marker_occurrence_index": 0}],
    }
    _write(path, [entry])

    with pytest.raises(ValueError, match="after|first character|start"):
        load_source_segments(path, (unit,))


def test_load_source_segments_requires_one_item_per_result_marker(tmp_path: Path) -> None:
    unit = TurnUnit(
        candidate_id="candidate-a", candidate_index=0, turn_index=0, source="synthetic",
        user="save", agent="[工具结果] first [工具调用] next() [工具结果] second",
        user_pointer="/candidates/0/turns/0/user", agent_pointer="/candidates/0/turns/0/agent",
    )
    path = tmp_path / "source-segments.json"
    entry = {
        "candidate_id": unit.candidate_id,
        "turn_index": 0,
        "agent_sha256": hashlib.sha256(unit.agent.encode("utf-8")).hexdigest(),
        "tool_results": [{"quote": "first ", "occurrence_index": 0, "marker_occurrence_index": 0}],
    }
    _write(path, [entry])

    with pytest.raises(ValueError, match="marker|coverage|exactly"):
        load_source_segments(path, (unit,))
