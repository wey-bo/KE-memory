from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tools.amr_pilot.inputs import load_and_validate_inputs, write_input_manifest


PHENOMENA = (
    "event_roles",
    "time_quantity_condition",
    "negation_modality_intent",
    "causality_comparison_multiclause",
)


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    candidates = [{"id": f"CAND-{index}", "source": "fixture", "turns": []} for index in range(12)]
    ke_test = tmp_path / "KE-test.json"
    ke_test.write_text(json.dumps({"candidates": candidates}), encoding="utf-8")

    records: list[dict[str, object]] = []
    samples: list[dict[str, object]] = []
    for index in range(12):
        number = index + 1
        sentence = f"Person {number} completed task {number} on Tuesday."
        source_text = f"Context sentence. {sentence} Closing sentence."
        source = {
            "dataset": "Synthetic",
            "source_url": "https://example.test/source",
            "source_revision": "fixture-revision",
            "source_artifact_sha256": "4" * 64,
            "record_locator": f"record={number}",
            "message_locator": f"message={number}",
            "speaker": "user",
        }
        records.append(
            {
                "source_record_id": f"SRC-{number:03d}",
                "candidate_id": f"CAND-{index}",
                "text": source_text,
                "text_sha256": sha256(source_text),
                "source": source,
            }
        )
        samples.append(
            {
                "sample_id": f"AMR-S{number:03d}",
                "candidate_id": f"CAND-{index}",
                "text": sentence,
                "language": "en",
                "phenomenon": PHENOMENA[index // 3],
                "text_sha256": sha256(sentence),
                "source_record_id": f"SRC-{number:03d}",
                "sentence_occurrence_index": 0,
                "source": source,
            }
        )

    records_path = tmp_path / "source-records.json"
    records_path.write_text(
        json.dumps({"schema_version": "amr-pilot-source-records-v1", "records": records}),
        encoding="utf-8",
    )
    samples_path = tmp_path / "sentences.json"
    samples_path.write_text(
        json.dumps({"schema_version": "amr-pilot-sentences-v1", "samples": samples}),
        encoding="utf-8",
    )
    return samples_path, records_path, ke_test


def test_load_inputs_accepts_exactly_twelve_balanced_source_bound_sentences(tmp_path: Path) -> None:
    samples_path, records_path, ke_test = write_fixture(tmp_path)

    result = load_and_validate_inputs(samples_path, records_path, ke_test)

    assert len(result.samples) == 12
    assert len(result.source_records) == 12
    assert {phenomenon: sum(item.phenomenon == phenomenon for item in result.samples) for phenomenon in PHENOMENA} == {
        phenomenon: 3 for phenomenon in PHENOMENA
    }


def test_load_inputs_rejects_unbalanced_sample_set(tmp_path: Path) -> None:
    samples_path, records_path, ke_test = write_fixture(tmp_path)
    document = json.loads(samples_path.read_text(encoding="utf-8"))
    document["samples"][0]["phenomenon"] = "event_roles"
    document["samples"][3]["phenomenon"] = "event_roles"
    samples_path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="three samples"):
        load_and_validate_inputs(samples_path, records_path, ke_test)


def test_load_inputs_rejects_duplicate_sentence_hashes(tmp_path: Path) -> None:
    samples_path, records_path, ke_test = write_fixture(tmp_path)
    samples = json.loads(samples_path.read_text(encoding="utf-8"))
    records = json.loads(records_path.read_text(encoding="utf-8"))
    samples["samples"][1]["text"] = samples["samples"][0]["text"]
    samples["samples"][1]["text_sha256"] = samples["samples"][0]["text_sha256"]
    records["records"][1]["text"] = records["records"][0]["text"]
    records["records"][1]["text_sha256"] = records["records"][0]["text_sha256"]
    samples_path.write_text(json.dumps(samples), encoding="utf-8")
    records_path.write_text(json.dumps(records), encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate sentence"):
        load_and_validate_inputs(samples_path, records_path, ke_test)


def test_load_inputs_rejects_sentence_not_present_in_source_record(tmp_path: Path) -> None:
    samples_path, records_path, ke_test = write_fixture(tmp_path)
    document = json.loads(samples_path.read_text(encoding="utf-8"))
    document["samples"][0]["text"] = "A paraphrase that is absent from the source."
    document["samples"][0]["text_sha256"] = sha256(document["samples"][0]["text"])
    samples_path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="exact substring"):
        load_and_validate_inputs(samples_path, records_path, ke_test)


def test_load_inputs_rejects_candidate_outside_ke_test(tmp_path: Path) -> None:
    samples_path, records_path, ke_test = write_fixture(tmp_path)
    document = json.loads(samples_path.read_text(encoding="utf-8"))
    document["samples"][0]["candidate_id"] = "UNKNOWN"
    samples_path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="KE-test"):
        load_and_validate_inputs(samples_path, records_path, ke_test)


def test_input_manifest_is_deterministic_and_refuses_different_overwrite(tmp_path: Path) -> None:
    samples_path, records_path, ke_test = write_fixture(tmp_path)
    inputs = load_and_validate_inputs(samples_path, records_path, ke_test)
    manifest_path = tmp_path / "manifest.json"

    first = write_input_manifest(inputs, manifest_path)
    second = write_input_manifest(inputs, manifest_path)

    assert first == second
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert set(manifest) == {
        "schema_version", "sample_count", "phenomenon_counts", "samples_sha256",
        "source_records_sha256", "input_set_sha256",
    }

    manifest_path.write_text('{"changed":true}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="refusing to overwrite"):
        write_input_manifest(inputs, manifest_path)
