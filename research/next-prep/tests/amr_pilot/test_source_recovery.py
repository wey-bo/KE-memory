from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from tools.amr_pilot.source_recovery import (
    extract_beam_message,
    extract_taskmaster_message,
    extract_tau_message,
    recover_selected_inputs,
)


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_dataset_adapters_recover_exact_message_and_speaker(tmp_path: Path) -> None:
    taskmaster = tmp_path / "taskmaster.json"
    taskmaster.write_text(
        json.dumps(
            [
                {
                    "conversation_id": "dialogue-1",
                    "utterances": [{"index": 4, "speaker": "USER", "text": "Taskmaster sentence."}],
                }
            ]
        ),
        encoding="utf-8",
    )
    tau = tmp_path / "tau.json"
    tau.write_text(
        json.dumps([{"task_id": 30, "trial": 0, "traj": [{"role": "assistant", "content": "Tau sentence."}]}]),
        encoding="utf-8",
    )
    beam = tmp_path / "beam.parquet"
    table = pa.Table.from_pylist(
        [
            {
                "conversation_id": "19",
                "chat": [
                    [{"role": "user", "content": "Session zero."}],
                    [{"role": "assistant", "content": "BEAM sentence."}],
                ],
            }
        ]
    )
    pq.write_table(table, beam)

    assert extract_taskmaster_message(taskmaster, "dialogue-1", 4) == ("Taskmaster sentence.", "user")
    assert extract_tau_message(tau, 0, 0) == ("Tau sentence.", "agent")
    assert extract_beam_message(beam, "19", 1, 0) == ("BEAM sentence.", "agent")


def test_recovery_writes_valid_source_bound_inputs(tmp_path: Path) -> None:
    source = tmp_path / "taskmaster.json"
    utterances = [
        {"index": index, "speaker": "USER", "text": f"Exact sentence {index + 1}."}
        for index in range(12)
    ]
    source.write_text(json.dumps([{"conversation_id": "dialogue-1", "utterances": utterances}]), encoding="utf-8")
    source_hash = file_sha256(source)
    plan = {
        "schema_version": "amr-pilot-selection-v1",
        "sources": [
            {
                "source_id": "taskmaster",
                "kind": "taskmaster_json",
                "dataset": "Taskmaster-2",
                "source_url": "https://example.test/taskmaster",
                "source_revision": "fixture-revision",
                "source_artifact_sha256": source_hash,
            }
        ],
        "samples": [],
    }
    phenomena = (
        "event_roles",
        "time_quantity_condition",
        "negation_modality_intent",
        "causality_comparison_multiclause",
    )
    for index in range(12):
        plan["samples"].append(
            {
                "sample_id": f"AMR-S{index + 1:03d}",
                "candidate_id": f"CAND-{index}",
                "phenomenon": phenomena[index // 3],
                "source_record_id": f"SRC-{index + 1:03d}",
                "source_id": "taskmaster",
                "locator": {"conversation_id": "dialogue-1", "utterance_index": index},
                "sentence": f"Exact sentence {index + 1}.",
                "sentence_occurrence_index": 0,
            }
        )
    plan_path = tmp_path / "selection.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    ke_test = tmp_path / "KE-test.json"
    ke_test.write_text(
        json.dumps(
            {
                "candidates": [
                    {"id": f"CAND-{index}", "source": "fixture", "turns": []}
                    for index in range(12)
                ]
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "inputs"

    result = recover_selected_inputs(
        plan_path,
        {"taskmaster": source},
        output,
        ke_test,
    )

    assert result.samples[0].text == "Exact sentence 1."
    assert (output / "sentences.json").is_file()
    assert (output / "source-records.json").is_file()
    assert (output / "manifest.json").is_file()
