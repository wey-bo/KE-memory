"""Leak regressions against the real corpora.

The review that rejected the first Stage 0.5 found gold recoverable from the public
channel in 500 of 500 LongMemEval questions. These tests run the actual loaders over the
actual files, because the defect was invisible to synthetic fixtures: it lived in how the
loader translated real source structure.

Skipped when a corpus is absent, so the suite still runs on a machine without the data.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ke_memory_demo.evaluation.beam_adapter import load_beam
from ke_memory_demo.evaluation.benchmark_loaders import load_locomo, load_longmemeval
from ke_memory_demo.evaluation.channels import (
    ALLOWED_CONVERSATION_METADATA,
    ALLOWED_SESSION_METADATA,
    LoadedBenchmark,
    assert_build_input_is_blind,
)
from ke_memory_demo.evaluation.regression_slice import load_regression_slice

LOCOMO = Path("/public/home/wwb/datasets/LoCoMo/locomo10.json")
LONGMEMEVAL = Path("/public/home/wwb/datasets/LongMemEval/longmemeval_oracle.json")
BEAM = Path("/public/home/wwb/datasets/BEAM.zip")
SLICE_DIR = Path("research/next-prep/artifacts/natural-benchmark-slices/slice-v1")


def _assert_metadata_is_allowlisted(loaded: LoadedBenchmark) -> None:
    """Every surviving key must be on the allowlist, at every level."""
    for conversation in loaded.build_input.conversations:
        assert set(conversation.metadata) <= ALLOWED_CONVERSATION_METADATA
        for session in conversation.sessions:
            assert set(session.metadata) <= ALLOWED_SESSION_METADATA


@pytest.mark.skipif(not LONGMEMEVAL.is_file(), reason="LongMemEval corpus not present")
def test_longmemeval_public_channel_cannot_identify_the_answer_sessions() -> None:
    """The exact defect a review found: an is_answer_session flag named gold.

    Also covers the follow-on: LongMemEval calls answer-bearing sessions ``answer_*``, so
    exposing any raw session id discloses gold even without a flag.
    """
    loaded = load_longmemeval(LONGMEMEVAL)
    _assert_metadata_is_allowlisted(loaded)

    for conversation in loaded.build_input.conversations:
        for session in conversation.sessions:
            assert "answer" not in session.session_handle
            for value in session.metadata.values():
                assert "answer" not in str(value)

    assert_build_input_is_blind(loaded.build_input, loaded.questions, loaded.gold)
    assert len(loaded.questions.questions) == len(loaded.gold.labels)


@pytest.mark.skipif(not LOCOMO.is_file(), reason="LoCoMo corpus not present")
def test_locomo_public_channel_is_gold_free() -> None:
    loaded = load_locomo(LOCOMO)
    _assert_metadata_is_allowlisted(loaded)
    assert_build_input_is_blind(loaded.build_input, loaded.questions, loaded.gold)
    # Category 5 has insufficient official gold and must stay manual.
    assert any(label.requires_manual_review for label in loaded.gold.labels)


@pytest.mark.skipif(not BEAM.is_file(), reason="BEAM archive not present")
def test_beam_adapter_moves_rubrics_into_the_gold_channel() -> None:
    """A BEAM rubric is the grading key, so it must never travel with the question."""
    loaded = load_beam(BEAM)
    _assert_metadata_is_allowlisted(loaded)
    assert_build_input_is_blind(loaded.build_input, loaded.questions, loaded.gold)
    assert loaded.questions.questions
    assert any(label.rubrics for label in loaded.gold.labels)
    # The public question exposes three fields and none of them is a rubric.
    assert set(loaded.questions.questions[0].model_dump()) == {
        "question_id",
        "conversation_handle",
        "question",
    }


@pytest.mark.skipif(not (SLICE_DIR / "slice.json").is_file(), reason="slice not present")
def test_regression_slice_uses_real_questions_from_the_public_channel() -> None:
    """The loader previously used a source_ref pointer as the question text."""
    loaded = load_regression_slice(SLICE_DIR)
    _assert_metadata_is_allowlisted(loaded)
    assert_build_input_is_blind(loaded.build_input, loaded.questions, loaded.gold)
    assert len(loaded.questions.questions) == 32

    for question in loaded.questions.questions:
        # A pointer looks like "conversation_id=1;group=...;question_index=1".
        assert "question_index=" not in question.question
        assert "conversation_id=" not in question.question
        assert len(question.question.split()) > 2
