from __future__ import annotations

import hashlib
import ctypes
import errno
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from . import typed_extractor_fresh_v2_authoring as authoring_module
from .io import canonical_json_bytes, load_json, sha256_file, write_json_immutable
from .typed_extractor_fresh_v2_authoring import (
    AuthoringSupersessionReceipt,
    DATASET_ID,
    L1_FAMILIES,
    L2_FAMILIES,
    NAMESPACE,
    RECEIPT_NAME,
    SUPERSESSION_REASON,
    SUPERSESSION_RECEIPT_NAME,
    SUPERSEDED_RECEIPT_SHA256,
    build_fresh_v2_authoring_bundle,
    validate_fresh_v2_active_authoring_receipt,
    validate_fresh_v2_authoring_bundle,
)


TEST_RELATIVE_PATH = Path(
    "tests/natural_memory_benchmark/"
    "test_typed_extractor_fresh_v2_materialization.py"
)
AUTHORING_TEST_RELATIVE_PATH = Path(
    "tests/natural_memory_benchmark/test_typed_extractor_fresh_v2_authoring.py"
)
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
APPROVED_ACTIVE_RECEIPT_SHA256 = (
    "4ce77c20c2941a66c3e74c1bd561e9d5ceee360a3723b75eed694fc47267c94b"
)
_AT_FDCWD = -100
_RENAME_NOREPLACE = 1


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
    mode: Literal["0444"] = "0444"


class PreregistrationBinding(MaterializedArtifact):
    path: str = Field(min_length=1)
    schema_version: Literal[
        "typed-extractor-fresh-v2-preregistration-v2"
    ] = "typed-extractor-fresh-v2-preregistration-v2"


class ActiveAuthoringReceiptBinding(MaterializedArtifact):
    path: str = Field(min_length=1)
    schema_version: Literal[
        "typed-extractor-fresh-v2-authoring-receipt-v2"
    ] = "typed-extractor-fresh-v2-authoring-receipt-v2"
    supersedes_receipt_sha256: Literal[SUPERSEDED_RECEIPT_SHA256] = (
        SUPERSEDED_RECEIPT_SHA256
    )
    supersession_reason: Literal[SUPERSESSION_REASON] = SUPERSESSION_REASON


class MaterializationSequence(StrictModel):
    active_receipt_validated_before_staging: Literal[True] = True
    outputs_validated_before_atomic_publish: Literal[True] = True
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


class FreshV2MaterializationReceipt(StrictModel):
    schema_version: Literal[
        "typed-extractor-fresh-v2-materialization-receipt-v1"
    ] = "typed-extractor-fresh-v2-materialization-receipt-v1"
    status: Literal["frozen_pre_model"] = "frozen_pre_model"
    evaluation_id: Literal[DATASET_ID] = DATASET_ID
    namespace: Literal[NAMESPACE] = NAMESPACE
    evidence_kind: Literal["active-receipt-plus-sha256"] = (
        "active-receipt-plus-sha256"
    )
    trusted_timestamp_authority: Literal[False] = False
    materialization_time: str
    materialization_time_source: Literal[
        "caller_supplied_untrusted_utc_label"
    ] = "caller_supplied_untrusted_utc_label"
    formal_evaluation_root: str = Field(min_length=1)
    preregistration: PreregistrationBinding
    active_authoring_receipt: ActiveAuthoringReceiptBinding
    materializer_sha256: dict[str, str]
    layers: dict[str, dict[str, MaterializedArtifact]]
    l1_case_count: Literal[24] = 24
    l2_case_count: Literal[12] = 12
    family_counts: dict[str, dict[str, int]]
    manifest_sha256: dict[str, str]
    sequence: MaterializationSequence = Field(
        default_factory=MaterializationSequence
    )
    model_runs_present_at_freeze: Literal[False] = False
    model_request_count: Literal[0] = 0
    automatic_write_counts: AutomaticWriteCounts = Field(
        default_factory=AutomaticWriteCounts
    )
    pipeline_integration_authorized: Literal[False] = False
    manual_identity_adjudications_materialized: Literal[False] = False
    embedding_authority: Literal[False] = False
    external_memory_systems_rerun: Literal[False] = False
    longmemeval_status: Literal["structured_l2_identity_unresolved"] = (
        "structured_l2_identity_unresolved"
    )

    @field_validator("materialization_time")
    @classmethod
    def validate_materialization_time(cls, value: str) -> str:
        return MaterializationTimeLabel(value=value).value

    @model_validator(mode="after")
    def validate_exact_contract(self) -> "FreshV2MaterializationReceipt":
        if set(self.layers) != set(LAYER_VALUES):
            raise ValueError("materialization layer set drift")
        for layer, names in LAYER_VALUES.items():
            if set(self.layers[layer]) != set(names):
                raise ValueError(f"materialization artifact set drift: {layer}")
        if self.family_counts != {"l1": L1_FAMILIES, "l2": L2_FAMILIES}:
            raise ValueError("materialization family counts drift")
        if set(self.materializer_sha256) != {"module", "test"}:
            raise ValueError("materializer hash set drift")
        if set(self.manifest_sha256) != {"l1", "l2"}:
            raise ValueError("materialization manifest hash set drift")
        hashes = [
            *self.materializer_sha256.values(),
            *self.manifest_sha256.values(),
        ]
        if any(
            len(value) != 64
            or any(c not in "0123456789abcdef" for c in value)
            for value in hashes
        ):
            raise ValueError("materialization contains an invalid hash")
        return self


def _require_mode(path: Path, expected: int, label: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"{label} missing: {path}")
    actual = path.stat().st_mode & 0o777
    if actual != expected:
        raise ValueError(f"{label} mode drift: expected {expected:04o}, got {actual:04o}")


def _require_approved_active_receipt(path: Path) -> None:
    actual = sha256_file(path)
    if actual != APPROVED_ACTIVE_RECEIPT_SHA256:
        raise ValueError(
            "approved active authoring receipt hash drift: "
            f"expected {APPROVED_ACTIVE_RECEIPT_SHA256}, got {actual}"
        )


def _publish_noreplace(source: Path, target: Path) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None:
        raise RuntimeError("renameat2 is required for no-clobber publication")
    renameat2.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    renameat2.restype = ctypes.c_int
    result = renameat2(
        _AT_FDCWD,
        os.fsencode(source),
        _AT_FDCWD,
        os.fsencode(target),
        _RENAME_NOREPLACE,
    )
    if result == 0:
        return
    error_number = ctypes.get_errno()
    if error_number == errno.EEXIST:
        raise FileExistsError(
            error_number,
            f"formal evaluation root already exists: {target}",
            str(target),
        )
    raise OSError(
        error_number,
        os.strerror(error_number),
        f"{source} -> {target}",
    )


def _materializer_paths(workspace_root: Path) -> dict[str, Path]:
    return {
        "module": Path(__file__).resolve(),
        "test": (workspace_root / TEST_RELATIVE_PATH).resolve(),
    }


def _authoring_binding_paths(workspace_root: Path) -> tuple[dict[str, Path], dict[str, Path]]:
    root = workspace_root / "tools/natural_memory_benchmark"
    code = {
        "module": Path(authoring_module.__file__).resolve(),
        "test": (workspace_root / AUTHORING_TEST_RELATIVE_PATH).resolve(),
    }
    dependencies = {
        "io.py": root / "io.py",
        "typed_extractor_fresh_v2_prereg.py": root
        / "typed_extractor_fresh_v2_prereg.py",
        "typed_extractor_l1.py": root / "typed_extractor_l1.py",
        "typed_extractor_l2.py": root / "typed_extractor_l2.py",
    }
    return code, dependencies


def _hash_value(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _validate_active_receipt_after_materialization(
    preregistration_path: Path,
    official_evaluation_root: Path,
    workspace_root: Path,
) -> tuple[Path, AuthoringSupersessionReceipt]:
    receipt_path = preregistration_path.parent / SUPERSESSION_RECEIPT_NAME
    _require_mode(receipt_path, 0o444, "active authoring receipt")
    _require_approved_active_receipt(receipt_path)
    receipt = AuthoringSupersessionReceipt.model_validate(load_json(receipt_path))
    if receipt.preregistration_path != str(preregistration_path.resolve()):
        raise ValueError("active authoring receipt preregistration path drift")
    if receipt.formal_evaluation_root != str(official_evaluation_root.resolve()):
        raise ValueError("active authoring receipt evaluation path drift")
    predecessor = preregistration_path.parent / RECEIPT_NAME
    _require_mode(predecessor, 0o444, "superseded authoring receipt")
    if sha256_file(predecessor) != SUPERSEDED_RECEIPT_SHA256:
        raise ValueError("superseded authoring receipt hash drift")
    code, dependencies = _authoring_binding_paths(workspace_root)
    expected_code = {name: sha256_file(path) for name, path in code.items()}
    expected_dependencies = {
        name: sha256_file(path) for name, path in dependencies.items()
    }
    if receipt.code_sha256 != expected_code:
        raise ValueError("active authoring receipt code drift")
    if receipt.dependency_sha256 != expected_dependencies:
        raise ValueError("active authoring receipt dependency drift")
    return receipt_path, receipt


def _layer_payloads(bundle: Any) -> dict[str, dict[str, Any]]:
    return {
        layer: {
            name: getattr(getattr(bundle, layer), attribute)
            for name, attribute in names.items()
        }
        for layer, names in LAYER_VALUES.items()
    }


def _write_layer_payloads(root: Path, payloads: dict[str, dict[str, Any]]) -> None:
    for layer, values in payloads.items():
        layer_root = root / layer
        layer_root.mkdir(parents=True)
        for name, value in values.items():
            path = layer_root / name
            write_json_immutable(path, value)
            path.chmod(0o444)
        layer_root.chmod(0o775)


def _artifact(path: Path, label: str) -> MaterializedArtifact:
    if not path.is_file():
        raise FileNotFoundError(f"{label} missing: {path}")
    _require_mode(path, 0o444, label)
    return MaterializedArtifact(sha256=sha256_file(path))


def _build_materialization_receipt(
    *,
    preregistration_path: Path,
    artifact_root: Path,
    official_evaluation_root: Path,
    workspace_root: Path,
    materialization_time: str,
    active_receipt_path: Path,
    active_receipt: AuthoringSupersessionReceipt,
) -> FreshV2MaterializationReceipt:
    layers = {
        layer: {
            name: _artifact(artifact_root / layer / name, f"fresh v2 {layer} {name}")
            for name in names
        }
        for layer, names in LAYER_VALUES.items()
    }
    materializer_paths = _materializer_paths(workspace_root)
    for label, path in materializer_paths.items():
        if not path.is_file():
            raise FileNotFoundError(f"materializer {label} missing: {path}")
    return FreshV2MaterializationReceipt(
        materialization_time=materialization_time,
        formal_evaluation_root=str(official_evaluation_root.resolve()),
        preregistration=PreregistrationBinding(
            path=str(preregistration_path.resolve()),
            sha256=sha256_file(preregistration_path),
        ),
        active_authoring_receipt=ActiveAuthoringReceiptBinding(
            path=str(active_receipt_path.resolve()),
            sha256=sha256_file(active_receipt_path),
            supersedes_receipt_sha256=active_receipt.supersedes_receipt_sha256,
            supersession_reason=active_receipt.supersession_reason,
        ),
        materializer_sha256={
            label: sha256_file(path) for label, path in materializer_paths.items()
        },
        layers=layers,
        family_counts=active_receipt.family_counts,
        manifest_sha256={
            layer: layers[layer][f"manifest-{layer}.json"].sha256
            for layer in LAYER_VALUES
        },
    )


def _validate_materialized_root(
    *,
    preregistration_path: Path,
    artifact_root: Path,
    official_evaluation_root: Path,
    workspace_root: Path,
) -> dict[str, Any]:
    if not artifact_root.is_dir():
        raise FileNotFoundError(f"formal evaluation root missing: {artifact_root}")
    _require_mode(artifact_root, 0o775, "formal evaluation root")
    if {path.name for path in artifact_root.iterdir()} != {
        "chronology-receipt.json",
        "l1",
        "l2",
    }:
        raise ValueError("materialization root artifact set drift")
    _require_mode(preregistration_path, 0o444, "fresh v2 preregistration")
    active_path, active_receipt = _validate_active_receipt_after_materialization(
        preregistration_path,
        official_evaluation_root,
        workspace_root,
    )
    bundle = build_fresh_v2_authoring_bundle(preregistration_path)
    validation = validate_fresh_v2_authoring_bundle(bundle, preregistration_path)
    if validation["l1_case_count"] != 24 or validation["l2_case_count"] != 12:
        raise ValueError("materialization case count drift")
    blueprint_hashes = {
        "l1": _hash_value(
            [item.model_dump(mode="json") for item in bundle.l1.blueprints]
        ),
        "l2": _hash_value(
            [item.model_dump(mode="json") for item in bundle.l2.blueprints]
        ),
    }
    if active_receipt.blueprint_manifest_sha256 != blueprint_hashes:
        raise ValueError("active authoring receipt blueprint drift")
    expected_payloads = _layer_payloads(bundle)
    for layer, values in expected_payloads.items():
        layer_root = artifact_root / layer
        _require_mode(layer_root, 0o775, f"fresh v2 {layer} directory")
        if (layer_root / "model-runs").exists():
            raise ValueError("model runs must be absent from fresh v2 materialization")
        if {path.name for path in layer_root.iterdir()} != set(values):
            raise ValueError(f"materialization artifact set drift: {layer}")
        for name, expected in values.items():
            path = layer_root / name
            _require_mode(path, 0o444, f"fresh v2 {layer} {name}")
            if path.read_bytes() != canonical_json_bytes(expected):
                raise ValueError(f"materialization payload drift: {layer}/{name}")
    receipt_path = artifact_root / "chronology-receipt.json"
    _require_mode(receipt_path, 0o444, "fresh v2 chronology receipt")
    actual = FreshV2MaterializationReceipt.model_validate(load_json(receipt_path))
    expected_receipt = _build_materialization_receipt(
        preregistration_path=preregistration_path,
        artifact_root=artifact_root,
        official_evaluation_root=official_evaluation_root,
        workspace_root=workspace_root,
        materialization_time=actual.materialization_time,
        active_receipt_path=active_path,
        active_receipt=active_receipt,
    )
    if canonical_json_bytes(actual) != canonical_json_bytes(expected_receipt):
        raise ValueError("fresh v2 materialization chronology drift")
    return {
        "status": "valid",
        "evaluation_id": DATASET_ID,
        "l1_case_count": 24,
        "l2_case_count": 12,
        "model_runs_present_at_freeze": False,
    }


def materialize_fresh_v2_hidden(
    preregistration_path: Path,
    evaluation_root: Path,
    workspace_root: Path,
    materialization_time: str,
) -> dict[str, Any]:
    preregistration_path = preregistration_path.resolve()
    evaluation_root = evaluation_root.resolve()
    workspace_root = workspace_root.resolve()
    MaterializationTimeLabel(value=materialization_time)
    if evaluation_root.exists():
        raise ValueError(f"formal evaluation root must be absent: {evaluation_root}")
    if not evaluation_root.parent.is_dir():
        raise FileNotFoundError(
            f"formal evaluation parent missing: {evaluation_root.parent}"
        )
    active_path = preregistration_path.parent / SUPERSESSION_RECEIPT_NAME
    _require_mode(active_path, 0o444, "active authoring receipt")
    _require_approved_active_receipt(active_path)
    active_raw = validate_fresh_v2_active_authoring_receipt(
        preregistration_path,
        evaluation_root,
        workspace_root,
    )
    if active_raw.get("schema_version") != (
        "typed-extractor-fresh-v2-authoring-receipt-v2"
    ):
        raise ValueError("fresh v2 materialization requires active v2 receipt")
    active_receipt = AuthoringSupersessionReceipt.model_validate(active_raw)
    bundle = build_fresh_v2_authoring_bundle(preregistration_path)
    validate_fresh_v2_authoring_bundle(bundle, preregistration_path)
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{evaluation_root.name}.staging-",
            dir=evaluation_root.parent,
        )
    )
    try:
        _write_layer_payloads(staging, _layer_payloads(bundle))
        staging.chmod(0o775)
        receipt = _build_materialization_receipt(
            preregistration_path=preregistration_path,
            artifact_root=staging,
            official_evaluation_root=evaluation_root,
            workspace_root=workspace_root,
            materialization_time=materialization_time,
            active_receipt_path=active_path,
            active_receipt=active_receipt,
        )
        receipt_path = staging / "chronology-receipt.json"
        write_json_immutable(receipt_path, receipt)
        receipt_path.chmod(0o444)
        result = _validate_materialized_root(
            preregistration_path=preregistration_path,
            artifact_root=staging,
            official_evaluation_root=evaluation_root,
            workspace_root=workspace_root,
        )
        if evaluation_root.exists():
            raise ValueError(
                f"formal evaluation root must be absent: {evaluation_root}"
            )
        _publish_noreplace(staging, evaluation_root)
        return result
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise


def validate_fresh_v2_hidden_materialization(
    preregistration_path: Path,
    evaluation_root: Path,
    workspace_root: Path,
) -> dict[str, Any]:
    preregistration_path = preregistration_path.resolve()
    evaluation_root = evaluation_root.resolve()
    workspace_root = workspace_root.resolve()
    return _validate_materialized_root(
        preregistration_path=preregistration_path,
        artifact_root=evaluation_root,
        official_evaluation_root=evaluation_root,
        workspace_root=workspace_root,
    )
