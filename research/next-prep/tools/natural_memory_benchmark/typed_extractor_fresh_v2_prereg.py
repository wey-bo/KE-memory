from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .frozen_input_guard import require_frozen_input
from .io import load_json, sha256_file, write_json_immutable


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


L1_FAMILIES = {
    "explicit_event_roles": 4,
    "condition_scope": 4,
    "modality_time": 4,
    "lifecycle_revision": 4,
    "derivation_epistemic": 4,
    "abstention_no_memory_controls": 4,
}

L2_FAMILIES = {
    "coreference_task_composition": 2,
    "preference_state_aggregation": 2,
    "lifecycle_supersession": 2,
    "multi_evidence_closure": 2,
    "abstraction_structured_claim_boundary": 2,
    "abstention_unresolved_controls": 2,
}

L1_QUALITY_THRESHOLDS = {
    "proposal_coverage": 1.0,
    "schema_valid_rate": 1.0,
    "raw_decision_accuracy": 1.0,
    "raw_abstention_f1": 1.0,
    "exact_evidence_rate": 1.0,
    "kind_accuracy": 1.0,
    "predicate_or_operator_accuracy": 1.0,
    "role_or_local_entity_accuracy": 1.0,
    "modality_or_polarity_accuracy": 1.0,
    "time_accuracy": 1.0,
    "condition_or_scope_accuracy": 1.0,
    "lifecycle_accuracy": 1.0,
    "derivation_or_speaker_accuracy": 1.0,
    "operation_provenance_accuracy": 1.0,
}

L2_QUALITY_THRESHOLDS = {
    "proposal_coverage": 1.0,
    "schema_valid_rate": 1.0,
    "raw_decision_accuracy": 1.0,
    "raw_abstention_f1": 1.0,
    "exact_evidence_rate": 1.0,
    "support_id_accuracy": 1.0,
    "kind_accuracy": 1.0,
    "structured_claim_accuracy": 1.0,
    "abstraction_accuracy": 1.0,
    "closure_accuracy": 1.0,
    "source_coverage_accuracy": 1.0,
    "summary_accuracy": 1.0,
}

SAFETY_THRESHOLDS = {
    "raw_critical_false_emission_count": 0,
    "gate_intervention_count": 0,
    "deterministic_critical_false_materialization_count": 0,
}

L1_RUN_ID = (
    "run-20260728T130544Z-deepseek-chat-official-typed-l1-dev-repair-v10"
)
L2_RUN_ID = (
    "run-20260728T123925Z-deepseek-chat-official-typed-l2-dev-repair-v9"
)

EXPECTED_PASSING_CHAINS: dict[str, dict[str, Any]] = {
    "l1": {
        "layer": "l1",
        "prompt_path": (
            "artifacts/automatic-extraction-assessment/"
            "typed-extractor-v2-l1-dev-repair-v2/proposer-prompt-l1-v10.md"
        ),
        "prompt_sha256": (
            "b868bb2baaf1dfb3c27f99e2fe29888e2af0c57e56be3d2ecf70bfb6d2bcdfcf"
        ),
        "run_id": L1_RUN_ID,
        "requested_model": "deepseek-chat",
        "response_model": "deepseek-v4-flash",
        "artifact_sha256": {
            "proposals.json": (
                "7cca8c171d784fbee1ea4849c52403fa6446f3d78fe746cec4134a3effb95c39"
            ),
            "provenance.json": (
                "8a2ef39bf2da9a059a24537505b05f5391a1806f5012642fa173864746dbf483"
            ),
            "score.json": (
                "993200f235b075b4f7e5e72bf37d19cc8427d360ce75ab5375f91f3e7923ba43"
            ),
            "qualification.json": (
                "377d91553db76fa1e3d48602e739aed255b107fca3856a35908234c769cb93a0"
            ),
        },
    },
    "l2": {
        "layer": "l2",
        "prompt_path": (
            "artifacts/automatic-extraction-assessment/"
            "typed-extractor-v2-l2-dev-repair-v3/proposer-prompt-l2.md"
        ),
        "prompt_sha256": (
            "d547a7d8b61eea33735bce4b3c96bb34466bb0fa6eb95d4e1b9070d64f211c6a"
        ),
        "run_id": L2_RUN_ID,
        "requested_model": "deepseek-chat",
        "response_model": "deepseek-v4-flash",
        "artifact_sha256": {
            "proposals.json": (
                "d27e614b8bef0dfbc2dedf53eb7a320b5c1f1fcdc87021bd951bc5d02082d77a"
            ),
            "provenance.json": (
                "2f6d87a6a71c3dd471606cdcf76d2e59b31879a6ba47a0171c1acbab4b069049"
            ),
            "score.json": (
                "ea1c87d15f775b6d1e93dc1b80ce63125dfdd33e2b73713d4312c6b41cfa8e7c"
            ),
            "qualification.json": (
                "4abdc7c1f256178c13d5b47cc0455c5ce183ee3ab40c0fbc9f723967d9885a46"
            ),
        },
    },
}

FUTURE_WORKSPACE_PATHS = (
    "tools/natural_memory_benchmark/typed_extractor_fresh_v2_authoring.py",
    "tests/natural_memory_benchmark/test_typed_extractor_fresh_v2_authoring.py",
)

AUTHORING_RECEIPT_NAME = "authoring-implementation-receipt.json"

EXPECTED_HIDDEN_PATHS = (
    "l1/source-cases-l1.json",
    "l1/public-l1.json",
    "l1/authority-l1.json",
    "l1/gold-l1.json",
    "l1/manifest-l1.json",
    "l2/source-cases-l2.json",
    "l2/public-l2.json",
    "l2/authority-l2.json",
    "l2/gold-l2.json",
    "l2/manifest-l2.json",
    "chronology-receipt.json",
)

EXPECTED_FUTURE_PATHS = (
    *(f"workspace:{path}" for path in FUTURE_WORKSPACE_PATHS),
    f"preregistration:{AUTHORING_RECEIPT_NAME}",
    *(f"evaluation:{path}" for path in EXPECTED_HIDDEN_PATHS),
)


class FrozenPassingChain(StrictModel):
    layer: Literal["l1", "l2"]
    prompt_path: str = Field(min_length=1)
    prompt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    run_id: str = Field(min_length=1)
    requested_model: Literal["deepseek-chat"] = "deepseek-chat"
    response_model: Literal["deepseek-v4-flash"] = "deepseek-v4-flash"
    artifact_sha256: dict[str, str]

    @model_validator(mode="after")
    def validate_artifacts(self) -> "FrozenPassingChain":
        expected_names = {
            "proposals.json",
            "provenance.json",
            "score.json",
            "qualification.json",
        }
        if set(self.artifact_sha256) != expected_names:
            raise ValueError("passing chain artifact set mismatch")
        if any(
            len(value) != 64
            or any(char not in "0123456789abcdef" for char in value)
            for value in self.artifact_sha256.values()
        ):
            raise ValueError("invalid passing chain hash")
        return self


class AuthorshipPolicy(StrictModel):
    namespace: Literal[
        "typed-extractor-fresh-hidden-v2-authored:2026-07-28"
    ] = "typed-extractor-fresh-hidden-v2-authored:2026-07-28"
    policy: Literal[
        "deterministic_blueprints_use_all_no_replacement_v1"
    ] = "deterministic_blueprints_use_all_no_replacement_v1"
    l1_case_count: Literal[24] = 24
    l2_case_count: Literal[12] = 12
    l1_families: dict[str, int]
    l2_families: dict[str, int]
    semantic_filtering_allowed: Literal[False] = False
    case_replacement_allowed: Literal[False] = False
    post_generation_resampling_allowed: Literal[False] = False
    use_every_authored_blueprint: Literal[True] = True
    normalized_contamination_check_required: Literal[True] = True

    @model_validator(mode="after")
    def validate_composition(self) -> "AuthorshipPolicy":
        if self.l1_families != L1_FAMILIES:
            raise ValueError("fresh v2 L1 family contract mismatch")
        if self.l2_families != L2_FAMILIES:
            raise ValueError("fresh v2 L2 family contract mismatch")
        if sum(self.l1_families.values()) != self.l1_case_count:
            raise ValueError("fresh v2 L1 case count mismatch")
        if sum(self.l2_families.values()) != self.l2_case_count:
            raise ValueError("fresh v2 L2 case count mismatch")
        return self


class ModelPolicy(StrictModel):
    requested_model: Literal["deepseek-chat"] = "deepseek-chat"
    response_model_recorded_separately: Literal[True] = True
    history_context_inherited: Literal[False] = False
    public_payload_only: Literal[True] = True
    authority_or_gold_allowed_before_proposal_freeze: Literal[False] = False
    proposals_and_provenance_frozen_before_scoring: Literal[True] = True
    semantic_runs_per_layer: Literal[1] = 1
    semantic_retry_allowed: Literal[False] = False
    transport_retry_requires_new_immutable_run: Literal[True] = True
    raw_and_gated_reported_separately: Literal[True] = True
    isolation_enforcement: Literal[
        "declarative-agent-file-access-contract"
    ] = "declarative-agent-file-access-contract"


class Chronology(StrictModel):
    freeze_time: str = Field(pattern=r"^2026-07-28T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
    preregistration_root: str = Field(min_length=1)
    evaluation_root: str = Field(min_length=1)
    evidence_kind: Literal[
        "filesystem-presence-plus-sha256"
    ] = "filesystem-presence-plus-sha256"
    freeze_time_source: Literal[
        "caller_supplied_untrusted_utc_label"
    ] = "caller_supplied_untrusted_utc_label"
    trusted_timestamp_authority: Literal[False] = False
    future_artifacts_absent_at_freeze: Literal[True] = True
    authoring_receipt_required_before_hidden: Literal[True] = True
    preregistration_validator_phase: Literal[
        "pre_authoring_only"
    ] = "pre_authoring_only"

    @field_validator("freeze_time")
    @classmethod
    def validate_freeze_time(cls, value: str) -> str:
        try:
            parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError as exc:
            raise ValueError("freeze_time must be a valid UTC timestamp") from exc
        if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
            raise ValueError("freeze_time must be a valid UTC timestamp")
        return value


class ClaimBoundary(StrictModel):
    hidden_artifact_write_count: Literal[0] = 0
    model_request_count: Literal[0] = 0
    automatic_l1_write_count: Literal[0] = 0
    automatic_l2_write_count: Literal[0] = 0
    automatic_identity_write_count: Literal[0] = 0
    automatic_membership_write_count: Literal[0] = 0
    automatic_closure_write_count: Literal[0] = 0
    automatic_revision_write_count: Literal[0] = 0
    automatic_source_revision_write_count: Literal[0] = 0
    automatic_snapshot_write_count: Literal[0] = 0
    automatic_aggregate_write_count: Literal[0] = 0
    embedding_authority: Literal[False] = False
    pipeline_integration_authorized: Literal[False] = False
    external_memory_systems_rerun: Literal[False] = False
    manual_identity_adjudications_materialized: Literal[False] = False
    candidate_v3_queue_modified: Literal[False] = False
    longmemeval_status: Literal[
        "structured_l2_identity_unresolved"
    ] = "structured_l2_identity_unresolved"


class TypedExtractorFreshV2Preregistration(StrictModel):
    schema_version: Literal[
        "typed-extractor-fresh-v2-preregistration-v2"
    ] = "typed-extractor-fresh-v2-preregistration-v2"
    status: Literal["frozen"] = "frozen"
    evaluation_id: Literal[
        "typed-extractor-v2-fresh-hidden-v2"
    ] = "typed-extractor-v2-fresh-hidden-v2"
    passing_chains: dict[str, FrozenPassingChain]
    authorship: AuthorshipPolicy
    quality_thresholds: dict[str, dict[str, float]]
    safety_thresholds: dict[str, int]
    model_policy: ModelPolicy
    input_sha256: dict[str, str]
    code_sha256: dict[str, str]
    expected_future_paths: list[str]
    chronology: Chronology
    claim_boundary: ClaimBoundary

    @model_validator(mode="after")
    def validate_contract(self) -> "TypedExtractorFreshV2Preregistration":
        expected_chains = {
            layer: FrozenPassingChain.model_validate(value)
            for layer, value in EXPECTED_PASSING_CHAINS.items()
        }
        if self.passing_chains != expected_chains:
            raise ValueError("fresh v2 passing chain contract mismatch")
        expected_quality = {
            "l1": L1_QUALITY_THRESHOLDS,
            "l2": L2_QUALITY_THRESHOLDS,
        }
        if self.quality_thresholds != expected_quality:
            raise ValueError("fresh v2 quality threshold mismatch")
        if self.safety_thresholds != SAFETY_THRESHOLDS:
            raise ValueError("fresh v2 safety threshold mismatch")
        if self.expected_future_paths != list(EXPECTED_FUTURE_PATHS):
            raise ValueError("fresh v2 future path contract mismatch")
        for hashes in (self.input_sha256, self.code_sha256):
            if not hashes or any(
                len(value) != 64
                or any(char not in "0123456789abcdef" for char in value)
                for value in hashes.values()
            ):
                raise ValueError("invalid fresh v2 preregistration hash set")
        return self


def _input_paths(workspace_root: Path) -> dict[str, Path]:
    assessment = workspace_root / "artifacts/automatic-extraction-assessment"
    l1_dev_root = assessment / "typed-extractor-v2-dev-v3"
    l2_dev_root = assessment / "typed-extractor-v2-l2-dev-v9"
    l1_root = assessment / "typed-extractor-v2-l1-dev-repair-v2"
    l2_root = assessment / "typed-extractor-v2-l2-dev-repair-v3"
    l1_run = l1_root / "model-runs" / L1_RUN_ID
    l2_run = l2_root / "model-runs" / L2_RUN_ID
    fresh_v1 = assessment / "typed-extractor-v2-fresh-hidden-v1"
    return {
        "l1-dev/source-cases-l1.json": l1_dev_root / "source-cases-l1.json",
        "l1-dev/public-l1.json": l1_dev_root / "public-l1.json",
        "l1-dev/authority-l1.json": l1_dev_root / "authority-l1.json",
        "l1-dev/gold-l1.json": l1_dev_root / "gold-l1.json",
        "l1-dev/manifest-l1.json": l1_dev_root / "manifest-l1.json",
        "l2-dev/source-cases-l2.json": l2_dev_root / "source-cases-l2.json",
        "l2-dev/public-l2.json": l2_dev_root / "public-l2.json",
        "l2-dev/authority-l2.json": l2_dev_root / "authority-l2.json",
        "l2-dev/gold-l2.json": l2_dev_root / "gold-l2.json",
        "l2-dev/manifest-l2.json": l2_dev_root / "manifest-l2.json",
        "l1-final/proposer-prompt-l1-v10.md": l1_root
        / "proposer-prompt-l1-v10.md",
        "l1-final/diagnostic-source-l1.json": l1_root
        / "diagnostic-source-l1.json",
        "l1-final/public-l1.json": l1_root / "public-l1.json",
        "l1-final/authority-l1.json": l1_root / "authority-l1.json",
        "l1-final/gold-l1.json": l1_root / "gold-l1.json",
        "l1-final/manifest-l1.json": l1_root / "manifest-l1.json",
        "l1-final/dispatch.json": l1_run / "dispatch.json",
        "l1-final/raw-response.json": l1_run / "raw-response.json",
        "l1-final/proposals.json": l1_run / "proposals.json",
        "l1-final/provenance.json": l1_run / "provenance.json",
        "l1-final/score.json": l1_run / "score.json",
        "l1-final/qualification.json": l1_run / "qualification.json",
        "l2-final/proposer-prompt-l2.md": l2_root / "proposer-prompt-l2.md",
        "l2-final/diagnostic-source-l2.json": l2_root
        / "diagnostic-source-l2.json",
        "l2-final/public-l2.json": l2_root / "public-l2.json",
        "l2-final/authority-l2.json": l2_root / "authority-l2.json",
        "l2-final/gold-l2.json": l2_root / "gold-l2.json",
        "l2-final/manifest-l2.json": l2_root / "manifest-l2.json",
        "l2-final/dispatch.json": l2_run / "dispatch.json",
        "l2-final/raw-response.json": l2_run / "raw-response.json",
        "l2-final/proposals.json": l2_run / "proposals.json",
        "l2-final/provenance.json": l2_run / "provenance.json",
        "l2-final/score.json": l2_run / "score.json",
        "l2-final/qualification.json": l2_run / "qualification.json",
        "fresh-v1/preregistration.json": assessment
        / "typed-extractor-v2-fresh-hidden-prereg-v1/preregistration.json",
        "fresh-v1/chronology-receipt.json": fresh_v1
        / "chronology-receipt.json",
        "fresh-v1/overall-report.md": fresh_v1 / "overall-report.md",
        "fresh-v1/l1/source-cases-l1.json": fresh_v1
        / "l1/source-cases-l1.json",
        "fresh-v1/l1/public-l1.json": fresh_v1 / "l1/public-l1.json",
        "fresh-v1/l1/authority-l1.json": fresh_v1 / "l1/authority-l1.json",
        "fresh-v1/l1/gold-l1.json": fresh_v1 / "l1/gold-l1.json",
        "fresh-v1/l1/manifest-l1.json": fresh_v1 / "l1/manifest-l1.json",
        "fresh-v1/l2/source-cases-l2.json": fresh_v1
        / "l2/source-cases-l2.json",
        "fresh-v1/l2/public-l2.json": fresh_v1 / "l2/public-l2.json",
        "fresh-v1/l2/authority-l2.json": fresh_v1 / "l2/authority-l2.json",
        "fresh-v1/l2/gold-l2.json": fresh_v1 / "l2/gold-l2.json",
        "fresh-v1/l2/manifest-l2.json": fresh_v1 / "l2/manifest-l2.json",
    }


def _code_paths(workspace_root: Path) -> dict[str, Path]:
    module_root = workspace_root / "tools/natural_memory_benchmark"
    test_root = workspace_root / "tests/natural_memory_benchmark"
    return {
        "cli.py": module_root / "cli.py",
        "io.py": module_root / "io.py",
        "typed_extractor_dev_repair_qualification.py": module_root
        / "typed_extractor_dev_repair_qualification.py",
        "typed_extractor_fresh_v2_prereg.py": module_root
        / "typed_extractor_fresh_v2_prereg.py",
        "typed_extractor_l1.py": module_root / "typed_extractor_l1.py",
        "typed_extractor_l2.py": module_root / "typed_extractor_l2.py",
        "typed_extractor_model_run.py": module_root
        / "typed_extractor_model_run.py",
        "typed_extractor_l2_model_run.py": module_root
        / "typed_extractor_l2_model_run.py",
        "test_typed_extractor_fresh_v2_prereg.py": test_root
        / "test_typed_extractor_fresh_v2_prereg.py",
    }


def _require_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"{label} missing: {path}")


def _require_read_only(path: Path, label: str) -> None:
    """Verify a committed input portably.

    Content-based rather than mode-based: git records only the executable bit, so
    a 0444 input arrives as 0644 and a mode precondition rejects correct files on
    every fresh clone. Mode is retained only for freshly written output -- see
    ``frozen_input_guard``.
    """
    require_frozen_input(path, label)


def _require_future_artifacts_absent(
    *,
    preregistration_root: Path,
    evaluation_root: Path,
    workspace_root: Path,
) -> None:
    if evaluation_root.exists():
        raise ValueError("fresh v2 evaluation root must be absent before preregistration")
    for raw_path in FUTURE_WORKSPACE_PATHS:
        path = workspace_root / raw_path
        if path.exists():
            raise ValueError(f"future authoring artifact must be absent: {path}")
    receipt = preregistration_root / AUTHORING_RECEIPT_NAME
    if receipt.exists():
        raise ValueError(f"future authoring receipt must be absent: {receipt}")


def _assert_exact_passing_hashes(input_sha256: dict[str, str]) -> None:
    expected = {
        "l1-final/proposer-prompt-l1-v10.md": EXPECTED_PASSING_CHAINS["l1"][
            "prompt_sha256"
        ],
        "l2-final/proposer-prompt-l2.md": EXPECTED_PASSING_CHAINS["l2"][
            "prompt_sha256"
        ],
    }
    for layer in ("l1", "l2"):
        for filename, expected_hash in EXPECTED_PASSING_CHAINS[layer][
            "artifact_sha256"
        ].items():
            expected[f"{layer}-final/{filename}"] = expected_hash
    for name, expected_hash in expected.items():
        if input_sha256.get(name) != expected_hash:
            raise ValueError(f"frozen passing chain hash mismatch: {name}")


def _verify_qualified_chain(input_paths: dict[str, Path], layer: str) -> None:
    score = load_json(input_paths[f"{layer}-final/score.json"])
    qualification = load_json(input_paths[f"{layer}-final/qualification.json"])
    if qualification.get("status") != "qualified":
        raise ValueError(f"{layer} passing chain is not qualified")
    if not qualification.get("raw_proposer_quality_ready"):
        raise ValueError(f"{layer} raw proposer quality is not ready")
    if not qualification.get("deterministic_gate_safety_ready"):
        raise ValueError(f"{layer} deterministic gate safety is not ready")
    expected_metrics = (
        L1_QUALITY_THRESHOLDS if layer == "l1" else L2_QUALITY_THRESHOLDS
    )
    metrics = score.get("metrics", {})
    if any(metrics.get(name) != value for name, value in expected_metrics.items()):
        raise ValueError(f"{layer} passing chain exact metric mismatch")
    if any(metrics.get(name) != value for name, value in SAFETY_THRESHOLDS.items()):
        raise ValueError(f"{layer} passing chain safety count mismatch")


def _build_preregistration(
    *,
    preregistration_root: Path,
    evaluation_root: Path,
    workspace_root: Path,
    freeze_time: str,
) -> TypedExtractorFreshV2Preregistration:
    _require_future_artifacts_absent(
        preregistration_root=preregistration_root,
        evaluation_root=evaluation_root,
        workspace_root=workspace_root,
    )
    input_paths = _input_paths(workspace_root)
    code_paths = _code_paths(workspace_root)
    for name, path in input_paths.items():
        _require_read_only(path, name)
    for name, path in code_paths.items():
        _require_file(path, name)
    input_sha256 = {name: sha256_file(path) for name, path in input_paths.items()}
    _assert_exact_passing_hashes(input_sha256)
    _verify_qualified_chain(input_paths, "l1")
    _verify_qualified_chain(input_paths, "l2")
    return TypedExtractorFreshV2Preregistration(
        passing_chains={
            layer: FrozenPassingChain.model_validate(value)
            for layer, value in EXPECTED_PASSING_CHAINS.items()
        },
        authorship=AuthorshipPolicy(
            l1_families=dict(L1_FAMILIES),
            l2_families=dict(L2_FAMILIES),
        ),
        quality_thresholds={
            "l1": dict(L1_QUALITY_THRESHOLDS),
            "l2": dict(L2_QUALITY_THRESHOLDS),
        },
        safety_thresholds=dict(SAFETY_THRESHOLDS),
        model_policy=ModelPolicy(),
        input_sha256=input_sha256,
        code_sha256={name: sha256_file(path) for name, path in code_paths.items()},
        expected_future_paths=list(EXPECTED_FUTURE_PATHS),
        chronology=Chronology(
            freeze_time=freeze_time,
            preregistration_root=str(preregistration_root),
            evaluation_root=str(evaluation_root),
        ),
        claim_boundary=ClaimBoundary(),
    )


def _resolved(path: Path) -> Path:
    return path.resolve()


def freeze_typed_extractor_fresh_v2_preregistration(
    *,
    output_root: Path,
    evaluation_root: Path,
    workspace_root: Path,
    freeze_time: str,
) -> dict[str, Any]:
    output_root = _resolved(output_root)
    evaluation_root = _resolved(evaluation_root)
    workspace_root = _resolved(workspace_root)
    if output_root.exists():
        raise ValueError("fresh v2 preregistration root must be absent before freeze")
    preregistration = _build_preregistration(
        preregistration_root=output_root,
        evaluation_root=evaluation_root,
        workspace_root=workspace_root,
        freeze_time=freeze_time,
    )
    output_path = output_root / "preregistration.json"
    write_json_immutable(output_path, preregistration)
    output_path.chmod(0o444)
    return preregistration.model_dump(mode="json")


def validate_typed_extractor_fresh_v2_preregistration(
    *,
    root: Path,
    evaluation_root: Path,
    workspace_root: Path,
    freeze_time: str,
) -> dict[str, Any]:
    root = _resolved(root)
    evaluation_root = _resolved(evaluation_root)
    workspace_root = _resolved(workspace_root)
    preregistration_path = root / "preregistration.json"
    _require_read_only(preregistration_path, "fresh v2 preregistration")
    actual = TypedExtractorFreshV2Preregistration.model_validate(
        load_json(preregistration_path)
    )
    expected = _build_preregistration(
        preregistration_root=root,
        evaluation_root=evaluation_root,
        workspace_root=workspace_root,
        freeze_time=freeze_time,
    )
    if actual != expected:
        raise ValueError("typed extractor fresh v2 preregistration drift")
    return {
        "status": "valid",
        "evaluation_id": actual.evaluation_id,
        "l1_case_count": actual.authorship.l1_case_count,
        "l2_case_count": actual.authorship.l2_case_count,
        "future_artifacts_absent": True,
        "hidden_artifacts_created": False,
    }
