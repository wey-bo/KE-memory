from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from knowledge_pipeline.cli import main
from knowledge_pipeline.evidence import resolve_evidence
from knowledge_pipeline.source import load_turn_units, write_turn_inputs


DATASET = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "gold-candidates"
    / "KE-test.json"
)


def test_load_turn_units_preserves_expected_dataset_counts_and_first_turn() -> None:
    units = load_turn_units(DATASET)
    raw = json.loads(DATASET.read_text(encoding="utf-8"))

    assert len({unit.candidate_id for unit in units}) == 10
    assert len(units) == 43
    assert sum(2 for _ in units) == 86
    first = units[0]
    assert first.candidate_id == "WILDCHAT-MGMT-CAND-001"
    assert first.candidate_index == 0
    assert first.turn_index == 0
    assert first.user == raw["candidates"][0]["turns"][0]["user"]
    assert first.agent == raw["candidates"][0]["turns"][0]["agent"]
    assert first.user_pointer == "/candidates/0/turns/0/user"
    assert first.agent_pointer == "/candidates/0/turns/0/agent"


def test_load_turn_units_returns_immutable_records() -> None:
    unit = load_turn_units(DATASET)[0]

    with pytest.raises((AttributeError, TypeError)):
        unit.user = "changed"  # type: ignore[misc]


def test_write_turn_inputs_writes_only_isolated_payload_fields(tmp_path: Path) -> None:
    unit = load_turn_units(DATASET)[0]
    manifest_path = write_turn_inputs((unit,), tmp_path)
    payload_path = tmp_path / "knowledge-extraction" / "inputs" / "turns" / "0000-0000.json"
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert set(payload) == {
        "candidate_id", "candidate_index", "turn_index", "source", "user", "agent",
        "user_pointer", "agent_pointer", "prompt_version",
    }
    assert payload["user"] == unit.user
    assert payload["agent"] == unit.agent
    assert set(manifest) == {"prompt_version", "turns"}
    assert manifest["turns"][0]["user_sha256"] == hashlib.sha256(unit.user.encode("utf-8")).hexdigest()
    assert manifest["turns"][0]["agent_sha256"] == hashlib.sha256(unit.agent.encode("utf-8")).hexdigest()


def test_write_turn_inputs_rejects_stale_managed_turn_file_without_writing(tmp_path: Path) -> None:
    unit = load_turn_units(DATASET)[0]
    stale_path = tmp_path / "knowledge-extraction" / "inputs" / "turns" / "stale.json"
    stale_path.parent.mkdir(parents=True)
    stale_path.write_text('{"stale": true}\n', encoding="utf-8")

    with pytest.raises(ValueError, match="stale"):
        write_turn_inputs((unit,), tmp_path)

    assert stale_path.read_text(encoding="utf-8") == '{"stale": true}\n'
    assert not (tmp_path / "knowledge-extraction" / "inputs" / "manifest.json").exists()


def test_load_turn_units_rejects_whitespace_only_required_text(tmp_path: Path) -> None:
    dataset = tmp_path / "KE-test.json"
    dataset.write_text(
        json.dumps({"candidates": [{"id": "candidate", "source": "source", "turns": [{"user": " ", "agent": "agent"}]}]}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="user"):
        load_turn_units(dataset)


def test_load_turn_units_rejects_whitespace_only_candidate_source(tmp_path: Path) -> None:
    dataset = tmp_path / "KE-test.json"
    dataset.write_text(
        json.dumps({"candidates": [{"id": "candidate", "source": "\t ", "turns": [{"user": "user", "agent": "agent"}]}]}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="candidate source"):
        load_turn_units(dataset)


def test_load_turn_units_rejects_duplicate_candidate_ids(tmp_path: Path) -> None:
    dataset = tmp_path / "KE-test.json"
    candidate = {"id": "duplicate-id", "source": "source", "turns": [{"user": "user", "agent": "agent"}]}
    dataset.write_text(json.dumps({"candidates": [candidate, candidate]}), encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate-id"):
        load_turn_units(dataset)


def test_cli_prepare_turns_dispatch_writes_manifest_and_turn_file(tmp_path: Path) -> None:
    output_dir = tmp_path / "prepared"

    assert main(["prepare-turns", "--input", str(DATASET), "--output-dir", str(output_dir)]) == 0
    assert (output_dir / "knowledge-extraction" / "inputs" / "manifest.json").is_file()
    assert (output_dir / "knowledge-extraction" / "inputs" / "turns" / "0000-0000.json").is_file()


def test_resolve_evidence_uses_requested_repeated_quote_occurrence() -> None:
    evidence = resolve_evidence("candidate-a", 7, "again and again", "agent", "again", 1, "agent_generated")

    assert evidence.candidate_id == "candidate-a"
    assert evidence.turn_index == 7
    assert evidence.message == "agent"
    assert evidence.quote == "again"
    assert evidence.evidence_role == "agent_generated"
    assert evidence.start == 10
    assert evidence.end == 15


def test_resolve_evidence_uses_unicode_code_point_offsets() -> None:
    text = "start 😀 target end"
    evidence = resolve_evidence("candidate-a", 3, text, "agent", "target", 0, "tool_observed")

    assert evidence.start == 8
    assert evidence.end == 14
    assert text[evidence.start : evidence.end] == evidence.quote


def test_resolve_evidence_uses_distinct_ids_for_distinct_turn_scopes() -> None:
    first = resolve_evidence("candidate-a", 0, "same", "user", "same", 0, "user_reported")
    second = resolve_evidence("candidate-b", 4, "same", "user", "same", 0, "user_reported")

    assert first.evidence_id != second.evidence_id
    assert (first.candidate_id, first.turn_index) == ("candidate-a", 0)
    assert (second.candidate_id, second.turn_index) == ("candidate-b", 4)


@pytest.mark.parametrize(
    ("quote", "occurrence_index", "message"),
    [("missing", 0, "present"), ("present", 1, "present"), ("present", -1, "present"), ("", 0, "present")],
)
def test_resolve_evidence_rejects_invalid_quote_or_occurrence(
    quote: str, occurrence_index: int, message: str
) -> None:
    with pytest.raises(ValueError):
        resolve_evidence("candidate-a", 0, message, "user", quote, occurrence_index, "user_reported")


def test_resolve_evidence_rejects_invalid_message() -> None:
    with pytest.raises(ValueError):
        resolve_evidence("candidate-a", 0, "text", "tool", "text", 0, "tool_observed")


def test_resolve_evidence_rejects_invalid_evidence_role() -> None:
    with pytest.raises(ValueError):
        resolve_evidence("candidate-a", 0, "text", "agent", "text", 0, "unknown")  # type: ignore[arg-type]
