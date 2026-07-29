from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from .io import load_json, sha256_file, write_json_immutable, write_text_immutable
from .typed_extractor_l1 import (
    L1Manifest,
    L1PublicPayload,
    L1ScorePayload,
    StrictModel,
)
from .typed_extractor_l2 import L2Manifest, L2PublicPayload, L2ScorePayload


L1_EXACT = frozenset(
    {
        "proposal_coverage",
        "schema_valid_rate",
        "raw_decision_accuracy",
        "raw_abstention_f1",
        "exact_evidence_rate",
        "kind_accuracy",
        "predicate_or_operator_accuracy",
        "role_or_local_entity_accuracy",
        "modality_or_polarity_accuracy",
        "time_accuracy",
        "condition_or_scope_accuracy",
        "derivation_or_speaker_accuracy",
        "lifecycle_accuracy",
        "operation_provenance_accuracy",
    }
)

L2_EXACT = frozenset(
    {
        "proposal_coverage",
        "schema_valid_rate",
        "raw_decision_accuracy",
        "raw_abstention_f1",
        "exact_evidence_rate",
        "support_id_accuracy",
        "source_coverage_accuracy",
        "kind_accuracy",
        "structured_claim_accuracy",
        "abstraction_accuracy",
        "closure_accuracy",
        "summary_accuracy",
    }
)

_COMMON_METRICS = frozenset(
    {
        "raw_abstention_precision",
        "raw_abstention_recall",
        "gated_decision_accuracy",
        "raw_critical_false_emission_count",
        "gate_intervention_count",
        "deterministic_critical_false_materialization_count",
    }
)

_ZERO_COUNT_METRICS = (
    "raw_critical_false_emission_count",
    "gate_intervention_count",
    "deterministic_critical_false_materialization_count",
)


class DevRepairQualification(StrictModel):
    schema_version: Literal["typed-extractor-dev-repair-qualification-v1"] = (
        "typed-extractor-dev-repair-qualification-v1"
    )
    status: Literal["qualified"] = "qualified"
    layer: Literal["l1", "l2"]
    dataset_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    score_filename: str
    score_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    manifest_filename: str
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    scorer_raw_proposer_quality_ready: bool
    scorer_deterministic_gate_safety_ready: bool
    exact_metric_checks: dict[str, bool]
    zero_count_checks: dict[str, bool]
    guard_unchanged: bool
    zero_writes: bool
    raw_proposer_quality_ready: bool
    deterministic_gate_safety_ready: bool
    dev_repair_ready: bool
    diagnostic_only: Literal[True] = True
    natural_benchmark_evidence: Literal[False] = False
    fresh_hidden_v2_authorized: Literal[False] = False
    pipeline_integration_authorized: Literal[False] = False
    authoritative_writes_authorized: Literal[False] = False
    longmemeval_status: Literal["structured_l2_identity_unresolved"] = (
        "structured_l2_identity_unresolved"
    )


def _require_read_only(path: Path, label: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"{label} missing: {path}")
    if path.stat().st_mode & 0o222:
        raise ValueError(f"{label} must be read-only")


def _score_root(score_path: Path) -> Path:
    if score_path.name != "score.json" or score_path.parent.parent.name != "model-runs":
        raise ValueError("score path must be under model-runs/<run_id>/score.json")
    return score_path.parents[2]


def _validate_manifest_and_hashes(
    layer: Literal["l1", "l2"],
    root: Path,
    dataset_id: str,
    case_count: int,
) -> tuple[Path, L1Manifest | L2Manifest, L1PublicPayload | L2PublicPayload]:
    manifest_path = root / f"manifest-{layer}.json"
    public_path = root / f"public-{layer}.json"
    authority_path = root / f"authority-{layer}.json"
    gold_path = root / f"gold-{layer}.json"
    for path, label in (
        (manifest_path, "matching manifest"),
        (public_path, "matching public input"),
        (authority_path, "matching authority input"),
        (gold_path, "matching gold input"),
    ):
        _require_read_only(path, label)

    if layer == "l1":
        manifest: L1Manifest | L2Manifest = L1Manifest.model_validate(
            load_json(manifest_path)
        )
        public: L1PublicPayload | L2PublicPayload = L1PublicPayload.model_validate(
            load_json(public_path)
        )
    else:
        manifest = L2Manifest.model_validate(load_json(manifest_path))
        public = L2PublicPayload.model_validate(load_json(public_path))
    if manifest.dataset_id != dataset_id or public.dataset_id != dataset_id:
        raise ValueError("dataset mismatch between score and diagnostic manifest")
    if manifest.case_count != case_count or public.case_count != case_count:
        raise ValueError("dataset case count mismatch")
    actual_hashes = {
        f"authority-{layer}.json": sha256_file(authority_path),
        f"gold-{layer}.json": sha256_file(gold_path),
        f"public-{layer}.json": sha256_file(public_path),
    }
    if manifest.output_sha256 != actual_hashes:
        raise ValueError("hash mismatch in diagnostic manifest outputs")
    boundary = manifest.claim_boundary
    if boundary.get("diagnostic_only") is not True:
        raise ValueError("matching manifest is not diagnostic-only")
    if boundary.get("automatic_authoritative_writes") is not False:
        raise ValueError("matching manifest authorizes a write")
    if boundary.get("fresh_hidden_v2_created") is not False:
        raise ValueError("matching manifest claims fresh-v2 exists")
    if boundary.get("longmemeval_status") != "structured_l2_identity_unresolved":
        raise ValueError("LongMemEval status drift in matching manifest")
    return manifest_path, manifest, public


def _validate_metrics(
    layer: Literal["l1", "l2"],
    metrics: dict[str, Any],
) -> tuple[dict[str, bool], dict[str, bool]]:
    exact_names = L1_EXACT if layer == "l1" else L2_EXACT
    expected_names = exact_names | _COMMON_METRICS
    actual_names = set(metrics)
    unknown = actual_names - expected_names
    missing = expected_names - actual_names
    if unknown:
        raise ValueError(f"unknown metric keys: {sorted(unknown)}")
    if missing:
        raise ValueError(f"missing metric keys: {sorted(missing)}")
    exact_checks = {
        name: isinstance(metrics[name], (int, float))
        and not isinstance(metrics[name], bool)
        and metrics[name] == 1.0
        for name in sorted(exact_names)
    }
    zero_checks = {
        name: isinstance(metrics[name], (int, float))
        and not isinstance(metrics[name], bool)
        and metrics[name] == 0
        for name in _ZERO_COUNT_METRICS
    }
    return exact_checks, zero_checks


def _validate_guard(guard_state: dict[str, Any]) -> bool:
    required = {
        "before_fingerprint",
        "after_fingerprint",
        "before_counts",
        "after_counts",
    }
    if not required.issubset(guard_state):
        raise ValueError("guard state is incomplete")
    unchanged = (
        guard_state["before_fingerprint"] == guard_state["after_fingerprint"]
        and guard_state["before_counts"] == guard_state["after_counts"]
        and guard_state.get("unchanged", True) is True
    )
    if not unchanged:
        raise ValueError("guard state changed during scoring")
    return True


def _validate_claim_boundary(
    layer: Literal["l1", "l2"],
    boundary: dict[str, Any],
) -> bool:
    if boundary.get("longmemeval_status") != "structured_l2_identity_unresolved":
        raise ValueError("LongMemEval status drift in score")
    if boundary.get("embedding_authority") is not False:
        raise ValueError("embedding authority boundary drift")
    if boundary.get("fresh_hidden_created") is not False:
        raise ValueError("score claims a fresh hidden artifact")
    if boundary.get("pipeline_integration_authorized", False) is not False:
        raise ValueError("score authorizes pipeline integration")
    if layer == "l1":
        names = {
            "automatic_closure_write_count",
            "automatic_identity_write_count",
            "automatic_l1_write_count",
            "automatic_l2_write_count",
            "automatic_membership_write_count",
            "automatic_unit_revision_write_count",
        }
        if any(boundary.get(name) != 0 for name in names):
            raise ValueError("non-zero automatic write count")
    else:
        counts = boundary.get("automatic_write_counts")
        expected = {"closure", "identity", "l1", "l2", "membership", "unit_revision"}
        if not isinstance(counts, dict) or set(counts) != expected:
            raise ValueError("automatic write count set mismatch")
        if any(counts[name] != 0 for name in expected):
            raise ValueError("non-zero automatic write count")
    return True


def _report(value: DevRepairQualification) -> str:
    metric_lines = "\n".join(
        f"- `{name}`: {'pass' if passed else 'fail'}"
        for name, passed in value.exact_metric_checks.items()
    )
    count_lines = "\n".join(
        f"- `{name}`: {'pass' if passed else 'fail'}"
        for name, passed in value.zero_count_checks.items()
    )
    return (
        "# Typed Extractor Dev-Repair Qualification\n\n"
        f"- Layer: `{value.layer}`\n"
        f"- Dataset: `{value.dataset_id}`\n"
        f"- Run: `{value.run_id}`\n"
        f"- Raw proposer quality: `{'pass' if value.raw_proposer_quality_ready else 'fail'}`\n"
        f"- Deterministic gate safety: `{'pass' if value.deterministic_gate_safety_ready else 'fail'}`\n"
        f"- Dev repair ready: `{'pass' if value.dev_repair_ready else 'fail'}`\n\n"
        "This result is diagnostic-only and is not natural benchmark evidence. "
        "Even on pass, fresh-v2 remains unauthorized until both layers pass and "
        "a separate preregistration is frozen.\n\n"
        "## Exact metrics\n\n"
        f"{metric_lines}\n\n"
        "## Zero-count safety checks\n\n"
        f"{count_lines}\n\n"
        "Raw proposer quality and deterministic gate safety are reported "
        "separately. No pipeline integration or authoritative write is authorized.\n"
    )


def qualify_dev_repair(
    layer: Literal["l1", "l2"],
    score_path: Path,
    output_path: Path,
    report_path: Path,
) -> dict[str, Any]:
    score_path = score_path.resolve()
    _require_read_only(score_path, "score input")
    root = _score_root(score_path)
    raw_score = load_json(score_path)
    if layer == "l1":
        score: L1ScorePayload | L2ScorePayload = L1ScorePayload.model_validate(raw_score)
    else:
        score = L2ScorePayload.model_validate(raw_score)
    if score_path.parent.name != score.run_id:
        raise ValueError("run mismatch between score and model-run directory")
    if score.case_count != len(score.cases):
        raise ValueError("score case count mismatch")

    manifest_path, _, public = _validate_manifest_and_hashes(
        layer,
        root,
        score.dataset_id,
        score.case_count,
    )
    public_case_ids = {case.case_id for case in public.cases}
    score_case_ids = {case.case_id for case in score.cases}
    if public_case_ids != score_case_ids:
        raise ValueError("score case coverage mismatch")

    exact_checks, zero_checks = _validate_metrics(layer, score.metrics)
    guard_unchanged = _validate_guard(score.guard_state)
    zero_writes = _validate_claim_boundary(layer, score.claim_boundary)
    raw_ready = (
        score.raw_proposer_quality_ready
        and all(exact_checks.values())
        and zero_checks["raw_critical_false_emission_count"]
    )
    gate_ready = (
        score.deterministic_gate_safety_ready
        and zero_checks["gate_intervention_count"]
        and zero_checks["deterministic_critical_false_materialization_count"]
        and guard_unchanged
        and zero_writes
    )
    result = DevRepairQualification(
        layer=layer,
        dataset_id=score.dataset_id,
        run_id=score.run_id,
        score_filename=score_path.name,
        score_sha256=sha256_file(score_path),
        manifest_filename=manifest_path.name,
        manifest_sha256=sha256_file(manifest_path),
        scorer_raw_proposer_quality_ready=score.raw_proposer_quality_ready,
        scorer_deterministic_gate_safety_ready=(
            score.deterministic_gate_safety_ready
        ),
        exact_metric_checks=exact_checks,
        zero_count_checks=zero_checks,
        guard_unchanged=guard_unchanged,
        zero_writes=zero_writes,
        raw_proposer_quality_ready=raw_ready,
        deterministic_gate_safety_ready=gate_ready,
        dev_repair_ready=raw_ready and gate_ready,
    )
    write_json_immutable(output_path.resolve(), result)
    write_text_immutable(report_path.resolve(), _report(result))
    output_path.resolve().chmod(0o444)
    report_path.resolve().chmod(0o444)
    return result.model_dump(mode="json")
