from __future__ import annotations

import hashlib
import os
import stat
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from . import typed_extractor_fresh_v3_authoring as authoring
from . import typed_extractor_fresh_v3_snapshot_receipt as relocation
from .typed_extractor_fresh_v3_prereg import L1_FAMILIES, L2_FAMILIES


APPROVED_ACTIVE_RECEIPT_SHA256 = (
    "c810f421d5a3b0726b862ec2f12c89e0d638e0747892637e2a32977587b7ef8c"
)
MATERIALIZER_RELATIVE_PATHS = {
    "typed_extractor_fresh_v3_materialization.py": (
        "tools/natural_memory_benchmark/"
        "typed_extractor_fresh_v3_materialization.py"
    ),
    "test_typed_extractor_fresh_v3_materialization.py": (
        "tests/natural_memory_benchmark/"
        "test_typed_extractor_fresh_v3_materialization.py"
    ),
}
LAYER_VALUES = {
    "l1": {
        "source-cases-l1.json": "source",
        "public-l1.json": "public",
        "authority-l1.json": "authority",
        "gold-l1.json": "gold",
        "manifest-l1.json": "manifest",
    },
    "l2": {
        "source-cases-l2.json": "source",
        "public-l2.json": "public",
        "authority-l2.json": "authority",
        "gold-l2.json": "gold",
        "manifest-l2.json": "manifest",
    },
}
ZERO_WRITES = {
    "aggregate": 0,
    "closure": 0,
    "identity": 0,
    "l1": 0,
    "l2": 0,
    "membership": 0,
    "revision": 0,
    "snapshot": 0,
    "source_revision": 0,
}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class MaterializationTimeLabel(StrictModel):
    value: str

    @field_validator("value")
    @classmethod
    def validate_value(cls, value: str) -> str:
        try:
            parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError as exc:
            raise ValueError(
                "materialization_time must be a valid UTC timestamp"
            ) from exc
        if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
            raise ValueError(
                "materialization_time must be a valid UTC timestamp"
            )
        return value


class MaterializedArtifact(StrictModel):
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=1)
    mode: Literal["0444"] = "0444"


class PreregistrationBinding(MaterializedArtifact):
    path: Literal[
        "research/next-prep/artifacts/automatic-extraction-assessment/"
        "typed-extractor-v3-fresh-hidden-prereg-v1/preregistration.json"
    ] = relocation.NORMALIZED_PREREGISTRATION_PATH
    schema_version: Literal[
        "typed-extractor-fresh-v3-preregistration-v1"
    ] = relocation.PREREGISTRATION_SCHEMA


class ActiveReceiptBinding(MaterializedArtifact):
    path: Literal[
        "research/next-prep/artifacts/automatic-extraction-assessment/"
        "typed-extractor-v3-fresh-hidden-prereg-v1/"
        "authoring-implementation-receipt.json"
    ] = (
        "research/next-prep/artifacts/automatic-extraction-assessment/"
        "typed-extractor-v3-fresh-hidden-prereg-v1/"
        "authoring-implementation-receipt.json"
    )
    schema_version: Literal[
        "typed-extractor-fresh-v3-authoring-receipt-v2"
    ] = "typed-extractor-fresh-v3-authoring-receipt-v2"


class MaterializationSequence(StrictModel):
    active_receipt_transition_validated_before_staging: Literal[True] = True
    outputs_validated_before_atomic_publish: Literal[True] = True
    receipt_and_protected_state_revalidated_before_publish: Literal[True] = True
    model_runs_absent_at_publish: Literal[True] = True


class AutomaticWriteCounts(StrictModel):
    aggregate: Literal[0] = 0
    closure: Literal[0] = 0
    identity: Literal[0] = 0
    l1: Literal[0] = 0
    l2: Literal[0] = 0
    membership: Literal[0] = 0
    revision: Literal[0] = 0
    snapshot: Literal[0] = 0
    source_revision: Literal[0] = 0


class ActiveTransition(StrictModel):
    receipt: relocation.FreshV3SnapshotRelocationReceipt
    receipt_sha256: Literal[
        "c810f421d5a3b0726b862ec2f12c89e0d638e0747892637e2a32977587b7ef8c"
    ] = APPROVED_ACTIVE_RECEIPT_SHA256
    receipt_size_bytes: Literal[9370] = 9370
    materializer_sha256: dict[str, str]
    evaluation_root_absent: bool

    @model_validator(mode="after")
    def validate_materializer_registry(self) -> "ActiveTransition":
        if set(self.materializer_sha256) != set(MATERIALIZER_RELATIVE_PATHS):
            raise ValueError("materializer hash registry mismatch")
        if any(
            not authoring._is_sha256(value)
            for value in self.materializer_sha256.values()
        ):
            raise ValueError("invalid materializer hash")
        return self


class FreshV3MaterializationReceipt(StrictModel):
    schema_version: Literal[
        "typed-extractor-fresh-v3-materialization-receipt-v1"
    ] = "typed-extractor-fresh-v3-materialization-receipt-v1"
    status: Literal["frozen_pre_model"] = "frozen_pre_model"
    evaluation_id: Literal[
        "typed-extractor-v3-fresh-hidden-v1"
    ] = relocation.EVALUATION_ID
    evidence_kind: Literal[
        "git-relocation-receipt-plus-sha256"
    ] = "git-relocation-receipt-plus-sha256"
    trusted_timestamp_authority: Literal[False] = False
    materialization_time: str
    materialization_time_source: Literal[
        "caller_supplied_untrusted_utc_label"
    ] = "caller_supplied_untrusted_utc_label"
    logical_evaluation_root: Literal[
        "research/next-prep/artifacts/automatic-extraction-assessment/"
        "typed-extractor-v3-fresh-hidden-v1"
    ] = relocation.NORMALIZED_EVALUATION_ROOT
    preregistration: PreregistrationBinding
    active_authoring_receipt: ActiveReceiptBinding
    git_snapshot: relocation.GitSnapshotBinding
    materializer_sha256: dict[str, str]
    layers: dict[str, dict[str, MaterializedArtifact]]
    l1_case_count: Literal[24] = 24
    l2_case_count: Literal[18] = 18
    family_counts: dict[str, dict[str, int]]
    manifest_sha256: dict[str, str]
    sequence: MaterializationSequence = MaterializationSequence()
    hidden_source_artifacts_created: Literal[True] = True
    model_request_count: Literal[0] = 0
    evaluation_result_write_count: Literal[0] = 0
    automatic_write_counts: AutomaticWriteCounts = AutomaticWriteCounts()
    proposer_run_authorized: Literal[False] = False
    scoring_authorized: Literal[False] = False
    pipeline_integration_authorized: Literal[False] = False
    manual_identity_adjudications_materialized: Literal[False] = False
    embedding_authority: Literal[False] = False
    external_memory_systems_rerun: Literal[False] = False
    longmemeval_status: Literal[
        "structured_l2_identity_unresolved"
    ] = "structured_l2_identity_unresolved"

    @field_validator("materialization_time")
    @classmethod
    def validate_materialization_time(cls, value: str) -> str:
        return MaterializationTimeLabel(value=value).value

    @model_validator(mode="after")
    def validate_exact_contract(self) -> "FreshV3MaterializationReceipt":
        if set(self.materializer_sha256) != set(MATERIALIZER_RELATIVE_PATHS):
            raise ValueError("materializer hash registry mismatch")
        if set(self.layers) != set(LAYER_VALUES):
            raise ValueError("materialization layer registry mismatch")
        for layer, values in LAYER_VALUES.items():
            if set(self.layers[layer]) != set(values):
                raise ValueError(f"materialization artifact registry mismatch: {layer}")
        if self.family_counts != {
            "l1": L1_FAMILIES,
            "l2": L2_FAMILIES,
        }:
            raise ValueError("materialization family counts mismatch")
        if set(self.manifest_sha256) != {"l1", "l2"}:
            raise ValueError("materialization manifest registry mismatch")
        if any(
            not authoring._is_sha256(value)
            for value in (
                *self.materializer_sha256.values(),
                *self.manifest_sha256.values(),
            )
        ):
            raise ValueError("invalid materialization hash")
        if self.automatic_write_counts.model_dump() != ZERO_WRITES:
            raise ValueError("materialization write boundary mismatch")
        return self


def _read_approved_receipt(
    path: Path,
) -> tuple[
    relocation.FreshV3SnapshotRelocationReceipt,
    bytes,
    os.stat_result,
]:
    receipt, content, opened = relocation._read_snapshot_receipt(path)
    actual_sha256 = hashlib.sha256(content).hexdigest()
    if actual_sha256 != APPROVED_ACTIVE_RECEIPT_SHA256:
        raise ValueError(
            "approved active receipt hash drift: "
            f"expected {APPROVED_ACTIVE_RECEIPT_SHA256}, got {actual_sha256}"
        )
    return receipt, content, opened


def _bind_materializer_files(
    receipt: relocation.FreshV3SnapshotRelocationReceipt,
    workspace_root: Path,
) -> dict[str, str]:
    if receipt.materialization_workspace_paths != list(
        MATERIALIZER_RELATIVE_PATHS.values()
    ):
        raise ValueError("materialization path set mismatch")
    return {
        name: relocation._hash_regular_file(
            workspace_root / relative,
            label=f"fresh v3 materializer {name}",
        )
        for name, relative in MATERIALIZER_RELATIVE_PATHS.items()
    }


def _expected_authoring_binding(
    workspace_root: Path,
    preregistration_path: Path,
) -> relocation.PathNeutralAuthoringBinding:
    preregistration = authoring._load_preregistration(preregistration_path)
    bundle = authoring.build_fresh_v3_authoring_bundle(preregistration_path)
    return relocation.PathNeutralAuthoringBinding(
        code_sha256={
            name: relocation._hash_regular_file(
                path,
                label=f"authoring code {name}",
            )
            for name, path in authoring._code_paths(workspace_root).items()
        },
        dependency_sha256={
            name: relocation._hash_regular_file(
                path,
                label=f"authoring dependency {name}",
            )
            for name, path in authoring._dependency_paths(workspace_root).items()
        },
        blueprint_manifest_sha256={
            "l1": authoring._hash_value(
                [item.model_dump(mode="json") for item in bundle.l1.blueprints]
            ),
            "l2": authoring._hash_value(
                [item.model_dump(mode="json") for item in bundle.l2.blueprints]
            ),
        },
        prior_input_sha256=preregistration["input_sha256"],
        l1_families=dict(L1_FAMILIES),
        l2_families=dict(L2_FAMILIES),
    )


def _validate_active_receipt_transition(
    repository_root: Path,
    workspace_root: Path,
    *,
    require_evaluation_absent: bool,
) -> ActiveTransition:
    repository_root = relocation._require_repository_root(repository_root)
    workspace_root = relocation._require_workspace_root(
        repository_root,
        workspace_root,
    )
    preregistration_path = repository_root / relocation.NORMALIZED_PREREGISTRATION_PATH
    evaluation_root = repository_root / relocation.NORMALIZED_EVALUATION_ROOT
    receipt_path = preregistration_path.parent / relocation.RECEIPT_NAME
    receipt, receipt_bytes, opened_receipt = _read_approved_receipt(receipt_path)
    preregistration = authoring._load_preregistration(preregistration_path)

    expected_path_binding = relocation._validate_relocation_paths(
        preregistration=preregistration,
        repository_root=repository_root,
        workspace_root=workspace_root,
        evaluation_root=evaluation_root,
    )
    if receipt.path_binding != expected_path_binding:
        raise ValueError("active receipt relocation path drift")
    if receipt.git_snapshot != relocation._build_git_snapshot_binding(
        repository_root,
        workspace_root,
    ):
        raise ValueError("active receipt Git snapshot drift")

    preregistration_bytes, preregistration_stat = authoring._read_regular_path(
        preregistration_path,
        label="fresh v3 preregistration",
    )
    if hashlib.sha256(preregistration_bytes).hexdigest() != (
        relocation.PREREGISTRATION_SHA256
    ):
        raise ValueError("fresh v3 preregistration hash drift")
    if stat.S_IMODE(preregistration_stat.st_mode) != 0o444:
        raise ValueError("fresh v3 preregistration must have mode 0444")
    if receipt.authoring_binding != _expected_authoring_binding(
        workspace_root,
        preregistration_path,
    ):
        raise ValueError("active receipt authoring binding drift")

    relocation_hashes = {
        name: relocation._hash_regular_file(
            path,
            label=f"relocation code {name}",
        )
        for name, path in relocation._relocation_code_paths(workspace_root).items()
    }
    if receipt.relocation_code_sha256 != relocation_hashes:
        raise ValueError("active receipt relocation code drift")
    materializer_sha256 = _bind_materializer_files(receipt, workspace_root)

    protected_state = relocation._protected_state(workspace_root)
    if (
        receipt.candidate_v3_queue_sha256
        != authoring.CANDIDATE_QUEUE_SHA256
        or receipt.guard_fingerprint != relocation.GUARD_FINGERPRINT
        or receipt.guard_results_sha256
        != protected_state["guard_results_sha256"]
        or receipt.guard_counts != protected_state["guard_counts"]
    ):
        raise ValueError("active receipt protected state drift")
    evaluation_root_absent = not relocation._entry_exists(evaluation_root)
    if require_evaluation_absent and not evaluation_root_absent:
        raise ValueError("fresh v3 evaluation root must be absent")
    authoring._assert_path_matches_opened(
        receipt_path,
        opened_receipt,
        label="fresh v3 active relocation receipt",
    )
    return ActiveTransition(
        receipt=receipt,
        receipt_sha256=hashlib.sha256(receipt_bytes).hexdigest(),
        receipt_size_bytes=len(receipt_bytes),
        materializer_sha256=materializer_sha256,
        evaluation_root_absent=evaluation_root_absent,
    )


def _artifact(path: Path, *, label: str) -> MaterializedArtifact:
    content, opened = authoring._read_regular_path(path, label=label)
    if stat.S_IMODE(opened.st_mode) != 0o444:
        raise ValueError(f"{label} must have mode 0444")
    return MaterializedArtifact(
        sha256=hashlib.sha256(content).hexdigest(),
        size_bytes=len(content),
    )


def _layer_payloads(bundle: Any) -> dict[str, dict[str, Any]]:
    return {
        layer: {
            name: getattr(getattr(bundle, layer), attribute)
            for name, attribute in values.items()
        }
        for layer, values in LAYER_VALUES.items()
    }


def _build_materialization_receipt(
    *,
    preregistration_path: Path,
    artifact_root: Path,
    transition: ActiveTransition,
    materialization_time: str,
) -> FreshV3MaterializationReceipt:
    MaterializationTimeLabel(value=materialization_time)
    preregistration = _artifact(
        preregistration_path,
        label="fresh v3 preregistration",
    )
    layers = {
        layer: {
            name: _artifact(
                artifact_root / layer / name,
                label=f"fresh v3 {layer} {name}",
            )
            for name in names
        }
        for layer, names in LAYER_VALUES.items()
    }
    return FreshV3MaterializationReceipt(
        materialization_time=materialization_time,
        preregistration=PreregistrationBinding(
            sha256=preregistration.sha256,
            size_bytes=preregistration.size_bytes,
        ),
        active_authoring_receipt=ActiveReceiptBinding(
            sha256=transition.receipt_sha256,
            size_bytes=transition.receipt_size_bytes,
        ),
        git_snapshot=transition.receipt.git_snapshot,
        materializer_sha256=transition.materializer_sha256,
        layers=layers,
        family_counts={"l1": dict(L1_FAMILIES), "l2": dict(L2_FAMILIES)},
        manifest_sha256={
            "l1": layers["l1"]["manifest-l1.json"].sha256,
            "l2": layers["l2"]["manifest-l2.json"].sha256,
        },
    )
