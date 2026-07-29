from __future__ import annotations

from pathlib import Path
from typing import Any

from .io import load_json, write_json_immutable
from .models import ExternalResultEntry, ExternalResultsLedger


def build_external_results_ledger() -> ExternalResultsLedger:
    entries = [
        ExternalResultEntry(
            system="mem0",
            benchmark="locomo",
            metric_name="accuracy",
            metric_value=92.5,
            official_source_url="https://github.com/mem0ai/mem0/blob/d653b63fac6c8ad0ad84aead0912b366e705d269/docs/core-concepts/memory-evaluation.mdx",
            version_or_retrieval_date="2026-07-25",
            source_identity="mem0 d653b63fac6c8ad0ad84aead0912b366e705d269",
            note="Author-reported end-to-end accuracy from the frozen official source.",
        ),
        ExternalResultEntry(
            system="mem0",
            benchmark="longmemeval",
            metric_name="accuracy",
            metric_value=94.4,
            official_source_url="https://github.com/mem0ai/mem0/blob/d653b63fac6c8ad0ad84aead0912b366e705d269/docs/core-concepts/memory-evaluation.mdx",
            version_or_retrieval_date="2026-07-25",
            source_identity="mem0 d653b63fac6c8ad0ad84aead0912b366e705d269",
            note="Author-reported end-to-end accuracy from the frozen official source.",
        ),
        ExternalResultEntry(
            system="mem0",
            benchmark="beam-1m",
            metric_name="accuracy",
            metric_value=64.1,
            official_source_url="https://github.com/mem0ai/mem0/blob/d653b63fac6c8ad0ad84aead0912b366e705d269/docs/core-concepts/memory-evaluation.mdx",
            version_or_retrieval_date="2026-07-25",
            source_identity="mem0 d653b63fac6c8ad0ad84aead0912b366e705d269",
            note="Author-reported BEAM 1M accuracy from the frozen official source.",
        ),
        ExternalResultEntry(
            system="mem0",
            benchmark="beam-10m",
            metric_name="accuracy",
            metric_value=48.6,
            official_source_url="https://github.com/mem0ai/mem0/blob/d653b63fac6c8ad0ad84aead0912b366e705d269/docs/core-concepts/memory-evaluation.mdx",
            version_or_retrieval_date="2026-07-25",
            source_identity="mem0 d653b63fac6c8ad0ad84aead0912b366e705d269",
            note="Author-reported BEAM 10M accuracy from the frozen official source.",
        ),
        ExternalResultEntry(
            system="hindsight",
            benchmark="locomo",
            metric_name="accuracy",
            metric_value=92.0,
            official_source_url="https://github.com/vectorize-io/hindsight/blob/ed120a256d51d731085ec8aca724573a7f2f1e1c/hindsight-docs/blog/2026-03-23-agent-memory-benchmark.mdx",
            version_or_retrieval_date="2026-07-25",
            source_identity="hindsight ed120a256d51d731085ec8aca724573a7f2f1e1c",
            note="Author-reported benchmark accuracy from the frozen official source.",
        ),
        ExternalResultEntry(
            system="hindsight",
            benchmark="longmemeval",
            metric_name="accuracy",
            metric_value=94.6,
            official_source_url="https://github.com/vectorize-io/hindsight/blob/ed120a256d51d731085ec8aca724573a7f2f1e1c/hindsight-docs/blog/2026-03-23-agent-memory-benchmark.mdx",
            version_or_retrieval_date="2026-07-25",
            source_identity="hindsight ed120a256d51d731085ec8aca724573a7f2f1e1c",
            note="Author-reported benchmark accuracy from the frozen official source.",
        ),
        ExternalResultEntry(
            system="hindsight",
            benchmark="beam-1m",
            metric_name="accuracy",
            metric_value=73.9,
            official_source_url="https://github.com/vectorize-io/hindsight/blob/ed120a256d51d731085ec8aca724573a7f2f1e1c/hindsight-docs/blog/2026-04-02-beam-sota.md",
            version_or_retrieval_date="2026-07-25",
            source_identity="hindsight ed120a256d51d731085ec8aca724573a7f2f1e1c",
            note="Author-reported BEAM 1M accuracy from the frozen official source.",
        ),
        ExternalResultEntry(
            system="hindsight",
            benchmark="beam-10m",
            metric_name="accuracy",
            metric_value=64.1,
            official_source_url="https://github.com/vectorize-io/hindsight/blob/ed120a256d51d731085ec8aca724573a7f2f1e1c/hindsight-docs/blog/2026-04-02-beam-sota.md",
            version_or_retrieval_date="2026-07-25",
            source_identity="hindsight ed120a256d51d731085ec8aca724573a7f2f1e1c",
            note="Author-reported BEAM 10M accuracy from the frozen official source.",
        ),
        ExternalResultEntry(
            system="mempalace",
            benchmark="locomo",
            metric_name="retrieval_recall",
            metric_value=88.9,
            official_source_url="https://github.com/Cozy-ctrl/mempalace/blob/8ab251c452c43f2b07a76a28f2433e258307f571/website/reference/benchmarks.md",
            version_or_retrieval_date="2026-07-25",
            source_identity="mempalace 8ab251c452c43f2b07a76a28f2433e258307f571",
            note="Author-reported session retrieval recall from the frozen official source.",
        ),
        ExternalResultEntry(
            system="mempalace",
            benchmark="locomo",
            metric_name="retrieval_recall_heldout",
            metric_value=98.4,
            official_source_url="https://github.com/Cozy-ctrl/mempalace/blob/8ab251c452c43f2b07a76a28f2433e258307f571/website/reference/benchmarks.md",
            version_or_retrieval_date="2026-07-25",
            source_identity="mempalace 8ab251c452c43f2b07a76a28f2433e258307f571",
            note="Author-reported held-out recall from the frozen official source.",
        ),
        ExternalResultEntry(
            system="mempalace",
            benchmark="longmemeval",
            metric_name="retrieval_recall_top5",
            metric_value=96.6,
            official_source_url="https://github.com/Cozy-ctrl/mempalace/blob/8ab251c452c43f2b07a76a28f2433e258307f571/website/reference/benchmarks.md",
            version_or_retrieval_date="2026-07-25",
            source_identity="mempalace 8ab251c452c43f2b07a76a28f2433e258307f571",
            note="Author-reported full-500 LongMemEval recall from the frozen official source.",
        ),
        ExternalResultEntry(
            system="zep",
            benchmark="longmemeval-s",
            metric_name="accuracy",
            metric_value=71.2,
            official_source_url="https://arxiv.org/pdf/2501.13956v1",
            version_or_retrieval_date="2025-01-20",
            source_identity="arXiv 2501.13956v1",
            note="Paper-reported Zep result on LongMemEval-S with gpt-4o.",
        ),
        ExternalResultEntry(
            system="graphiti",
            benchmark="architecture",
            metric_name="provenance",
            metric_value="paper-context-only",
            official_source_url="https://github.com/getzep/graphiti/tree/3bb2d0bba56f8e22311574c045452c420a012f49",
            version_or_retrieval_date="2026-07-25",
            source_identity="graphiti 3bb2d0bba56f8e22311574c045452c420a012f49",
            note="Architecture provenance only; not a local benchmark score.",
        ),
    ]
    return ExternalResultsLedger(entries=entries)


def validate_external_results_ledger(path: Path) -> ExternalResultsLedger:
    ledger = ExternalResultsLedger.model_validate(load_json(path))
    if not ledger.entries:
        raise ValueError("external results ledger is empty")
    for entry in ledger.entries:
        if entry.comparability_status != "contextual_only":
            raise ValueError("external results entries must remain contextual only")
        if entry.local_rerun:
            raise ValueError("external results ledger must not record local reruns")
    return ledger


def write_external_results_ledger(path: Path) -> ExternalResultsLedger:
    ledger = build_external_results_ledger()
    write_json_immutable(path, ledger)
    return ledger
