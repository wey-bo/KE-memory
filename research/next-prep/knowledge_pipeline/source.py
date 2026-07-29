"""Read KE-test source turns and create isolated extraction inputs."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Iterable


PROMPT_VERSION = "knowledge-extraction-turn-v1"


@dataclass(frozen=True, slots=True)
class TurnUnit:
    candidate_id: str
    candidate_index: int
    turn_index: int
    source: str
    user: str
    agent: str
    user_pointer: str
    agent_pointer: str


def _require_non_blank_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value


def load_turn_units(path: str | Path) -> tuple[TurnUnit, ...]:
    """Parse the canonical KE-test dataset without normalizing its text."""
    dataset_path = Path(path)
    if dataset_path.name != "KE-test.json":
        raise ValueError("only KE-test.json may be loaded")
    try:
        document = json.loads(dataset_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"could not parse KE-test.json: {error}") from error

    if not isinstance(document, dict) or set(document) != {"candidates"}:
        raise ValueError("KE-test.json must contain only candidates")
    candidates = document["candidates"]
    if not isinstance(candidates, list):
        raise ValueError("candidates must be a list")

    units: list[TurnUnit] = []
    candidate_ids: set[str] = set()
    for candidate_index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict) or set(candidate) != {"id", "source", "turns"}:
            raise ValueError(f"candidate {candidate_index} has unknown or missing fields")
        candidate_id = _require_non_blank_string(candidate["id"], "candidate id")
        if candidate_id in candidate_ids:
            raise ValueError(f"duplicate candidate id: {candidate_id}")
        candidate_ids.add(candidate_id)
        source = _require_non_blank_string(candidate["source"], "candidate source")
        turns = candidate["turns"]
        if not isinstance(turns, list):
            raise ValueError(f"candidate {candidate_index} turns must be a list")
        for turn_index, turn in enumerate(turns):
            if not isinstance(turn, dict) or set(turn) != {"user", "agent"}:
                raise ValueError(f"candidate {candidate_index} turn {turn_index} has unknown or missing fields")
            user = _require_non_blank_string(turn["user"], "user")
            agent = _require_non_blank_string(turn["agent"], "agent")
            pointer = f"/candidates/{candidate_index}/turns/{turn_index}"
            units.append(
                TurnUnit(
                    candidate_id=candidate_id,
                    candidate_index=candidate_index,
                    turn_index=turn_index,
                    source=source,
                    user=user,
                    agent=agent,
                    user_pointer=f"{pointer}/user",
                    agent_pointer=f"{pointer}/agent",
                )
            )
    return tuple(units)


def _payload(unit: TurnUnit) -> dict[str, object]:
    return {
        "candidate_id": unit.candidate_id,
        "candidate_index": unit.candidate_index,
        "turn_index": unit.turn_index,
        "source": unit.source,
        "user": unit.user,
        "agent": unit.agent,
        "user_pointer": unit.user_pointer,
        "agent_pointer": unit.agent_pointer,
        "prompt_version": PROMPT_VERSION,
    }


def write_turn_inputs(units: Iterable[TurnUnit], output_dir: str | Path) -> Path:
    """Write per-turn extraction payloads and an exact-text hash manifest."""
    turn_units = tuple(units)
    turns_dir = Path(output_dir) / "knowledge-extraction" / "inputs" / "turns"
    expected_filenames = {
        f"{unit.candidate_index:04d}-{unit.turn_index:04d}.json" for unit in turn_units
    }
    if turns_dir.is_dir():
        stale_files = sorted(path.name for path in turns_dir.glob("*.json") if path.name not in expected_filenames)
        if stale_files:
            raise ValueError(f"stale managed turn input files: {', '.join(stale_files)}")
    turns_dir.mkdir(parents=True, exist_ok=True)
    manifest_turns: list[dict[str, object]] = []
    for unit in turn_units:
        filename = f"{unit.candidate_index:04d}-{unit.turn_index:04d}.json"
        (turns_dir / filename).write_text(
            json.dumps(_payload(unit), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        manifest_turns.append(
            {
                "candidate_id": unit.candidate_id,
                "candidate_index": unit.candidate_index,
                "turn_index": unit.turn_index,
                "input_file": filename,
                "user_sha256": hashlib.sha256(unit.user.encode("utf-8")).hexdigest(),
                "agent_sha256": hashlib.sha256(unit.agent.encode("utf-8")).hexdigest(),
            }
        )
    manifest_path = turns_dir.parent / "manifest.json"
    manifest_path.write_text(
        json.dumps({"prompt_version": PROMPT_VERSION, "turns": manifest_turns}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest_path
