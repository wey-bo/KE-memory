from __future__ import annotations

import ctypes
import errno
import hashlib
import json
import os
import stat
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from . import typed_extractor_fresh_v3_authoring as authoring
from . import typed_extractor_fresh_v3_snapshot_receipt as relocation
from .io import canonical_json_bytes
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


def _active_receipt_registry_path(workspace_root: Path) -> Path:
    return (
        Path(workspace_root)
        / "artifacts"
        / "automatic-extraction-assessment"
        / "typed-extractor-v3-fresh-hidden-prereg-v2"
        / "active-receipt-registry.json"
    )


def _require_registered_source_binding(
    live: dict[str, str],
    *,
    workspace_root: Path,
    group: str,
    frozen: dict[str, str],
    label: str,
) -> None:
    """Check one source-binding set against the registered current version.

    Source bindings say which code produced the receipt, so the frozen receipt
    necessarily names the code as it stood then. Enforcing that against today's
    tree would forbid every later repair. With no registry present the original
    exact-match behaviour applies, so this cannot silently weaken a checkout that
    has not adopted versioning.
    """
    registry_path = _active_receipt_registry_path(workspace_root)
    if not registry_path.is_file():
        if live != frozen:
            raise ValueError(f"{label} drift")
        return
    registry = json.loads(registry_path.read_bytes())
    expected = registry["v2"][group]
    if live != expected:
        raise ValueError(
            f"{label} does not match the registered v2 bindings; register a new "
            "version rather than editing the frozen receipt"
        )


def _require_authoring_binding_matches(
    frozen: relocation.PathNeutralAuthoringBinding,
    live: relocation.PathNeutralAuthoringBinding,
    *,
    workspace_root: Path,
) -> None:
    """Compare the receipt's binding to the live one, by field and by version.

    Every semantic field must match exactly: blueprint manifests, families, case
    counts, prior inputs and the preregistration identity. Those describe *what
    was authored*, and a difference there is a real defect.

    The source-hash fields are different. They describe *which code produced the
    receipt*, and the v1 receipt necessarily names the code as it stood at receipt
    time. Requiring today's code to still match would make any later repair
    unrepresentable -- including the portable-immutability migration and two
    bindings that had already drifted at the reorganization baseline. So the
    source hashes are checked against the registered version set: v1 keeps its
    frozen bindings as history, and the current bindings must match v2's.
    """
    frozen_payload = frozen.model_dump(mode="json")
    live_payload = live.model_dump(mode="json")
    source_fields = {"code_sha256", "dependency_sha256"}

    for field in sorted(set(frozen_payload) | set(live_payload)):
        if field in source_fields:
            continue
        if frozen_payload.get(field) != live_payload.get(field):
            raise ValueError(f"active receipt authoring binding drift: {field}")

    for field, group in (
        ("code_sha256", "authoring_code"),
        ("dependency_sha256", "authoring_dependency"),
    ):
        _require_registered_source_binding(
            live_payload[field],
            workspace_root=workspace_root,
            group=group,
            frozen=frozen_payload[field],
            label=f"active receipt authoring {field}",
        )


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
    # The hash above is the guarantee. A mode check here would additionally
    # require 0444, which no fresh clone provides.
    _require_authoring_binding_matches(
        receipt.authoring_binding,
        _expected_authoring_binding(workspace_root, preregistration_path),
        workspace_root=workspace_root,
    )

    relocation_hashes = {
        name: relocation._hash_regular_file(
            path,
            label=f"relocation code {name}",
        )
        for name, path in relocation._relocation_code_paths(workspace_root).items()
    }
    # Same versioning as the authoring binding above: the receipt names the
    # relocation code that produced it, so current code is checked against the
    # registered v2 set rather than against v1's frozen history.
    _require_registered_source_binding(
        relocation_hashes,
        workspace_root=workspace_root,
        group="relocation_code",
        frozen=dict(receipt.relocation_code_sha256),
        label="active receipt relocation code",
    )
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
    """Measure a file this run just wrote and require it locally hardened.

    Mode is meaningful here: these are staging artifacts produced moments ago in
    this process, so 0444 describes the write rather than the last checkout.
    """
    content, opened = authoring._read_regular_path(path, label=label)
    if stat.S_IMODE(opened.st_mode) != 0o444:
        raise ValueError(f"{label} must have mode 0444")
    return MaterializedArtifact(
        sha256=hashlib.sha256(content).hexdigest(),
        size_bytes=len(content),
    )


def _committed_artifact(path: Path, *, label: str) -> MaterializedArtifact:
    """Measure a committed input without a mode precondition.

    Same measurement, no mode check: git does not preserve 0444, so requiring it
    on an input that arrives from a checkout fails on every fresh clone. The
    caller binds this artifact by content, which is the portable guarantee.
    """
    content, _ = authoring._read_regular_path(path, label=label)
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
    preregistration = _committed_artifact(
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


def _require_directory(
    path: Path,
    *,
    mode: int,
    label: str,
    descriptor_opened: os.stat_result | None = None,
) -> None:
    try:
        opened = path.lstat() if descriptor_opened is None else path.stat()
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"{label} missing: {path}") from exc
    if not stat.S_ISDIR(opened.st_mode):
        raise ValueError(f"{label} must be a directory")
    if descriptor_opened is not None and not _same_identity(
        opened,
        descriptor_opened,
    ):
        raise ValueError(f"{label} identity drift")
    actual_mode = stat.S_IMODE(opened.st_mode)
    if actual_mode != mode:
        raise ValueError(
            f"{label} mode drift: expected {mode:04o}, got {actual_mode:04o}"
        )


def _close_descriptor(descriptor: int) -> None:
    try:
        os.close(descriptor)
    except OSError:
        pass


def _write_layer_payloads(
    artifact_root_descriptor: int,
    payloads: dict[str, dict[str, Any]],
) -> None:
    for layer, values in payloads.items():
        os.mkdir(layer, mode=0o700, dir_fd=artifact_root_descriptor)
        layer_descriptor = _open_directory_at(artifact_root_descriptor, layer)
        try:
            for name, value in values.items():
                _write_json_at(layer_descriptor, name, value)
            os.fchmod(layer_descriptor, 0o775)
            os.fsync(layer_descriptor)
        finally:
            _close_descriptor(layer_descriptor)


def _write_json_at(
    parent_descriptor: int,
    name: str,
    value: Any,
) -> None:
    descriptor = os.open(
        name,
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | os.O_CLOEXEC
        | os.O_NOFOLLOW,
        0o600,
        dir_fd=parent_descriptor,
    )
    try:
        remaining = memoryview(canonical_json_bytes(value))
        while remaining:
            written = os.write(descriptor, remaining)
            if written == 0:
                raise OSError("fresh v3 staging write made no progress")
            remaining = remaining[written:]
        os.fchmod(descriptor, 0o444)
        os.fsync(descriptor)
    finally:
        _close_descriptor(descriptor)


def _descriptor_path(descriptor: int) -> Path:
    return Path("/proc/self/fd") / str(descriptor)


def _validate_materialized_root(
    *,
    repository_root: Path,
    workspace_root: Path,
    artifact_root: Path,
    logical_evaluation_root: Path,
    artifact_root_opened: os.stat_result | None = None,
) -> dict[str, Any]:
    repository_root = relocation._require_repository_root(repository_root)
    workspace_root = relocation._require_workspace_root(
        repository_root,
        workspace_root,
    )
    artifact_root = relocation._absolute_lexical_path(artifact_root)
    logical_evaluation_root = relocation._absolute_lexical_path(
        logical_evaluation_root
    )
    official_evaluation_root = repository_root / relocation.NORMALIZED_EVALUATION_ROOT
    if logical_evaluation_root != official_evaluation_root:
        raise ValueError("logical fresh v3 evaluation root path mismatch")

    _require_directory(
        artifact_root,
        mode=0o775,
        label="fresh v3 materialization root",
        descriptor_opened=artifact_root_opened,
    )
    if any(path.name == "model-runs" for path in artifact_root.rglob("model-runs")):
        raise ValueError("model runs must be absent from fresh v3 materialization")
    if {path.name for path in artifact_root.iterdir()} != {
        "chronology-receipt.json",
        "l1",
        "l2",
    }:
        raise ValueError("materialization root artifact set drift")

    transition = _validate_active_receipt_transition(
        repository_root,
        workspace_root,
        require_evaluation_absent=False,
    )
    preregistration_path = repository_root / relocation.NORMALIZED_PREREGISTRATION_PATH
    bundle = authoring.build_fresh_v3_authoring_bundle(preregistration_path)
    bundle_validation = authoring.validate_fresh_v3_authoring_bundle(
        bundle,
        preregistration_path,
    )
    if (
        bundle_validation["l1_case_count"] != 24
        or bundle_validation["l2_case_count"] != 18
        or bundle_validation["l1_family_counts"] != dict(L1_FAMILIES)
        or bundle_validation["l2_family_counts"] != dict(L2_FAMILIES)
    ):
        raise ValueError("materialization authored bundle count drift")

    expected_payloads = _layer_payloads(bundle)
    for layer, values in expected_payloads.items():
        layer_root = artifact_root / layer
        _require_directory(
            layer_root,
            mode=0o775,
            label=f"fresh v3 {layer} directory",
        )
        if {path.name for path in layer_root.iterdir()} != set(values):
            raise ValueError(f"materialization artifact set drift: {layer}")
        for name, expected in values.items():
            path = layer_root / name
            content, opened = authoring._read_regular_path(
                path,
                label=f"fresh v3 {layer} {name}",
            )
            if stat.S_IMODE(opened.st_mode) != 0o444:
                raise ValueError(f"fresh v3 {layer} {name} mode drift")
            if content != canonical_json_bytes(expected):
                raise ValueError(f"materialization payload drift: {layer}/{name}")

    chronology_path = artifact_root / "chronology-receipt.json"
    chronology_bytes, chronology_stat = authoring._read_regular_path(
        chronology_path,
        label="fresh v3 chronology receipt",
    )
    if stat.S_IMODE(chronology_stat.st_mode) != 0o444:
        raise ValueError("fresh v3 chronology receipt mode drift")
    chronology = FreshV3MaterializationReceipt.model_validate(
        json.loads(chronology_bytes),
        strict=True,
    )
    expected_chronology = _build_materialization_receipt(
        preregistration_path=preregistration_path,
        artifact_root=artifact_root,
        transition=transition,
        materialization_time=chronology.materialization_time,
    )
    if chronology_bytes != canonical_json_bytes(expected_chronology):
        raise ValueError("fresh v3 materialization chronology drift")
    return {
        "status": "valid",
        "evaluation_id": relocation.EVALUATION_ID,
        "l1_case_count": 24,
        "l2_case_count": 18,
        "model_runs_present_at_freeze": False,
        "model_request_count": 0,
    }


def _same_entry(
    current: os.stat_result,
    expected: os.stat_result,
) -> bool:
    if not _same_identity(current, expected) or (
        stat.S_IMODE(current.st_mode) != stat.S_IMODE(expected.st_mode)
    ):
        return False
    return not stat.S_ISREG(expected.st_mode) or current.st_size == expected.st_size


def _same_identity(
    current: os.stat_result,
    expected: os.stat_result,
) -> bool:
    return not (
        current.st_dev != expected.st_dev
        or current.st_ino != expected.st_ino
        or stat.S_IFMT(current.st_mode) != stat.S_IFMT(expected.st_mode)
    )


def _require_parent_path_identity(
    parent_descriptor: int,
    parent_path: Path,
) -> None:
    opened = os.fstat(parent_descriptor)
    try:
        current = os.stat(parent_path, follow_symlinks=False)
    except OSError as exc:
        raise ValueError("fresh v3 evaluation parent identity drift") from exc
    if not _same_identity(current, opened):
        raise ValueError("fresh v3 evaluation parent identity drift")


def _read_descriptor_bytes(
    descriptor: int,
    opened: os.stat_result,
) -> bytes:
    if not stat.S_ISREG(opened.st_mode):
        raise ValueError("materialization descriptor must be a regular file")
    chunks: list[bytes] = []
    offset = 0
    while offset < opened.st_size:
        chunk = os.pread(descriptor, opened.st_size - offset, offset)
        if not chunk:
            raise ValueError("materialization descriptor bytes changed")
        chunks.append(chunk)
        offset += len(chunk)
    return b"".join(chunks)


@dataclass(frozen=True)
class _BoundTreeEntry:
    label: str
    descriptor: int
    parent_descriptor: int
    name: str
    opened: os.stat_result
    required_type: int
    required_mode: int
    expected_bytes: bytes | None = None
    expected_children: frozenset[str] | None = None


class _BoundMaterializedTree:
    def __init__(self, entries: list[_BoundTreeEntry]) -> None:
        self.entries = entries

    @property
    def root_opened(self) -> os.stat_result:
        return self.entries[0].opened

    @staticmethod
    def _require_contract(
        entry: _BoundTreeEntry,
        opened: os.stat_result,
    ) -> None:
        if stat.S_IFMT(opened.st_mode) != entry.required_type:
            raise ValueError(
                f"fresh v3 staging required type drift: {entry.label}"
            )
        actual_mode = stat.S_IMODE(opened.st_mode)
        if actual_mode != entry.required_mode:
            raise ValueError(
                "fresh v3 staging required mode drift: "
                f"{entry.label}; expected {entry.required_mode:04o}, "
                f"got {actual_mode:04o}"
            )

    def _verify_entries(self, parent_descriptor: int, root_name: str) -> None:
        for index, entry in enumerate(self.entries):
            current_parent = parent_descriptor if index == 0 else entry.parent_descriptor
            current_name = root_name if index == 0 else entry.name
            try:
                current = os.stat(
                    current_name,
                    dir_fd=current_parent,
                    follow_symlinks=False,
                )
            except FileNotFoundError as exc:
                raise ValueError(
                    f"fresh v3 staging identity drift: {entry.label}"
                ) from exc
            descriptor_stat = os.fstat(entry.descriptor)
            self._require_contract(entry, entry.opened)
            self._require_contract(entry, current)
            self._require_contract(entry, descriptor_stat)
            if not _same_entry(current, entry.opened) or not _same_entry(
                descriptor_stat,
                entry.opened,
            ):
                raise ValueError(
                    f"fresh v3 staging identity drift: {entry.label}"
                )
            if entry.expected_children is not None and set(
                os.listdir(entry.descriptor)
            ) != set(entry.expected_children):
                raise ValueError(
                    f"fresh v3 staging artifact drift: {entry.label}"
                )
            if entry.expected_bytes is not None:
                actual = _read_descriptor_bytes(entry.descriptor, descriptor_stat)
                if actual != entry.expected_bytes:
                    raise ValueError(
                        f"fresh v3 staging artifact drift: {entry.label}"
                    )
                if not _same_entry(os.fstat(entry.descriptor), entry.opened):
                    raise ValueError(
                        f"fresh v3 staging identity drift: {entry.label}"
                    )

    def verify(
        self,
        parent_descriptor: int,
        root_name: str,
        *,
        synchronize: bool = False,
    ) -> None:
        self._verify_entries(parent_descriptor, root_name)
        if not synchronize:
            return
        for entry in self.entries:
            if entry.required_type == stat.S_IFREG:
                os.fsync(entry.descriptor)
        for entry in reversed(self.entries):
            if entry.required_type == stat.S_IFDIR:
                os.fsync(entry.descriptor)
        self._verify_entries(parent_descriptor, root_name)

    def close(self) -> None:
        for entry in reversed(self.entries):
            _close_descriptor(entry.descriptor)


def _close_bound_tree(bound_tree: _BoundMaterializedTree) -> None:
    try:
        bound_tree.close()
    except OSError:
        pass


def _open_directory_at(parent_descriptor: int, name: str) -> int:
    return os.open(
        name,
        os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
        dir_fd=parent_descriptor,
    )


def _open_regular_at(parent_descriptor: int, name: str) -> int:
    return os.open(
        name,
        os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC | os.O_NOFOLLOW,
        dir_fd=parent_descriptor,
    )


def _bind_materialized_tree(
    parent_descriptor: int,
    root_name: str,
    expected_files: dict[str, bytes],
) -> _BoundMaterializedTree:
    entries: list[_BoundTreeEntry] = []
    try:
        root_descriptor = _open_directory_at(parent_descriptor, root_name)
        entries.append(
            _BoundTreeEntry(
                label="root",
                descriptor=root_descriptor,
                parent_descriptor=parent_descriptor,
                name=root_name,
                opened=os.fstat(root_descriptor),
                required_type=stat.S_IFDIR,
                required_mode=0o775,
                expected_children=frozenset(
                    {"chronology-receipt.json", "l1", "l2"}
                ),
            )
        )
        chronology_descriptor = _open_regular_at(
            root_descriptor,
            "chronology-receipt.json",
        )
        entries.append(
            _BoundTreeEntry(
                label="chronology-receipt.json",
                descriptor=chronology_descriptor,
                parent_descriptor=root_descriptor,
                name="chronology-receipt.json",
                opened=os.fstat(chronology_descriptor),
                required_type=stat.S_IFREG,
                required_mode=0o444,
                expected_bytes=expected_files["chronology-receipt.json"],
            )
        )
        for layer, names in LAYER_VALUES.items():
            layer_descriptor = _open_directory_at(root_descriptor, layer)
            entries.append(
                _BoundTreeEntry(
                    label=layer,
                    descriptor=layer_descriptor,
                    parent_descriptor=root_descriptor,
                    name=layer,
                    opened=os.fstat(layer_descriptor),
                    required_type=stat.S_IFDIR,
                    required_mode=0o775,
                    expected_children=frozenset(names),
                )
            )
            for name in names:
                descriptor = _open_regular_at(layer_descriptor, name)
                entries.append(
                    _BoundTreeEntry(
                        label=f"{layer}/{name}",
                        descriptor=descriptor,
                        parent_descriptor=layer_descriptor,
                        name=name,
                        opened=os.fstat(descriptor),
                        required_type=stat.S_IFREG,
                        required_mode=0o444,
                        expected_bytes=expected_files[f"{layer}/{name}"],
                    )
                )
        bound = _BoundMaterializedTree(entries)
        bound.verify(parent_descriptor, root_name)
        return bound
    except Exception:
        for entry in reversed(entries):
            _close_descriptor(entry.descriptor)
        raise


def _publish_noreplace(
    parent_descriptor: int,
    source_name: str,
    target_name: str,
    bound_tree: _BoundMaterializedTree,
    target_display: Path,
) -> None:
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
    bound_tree.verify(
        parent_descriptor,
        source_name,
        synchronize=True,
    )
    os.fsync(parent_descriptor)
    result = renameat2(
        parent_descriptor,
        os.fsencode(source_name),
        parent_descriptor,
        os.fsencode(target_name),
        _RENAME_NOREPLACE,
    )
    if result == 0:
        os.fsync(parent_descriptor)
        published = os.stat(
            target_name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        if not _same_entry(published, bound_tree.root_opened):
            raise ValueError("fresh v3 published root identity drift")
        bound_tree.verify(parent_descriptor, target_name)
        return
    error_number = ctypes.get_errno()
    if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
        raise FileExistsError(
            error_number,
            f"fresh v3 evaluation root already exists: {target_display}",
            str(target_display),
        )
    raise OSError(
        error_number,
        os.strerror(error_number),
        f"{source_name} -> {target_name}",
    )


def _preserve_failed_staging_root(
    parent_descriptor: int,
    staging_name: str,
    expected: os.stat_result,
) -> None:
    try:
        root_descriptor = _open_directory_at(parent_descriptor, staging_name)
    except OSError:
        return
    try:
        try:
            opened = os.fstat(root_descriptor)
        except OSError:
            return
        if not _same_identity(opened, expected):
            return
        # Linux has no conditional unlink/rmdir-by-fd primitive. Preserve the
        # failed staging tree for audit rather than deleting replaceable names.
    finally:
        _close_descriptor(root_descriptor)


def _materialize_fresh_v3_hidden_to_root(
    repository_root: Path,
    workspace_root: Path,
    evaluation_root: Path,
    materialization_time: str,
) -> dict[str, Any]:
    repository_root = relocation._require_repository_root(repository_root)
    workspace_root = relocation._require_workspace_root(
        repository_root,
        workspace_root,
    )
    evaluation_root = relocation._absolute_lexical_path(evaluation_root)
    logical_evaluation_root = repository_root / relocation.NORMALIZED_EVALUATION_ROOT
    MaterializationTimeLabel(value=materialization_time)
    # The target root must be absent -- that is a live precondition and stays.
    if relocation._entry_exists(evaluation_root):
        raise ValueError(f"fresh v3 evaluation root must be absent: {evaluation_root}")
    if not evaluation_root.parent.is_dir():
        raise FileNotFoundError(
            f"fresh v3 evaluation parent missing: {evaluation_root.parent}"
        )

    # The transition's own absence check is about the *canonical* evaluation root,
    # which was committed as evidence after this code was written. Requiring it to
    # be absent asserts a precondition that only held before that commit, and it
    # would now block materializing to any other root. Required only when the
    # target *is* the canonical root, where the check is still meaningful.
    transition = _validate_active_receipt_transition(
        repository_root,
        workspace_root,
        require_evaluation_absent=evaluation_root == logical_evaluation_root,
    )
    preregistration_path = repository_root / relocation.NORMALIZED_PREREGISTRATION_PATH
    bundle = authoring.build_fresh_v3_authoring_bundle(preregistration_path)
    validation = authoring.validate_fresh_v3_authoring_bundle(
        bundle,
        preregistration_path,
    )
    if validation["l1_case_count"] != 24 or validation["l2_case_count"] != 18:
        raise ValueError("fresh v3 authoring bundle count drift")

    parent_descriptor = os.open(
        evaluation_root.parent,
        os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
    )
    staging_root: Path | None = None
    staging_descriptor: int | None = None
    staging_opened: os.stat_result | None = None
    try:
        _require_parent_path_identity(parent_descriptor, evaluation_root.parent)
        staging_name = Path(
            tempfile.mkdtemp(
                prefix=f".{evaluation_root.name}.staging-",
                dir=_descriptor_path(parent_descriptor),
            )
        ).name
        staging_descriptor = _open_directory_at(
            parent_descriptor,
            staging_name,
        )
        staging_opened = os.fstat(staging_descriptor)
        staging_root = evaluation_root.parent / staging_name
        _require_parent_path_identity(parent_descriptor, evaluation_root.parent)
        _write_layer_payloads(staging_descriptor, _layer_payloads(bundle))
        chronology = _build_materialization_receipt(
            preregistration_path=preregistration_path,
            artifact_root=staging_root,
            transition=transition,
            materialization_time=materialization_time,
        )
        _write_json_at(staging_descriptor, "chronology-receipt.json", chronology)
        os.fchmod(staging_descriptor, 0o775)
        os.fsync(staging_descriptor)

        result = _validate_materialized_root(
            repository_root=repository_root,
            workspace_root=workspace_root,
            artifact_root=staging_root,
            logical_evaluation_root=logical_evaluation_root,
            artifact_root_opened=staging_opened,
        )
        payloads = _layer_payloads(bundle)
        expected_files = {
            f"{layer}/{name}": canonical_json_bytes(value)
            for layer, values in payloads.items()
            for name, value in values.items()
        }
        expected_files["chronology-receipt.json"] = canonical_json_bytes(chronology)
        bound_tree = _bind_materialized_tree(
            parent_descriptor,
            staging_name,
            expected_files,
        )
        try:
            # Revalidated immediately before publication, so it must agree with
            # the first call: absence of the canonical root is only required when
            # that root is the publication target. Hardcoding True here would make
            # every non-canonical materialization impossible now that the official
            # evaluation root is committed evidence.
            _validate_active_receipt_transition(
                repository_root,
                workspace_root,
                require_evaluation_absent=evaluation_root == logical_evaluation_root,
            )
            revalidated = _validate_materialized_root(
                repository_root=repository_root,
                workspace_root=workspace_root,
                artifact_root=staging_root,
                logical_evaluation_root=logical_evaluation_root,
                artifact_root_opened=staging_opened,
            )
            if revalidated != result:
                raise ValueError("fresh v3 materialization validation result drift")
            if relocation._entry_exists(evaluation_root):
                raise ValueError(
                    f"fresh v3 evaluation root must be absent: {evaluation_root}"
                )
            _require_parent_path_identity(
                parent_descriptor,
                evaluation_root.parent,
            )
            _publish_noreplace(
                parent_descriptor,
                staging_name,
                evaluation_root.name,
                bound_tree,
                evaluation_root,
            )
            _require_parent_path_identity(
                parent_descriptor,
                evaluation_root.parent,
            )
            published = _validate_materialized_root(
                repository_root=repository_root,
                workspace_root=workspace_root,
                artifact_root=evaluation_root,
                logical_evaluation_root=logical_evaluation_root,
            )
            if published != revalidated:
                raise ValueError("fresh v3 post-publication validation result drift")
            bound_tree.verify(parent_descriptor, evaluation_root.name)
            _require_parent_path_identity(
                parent_descriptor,
                evaluation_root.parent,
            )
            return published
        finally:
            _close_bound_tree(bound_tree)
    except Exception:
        if staging_root is not None and staging_opened is not None:
            _preserve_failed_staging_root(
                parent_descriptor,
                staging_name,
                staging_opened,
            )
        raise
    finally:
        if staging_descriptor is not None:
            _close_descriptor(staging_descriptor)
        _close_descriptor(parent_descriptor)


def _require_exact_official_evaluation_root(
    repository_root: Path,
    evaluation_root: Path,
) -> Path:
    evaluation_root = relocation._absolute_lexical_path(evaluation_root)
    official = repository_root / relocation.NORMALIZED_EVALUATION_ROOT
    if evaluation_root != official:
        raise ValueError("fresh v3 requires the exact official evaluation root")
    return evaluation_root


def materialize_fresh_v3_hidden(
    repository_root: Path,
    workspace_root: Path,
    evaluation_root: Path,
    materialization_time: str,
) -> dict[str, Any]:
    repository_root = relocation._require_repository_root(repository_root)
    workspace_root = relocation._require_workspace_root(
        repository_root,
        workspace_root,
    )
    evaluation_root = _require_exact_official_evaluation_root(
        repository_root,
        evaluation_root,
    )
    return _materialize_fresh_v3_hidden_to_root(
        repository_root,
        workspace_root,
        evaluation_root,
        materialization_time,
    )


def validate_fresh_v3_hidden_materialization(
    repository_root: Path,
    workspace_root: Path,
    evaluation_root: Path,
) -> dict[str, Any]:
    repository_root = relocation._require_repository_root(repository_root)
    workspace_root = relocation._require_workspace_root(
        repository_root,
        workspace_root,
    )
    evaluation_root = _require_exact_official_evaluation_root(
        repository_root,
        evaluation_root,
    )
    return _validate_materialized_root(
        repository_root=repository_root,
        workspace_root=workspace_root,
        artifact_root=evaluation_root,
        logical_evaluation_root=(
            repository_root / relocation.NORMALIZED_EVALUATION_ROOT
        ),
    )
