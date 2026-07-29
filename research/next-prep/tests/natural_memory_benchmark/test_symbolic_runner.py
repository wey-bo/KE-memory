from __future__ import annotations

import json
import subprocess
import sys

from tools.natural_memory_benchmark.io import write_json_immutable
from tools.natural_memory_benchmark.scoring import score_results
from tools.natural_memory_benchmark.symbolic_runner import run_symbolic


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
        "slice_id": "toy-symbolic",
        "source_manifest_sha256": "0" * 64,
        "selection_policy": {},
        "public_items": [
            {
                "benchmark": "locomo",
                "item_id": "I-role",
                "source_id": "s",
                "source_index": 0,
                "source_ref": "sample_id=toy",
                "question": "What status did Alice set for order 42?",
                "slice_group": "role_binding",
            },
            {
                "benchmark": "beam",
                "item_id": "I-abstain",
                "source_id": "s",
                "source_index": 1,
                "source_ref": "conversation_id=toy",
                "question": "What was the user's birthplace?",
                "slice_group": "abstention",
            },
            {
                "benchmark": "beam",
                "item_id": "I-generic-abstain",
                "source_id": "s",
                "source_index": 2,
                "source_ref": "conversation_id=toy",
                "question": "my background and previous development projects",
                "slice_group": "abstention",
            },
        ],
    }
    gold_payload = {
        "schema_version": "natural-benchmark-gold-v1",
        "slice_id": "toy-symbolic",
        "source_manifest_sha256": "0" * 64,
        "items": [
            {
                "benchmark": "locomo",
                "item_id": "I-role",
                "source_id": "s",
                "source_ref": "sample_id=toy",
                "slice_group": "role_binding",
                "category": "role_binding",
                "answer": "shipped",
                "answer_policy": "gold",
                "evidence_refs": ["E-alice-order"],
                "metadata": {},
            },
            {
                "benchmark": "beam",
                "item_id": "I-abstain",
                "source_id": "s",
                "source_ref": "conversation_id=toy",
                "slice_group": "abstention",
                "category": "abstention",
                "answer": "No information is available.",
                "answer_policy": "gold",
                "evidence_refs": [],
                "metadata": {},
            },
            {
                "benchmark": "beam",
                "item_id": "I-generic-abstain",
                "source_id": "s",
                "source_ref": "conversation_id=toy",
                "slice_group": "abstention",
                "category": "abstention",
                "answer": "No information is available.",
                "answer_policy": "gold",
                "evidence_refs": [],
                "metadata": {},
            },
        ],
    }
    corpus_payload = {
        "schema_version": "natural-benchmark-evidence-corpus-v1",
        "slice_id": "toy-symbolic",
        "item_count": 2,
        "items": {
            "I-role": [
                {
                    "benchmark": "locomo",
                    "source_id": "s",
                    "unit_id": "E-bob-order",
                    "source_ref": "sample_id=toy;dia_id=1",
                    "text": "Bob set order 42 to cancelled.",
                    "metadata": {"speaker": "Bob"},
                },
                {
                    "benchmark": "locomo",
                    "source_id": "s",
                    "unit_id": "E-alice-order",
                    "source_ref": "sample_id=toy;dia_id=2",
                    "text": "Alice set order 42 to shipped.",
                    "metadata": {"speaker": "Alice"},
                },
            ],
            "I-abstain": [
                {
                    "benchmark": "beam",
                    "source_id": "s",
                    "unit_id": "E-noise",
                    "source_ref": "conversation_id=toy;message_id=1",
                    "text": "The user discussed project deadlines and dashboard latency.",
                    "metadata": {},
                }
            ],
            "I-generic-abstain": [
                {
                    "benchmark": "beam",
                    "source_id": "s",
                    "unit_id": "E-generic-dev",
                    "source_ref": "conversation_id=toy;message_id=2",
                    "text": "The previous migration step updated a background job for a development database project.",
                    "metadata": {},
                }
            ],
        },
    }
    corpus_payload["items"]["I-generic-abstain"].extend(
        {
            "benchmark": "beam",
            "source_id": "s",
            "unit_id": f"E-unrelated-{offset}",
            "source_ref": f"conversation_id=toy;message_id={offset + 3}",
            "text": "The user discussed dashboard latency and Flask sessions.",
            "metadata": {},
        }
        for offset in range(20)
    )
    return slice_payload, gold_payload, corpus_payload


def test_run_symbolic_filters_by_role_and_exact_cues():
    slice_payload, gold_payload, corpus_payload = _toy_payloads()

    results = run_symbolic(slice_payload, corpus_payload, run_id="symbolic-toy", top_k=3)

    assert results["arm"] == "symbolic"
    assert results["items"][0]["retrieved_evidence_refs"] == ["E-alice-order"]
    assert results["items"][0]["fallback_triggered"] is False
    report = score_results(slice_payload, gold_payload, results)
    assert report["evidence_set_exact_match"] == 1.0
    assert report["critical_false_positive_count"] == 0


def test_run_symbolic_abstains_when_no_symbolic_evidence_matches():
    slice_payload, _gold_payload, corpus_payload = _toy_payloads()

    results = run_symbolic(slice_payload, corpus_payload, run_id="symbolic-toy", top_k=3)

    abstention = results["items"][1]
    assert abstention["retrieved_evidence_refs"] == []
    assert abstention["abstained"] is True
    assert abstention["fallback_triggered"] is False

    generic_abstention = results["items"][2]
    assert generic_abstention["retrieved_evidence_refs"] == []
    assert generic_abstention["abstained"] is True


def test_cli_run_symbolic_writes_results(tmp_path):
    slice_payload, _gold_payload, corpus_payload = _toy_payloads()
    slice_path = tmp_path / "slice.json"
    corpus_path = tmp_path / "corpus.json"
    output_path = tmp_path / "symbolic-results.json"
    write_json_immutable(slice_path, slice_payload)
    write_json_immutable(corpus_path, corpus_payload)

    result = _run_cli(
        "run-symbolic",
        "--slice",
        str(slice_path),
        "--corpus",
        str(corpus_path),
        "--output",
        str(output_path),
        "--run-id",
        "symbolic-cli",
        "--top-k",
        "3",
    )

    assert "valid" in result.stdout
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["arm"] == "symbolic"
    assert payload["items"][0]["retrieved_evidence_refs"] == ["E-alice-order"]
