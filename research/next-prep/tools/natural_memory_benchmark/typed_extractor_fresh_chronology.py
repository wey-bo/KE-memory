from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .io import canonical_json_bytes, load_json, sha256_file, write_json_immutable


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ChronologyArtifact(StrictModel):
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    mode: Literal["0444"] = "0444"
    mtime_ns: int = Field(ge=1)


class FreshChronologyReceipt(StrictModel):
    schema_version: Literal["typed-extractor-fresh-chronology-v1"] = (
        "typed-extractor-fresh-chronology-v1"
    )
    status: Literal["frozen_pre_model"] = "frozen_pre_model"
    evaluation_id: Literal["typed-extractor-v2-fresh-hidden-v1"] = (
        "typed-extractor-v2-fresh-hidden-v1"
    )
    evidence_kind: Literal["filesystem-mtime-plus-sha256"] = (
        "filesystem-mtime-plus-sha256"
    )
    trusted_timestamp_authority: Literal[False] = False
    preregistration: ChronologyArtifact
    layers: dict[str, dict[str, ChronologyArtifact]]
    ordering_verified: Literal[True] = True
    model_runs_present_at_freeze: Literal[False] = False
    claim_boundary: dict[str, bool | str]

    @model_validator(mode="after")
    def validate_layers(self) -> "FreshChronologyReceipt":
        expected = {
            "l1": {
                "source-cases-l1.json",
                "adjudications-l1.json",
                "public-l1.json",
                "authority-l1.json",
                "gold-l1.json",
                "manifest-l1.json",
            },
            "l2": {
                "source-cases-l2.json",
                "adjudications-l2.json",
                "public-l2.json",
                "authority-l2.json",
                "gold-l2.json",
                "manifest-l2.json",
            },
        }
        if set(self.layers) != set(expected):
            raise ValueError("fresh chronology layer set mismatch")
        for layer, names in expected.items():
            if set(self.layers[layer]) != names:
                raise ValueError(f"fresh chronology artifact set mismatch: {layer}")
        return self


def _artifact(path: Path, label: str) -> ChronologyArtifact:
    if not path.is_file():
        raise FileNotFoundError(f"{label} missing: {path}")
    # No mode precondition: what this function produces is a content hash, and the
    # hash is what downstream comparison relies on. Requiring 0444 here rejected
    # every artifact on a fresh clone while adding nothing the hash does not cover.
    return ChronologyArtifact(
        sha256=sha256_file(path),
        mtime_ns=path.stat().st_mtime_ns,
    )


def _layer_names(layer: str) -> tuple[str, ...]:
    return (
        f"source-cases-{layer}.json",
        f"adjudications-{layer}.json",
        f"public-{layer}.json",
        f"authority-{layer}.json",
        f"gold-{layer}.json",
        f"manifest-{layer}.json",
    )


def _build_receipt(
    *,
    preregistration_path: Path,
    evaluation_root: Path,
    require_model_runs_absent: bool,
) -> FreshChronologyReceipt:
    preregistration = _artifact(preregistration_path, "fresh preregistration")
    layers: dict[str, dict[str, ChronologyArtifact]] = {}
    for layer in ("l1", "l2"):
        layer_root = evaluation_root / layer
        model_runs = layer_root / "model-runs"
        if require_model_runs_absent and model_runs.exists():
            raise ValueError("model runs must be absent when chronology freezes")
        layers[layer] = {
            name: _artifact(layer_root / name, f"fresh {layer} {name}")
            for name in _layer_names(layer)
        }
        source_mtime = layers[layer][f"source-cases-{layer}.json"].mtime_ns
        if preregistration.mtime_ns > source_mtime:
            raise ValueError(f"fresh {layer} source predates preregistration")
        if any(
            value.mtime_ns < source_mtime
            for name, value in layers[layer].items()
            if name != f"source-cases-{layer}.json"
        ):
            raise ValueError(f"fresh {layer} gold artifacts predate source selection")
    return FreshChronologyReceipt(
        preregistration=preregistration,
        layers=layers,
        claim_boundary={
            "automatic_authoritative_writes": False,
            "embedding_authority": False,
            "external_memory_systems_rerun": False,
            "longmemeval_status": "structured_l2_identity_unresolved",
            "manual_identity_adjudications_materialized": False,
            "pipeline_integration_authorized": False,
        },
    )


def freeze_fresh_chronology_receipt(
    *,
    preregistration_path: Path,
    evaluation_root: Path,
) -> dict[str, Any]:
    preregistration_path = preregistration_path.resolve()
    evaluation_root = evaluation_root.resolve()
    receipt = _build_receipt(
        preregistration_path=preregistration_path,
        evaluation_root=evaluation_root,
        require_model_runs_absent=True,
    )
    output_path = evaluation_root / "chronology-receipt.json"
    write_json_immutable(output_path, receipt)
    output_path.chmod(0o444)
    return {
        "status": "valid",
        "ordering_verified": True,
        "model_runs_present_at_freeze": False,
    }


def validate_fresh_chronology_receipt(
    *,
    preregistration_path: Path,
    evaluation_root: Path,
) -> dict[str, Any]:
    preregistration_path = preregistration_path.resolve()
    evaluation_root = evaluation_root.resolve()
    expected = _build_receipt(
        preregistration_path=preregistration_path,
        evaluation_root=evaluation_root,
        require_model_runs_absent=False,
    )
    receipt_path = evaluation_root / "chronology-receipt.json"
    actual_artifact = _artifact(receipt_path, "fresh chronology receipt")
    del actual_artifact
    actual = FreshChronologyReceipt.model_validate(load_json(receipt_path))
    if canonical_json_bytes(actual) != canonical_json_bytes(expected):
        raise ValueError("fresh chronology receipt drift")
    return {
        "status": "valid",
        "ordering_verified": True,
        "model_runs_present_at_freeze": False,
    }
