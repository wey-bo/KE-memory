from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tools.natural_memory_benchmark.dense_runner import run_dense_reference
from tools.natural_memory_benchmark.io import write_json_immutable
from tools.natural_memory_benchmark.scoring import score_results


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "tools.natural_memory_benchmark.cli", *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _toy_payloads():
    slice_payload = {
        "schema_version": "natural-benchmark-slice-v1",
        "slice_id": "toy-slice",
        "source_manifest_sha256": "0" * 64,
        "selection_policy": {},
        "public_items": [
            {"benchmark": "beam", "item_id": "I1", "source_id": "s", "source_index": 0, "source_ref": "r1", "question": "alpha target", "slice_group": "knowledge_update"},
            {"benchmark": "beam", "item_id": "I2", "source_id": "s", "source_index": 1, "source_ref": "r2", "question": "beta target", "slice_group": "knowledge_update"},
        ],
    }
    gold_payload = {
        "schema_version": "natural-benchmark-gold-v1",
        "slice_id": "toy-slice",
        "source_manifest_sha256": "0" * 64,
        "items": [
            {"benchmark": "beam", "item_id": "I1", "source_id": "s", "source_ref": "r1", "slice_group": "knowledge_update", "category": "knowledge_update", "answer": "alpha", "answer_policy": "gold", "evidence_refs": ["E-alpha"], "metadata": {}},
            {"benchmark": "beam", "item_id": "I2", "source_id": "s", "source_ref": "r2", "slice_group": "knowledge_update", "category": "knowledge_update", "answer": "beta", "answer_policy": "gold", "evidence_refs": ["E-beta"], "metadata": {}},
        ],
    }
    corpus_payload = {
        "schema_version": "natural-benchmark-evidence-corpus-v1",
        "slice_id": "toy-slice",
        "item_count": 2,
        "items": {
            "I1": [
                {"benchmark": "beam", "source_id": "s", "unit_id": "E-noise", "source_ref": "n", "text": "unrelated text", "metadata": {}},
                {"benchmark": "beam", "source_id": "s", "unit_id": "E-alpha", "source_ref": "a", "text": "alpha target evidence", "metadata": {}},
            ],
            "I2": [
                {"benchmark": "beam", "source_id": "s", "unit_id": "E-beta", "source_ref": "b", "text": "beta target evidence", "metadata": {}},
                {"benchmark": "beam", "source_id": "s", "unit_id": "E-noise-2", "source_ref": "n2", "text": "other words", "metadata": {}},
            ],
        },
    }
    return slice_payload, gold_payload, corpus_payload


def test_run_dense_reference_uses_encoder_and_scores_evidence():
    slice_payload, gold_payload, corpus_payload = _toy_payloads()

    results = run_dense_reference(
        slice_payload,
        corpus_payload,
        run_id="toy-run",
        top_k=1,
        encoder=lambda texts: [[1.0 if "alpha" in text else 0.0, 1.0 if "beta" in text else 0.0] for text in texts],
    )

    assert results["arm"] == "dense_reference"
    assert [item["retrieved_evidence_refs"] for item in results["items"]] == [["E-alpha"], ["E-beta"]]
    assert all(not item["fallback_triggered"] for item in results["items"])
    report = score_results(slice_payload, gold_payload, results)
    assert report["evidence_set_exact_match"] == 1.0
    assert report["evidence_recall"] == 1.0


def test_run_dense_reference_outputs_json_serializable_scores():
    import numpy as np

    slice_payload, _gold_payload, corpus_payload = _toy_payloads()

    results = run_dense_reference(
        slice_payload,
        corpus_payload,
        run_id="toy-numpy-run",
        top_k=1,
        encoder=lambda texts: [[np.float32(1.0 if "alpha" in text else 0.0), np.float32(1.0 if "beta" in text else 0.0)] for text in texts],
    )

    json.dumps(results)


def test_run_dense_reference_batches_unique_texts_once():
    slice_payload, _gold_payload, corpus_payload = _toy_payloads()
    calls: list[list[str]] = []

    def encoder(texts: list[str]) -> list[list[float]]:
        calls.append(texts)
        return [[1.0 if "alpha" in text else 0.0, 1.0 if "beta" in text else 0.0] for text in texts]

    run_dense_reference(
        slice_payload,
        corpus_payload,
        run_id="toy-batch-run",
        top_k=1,
        encoder=encoder,
    )

    assert len(calls) == 1
    assert len(calls[0]) == len(set(calls[0]))


def test_cli_run_dense_reference_with_lexical_encoder(tmp_path):
    slice_payload, _gold_payload, corpus_payload = _toy_payloads()
    slice_path = tmp_path / "slice.json"
    corpus_path = tmp_path / "corpus.json"
    output_path = tmp_path / "dense-results.json"
    write_json_immutable(slice_path, slice_payload)
    write_json_immutable(corpus_path, corpus_payload)

    result = _run_cli(
        "run-dense-reference",
        "--slice",
        str(slice_path),
        "--corpus",
        str(corpus_path),
        "--output",
        str(output_path),
        "--run-id",
        "toy-cli",
        "--top-k",
        "1",
        "--encoder",
        "lexical",
    )

    assert "valid" in result.stdout
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["arm"] == "dense_reference"
    assert payload["items"][0]["retrieved_evidence_refs"] == ["E-alpha"]
