"""Recover exact English pilot inputs from authorized public source files."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal, Mapping

import duckdb

from tools.amr_pilot.inputs import PilotInputs, load_and_validate_inputs, write_input_manifest
from tools.amr_pilot.models import SentenceSample, SourceCoordinate, SourceRecord


SELECTION_SCHEMA = "amr-pilot-selection-v1"
SourceKind = Literal["taskmaster_json", "tau_json", "beam_parquet"]


def _read_json(path: str | Path) -> object:
    source_path = Path(path)
    try:
        return json.loads(source_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"could not parse {source_path}: {error}") from error


def _file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract_taskmaster_message(path: str | Path, conversation_id: str, utterance_index: int) -> tuple[str, str]:
    document = _read_json(path)
    if not isinstance(document, list):
        raise ValueError("Taskmaster source must be a list")
    matches = [item for item in document if isinstance(item, dict) and item.get("conversation_id") == conversation_id]
    if len(matches) != 1:
        raise ValueError(f"Taskmaster conversation match count is {len(matches)}")
    utterances = matches[0].get("utterances")
    if not isinstance(utterances, list):
        raise ValueError("Taskmaster utterances are missing")
    messages = [item for item in utterances if isinstance(item, dict) and item.get("index") == utterance_index]
    if len(messages) != 1:
        raise ValueError(f"Taskmaster utterance match count is {len(messages)}")
    message = messages[0]
    text = message.get("text")
    speaker = {"USER": "user", "ASSISTANT": "agent"}.get(message.get("speaker"))
    if not isinstance(text, str) or not text or speaker is None:
        raise ValueError("Taskmaster message is incomplete")
    return text, speaker


def extract_tau_message(path: str | Path, record_index: int, traj_index: int) -> tuple[str, str]:
    document = _read_json(path)
    if not isinstance(document, list) or record_index < 0 or record_index >= len(document):
        raise ValueError("tau-bench record index is out of range")
    record = document[record_index]
    if not isinstance(record, dict) or not isinstance(record.get("traj"), list):
        raise ValueError("tau-bench trajectory is missing")
    trajectory = record["traj"]
    if traj_index < 0 or traj_index >= len(trajectory) or not isinstance(trajectory[traj_index], dict):
        raise ValueError("tau-bench trajectory index is out of range")
    message = trajectory[traj_index]
    text = message.get("content")
    speaker = {"user": "user", "assistant": "agent"}.get(message.get("role"))
    if not isinstance(text, str) or not text or speaker is None:
        raise ValueError("tau-bench selection must be a natural user or assistant message")
    return text, speaker


def extract_beam_message(
    path: str | Path,
    conversation_id: str,
    session_index: int,
    message_index: int,
) -> tuple[str, str]:
    connection = duckdb.connect()
    try:
        matches = connection.execute(
            "select chat from read_parquet(?) where conversation_id = ?",
            [str(Path(path)), conversation_id],
        ).fetchall()
    finally:
        connection.close()
    if len(matches) != 1:
        raise ValueError(f"BEAM conversation match count is {len(matches)}")
    chat = matches[0][0]
    if session_index < 0 or session_index >= len(chat):
        raise ValueError("BEAM session index is out of range")
    session = chat[session_index]
    if message_index < 0 or message_index >= len(session):
        raise ValueError("BEAM message index is out of range")
    message = session[message_index]
    text = message.get("content")
    speaker = {"user": "user", "assistant": "agent"}.get(message.get("role"))
    if not isinstance(text, str) or not text or speaker is None:
        raise ValueError("BEAM message is incomplete")
    return text, speaker


def _require_dict(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _require_int(locator: dict[str, object], key: str) -> int:
    value = locator.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"locator {key} must be a non-negative integer")
    return value


def _require_str(locator: dict[str, object], key: str) -> str:
    value = locator.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"locator {key} must be a non-empty string")
    return value


def _extract_message(kind: SourceKind, path: Path, locator: dict[str, object]) -> tuple[str, str]:
    if kind == "taskmaster_json":
        return extract_taskmaster_message(
            path,
            _require_str(locator, "conversation_id"),
            _require_int(locator, "utterance_index"),
        )
    if kind == "tau_json":
        return extract_tau_message(path, _require_int(locator, "record_index"), _require_int(locator, "traj_index"))
    if kind == "beam_parquet":
        return extract_beam_message(
            path,
            _require_str(locator, "conversation_id"),
            _require_int(locator, "session_index"),
            _require_int(locator, "message_index"),
        )
    raise ValueError(f"unsupported source kind: {kind}")


def _locator_strings(kind: SourceKind, locator: dict[str, object]) -> tuple[str, str]:
    if kind == "taskmaster_json":
        return (
            f"conversation_id={_require_str(locator, 'conversation_id')}",
            f"utterance_index={_require_int(locator, 'utterance_index')}",
        )
    if kind == "tau_json":
        task_id = _require_int(locator, "task_id")
        trial = _require_int(locator, "trial")
        return (
            f"record_index={_require_int(locator, 'record_index')};task_id={task_id};trial={trial}",
            f"traj_index={_require_int(locator, 'traj_index')}",
        )
    return (
        f"conversation_id={_require_str(locator, 'conversation_id')};session_index={_require_int(locator, 'session_index')}",
        f"message_index={_require_int(locator, 'message_index')}",
    )


def _write_immutable_json(path: Path, value: object) -> None:
    content = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") == content:
            return
        raise ValueError(f"refusing to overwrite different recovered input: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def recover_selected_inputs(
    selection_path: str | Path,
    source_paths: Mapping[str, str | Path],
    output_dir: str | Path,
    ke_test_path: str | Path,
) -> PilotInputs:
    plan = _require_dict(_read_json(selection_path), "selection plan")
    if set(plan) != {"schema_version", "sources", "samples"} or plan.get("schema_version") != SELECTION_SCHEMA:
        raise ValueError("selection plan schema is invalid")
    source_values = plan.get("sources")
    sample_values = plan.get("samples")
    if not isinstance(source_values, list) or not isinstance(sample_values, list):
        raise ValueError("selection sources and samples must be lists")

    sources: dict[str, dict[str, object]] = {}
    for source_value in source_values:
        source = _require_dict(source_value, "source")
        required = {
            "source_id", "kind", "dataset", "source_url", "source_revision", "source_artifact_sha256",
        }
        if set(source) != required:
            raise ValueError("selection source has unknown or missing fields")
        source_id = source["source_id"]
        if not isinstance(source_id, str) or not source_id or source_id in sources:
            raise ValueError("selection source_id is invalid or duplicated")
        local_path = Path(source_paths.get(source_id, ""))
        if not local_path.is_file():
            raise ValueError(f"local source file is missing for {source_id}")
        if _file_sha256(local_path) != source["source_artifact_sha256"]:
            raise ValueError(f"source artifact hash mismatch for {source_id}")
        source = dict(source)
        source["local_path"] = local_path
        sources[source_id] = source

    samples: list[SentenceSample] = []
    records: dict[str, SourceRecord] = {}
    for sample_value in sample_values:
        selection = _require_dict(sample_value, "sample selection")
        required = {
            "sample_id", "candidate_id", "phenomenon", "source_record_id", "source_id", "locator",
            "sentence", "sentence_occurrence_index",
        }
        if set(selection) != required:
            raise ValueError("sample selection has unknown or missing fields")
        source_id = selection["source_id"]
        if not isinstance(source_id, str) or source_id not in sources:
            raise ValueError("sample source_id is unknown")
        source = sources[source_id]
        kind = source["kind"]
        if kind not in {"taskmaster_json", "tau_json", "beam_parquet"}:
            raise ValueError("source kind is invalid")
        locator = _require_dict(selection["locator"], "locator")
        text, speaker = _extract_message(kind, source["local_path"], locator)  # type: ignore[arg-type]
        if kind == "tau_json":
            tau_document = _read_json(source["local_path"])
            tau_record = tau_document[_require_int(locator, "record_index")]  # type: ignore[index]
            if tau_record.get("task_id") != _require_int(locator, "task_id") or tau_record.get("trial") != _require_int(locator, "trial"):
                raise ValueError("tau-bench task_id or trial does not match the selected record")
        record_locator, message_locator = _locator_strings(kind, locator)
        coordinate = SourceCoordinate.model_validate(
            {
                "dataset": source["dataset"],
                "source_url": source["source_url"],
                "source_revision": source["source_revision"],
                "source_artifact_sha256": source["source_artifact_sha256"],
                "record_locator": record_locator,
                "message_locator": message_locator,
                "speaker": speaker,
            }
        )
        record = SourceRecord.model_validate(
            {
                "source_record_id": selection["source_record_id"],
                "candidate_id": selection["candidate_id"],
                "text": text,
                "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "source": coordinate.model_dump(mode="json"),
            }
        )
        existing = records.get(record.source_record_id)
        if existing is not None and existing != record:
            raise ValueError(f"source record ID has conflicting content: {record.source_record_id}")
        records[record.source_record_id] = record
        sentence = selection["sentence"]
        if not isinstance(sentence, str):
            raise ValueError("selected sentence must be a string")
        samples.append(
            SentenceSample.model_validate(
                {
                    "sample_id": selection["sample_id"],
                    "candidate_id": selection["candidate_id"],
                    "text": sentence,
                    "language": "en",
                    "phenomenon": selection["phenomenon"],
                    "text_sha256": hashlib.sha256(sentence.encode("utf-8")).hexdigest(),
                    "source_record_id": selection["source_record_id"],
                    "sentence_occurrence_index": selection["sentence_occurrence_index"],
                    "source": coordinate.model_dump(mode="json"),
                }
            )
        )

    output = Path(output_dir)
    _write_immutable_json(
        output / "source-records.json",
        {"schema_version": "amr-pilot-source-records-v1", "records": [item.model_dump(mode="json") for item in records.values()]},
    )
    _write_immutable_json(
        output / "sentences.json",
        {"schema_version": "amr-pilot-sentences-v1", "samples": [item.model_dump(mode="json") for item in samples]},
    )
    inputs = load_and_validate_inputs(output / "sentences.json", output / "source-records.json", ke_test_path)
    write_input_manifest(inputs, output / "manifest.json")
    return inputs
