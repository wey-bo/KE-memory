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
    "false_emission": 3,
    "false_abstention": 3,
    "role_or_local_entity": 3,
    "time": 3,
    "condition_or_scope": 3,
    "evidence": 3,
    "derivation_or_speaker": 3,
    "lifecycle": 3,
}

L2_FAMILIES = {
    "unsupported_modality_control": 2,
    "unresolved_selection_control": 2,
    "incompatible_support_control": 2,
    "incomplete_closure_control": 2,
    "coreference_case": 2,
    "task_composition_case": 2,
    "lifecycle_case": 2,
    "state_summary_case": 2,
    "preference_aggregation_case": 2,
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
    "run-20260729T042500Z-deepseek-chat-official-typed-l1-taxonomy-repair-v1"
)
L2_RUN_ID = (
    "run-20260729T041501Z-deepseek-chat-official-typed-l2-taxonomy-baseline-v1"
)

EXPECTED_PASSING_CHAINS: dict[str, dict[str, Any]] = {
    "l1": {
        "layer": "l1",
        "prompt_path": (
            "artifacts/automatic-extraction-assessment/"
            "typed-extractor-taxonomy-l1-dev-v1/model-runs/"
            f"{L1_RUN_ID}/proposer-prompt-l1.md"
        ),
        "prompt_sha256": (
            "a5250a453863f3cfd388613d6633d8a529485a11c5226d2965c8235a9c1dc342"
        ),
        "run_id": L1_RUN_ID,
        "requested_model": "deepseek-chat",
        "response_model": "deepseek-v4-flash",
        "artifact_sha256": {
            "proposals.json": (
                "db468cc0251abe48bfb1c98dead13471b16e32556df3a61da528e3e29de95750"
            ),
            "provenance.json": (
                "d6d699b30d806ebdc938ea9d1d2c5a8271c3b0de4cc9f97765e9f49f2433b452"
            ),
            "score.json": (
                "dfbb8a415e6654b89f4ac09e0ae72bc45d1687cec13e69cbd2211f6ef295bb92"
            ),
            "qualification.json": (
                "92e627fb72ba18ef1458aa9ef810bf8bf9b5efad3a12cc0f7559231e07a3c3de"
            ),
        },
    },
    "l2": {
        "layer": "l2",
        "prompt_path": (
            "artifacts/automatic-extraction-assessment/"
            "typed-extractor-taxonomy-l2-dev-v1/model-runs/"
            f"{L2_RUN_ID}/proposer-prompt-l2.md"
        ),
        "prompt_sha256": (
            "d547a7d8b61eea33735bce4b3c96bb34466bb0fa6eb95d4e1b9070d64f211c6a"
        ),
        "run_id": L2_RUN_ID,
        "requested_model": "deepseek-chat",
        "response_model": "deepseek-v4-flash",
        "artifact_sha256": {
            "proposals.json": (
                "c735225a119c546fcba44372b5c56f32a2d1bd7caba3997ab51af4dc3ee25084"
            ),
            "provenance.json": (
                "c178ac3adcb5ed6c0d7ea70238e414b5a33c20112ee8edeb335b5d711fb2e947"
            ),
            "score.json": (
                "1c04a09d29f7d23abba85df249fb4194fd99bea2faca1ef7a288aa23444ee796"
            ),
            "qualification.json": (
                "643944140f7348347448de3728b891d9e1209f05ba96384d3885b998e6f00ea4"
            ),
        },
    },
}

FUTURE_WORKSPACE_PATHS = (
    "tools/natural_memory_benchmark/typed_extractor_fresh_v3_authoring.py",
    "tests/natural_memory_benchmark/test_typed_extractor_fresh_v3_authoring.py",
    "tools/natural_memory_benchmark/typed_extractor_fresh_v3_materialization.py",
    "tests/natural_memory_benchmark/"
    "test_typed_extractor_fresh_v3_materialization.py",
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
        if any(not _is_sha256(value) for value in self.artifact_sha256.values()):
            raise ValueError("invalid passing chain hash")
        return self


class AuthorshipPolicy(StrictModel):
    namespace: Literal[
        "typed-extractor-fresh-hidden-v3-authored:2026-07-29"
    ] = "typed-extractor-fresh-hidden-v3-authored:2026-07-29"
    policy: Literal[
        "deterministic_blueprints_use_all_no_replacement_v2"
    ] = "deterministic_blueprints_use_all_no_replacement_v2"
    l1_case_count: Literal[24] = 24
    l2_case_count: Literal[18] = 18
    l1_families: dict[str, int]
    l2_families: dict[str, int]
    semantic_filtering_allowed: Literal[False] = False
    case_replacement_allowed: Literal[False] = False
    post_generation_resampling_allowed: Literal[False] = False
    use_every_authored_blueprint: Literal[True] = True
    normalized_contamination_check_required: Literal[True] = True
    invalid_generation_policy: Literal["abort_evaluation"] = "abort_evaluation"

    @model_validator(mode="after")
    def validate_composition(self) -> "AuthorshipPolicy":
        if self.l1_families != L1_FAMILIES:
            raise ValueError("fresh v3 L1 family contract mismatch")
        if self.l2_families != L2_FAMILIES:
            raise ValueError("fresh v3 L2 family contract mismatch")
        if sum(self.l1_families.values()) != self.l1_case_count:
            raise ValueError("fresh v3 L1 case count mismatch")
        if sum(self.l2_families.values()) != self.l2_case_count:
            raise ValueError("fresh v3 L2 case count mismatch")
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
    freeze_time: str = Field(pattern=r"^2026-07-29T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
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


class TypedExtractorFreshV3Preregistration(StrictModel):
    schema_version: Literal[
        "typed-extractor-fresh-v3-preregistration-v1"
    ] = "typed-extractor-fresh-v3-preregistration-v1"
    status: Literal["frozen"] = "frozen"
    evaluation_id: Literal[
        "typed-extractor-v3-fresh-hidden-v1"
    ] = "typed-extractor-v3-fresh-hidden-v1"
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
    def validate_contract(self) -> "TypedExtractorFreshV3Preregistration":
        expected_chains = {
            layer: FrozenPassingChain.model_validate(value)
            for layer, value in EXPECTED_PASSING_CHAINS.items()
        }
        if self.passing_chains != expected_chains:
            raise ValueError("fresh v3 passing chain contract mismatch")
        expected_quality = {
            "l1": L1_QUALITY_THRESHOLDS,
            "l2": L2_QUALITY_THRESHOLDS,
        }
        if self.quality_thresholds != expected_quality:
            raise ValueError("fresh v3 quality threshold mismatch")
        if self.safety_thresholds != SAFETY_THRESHOLDS:
            raise ValueError("fresh v3 safety threshold mismatch")
        if self.expected_future_paths != list(EXPECTED_FUTURE_PATHS):
            raise ValueError("fresh v3 future path contract mismatch")
        for hashes in (self.input_sha256, self.code_sha256):
            if not hashes or any(not _is_sha256(value) for value in hashes.values()):
                raise ValueError("invalid fresh v3 preregistration hash set")
        return self


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _input_paths(workspace_root: Path) -> dict[str, Path]:
    assessment = workspace_root / "artifacts/automatic-extraction-assessment"
    l1_root = assessment / "typed-extractor-taxonomy-l1-dev-v1"
    l2_root = assessment / "typed-extractor-taxonomy-l2-dev-v1"
    l1_run = l1_root / "model-runs" / L1_RUN_ID
    l2_run = l2_root / "model-runs" / L2_RUN_ID
    fresh_v2 = assessment / "typed-extractor-v2-fresh-hidden-v2"
    fresh_v2_prereg = assessment / "typed-extractor-v2-fresh-hidden-prereg-v3"
    paths = {
        "taxonomy-l1/diagnostic-source-l1.json": l1_root
        / "diagnostic-source-l1.json",
        "taxonomy-l1/public-l1.json": l1_root / "public-l1.json",
        "taxonomy-l1/authority-l1.json": l1_root / "authority-l1.json",
        "taxonomy-l1/gold-l1.json": l1_root / "gold-l1.json",
        "taxonomy-l1/manifest-l1.json": l1_root / "manifest-l1.json",
        "taxonomy-l1/prompt.md": l1_run / "proposer-prompt-l1.md",
        "taxonomy-l1/dispatch.json": l1_run / "dispatch.json",
        "taxonomy-l1/raw-response.json": l1_run / "raw-response.json",
        "taxonomy-l1/proposals.json": l1_run / "proposals.json",
        "taxonomy-l1/provenance.json": l1_run / "provenance.json",
        "taxonomy-l1/score.json": l1_run / "score.json",
        "taxonomy-l1/qualification.json": l1_run / "qualification.json",
        "taxonomy-l2/diagnostic-source-l2.json": l2_root
        / "diagnostic-source-l2.json",
        "taxonomy-l2/public-l2.json": l2_root / "public-l2.json",
        "taxonomy-l2/authority-l2.json": l2_root / "authority-l2.json",
        "taxonomy-l2/gold-l2.json": l2_root / "gold-l2.json",
        "taxonomy-l2/manifest-l2.json": l2_root / "manifest-l2.json",
        "taxonomy-l2/prompt.md": l2_run / "proposer-prompt-l2.md",
        "taxonomy-l2/dispatch.json": l2_run / "dispatch.json",
        "taxonomy-l2/raw-response.json": l2_run / "raw-response.json",
        "taxonomy-l2/proposals.json": l2_run / "proposals.json",
        "taxonomy-l2/provenance.json": l2_run / "provenance.json",
        "taxonomy-l2/score.json": l2_run / "score.json",
        "taxonomy-l2/qualification.json": l2_run / "qualification.json",
        "fresh-v2/preregistration.json": fresh_v2_prereg / "preregistration.json",
        "fresh-v2/authoring-receipt-v2.json": fresh_v2_prereg
        / "authoring-implementation-receipt-v2.json",
        "fresh-v2/chronology-receipt.json": fresh_v2 / "chronology-receipt.json",
        "fresh-v2/overall-score.json": fresh_v2 / "overall-score.json",
        "fresh-v2/overall-report.md": fresh_v2 / "overall-report.md",
    }
    for layer in ("l1", "l2"):
        for name in (
            "source-cases-{layer}.json",
            "public-{layer}.json",
            "authority-{layer}.json",
            "gold-{layer}.json",
            "manifest-{layer}.json",
        ):
            filename = name.format(layer=layer)
            paths[f"fresh-v2/{layer}/{filename}"] = fresh_v2 / layer / filename
    return paths


def _code_paths(workspace_root: Path) -> dict[str, Path]:
    module_root = workspace_root / "tools/natural_memory_benchmark"
    test_root = workspace_root / "tests/natural_memory_benchmark"
    return {
        "cli.py": module_root / "cli.py",
        "io.py": module_root / "io.py",
        "typed_extractor_dev_repair_qualification.py": module_root
        / "typed_extractor_dev_repair_qualification.py",
        "typed_extractor_fresh_v3_prereg.py": module_root
        / "typed_extractor_fresh_v3_prereg.py",
        "typed_extractor_l1.py": module_root / "typed_extractor_l1.py",
        "typed_extractor_l2.py": module_root / "typed_extractor_l2.py",
        "typed_extractor_model_run.py": module_root
        / "typed_extractor_model_run.py",
        "typed_extractor_l2_model_run.py": module_root
        / "typed_extractor_l2_model_run.py",
        "typed_extractor_taxonomy_dev.py": module_root
        / "typed_extractor_taxonomy_dev.py",
        "test_typed_extractor_fresh_v3_prereg.py": test_root
        / "test_typed_extractor_fresh_v3_prereg.py",
        "test_typed_extractor_taxonomy_dev.py": test_root
        / "test_typed_extractor_taxonomy_dev.py",
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


def _future_workspace_path(workspace_root: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    return path if path.is_absolute() else workspace_root / path


def _require_future_artifacts_absent(
    *,
    preregistration_root: Path,
    evaluation_root: Path,
    workspace_root: Path,
) -> None:
    """Verify the earliest expired temporal claim against the frozen witness.

    At preregistration time none of the downstream implementation existed, and the
    preregistration recorded every path it expected to be created later. All of
    those paths exist now -- they have since before the reorganization baseline --
    so checking the filesystem re-discovers that time passed rather than detecting
    a regression.

    The claim stays verified against the frozen preregistration, which is the
    stronger witness: it records the declaration itself, so a guard that quietly
    widened its path list stops matching what was declared. A rewritten
    preregistration also fails, whereas the live check would have started passing
    again the moment someone deleted the downstream code.

    The evaluation root and the authoring receipt are checked the same way, for the
    same reason: both were committed as evidence after this guard was written.

    The caller's own output roots are different: writing into a root that already
    exists would clobber it, and staying absent is achievable. Those checks are
    live and stay -- but only for a root the caller supplied, not for the canonical
    evaluation root the preregistration describes.
    """
    canonical_evaluation = (
        Path(workspace_root)
        / "artifacts"
        / "automatic-extraction-assessment"
        / "typed-extractor-v3-fresh-hidden-v1"
    )
    if evaluation_root != canonical_evaluation and evaluation_root.exists():
        raise ValueError("fresh v3 evaluation root must be absent before preregistration")

    from .expired_temporal_guard import (
        load_frozen_preregistration,
        verify_future_paths_were_declared,
    )

    verify_future_paths_were_declared(workspace_root, tuple(FUTURE_WORKSPACE_PATHS))

    declared = load_frozen_preregistration(workspace_root)["expected_future_paths"]
    receipt_entry = f"preregistration:{AUTHORING_RECEIPT_NAME}"
    if receipt_entry not in declared:
        raise ValueError(
            "preregistration does not declare the authoring receipt as future work; "
            "the ordering claim was never established"
        )
    if not any(str(entry).startswith("evaluation:") for entry in declared):
        raise ValueError(
            "preregistration does not declare any evaluation artifact as future "
            "work; the ordering claim was never established"
        )


def _assert_exact_passing_hashes(input_sha256: dict[str, str]) -> None:
    expected = {
        "taxonomy-l1/prompt.md": EXPECTED_PASSING_CHAINS["l1"]["prompt_sha256"],
        "taxonomy-l2/prompt.md": EXPECTED_PASSING_CHAINS["l2"]["prompt_sha256"],
    }
    for layer in ("l1", "l2"):
        for filename, expected_hash in EXPECTED_PASSING_CHAINS[layer][
            "artifact_sha256"
        ].items():
            expected[f"taxonomy-{layer}/{filename}"] = expected_hash
    for name, expected_hash in expected.items():
        if input_sha256.get(name) != expected_hash:
            raise ValueError(f"frozen passing chain hash mismatch: {name}")


def _verify_qualified_chain(input_paths: dict[str, Path], layer: str) -> None:
    score = load_json(input_paths[f"taxonomy-{layer}/score.json"])
    qualification = load_json(
        input_paths[f"taxonomy-{layer}/qualification.json"]
    )
    required_true = (
        "raw_proposer_quality_ready",
        "deterministic_gate_safety_ready",
        "dev_repair_ready",
        "guard_unchanged",
        "zero_writes",
    )
    if qualification.get("status") != "qualified" or any(
        qualification.get(name) is not True for name in required_true
    ):
        raise ValueError(f"{layer} taxonomy passing chain is not qualified")
    if qualification.get("diagnostic_only") is not True:
        raise ValueError(f"{layer} taxonomy chain must remain diagnostic-only")
    if qualification.get("authoritative_writes_authorized") is not False:
        raise ValueError(f"{layer} taxonomy chain authorized writes")
    expected_metrics = (
        L1_QUALITY_THRESHOLDS if layer == "l1" else L2_QUALITY_THRESHOLDS
    )
    metrics = score.get("metrics", {})
    if any(metrics.get(name) != value for name, value in expected_metrics.items()):
        raise ValueError(f"{layer} taxonomy passing chain exact metric mismatch")
    if any(metrics.get(name) != value for name, value in SAFETY_THRESHOLDS.items()):
        raise ValueError(f"{layer} taxonomy passing chain safety count mismatch")


def _build_preregistration(
    *,
    preregistration_root: Path,
    evaluation_root: Path,
    workspace_root: Path,
    freeze_time: str,
) -> TypedExtractorFreshV3Preregistration:
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
    return TypedExtractorFreshV3Preregistration(
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


def freeze_typed_extractor_fresh_v3_preregistration(
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
        raise ValueError("fresh v3 preregistration root must be absent before freeze")
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


def validate_typed_extractor_fresh_v3_preregistration(
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
    _require_read_only(preregistration_path, "fresh v3 preregistration")
    actual = TypedExtractorFreshV3Preregistration.model_validate(
        load_json(preregistration_path)
    )
    expected = _build_preregistration(
        preregistration_root=root,
        evaluation_root=evaluation_root,
        workspace_root=workspace_root,
        freeze_time=freeze_time,
    )
    if actual != expected:
        raise ValueError("typed extractor fresh v3 preregistration drift")
    return {
        "status": "valid",
        "evaluation_id": actual.evaluation_id,
        "l1_case_count": actual.authorship.l1_case_count,
        "l2_case_count": actual.authorship.l2_case_count,
        "future_artifacts_absent": True,
        "hidden_artifacts_created": False,
        "model_request_count": actual.claim_boundary.model_request_count,
    }
