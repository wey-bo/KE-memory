from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from tools.natural_memory_benchmark import typed_extractor_fresh_v3_prereg as prereg
from tools.natural_memory_benchmark.cli import main as cli_main
from tools.natural_memory_benchmark.io import load_json, sha256_file
from tools.natural_memory_benchmark.portable_immutability import ImmutabilityViolation
from tools.natural_memory_benchmark.typed_extractor_fresh_v3_prereg import (
    freeze_typed_extractor_fresh_v3_preregistration,
    validate_typed_extractor_fresh_v3_preregistration,
)


WORKSPACE = Path(__file__).resolve().parents[2]
FREEZE_TIME = "2026-07-29T06:00:00Z"
L1_PROMPT_SHA256 = (
    "a5250a453863f3cfd388613d6633d8a529485a11c5226d2965c8235a9c1dc342"
)
L2_PROMPT_SHA256 = (
    "d547a7d8b61eea33735bce4b3c96bb34466bb0fa6eb95d4e1b9070d64f211c6a"
)


def _freeze(tmp_path: Path) -> dict[str, object]:
    return freeze_typed_extractor_fresh_v3_preregistration(
        output_root=tmp_path / "prereg-v3",
        evaluation_root=tmp_path / "fresh-hidden-v3",
        workspace_root=WORKSPACE,
        freeze_time=FREEZE_TIME,
    )


def _validate(tmp_path: Path) -> dict[str, object]:
    return validate_typed_extractor_fresh_v3_preregistration(
        root=tmp_path / "prereg-v3",
        evaluation_root=tmp_path / "fresh-hidden-v3",
        workspace_root=WORKSPACE,
        freeze_time=FREEZE_TIME,
    )


def _rewrite(path: Path, payload: dict[str, object]) -> None:
    path.chmod(0o644)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n",
        encoding="utf-8",
    )
    path.chmod(0o444)


def test_freeze_binds_taxonomy_chains_composition_gates_and_zero_writes(
    tmp_path: Path,
) -> None:
    result = _freeze(tmp_path)
    path = tmp_path / "prereg-v3" / "preregistration.json"
    payload = load_json(path)

    assert result == payload
    assert payload["schema_version"] == (
        "typed-extractor-fresh-v3-preregistration-v1"
    )
    assert payload["evaluation_id"] == "typed-extractor-v3-fresh-hidden-v1"
    assert payload["passing_chains"]["l1"]["prompt_sha256"] == L1_PROMPT_SHA256
    assert payload["passing_chains"]["l2"]["prompt_sha256"] == L2_PROMPT_SHA256
    assert payload["passing_chains"]["l1"]["run_id"].endswith(
        "typed-l1-taxonomy-repair-v1"
    )
    assert payload["passing_chains"]["l2"]["run_id"].endswith(
        "typed-l2-taxonomy-baseline-v1"
    )

    authorship = payload["authorship"]
    assert authorship["policy"] == (
        "deterministic_blueprints_use_all_no_replacement_v2"
    )
    assert authorship["l1_case_count"] == 24
    assert authorship["l2_case_count"] == 18
    assert authorship["l1_families"] == {
        "condition_or_scope": 3,
        "derivation_or_speaker": 3,
        "evidence": 3,
        "false_abstention": 3,
        "false_emission": 3,
        "lifecycle": 3,
        "role_or_local_entity": 3,
        "time": 3,
    }
    assert authorship["l2_families"] == {
        "coreference_case": 2,
        "incompatible_support_control": 2,
        "incomplete_closure_control": 2,
        "lifecycle_case": 2,
        "preference_aggregation_case": 2,
        "state_summary_case": 2,
        "task_composition_case": 2,
        "unresolved_selection_control": 2,
        "unsupported_modality_control": 2,
    }
    assert authorship["semantic_filtering_allowed"] is False
    assert authorship["case_replacement_allowed"] is False
    assert authorship["post_generation_resampling_allowed"] is False
    assert authorship["use_every_authored_blueprint"] is True

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
    assert payload["model_policy"]["history_context_inherited"] is False
    assert payload["model_policy"]["public_payload_only"] is True
    assert payload["model_policy"]["semantic_runs_per_layer"] == 1
    assert payload["model_policy"]["raw_and_gated_reported_separately"] is True
    assert payload["chronology"]["future_artifacts_absent_at_freeze"] is True
    assert payload["chronology"]["preregistration_validator_phase"] == (
        "pre_authoring_only"
    )
    assert payload["claim_boundary"]["hidden_artifact_write_count"] == 0
    assert payload["claim_boundary"]["model_request_count"] == 0
    assert payload["claim_boundary"]["automatic_l1_write_count"] == 0
    assert payload["claim_boundary"]["automatic_l2_write_count"] == 0
    assert payload["claim_boundary"]["pipeline_integration_authorized"] is False
    assert payload["claim_boundary"]["longmemeval_status"] == (
        "structured_l2_identity_unresolved"
    )
    assert payload["input_sha256"]["taxonomy-l1/prompt.md"] == L1_PROMPT_SHA256
    assert payload["input_sha256"]["taxonomy-l2/prompt.md"] == L2_PROMPT_SHA256
    assert "taxonomy-l1/diagnostic-source-l1.json" in payload["input_sha256"]
    assert "taxonomy-l2/diagnostic-source-l2.json" in payload["input_sha256"]
    assert "fresh-v2/chronology-receipt.json" in payload["input_sha256"]
    assert "fresh-v2/l1/source-cases-l1.json" in payload["input_sha256"]
    assert "fresh-v2/l2/source-cases-l2.json" in payload["input_sha256"]
    assert path.stat().st_mode & 0o777 == 0o444
    assert {item.name for item in path.parent.iterdir()} == {"preregistration.json"}
    assert not (tmp_path / "fresh-hidden-v3").exists()


def test_validate_rehashes_contract_and_reports_pre_authoring_state(
    tmp_path: Path,
) -> None:
    _freeze(tmp_path)

    assert _validate(tmp_path) == {
        "status": "valid",
        "evaluation_id": "typed-extractor-v3-fresh-hidden-v1",
        "l1_case_count": 24,
        "l2_case_count": 18,
        "future_artifacts_absent": True,
        "hidden_artifacts_created": False,
        "model_request_count": 0,
    }


def test_freeze_rejects_existing_output_or_evaluation_root(tmp_path: Path) -> None:
    (tmp_path / "fresh-hidden-v3").mkdir()
    with pytest.raises(ValueError, match="evaluation root must be absent"):
        _freeze(tmp_path)

    (tmp_path / "fresh-hidden-v3").rmdir()
    (tmp_path / "prereg-v3").mkdir()
    with pytest.raises(ValueError, match="preregistration root must be absent"):
        _freeze(tmp_path)


@pytest.mark.parametrize(
    "future_name",
    [
        "typed_extractor_fresh_v3_authoring.py",
        "test_typed_extractor_fresh_v3_authoring.py",
        "typed_extractor_fresh_v3_materialization.py",
        "test_typed_extractor_fresh_v3_materialization.py",
    ],
)
def test_freeze_rejects_guard_paths_the_preregistration_never_declared(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    future_name: str,
) -> None:
    """A widened guard path list must fail against the frozen declaration.

    Was: create the file and expect "future implementation artifact must be
    absent". All four of those files exist now -- since before the reorganization
    baseline -- so that check can never pass again. The claim is verified against
    the frozen preregistration instead, which listed exactly the paths it expected
    to be created later. Substituting a path it never declared is now the failure,
    and it is a stronger one: it catches a guard quietly changing its own scope,
    which the filesystem check could not see.
    """
    premature = tmp_path / future_name
    premature.write_text("premature = True\n", encoding="utf-8")
    monkeypatch.setattr(prereg, "FUTURE_WORKSPACE_PATHS", (str(premature),))

    with pytest.raises(ImmutabilityViolation) as error:
        _freeze(tmp_path)
    assert error.value.violation == "guard_path_not_declared_future"


def test_freeze_accepts_the_declared_future_paths_even_though_they_exist(
    tmp_path: Path,
) -> None:
    """The inverse: the real, declared path set must not block a freeze now."""
    for raw in prereg.FUTURE_WORKSPACE_PATHS:
        assert (WORKSPACE / raw).exists(), (
            f"precondition: {raw} exists, which is why the live check expired"
        )
    _freeze(tmp_path)


def test_validate_still_declares_the_authoring_receipt_as_future_work(
    tmp_path: Path,
) -> None:
    """The receipt's ordering claim survives as a declaration, not a live check.

    Was: write a stub receipt and expect "future authoring receipt must be
    absent". The real receipt was committed as evidence, so that check expired.
    What must remain true is that the frozen preregistration declared the receipt
    as future work -- otherwise the ordering was never established at all.
    """
    _freeze(tmp_path)
    receipt = tmp_path / "prereg-v3" / "authoring-implementation-receipt.json"
    receipt.write_text("{}\n", encoding="utf-8")

    # Validation no longer fails on the receipt's presence.
    _validate(tmp_path)

    from tools.natural_memory_benchmark.expired_temporal_guard import (
        load_frozen_preregistration,
    )

    declared = load_frozen_preregistration(WORKSPACE)["expected_future_paths"]
    assert "preregistration:authoring-implementation-receipt.json" in declared


def test_validate_rejects_bound_passing_input_hash_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _freeze(tmp_path)
    original = prereg.sha256_file

    def drift_one(path: Path) -> str:
        if path.name == "proposer-prompt-l1.md":
            return "0" * 64
        return original(path)

    monkeypatch.setattr(prereg, "sha256_file", drift_one)
    with pytest.raises(ValueError, match="frozen passing chain hash mismatch"):
        _validate(tmp_path)


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


def test_validate_rejects_unknown_contract_fields(tmp_path: Path) -> None:
    _freeze(tmp_path)
    path = tmp_path / "prereg-v3" / "preregistration.json"
    payload = load_json(path)
    payload["unregistered"] = True
    _rewrite(path, payload)

    with pytest.raises(ValidationError, match="extra_forbidden"):
        _validate(tmp_path)


@pytest.mark.parametrize(
    ("field_path", "coercive_value"),
    [
        (("quality_thresholds", "l1", "proposal_coverage"), "1.0"),
        (("safety_thresholds", "raw_critical_false_emission_count"), False),
        (("authorship", "l1_families", "false_emission"), "3"),
    ],
)
def test_validate_rejects_coercive_contract_types(
    tmp_path: Path,
    field_path: tuple[str, ...],
    coercive_value: object,
) -> None:
    _freeze(tmp_path)
    path = tmp_path / "prereg-v3" / "preregistration.json"
    payload = load_json(path)
    target = payload
    for key in field_path[:-1]:
        target = target[key]
    target[field_path[-1]] = coercive_value
    _rewrite(path, payload)

    with pytest.raises(ValidationError):
        _validate(tmp_path)


def test_freeze_rejects_impossible_utc_time(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="valid UTC timestamp"):
        freeze_typed_extractor_fresh_v3_preregistration(
            output_root=tmp_path / "prereg-v3",
            evaluation_root=tmp_path / "fresh-hidden-v3",
            workspace_root=WORKSPACE,
            freeze_time="2026-07-29T24:00:00Z",
        )


def test_cli_freezes_and_validates_v3_preregistration(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    prereg_root = tmp_path / "prereg-v3"
    evaluation_root = tmp_path / "fresh-hidden-v3"
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
            "freeze-typed-extractor-fresh-v3-preregistration",
            *common,
            "--output-root",
            str(prereg_root),
        ]
    ) == 0
    assert cli_main(
        [
            "validate-typed-extractor-fresh-v3-preregistration",
            *common,
            "--root",
            str(prereg_root),
        ]
    ) == 0
    output_lines = capsys.readouterr().out.strip().splitlines()
    assert json.loads(output_lines[0]) == {
        "evaluation_id": "typed-extractor-v3-fresh-hidden-v1",
        "l1_case_count": 24,
        "l2_case_count": 18,
        "status": "frozen",
    }
    assert json.loads(output_lines[1]) == {
        "evaluation_id": "typed-extractor-v3-fresh-hidden-v1",
        "future_artifacts_absent": True,
        "hidden_artifacts_created": False,
        "l1_case_count": 24,
        "l2_case_count": 18,
        "model_request_count": 0,
        "status": "valid",
    }
    assert len(sha256_file(prereg_root / "preregistration.json")) == 64
