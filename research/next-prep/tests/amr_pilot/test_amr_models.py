from __future__ import annotations

import hashlib

import pytest

from pydantic import ValidationError

from tools.amr_pilot.models import (
    AttemptSidecar,
    GoldItem,
    MeasuredUsage,
    SentenceSample,
    UnavailableUsage,
)


TEXT = "The customer did not cancel the tablet order on Tuesday."
TEXT_SHA256 = hashlib.sha256(TEXT.encode("utf-8")).hexdigest()


def sample(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "sample_id": "AMR-S001",
        "candidate_id": "TASKMASTER2-CAND-001",
        "text": TEXT,
        "language": "en",
        "phenomenon": "negation_modality_intent",
        "text_sha256": TEXT_SHA256,
        "source_record_id": "SRC-001",
        "sentence_occurrence_index": 0,
        "source": {
            "dataset": "Taskmaster-2",
            "source_url": "https://example.test/taskmaster",
            "source_revision": "fixture-revision",
            "source_artifact_sha256": "4" * 64,
            "record_locator": "conversation=example",
            "message_locator": "utterance=3",
            "speaker": "user",
        },
    }
    value.update(overrides)
    return value


def test_sentence_sample_accepts_matching_text_hash() -> None:
    item = SentenceSample.model_validate(sample())

    assert item.sample_id == "AMR-S001"
    assert item.text_sha256 == TEXT_SHA256
    assert item.source.source_revision == "fixture-revision"


@pytest.mark.parametrize("sample_id", ["S001", "AMR-001", "AMR-S01", "amr-S001"])
def test_sentence_sample_requires_stable_id_format(sample_id: str) -> None:
    with pytest.raises(ValidationError, match="sample_id"):
        SentenceSample.model_validate(sample(sample_id=sample_id))


def test_sentence_sample_rejects_mismatched_text_hash() -> None:
    with pytest.raises(ValidationError, match="text_sha256"):
        SentenceSample.model_validate(sample(text_sha256="0" * 64))


def test_sentence_sample_rejects_unknown_phenomenon() -> None:
    with pytest.raises(ValidationError, match="phenomenon"):
        SentenceSample.model_validate(sample(phenomenon="coreference"))


def test_sentence_sample_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs"):
        SentenceSample.model_validate(sample(gold_answer="hidden"))


def test_gold_item_requires_positive_explicit_weight() -> None:
    payload = {
        "item_id": "AMR-S001-G001",
        "statement": "The cancellation did not occur.",
        "importance": "critical",
        "weight": 0,
        "evidence_quotes": ["did not cancel"],
        "category": "polarity",
    }

    with pytest.raises(ValidationError, match="weight"):
        GoldItem.model_validate(payload)


def test_usage_contract_distinguishes_measured_and_unavailable() -> None:
    measured = MeasuredUsage.model_validate(
        {"status": "measured", "input_tokens": 15, "output_tokens": 20, "cost_usd": 0.01}
    )
    unavailable = UnavailableUsage.model_validate(
        {"status": "unavailable", "reason": "subagent interface did not expose usage"}
    )

    assert measured.total_tokens == 35
    assert unavailable.reason.startswith("subagent")


def sidecar(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "sample_id": "AMR-S001",
        "route": "A",
        "run_id": "run-20260724T120000Z",
        "attempt": 1,
        "previous_attempt_sha256": None,
        "model_id": "gpt-5.6-terra",
        "prompt_sha256": "1" * 64,
        "raw_output_sha256": "2" * 64,
        "started_at": "2026-07-24T12:00:00Z",
        "finished_at": "2026-07-24T12:00:01Z",
        "latency_ms": 1000,
        "usage": {"status": "unavailable", "reason": "not exposed"},
        "parse_status": "valid",
        "parse_errors": [],
        "representation_gaps": [],
    }
    value.update(overrides)
    return value


def test_second_attempt_requires_previous_attempt_hash() -> None:
    with pytest.raises(ValidationError, match="previous_attempt_sha256"):
        AttemptSidecar.model_validate(sidecar(attempt=2))

    result = AttemptSidecar.model_validate(
        sidecar(attempt=2, previous_attempt_sha256="3" * 64)
    )
    assert result.attempt == 2


def test_first_attempt_rejects_previous_attempt_hash() -> None:
    with pytest.raises(ValidationError, match="previous_attempt_sha256"):
        AttemptSidecar.model_validate(sidecar(previous_attempt_sha256="3" * 64))


def test_sidecar_rejects_unknown_route() -> None:
    with pytest.raises(ValidationError, match="route"):
        AttemptSidecar.model_validate(sidecar(route="D"))


def test_sidecar_requires_latency_value_to_match_its_status() -> None:
    unavailable = AttemptSidecar.model_validate(
        sidecar(latency_ms=None, latency_status="unavailable")
    )
    assert unavailable.latency_status == "unavailable"
    assert unavailable.latency_ms is None

    with pytest.raises(ValidationError, match="latency_ms"):
        AttemptSidecar.model_validate(sidecar(latency_ms=None, latency_status="measured"))
