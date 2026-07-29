"""Load and bind pilot sentences to exact authorized source records."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Iterable

from tools.amr_pilot.models import Phenomenon, SentenceSample, SourceRecord


SCHEMA_SENTENCES = "amr-pilot-sentences-v1"
SCHEMA_SOURCE_RECORDS = "amr-pilot-source-records-v1"
SCHEMA_MANIFEST = "amr-pilot-input-manifest-v1"
PHENOMENA: tuple[Phenomenon, ...] = (
    "event_roles",
    "time_quantity_condition",
    "negation_modality_intent",
    "causality_comparison_multiclause",
)


@dataclass(frozen=True, slots=True)
class PilotInputs:
    samples: tuple[SentenceSample, ...]
    source_records: tuple[SourceRecord, ...]


def _load_json(path: str | Path) -> object:
    source_path = Path(path)
    try:
        return json.loads(source_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"could not parse {source_path}: {error}") from error


def _require_document(value: object, schema: str, collection_key: str) -> list[object]:
    if not isinstance(value, dict) or set(value) != {"schema_version", collection_key}:
        raise ValueError(f"{schema} document has unknown or missing fields")
    if value["schema_version"] != schema:
        raise ValueError(f"expected schema_version {schema}")
    collection = value[collection_key]
    if not isinstance(collection, list):
        raise ValueError(f"{collection_key} must be a list")
    return collection


def _candidate_ids(ke_test_path: str | Path) -> set[str]:
    value = _load_json(ke_test_path)
    if not isinstance(value, dict) or set(value) != {"candidates"} or not isinstance(value["candidates"], list):
        raise ValueError("KE-test.json must contain only a candidates list")
    result: set[str] = set()
    for candidate in value["candidates"]:
        if not isinstance(candidate, dict) or not isinstance(candidate.get("id"), str):
            raise ValueError("KE-test candidate is missing id")
        result.add(candidate["id"])
    return result


def _occurrence_starts(text: str, quote: str) -> tuple[int, ...]:
    starts: list[int] = []
    start = text.find(quote)
    while start != -1:
        starts.append(start)
        start = text.find(quote, start + 1)
    return tuple(starts)


def load_and_validate_inputs(
    sentences_path: str | Path,
    source_records_path: str | Path,
    ke_test_path: str | Path,
) -> PilotInputs:
    sample_values = _require_document(_load_json(sentences_path), SCHEMA_SENTENCES, "samples")
    record_values = _require_document(_load_json(source_records_path), SCHEMA_SOURCE_RECORDS, "records")
    samples = tuple(SentenceSample.model_validate(value) for value in sample_values)
    records = tuple(SourceRecord.model_validate(value) for value in record_values)

    if len(samples) != 12:
        raise ValueError("pilot requires exactly 12 samples")
    expected_ids = [f"AMR-S{index:03d}" for index in range(1, 13)]
    if [sample.sample_id for sample in samples] != expected_ids:
        raise ValueError("sample IDs must be ordered AMR-S001 through AMR-S012")
    counts = Counter(sample.phenomenon for sample in samples)
    if any(counts[phenomenon] != 3 for phenomenon in PHENOMENA):
        raise ValueError("pilot requires exactly three samples per phenomenon")
    if len({sample.text_sha256 for sample in samples}) != len(samples):
        raise ValueError("duplicate sentence text is not allowed")

    record_by_id: dict[str, SourceRecord] = {}
    for record in records:
        if record.source_record_id in record_by_id:
            raise ValueError(f"duplicate source record ID: {record.source_record_id}")
        record_by_id[record.source_record_id] = record
    allowed_candidates = _candidate_ids(ke_test_path)
    for sample in samples:
        if sample.candidate_id not in allowed_candidates:
            raise ValueError(f"sample {sample.sample_id} candidate is not in KE-test")
        record = record_by_id.get(sample.source_record_id)
        if record is None:
            raise ValueError(f"sample {sample.sample_id} source record is missing")
        if record.candidate_id != sample.candidate_id or record.source != sample.source:
            raise ValueError(f"sample {sample.sample_id} source coordinate does not match its record")
        starts = _occurrence_starts(record.text, sample.text)
        if sample.sentence_occurrence_index >= len(starts):
            raise ValueError(f"sample {sample.sample_id} is not an exact substring occurrence of its source record")

    return PilotInputs(samples=samples, source_records=records)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _models_dump(items: Iterable[SentenceSample | SourceRecord]) -> list[dict[str, object]]:
    return [item.model_dump(mode="json") for item in items]


def write_input_manifest(inputs: PilotInputs, path: str | Path) -> Path:
    samples = _models_dump(inputs.samples)
    records = _models_dump(inputs.source_records)
    phenomenon_counts = dict(sorted(Counter(sample.phenomenon for sample in inputs.samples).items()))
    samples_sha256 = _sha256(samples)
    source_records_sha256 = _sha256(records)
    manifest = {
        "schema_version": SCHEMA_MANIFEST,
        "sample_count": len(samples),
        "phenomenon_counts": phenomenon_counts,
        "samples_sha256": samples_sha256,
        "source_records_sha256": source_records_sha256,
        "input_set_sha256": _sha256(
            {"samples_sha256": samples_sha256, "source_records_sha256": source_records_sha256}
        ),
    }
    manifest_path = Path(path)
    content = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if manifest_path.exists():
        if manifest_path.read_text(encoding="utf-8") == content:
            return manifest_path
        raise ValueError(f"refusing to overwrite different input manifest: {manifest_path}")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(content, encoding="utf-8")
    return manifest_path
