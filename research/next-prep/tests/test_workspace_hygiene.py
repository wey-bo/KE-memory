from __future__ import annotations

import json
import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

import tools.workspace_hygiene as workspace_hygiene
from tools.workspace_hygiene import (
    apply_cleanup_plan,
    build_cleanup_plan,
    discover_cleanup_targets,
)


def _write(path: Path, content: bytes = b"x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _workspace(tmp_path: Path) -> Path:
    root = tmp_path / "workspace"
    for name in (".t", ".tmp", ".pytest_cache", ".pytest-tmp-old", "t", "t2"):
        _write(root / name / "payload.bin", name.encode("utf-8"))
    _write(root / "tmp" / "ontology-venv" / "payload.bin", b"ontology-venv")
    _write(root / "tmp" / "amr-pilot-sources" / "keep.bin", b"offline-source")
    _write(root / "tmp" / "ontology-model-cache" / "keep.bin", b"warm-cache")
    _write(root / "tmp" / "unknown-future-cache" / "keep.bin", b"unknown")
    for name in (
        "artifacts",
        "data",
        "docs",
        "knowledge-extraction",
        ".venv-dense",
        ".fastembed-cache",
    ):
        _write(root / name / "keep.bin", name.encode("utf-8"))
    _write(root / "artifacts" / ".t" / "nested.bin", b"nested")
    return root


def test_discovery_is_limited_to_allowlisted_top_level_directories(tmp_path):
    root = _workspace(tmp_path)

    targets = [path.relative_to(root).as_posix() for path in discover_cleanup_targets(root)]

    assert targets == [
        ".pytest-tmp-old",
        ".pytest_cache",
        ".t",
        ".tmp",
        "t",
        "t2",
        "tmp/ontology-venv",
    ]
    assert (root / "artifacts" / ".t" / "nested.bin").exists()
    assert (root / ".venv-dense" / "keep.bin").exists()
    assert (root / "tmp" / "amr-pilot-sources" / "keep.bin").exists()
    assert (root / "tmp" / "ontology-model-cache" / "keep.bin").exists()
    assert (root / "tmp" / "unknown-future-cache" / "keep.bin").exists()


def test_plan_is_deterministic_and_counts_only_cleanup_targets(tmp_path):
    root = _workspace(tmp_path)

    first = build_cleanup_plan(root, run_id="cleanup-v1")
    second = build_cleanup_plan(root, run_id="cleanup-v1")

    assert first == second
    assert first["core_impact"] == "none"
    assert first["target_count"] == 7
    assert first["removable_file_count"] == 7
    assert [item["path"] for item in first["targets"]][-1] == "tmp/ontology-venv"
    assert all(len(item["tree_sha256"]) == 64 for item in first["targets"])
    assert first["removable_bytes"] == sum(
        len(name.encode("utf-8"))
        for name in (
            ".t",
            ".tmp",
            ".pytest_cache",
            ".pytest-tmp-old",
            "t",
            "t2",
            "ontology-venv",
        )
    )
    assert "artifacts" in first["protected_roots_present"]
    assert ".venv-dense" in first["protected_roots_present"]


def test_apply_removes_exact_plan_and_preserves_protected_roots(tmp_path):
    root = _workspace(tmp_path)
    plan = build_cleanup_plan(root, run_id="cleanup-v1")

    report = apply_cleanup_plan(root, plan)

    assert report["status"] == "cleaned"
    assert report["removed_bytes"] == plan["removable_bytes"]
    assert report["remaining_target_count"] == 0
    assert not (root / ".t").exists()
    assert not (root / "tmp" / "ontology-venv").exists()
    assert (root / "tmp" / "amr-pilot-sources" / "keep.bin").exists()
    assert (root / "tmp" / "ontology-model-cache" / "keep.bin").exists()
    assert (root / "tmp" / "unknown-future-cache" / "keep.bin").exists()
    assert (root / "artifacts" / "keep.bin").exists()
    assert (root / "artifacts" / ".t" / "nested.bin").exists()
    assert (root / ".fastembed-cache" / "keep.bin").exists()


def test_apply_marks_report_incomplete_when_a_target_reappears(tmp_path, monkeypatch):
    root = _workspace(tmp_path)
    plan = build_cleanup_plan(root, run_id="cleanup-v1")
    real_discover = workspace_hygiene.discover_cleanup_targets
    discovery_calls = 0

    def discover_with_late_target(current_root):
        nonlocal discovery_calls
        discovery_calls += 1
        if discovery_calls == 1:
            return real_discover(current_root)
        return [Path(current_root) / ".pytest-tmp-late"]

    monkeypatch.setattr(
        workspace_hygiene,
        "discover_cleanup_targets",
        discover_with_late_target,
    )

    report = apply_cleanup_plan(root, plan)

    assert report["status"] == "incomplete"
    assert report["remaining_targets"] == [".pytest-tmp-late"]


def test_apply_rejects_target_drift(tmp_path):
    root = _workspace(tmp_path)
    plan = build_cleanup_plan(root, run_id="cleanup-v1")
    _write(root / ".t" / "late.bin", b"late")

    with pytest.raises(ValueError, match="target drift"):
        apply_cleanup_plan(root, plan)

    assert (root / ".t" / "late.bin").exists()


def test_apply_rejects_target_set_drift(tmp_path):
    root = _workspace(tmp_path)
    plan = build_cleanup_plan(root, run_id="cleanup-v1")
    _write(root / ".pytest-tmp-new" / "payload.bin", b"new-target")

    with pytest.raises(ValueError, match="target set drift"):
        apply_cleanup_plan(root, plan)

    assert (root / ".t" / "payload.bin").exists()


def test_apply_rejects_same_size_content_drift(tmp_path):
    root = _workspace(tmp_path)
    plan = build_cleanup_plan(root, run_id="cleanup-v1")
    (root / ".t" / "payload.bin").write_bytes(b"zz")

    with pytest.raises(ValueError, match="target drift"):
        apply_cleanup_plan(root, plan)

    assert (root / ".t" / "payload.bin").exists()


def test_apply_rejects_missing_required_plan_fields_before_deletion(tmp_path):
    root = _workspace(tmp_path)
    plan = build_cleanup_plan(root, run_id="cleanup-v1")
    plan.pop("run_id")

    with pytest.raises(ValueError, match="run_id"):
        apply_cleanup_plan(root, plan)

    assert (root / ".t" / "payload.bin").exists()


def test_apply_rejects_non_allowlisted_target(tmp_path):
    root = _workspace(tmp_path)
    plan = build_cleanup_plan(root, run_id="cleanup-v1")
    plan["targets"].append(
        {
            "path": "artifacts",
            "file_count": 2,
            "bytes": 16,
            "reason": "tampered",
        }
    )
    plan["target_count"] += 1

    with pytest.raises(ValueError, match="not allowlisted"):
        apply_cleanup_plan(root, plan)

    assert (root / "artifacts" / "keep.bin").exists()


def test_apply_rejects_equivalent_duplicate_paths_before_deletion(tmp_path):
    root = _workspace(tmp_path)
    plan = build_cleanup_plan(root, run_id="cleanup-v1")
    duplicate = dict(plan["targets"][-1])
    duplicate["path"] = duplicate["path"].replace("/", "\\")
    plan["targets"].append(duplicate)
    plan["target_count"] += 1
    plan["removable_file_count"] += duplicate["file_count"]
    plan["removable_bytes"] += duplicate["bytes"]

    with pytest.raises(ValueError, match="canonical|duplicate"):
        apply_cleanup_plan(root, plan)

    assert (root / ".t" / "payload.bin").exists()
    assert (root / "tmp" / "ontology-venv" / "payload.bin").exists()


@pytest.mark.parametrize(
    "tampered_path",
    [
        "tmp/unknown-future-cache",
        "tmp/ontology-venv/nested",
    ],
)
def test_apply_rejects_non_allowlisted_nested_target(tmp_path, tampered_path):
    root = _workspace(tmp_path)
    _write(root / "tmp" / "ontology-venv" / "nested" / "payload.bin")
    plan = build_cleanup_plan(root, run_id="cleanup-v1")
    plan["targets"].append(
        {
            "path": tampered_path,
            "file_count": 1,
            "bytes": 1,
            "reason": "tampered",
        }
    )
    plan["target_count"] += 1

    with pytest.raises(ValueError, match="not allowlisted"):
        apply_cleanup_plan(root, plan)

    assert (root / tampered_path).exists()


def test_cli_inventory_and_clean_write_canonical_json(tmp_path):
    root = _workspace(tmp_path)
    plan_path = tmp_path / "plan.json"
    report_path = tmp_path / "report.json"

    inventory = subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.workspace_hygiene",
            "inventory",
            "--root",
            str(root),
            "--run-id",
            "cleanup-cli-v1",
            "--output",
            str(plan_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(inventory.stdout)["target_count"] == 7
    assert plan_path.read_bytes().endswith(b"\n")

    clean = subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.workspace_hygiene",
            "clean",
            "--root",
            str(root),
            "--plan",
            str(plan_path),
            "--output",
            str(report_path),
            "--expected-plan-sha256",
            hashlib.sha256(plan_path.read_bytes()).hexdigest(),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(clean.stdout)["status"] == "cleaned"
    assert json.loads(report_path.read_text(encoding="utf-8"))["remaining_target_count"] == 0


def test_cli_clean_rejects_wrong_plan_hash_before_deletion(tmp_path):
    root = _workspace(tmp_path)
    plan_path = tmp_path / "plan.json"
    report_path = tmp_path / "report.json"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.workspace_hygiene",
            "inventory",
            "--root",
            str(root),
            "--run-id",
            "cleanup-cli-v1",
            "--output",
            str(plan_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    clean = subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.workspace_hygiene",
            "clean",
            "--root",
            str(root),
            "--plan",
            str(plan_path),
            "--output",
            str(report_path),
            "--expected-plan-sha256",
            "0" * 64,
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert clean.returncode != 0
    assert "SHA-256 mismatch" in clean.stderr
    assert (root / ".t" / "payload.bin").exists()


@pytest.mark.parametrize("output_location", ["existing", "inside-target"])
def test_cli_clean_preflights_report_output_before_deletion(tmp_path, output_location):
    root = _workspace(tmp_path)
    plan_path = tmp_path / "plan.json"
    report_path = (
        tmp_path / "report.json"
        if output_location == "existing"
        else root / ".t" / "report.json"
    )
    subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.workspace_hygiene",
            "inventory",
            "--root",
            str(root),
            "--run-id",
            "cleanup-cli-v1",
            "--output",
            str(plan_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    if output_location == "existing":
        report_path.write_text("conflict", encoding="utf-8")

    clean = subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.workspace_hygiene",
            "clean",
            "--root",
            str(root),
            "--plan",
            str(plan_path),
            "--output",
            str(report_path),
            "--expected-plan-sha256",
            hashlib.sha256(plan_path.read_bytes()).hexdigest(),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert clean.returncode != 0
    assert "report output" in clean.stderr
    assert (root / ".t" / "payload.bin").exists()


def test_cleanup_file_persists_partial_failure_after_one_target_is_removed(
    tmp_path,
    monkeypatch,
):
    root = _workspace(tmp_path)
    plan_path = tmp_path / "plan.json"
    report_path = tmp_path / "report.json"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.workspace_hygiene",
            "inventory",
            "--root",
            str(root),
            "--run-id",
            "cleanup-cli-v1",
            "--output",
            str(plan_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    real_rmtree = workspace_hygiene.shutil.rmtree
    delete_calls = 0

    def fail_second_delete(path):
        nonlocal delete_calls
        delete_calls += 1
        if delete_calls == 2:
            raise PermissionError("simulated locked directory")
        real_rmtree(path)

    monkeypatch.setattr(workspace_hygiene.shutil, "rmtree", fail_second_delete)

    report = workspace_hygiene.run_cleanup_file(
        root,
        plan_path,
        report_path,
        expected_plan_sha256=hashlib.sha256(plan_path.read_bytes()).hexdigest(),
    )

    assert report["status"] == "partial_failed"
    assert report["removed_targets"] == [plan["targets"][0]["path"]]
    assert report["failed_target"] == plan["targets"][1]["path"]
    assert report["error"]["type"] == "PermissionError"
    assert json.loads(report_path.read_text(encoding="utf-8")) == report
    assert not (root / plan["targets"][0]["path"]).exists()
    assert (root / plan["targets"][1]["path"]).exists()
