from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.natural_memory_benchmark.io import load_json
from tools.natural_memory_benchmark.typed_extractor_l2 import prepare_l2_dev_slice
from tools.natural_memory_benchmark.typed_extractor_l2_api_run import (
    run_l2_openai_compatible_proposer,
)
from tools.natural_memory_benchmark.typed_extractor_l2_model_run import (
    write_l2_model_dispatch,
)


FORMAL_ROOT = Path(
    "artifacts/automatic-extraction-assessment/typed-extractor-v2-l2-dev"
)
PROMPT = FORMAL_ROOT / "proposer-prompt-l2.md"
ISOLATION = "fresh-agent-no-history-declarative"


class _Response:
    def __init__(self, payload: bytes):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return self._payload


def _prepare(root: Path) -> None:
    prepare_l2_dev_slice(
        source_config_path=FORMAL_ROOT / "source-cases-l2.json",
        prompt_path=PROMPT,
        bridge_ledger_path=Path(
            "artifacts/automatic-extraction-assessment/bridge-v3/compatibility-ledger.json"
        ),
        source_path=Path("data/gold-candidates/KE-test.json"),
        turn_manifest_path=Path("knowledge-extraction/turn-pass/validated/manifest.json"),
        dialogue_manifest_path=Path("knowledge-extraction/dialogue-pass/validated/manifest.json"),
        final_knowledge_path=Path("knowledge-extraction/final-knowledge.json"),
        run_path=Path("knowledge-extraction/run.json"),
        source_segments_path=Path("knowledge-extraction/source-segments.json"),
        l1_qualification_root=Path(
            "artifacts/automatic-extraction-assessment/typed-extractor-v2-dev-v3"
        ),
        output_root=root,
    )


def test_api_runner_archives_raw_and_extracts_reasoning_content(tmp_path: Path) -> None:
    root = tmp_path / "slice"
    _prepare(root)
    run_root = tmp_path / "run"
    dispatch = run_root / "dispatch.json"
    write_l2_model_dispatch(
        root / "public-l2.json",
        PROMPT,
        dispatch,
        run_id="run-api-test",
        proposer_id="openai-compatible-api",
        proposer_version="test-model-v1",
        requested_model="test-model-alias",
        isolation_context=ISOLATION,
    )
    gold = load_json(root / "gold-l2.json")
    proposal_payload = {
        "schema_version": "typed-extractor-l2-proposals-v1",
        "dataset_id": gold["dataset_id"],
        "run_id": "run-api-test",
        "proposer_id": "openai-compatible-api",
        "proposer_version": "test-model-v1",
        "case_count": gold["case_count"],
        "proposals": [
            {
                "case_id": item["case_id"],
                "candidate_ref": item["candidate_ref"],
                "decision": item["expected_decision"],
                "confidence": 1.0,
                "typed_candidate": item["expected_typed_candidate"],
                "reason_code": "fixture",
            }
            for item in gold["items"]
        ],
    }
    raw_payload = json.dumps(
        {
            "model": "resolved-test-model",
            "choices": [
                {
                    "message": {
                        "content": None,
                        "reasoning_content": json.dumps(
                            proposal_payload, ensure_ascii=False
                        ),
                    }
                }
            ],
        },
        ensure_ascii=False,
    ).encode()
    captured: dict[str, object] = {}

    def opener(request, timeout):
        captured["body"] = json.loads(request.data)
        captured["timeout"] = timeout
        return _Response(raw_payload)

    result = run_l2_openai_compatible_proposer(
        public_path=root / "public-l2.json",
        prompt_path=PROMPT,
        dispatch_path=dispatch,
        raw_response_path=run_root / "raw-response.json",
        staged_proposals_path=run_root / "staged-proposals.json",
        base_url="https://example.test/v1",
        api_key="secret",
        model="test-model-alias",
        timeout_seconds=30,
        opener=opener,
    )
    assert result["status"] == "staged"
    assert result["requested_model"] == "test-model-alias"
    assert result["response_model"] == "resolved-test-model"
    assert (run_root / "raw-response.json").read_bytes() == raw_payload
    assert load_json(run_root / "staged-proposals.json") == proposal_payload
    body = captured["body"]
    serialized = json.dumps(body, ensure_ascii=False)
    assert "gold-l2" not in serialized
    assert "authority-l2" not in serialized
    assert len(body["messages"]) == 2
    assert (run_root / "raw-response.json").stat().st_mode & 0o222 == 0


def test_api_runner_rejects_model_not_bound_by_dispatch(tmp_path: Path) -> None:
    root = tmp_path / "slice"
    _prepare(root)
    run_root = tmp_path / "run"
    dispatch = run_root / "dispatch.json"
    write_l2_model_dispatch(
        root / "public-l2.json",
        PROMPT,
        dispatch,
        run_id="run-api-test",
        proposer_id="openai-compatible-api",
        proposer_version="test-model-v1",
        requested_model="bound-model",
        isolation_context=ISOLATION,
    )
    with pytest.raises(ValueError, match="requested model"):
        run_l2_openai_compatible_proposer(
            public_path=root / "public-l2.json",
            prompt_path=PROMPT,
            dispatch_path=dispatch,
            raw_response_path=run_root / "raw-response.json",
            staged_proposals_path=run_root / "staged-proposals.json",
            base_url="https://example.test/v1",
            api_key="secret",
            model="different-model",
            timeout_seconds=30,
            opener=lambda *args, **kwargs: None,
        )
