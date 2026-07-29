from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from tools.natural_memory_benchmark.loaders import (
    load_beam_candidates,
    load_locomo_candidates,
    load_longmemeval_candidates,
)
from tools.natural_memory_benchmark.slices import build_slice_v1, freeze_slice_bundle


BEAM_PATH = Path("artifacts/natural-benchmark-slices/raw/beam/100K-00000-of-00001.parquet")
LOCOMO_PATH = Path("artifacts/natural-benchmark-slices/raw/locomo/locomo10.json")
LONGMEM_PATH = Path("artifacts/natural-benchmark-slices/raw/longmemeval/longmemeval_oracle.json")


def test_slice_v1_has_fixed_per_benchmark_quotas():
    bundle = build_slice_v1(
        {
            "beam": load_beam_candidates(BEAM_PATH),
            "locomo": load_locomo_candidates(LOCOMO_PATH),
            "longmemeval": load_longmemeval_candidates(LONGMEM_PATH),
        }
    )

    assert len(bundle.public_items) == 32
    assert len(bundle.gold_items) == 32
    assert Counter(item["benchmark"] for item in bundle.public_items) == {
        "beam": 10,
        "locomo": 10,
        "longmemeval": 12,
    }
    assert bundle.public_items[0]["item_id"].startswith("BEAM-")
    assert bundle.public_items[-1]["item_id"].startswith("LONGMEMEVAL-")


def test_slice_v1_public_items_do_not_leak_gold_fields():
    bundle = build_slice_v1(
        {
            "beam": load_beam_candidates(BEAM_PATH),
            "locomo": load_locomo_candidates(LOCOMO_PATH),
            "longmemeval": load_longmemeval_candidates(LONGMEM_PATH),
        }
    )

    forbidden = {
        "answer",
        "evidence_refs",
        "rubric",
        "adversarial_answer",
        "answer_session_ids",
        "haystack_sessions",
        "haystack_session_ids",
    }
    for item in bundle.public_items:
        assert forbidden.isdisjoint(item)
        assert "manual_required" not in json.dumps(item, ensure_ascii=False)


def test_freeze_slice_json_excludes_gold_payload(tmp_path):
    out_root = tmp_path / "natural-benchmark-slices"

    freeze_slice_bundle(Path("artifacts/natural-benchmark-slices"), out_root)
    public_slice = json.loads((out_root / "slice-v1" / "slice.json").read_text(encoding="utf-8"))
    gold = json.loads((out_root / "slice-v1" / "gold.json").read_text(encoding="utf-8"))

    assert "public_items" in public_slice
    assert "gold_items" not in public_slice
    serialized_public = json.dumps(public_slice, ensure_ascii=False)
    assert "evidence_refs" not in serialized_public
    assert "answer_policy" not in serialized_public
    assert "manual_required" not in serialized_public
    assert "items" in gold
    assert any(item["answer_policy"] == "manual_required" for item in gold["items"])


def test_slice_v1_gold_items_keep_manual_required_for_locomo_category5():
    bundle = build_slice_v1(
        {
            "beam": load_beam_candidates(BEAM_PATH),
            "locomo": load_locomo_candidates(LOCOMO_PATH),
            "longmemeval": load_longmemeval_candidates(LONGMEM_PATH),
        }
    )

    locomo_manual = [
        item
        for item in bundle.gold_items
        if item["benchmark"] == "locomo" and item["answer_policy"] == "manual_required"
    ]
    assert locomo_manual
    assert all(item["answer"] is None for item in locomo_manual)
