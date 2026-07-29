from __future__ import annotations

import json
import subprocess
import sys

from tools.natural_memory_benchmark.io import write_json_immutable
from tools.natural_memory_benchmark.scoring import score_results
from tools.natural_memory_benchmark.symbolic_fallback_runner import run_symbolic_fallback


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
        "slice_id": "toy-fallback",
        "source_manifest_sha256": "0" * 64,
        "selection_policy": {},
        "public_items": [
            {
                "benchmark": "locomo",
                "item_id": "I-symbolic",
                "source_id": "s",
                "source_index": 0,
                "source_ref": "sample_id=toy",
                "question": "What status did Alice set for order 42?",
                "slice_group": "role_binding",
            },
            {
                "benchmark": "longmemeval",
                "item_id": "I-fallback",
                "source_id": "s",
                "source_index": 1,
                "source_ref": "question_id=toy",
                "question": "Which fruit did I mention?",
                "slice_group": "single-session-user",
            },
            {
                "benchmark": "beam",
                "item_id": "I-abstain",
                "source_id": "s",
                "source_index": 2,
                "source_ref": "conversation_id=toy",
                "question": "Where was I born?",
                "slice_group": "abstention",
            },
        ],
    }
    gold_payload = {
        "schema_version": "natural-benchmark-gold-v1",
        "slice_id": "toy-fallback",
        "source_manifest_sha256": "0" * 64,
        "items": [
            {
                "benchmark": "locomo",
                "item_id": "I-symbolic",
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
                "benchmark": "longmemeval",
                "item_id": "I-fallback",
                "source_id": "s",
                "source_ref": "question_id=toy",
                "slice_group": "single-session-user",
                "category": "single-session-user",
                "answer": "dragonfruit",
                "answer_policy": "gold",
                "evidence_refs": ["E-dragonfruit"],
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
        ],
    }
    corpus_payload = {
        "schema_version": "natural-benchmark-evidence-corpus-v1",
        "slice_id": "toy-fallback",
        "item_count": 3,
        "items": {
            "I-symbolic": [
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
            "I-fallback": [
                {
                    "benchmark": "longmemeval",
                    "source_id": "s",
                    "unit_id": "E-noise",
                    "source_ref": "question_id=toy;session_id=1",
                    "text": "I discussed a parking receipt.",
                    "metadata": {},
                },
                {
                    "benchmark": "longmemeval",
                    "source_id": "s",
                    "unit_id": "E-dragonfruit",
                    "source_ref": "question_id=toy;session_id=2",
                    "text": "I mentioned dragonfruit during the grocery conversation.",
                    "metadata": {},
                },
            ],
            "I-abstain": [
                {
                    "benchmark": "beam",
                    "source_id": "s",
                    "unit_id": "E-born-noise",
                    "source_ref": "conversation_id=toy;message_id=1",
                    "text": "The app was born from a weekend project.",
                    "metadata": {},
                }
            ],
        },
    }
    return slice_payload, gold_payload, corpus_payload


def _fruit_encoder(texts: list[str]) -> list[list[float]]:
    vectors = []
    for text in texts:
        lowered = text.casefold()
        vectors.append([1.0 if "fruit" in lowered or "dragonfruit" in lowered else 0.0])
    return vectors


def test_symbolic_fallback_only_triggers_for_empty_non_abstention_result():
    slice_payload, gold_payload, corpus_payload = _toy_payloads()

    results = run_symbolic_fallback(
        slice_payload,
        corpus_payload,
        run_id="fallback-toy",
        symbolic_top_k=3,
        fallback_top_k=1,
        encoder=_fruit_encoder,
    )

    symbolic_item, fallback_item, abstention_item = results["items"]
    assert symbolic_item["retrieved_evidence_refs"] == ["E-alice-order"]
    assert symbolic_item["fallback_triggered"] is False
    assert fallback_item["retrieved_evidence_refs"] == ["E-dragonfruit"]
    assert fallback_item["fallback_triggered"] is True
    assert fallback_item["fallback_reason"] == "lexical_predicate_missing_link"
    assert fallback_item["metadata"]["fallback_decision"] == "triggered"
    assert fallback_item["metadata"]["fallback_reason_candidate"] == "lexical_predicate_missing_link"
    assert abstention_item["retrieved_evidence_refs"] == []
    assert abstention_item["fallback_triggered"] is False
    assert abstention_item["metadata"]["fallback_decision"] == "blocked"
    assert abstention_item["metadata"]["fallback_reason_candidate"] == "abstention_or_answerability_missing"

    report = score_results(slice_payload, gold_payload, results)
    assert report["evidence_set_exact_match"] == 1.0
    assert report["critical_false_positive_count"] == 0
    assert report["fallback_trigger_rate"] == 1 / 3


def test_symbolic_fallback_blocks_structural_empty_results():
    slice_payload = {
        "schema_version": "natural-benchmark-slice-v1",
        "slice_id": "toy-structural-block",
        "source_manifest_sha256": "0" * 64,
        "selection_policy": {},
        "public_items": [
            {
                "benchmark": "beam",
                "item_id": "I-structural-empty",
                "source_id": "s",
                "source_index": 0,
                "source_ref": "conversation_id=toy",
                "question": "Before the deadline, which milestone came first?",
                "slice_group": "temporal_reasoning",
            }
        ],
    }
    corpus_payload = {
        "schema_version": "natural-benchmark-evidence-corpus-v1",
        "slice_id": "toy-structural-block",
        "item_count": 1,
        "items": {
            "I-structural-empty": [
                {
                    "benchmark": "beam",
                    "source_id": "s",
                    "unit_id": "E-timeline",
                    "source_ref": "conversation_id=toy;message_id=1",
                    "text": "chronology alpha evidence",
                    "metadata": {},
                }
            ]
        },
    }

    results = run_symbolic_fallback(
        slice_payload,
        corpus_payload,
        run_id="fallback-structural-block",
        symbolic_top_k=3,
        fallback_top_k=1,
        encoder=lambda texts: [[1.0] for _ in texts],
    )

    item = results["items"][0]
    assert item["retrieved_evidence_refs"] == []
    assert item["fallback_triggered"] is False
    assert item["metadata"]["fallback_decision"] == "blocked"
    assert item["metadata"]["fallback_reason_candidate"] == "temporal_negation_modality_conflict_mismatch"


def test_symbolic_fallback_blocks_causal_topic_overlap_without_dense_fallback():
    slice_payload = {
        "schema_version": "natural-benchmark-slice-v1",
        "slice_id": "toy-answerability-block",
        "source_manifest_sha256": "0" * 64,
        "selection_policy": {},
        "public_items": [
            {
                "benchmark": "beam",
                "item_id": "I-causal-overlap",
                "source_id": "s",
                "source_index": 0,
                "source_ref": "conversation_id=toy",
                "question": "How did the user feedback influence the UI/UX improvements I made before the public launch?",
                "slice_group": "abstention",
            }
        ],
    }
    gold_payload = {
        "schema_version": "natural-benchmark-gold-v1",
        "slice_id": "toy-answerability-block",
        "source_manifest_sha256": "0" * 64,
        "items": [
            {
                "benchmark": "beam",
                "item_id": "I-causal-overlap",
                "source_id": "s",
                "source_ref": "conversation_id=toy",
                "slice_group": "abstention",
                "category": "abstention",
                "answer": "No answer is available.",
                "answer_policy": "gold",
                "evidence_refs": [],
                "metadata": {},
            }
        ],
    }
    corpus_payload = {
        "schema_version": "natural-benchmark-evidence-corpus-v1",
        "slice_id": "toy-answerability-block",
        "item_count": 1,
        "items": {
            "I-causal-overlap": [
                {
                    "benchmark": "beam",
                    "source_id": "s",
                    "unit_id": "E-topic-overlap",
                    "source_ref": "conversation_id=toy;message_id=1",
                    "text": "I want to make sure the UI/UX is improved based on user feedback before the public launch.",
                    "metadata": {},
                },
                {
                    "benchmark": "beam",
                    "source_id": "s",
                    "unit_id": "E-generic-review",
                    "source_ref": "conversation_id=toy;message_id=2",
                    "text": "Let's review the current implementation and suggest improvements for UI/UX and security.",
                    "metadata": {},
                },
            ]
        },
    }

    results = run_symbolic_fallback(
        slice_payload,
        corpus_payload,
        run_id="fallback-answerability-block",
        symbolic_top_k=3,
        fallback_top_k=1,
        encoder=lambda texts: [[1.0] for _ in texts],
    )

    item = results["items"][0]
    assert item["retrieved_evidence_refs"] == []
    assert item["abstained"] is True
    assert item["fallback_triggered"] is False
    assert item["metadata"]["answerability_decision"] == "blocked"
    assert item["metadata"]["answerability_reason"] == "causal_relation_missing"

    report = score_results(slice_payload, gold_payload, results)
    assert report["critical_false_positive_count"] == 0


def test_cli_run_symbolic_fallback_writes_results(tmp_path):
    slice_payload, _gold_payload, corpus_payload = _toy_payloads()
    slice_path = tmp_path / "slice.json"
    corpus_path = tmp_path / "corpus.json"
    output_path = tmp_path / "symbolic-fallback-results.json"
    write_json_immutable(slice_path, slice_payload)
    write_json_immutable(corpus_path, corpus_payload)

    result = _run_cli(
        "run-symbolic-fallback",
        "--slice",
        str(slice_path),
        "--corpus",
        str(corpus_path),
        "--output",
        str(output_path),
        "--run-id",
        "fallback-cli",
        "--symbolic-top-k",
        "3",
        "--fallback-top-k",
        "1",
        "--encoder",
        "lexical",
    )

    assert "valid" in result.stdout
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["arm"] == "symbolic_fallback"
