from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from tools.natural_memory_benchmark import (
    typed_extractor_fresh_v2_materialization as materialization_module,
)
from tools.natural_memory_benchmark.io import (
    canonical_json_bytes,
    load_json,
    sha256_file,
)
from tools.natural_memory_benchmark.typed_extractor_fresh_v2_authoring import (
    build_fresh_v2_authoring_bundle,
    freeze_fresh_v2_authoring_supersession_receipt,
)
from tools.natural_memory_benchmark.typed_extractor_fresh_v2_materialization import (
    materialize_fresh_v2_hidden,
    validate_fresh_v2_hidden_materialization,
)


WORKSPACE = Path(".")
OFFICIAL_PREREGISTRATION = Path(
    "artifacts/automatic-extraction-assessment/"
    "typed-extractor-v2-fresh-hidden-prereg-v3/preregistration.json"
)
OFFICIAL_PREDECESSOR = OFFICIAL_PREREGISTRATION.parent / (
    "authoring-implementation-receipt.json"
)
RECEIPT_TIME = "2026-07-29T00:30:16Z"
MATERIALIZATION_TIME = "2026-07-29T01:00:00Z"
LAYER_NAMES = {
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


def _prepared_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path]:
    preregistration = tmp_path / "prereg" / "preregistration.json"
    preregistration.parent.mkdir(parents=True)
    shutil.copyfile(OFFICIAL_PREREGISTRATION, preregistration)
    preregistration.chmod(0o444)
    predecessor = preregistration.parent / OFFICIAL_PREDECESSOR.name
    shutil.copyfile(OFFICIAL_PREDECESSOR, predecessor)
    predecessor.chmod(0o444)
    evaluation_root = tmp_path / "typed-extractor-v2-fresh-hidden-v2"
    freeze_fresh_v2_authoring_supersession_receipt(
        preregistration,
        evaluation_root,
        WORKSPACE,
        RECEIPT_TIME,
    )
    receipt_path = preregistration.parent / "authoring-implementation-receipt-v2.json"
    monkeypatch.setattr(
        materialization_module,
        "APPROVED_ACTIVE_RECEIPT_SHA256",
        sha256_file(receipt_path),
        raising=False,
    )
    return preregistration, evaluation_root


def _expected_payloads(preregistration: Path) -> dict[str, dict[str, Any]]:
    bundle = build_fresh_v2_authoring_bundle(preregistration)
    return {
        layer: {
            name: getattr(getattr(bundle, layer), attribute)
            for name, attribute in names.items()
        }
        for layer, names in LAYER_NAMES.items()
    }


def _rewrite_json(path: Path, payload: dict[str, Any]) -> None:
    path.chmod(0o644)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n",
        encoding="utf-8",
    )
    path.chmod(0o444)


def test_materializes_exact_read_only_bundle_and_hash_chronology(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    preregistration, evaluation_root = _prepared_paths(tmp_path, monkeypatch)
    expected = _expected_payloads(preregistration)

    result = materialize_fresh_v2_hidden(
        preregistration,
        evaluation_root,
        WORKSPACE,
        MATERIALIZATION_TIME,
    )

    assert result == {
        "status": "valid",
        "evaluation_id": "typed-extractor-v2-fresh-hidden-v2",
        "l1_case_count": 24,
        "l2_case_count": 12,
        "model_runs_present_at_freeze": False,
    }
    assert evaluation_root.stat().st_mode & 0o777 == 0o775
    for layer, names in LAYER_NAMES.items():
        layer_root = evaluation_root / layer
        assert layer_root.stat().st_mode & 0o777 == 0o775
        assert {path.name for path in layer_root.iterdir()} == set(names)
        assert not (layer_root / "model-runs").exists()
        for name, expected_payload in expected[layer].items():
            path = layer_root / name
            assert path.read_bytes() == canonical_json_bytes(expected_payload)
            assert path.stat().st_mode & 0o777 == 0o444

    chronology_path = evaluation_root / "chronology-receipt.json"
    chronology = load_json(chronology_path)
    assert chronology_path.stat().st_mode & 0o777 == 0o444
    assert chronology["schema_version"] == (
        "typed-extractor-fresh-v2-materialization-receipt-v1"
    )
    assert chronology["status"] == "frozen_pre_model"
    assert chronology["materialization_time"] == MATERIALIZATION_TIME
    assert chronology["active_authoring_receipt"]["schema_version"] == (
        "typed-extractor-fresh-v2-authoring-receipt-v2"
    )
    assert chronology["sequence"] == {
        "active_receipt_validated_before_staging": True,
        "model_runs_absent_at_publish": True,
        "outputs_validated_before_atomic_publish": True,
    }
    assert sum(chronology["automatic_write_counts"].values()) == 0
    assert validate_fresh_v2_hidden_materialization(
        preregistration,
        evaluation_root,
        WORKSPACE,
    ) == result


def test_materialization_refuses_existing_root_and_second_publish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    preregistration, evaluation_root = _prepared_paths(tmp_path, monkeypatch)
    evaluation_root.mkdir()

    with pytest.raises(ValueError, match="formal evaluation root must be absent"):
        materialize_fresh_v2_hidden(
            preregistration,
            evaluation_root,
            WORKSPACE,
            MATERIALIZATION_TIME,
        )

    evaluation_root.rmdir()
    materialize_fresh_v2_hidden(
        preregistration,
        evaluation_root,
        WORKSPACE,
        MATERIALIZATION_TIME,
    )
    with pytest.raises(ValueError, match="formal evaluation root must be absent"):
        materialize_fresh_v2_hidden(
            preregistration,
            evaluation_root,
            WORKSPACE,
            MATERIALIZATION_TIME,
        )


@pytest.mark.parametrize("receipt_state", ["missing", "writable", "modified"])
def test_materialization_rejects_invalid_active_receipt_before_staging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    receipt_state: str,
) -> None:
    preregistration, evaluation_root = _prepared_paths(tmp_path, monkeypatch)
    receipt_path = preregistration.parent / "authoring-implementation-receipt-v2.json"
    if receipt_state == "missing":
        receipt_path.unlink()
    elif receipt_state == "writable":
        receipt_path.chmod(0o644)
    else:
        payload = load_json(receipt_path)
        payload["code_sha256"]["module"] = "0" * 64
        _rewrite_json(receipt_path, payload)

    with pytest.raises((ValueError, FileNotFoundError)):
        materialize_fresh_v2_hidden(
            preregistration,
            evaluation_root,
            WORKSPACE,
            MATERIALIZATION_TIME,
        )
    assert not evaluation_root.exists()
    assert not list(tmp_path.glob(f".{evaluation_root.name}.staging-*"))


@pytest.mark.parametrize(
    "materialization_time",
    ["2026-07-29T25:00:00Z", "2026-07-29T09:00:00+08:00"],
)
def test_materialization_rejects_invalid_utc_label(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    materialization_time: str,
) -> None:
    preregistration, evaluation_root = _prepared_paths(tmp_path, monkeypatch)

    with pytest.raises(ValidationError, match="valid UTC timestamp"):
        materialize_fresh_v2_hidden(
            preregistration,
            evaluation_root,
            WORKSPACE,
            materialization_time,
        )
    assert not evaluation_root.exists()


def test_atomic_publish_failure_cleans_only_staging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    preregistration, evaluation_root = _prepared_paths(tmp_path, monkeypatch)

    def fail_publish(source: Path, target: Path) -> None:
        raise OSError(f"injected publish failure: {source} -> {target}")

    monkeypatch.setattr(
        materialization_module,
        "_publish_noreplace",
        fail_publish,
        raising=False,
    )
    with pytest.raises(OSError, match="injected publish failure"):
        materialize_fresh_v2_hidden(
            preregistration,
            evaluation_root,
            WORKSPACE,
            MATERIALIZATION_TIME,
        )

    assert not evaluation_root.exists()
    assert not list(tmp_path.glob(f".{evaluation_root.name}.staging-*"))


def test_materialization_rejects_coherently_regenerated_active_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    preregistration, evaluation_root = _prepared_paths(tmp_path, monkeypatch)
    receipt_path = preregistration.parent / "authoring-implementation-receipt-v2.json"
    approved_sha256 = sha256_file(receipt_path)
    receipt_path.unlink()
    freeze_fresh_v2_authoring_supersession_receipt(
        preregistration,
        evaluation_root,
        WORKSPACE,
        "2026-07-29T00:30:17Z",
    )
    assert sha256_file(receipt_path) != approved_sha256

    with pytest.raises(ValueError, match="approved active authoring receipt hash drift"):
        materialize_fresh_v2_hidden(
            preregistration,
            evaluation_root,
            WORKSPACE,
            MATERIALIZATION_TIME,
        )

    assert not evaluation_root.exists()
    assert not list(tmp_path.glob(f".{evaluation_root.name}.staging-*"))


def test_atomic_publish_refuses_concurrently_created_empty_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    preregistration, evaluation_root = _prepared_paths(tmp_path, monkeypatch)
    current_publish = getattr(materialization_module, "_publish_noreplace", Path.replace)

    def create_target_then_publish(source: Path, target: Path) -> None:
        target.mkdir()
        current_publish(source, target)

    monkeypatch.setattr(
        materialization_module,
        "_publish_noreplace",
        create_target_then_publish,
        raising=False,
    )

    with pytest.raises(FileExistsError, match="formal evaluation root already exists"):
        materialize_fresh_v2_hidden(
            preregistration,
            evaluation_root,
            WORKSPACE,
            MATERIALIZATION_TIME,
        )

    assert evaluation_root.is_dir()
    assert not list(evaluation_root.iterdir())
    assert not list(tmp_path.glob(f".{evaluation_root.name}.staging-*"))


@pytest.mark.parametrize("drift", ["mode", "payload", "chronology"])
def test_validation_rejects_materialized_artifact_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    drift: str,
) -> None:
    preregistration, evaluation_root = _prepared_paths(tmp_path, monkeypatch)
    materialize_fresh_v2_hidden(
        preregistration,
        evaluation_root,
        WORKSPACE,
        MATERIALIZATION_TIME,
    )

    if drift == "mode":
        (evaluation_root / "l1" / "public-l1.json").chmod(0o644)
    elif drift == "payload":
        path = evaluation_root / "l2" / "manifest-l2.json"
        payload = load_json(path)
        payload["case_count"] = 11
        _rewrite_json(path, payload)
    else:
        path = evaluation_root / "chronology-receipt.json"
        payload = load_json(path)
        payload["materializer_sha256"]["module"] = "f" * 64
        _rewrite_json(path, payload)

    with pytest.raises((ValueError, ValidationError), match="drift|mode|read-only"):
        validate_fresh_v2_hidden_materialization(
            preregistration,
            evaluation_root,
            WORKSPACE,
        )


def test_validation_rejects_model_run_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    preregistration, evaluation_root = _prepared_paths(tmp_path, monkeypatch)
    materialize_fresh_v2_hidden(
        preregistration,
        evaluation_root,
        WORKSPACE,
        MATERIALIZATION_TIME,
    )
    (evaluation_root / "l1" / "model-runs").mkdir()

    with pytest.raises(ValueError, match="model runs must be absent"):
        validate_fresh_v2_hidden_materialization(
            preregistration,
            evaluation_root,
            WORKSPACE,
        )


def test_validation_rejects_unregistered_root_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    preregistration, evaluation_root = _prepared_paths(tmp_path, monkeypatch)
    materialize_fresh_v2_hidden(
        preregistration,
        evaluation_root,
        WORKSPACE,
        MATERIALIZATION_TIME,
    )
    (evaluation_root / "model-runs").mkdir()

    with pytest.raises(ValueError, match="root artifact set drift"):
        validate_fresh_v2_hidden_materialization(
            preregistration,
            evaluation_root,
            WORKSPACE,
        )
