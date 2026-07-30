from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .io import (
    canonical_json_bytes,
    sha256_file,
    write_json_immutable,
    write_text_immutable,
)
from .typed_extractor_fresh_v3_authoring import AUTOMATIC_WRITE_COUNTS
from .typed_extractor_fresh_v3_proposer_freeze import (
    EVALUATION_ID,
    FreshV3ProposalFailureReceipt,
    _discover_run_roots,
    _read_immutable,
    _roots as _proposer_roots,
    _validate_proposer_state,
    validate_fresh_v3_proposal_freeze,
)
from .typed_extractor_l1 import run_l1_scoring_file
from .typed_extractor_l2 import run_l2_scoring_file


V3_L1_OUTPUTS = (
    "authority-l1.json",
    "gold-l1.json",
    "public-l1.json",
    "source-cases-l1.json",
)
V3_L2_OUTPUTS = (
    "authority-l2.json",
    "gold-l2.json",
    "public-l2.json",
    "source-cases-l2.json",
)
V3_L2_THRESHOLDS: dict[str, float | int] = {
    "abstraction_accuracy": 1.0,
    "closure_accuracy": 1.0,
    "deterministic_critical_false_materialization_count": 0,
    "exact_evidence_rate": 1.0,
    "gate_intervention_count": 0,
    "kind_accuracy": 1.0,
    "proposal_coverage": 1.0,
    "raw_abstention_f1": 1.0,
    "raw_critical_false_emission_count": 0,
    "raw_decision_accuracy": 1.0,
    "schema_valid_rate": 1.0,
    "source_coverage_accuracy": 1.0,
    "structured_claim_accuracy": 1.0,
    "summary_accuracy": 1.0,
    "support_id_accuracy": 1.0,
}

L1_QUALITY_METRICS = (
    "proposal_coverage",
    "schema_valid_rate",
    "raw_decision_accuracy",
    "raw_abstention_f1",
    "exact_evidence_rate",
    "kind_accuracy",
    "predicate_or_operator_accuracy",
    "modality_or_polarity_accuracy",
    "role_or_local_entity_accuracy",
    "time_accuracy",
    "condition_or_scope_accuracy",
    "derivation_or_speaker_accuracy",
    "lifecycle_accuracy",
    "operation_provenance_accuracy",
)
L2_QUALITY_METRICS = (
    "proposal_coverage",
    "schema_valid_rate",
    "raw_decision_accuracy",
    "raw_abstention_f1",
    "exact_evidence_rate",
    "support_id_accuracy",
    "kind_accuracy",
    "structured_claim_accuracy",
    "abstraction_accuracy",
    "closure_accuracy",
    "source_coverage_accuracy",
    "summary_accuracy",
)
SAFETY_COUNTS = (
    "raw_critical_false_emission_count",
    "gate_intervention_count",
    "deterministic_critical_false_materialization_count",
)
POST_SCORE_FILES = {
    "dispatch.json",
    "raw-response.json",
    "proposals.json",
    "provenance.json",
    "proposal-freeze-receipt.json",
    "score.json",
    "error-analysis.json",
    "report.md",
    "qualification.json",
}
OVERALL_FILES = {
    "overall-score.json",
    "overall-report.md",
    "qualification-chronology.json",
}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class LayerQualification(StrictModel):
    schema_version: Literal["typed-extractor-fresh-v3-layer-qualification-v1"] = (
        "typed-extractor-fresh-v3-layer-qualification-v1"
    )
    status: Literal["qualified", "not_qualified"]
    evaluation_id: Literal["typed-extractor-v3-fresh-hidden-v1"] = EVALUATION_ID
    layer: Literal["l1", "l2"]
    dataset_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    case_count: int = Field(ge=1)
    proposal_freeze_receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    score_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    requested_model: Literal["deepseek-chat"] = "deepseek-chat"
    response_model: str = Field(min_length=1)
    request_count: Literal[1] = 1
    metrics: dict[str, float | int]
    quality_checks: dict[str, bool]
    safety_checks: dict[str, bool]
    scorer_raw_proposer_quality_ready: bool
    scorer_deterministic_gate_safety_ready: bool
    raw_proposer_quality_ready: bool
    deterministic_gate_safety_ready: bool
    layer_ready: bool
    automatic_write_counts: dict[str, int]
    manual_identity_adjudications_materialized: Literal[False] = False
    embedding_authority: Literal[False] = False
    pipeline_integration_authorized: Literal[False] = False
    longmemeval_status: Literal["structured_l2_identity_unresolved"] = (
        "structured_l2_identity_unresolved"
    )

    @model_validator(mode="after")
    def validate_exact_contract(self) -> "LayerQualification":
        expected = L1_QUALITY_METRICS if self.layer == "l1" else L2_QUALITY_METRICS
        if set(self.quality_checks) != set(expected):
            raise ValueError("layer quality metric registry mismatch")
        if set(self.safety_checks) != set(SAFETY_COUNTS):
            raise ValueError("layer safety count registry mismatch")
        if self.automatic_write_counts != AUTOMATIC_WRITE_COUNTS:
            raise ValueError("layer write boundary mismatch")
        if self.raw_proposer_quality_ready != (
            all(self.quality_checks.values())
            and self.safety_checks["raw_critical_false_emission_count"]
            and self.scorer_raw_proposer_quality_ready
        ):
            raise ValueError("raw proposer readiness mismatch")
        if self.deterministic_gate_safety_ready != (
            self.safety_checks["gate_intervention_count"]
            and self.safety_checks[
                "deterministic_critical_false_materialization_count"
            ]
            and self.scorer_deterministic_gate_safety_ready
        ):
            raise ValueError("deterministic gate readiness mismatch")
        if self.layer_ready != (
            self.raw_proposer_quality_ready
            and self.deterministic_gate_safety_ready
        ):
            raise ValueError("layer readiness mismatch")
        expected_status = "qualified" if self.layer_ready else "not_qualified"
        if self.status != expected_status:
            raise ValueError("layer qualification status mismatch")
        return self


class ScoringFailureQualification(StrictModel):
    schema_version: Literal[
        "typed-extractor-fresh-v3-scoring-failure-qualification-v1"
    ] = "typed-extractor-fresh-v3-scoring-failure-qualification-v1"
    status: Literal["not_qualified"] = "not_qualified"
    evaluation_id: Literal["typed-extractor-v3-fresh-hidden-v1"] = EVALUATION_ID
    layer: Literal["l1", "l2"]
    run_id: str = Field(min_length=1)
    proposal_freeze_receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_count: Literal[1] = 1
    failure_class: str = Field(pattern=r"^scorer_failure:[A-Za-z_][A-Za-z0-9_]*$")
    failure_message: str = Field(min_length=1)
    scoring_complete: Literal[False] = False
    automatic_write_counts: dict[str, int]
    pipeline_integration_authorized: Literal[False] = False
    authoritative_writes_authorized: Literal[False] = False
    longmemeval_status: Literal["structured_l2_identity_unresolved"] = (
        "structured_l2_identity_unresolved"
    )


class OverallQualification(StrictModel):
    schema_version: Literal["typed-extractor-fresh-v3-overall-qualification-v1"] = (
        "typed-extractor-fresh-v3-overall-qualification-v1"
    )
    status: Literal["qualified", "not_qualified", "incomplete_not_qualified"]
    evaluation_id: Literal["typed-extractor-v3-fresh-hidden-v1"] = EVALUATION_ID
    qualification_time: str
    layers: dict[str, Any]
    request_counts: dict[str, int]
    requested_model: Literal["deepseek-chat"] = "deepseek-chat"
    automatic_write_counts: dict[str, int]
    raw_and_gated_reported_separately: Literal[True] = True
    manual_identity_adjudications_materialized: Literal[False] = False
    embedding_authority: Literal[False] = False
    pipeline_integration_authorized: Literal[False] = False
    authoritative_writes_authorized: Literal[False] = False
    longmemeval_status: Literal["structured_l2_identity_unresolved"] = (
        "structured_l2_identity_unresolved"
    )

    @model_validator(mode="after")
    def validate_boundaries(self) -> "OverallQualification":
        if set(self.layers) != {"l1", "l2"}:
            raise ValueError("overall layer registry mismatch")
        if set(self.request_counts) != {"l1", "l2"}:
            raise ValueError("overall request count registry mismatch")
        if self.automatic_write_counts != AUTOMATIC_WRITE_COUNTS:
            raise ValueError("overall write boundary mismatch")
        return self


class QualificationChronology(StrictModel):
    schema_version: Literal["typed-extractor-fresh-v3-qualification-chronology-v1"] = (
        "typed-extractor-fresh-v3-qualification-chronology-v1"
    )
    status: Literal["frozen"] = "frozen"
    evaluation_id: Literal["typed-extractor-v3-fresh-hidden-v1"] = EVALUATION_ID
    qualification_time: str
    conclusion: Literal["qualified", "not_qualified", "incomplete_not_qualified"]
    proposer_receipt_sha256: dict[str, str]
    score_sha256: dict[str, str]
    qualification_sha256: dict[str, str]
    overall_score_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    implementation_sha256: dict[str, str]
    parallel_sha256: dict[str, str]
    head: str = Field(pattern=r"^[0-9a-f]{40}$")
    automatic_write_counts: dict[str, int]
    sequence: tuple[
        Literal["proposal_freezes_validated"],
        Literal["scores_frozen"],
        Literal["layer_qualifications_frozen"],
        Literal["overall_conclusion_frozen"],
    ] = (
        "proposal_freezes_validated",
        "scores_frozen",
        "layer_qualifications_frozen",
        "overall_conclusion_frozen",
    )


def _roots(repository_root: Path, workspace_root: Path) -> tuple[Path, Path, Path]:
    return _proposer_roots(repository_root, workspace_root)


def _validate_time(value: str) -> str:
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError) as error:
        raise ValueError("qualification_time must be a valid UTC timestamp") from error
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        raise ValueError("qualification_time must be a valid UTC timestamp")
    return value


def _qualification_bindings(
    repository_root: Path,
    workspace_root: Path,
) -> dict[str, Any]:
    state = _validate_proposer_state(repository_root, workspace_root)
    return {
        "head": state["head"],
        "implementation_sha256": state["implementation_sha256"],
        "parallel_sha256": state["parallel_sha256"],
        "automatic_write_counts": state["automatic_write_counts"],
    }


def _number_equals(value: Any, expected: float | int) -> bool:
    return not isinstance(value, bool) and isinstance(value, (float, int)) and value == expected


def _build_layer_qualification(
    layer: Literal["l1", "l2"],
    score: dict[str, Any],
    proposal_receipt: dict[str, Any],
    score_path: Path,
) -> LayerQualification:
    quality_names = L1_QUALITY_METRICS if layer == "l1" else L2_QUALITY_METRICS
    metrics = score.get("metrics")
    if not isinstance(metrics, dict):
        raise ValueError(f"{layer} score metrics missing")
    quality_checks = {
        name: _number_equals(metrics.get(name), 1.0) for name in quality_names
    }
    safety_checks = {
        name: _number_equals(metrics.get(name), 0) for name in SAFETY_COUNTS
    }
    scorer_raw_ready = score.get("raw_proposer_quality_ready") is True
    scorer_gate_ready = score.get("deterministic_gate_safety_ready") is True
    raw_ready = (
        all(quality_checks.values())
        and safety_checks["raw_critical_false_emission_count"]
        and scorer_raw_ready
    )
    gate_ready = (
        safety_checks["gate_intervention_count"]
        and safety_checks["deterministic_critical_false_materialization_count"]
        and scorer_gate_ready
    )
    layer_ready = raw_ready and gate_ready
    return LayerQualification(
        status="qualified" if layer_ready else "not_qualified",
        layer=layer,
        dataset_id=score["dataset_id"],
        run_id=score["run_id"],
        case_count=score["case_count"],
        proposal_freeze_receipt_sha256=proposal_receipt["receipt_sha256"],
        score_sha256=sha256_file(score_path),
        requested_model=proposal_receipt["requested_model"],
        response_model=proposal_receipt["response_model"],
        request_count=proposal_receipt["request_count"],
        metrics=metrics,
        quality_checks=quality_checks,
        safety_checks=safety_checks,
        scorer_raw_proposer_quality_ready=scorer_raw_ready,
        scorer_deterministic_gate_safety_ready=scorer_gate_ready,
        raw_proposer_quality_ready=raw_ready,
        deterministic_gate_safety_ready=gate_ready,
        layer_ready=layer_ready,
        automatic_write_counts=dict(AUTOMATIC_WRITE_COUNTS),
    )


def _write_layer_qualification(
    run_root: Path,
    layer_qualification: LayerQualification,
) -> None:
    path = run_root / "qualification.json"
    write_json_immutable(path, layer_qualification)
    path.chmod(0o444)


def _overall_report(overall: OverallQualification) -> str:
    lines = [
        "# Typed Extractor Fresh-V3 Qualification",
        "",
        f"- Conclusion: `{overall.status}`",
        f"- Qualification time: `{overall.qualification_time}`",
        "",
        "## Layer Results",
        "",
    ]
    for layer in ("l1", "l2"):
        payload = overall.layers[layer]
        lines.extend(
            [
                f"- {layer.upper()} status: `{payload['status']}`",
                f"- {layer.upper()} raw proposer quality ready: `{str(payload.get('raw_proposer_quality_ready', False)).lower()}`",
                f"- {layer.upper()} deterministic gate safety ready: `{str(payload.get('deterministic_gate_safety_ready', False)).lower()}`",
            ]
        )
    lines.extend(
        [
            "",
            "Raw proposer quality and deterministic gate safety are reported separately.",
            "No pipeline integration or authoritative memory write is authorized.",
            "",
        ]
    )
    return "\n".join(lines)


def _freeze_overall(
    evaluation_root: Path,
    overall: OverallQualification,
    bindings: dict[str, Any],
    *,
    proposer_receipt_sha256: dict[str, str],
    score_sha256: dict[str, str],
    qualification_sha256: dict[str, str],
) -> None:
    overall_path = evaluation_root / "overall-score.json"
    report_path = evaluation_root / "overall-report.md"
    chronology_path = evaluation_root / "qualification-chronology.json"
    write_json_immutable(overall_path, overall)
    overall_path.chmod(0o444)
    write_text_immutable(report_path, _overall_report(overall))
    report_path.chmod(0o444)
    chronology = QualificationChronology(
        qualification_time=overall.qualification_time,
        conclusion=overall.status,
        proposer_receipt_sha256=proposer_receipt_sha256,
        score_sha256=score_sha256,
        qualification_sha256=qualification_sha256,
        overall_score_sha256=sha256_file(overall_path),
        implementation_sha256=bindings["implementation_sha256"],
        parallel_sha256=bindings["parallel_sha256"],
        head=bindings["head"],
        automatic_write_counts=dict(AUTOMATIC_WRITE_COUNTS),
    )
    write_json_immutable(chronology_path, chronology)
    chronology_path.chmod(0o444)


def _freeze_scoring_failure(
    evaluation_root: Path,
    qualification_time: str,
    proposal_receipts: dict[str, dict[str, Any]],
    bindings: dict[str, Any],
    failed_layer: Literal["l1", "l2"],
    error: Exception,
) -> dict[str, Any]:
    failed_run = Path(proposal_receipts[failed_layer]["run_root"])
    failure = ScoringFailureQualification(
        layer=failed_layer,
        run_id=failed_run.name,
        proposal_freeze_receipt_sha256=proposal_receipts[failed_layer][
            "receipt_sha256"
        ],
        request_count=proposal_receipts[failed_layer]["request_count"],
        failure_class=f"scorer_failure:{type(error).__name__}",
        failure_message=str(error) or type(error).__name__,
        automatic_write_counts=dict(AUTOMATIC_WRITE_COUNTS),
    )
    qualification_path = failed_run / "qualification.json"
    write_json_immutable(qualification_path, failure)
    qualification_path.chmod(0o444)
    layers: dict[str, Any] = {}
    for layer in ("l1", "l2"):
        if layer == failed_layer:
            layers[layer] = failure.model_dump(mode="json")
        else:
            layers[layer] = {
                "status": "not_scored",
                "run_id": proposal_receipts[layer]["run_id"],
                "proposal_freeze_receipt_sha256": proposal_receipts[layer][
                    "receipt_sha256"
                ],
                "request_count": proposal_receipts[layer]["request_count"],
            }
    overall = OverallQualification(
        status="not_qualified",
        qualification_time=qualification_time,
        layers=layers,
        request_counts={
            layer: proposal_receipts[layer]["request_count"]
            for layer in ("l1", "l2")
        },
        automatic_write_counts=dict(AUTOMATIC_WRITE_COUNTS),
    )
    score_sha256 = {
        layer: sha256_file(Path(proposal_receipts[layer]["run_root"]) / "score.json")
        for layer in ("l1", "l2")
        if (Path(proposal_receipts[layer]["run_root"]) / "score.json").is_file()
    }
    _freeze_overall(
        evaluation_root,
        overall,
        bindings,
        proposer_receipt_sha256={
            layer: proposal_receipts[layer]["receipt_sha256"]
            for layer in ("l1", "l2")
        },
        score_sha256=score_sha256,
        qualification_sha256={failed_layer: sha256_file(qualification_path)},
    )
    return overall.model_dump(mode="json")


def score_and_qualify_fresh_v3(
    repository_root: Path,
    workspace_root: Path,
    qualification_time: str,
) -> dict[str, Any]:
    qualification_time = _validate_time(qualification_time)
    repository_root, workspace_root, evaluation_root = _roots(
        repository_root,
        workspace_root,
    )
    for name in OVERALL_FILES:
        if (evaluation_root / name).exists():
            raise ValueError(f"qualification output already exists: {name}")

    proposal_receipts: dict[str, dict[str, Any]] = {}
    for layer in ("l1", "l2"):
        proposal_receipts[layer] = validate_fresh_v3_proposal_freeze(
            repository_root,
            workspace_root,
            layer,
        )
    bindings = _qualification_bindings(repository_root, workspace_root)

    guard_root = workspace_root / "artifacts/natural-benchmark-slices"
    guard_results = (
        guard_root
        / "slice-v1/symbolic-fallback-answerability-v2-fastembed-results.json"
    )
    scores: dict[str, dict[str, Any]] = {}
    layer_qualifications: dict[str, LayerQualification] = {}
    for layer in ("l1", "l2"):
        run_root = Path(proposal_receipts[layer]["run_root"])
        layer_root = evaluation_root / layer
        common = {
            "guard_root": guard_root,
            "guard_slice_id": "slice-v1",
            "guard_results_path": guard_results,
            "score_path": run_root / "score.json",
            "report_path": run_root / "report.md",
            "error_analysis_path": run_root / "error-analysis.json",
        }
        try:
            if layer == "l1":
                scores[layer] = run_l1_scoring_file(
                    layer_root,
                    run_root / "proposals.json",
                    run_root / "provenance.json",
                    manifest_output_names=V3_L1_OUTPUTS,
                    **common,
                )
            else:
                scores[layer] = run_l2_scoring_file(
                    layer_root,
                    run_root / "proposals.json",
                    run_root / "provenance.json",
                    manifest_output_names=V3_L2_OUTPUTS,
                    required_thresholds=V3_L2_THRESHOLDS,
                    **common,
                )
            layer_qualification = _build_layer_qualification(
                layer,
                scores[layer],
                proposal_receipts[layer],
                run_root / "score.json",
            )
            _write_layer_qualification(run_root, layer_qualification)
            layer_qualifications[layer] = layer_qualification
        except Exception as error:
            try:
                return _freeze_scoring_failure(
                    evaluation_root,
                    qualification_time,
                    proposal_receipts,
                    bindings,
                    layer,
                    error,
                )
            except Exception as freeze_error:
                error.add_note(
                    f"scoring failure conclusion could not be frozen: {freeze_error}"
                )
                raise error

    overall_status: Literal["qualified", "not_qualified"] = (
        "qualified"
        if all(item.layer_ready for item in layer_qualifications.values())
        else "not_qualified"
    )
    overall = OverallQualification(
        status=overall_status,
        qualification_time=qualification_time,
        layers={
            layer: item.model_dump(mode="json")
            for layer, item in layer_qualifications.items()
        },
        request_counts={
            layer: proposal_receipts[layer]["request_count"]
            for layer in ("l1", "l2")
        },
        automatic_write_counts=dict(AUTOMATIC_WRITE_COUNTS),
    )
    _freeze_overall(
        evaluation_root,
        overall,
        bindings,
        proposer_receipt_sha256={
            layer: proposal_receipts[layer]["receipt_sha256"]
            for layer in ("l1", "l2")
        },
        score_sha256={
            layer: sha256_file(Path(proposal_receipts[layer]["run_root"]) / "score.json")
            for layer in ("l1", "l2")
        },
        qualification_sha256={
            layer: sha256_file(
                Path(proposal_receipts[layer]["run_root"]) / "qualification.json"
            )
            for layer in ("l1", "l2")
        },
    )
    return overall.model_dump(mode="json")


def _load_failure(run_root: Path, layer: str) -> dict[str, Any]:
    path = run_root / "proposal-freeze-failure-receipt.json"
    content = _read_immutable(path, f"{layer} proposal failure receipt")
    receipt = FreshV3ProposalFailureReceipt.model_validate_json(content, strict=True)
    if content != canonical_json_bytes(receipt):
        raise ValueError(f"{layer} proposal failure receipt is not canonical JSON")
    return {
        "status": "failed",
        "failure_type": receipt.failure_type,
        "failure_message": receipt.failure_message,
        "request_count": receipt.request_count,
        "receipt_sha256": sha256_file(path),
        "implementation_sha256": receipt.implementation_sha256,
        "parallel_sha256": receipt.parallel_sha256,
    }


def freeze_incomplete_fresh_v3_qualification(
    repository_root: Path,
    workspace_root: Path,
    qualification_time: str,
) -> dict[str, Any]:
    qualification_time = _validate_time(qualification_time)
    repository_root, workspace_root, evaluation_root = _roots(
        repository_root,
        workspace_root,
    )
    bindings = _qualification_bindings(repository_root, workspace_root)
    runs = _discover_run_roots(evaluation_root)
    layers: dict[str, Any] = {}
    for layer in ("l1", "l2"):
        try:
            layers[layer] = validate_fresh_v3_proposal_freeze(
                repository_root,
                workspace_root,
                layer,
            )
        except (FileNotFoundError, ValueError):
            layers[layer] = _load_failure(runs[layer], layer)
    if all(item.get("status") == "valid" for item in layers.values()):
        raise ValueError("both proposal freezes are valid; incomplete conclusion forbidden")
    for layer, item in layers.items():
        if item.get("status") == "failed" and (
            item["implementation_sha256"] != bindings["implementation_sha256"]
            or item["parallel_sha256"] != bindings["parallel_sha256"]
        ):
            raise ValueError(f"{layer} failure receipt binding drift")
    overall = OverallQualification(
        status="incomplete_not_qualified",
        qualification_time=qualification_time,
        layers=layers,
        request_counts={layer: layers[layer]["request_count"] for layer in ("l1", "l2")},
        automatic_write_counts=dict(AUTOMATIC_WRITE_COUNTS),
    )
    _freeze_overall(
        evaluation_root,
        overall,
        bindings,
        proposer_receipt_sha256={
            layer: layers[layer]["receipt_sha256"] for layer in ("l1", "l2")
        },
        score_sha256={},
        qualification_sha256={},
    )
    return overall.model_dump(mode="json")


def validate_fresh_v3_qualification(
    repository_root: Path,
    workspace_root: Path,
) -> dict[str, Any]:
    _, _, evaluation_root = _roots(repository_root, workspace_root)
    overall_path = evaluation_root / "overall-score.json"
    overall_bytes = _read_immutable(overall_path, "fresh v3 overall score")
    overall = OverallQualification.model_validate_json(overall_bytes, strict=True)
    if overall_bytes != canonical_json_bytes(overall):
        raise ValueError("fresh v3 overall score is not canonical JSON")
    report_path = evaluation_root / "overall-report.md"
    _read_immutable(report_path, "fresh v3 overall report")
    chronology_path = evaluation_root / "qualification-chronology.json"
    chronology_bytes = _read_immutable(
        chronology_path,
        "fresh v3 qualification chronology",
    )
    chronology = QualificationChronology.model_validate_json(
        chronology_bytes,
        strict=True,
    )
    if chronology_bytes != canonical_json_bytes(chronology):
        raise ValueError("fresh v3 qualification chronology is not canonical JSON")
    if (
        chronology.conclusion != overall.status
        or chronology.qualification_time != overall.qualification_time
        or chronology.overall_score_sha256 != sha256_file(overall_path)
    ):
        raise ValueError("fresh v3 qualification chronology drift")
    if overall.status == "incomplete_not_qualified":
        if chronology.score_sha256 or chronology.qualification_sha256:
            raise ValueError("incomplete qualification must not bind scores")
        runs = _discover_run_roots(evaluation_root)
        for layer in ("l1", "l2"):
            item = overall.layers[layer]
            if item.get("status") == "failed":
                receipt_path = runs[layer] / "proposal-freeze-failure-receipt.json"
                receipt = FreshV3ProposalFailureReceipt.model_validate_json(
                    _read_immutable(receipt_path, f"{layer} proposal failure receipt"),
                    strict=True,
                )
                matches_payload = (
                    item.get("failure_type") == receipt.failure_type
                    and item.get("failure_message") == receipt.failure_message
                )
            elif item.get("status") == "valid":
                receipt_path = runs[layer] / "proposal-freeze-receipt.json"
                matches_payload = True
            else:
                raise ValueError("incomplete qualification layer status drift")
            receipt_sha256 = sha256_file(receipt_path)
            if (
                not matches_payload
                or item.get("receipt_sha256") != receipt_sha256
                or chronology.proposer_receipt_sha256.get(layer) != receipt_sha256
                or overall.request_counts[layer] != item.get("request_count")
            ):
                raise ValueError(f"{layer} incomplete proposal binding drift")
    elif any("failure_class" in overall.layers[layer] for layer in ("l1", "l2")):
        failed_layers = [
            layer
            for layer in ("l1", "l2")
            if "failure_class" in overall.layers[layer]
        ]
        if overall.status != "not_qualified" or len(failed_layers) != 1:
            raise ValueError("scoring failure conclusion drift")
        failed_layer = failed_layers[0]
        runs = _discover_run_roots(evaluation_root)
        failure_path = runs[failed_layer] / "qualification.json"
        failure_bytes = _read_immutable(
            failure_path,
            f"{failed_layer} scoring failure qualification",
        )
        failure = ScoringFailureQualification.model_validate_json(
            failure_bytes,
            strict=True,
        )
        if (
            failure_bytes != canonical_json_bytes(failure)
            or failure.model_dump(mode="json") != overall.layers[failed_layer]
            or failure.proposal_freeze_receipt_sha256
            != sha256_file(runs[failed_layer] / "proposal-freeze-receipt.json")
            or chronology.qualification_sha256
            != {failed_layer: sha256_file(failure_path)}
        ):
            raise ValueError("scoring failure qualification binding drift")
        actual_score_sha256 = {
            layer: sha256_file(runs[layer] / "score.json")
            for layer in ("l1", "l2")
            if (runs[layer] / "score.json").is_file()
        }
        if chronology.score_sha256 != actual_score_sha256:
            raise ValueError("scoring failure partial score binding drift")
        for layer in ("l1", "l2"):
            receipt_sha256 = sha256_file(
                runs[layer] / "proposal-freeze-receipt.json"
            )
            if (
                chronology.proposer_receipt_sha256.get(layer) != receipt_sha256
                or overall.request_counts[layer] != 1
            ):
                raise ValueError("scoring failure proposer binding drift")
        other_layer = "l2" if failed_layer == "l1" else "l1"
        if overall.layers[other_layer].get("status") != "not_scored":
            raise ValueError("post-failure scorer stop boundary drift")
    else:
        runs = _discover_run_roots(evaluation_root)
        qualifications: dict[str, LayerQualification] = {}
        for layer in ("l1", "l2"):
            run_root = runs[layer]
            if {path.name for path in run_root.iterdir()} != POST_SCORE_FILES:
                raise ValueError(f"{layer} post-score artifact set mismatch")
            content = _read_immutable(
                run_root / "qualification.json",
                f"{layer} qualification",
            )
            item = LayerQualification.model_validate_json(content, strict=True)
            if content != canonical_json_bytes(item):
                raise ValueError(f"{layer} qualification is not canonical JSON")
            if (
                item.score_sha256 != sha256_file(run_root / "score.json")
                or item.proposal_freeze_receipt_sha256
                != sha256_file(run_root / "proposal-freeze-receipt.json")
                or item.model_dump(mode="json") != overall.layers[layer]
                or chronology.score_sha256.get(layer) != item.score_sha256
                or chronology.qualification_sha256.get(layer)
                != sha256_file(run_root / "qualification.json")
            ):
                raise ValueError(f"{layer} qualification binding drift")
            qualifications[layer] = item
        expected = (
            "qualified"
            if all(item.layer_ready for item in qualifications.values())
            else "not_qualified"
        )
        if overall.status != expected:
            raise ValueError("overall qualification conclusion drift")
    return {
        "status": overall.status,
        "qualification_time": overall.qualification_time,
        "overall_score_sha256": sha256_file(overall_path),
        "chronology_sha256": sha256_file(chronology_path),
        "layers": overall.layers,
    }
