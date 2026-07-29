from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from tools.natural_memory_benchmark.cli import main as cli_main
from tools.natural_memory_benchmark.io import load_json, sha256_file
from tools.natural_memory_benchmark import typed_extractor_fresh_v2_prereg as prereg
from tools.natural_memory_benchmark.typed_extractor_fresh_v2_prereg import (
    freeze_typed_extractor_fresh_v2_preregistration,
    validate_typed_extractor_fresh_v2_preregistration,
)


LIVE_WORKSPACE = Path(".").resolve()
WORKSPACE = LIVE_WORKSPACE
FREEZE_TIME = "2026-07-28T13:30:00Z"
L1_PROMPT_SHA256 = (
    "b868bb2baaf1dfb3c27f99e2fe29888e2af0c57e56be3d2ecf70bfb6d2bcdfcf"
)
L2_PROMPT_SHA256 = (
    "d547a7d8b61eea33735bce4b3c96bb34466bb0fa6eb95d4e1b9070d64f211c6a"
)


@pytest.fixture(autouse=True)
def isolate_pre_authoring_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    bound_inputs = prereg._input_paths(LIVE_WORKSPACE)
    bound_code = prereg._code_paths(LIVE_WORKSPACE)
    workspace = tmp_path / "pre-authoring-workspace"
    workspace.mkdir()
    monkeypatch.setattr(prereg, "_input_paths", lambda _root: bound_inputs)
    monkeypatch.setattr(prereg, "_code_paths", lambda _root: bound_code)
    monkeypatch.setattr(sys.modules[__name__], "WORKSPACE", workspace)
    return workspace


def _freeze(tmp_path: Path) -> dict[str, object]:
    return freeze_typed_extractor_fresh_v2_preregistration(
        output_root=tmp_path / "prereg-v2",
        evaluation_root=tmp_path / "fresh-hidden-v2",
        workspace_root=WORKSPACE,
        freeze_time=FREEZE_TIME,
    )


def _validate(tmp_path: Path) -> dict[str, object]:
    return validate_typed_extractor_fresh_v2_preregistration(
        root=tmp_path / "prereg-v2",
        evaluation_root=tmp_path / "fresh-hidden-v2",
        workspace_root=WORKSPACE,
        freeze_time=FREEZE_TIME,
    )


def test_freeze_binds_final_chains_authorship_exact_gates_and_zero_writes(
    tmp_path: Path,
) -> None:
    result = _freeze(tmp_path)
    path = tmp_path / "prereg-v2" / "preregistration.json"
    payload = load_json(path)

    assert result == payload
    assert payload["schema_version"] == (
        "typed-extractor-fresh-v2-preregistration-v2"
    )
    assert payload["evaluation_id"] == "typed-extractor-v2-fresh-hidden-v2"
    assert payload["passing_chains"]["l1"]["prompt_sha256"] == L1_PROMPT_SHA256
    assert payload["passing_chains"]["l2"]["prompt_sha256"] == L2_PROMPT_SHA256
    assert payload["passing_chains"]["l1"]["run_id"].endswith(
        "typed-l1-dev-repair-v10"
    )
    assert payload["passing_chains"]["l2"]["run_id"].endswith(
        "typed-l2-dev-repair-v9"
    )

    authorship = payload["authorship"]
    assert authorship["policy"] == (
        "deterministic_blueprints_use_all_no_replacement_v1"
    )
    assert authorship["l1_case_count"] == 24
    assert authorship["l2_case_count"] == 12
    assert sum(authorship["l1_families"].values()) == 24
    assert sum(authorship["l2_families"].values()) == 12
    assert set(authorship["l1_families"].values()) == {4}
    assert set(authorship["l2_families"].values()) == {2}
    assert authorship["semantic_filtering_allowed"] is False
    assert authorship["case_replacement_allowed"] is False
    assert authorship["use_every_authored_blueprint"] is True

    assert set(payload["quality_thresholds"]) == {"l1", "l2"}
    assert all(
        value == 1.0
        for layer in payload["quality_thresholds"].values()
        for value in layer.values()
    )
    assert payload["safety_thresholds"] == {
        "raw_critical_false_emission_count": 0,
        "gate_intervention_count": 0,
        "deterministic_critical_false_materialization_count": 0,
    }
    assert payload["model_policy"]["requested_model"] == "deepseek-chat"
    assert payload["model_policy"]["history_context_inherited"] is False
    assert payload["model_policy"]["semantic_runs_per_layer"] == 1
    assert payload["model_policy"]["raw_and_gated_reported_separately"] is True
    assert payload["chronology"]["future_artifacts_absent_at_freeze"] is True
    assert payload["chronology"]["authoring_receipt_required_before_hidden"] is True
    assert payload["chronology"]["freeze_time_source"] == (
        "caller_supplied_untrusted_utc_label"
    )
    assert payload["chronology"]["evidence_kind"] == (
        "filesystem-presence-plus-sha256"
    )
    assert payload["claim_boundary"]["automatic_l1_write_count"] == 0
    assert payload["claim_boundary"]["automatic_l2_write_count"] == 0
    assert payload["claim_boundary"]["pipeline_integration_authorized"] is False
    assert payload["claim_boundary"]["longmemeval_status"] == (
        "structured_l2_identity_unresolved"
    )
    assert payload["input_sha256"][
        "l1-final/proposer-prompt-l1-v10.md"
    ] == L1_PROMPT_SHA256
    assert payload["input_sha256"][
        "l2-final/proposer-prompt-l2.md"
    ] == L2_PROMPT_SHA256
    assert "l1-dev/source-cases-l1.json" in payload["input_sha256"]
    assert "l2-dev/source-cases-l2.json" in payload["input_sha256"]
    assert "fresh-v1/preregistration.json" in payload["input_sha256"]
    assert "fresh-v1/l1/source-cases-l1.json" in payload["input_sha256"]
    assert "fresh-v1/l2/source-cases-l2.json" in payload["input_sha256"]
    assert path.stat().st_mode & 0o777 == 0o444
    assert not (tmp_path / "fresh-hidden-v2").exists()


def test_validate_rehashes_contract_and_reports_pre_authoring_state(
    tmp_path: Path,
) -> None:
    _freeze(tmp_path)

    assert _validate(tmp_path) == {
        "status": "valid",
        "evaluation_id": "typed-extractor-v2-fresh-hidden-v2",
        "l1_case_count": 24,
        "l2_case_count": 12,
        "future_artifacts_absent": True,
        "hidden_artifacts_created": False,
    }


def test_freeze_rejects_existing_evaluation_root(tmp_path: Path) -> None:
    (tmp_path / "fresh-hidden-v2").mkdir()

    with pytest.raises(ValueError, match="evaluation root must be absent"):
        _freeze(tmp_path)


def test_live_post_authoring_workspace_is_rejected(tmp_path: Path) -> None:
    assert all(
        (LIVE_WORKSPACE / path).is_file()
        for path in prereg.FUTURE_WORKSPACE_PATHS
    )

    with pytest.raises(ValueError, match="future authoring artifact must be absent"):
        freeze_typed_extractor_fresh_v2_preregistration(
            output_root=tmp_path / "live-prereg-v2",
            evaluation_root=tmp_path / "live-fresh-hidden-v2",
            workspace_root=LIVE_WORKSPACE,
            freeze_time=FREEZE_TIME,
        )


def test_freeze_rejects_premature_authoring_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    premature = tmp_path / "typed_extractor_fresh_v2_authoring.py"
    premature.write_text("premature = True\n", encoding="utf-8")
    monkeypatch.setattr(prereg, "FUTURE_WORKSPACE_PATHS", (str(premature),))

    with pytest.raises(ValueError, match="future authoring artifact must be absent"):
        _freeze(tmp_path)


def test_validate_rejects_premature_authoring_receipt(tmp_path: Path) -> None:
    _freeze(tmp_path)
    receipt = tmp_path / "prereg-v2" / "authoring-implementation-receipt.json"
    receipt.write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="future authoring receipt must be absent"):
        _validate(tmp_path)


def test_validate_rejects_bound_input_hash_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _freeze(tmp_path)
    original = prereg.sha256_file

    def drift_one(path: Path) -> str:
        if path.name == "proposer-prompt-l1-v10.md":
            return "0" * 64
        return original(path)

    monkeypatch.setattr(prereg, "sha256_file", drift_one)

    with pytest.raises(ValueError, match="frozen passing chain hash mismatch"):
        _validate(tmp_path)


def test_validate_rejects_unknown_contract_fields(tmp_path: Path) -> None:
    _freeze(tmp_path)
    path = tmp_path / "prereg-v2" / "preregistration.json"
    payload = load_json(path)
    payload["unregistered"] = True
    path.chmod(0o644)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n",
        encoding="utf-8",
    )
    path.chmod(0o444)

    with pytest.raises(ValidationError, match="extra_forbidden"):
        _validate(tmp_path)


@pytest.mark.parametrize(
    ("field_path", "coercive_value"),
    [
        (("quality_thresholds", "l1", "proposal_coverage"), "1.0"),
        (("safety_thresholds", "raw_critical_false_emission_count"), False),
        (("authorship", "l1_families", "explicit_event_roles"), "4"),
    ],
)
def test_validate_rejects_coercive_contract_types(
    tmp_path: Path,
    field_path: tuple[str, ...],
    coercive_value: object,
) -> None:
    _freeze(tmp_path)
    path = tmp_path / "prereg-v2" / "preregistration.json"
    payload = load_json(path)
    target = payload
    for key in field_path[:-1]:
        target = target[key]
    target[field_path[-1]] = coercive_value
    path.chmod(0o644)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n",
        encoding="utf-8",
    )
    path.chmod(0o444)

    with pytest.raises(ValidationError):
        _validate(tmp_path)


def test_freeze_rejects_impossible_utc_time(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="valid UTC timestamp"):
        freeze_typed_extractor_fresh_v2_preregistration(
            output_root=tmp_path / "prereg-v2",
            evaluation_root=tmp_path / "fresh-hidden-v2",
            workspace_root=WORKSPACE,
            freeze_time="2026-07-28T24:00:00Z",
        )


def test_validate_rejects_bound_code_hash_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _freeze(tmp_path)
    original = prereg.sha256_file

    def drift_code(path: Path) -> str:
        if path.name == "cli.py":
            return "f" * 64
        return original(path)

    monkeypatch.setattr(prereg, "sha256_file", drift_code)

    with pytest.raises(ValueError, match="preregistration drift"):
        _validate(tmp_path)


def test_cli_freezes_and_validates_v2_preregistration(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    prereg_root = tmp_path / "prereg-v2"
    evaluation_root = tmp_path / "fresh-hidden-v2"
    common = [
        "--evaluation-root",
        str(evaluation_root),
        "--workspace-root",
        str(WORKSPACE),
        "--freeze-time",
        FREEZE_TIME,
    ]

    assert cli_main(
        [
            "freeze-typed-extractor-fresh-v2-preregistration",
            *common,
            "--output-root",
            str(prereg_root),
        ]
    ) == 0
    assert cli_main(
        [
            "validate-typed-extractor-fresh-v2-preregistration",
            *common,
            "--root",
            str(prereg_root),
        ]
    ) == 0
    output_lines = capsys.readouterr().out.strip().splitlines()
    assert json.loads(output_lines[0]) == {
        "evaluation_id": "typed-extractor-v2-fresh-hidden-v2",
        "l1_case_count": 24,
        "l2_case_count": 12,
        "status": "frozen",
    }
    assert json.loads(output_lines[1]) == {
        "evaluation_id": "typed-extractor-v2-fresh-hidden-v2",
        "future_artifacts_absent": True,
        "hidden_artifacts_created": False,
        "l1_case_count": 24,
        "l2_case_count": 12,
        "status": "valid",
    }
    payload = load_json(prereg_root / "preregistration.json")
    assert payload["input_sha256"][
        "l1-final/proposer-prompt-l1-v10.md"
    ] == L1_PROMPT_SHA256
    assert len(sha256_file(prereg_root / "preregistration.json")) == 64
