from __future__ import annotations

from tools.natural_memory_benchmark.ledger import build_external_results_ledger


def test_external_results_ledger_is_contextual_only():
    ledger = build_external_results_ledger()

    assert ledger.schema_version == "natural-benchmark-external-results-ledger-v1"
    assert ledger.entries
    assert {entry.system for entry in ledger.entries} >= {"mem0", "hindsight", "mempalace", "zep"}
    assert all(entry.comparability_status == "contextual_only" for entry in ledger.entries)
    assert all(entry.local_rerun is False for entry in ledger.entries)
    assert all(entry.official_source_url.startswith("http") for entry in ledger.entries)


def test_external_results_ledger_records_metrics_per_entry():
    ledger = build_external_results_ledger()

    metrics = {(entry.system, entry.benchmark, entry.metric_name) for entry in ledger.entries}
    assert ("mem0", "loComo".lower(), "accuracy") in metrics
    assert ("hindsight", "beam-1m", "accuracy") in metrics
    assert ("mempalace", "locomo", "retrieval_recall") in metrics
