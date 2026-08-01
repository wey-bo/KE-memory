from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .frozen_input_guard import require_frozen_input
from .io import load_json, sha256_file, write_json_immutable


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


L1_THRESHOLDS: dict[str, float | int] = {
    "proposal_coverage": 1.0,
    "schema_valid_rate": 1.0,
    "raw_decision_accuracy": 0.9,
    "raw_abstention_f1": 0.8,
    "exact_evidence_rate": 1.0,
    "safety_field_accuracy": 0.85,
    "raw_critical_false_emission_count": 0,
    "deterministic_critical_false_materialization_count": 0,
}

L2_THRESHOLDS: dict[str, float | int] = {
    "proposal_coverage": 1.0,
    "schema_valid_rate": 1.0,
    "raw_decision_accuracy": 0.9,
    "raw_abstention_f1": 0.8,
    "exact_evidence_rate": 1.0,
    "support_id_accuracy": 1.0,
    "source_coverage_accuracy": 1.0,
    "safety_field_accuracy": 0.85,
    "raw_critical_false_emission_count": 0,
    "deterministic_critical_false_materialization_count": 0,
}

L1_STRATA = {
    "ordinary_explicit": 8,
    "non_explicit_derivation": 4,
    "condition_bearing": 3,
    "scope_bearing": 3,
    "non_active_lifecycle": 2,
    "time_bearing": 2,
    "negative_or_control": 2,
}

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


class FreshSelection(StrictModel):
    l1_case_count: Literal[24] = 24
    l2_case_count: Literal[8] = 8
    l1_namespace: Literal[
        "typed-extractor-l1-fresh-hidden-v1:2026-07-28"
    ] = "typed-extractor-l1-fresh-hidden-v1:2026-07-28"
    l2_namespace: Literal[
        "typed-extractor-l2-fresh-hidden-v1:2026-07-28"
    ] = "typed-extractor-l2-fresh-hidden-v1:2026-07-28"
    l1_strata: dict[str, int]
    l1_priority_order: list[str]
    l2_selection_policy: Literal["all_unused_bridge_v3_cross_turn"] = (
        "all_unused_bridge_v3_cross_turn"
    )
    semantic_filtering_allowed: Literal[False] = False

    @model_validator(mode="after")
    def validate_selection(self) -> "FreshSelection":
        if self.l1_strata != L1_STRATA:
            raise ValueError("fresh L1 stratum contract mismatch")
        if self.l1_priority_order != list(L1_STRATA):
            raise ValueError("fresh L1 stratum priority mismatch")
        if sum(self.l1_strata.values()) != self.l1_case_count:
            raise ValueError("fresh L1 stratum count mismatch")
        return self


class FreshModelPolicy(StrictModel):
    requested_model: Literal["deepseek-chat"] = "deepseek-chat"
    history_context_inherited: Literal[False] = False
    authority_or_gold_allowed_before_freeze: Literal[False] = False
    semantic_retry_allowed: Literal[False] = False
    transport_retry_requires_new_immutable_run: Literal[True] = True
    isolation_enforcement: Literal["declarative-agent-file-access-contract"] = (
        "declarative-agent-file-access-contract"
    )


class FreshChronology(StrictModel):
    freeze_time: str = Field(pattern=r"^2026-07-28T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
    evidence_kind: Literal["filesystem-mtime-plus-sha256"] = (
        "filesystem-mtime-plus-sha256"
    )
    trusted_timestamp_authority: Literal[False] = False
    hidden_artifacts_absent_at_freeze: Literal[True] = True
    evaluation_root: str = Field(min_length=1)


class FreshClaimBoundary(StrictModel):
    automatic_l1_write_count: Literal[0] = 0
    automatic_l2_write_count: Literal[0] = 0
    automatic_identity_write_count: Literal[0] = 0
    automatic_membership_write_count: Literal[0] = 0
    automatic_closure_write_count: Literal[0] = 0
    automatic_revision_write_count: Literal[0] = 0
    automatic_snapshot_write_count: Literal[0] = 0
    automatic_aggregate_write_count: Literal[0] = 0
    embedding_authority: Literal[False] = False
    pipeline_integration_authorized: Literal[False] = False
    external_memory_systems_rerun: Literal[False] = False
    manual_identity_adjudications_materialized: Literal[False] = False
    longmemeval_status: Literal["structured_l2_identity_unresolved"] = (
        "structured_l2_identity_unresolved"
    )


class TypedExtractorFreshPreregistration(StrictModel):
    schema_version: Literal["typed-extractor-fresh-preregistration-v1"] = (
        "typed-extractor-fresh-preregistration-v1"
    )
    status: Literal["frozen"] = "frozen"
    evaluation_id: Literal["typed-extractor-v2-fresh-hidden-v1"] = (
        "typed-extractor-v2-fresh-hidden-v1"
    )
    selection: FreshSelection
    thresholds: dict[str, dict[str, float | int]]
    model_policy: FreshModelPolicy
    input_sha256: dict[str, str]
    code_sha256: dict[str, str]
    expected_hidden_paths: list[str]
    chronology: FreshChronology
    claim_boundary: FreshClaimBoundary

    @model_validator(mode="after")
    def validate_contract(self) -> "TypedExtractorFreshPreregistration":
        if self.thresholds != {"l1": L1_THRESHOLDS, "l2": L2_THRESHOLDS}:
            raise ValueError("fresh qualification threshold mismatch")
        if self.expected_hidden_paths != list(EXPECTED_HIDDEN_PATHS):
            raise ValueError("fresh expected hidden path mismatch")
        for hashes in (self.input_sha256, self.code_sha256):
            if not hashes or any(
                len(value) != 64
                or any(char not in "0123456789abcdef" for char in value)
                for value in hashes.values()
            ):
                raise ValueError("invalid preregistration hash set")
        return self


def _require_read_only(path: Path, label: str) -> None:
    """Verify a committed input portably.

    Content-based rather than mode-based: git records only the executable bit, so
    a 0444 input arrives as 0644 and a mode precondition rejects correct files on
    every fresh clone. Mode is retained only for freshly written output -- see
    ``frozen_input_guard``.
    """
    require_frozen_input(path, label)


def _require_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"{label} missing: {path}")


def _input_paths(
    *,
    workspace_root: Path,
    bridge_ledger_path: Path,
    l1_prompt_path: Path,
    l2_prompt_path: Path,
    l1_dev_root: Path,
    l2_dev_root: Path,
) -> dict[str, Path]:
    l1_run = (
        l1_dev_root
        / "model-runs"
        / "run-20260728T091848Z-deepseek-chat-official-typed-l1-dev-v9"
    )
    l2_run = (
        l2_dev_root
        / "model-runs"
        / "run-20260728T084011Z-deepseek-chat-official-typed-l2-dev-v12"
    )
    return {
        "bridge-v3/compatibility-ledger.json": bridge_ledger_path,
        "l1/proposer-prompt-l1.md": l1_prompt_path,
        "l1/source-cases-l1.json": l1_dev_root / "source-cases-l1.json",
        "l1/public-l1.json": l1_dev_root / "public-l1.json",
        "l1/passing/proposals.json": l1_run / "proposals.json",
        "l1/passing/provenance.json": l1_run / "provenance.json",
        "l1/passing/score.json": l1_run / "score.json",
        "l2/proposer-prompt-l2.md": l2_prompt_path,
        "l2/source-cases-l2.json": l2_dev_root / "source-cases-l2.json",
        "l2/public-l2.json": l2_dev_root / "public-l2.json",
        "l2/passing/proposals.json": l2_run / "proposals.json",
        "l2/passing/provenance.json": l2_run / "provenance.json",
        "l2/passing/score.json": l2_run / "score.json",
        "source/KE-test.json": workspace_root / "data/gold-candidates/KE-test.json",
        "source/turn-manifest.json": (
            workspace_root / "knowledge-extraction/turn-pass/validated/manifest.json"
        ),
        "source/dialogue-manifest.json": (
            workspace_root
            / "knowledge-extraction/dialogue-pass/validated/manifest.json"
        ),
        "source/final-knowledge.json": (
            workspace_root / "knowledge-extraction/final-knowledge.json"
        ),
        "source/run.json": workspace_root / "knowledge-extraction/run.json",
        "source/source-segments.json": (
            workspace_root / "knowledge-extraction/source-segments.json"
        ),
    }


def _code_paths(workspace_root: Path) -> dict[str, Path]:
    module_root = workspace_root / "tools/natural_memory_benchmark"
    return {
        name: module_root / name
        for name in (
            "extraction_bridge_assessment.py",
            "typed_extractor_fresh_prereg.py",
            "typed_extractor_l1.py",
            "typed_extractor_l1_api_run.py",
            "typed_extractor_l2.py",
            "typed_extractor_l2_api_run.py",
            "typed_extractor_l2_model_run.py",
            "typed_extractor_model_run.py",
        )
    }


def _build_preregistration(
    *,
    evaluation_root: Path,
    workspace_root: Path,
    bridge_ledger_path: Path,
    l1_prompt_path: Path,
    l2_prompt_path: Path,
    l1_dev_root: Path,
    l2_dev_root: Path,
    freeze_time: str,
) -> TypedExtractorFreshPreregistration:
    if evaluation_root.exists():
        raise ValueError("fresh hidden evaluation root must be absent before preregistration")
    inputs = _input_paths(
        workspace_root=workspace_root,
        bridge_ledger_path=bridge_ledger_path,
        l1_prompt_path=l1_prompt_path,
        l2_prompt_path=l2_prompt_path,
        l1_dev_root=l1_dev_root,
        l2_dev_root=l2_dev_root,
    )
    code = _code_paths(workspace_root)
    for name, path in inputs.items():
        if name.startswith("source/"):
            _require_file(path, name)
        else:
            _require_read_only(path, name)
    for name, path in code.items():
        _require_file(path, name)
    return TypedExtractorFreshPreregistration(
        selection=FreshSelection(
            l1_strata=dict(L1_STRATA),
            l1_priority_order=list(L1_STRATA),
        ),
        thresholds={"l1": dict(L1_THRESHOLDS), "l2": dict(L2_THRESHOLDS)},
        model_policy=FreshModelPolicy(),
        input_sha256={name: sha256_file(path) for name, path in inputs.items()},
        code_sha256={name: sha256_file(path) for name, path in code.items()},
        expected_hidden_paths=list(EXPECTED_HIDDEN_PATHS),
        chronology=FreshChronology(
            freeze_time=freeze_time,
            evaluation_root=str(evaluation_root),
        ),
        claim_boundary=FreshClaimBoundary(),
    )


def _resolve_inputs(
    *,
    output_root: Path | None = None,
    root: Path | None = None,
    evaluation_root: Path,
    workspace_root: Path,
    bridge_ledger_path: Path,
    l1_prompt_path: Path,
    l2_prompt_path: Path,
    l1_dev_root: Path,
    l2_dev_root: Path,
) -> dict[str, Path]:
    values = {
        "evaluation_root": evaluation_root,
        "workspace_root": workspace_root,
        "bridge_ledger_path": bridge_ledger_path,
        "l1_prompt_path": l1_prompt_path,
        "l2_prompt_path": l2_prompt_path,
        "l1_dev_root": l1_dev_root,
        "l2_dev_root": l2_dev_root,
    }
    if output_root is not None:
        values["output_root"] = output_root
    if root is not None:
        values["root"] = root
    return {name: value.resolve() for name, value in values.items()}


def freeze_typed_extractor_fresh_preregistration(
    *,
    output_root: Path,
    evaluation_root: Path,
    workspace_root: Path,
    bridge_ledger_path: Path,
    l1_prompt_path: Path,
    l2_prompt_path: Path,
    l1_dev_root: Path,
    l2_dev_root: Path,
    freeze_time: str,
) -> dict[str, Any]:
    paths = _resolve_inputs(
        output_root=output_root,
        evaluation_root=evaluation_root,
        workspace_root=workspace_root,
        bridge_ledger_path=bridge_ledger_path,
        l1_prompt_path=l1_prompt_path,
        l2_prompt_path=l2_prompt_path,
        l1_dev_root=l1_dev_root,
        l2_dev_root=l2_dev_root,
    )
    preregistration = _build_preregistration(
        evaluation_root=paths["evaluation_root"],
        workspace_root=paths["workspace_root"],
        bridge_ledger_path=paths["bridge_ledger_path"],
        l1_prompt_path=paths["l1_prompt_path"],
        l2_prompt_path=paths["l2_prompt_path"],
        l1_dev_root=paths["l1_dev_root"],
        l2_dev_root=paths["l2_dev_root"],
        freeze_time=freeze_time,
    )
    output_path = paths["output_root"] / "preregistration.json"
    write_json_immutable(output_path, preregistration)
    output_path.chmod(0o444)
    return preregistration.model_dump(mode="json")


def validate_typed_extractor_fresh_preregistration(
    *,
    root: Path,
    evaluation_root: Path,
    workspace_root: Path,
    bridge_ledger_path: Path,
    l1_prompt_path: Path,
    l2_prompt_path: Path,
    l1_dev_root: Path,
    l2_dev_root: Path,
    freeze_time: str,
) -> dict[str, Any]:
    paths = _resolve_inputs(
        root=root,
        evaluation_root=evaluation_root,
        workspace_root=workspace_root,
        bridge_ledger_path=bridge_ledger_path,
        l1_prompt_path=l1_prompt_path,
        l2_prompt_path=l2_prompt_path,
        l1_dev_root=l1_dev_root,
        l2_dev_root=l2_dev_root,
    )
    prereg_path = paths["root"] / "preregistration.json"
    _require_read_only(prereg_path, "preregistration")
    actual = TypedExtractorFreshPreregistration.model_validate(load_json(prereg_path))
    expected = _build_preregistration(
        evaluation_root=paths["evaluation_root"],
        workspace_root=paths["workspace_root"],
        bridge_ledger_path=paths["bridge_ledger_path"],
        l1_prompt_path=paths["l1_prompt_path"],
        l2_prompt_path=paths["l2_prompt_path"],
        l1_dev_root=paths["l1_dev_root"],
        l2_dev_root=paths["l2_dev_root"],
        freeze_time=freeze_time,
    )
    if actual != expected:
        raise ValueError("typed extractor fresh preregistration drift")
    return {
        "status": "valid",
        "l1_case_count": actual.selection.l1_case_count,
        "l2_case_count": actual.selection.l2_case_count,
        "hidden_artifacts_absent": True,
    }
