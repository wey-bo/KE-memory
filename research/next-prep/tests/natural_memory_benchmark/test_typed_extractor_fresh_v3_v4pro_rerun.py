from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tools.natural_memory_benchmark.io import load_json
from tools.natural_memory_benchmark.typed_extractor_l1 import (
    L1ProposalPayload,
    L1ProposalRecord,
    L1PublicPayload,
)
from tools.natural_memory_benchmark.typed_extractor_l2 import (
    L2ProposalPayload,
    L2ProposalRecord,
    L2PublicPayload,
)
from tools.natural_memory_benchmark import (
    typed_extractor_fresh_v3_v4pro_rerun as rerun,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
WORKSPACE_ROOT = REPOSITORY_ROOT / "research/next-prep"
ORIGINAL_ROOT = (
    WORKSPACE_ROOT
    / "artifacts/automatic-extraction-assessment/typed-extractor-v3-fresh-hidden-v1"
)
PROMPTS = {
    "l1": WORKSPACE_ROOT
    / "artifacts/automatic-extraction-assessment/typed-extractor-taxonomy-l1-dev-v1/"
    "model-runs/run-20260729T042500Z-deepseek-chat-official-typed-l1-taxonomy-repair-v1/"
    "proposer-prompt-l1.md",
    "l2": WORKSPACE_ROOT
    / "artifacts/automatic-extraction-assessment/typed-extractor-taxonomy-l2-dev-v1/"
    "model-runs/run-20260729T041501Z-deepseek-chat-official-typed-l2-taxonomy-baseline-v1/"
    "proposer-prompt-l2.md",
}


class FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.payload


def phase_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path, Path]:
    repository_root = tmp_path / "repository"
    workspace_root = repository_root / "research/next-prep"
    original_root = workspace_root / rerun.ORIGINAL_RELATIVE_ROOT
    for layer in ("l1", "l2"):
        layer_root = original_root / layer
        layer_root.mkdir(parents=True)
        public = layer_root / f"public-{layer}.json"
        public.write_bytes((ORIGINAL_ROOT / layer / public.name).read_bytes())
        public.chmod(0o444)
        prompt = workspace_root / rerun.PROMPT_PATHS[layer]
        prompt.parent.mkdir(parents=True, exist_ok=True)
        prompt.write_bytes(PROMPTS[layer].read_bytes())
        prompt.chmod(0o444)
    monkeypatch.setattr(
        rerun,
        "validate_v4pro_rerun_preflight",
        lambda *_args: {
            "status": "valid",
            "preflight_sha256": "a" * 64,
            "implementation_sha256": {"rerun.py": "b" * 64},
            "original_bindings": {"qualification-chronology.json": "c" * 64},
        },
    )
    return repository_root, workspace_root, workspace_root / rerun.RERUN_RELATIVE_ROOT


def proposal_response(workspace_root: Path, layer: str) -> bytes:
    original_root = workspace_root / rerun.ORIGINAL_RELATIVE_ROOT
    rerun_root = workspace_root / rerun.RERUN_RELATIVE_ROOT
    run_root = next((rerun_root / layer / "model-runs").iterdir())
    dispatch = load_json(run_root / "dispatch.json")
    if layer == "l1":
        public = L1PublicPayload.model_validate(
            load_json(original_root / layer / f"public-{layer}.json")
        )
        payload: Any = L1ProposalPayload(
            dataset_id=public.dataset_id,
            run_id=dispatch["run_id"],
            proposer_id=dispatch["proposer_id"],
            proposer_version=dispatch["proposer_version"],
            case_count=public.case_count,
            proposals=[
                L1ProposalRecord(
                    case_id=case.case_id,
                    candidate_ref=case.candidate_ref,
                    decision="abstain",
                    confidence=0.0,
                    typed_candidate=None,
                    reason_code="test_abstention",
                )
                for case in public.cases
            ],
        ).model_dump(mode="json")
    else:
        public = L2PublicPayload.model_validate(
            load_json(original_root / layer / f"public-{layer}.json")
        )
        payload = L2ProposalPayload(
            dataset_id=public.dataset_id,
            run_id=dispatch["run_id"],
            proposer_id=dispatch["proposer_id"],
            proposer_version=dispatch["proposer_version"],
            case_count=public.case_count,
            proposals=[
                L2ProposalRecord(
                    case_id=case.case_id,
                    candidate_ref=case.candidate_ref,
                    decision="abstain",
                    confidence=0.0,
                    typed_candidate=None,
                    reason_code="test_abstention",
                )
                for case in public.cases
            ],
        ).model_dump(mode="json")
    content = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return json.dumps(
        {
            "model": "deepseek-v4-pro",
            "choices": [{"message": {"content": content}}],
        },
        ensure_ascii=False,
        sort_keys=True,
    ).encode()


def test_run_ids_bind_v4pro_and_one_label() -> None:
    assert rerun.EVALUATION_ID == (
        "typed-extractor-v3-fresh-hidden-v1-deepseek-v4-pro-official-v1"
    )
    assert rerun.RERUN_RELATIVE_ROOT.endswith(rerun.EVALUATION_ID)
    assert rerun.PROPOSER_VERSIONS == {
        "l1": "deepseek-v4-pro@official-api-2026-07-30-fresh-v3-l1",
        "l2": "deepseek-v4-pro@official-api-2026-07-30-fresh-v3-l2",
    }
    assert rerun.run_ids("20260730T080000Z") == {
        "l1": "run-20260730T080000Z-deepseek-v4-pro-official-typed-l1-fresh-hidden-v3",
        "l2": "run-20260730T080000Z-deepseek-v4-pro-official-typed-l2-fresh-hidden-v3",
    }
    with pytest.raises(ValueError, match="run label"):
        rerun.run_ids("2026-07-30T08:00:00Z")


def test_dispatches_use_sibling_root_and_public_only_v4pro(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository_root, workspace_root, result_root = phase_fixture(tmp_path, monkeypatch)

    result = rerun.freeze_v4pro_rerun_dispatches(
        repository_root, workspace_root, "20260730T080000Z"
    )

    assert result["status"] == "dispatches_frozen"
    for layer in ("l1", "l2"):
        run_root = result_root / layer / "model-runs" / result["run_ids"][layer]
        dispatch = load_json(run_root / "dispatch.json")
        assert dispatch["requested_model"] == "deepseek-v4-pro"
        assert dispatch["proposer_version"] == rerun.PROPOSER_VERSIONS[layer]
        assert dispatch["history_context_inherited"] is False
        assert dispatch["authority_or_gold_allowed"] is False
        assert set(dispatch["allowed_files"]) == {
            f"proposer-prompt-{layer}.md",
            f"public-{layer}.json",
        }
        assert run_root.is_relative_to(result_root)
        assert (run_root / "dispatch.json").stat().st_mode & 0o777 == 0o444


@pytest.mark.parametrize("layer", ["l1", "l2"])
def test_successful_layer_calls_opener_once_and_freezes_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, layer: str
) -> None:
    repository_root, workspace_root, _ = phase_fixture(tmp_path, monkeypatch)
    rerun.freeze_v4pro_rerun_dispatches(
        repository_root, workspace_root, "20260730T080000Z"
    )
    calls: list[dict[str, Any]] = []

    def opener(request: Any, *, timeout: int) -> FakeResponse:
        body = json.loads(request.data)
        calls.append(body)
        assert body["model"] == "deepseek-v4-pro"
        assert len(body["messages"]) == 2
        user_payload = json.loads(body["messages"][1]["content"])
        assert set(user_payload) == {"dispatch_metadata", "public_input"}
        assert not any(
            word in json.dumps(user_payload).lower()
            for word in ("authority", "gold")
        )
        assert timeout == 30
        return FakeResponse(proposal_response(workspace_root, layer))

    result = rerun.run_and_freeze_v4pro_layer(
        repository_root,
        workspace_root,
        layer,
        base_url="https://api.deepseek.com/",
        api_key="runtime-only",
        timeout_seconds=30,
        opener=opener,
    )

    assert len(calls) == 1
    assert result["status"] == "valid"
    assert result["requested_model"] == "deepseek-v4-pro"
    assert set(Path(result["run_root"]).iterdir()) == {
        Path(result["run_root"]) / name
        for name in rerun.SUCCESS_FILES
    }


def test_non_official_base_url_is_rejected_before_opener(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository_root, workspace_root, _ = phase_fixture(tmp_path, monkeypatch)
    rerun.freeze_v4pro_rerun_dispatches(
        repository_root, workspace_root, "20260730T080000Z"
    )
    opener_called = False

    def opener(*_args: Any, **_kwargs: Any) -> FakeResponse:
        nonlocal opener_called
        opener_called = True
        raise AssertionError("opener must not be called")

    with pytest.raises(ValueError, match="official DeepSeek base URL"):
        rerun.run_and_freeze_v4pro_layer(
            repository_root,
            workspace_root,
            "l1",
            base_url="https://api.deepseek.com.attacker.invalid",
            api_key="runtime-only",
            timeout_seconds=30,
            opener=opener,
        )

    assert opener_called is False


def test_transport_failure_calls_opener_once_and_cannot_be_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository_root, workspace_root, _ = phase_fixture(tmp_path, monkeypatch)
    rerun.freeze_v4pro_rerun_dispatches(
        repository_root, workspace_root, "20260730T080000Z"
    )
    calls = 0

    def opener(*_args: Any, **_kwargs: Any) -> FakeResponse:
        nonlocal calls
        calls += 1
        raise PermissionError("denied")

    kwargs = {
        "base_url": "https://api.deepseek.com",
        "api_key": "runtime-only",
        "timeout_seconds": 30,
        "opener": opener,
    }
    with pytest.raises(PermissionError, match="denied"):
        rerun.run_and_freeze_v4pro_layer(
            repository_root, workspace_root, "l1", **kwargs
        )
    assert calls == 1
    with pytest.raises(ValueError, match="already been attempted"):
        rerun.run_and_freeze_v4pro_layer(
            repository_root, workspace_root, "l1", **kwargs
        )
    assert calls == 1


def test_layer_qualification_keeps_raw_and_gate_readiness_separate() -> None:
    metrics = {name: 1.0 for name in rerun.L1_QUALITY_METRICS}
    metrics.update(
        {
            "raw_critical_false_emission_count": 0,
            "gate_intervention_count": 1,
            "deterministic_critical_false_materialization_count": 0,
        }
    )

    result = rerun.build_layer_qualification(
        "l1",
        {
            "dataset_id": "dataset",
            "run_id": "run",
            "case_count": 24,
            "metrics": metrics,
            "raw_proposer_quality_ready": True,
            "deterministic_gate_safety_ready": False,
        },
        {
            "receipt_sha256": "a" * 64,
            "requested_model": "deepseek-v4-pro",
            "response_model": "deepseek-v4-pro",
            "request_count": 1,
        },
        "b" * 64,
    )

    assert result["raw_proposer_quality_ready"] is True
    assert result["deterministic_gate_safety_ready"] is False
    assert result["layer_ready"] is False
    assert result["status"] == "not_qualified"
