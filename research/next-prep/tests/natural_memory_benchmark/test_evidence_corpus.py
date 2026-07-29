from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tools.natural_memory_benchmark.evidence import build_item_evidence_corpus


SLICE_ROOT = Path("artifacts/natural-benchmark-slices")


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "tools.natural_memory_benchmark.cli", *args],
        check=True,
        capture_output=True,
        text=True,
    )


def test_build_item_evidence_corpus_contains_gold_and_distractors():
    corpus = build_item_evidence_corpus(SLICE_ROOT, "slice-v1")

    beam_units = corpus["BEAM-100K-C001-contradiction_resolution-001"]
    beam_ids = {unit["unit_id"] for unit in beam_units}
    assert {"24", "58"}.issubset(beam_ids)
    assert len(beam_units) > 100
    assert any(unit["metadata"]["role"] == "assistant" for unit in beam_units)

    locomo_units = corpus["LOCOMO-S01-Q004"]
    locomo_ids = {unit["unit_id"] for unit in locomo_units}
    assert "D2:8" in locomo_ids
    assert len(locomo_units) > 100

    longmem_units = corpus["LONGMEMEVAL-gpt4_2655b836"]
    longmem_ids = {unit["unit_id"] for unit in longmem_units}
    assert {"answer_4be1b6b4_1", "answer_4be1b6b4_2", "answer_4be1b6b4_3"}.issubset(longmem_ids)
    assert all(unit["text"] for unit in longmem_units)


def test_cli_export_evidence_corpus_writes_public_candidate_units(tmp_path):
    output_path = tmp_path / "evidence-corpus.json"

    result = _run_cli(
        "export-evidence-corpus",
        "--root",
        str(SLICE_ROOT),
        "--slice-id",
        "slice-v1",
        "--output",
        str(output_path),
    )

    assert "valid" in result.stdout
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "natural-benchmark-evidence-corpus-v1"
    assert payload["item_count"] == 32
    assert "answer_policy" not in json.dumps(payload, ensure_ascii=False)
    assert "gold_items" not in json.dumps(payload, ensure_ascii=False)
