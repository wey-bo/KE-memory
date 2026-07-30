from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

import pytest

from tools.natural_memory_benchmark.io import (
    canonical_json_bytes,
    load_json,
    sha256_file,
    write_json_immutable,
)
from tools.natural_memory_benchmark import typed_extractor_fresh_v3_qualification as qualification
from tools.natural_memory_benchmark.typed_extractor_fresh_v3_qualification import (
    L1_QUALITY_METRICS,
    L2_QUALITY_METRICS,
    V3_L1_OUTPUTS,
    V3_L2_OUTPUTS,
    V3_L2_THRESHOLDS,
    freeze_incomplete_fresh_v3_qualification,
    score_and_qualify_fresh_v3,
    validate_fresh_v3_qualification,
)


def _fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path, dict[str, Path]]:
    repository_root = tmp_path / "repository"
    workspace_root = repository_root / "research/next-prep"
    evaluation_root = (
        workspace_root
        / "artifacts/automatic-extraction-assessment/typed-extractor-v3-fresh-hidden-v1"
    )
    runs: dict[str, Path] = {}
    for layer in ("l1", "l2"):
        layer_root = evaluation_root / layer
        layer_root.mkdir(parents=True, mode=0o775)
        run_root = layer_root / "model-runs" / f"run-test-{layer}"
        run_root.mkdir(parents=True, mode=0o775)
        run_root.parent.chmod(0o775)
        run_root.chmod(0o775)
        for name in (
            "dispatch.json",
            "raw-response.json",
            "proposals.json",
            "provenance.json",
            "proposal-freeze-receipt.json",
        ):
            write_json_immutable(run_root / name, {"fixture": f"{layer}-{name}"})
            (run_root / name).chmod(0o444)
        runs[layer] = run_root
    evaluation_root.chmod(0o775)
    (evaluation_root / "l1").chmod(0o775)
    (evaluation_root / "l2").chmod(0o775)
    monkeypatch.setattr(
        qualification,
        "_roots",
        lambda supplied_repository, supplied_workspace: (
            supplied_repository,
            supplied_workspace,
            evaluation_root,
        ),
    )
    monkeypatch.setattr(
        qualification,
        "_qualification_bindings",
        lambda *_args: {
            "head": "d" * 40,
            "implementation_sha256": {"qualification.py": "a" * 64},
            "parallel_sha256": {"parallel.py": "b" * 64},
            "automatic_write_counts": {
                "aggregate": 0,
                "closure": 0,
                "identity": 0,
                "l1": 0,
                "l2": 0,
                "membership": 0,
                "revision": 0,
                "snapshot": 0,
                "source_revision": 0,
            },
        },
    )
    return repository_root, workspace_root, runs


def _receipt(layer: str, run_root: Path) -> dict[str, Any]:
    return {
        "status": "valid",
        "layer": layer,
        "run_id": run_root.name,
        "run_root": str(run_root),
        "request_count": 1,
        "request_ordinal": 1,
        "requested_model": "deepseek-chat",
        "response_model": "deepseek-v4-flash",
        "receipt_sha256": sha256_file(run_root / "proposal-freeze-receipt.json"),
    }


def _score(layer: str, run_root: Path, *, metric: str | None = None, safety: str | None = None) -> dict[str, Any]:
    quality_names = L1_QUALITY_METRICS if layer == "l1" else L2_QUALITY_METRICS
    metrics = {name: 1.0 for name in quality_names}
    metrics.update(
        {
            "raw_critical_false_emission_count": 0,
            "gate_intervention_count": 0,
            "deterministic_critical_false_materialization_count": 0,
        }
    )
    if metric is not None:
        metrics[metric] = 0.9
    if safety is not None:
        metrics[safety] = 1
    return {
        "schema_version": f"typed-extractor-{layer}-score-v1",
        "dataset_id": f"typed-extractor-v3-fresh-hidden-v1-{layer}",
        "run_id": run_root.name,
        "case_count": 24 if layer == "l1" else 18,
        "raw_proposer_quality_ready": metric is None and safety != "raw_critical_false_emission_count",
        "deterministic_gate_safety_ready": safety not in {
            "gate_intervention_count",
            "deterministic_critical_false_materialization_count",
        },
        "metrics": metrics,
        "cases": [],
        "error_taxonomy": {},
        "gate_reason_counts": {},
        "guard_state": {"unchanged": True},
        "claim_boundary": {},
    }


def _install_scorers(
    monkeypatch: pytest.MonkeyPatch,
    runs: dict[str, Path],
    calls: list[str],
    *,
    metric: tuple[str, str] | None = None,
    safety: tuple[str, str] | None = None,
) -> None:
    def scorer(layer: str):
        def run(*_args: object, **kwargs: Any) -> dict[str, Any]:
            calls.append(layer)
            assert kwargs["manifest_output_names"] == (
                V3_L1_OUTPUTS if layer == "l1" else V3_L2_OUTPUTS
            )
            if layer == "l2":
                assert kwargs["required_thresholds"] == V3_L2_THRESHOLDS
            score = _score(
                layer,
                runs[layer],
                metric=metric[1] if metric and metric[0] == layer else None,
                safety=safety[1] if safety and safety[0] == layer else None,
            )
            write_json_immutable(kwargs["score_path"], score)
            write_json_immutable(kwargs["error_analysis_path"], {"cases": []})
            kwargs["report_path"].write_text(f"# {layer} report\n", encoding="utf-8")
            for key in ("score_path", "error_analysis_path", "report_path"):
                kwargs[key].chmod(0o444)
            return score

        return run

    monkeypatch.setattr(qualification, "run_l1_scoring_file", scorer("l1"))
    monkeypatch.setattr(qualification, "run_l2_scoring_file", scorer("l2"))


def _replace_l2_with_failure(
    runs: dict[str, Path],
    *,
    implementation_sha256: dict[str, str],
) -> None:
    receipt_path = runs["l2"] / "proposal-freeze-receipt.json"
    receipt_path.chmod(0o644)
    receipt_path.unlink()
    write_json_immutable(
        runs["l2"] / "proposal-freeze-failure-receipt.json",
        {
            "schema_version": "typed-extractor-fresh-v3-proposal-failure-v1",
            "status": "frozen_failure",
            "evaluation_id": "typed-extractor-v3-fresh-hidden-v1",
            "layer": "l2",
            "run_id": runs["l2"].name,
            "request_ordinal": 1,
            "request_count": 1,
            "requested_model": "deepseek-chat",
            "failure_type": "ValueError",
            "failure_message": "invalid proposal",
            "retry_performed": False,
            "fallback_model_used": False,
            "preflight_sha256": "a" * 64,
            "implementation_sha256": implementation_sha256,
            "parallel_sha256": {"parallel.py": "b" * 64},
            "artifacts": {},
        },
    )
    (runs["l2"] / "proposal-freeze-failure-receipt.json").chmod(0o444)


def test_qualification_api_has_no_transport_or_credential_parameter() -> None:
    parameters = inspect.signature(score_and_qualify_fresh_v3).parameters
    assert set(parameters) == {"repository_root", "workspace_root", "qualification_time"}


def test_no_scorer_runs_until_both_proposal_receipts_validate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository_root, workspace_root, runs = _fixture(tmp_path, monkeypatch)
    validations: list[str] = []
    scorer_calls: list[str] = []

    def validate(_repository: Path, _workspace: Path, layer: str) -> dict[str, Any]:
        validations.append(layer)
        if layer == "l2":
            raise ValueError("l2 proposal receipt drift")
        return _receipt(layer, runs[layer])

    monkeypatch.setattr(qualification, "validate_fresh_v3_proposal_freeze", validate)
    _install_scorers(monkeypatch, runs, scorer_calls)

    with pytest.raises(ValueError, match="l2 proposal receipt drift"):
        score_and_qualify_fresh_v3(
            repository_root,
            workspace_root,
            "2026-07-30T07:00:00Z",
        )

    assert validations == ["l1", "l2"]
    assert scorer_calls == []


@pytest.mark.parametrize(
    ("metric", "safety", "expected"),
    [
        (None, None, "qualified"),
        (("l1", "role_or_local_entity_accuracy"), None, "not_qualified"),
        (("l2", "structured_claim_accuracy"), None, "not_qualified"),
        (None, ("l1", "gate_intervention_count"), "not_qualified"),
        (None, ("l2", "raw_critical_false_emission_count"), "not_qualified"),
    ],
)
def test_exact_raw_and_gate_contract_controls_qualification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    metric: tuple[str, str] | None,
    safety: tuple[str, str] | None,
    expected: str,
) -> None:
    repository_root, workspace_root, runs = _fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(
        qualification,
        "validate_fresh_v3_proposal_freeze",
        lambda _repository, _workspace, layer: _receipt(layer, runs[layer]),
    )
    scorer_calls: list[str] = []
    _install_scorers(
        monkeypatch,
        runs,
        scorer_calls,
        metric=metric,
        safety=safety,
    )

    result = score_and_qualify_fresh_v3(
        repository_root,
        workspace_root,
        "2026-07-30T07:00:00Z",
    )

    assert scorer_calls == ["l1", "l2"]
    assert result["status"] == expected
    overall = load_json(
        workspace_root
        / "artifacts/automatic-extraction-assessment/typed-extractor-v3-fresh-hidden-v1/overall-score.json"
    )
    assert overall["status"] == expected
    assert set(overall["layers"]["l1"]["quality_checks"]) == set(L1_QUALITY_METRICS)
    assert set(overall["layers"]["l2"]["quality_checks"]) == set(L2_QUALITY_METRICS)
    assert validate_fresh_v3_qualification(repository_root, workspace_root)["status"] == expected


def test_incomplete_conclusion_never_invokes_a_scorer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository_root, workspace_root, runs = _fixture(tmp_path, monkeypatch)
    _replace_l2_with_failure(
        runs,
        implementation_sha256={"qualification.py": "a" * 64},
    )
    scorer_calls: list[str] = []
    _install_scorers(monkeypatch, runs, scorer_calls)
    monkeypatch.setattr(
        qualification,
        "validate_fresh_v3_proposal_freeze",
        lambda _repository, _workspace, layer: (
            _receipt(layer, runs[layer])
            if layer == "l1"
            else (_ for _ in ()).throw(ValueError("frozen proposer failure"))
        ),
    )

    result = freeze_incomplete_fresh_v3_qualification(
        repository_root,
        workspace_root,
        "2026-07-30T07:00:00Z",
    )

    assert scorer_calls == []
    assert result["status"] == "incomplete_not_qualified"
    assert result["layers"]["l2"]["failure_type"] == "ValueError"
    assert validate_fresh_v3_qualification(
        repository_root,
        workspace_root,
    )["status"] == "incomplete_not_qualified"

    failure_path = runs["l2"] / "proposal-freeze-failure-receipt.json"
    failure = load_json(failure_path)
    failure["failure_message"] = "tampered failure"
    failure_path.chmod(0o644)
    failure_path.write_bytes(canonical_json_bytes(failure))
    failure_path.chmod(0o444)
    with pytest.raises(ValueError, match="incomplete proposal binding"):
        validate_fresh_v3_qualification(repository_root, workspace_root)


def test_incomplete_conclusion_rejects_failure_receipt_code_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository_root, workspace_root, runs = _fixture(tmp_path, monkeypatch)
    _replace_l2_with_failure(
        runs,
        implementation_sha256={"qualification.py": "f" * 64},
    )
    monkeypatch.setattr(
        qualification,
        "validate_fresh_v3_proposal_freeze",
        lambda _repository, _workspace, layer: (
            _receipt(layer, runs[layer])
            if layer == "l1"
            else (_ for _ in ()).throw(ValueError("frozen proposer failure"))
        ),
    )

    with pytest.raises(ValueError, match="failure receipt binding"):
        freeze_incomplete_fresh_v3_qualification(
            repository_root,
            workspace_root,
            "2026-07-30T07:00:00Z",
        )


def test_scorer_failure_freezes_not_qualified_and_stops(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository_root, workspace_root, runs = _fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(
        qualification,
        "validate_fresh_v3_proposal_freeze",
        lambda _repository, _workspace, layer: _receipt(layer, runs[layer]),
    )
    scorer_calls: list[str] = []

    def fail_l1(*_args: object, **_kwargs: object) -> dict[str, Any]:
        scorer_calls.append("l1")
        raise RuntimeError("deterministic scorer failed")

    def forbid_l2(*_args: object, **_kwargs: object) -> dict[str, Any]:
        scorer_calls.append("l2")
        raise AssertionError("L2 scorer must not run after L1 scorer failure")

    monkeypatch.setattr(qualification, "run_l1_scoring_file", fail_l1)
    monkeypatch.setattr(qualification, "run_l2_scoring_file", forbid_l2)

    result = score_and_qualify_fresh_v3(
        repository_root,
        workspace_root,
        "2026-07-30T07:00:00Z",
    )

    assert scorer_calls == ["l1"]
    assert result["status"] == "not_qualified"
    assert result["layers"]["l1"]["failure_class"] == "scorer_failure:RuntimeError"
    assert result["layers"]["l2"]["status"] == "not_scored"
    assert validate_fresh_v3_qualification(
        repository_root,
        workspace_root,
    )["status"] == "not_qualified"
