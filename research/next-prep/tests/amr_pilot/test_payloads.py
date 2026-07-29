from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tools.amr_pilot.models import SentenceSample
from tools.amr_pilot.payloads import (
    build_payload,
    load_prompt_contracts,
    write_payload_manifest,
)


PROMPTS = Path("artifacts/amr-pilot/prompts")
SENTENCE = "The customer did not cancel the tablet order on Tuesday."


def sample(text: str = SENTENCE) -> SentenceSample:
    return SentenceSample.model_validate(
        {
            "sample_id": "AMR-S001",
            "candidate_id": "TAU-BENCH-CAND-001",
            "text": text,
            "language": "en",
            "phenomenon": "negation_modality_intent",
            "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "source_record_id": "SRC-001",
            "sentence_occurrence_index": 0,
            "source": {
                "dataset": "Synthetic",
                "source_url": "https://example.test/source",
                "source_revision": "fixture",
                "source_artifact_sha256": "4" * 64,
                "record_locator": "record=1",
                "message_locator": "message=1",
                "speaker": "user",
            },
        }
    )


def visible_text(payload: dict[str, object]) -> str:
    return "\n".join(message["content"] for message in payload["messages"])


def test_prompt_contracts_are_versioned_and_hashed() -> None:
    contracts = load_prompt_contracts(PROMPTS)

    assert set(contracts) == {"A", "B", "C"}
    assert contracts["A"].version == "direct-amr-v1"
    assert contracts["B"].version == "knowledge-to-amr-v1"
    assert contracts["C"].version == "atomic-knowledge-v1"
    assert all(len(contract.sha256) == 64 for contract in contracts.values())


def test_route_a_sees_only_its_contract_and_the_sentence() -> None:
    contracts = load_prompt_contracts(PROMPTS)
    payload = build_payload(sample(), "A", contracts)
    text = visible_text(payload)

    assert payload["model_id"] == "gpt-5.6-terra"
    assert payload["temperature"] == 0
    assert payload["max_output_tokens"] == 1200
    assert SENTENCE in text
    assert contracts["A"].text in text
    assert "atomic-knowledge-v1" not in text
    assert set(payload) == {
        "schema_version",
        "sample_id",
        "route",
        "model_id",
        "temperature",
        "max_output_tokens",
        "prompt_version",
        "prompt_sha256",
        "input_sha256",
        "messages",
        "payload_sha256",
    }


def test_route_c_sees_only_its_contract_and_the_sentence() -> None:
    contracts = load_prompt_contracts(PROMPTS)
    payload = build_payload(sample(), "C", contracts)
    text = visible_text(payload)

    assert SENTENCE in text
    assert contracts["C"].text in text
    assert "knowledge-to-amr-v1" not in text
    assert payload["max_output_tokens"] == 1000


def test_route_b_sees_only_validated_atomic_knowledge() -> None:
    contracts = load_prompt_contracts(PROMPTS)
    atomic = {
        "schema_version": "amr-pilot-atomic-knowledge-v1",
        "items": [
            {
                "knowledge_id": "K001",
                "statement": "The customer did not cancel the tablet order.",
                "evidence_quote": "did not cancel the tablet order",
            }
        ],
        "representation_gaps": [],
    }

    payload = build_payload(sample(), "B", contracts, atomic_knowledge=atomic)
    text = visible_text(payload)

    assert contracts["B"].text in text
    assert atomic["items"][0]["statement"] in text
    assert SENTENCE not in text
    assert "Taskmaster" not in text
    assert payload["input_sha256"] == hashlib.sha256(
        json.dumps(atomic, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def test_route_b_rejects_unvalidated_or_missing_atomic_knowledge() -> None:
    contracts = load_prompt_contracts(PROMPTS)

    with pytest.raises(ValueError, match="requires validated atomic knowledge"):
        build_payload(sample(), "B", contracts)
    with pytest.raises(ValueError, match="atomic knowledge"):
        build_payload(sample(), "B", contracts, atomic_knowledge={"items": []})


def test_routes_a_and_c_reject_atomic_knowledge_input() -> None:
    contracts = load_prompt_contracts(PROMPTS)

    with pytest.raises(ValueError, match="must not receive atomic knowledge"):
        build_payload(sample(), "A", contracts, atomic_knowledge={"items": []})


def test_payload_text_excludes_gold_other_samples_and_project_context() -> None:
    contracts = load_prompt_contracts(PROMPTS)
    other_sentence = "This sentence belongs to another sample."
    forbidden = [
        other_sentence,
        "semantic-checklists",
        "gold answer",
        "KEOL",
        "LongMemEval",
        "LoCoMo",
        "BEAM benchmark",
        "原始文本",
        "知识",
    ]

    for route in ("A", "C"):
        text = visible_text(build_payload(sample(), route, contracts))
        assert all(term not in text for term in forbidden)


def test_manifest_records_prompt_and_payload_hashes_immutably(tmp_path: Path) -> None:
    contracts = load_prompt_contracts(PROMPTS)
    payloads = [
        build_payload(sample(), "A", contracts),
        build_payload(sample(), "C", contracts),
    ]
    path = tmp_path / "manifest.json"

    write_payload_manifest(contracts, payloads, path)
    document = json.loads(path.read_text(encoding="utf-8"))

    assert document["prompt_hashes"] == {
        route: contracts[route].sha256 for route in ("A", "B", "C")
    }
    assert document["payload_hashes"] == {
        f"{payload['sample_id']}:{payload['route']}": payload["payload_sha256"]
        for payload in payloads
    }

    write_payload_manifest(contracts, payloads, path)
    changed = dict(payloads[0])
    changed["payload_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="refusing to overwrite"):
        write_payload_manifest(contracts, [changed, payloads[1]], path)
