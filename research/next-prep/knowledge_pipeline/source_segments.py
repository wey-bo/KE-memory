"""Strict loading of human-annotated tool-result source segments."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Iterable

from knowledge_pipeline.source import TurnUnit


SOURCE_SEGMENTS_VERSION = "source-segments-v1"
TOOL_RESULT_MARKER = "[\u5de5\u5177\u7ed3\u679c]"
TOOL_MARKER_PATTERN = re.compile(r"\[(?:\u5de5\u5177\u8c03\u7528|\u5de5\u5177\u7ed3\u679c)\]")


@dataclass(frozen=True, slots=True)
class ToolResultSpan:
    quote: str
    occurrence_index: int
    marker_occurrence_index: int
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class SourceSegments:
    version: str
    path: Path
    sha256: str
    turns: dict[tuple[str, int], tuple[ToolResultSpan, ...]]

    def for_turn(self, candidate_id: str, turn_index: int) -> tuple[ToolResultSpan, ...]:
        return self.turns.get((candidate_id, turn_index), ())


def tool_marker_ranges(agent: str) -> tuple[tuple[int, int], ...]:
    return tuple((match.start(), match.end()) for match in TOOL_MARKER_PATTERN.finditer(agent))


def validate_tool_result_spans(agent: str, spans: tuple[ToolResultSpan, ...]) -> None:
    all_markers = list(TOOL_MARKER_PATTERN.finditer(agent))
    result_markers = [marker for marker in all_markers if marker.group() == TOOL_RESULT_MARKER]
    if result_markers and not spans:
        raise ValueError("agent messages with a tool result marker require explicit tool_result_spans")
    if not result_markers and spans:
        raise ValueError("markerless agent messages must not have tool_result_spans")
    marker_indices = [span.marker_occurrence_index for span in spans]
    if len(spans) != len(result_markers) or sorted(marker_indices) != list(range(len(result_markers))):
        raise ValueError("tool_result_spans must uniquely cover every result marker occurrence index")
    prior_end = -1
    for span in spans:
        if span.start < 0 or span.end <= span.start or span.end > len(agent):
            raise ValueError("tool_result_spans contain invalid coordinates")
        if agent[span.start:span.end] != span.quote or TOOL_MARKER_PATTERN.search(span.quote):
            raise ValueError("tool_result_spans do not match explicit source text")
        expected_start, expected_end = _resolve_occurrence(agent, span.quote, span.occurrence_index)
        if (span.start, span.end) != (expected_start, expected_end):
            raise ValueError("tool_result_spans occurrence coordinates are invalid")
        marker = result_markers[span.marker_occurrence_index]
        required_start = marker.end()
        while required_start < len(agent) and agent[required_start].isspace():
            required_start += 1
        if span.start != required_start:
            raise ValueError("tool result span start must be the first non-whitespace character after its result marker")
        next_marker_start = next(
            (candidate.start() for candidate in all_markers if candidate.start() > marker.start()),
            len(agent),
        )
        if span.end > next_marker_start:
            raise ValueError("tool result span must end before the next tool marker")
        if span.start < prior_end:
            raise ValueError("tool_result_spans must not overlap")
        prior_end = span.end


def parse_tool_result_spans(value: object, agent: str) -> tuple[ToolResultSpan, ...]:
    if not isinstance(value, list):
        raise ValueError("tool_result_spans must be a list")
    spans: list[ToolResultSpan] = []
    for item in value:
        if not isinstance(item, dict) or set(item) != {
            "quote", "occurrence_index", "marker_occurrence_index", "start", "end",
        }:
            raise ValueError("tool_result_spans contain an invalid entry")
        quote = item["quote"]
        occurrence_index = item["occurrence_index"]
        marker_occurrence_index = item["marker_occurrence_index"]
        start = item["start"]
        end = item["end"]
        if (
            not isinstance(quote, str)
            or not quote.strip()
            or not isinstance(occurrence_index, int)
            or isinstance(occurrence_index, bool)
            or occurrence_index < 0
            or not isinstance(marker_occurrence_index, int)
            or isinstance(marker_occurrence_index, bool)
            or marker_occurrence_index < 0
            or not isinstance(start, int)
            or isinstance(start, bool)
            or not isinstance(end, int)
            or isinstance(end, bool)
        ):
            raise ValueError("tool_result_spans contain invalid field types")
        spans.append(ToolResultSpan(quote, occurrence_index, marker_occurrence_index, start, end))
    result = tuple(spans)
    validate_tool_result_spans(agent, result)
    return result


def _non_blank(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _resolve_occurrence(text: str, quote: str, occurrence_index: int) -> tuple[int, int]:
    starts: list[int] = []
    start = text.find(quote)
    while start != -1:
        starts.append(start)
        start = text.find(quote, start + 1)
    if occurrence_index >= len(starts):
        raise ValueError("tool result quote occurrence is missing or out of range")
    start = starts[occurrence_index]
    return start, start + len(quote)


def load_source_segments(path: str | Path, units: Iterable[TurnUnit]) -> SourceSegments:
    """Validate and resolve the complete source-segment sidecar for source turns."""
    source_path = Path(path).resolve()
    try:
        content = source_path.read_bytes()
        document = json.loads(content)
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"could not parse source-segments.json: {error}") from error
    if not isinstance(document, dict) or set(document) != {"version", "turns"}:
        raise ValueError("source segments must contain only version and turns")
    if document["version"] != SOURCE_SEGMENTS_VERSION:
        raise ValueError(f"source segments version must be {SOURCE_SEGMENTS_VERSION}")
    if not isinstance(document["turns"], list):
        raise ValueError("source segments turns must be a list")

    turn_units = tuple(units)
    unit_by_key = {(unit.candidate_id, unit.turn_index): unit for unit in turn_units}
    if len(unit_by_key) != len(turn_units):
        raise ValueError("source turns contain duplicate candidate/turn coordinates")
    annotated: dict[tuple[str, int], tuple[ToolResultSpan, ...]] = {}
    for entry in document["turns"]:
        if not isinstance(entry, dict) or set(entry) != {
            "candidate_id", "turn_index", "agent_sha256", "tool_results",
        }:
            raise ValueError("source segment turn entry has an unexpected schema")
        candidate_id = _non_blank(entry["candidate_id"], "candidate_id")
        turn_index = entry["turn_index"]
        if not isinstance(turn_index, int) or isinstance(turn_index, bool) or turn_index < 0:
            raise ValueError("source segment turn_index must be a non-negative integer")
        key = (candidate_id, turn_index)
        if key in annotated:
            raise ValueError("source segments contain a duplicate candidate/turn entry")
        unit = unit_by_key.get(key)
        if unit is None:
            raise ValueError("source segment candidate/turn coordinate is unknown")
        if TOOL_RESULT_MARKER not in unit.agent:
            raise ValueError("markerless agent messages must not have source segment entries")
        agent_sha256 = _non_blank(entry["agent_sha256"], "agent_sha256")
        if agent_sha256 != hashlib.sha256(unit.agent.encode("utf-8")).hexdigest():
            raise ValueError("source segment agent SHA256 does not match the source turn")
        tool_results = entry["tool_results"]
        if not isinstance(tool_results, list) or not tool_results:
            raise ValueError("source segment tool_results must be a non-empty list")
        spans: list[ToolResultSpan] = []
        all_markers = list(TOOL_MARKER_PATTERN.finditer(unit.agent))
        result_markers = [marker for marker in all_markers if marker.group() == TOOL_RESULT_MARKER]
        for result in tool_results:
            if not isinstance(result, dict) or set(result) != {
                "quote", "occurrence_index", "marker_occurrence_index",
            }:
                raise ValueError("tool result annotation has an unexpected schema")
            quote = _non_blank(result["quote"], "tool result quote")
            if TOOL_MARKER_PATTERN.search(quote):
                raise ValueError("tool result spans must not contain a tool marker")
            occurrence_index = result["occurrence_index"]
            if not isinstance(occurrence_index, int) or isinstance(occurrence_index, bool) or occurrence_index < 0:
                raise ValueError("tool result occurrence_index must be a non-negative integer")
            marker_occurrence_index = result["marker_occurrence_index"]
            if (
                not isinstance(marker_occurrence_index, int)
                or isinstance(marker_occurrence_index, bool)
                or marker_occurrence_index < 0
            ):
                raise ValueError("tool result marker_occurrence_index must be a non-negative integer")
            start, end = _resolve_occurrence(unit.agent, quote, occurrence_index)
            if end <= start:
                raise ValueError("tool result spans must be non-empty")
            spans.append(ToolResultSpan(quote, occurrence_index, marker_occurrence_index, start, end))
        spans.sort(key=lambda item: (item.start, item.end))
        if any(current.start < previous.end for previous, current in zip(spans, spans[1:])):
            raise ValueError("tool result spans must not overlap")
        resolved_spans = tuple(spans)
        validate_tool_result_spans(unit.agent, resolved_spans)
        annotated[key] = resolved_spans

    marker_turns = {
        (unit.candidate_id, unit.turn_index)
        for unit in turn_units
        if TOOL_RESULT_MARKER in unit.agent
    }
    missing = marker_turns - set(annotated)
    extra = set(annotated) - marker_turns
    if missing:
        raise ValueError("every agent message containing a tool result marker requires exactly one source segment turn entry")
    if extra:
        raise ValueError("agent messages without a tool result marker must not have source segment entries")
    return SourceSegments(
        version=SOURCE_SEGMENTS_VERSION,
        path=source_path,
        sha256=hashlib.sha256(content).hexdigest(),
        turns=annotated,
    )
