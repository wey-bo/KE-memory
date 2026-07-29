from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

import pytest

from tools.natural_memory_benchmark.io import load_json
from tools.natural_memory_benchmark.typed_extractor_dev_repair_qualification import (
    L1_EXACT,
    L2_EXACT,
    qualify_dev_repair,
)


L1_ROOT = Path(
    "artifacts/automatic-extraction-assessment/"
    "typed-extractor-v2-l1-dev-repair-v1"
)
L2_ROOT = Path(
    "artifacts/automatic-extraction-assessment/"
    "typed-extractor-v2-l2-dev-repair-v1"
)
GUARD_STATE = {
    "before_fingerprint": "a" * 64,
    "after_fingerprint": "a" * 64,
    "before_counts": {
        "closure_evaluation_count": 6,
        "closure_spec_count": 6,
        "l1_unit_count": 13,
        "l2_unit_count": 1,
        "query_plan_count": 5,
        "raw_artifact_revision_count": 2,
        "source_record_revision_count": 13,
        "unit_revision_count": 14,
    },
    "after_counts": {
        "closure_evaluation_count": 6,
        "closure_spec_count": 6,
        "l1_unit_count": 13,
        "l2_unit_count": 1,
        "query_plan_count": 5,
        "raw_artifact_revision_count": 2,
        "source_record_revision_count": 13,
        "unit_revision_count": 14,
    },
}


def _copy_root(source: Path, target: Path, layer: str) -> None:
    target.mkdir(parents=True)
    for name in (
        f"public-{layer}.json",
        f"authority-{layer}.json",
        f"gold-{layer}.json",
        f"manifest-{layer}.json",
    ):
        shutil.copyfile(source / name, target / name)
        target.joinpath(name).chmod(0o444)


def _score_payload(root: Path, layer: str, run_id: str) -> dict:
    gold = load_json(root / f"gold-{layer}.json")
    exact = L1_EXACT if layer == "l1" else L2_EXACT
    metrics = {name: 1.0 for name in exact}
    metrics.update(
        {
            "raw_abstention_precision": 1.0,
            "raw_abstention_recall": 1.0,
            "gated_decision_accuracy": 1.0,
            "raw_critical_false_emission_count": 0,
            "gate_intervention_count": 0,
            "deterministic_critical_false_materialization_count": 0,
        }
    )
    decision = "expected_decision"
    cases = [
        {
            "case_id": item["case_id"],
            "expected_decision": item[decision],
            "raw_decision": item[decision],
            "gated_decision": item[decision],
            "raw_errors": [],
            "gate_reasons": [],
        }
        for item in gold["items"]
    ]
    if layer == "l1":
        claim_boundary = {
            "automatic_closure_write_count": 0,
            "automatic_identity_write_count": 0,
            "automatic_l1_write_count": 0,
            "automatic_l2_write_count": 0,
            "automatic_membership_write_count": 0,
            "automatic_unit_revision_write_count": 0,
            "embedding_authority": False,
            "fresh_hidden_created": False,
            "longmemeval_status": "structured_l2_identity_unresolved",
        }
        return {
            "schema_version": "typed-extractor-l1-score-v1",
            "status": "pass",
            "dataset_id": gold["dataset_id"],
            "run_id": run_id,
            "case_count": gold["case_count"],
            "raw_proposer_quality_ready": True,
            "deterministic_gate_safety_ready": True,
            "metrics": metrics,
            "cases": cases,
            "error_taxonomy": {},
            "gate_reason_counts": {},
            "guard_state": {**GUARD_STATE, "unchanged": True},
            "claim_boundary": claim_boundary,
        }
    return {
        "schema_version": "typed-extractor-l2-score-v2",
        "status": "scored",
        "scoring_policy_version": "evidence-set-abstraction-method-v2",
        "dataset_id": gold["dataset_id"],
        "run_id": run_id,
        "case_count": gold["case_count"],
        "raw_proposer_quality_ready": True,
        "deterministic_gate_safety_ready": True,
        "metrics": metrics,
        "cases": cases,
        "error_taxonomy": {},
        "gate_reason_counts": {},
        "guard_state": copy.deepcopy(GUARD_STATE),
        "claim_boundary": {
            "automatic_write_counts": {
                "closure": 0,
                "identity": 0,
                "l1": 0,
                "l2": 0,
                "membership": 0,
                "unit_revision": 0,
            },
            "embedding_authority": False,
            "fresh_hidden_created": False,
            "longmemeval_status": "structured_l2_identity_unresolved",
            "pipeline_integration_authorized": False,
        },
    }


def _write_score(root: Path, layer: str, payload: dict) -> Path:
    path = root / "model-runs" / payload["run_id"] / "score.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    path.chmod(0o444)
    return path


@pytest.mark.parametrize(
    ("layer", "formal_root"),
    (("l1", L1_ROOT), ("l2", L2_ROOT)),
)
def test_exact_diagnostic_score_qualifies_and_replays(
    tmp_path: Path,
    layer: str,
    formal_root: Path,
) -> None:
    root = tmp_path / layer
    _copy_root(formal_root, root, layer)
    run_id = f"run-diagnostic-{layer}-exact"
    score_path = _write_score(root, layer, _score_payload(root, layer, run_id))
    output_path = score_path.parent / "dev-repair-qualification.json"
    report_path = score_path.parent / "dev-repair-qualification.md"

    first = qualify_dev_repair(layer, score_path, output_path, report_path)
    second = qualify_dev_repair(layer, score_path, output_path, report_path)

    assert first == second
    assert first["raw_proposer_quality_ready"] is True
    assert first["deterministic_gate_safety_ready"] is True
    assert first["dev_repair_ready"] is True
    assert first["fresh_hidden_v2_authorized"] is False
    assert all(first["exact_metric_checks"].values())
    report = report_path.read_text(encoding="utf-8")
    assert "diagnostic-only" in report
    assert "not natural benchmark evidence" in report
    assert "fresh-v2 remains unauthorized" in report
    assert output_path.stat().st_mode & 0o777 == 0o444
    assert report_path.stat().st_mode & 0o777 == 0o444


def test_scorer_readiness_is_insufficient_below_exact_or_with_intervention(
    tmp_path: Path,
) -> None:
    root = tmp_path / "l1"
    _copy_root(L1_ROOT, root, "l1")
    payload = _score_payload(root, "l1", "run-diagnostic-l1-near-pass")
    payload["metrics"]["role_or_local_entity_accuracy"] = 0.99
    payload["metrics"]["gate_intervention_count"] = 1
    score_path = _write_score(root, "l1", payload)

    result = qualify_dev_repair(
        "l1",
        score_path,
        score_path.parent / "qualification.json",
        score_path.parent / "qualification.md",
    )

    assert payload["raw_proposer_quality_ready"] is True
    assert payload["deterministic_gate_safety_ready"] is True
    assert result["raw_proposer_quality_ready"] is False
    assert result["deterministic_gate_safety_ready"] is False
    assert result["dev_repair_ready"] is False
    assert result["exact_metric_checks"]["role_or_local_entity_accuracy"] is False
    assert result["zero_count_checks"]["gate_intervention_count"] is False


@pytest.mark.parametrize("failure", ("dataset", "run", "hash"))
def test_qualification_rejects_dataset_run_and_hash_mismatch(
    tmp_path: Path,
    failure: str,
) -> None:
    root = tmp_path / failure
    _copy_root(L2_ROOT, root, "l2")
    payload = _score_payload(root, "l2", "run-diagnostic-l2-binding")
    if failure == "dataset":
        payload["dataset_id"] = "wrong-dataset"
    if failure == "run":
        payload["run_id"] = "wrong-run-id"
    score_path = _write_score(root, "l2", payload)
    if failure == "run":
        score_path.parent.rename(score_path.parent.parent / "actual-run-directory")
        score_path = score_path.parent.parent / "actual-run-directory" / "score.json"
    if failure == "hash":
        public_path = root / "public-l2.json"
        public_path.chmod(0o644)
        public_path.write_bytes(public_path.read_bytes() + b" ")
        public_path.chmod(0o444)

    with pytest.raises(ValueError, match=failure):
        qualify_dev_repair(
            "l2",
            score_path,
            score_path.parent / "qualification.json",
            score_path.parent / "qualification.md",
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("writes", "write"),
        ("guard", "guard"),
        ("longmem", "LongMemEval"),
        ("unknown_metric", "unknown metric"),
    ),
)
def test_qualification_rejects_unsafe_or_unknown_score_fields(
    tmp_path: Path,
    mutation: str,
    message: str,
) -> None:
    root = tmp_path / mutation
    _copy_root(L2_ROOT, root, "l2")
    payload = _score_payload(root, "l2", f"run-diagnostic-l2-{mutation}")
    if mutation == "writes":
        payload["claim_boundary"]["automatic_write_counts"]["l2"] = 1
    elif mutation == "guard":
        payload["guard_state"]["after_fingerprint"] = "b" * 64
    elif mutation == "longmem":
        payload["claim_boundary"]["longmemeval_status"] = "merged"
    else:
        payload["metrics"]["unexpected_accuracy"] = 1.0
    score_path = _write_score(root, "l2", payload)

    with pytest.raises(ValueError, match=message):
        qualify_dev_repair(
            "l2",
            score_path,
            score_path.parent / "qualification.json",
            score_path.parent / "qualification.md",
        )


def test_qualification_requires_read_only_score(tmp_path: Path) -> None:
    root = tmp_path / "mutable"
    _copy_root(L1_ROOT, root, "l1")
    payload = _score_payload(root, "l1", "run-diagnostic-l1-mutable")
    score_path = _write_score(root, "l1", payload)
    score_path.chmod(0o644)

    with pytest.raises(ValueError, match="read-only"):
        qualify_dev_repair(
            "l1",
            score_path,
            score_path.parent / "qualification.json",
            score_path.parent / "qualification.md",
        )
