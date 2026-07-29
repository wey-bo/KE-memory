from __future__ import annotations

from pathlib import Path

import pytest

from tools.natural_memory_benchmark.io import load_json
from tools.natural_memory_benchmark.typed_extractor_fresh_chronology import (
    freeze_fresh_chronology_receipt,
    validate_fresh_chronology_receipt,
)


L1_NAMES = (
    "source-cases-l1.json",
    "adjudications-l1.json",
    "public-l1.json",
    "authority-l1.json",
    "gold-l1.json",
    "manifest-l1.json",
)
L2_NAMES = tuple(name.replace("l1", "l2") for name in L1_NAMES)


def _artifacts(tmp_path: Path) -> tuple[Path, Path]:
    prereg = tmp_path / "preregistration.json"
    prereg.write_text("{}\n", encoding="utf-8")
    prereg.chmod(0o444)
    evaluation = tmp_path / "evaluation"
    for layer, names in (("l1", L1_NAMES), ("l2", L2_NAMES)):
        root = evaluation / layer
        root.mkdir(parents=True)
        for index, name in enumerate(names):
            path = root / name
            path.write_text(f"{layer}:{index}\n", encoding="utf-8")
            path.chmod(0o444)
    return prereg, evaluation


def test_freeze_chronology_binds_read_only_artifacts_before_model_runs(
    tmp_path: Path,
) -> None:
    prereg, evaluation = _artifacts(tmp_path)

    result = freeze_fresh_chronology_receipt(
        preregistration_path=prereg,
        evaluation_root=evaluation,
    )
    receipt_path = evaluation / "chronology-receipt.json"
    receipt = load_json(receipt_path)

    assert result["status"] == "valid"
    assert receipt["ordering_verified"] is True
    assert receipt["model_runs_present_at_freeze"] is False
    assert receipt["preregistration"]["mtime_ns"] <= receipt["layers"]["l1"][
        "source-cases-l1.json"
    ]["mtime_ns"]
    assert receipt["layers"]["l1"]["source-cases-l1.json"]["mtime_ns"] <= min(
        value["mtime_ns"]
        for name, value in receipt["layers"]["l1"].items()
        if name != "source-cases-l1.json"
    )
    assert receipt_path.stat().st_mode & 0o777 == 0o444

    (evaluation / "l1" / "model-runs").mkdir()
    assert validate_fresh_chronology_receipt(
        preregistration_path=prereg,
        evaluation_root=evaluation,
    )["status"] == "valid"


def test_freeze_chronology_rejects_existing_model_runs_or_mutable_inputs(
    tmp_path: Path,
) -> None:
    prereg, evaluation = _artifacts(tmp_path)
    (evaluation / "l2" / "model-runs").mkdir()

    with pytest.raises(ValueError, match="model runs must be absent"):
        freeze_fresh_chronology_receipt(
            preregistration_path=prereg,
            evaluation_root=evaluation,
        )

    (evaluation / "l2" / "model-runs").rmdir()
    (evaluation / "l1" / "public-l1.json").chmod(0o644)
    with pytest.raises(ValueError, match="must be read-only"):
        freeze_fresh_chronology_receipt(
            preregistration_path=prereg,
            evaluation_root=evaluation,
        )
