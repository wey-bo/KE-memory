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
    typed_extractor_fresh_v3_proposer_freeze as proposer_freeze,
)
from tools.natural_memory_benchmark.typed_extractor_fresh_v3_proposer_freeze import (
    IMPLEMENTATION_PATHS,
    _require_git_state,
    _validate_base_materialization,
    _implementation_git_bindings,
    _run_ids,
    freeze_fresh_v3_dispatches,
    run_and_freeze_fresh_v3_layer,
    validate_fresh_v3_proposal_freeze,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
WORKSPACE_ROOT = REPOSITORY_ROOT / "research/next-prep"
OFFICIAL_ROOT = (
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


class _FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.payload


def _phase_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    repository_root = tmp_path / "repository"
    workspace_root = repository_root / "research/next-prep"
    evaluation_root = (
        workspace_root
        / "artifacts/automatic-extraction-assessment/typed-extractor-v3-fresh-hidden-v1"
    )
    for layer in ("l1", "l2"):
        layer_root = evaluation_root / layer
        layer_root.mkdir(parents=True, mode=0o775)
        public_name = f"public-{layer}.json"
        (layer_root / public_name).write_bytes(
            (OFFICIAL_ROOT / layer / public_name).read_bytes()
        )
        (layer_root / public_name).chmod(0o444)
        prompt_path = workspace_root / proposer_freeze.PROMPT_PATHS[layer]
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        prompt_path.write_bytes(PROMPTS[layer].read_bytes())
        prompt_path.chmod(0o444)
    evaluation_root.chmod(0o775)
    (evaluation_root / "l1").chmod(0o775)
    (evaluation_root / "l2").chmod(0o775)
    monkeypatch.setattr(
        proposer_freeze,
        "validate_fresh_v3_proposer_preflight",
        lambda *_args: {"status": "valid", "preflight_sha256": "a" * 64},
    )
    monkeypatch.setattr(
        proposer_freeze,
        "_roots",
        lambda supplied_repository, supplied_workspace: (
            supplied_repository,
            supplied_workspace,
            evaluation_root,
        ),
    )
    monkeypatch.setattr(
        proposer_freeze,
        "_validate_proposer_state",
        lambda *_args: {
            "preflight_sha256": "a" * 64,
            "implementation_sha256": {"controller.py": "b" * 64},
            "parallel_sha256": {"parallel.py": "c" * 64},
        },
    )
    return repository_root, workspace_root


def _proposal_response(
    workspace_root: Path,
    layer: str,
    *,
    mutate: str | None = None,
) -> bytes:
    evaluation_root = (
        workspace_root
        / "artifacts/automatic-extraction-assessment/typed-extractor-v3-fresh-hidden-v1"
    )
    run_root = next((evaluation_root / layer / "model-runs").iterdir())
    dispatch = load_json(run_root / "dispatch.json")
    public_path = evaluation_root / layer / f"public-{layer}.json"
    if layer == "l1":
        public = L1PublicPayload.model_validate(load_json(public_path))
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
        public = L2PublicPayload.model_validate(load_json(public_path))
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
    if mutate == "metadata":
        payload["run_id"] = "wrong-run"
    elif mutate == "coverage":
        payload["proposals"] = payload["proposals"][:-1]
    elif mutate == "reference":
        payload["proposals"][0]["candidate_ref"] = "candidate-0000000000000000"
    content = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    response = {
        "model": "deepseek-v4-flash",
        "choices": [{"message": {"content": content}}],
    }
    return json.dumps(response, ensure_ascii=False, sort_keys=True).encode()


def test_run_ids_are_fixed_by_one_compact_utc_label() -> None:
    assert _run_ids("20260730T060000Z") == {
        "l1": "run-20260730T060000Z-deepseek-chat-official-typed-l1-fresh-hidden-v3",
        "l2": "run-20260730T060000Z-deepseek-chat-official-typed-l2-fresh-hidden-v3",
    }


@pytest.mark.parametrize(
    "value",
    [
        "2026-07-30T06:00:00Z",
        "20260730T060000+00:00",
        "20260730T060000Z-extra",
        "20260230T060000Z",
    ],
)
def test_run_ids_reject_noncanonical_or_impossible_labels(value: str) -> None:
    with pytest.raises(ValueError, match="run label"):
        _run_ids(value)


def test_validator_rejects_unknown_layer(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="layer"):
        validate_fresh_v3_proposal_freeze(
            tmp_path,
            tmp_path,
            "l3",  # type: ignore[arg-type]
        )


def test_git_bindings_compare_committed_bytes_without_requiring_artifact_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository_root = tmp_path / "repository"
    workspace_root = repository_root / "research/next-prep"
    committed = b"committed implementation\n"
    for relative in IMPLEMENTATION_PATHS.values():
        path = workspace_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(committed)
        path.chmod(0o644)
    monkeypatch.setattr(
        proposer_freeze,
        "_run_git",
        lambda *_args: committed,
    )

    bindings = _implementation_git_bindings(repository_root, workspace_root)

    assert set(bindings) == set(IMPLEMENTATION_PATHS)


def test_base_materialization_replays_current_official_root() -> None:
    """Replay the official root as it stands, with the model run present.

    ``allow_model_runs=False`` means "before any model was dispatched". That state is
    gone: the run under l1/model-runs was committed as evidence, so the pre-dispatch
    precondition can never hold against the official root again. The preflight path
    that genuinely needs it still passes False -- it checks a root before dispatch --
    but replaying today's root must accept what is there.
    """
    result = _validate_base_materialization(
        REPOSITORY_ROOT,
        WORKSPACE_ROOT,
        OFFICIAL_ROOT,
        allow_model_runs=True,
    )

    assert result["status"] == "frozen_pre_model"
    assert (OFFICIAL_ROOT / "l1" / "model-runs").is_dir(), (
        "the committed model run is why the pre-dispatch state is unreachable"
    )


def test_preflight_uses_frozen_artifact_replay_after_scorer_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        proposer_freeze,
        "_common_bindings",
        lambda *_args, **_kwargs: {"status": "valid"},
    )
    monkeypatch.setattr(
        proposer_freeze,
        "_require_no_result_paths",
        lambda *_args, **_kwargs: None,
    )

    result = proposer_freeze.validate_fresh_v3_proposer_preflight(
        REPOSITORY_ROOT,
        WORKSPACE_ROOT,
    )

    assert result["status"] == "valid"


def test_git_state_allows_only_formal_fresh_v3_evidence_after_dispatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, ...]] = []
    status = (
        "?? research/next-prep/artifacts/automatic-extraction-assessment/"
        "typed-extractor-v3-fresh-hidden-v1/l1/model-runs/run-test/dispatch.json\0"
    ).encode()

    def run_git(_repository: Path, *args: str) -> bytes:
        calls.append(args)
        if args[:2] == ("status", "--porcelain=v1"):
            return status
        if args == ("rev-parse", "HEAD"):
            return ("d" * 40 + "\n").encode()
        return b""

    monkeypatch.setattr(proposer_freeze, "_run_git", run_git)

    assert _require_git_state(tmp_path) == "d" * 40

    unexpected = status + b"?? unrelated.txt\0"
    monkeypatch.setattr(
        proposer_freeze,
        "_run_git",
        lambda _repository, *args: (
            unexpected
            if args[:2] == ("status", "--porcelain=v1")
            else (("d" * 40 + "\n").encode() if args == ("rev-parse", "HEAD") else b"")
        ),
    )
    with pytest.raises(ValueError, match="unexpected dirty paths"):
        _require_git_state(tmp_path)


def test_dispatches_freeze_both_public_only_layers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository_root, workspace_root = _phase_fixture(tmp_path, monkeypatch)

    result = freeze_fresh_v3_dispatches(
        repository_root,
        workspace_root,
        "20260730T060000Z",
    )

    assert set(result["run_ids"]) == {"l1", "l2"}
    for layer in ("l1", "l2"):
        run_root = (
            workspace_root
            / "artifacts/automatic-extraction-assessment/typed-extractor-v3-fresh-hidden-v1"
            / layer
            / "model-runs"
            / result["run_ids"][layer]
        )
        dispatch = load_json(run_root / "dispatch.json")
        assert dispatch["requested_model"] == "deepseek-chat"
        assert dispatch["history_context_inherited"] is False
        assert dispatch["authority_or_gold_allowed"] is False
        assert set(dispatch["allowed_files"]) == {
            f"proposer-prompt-{layer}.md",
            f"public-{layer}.json",
        }
        assert not any(
            word in json.dumps(dispatch["allowed_files"]).lower()
            for word in ("authority", "gold")
        )
        assert (run_root / "dispatch.json").stat().st_mode & 0o777 == 0o444


def test_layer_run_requires_both_frozen_dispatches_before_opener(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository_root, workspace_root = _phase_fixture(tmp_path, monkeypatch)
    result = freeze_fresh_v3_dispatches(
        repository_root,
        workspace_root,
        "20260730T060000Z",
    )
    l2_dispatch = (
        workspace_root
        / "artifacts/automatic-extraction-assessment/typed-extractor-v3-fresh-hidden-v1/l2"
        / "model-runs"
        / result["run_ids"]["l2"]
        / "dispatch.json"
    )
    l2_dispatch.unlink()
    calls: list[object] = []

    with pytest.raises((FileNotFoundError, ValueError), match="dispatch"):
        run_and_freeze_fresh_v3_layer(
            repository_root,
            workspace_root,
            "l1",
            base_url="https://example.test/v1",
            api_key="secret",
            timeout_seconds=30,
            opener=lambda *args, **kwargs: calls.append(args),
        )

    assert calls == []


@pytest.mark.parametrize("layer", ["l1", "l2"])
def test_one_shot_success_freezes_exact_public_only_chain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    layer: str,
) -> None:
    repository_root, workspace_root = _phase_fixture(tmp_path, monkeypatch)
    freeze_fresh_v3_dispatches(repository_root, workspace_root, "20260730T060000Z")
    raw = _proposal_response(workspace_root, layer)
    calls: list[tuple[object, int]] = []

    def opener(request: object, *, timeout: int) -> _FakeResponse:
        calls.append((request, timeout))
        return _FakeResponse(raw)

    result = run_and_freeze_fresh_v3_layer(
        repository_root,
        workspace_root,
        layer,  # type: ignore[arg-type]
        base_url="https://example.test/v1",
        api_key="secret",
        timeout_seconds=30,
        opener=opener,
    )

    assert len(calls) == 1
    request_body = json.loads(calls[0][0].data)  # type: ignore[union-attr]
    assert len(request_body["messages"]) == 2
    serialized_body = json.dumps(request_body, ensure_ascii=False).lower()
    assert f"authority-{layer}.json" not in serialized_body
    assert f"gold-{layer}.json" not in serialized_body
    user_payload = json.loads(request_body["messages"][1]["content"])
    assert set(user_payload) == {"dispatch_metadata", "public_input"}
    run_root = Path(result["run_root"])
    assert {path.name for path in run_root.iterdir()} == {
        "dispatch.json",
        "raw-response.json",
        "proposals.json",
        "provenance.json",
        "proposal-freeze-receipt.json",
    }
    assert all(path.stat().st_mode & 0o777 == 0o444 for path in run_root.iterdir())
    assert result["request_ordinal"] == 1
    assert validate_fresh_v3_proposal_freeze(
        repository_root,
        workspace_root,
        layer,  # type: ignore[arg-type]
    )["status"] == "valid"


@pytest.mark.parametrize("layer", ["l1", "l2"])
@pytest.mark.parametrize(
    ("failure", "expected_error"),
    [
        ("transport", RuntimeError),
        ("json", json.JSONDecodeError),
        ("metadata", ValueError),
        ("coverage", ValueError),
        ("reference", ValueError),
    ],
)
def test_one_shot_failure_is_frozen_without_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    layer: str,
    failure: str,
    expected_error: type[BaseException],
) -> None:
    repository_root, workspace_root = _phase_fixture(tmp_path, monkeypatch)
    freeze_fresh_v3_dispatches(repository_root, workspace_root, "20260730T060000Z")
    raw = b"not-json" if failure == "json" else _proposal_response(
        workspace_root,
        layer,
        mutate=failure if failure in {"metadata", "coverage", "reference"} else None,
    )
    calls = 0

    def opener(*_args: object, **_kwargs: object) -> _FakeResponse:
        nonlocal calls
        calls += 1
        if failure == "transport":
            raise RuntimeError("transport failed")
        return _FakeResponse(raw)

    with pytest.raises(expected_error):
        run_and_freeze_fresh_v3_layer(
            repository_root,
            workspace_root,
            layer,  # type: ignore[arg-type]
            base_url="https://example.test/v1",
            api_key="secret",
            timeout_seconds=30,
            opener=opener,
        )

    assert calls == 1
    evaluation_root = (
        workspace_root
        / "artifacts/automatic-extraction-assessment/typed-extractor-v3-fresh-hidden-v1"
    )
    run_root = next((evaluation_root / layer / "model-runs").iterdir())
    assert (run_root / "proposal-freeze-failure-receipt.json").is_file()
    assert not (run_root / "provenance.json").exists()
    assert len(list((evaluation_root / layer / "model-runs").iterdir())) == 1
