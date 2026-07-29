from __future__ import annotations

from collections import Counter
from pathlib import Path

from tools.natural_memory_benchmark.loaders import (
    load_beam_candidates,
    load_locomo_candidates,
    load_longmemeval_candidates,
)


BEAM_PATH = Path("artifacts/natural-benchmark-slices/raw/beam/100K-00000-of-00001.parquet")
LOCOMO_PATH = Path("artifacts/natural-benchmark-slices/raw/locomo/locomo10.json")
LONGMEM_PATH = Path("artifacts/natural-benchmark-slices/raw/longmemeval/longmemeval_oracle.json")


def test_beam_loader_extracts_all_questions():
    candidates = load_beam_candidates(BEAM_PATH)

    assert len(candidates) == 400
    assert len({candidate.item_id for candidate in candidates}) == 400
    assert all(candidate.benchmark == "beam" for candidate in candidates)
    assert Counter(candidate.slice_group for candidate in candidates) == {
        "abstention": 40,
        "contradiction_resolution": 40,
        "event_ordering": 40,
        "information_extraction": 40,
        "instruction_following": 40,
        "knowledge_update": 40,
        "multi_session_reasoning": 40,
        "preference_following": 40,
        "summarization": 40,
        "temporal_reasoning": 40,
    }


def test_locomo_loader_marks_adversarial_items_manual_required():
    candidates = load_locomo_candidates(LOCOMO_PATH)

    assert len(candidates) == 1986
    assert len({candidate.item_id for candidate in candidates}) == 1986
    assert Counter(candidate.slice_group for candidate in candidates) == {
        "1": 282,
        "2": 321,
        "3": 96,
        "4": 841,
        "5": 446,
    }
    adversarial = [candidate for candidate in candidates if candidate.slice_group == "5"]
    assert adversarial
    assert all(candidate.answer_policy == "manual_required" for candidate in adversarial)
    assert all(candidate.answer is None for candidate in adversarial)


def test_longmemeval_loader_extracts_all_questions():
    candidates = load_longmemeval_candidates(LONGMEM_PATH)

    assert len(candidates) == 500
    assert len({candidate.item_id for candidate in candidates}) == 500
    assert Counter(candidate.slice_group for candidate in candidates) == {
        "temporal-reasoning": 133,
        "multi-session": 133,
        "knowledge-update": 78,
        "single-session-preference": 30,
        "single-session-assistant": 56,
        "single-session-user": 70,
    }
    first = candidates[0]
    assert first.answer_policy == "gold"
    assert first.answer is not None
    assert first.evidence_refs
