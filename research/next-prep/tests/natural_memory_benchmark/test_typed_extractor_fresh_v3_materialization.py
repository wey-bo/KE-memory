from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from tools.natural_memory_benchmark import (
    typed_extractor_fresh_v3_materialization as materialization,
)
from tools.natural_memory_benchmark.io import (
    canonical_json_bytes,
    load_json,
    sha256_file,
    write_json_immutable,
)
from tools.natural_memory_benchmark.typed_extractor_fresh_v3_authoring import (
    build_fresh_v3_authoring_bundle,
)


WORKSPACE = Path(__file__).resolve().parents[2]
REPOSITORY = WORKSPACE.parents[1]
PREREGISTRATION = (
    WORKSPACE
    / "artifacts/automatic-extraction-assessment/"
    "typed-extractor-v3-fresh-hidden-prereg-v1/preregistration.json"
)
ACTIVE_RECEIPT = PREREGISTRATION.parent / "authoring-implementation-receipt.json"
OFFICIAL_EVALUATION = (
    WORKSPACE
    / "artifacts/automatic-extraction-assessment/"
    "typed-extractor-v3-fresh-hidden-v1"
)
MATERIALIZATION_TIME = "2026-07-29T15:00:00Z"
EXPECTED_RECEIPT_SHA256 = (
    "c810f421d5a3b0726b862ec2f12c89e0d638e0747892637e2a32977587b7ef8c"
)


def _rewrite_json(path: Path, payload: dict[str, Any], *, canonical: bool) -> None:
    path.chmod(0o644)
    if canonical:
        content = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ) + "\n"
    else:
        content = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    path.write_text(content, encoding="utf-8")
    path.chmod(0o444)


def _write_payload_tree(root: Path) -> None:
    bundle = build_fresh_v3_authoring_bundle(PREREGISTRATION)
    for layer, values in materialization.LAYER_VALUES.items():
        layer_root = root / layer
        layer_root.mkdir(parents=True)
        layer_root.chmod(0o775)
        bundle_layer = getattr(bundle, layer)
        for name, attribute in values.items():
            path = layer_root / name
            write_json_immutable(path, getattr(bundle_layer, attribute))
            path.chmod(0o444)
    root.chmod(0o775)


def _make_bindable_tree(root: Path) -> dict[str, bytes]:
    _write_payload_tree(root)
    chronology_path = root / "chronology-receipt.json"
    chronology_path.write_bytes(b"{}\n")
    chronology_path.chmod(0o444)
    expected_files = {"chronology-receipt.json": chronology_path.read_bytes()}
    for layer, names in materialization.LAYER_VALUES.items():
        for name in names:
            path = root / layer / name
            expected_files[f"{layer}/{name}"] = path.read_bytes()
    return expected_files


def test_transition_binds_approved_receipt_git_authoring_and_materializer() -> None:
    transition = materialization._validate_active_receipt_transition(
        REPOSITORY,
        WORKSPACE,
        require_evaluation_absent=True,
    )

    assert transition.receipt_sha256 == EXPECTED_RECEIPT_SHA256
    assert transition.receipt.schema_version == (
        "typed-extractor-fresh-v3-authoring-receipt-v2"
    )
    assert transition.receipt.git_snapshot.snapshot_commit == (
        "00fa803ee44bcef5a299babb9a8e2b7ba9f994e4"
    )
    assert {
        name: binding.git_blob_oid
        for name, binding in transition.receipt.git_snapshot.files.items()
    } == {
        "preregistration": "6433fef43d7c2d68f064d900ff28172f94b4968e",
        "authoring_module": "bbe36a908ce7210c2919bb66328d4d4275851fe9",
        "authoring_test": "d92a28b2dae92bc4ddeecaca05f7520b864f24c2",
    }
    assert transition.receipt.authoring_binding.l1_case_count == 24
    assert transition.receipt.authoring_binding.l2_case_count == 18
    assert transition.receipt.candidate_v3_queue_sha256 == (
        "518ead9de8627a9a4384df8cdd9b8728a21fcf797f6b0f3d208dfcb28ac41c0f"
    )
    assert transition.receipt.guard_fingerprint == (
        "e184b6caf2998acf1c8700bc84d24bbafd49ab9c8f15738d1af8cc484ee5ebcc"
    )
    assert transition.materializer_sha256 == {
        "typed_extractor_fresh_v3_materialization.py": sha256_file(
            WORKSPACE
            / "tools/natural_memory_benchmark/"
            "typed_extractor_fresh_v3_materialization.py"
        ),
        "test_typed_extractor_fresh_v3_materialization.py": sha256_file(
            Path(__file__)
        ),
    }
    assert transition.evaluation_root_absent is True


def test_approved_receipt_reader_rejects_mode_noncanonical_and_strict_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    copied = tmp_path / ACTIVE_RECEIPT.name
    shutil.copyfile(ACTIVE_RECEIPT, copied)
    copied.chmod(0o644)
    with pytest.raises(ValueError, match="mode 0444"):
        materialization._read_approved_receipt(copied)

    payload = json.loads(ACTIVE_RECEIPT.read_text(encoding="utf-8"))
    _rewrite_json(copied, payload, canonical=False)
    monkeypatch.setattr(
        materialization,
        "APPROVED_ACTIVE_RECEIPT_SHA256",
        sha256_file(copied),
    )
    with pytest.raises(ValueError, match="canonical"):
        materialization._read_approved_receipt(copied)

    payload["unexpected"] = True
    _rewrite_json(copied, payload, canonical=True)
    monkeypatch.setattr(
        materialization,
        "APPROVED_ACTIVE_RECEIPT_SHA256",
        sha256_file(copied),
    )
    with pytest.raises(ValidationError):
        materialization._read_approved_receipt(copied)

    payload.pop("unexpected")
    payload["model_request_count"] = "0"
    _rewrite_json(copied, payload, canonical=True)
    monkeypatch.setattr(
        materialization,
        "APPROVED_ACTIVE_RECEIPT_SHA256",
        sha256_file(copied),
    )
    with pytest.raises(ValidationError):
        materialization._read_approved_receipt(copied)


def test_transition_rejects_declared_path_or_protected_state_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt, _, _ = materialization._read_approved_receipt(ACTIVE_RECEIPT)
    changed = receipt.model_copy(
        update={"materialization_workspace_paths": ["unexpected.py"]}
    )
    with pytest.raises(ValueError, match="materialization path set"):
        materialization._bind_materializer_files(changed, WORKSPACE)

    original = materialization.relocation._protected_state

    def drifted_protected_state(workspace_root: Path) -> dict[str, Any]:
        state = original(workspace_root)
        return {**state, "guard_results_sha256": "0" * 64}

    monkeypatch.setattr(
        materialization.relocation,
        "_protected_state",
        drifted_protected_state,
    )
    with pytest.raises(ValueError, match="protected state"):
        materialization._validate_active_receipt_transition(
            REPOSITORY,
            WORKSPACE,
            require_evaluation_absent=True,
        )


def test_chronology_binds_outputs_and_all_authorization_boundaries(
    tmp_path: Path,
) -> None:
    _write_payload_tree(tmp_path)
    transition = materialization._validate_active_receipt_transition(
        REPOSITORY,
        WORKSPACE,
        require_evaluation_absent=True,
    )

    chronology = materialization._build_materialization_receipt(
        preregistration_path=PREREGISTRATION,
        artifact_root=tmp_path,
        transition=transition,
        materialization_time=MATERIALIZATION_TIME,
    )
    payload = chronology.model_dump(mode="json")

    assert payload["schema_version"] == (
        "typed-extractor-fresh-v3-materialization-receipt-v1"
    )
    assert payload["status"] == "frozen_pre_model"
    assert payload["materialization_time"] == MATERIALIZATION_TIME
    assert payload["active_authoring_receipt"]["sha256"] == (
        EXPECTED_RECEIPT_SHA256
    )
    assert payload["l1_case_count"] == 24
    assert payload["l2_case_count"] == 18
    assert sum(payload["family_counts"]["l1"].values()) == 24
    assert sum(payload["family_counts"]["l2"].values()) == 18
    assert set(payload["layers"]) == {"l1", "l2"}
    assert all(len(values) == 5 for values in payload["layers"].values())
    assert payload["hidden_source_artifacts_created"] is True
    assert payload["model_request_count"] == 0
    assert payload["evaluation_result_write_count"] == 0
    assert set(payload["automatic_write_counts"].values()) == {0}
    assert payload["proposer_run_authorized"] is False
    assert payload["scoring_authorized"] is False
    assert payload["pipeline_integration_authorized"] is False
    assert payload["manual_identity_adjudications_materialized"] is False
    assert payload["embedding_authority"] is False
    assert payload["external_memory_systems_rerun"] is False
    assert payload["longmemeval_status"] == (
        "structured_l2_identity_unresolved"
    )
    assert hashlib.sha256(canonical_json_bytes(chronology)).hexdigest()


def test_chronology_model_rejects_unknown_and_coercive_fields(
    tmp_path: Path,
) -> None:
    _write_payload_tree(tmp_path)
    transition = materialization._validate_active_receipt_transition(
        REPOSITORY,
        WORKSPACE,
        require_evaluation_absent=True,
    )
    chronology = materialization._build_materialization_receipt(
        preregistration_path=PREREGISTRATION,
        artifact_root=tmp_path,
        transition=transition,
        materialization_time=MATERIALIZATION_TIME,
    )
    payload = chronology.model_dump(mode="json")
    payload["unexpected"] = True
    with pytest.raises(ValidationError):
        materialization.FreshV3MaterializationReceipt.model_validate(payload)

    payload.pop("unexpected")
    payload["l1_case_count"] = "24"
    with pytest.raises(ValidationError):
        materialization.FreshV3MaterializationReceipt.model_validate(payload)


def _temporary_evaluation_root(tmp_path: Path) -> Path:
    return tmp_path / "typed-extractor-v3-fresh-hidden-v1"


def _staging_roots(evaluation_root: Path) -> list[Path]:
    return list(evaluation_root.parent.glob(f".{evaluation_root.name}.staging-*"))


def _materialize_temporary(
    evaluation_root: Path,
    materialization_time: str = MATERIALIZATION_TIME,
) -> dict[str, Any]:
    return materialization._materialize_fresh_v3_hidden_to_root(
        REPOSITORY,
        WORKSPACE,
        evaluation_root,
        materialization_time,
    )


def _validate_temporary(evaluation_root: Path) -> dict[str, Any]:
    return materialization._validate_materialized_root(
        repository_root=REPOSITORY,
        workspace_root=WORKSPACE,
        artifact_root=evaluation_root,
        logical_evaluation_root=OFFICIAL_EVALUATION,
    )


def test_materializes_exact_read_only_bundle_and_hash_chronology(
    tmp_path: Path,
) -> None:
    evaluation_root = _temporary_evaluation_root(tmp_path)
    bundle = build_fresh_v3_authoring_bundle(PREREGISTRATION)

    result = _materialize_temporary(evaluation_root)

    assert result == {
        "status": "valid",
        "evaluation_id": "typed-extractor-v3-fresh-hidden-v1",
        "l1_case_count": 24,
        "l2_case_count": 18,
        "model_runs_present_at_freeze": False,
        "model_request_count": 0,
    }
    assert {path.name for path in evaluation_root.iterdir()} == {
        "chronology-receipt.json",
        "l1",
        "l2",
    }
    assert evaluation_root.stat().st_mode & 0o777 == 0o775
    payloads = materialization._layer_payloads(bundle)
    for layer, values in payloads.items():
        layer_root = evaluation_root / layer
        assert layer_root.stat().st_mode & 0o777 == 0o775
        assert {path.name for path in layer_root.iterdir()} == set(values)
        assert not (layer_root / "model-runs").exists()
        for name, expected in values.items():
            path = layer_root / name
            assert path.read_bytes() == canonical_json_bytes(expected)
            assert path.stat().st_mode & 0o777 == 0o444

    chronology_path = evaluation_root / "chronology-receipt.json"
    chronology = load_json(chronology_path)
    assert chronology_path.stat().st_mode & 0o777 == 0o444
    assert chronology["materialization_time"] == MATERIALIZATION_TIME
    assert chronology["l1_case_count"] == 24
    assert chronology["l2_case_count"] == 18
    assert chronology["model_request_count"] == 0
    assert chronology["evaluation_result_write_count"] == 0
    assert set(chronology["automatic_write_counts"].values()) == {0}
    assert _validate_temporary(evaluation_root) == result


def test_public_writer_and_validator_require_exact_official_root(
    tmp_path: Path,
) -> None:
    evaluation_root = _temporary_evaluation_root(tmp_path)

    with pytest.raises(ValueError, match="exact official evaluation root"):
        materialization.materialize_fresh_v3_hidden(
            REPOSITORY,
            WORKSPACE,
            evaluation_root,
            MATERIALIZATION_TIME,
        )
    with pytest.raises(ValueError, match="exact official evaluation root"):
        materialization.validate_fresh_v3_hidden_materialization(
            REPOSITORY,
            WORKSPACE,
            evaluation_root,
        )

    assert not evaluation_root.exists()
    assert not _staging_roots(evaluation_root)


def test_materialization_refuses_existing_root_and_second_publish(
    tmp_path: Path,
) -> None:
    evaluation_root = _temporary_evaluation_root(tmp_path)
    evaluation_root.mkdir()

    with pytest.raises(ValueError, match="evaluation root must be absent"):
        _materialize_temporary(evaluation_root)

    evaluation_root.rmdir()
    _materialize_temporary(evaluation_root)
    with pytest.raises(ValueError, match="evaluation root must be absent"):
        _materialize_temporary(evaluation_root)


@pytest.mark.parametrize(
    "materialization_time",
    ["2026-07-29T25:00:00Z", "2026-07-29T15:00:00+08:00"],
)
def test_materialization_rejects_invalid_utc_before_staging(
    tmp_path: Path,
    materialization_time: str,
) -> None:
    evaluation_root = _temporary_evaluation_root(tmp_path)

    with pytest.raises(ValidationError, match="valid UTC timestamp"):
        _materialize_temporary(evaluation_root, materialization_time)

    assert not evaluation_root.exists()
    assert not _staging_roots(evaluation_root)


def test_atomic_publish_failure_cleans_only_current_staging_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evaluation_root = _temporary_evaluation_root(tmp_path)
    stale_staging = tmp_path / f".{evaluation_root.name}.staging-stale"
    stale_staging.mkdir()
    marker = stale_staging / "preserve.txt"
    marker.write_text("preserve\n", encoding="utf-8")

    def fail_publish(*args: Any, **kwargs: Any) -> None:
        raise OSError(f"injected publish failure: {args} {kwargs}")

    monkeypatch.setattr(materialization, "_publish_noreplace", fail_publish)
    with pytest.raises(OSError, match="injected publish failure"):
        _materialize_temporary(evaluation_root)

    assert not evaluation_root.exists()
    assert marker.read_text(encoding="utf-8") == "preserve\n"
    assert _staging_roots(evaluation_root) == [stale_staging]


def test_cleanup_does_not_delete_a_root_replacement_through_path_rmtree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evaluation_root = _temporary_evaluation_root(tmp_path)
    replacement = tmp_path / "replacement-root"
    replacement.mkdir()
    marker = replacement / "preserve.txt"
    marker.write_text("preserve\n", encoding="utf-8")
    original_rmtree = shutil.rmtree

    def exchange_then_rmtree(
        path: str,
        *args: Any,
        dir_fd: int | None = None,
        **kwargs: Any,
    ) -> None:
        assert dir_fd is not None
        moved_name = f"{path}.original"
        os.rename(
            path,
            moved_name,
            src_dir_fd=dir_fd,
            dst_dir_fd=dir_fd,
        )
        os.rename(
            replacement.name,
            path,
            src_dir_fd=dir_fd,
            dst_dir_fd=dir_fd,
        )
        original_rmtree(path, *args, dir_fd=dir_fd, **kwargs)

    def fail_publish(*args: Any, **kwargs: Any) -> None:
        raise OSError(f"injected publish failure: {args} {kwargs}")

    monkeypatch.setattr(shutil, "rmtree", exchange_then_rmtree)
    monkeypatch.setattr(materialization, "_publish_noreplace", fail_publish)

    with pytest.raises(OSError, match="injected publish failure"):
        _materialize_temporary(evaluation_root)

    assert marker.read_text(encoding="utf-8") == "preserve\n"
    assert not evaluation_root.exists()


def test_atomic_publish_refuses_concurrently_created_empty_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evaluation_root = _temporary_evaluation_root(tmp_path)
    current_publish = materialization._publish_noreplace

    def create_target_then_publish(
        parent_descriptor: int,
        source_name: str,
        target_name: str,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        os.mkdir(target_name, dir_fd=parent_descriptor)
        current_publish(
            parent_descriptor,
            source_name,
            target_name,
            *args,
            **kwargs,
        )

    monkeypatch.setattr(
        materialization,
        "_publish_noreplace",
        create_target_then_publish,
    )

    with pytest.raises(FileExistsError, match="evaluation root already exists"):
        _materialize_temporary(evaluation_root)

    assert evaluation_root.is_dir()
    assert not list(evaluation_root.iterdir())
    assert not _staging_roots(evaluation_root)


def test_materialization_revalidates_protected_state_after_staging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evaluation_root = _temporary_evaluation_root(tmp_path)
    original = materialization.relocation._protected_state
    calls = 0

    def drift_after_initial_validation(workspace_root: Path) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        state = original(workspace_root)
        if calls > 1:
            return {**state, "guard_results_sha256": "0" * 64}
        return state

    monkeypatch.setattr(
        materialization.relocation,
        "_protected_state",
        drift_after_initial_validation,
    )

    with pytest.raises(ValueError, match="protected state drift"):
        _materialize_temporary(evaluation_root)

    assert calls > 1
    assert not evaluation_root.exists()
    assert not _staging_roots(evaluation_root)


def test_materialization_replays_transition_and_tree_immediately_before_publish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evaluation_root = _temporary_evaluation_root(tmp_path)
    original = materialization._validate_active_receipt_transition
    requirements: list[bool] = []

    def record_transition(
        repository_root: Path,
        workspace_root: Path,
        *,
        require_evaluation_absent: bool,
    ) -> materialization.ActiveTransition:
        requirements.append(require_evaluation_absent)
        return original(
            repository_root,
            workspace_root,
            require_evaluation_absent=require_evaluation_absent,
        )

    monkeypatch.setattr(
        materialization,
        "_validate_active_receipt_transition",
        record_transition,
    )

    _materialize_temporary(evaluation_root)

    assert requirements == [True, False, True, False, False]


@pytest.mark.parametrize("swap", ["root", "layer", "file"])
def test_publish_rejects_staging_identity_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    swap: str,
) -> None:
    evaluation_root = _temporary_evaluation_root(tmp_path)
    current_publish = materialization._publish_noreplace
    replacement_marker = tmp_path / "replacement-preserved.txt"

    def swap_then_publish(
        parent_descriptor: int,
        source_name: str,
        target_name: str,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        source = tmp_path / source_name
        if swap == "root":
            moved = tmp_path / f"{source_name}.moved"
            os.rename(
                source_name,
                moved.name,
                src_dir_fd=parent_descriptor,
                dst_dir_fd=parent_descriptor,
            )
            source.mkdir()
            replacement_marker.write_text("preserve\n", encoding="utf-8")
            (source / replacement_marker.name).symlink_to(replacement_marker)
        elif swap == "layer":
            moved = source / "l1-original"
            (source / "l1").rename(moved)
            shutil.copytree(moved, source / "l1", copy_function=shutil.copy2)
        else:
            path = source / "l1" / "public-l1.json"
            moved = path.with_name("public-l1-original.json")
            path.rename(moved)
            shutil.copy2(moved, path)
        current_publish(
            parent_descriptor,
            source_name,
            target_name,
            *args,
            **kwargs,
        )

    monkeypatch.setattr(materialization, "_publish_noreplace", swap_then_publish)

    with pytest.raises(ValueError, match="identity|staging|artifact"):
        _materialize_temporary(evaluation_root)

    assert not evaluation_root.exists()
    if swap == "root":
        replacement = next(
            path
            for path in _staging_roots(evaluation_root)
            if (path / replacement_marker.name).is_symlink()
        )
        assert (replacement / replacement_marker.name).is_symlink()
        assert replacement_marker.read_text(encoding="utf-8") == "preserve\n"


@pytest.mark.parametrize("target", ["root", "layer", "file"])
def test_bound_tree_enforces_required_modes(
    tmp_path: Path,
    target: str,
) -> None:
    staging_root = tmp_path / ".typed-extractor-v3-fresh-hidden-v1.staging-bind"
    expected_files = _make_bindable_tree(staging_root)
    if target == "root":
        staging_root.chmod(0o755)
    elif target == "layer":
        (staging_root / "l1").chmod(0o755)
    else:
        (staging_root / "l1" / "public-l1.json").chmod(0o644)

    parent_descriptor = os.open(
        tmp_path,
        os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
    )
    bound_tree: materialization._BoundMaterializedTree | None = None
    try:
        with pytest.raises(ValueError, match="required mode"):
            bound_tree = materialization._bind_materialized_tree(
                parent_descriptor,
                staging_root.name,
                expected_files,
            )
    finally:
        if bound_tree is not None:
            bound_tree.close()
        os.close(parent_descriptor)


@pytest.mark.parametrize("target", ["root", "layer", "file"])
def test_publish_rejects_mode_mutation_after_final_staging_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    target: str,
) -> None:
    evaluation_root = _temporary_evaluation_root(tmp_path)
    original_validate = materialization._validate_materialized_root
    staging_validation_count = 0

    def mutate_after_final_staging_validation(**kwargs: Any) -> dict[str, Any]:
        nonlocal staging_validation_count
        result = original_validate(**kwargs)
        artifact_root = Path(kwargs["artifact_root"])
        if artifact_root.name.startswith(f".{evaluation_root.name}.staging-"):
            staging_validation_count += 1
            if staging_validation_count == 2:
                if target == "root":
                    artifact_root.chmod(0o755)
                elif target == "layer":
                    (artifact_root / "l1").chmod(0o755)
                else:
                    (artifact_root / "l1" / "public-l1.json").chmod(0o644)
        return result

    monkeypatch.setattr(
        materialization,
        "_validate_materialized_root",
        mutate_after_final_staging_validation,
    )

    with pytest.raises(ValueError, match="mode|identity"):
        _materialize_temporary(evaluation_root)

    assert staging_validation_count == 2
    assert not evaluation_root.exists()


def test_publish_rejects_canonical_file_replacement_after_final_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evaluation_root = _temporary_evaluation_root(tmp_path)
    original_validate = materialization._validate_materialized_root
    staging_validation_count = 0

    def replace_after_final_staging_validation(**kwargs: Any) -> dict[str, Any]:
        nonlocal staging_validation_count
        result = original_validate(**kwargs)
        artifact_root = Path(kwargs["artifact_root"])
        if artifact_root.name.startswith(f".{evaluation_root.name}.staging-"):
            staging_validation_count += 1
            if staging_validation_count == 2:
                path = artifact_root / "l1" / "public-l1.json"
                moved = tmp_path / "original-public-l1.json"
                path.rename(moved)
                shutil.copy2(moved, path)
        return result

    monkeypatch.setattr(
        materialization,
        "_validate_materialized_root",
        replace_after_final_staging_validation,
    )

    with pytest.raises(ValueError, match="identity"):
        _materialize_temporary(evaluation_root)

    assert staging_validation_count == 2
    assert not evaluation_root.exists()


def test_materialization_fsyncs_files_directories_and_publication_parent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evaluation_root = _temporary_evaluation_root(tmp_path)
    original_fsync = materialization.os.fsync
    synced_types: list[int] = []
    synced_identities: Counter[tuple[int, int]] = Counter()

    def record_fsync(descriptor: int) -> None:
        opened = os.fstat(descriptor)
        synced_types.append(stat.S_IFMT(opened.st_mode))
        synced_identities[(opened.st_dev, opened.st_ino)] += 1
        original_fsync(descriptor)

    monkeypatch.setattr(materialization.os, "fsync", record_fsync)

    _materialize_temporary(evaluation_root)

    published_entries = [evaluation_root, evaluation_root / "l1", evaluation_root / "l2"]
    published_entries.extend(
        path
        for path in evaluation_root.rglob("*")
        if path.is_file()
    )
    for path in published_entries:
        opened = path.stat()
        assert synced_identities[(opened.st_dev, opened.st_ino)] >= 2
    assert synced_types.count(stat.S_IFREG) >= 22
    assert synced_types.count(stat.S_IFDIR) >= 8


@pytest.mark.parametrize(
    "drift",
    ["root_mode", "layer_mode", "mode", "payload", "chronology"],
)
def test_validation_rejects_materialized_artifact_drift(
    tmp_path: Path,
    drift: str,
) -> None:
    evaluation_root = _temporary_evaluation_root(tmp_path)
    _materialize_temporary(evaluation_root)

    if drift == "root_mode":
        evaluation_root.chmod(0o755)
    elif drift == "layer_mode":
        (evaluation_root / "l2").chmod(0o755)
    elif drift == "mode":
        (evaluation_root / "l1" / "public-l1.json").chmod(0o644)
    elif drift == "payload":
        path = evaluation_root / "l2" / "manifest-l2.json"
        payload = load_json(path)
        payload["case_count"] = 0
        _rewrite_json(path, payload, canonical=True)
    else:
        path = evaluation_root / "chronology-receipt.json"
        payload = load_json(path)
        payload["materializer_sha256"][
            "typed_extractor_fresh_v3_materialization.py"
        ] = "f" * 64
        _rewrite_json(path, payload, canonical=True)

    with pytest.raises((ValueError, ValidationError), match="drift|mode"):
        _validate_temporary(evaluation_root)


def test_validation_rejects_symlink_payload(
    tmp_path: Path,
) -> None:
    evaluation_root = _temporary_evaluation_root(tmp_path)
    _materialize_temporary(evaluation_root)
    path = evaluation_root / "l1" / "public-l1.json"
    path.unlink()
    path.symlink_to(PREREGISTRATION)

    with pytest.raises(ValueError, match="symlink|regular"):
        _validate_temporary(evaluation_root)


@pytest.mark.parametrize("location", ["root", "l1", "l2"])
def test_validation_rejects_unregistered_artifact(
    tmp_path: Path,
    location: str,
) -> None:
    evaluation_root = _temporary_evaluation_root(tmp_path)
    _materialize_temporary(evaluation_root)
    parent = evaluation_root if location == "root" else evaluation_root / location
    (parent / "unexpected.json").write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="artifact.*drift"):
        _validate_temporary(evaluation_root)


@pytest.mark.parametrize("location", ["root", "l1", "l2"])
def test_validation_rejects_any_model_runs_path(
    tmp_path: Path,
    location: str,
) -> None:
    evaluation_root = _temporary_evaluation_root(tmp_path)
    _materialize_temporary(evaluation_root)
    parent = evaluation_root if location == "root" else evaluation_root / location
    (parent / "model-runs").mkdir()

    with pytest.raises(ValueError, match="model runs|artifact.*drift"):
        _validate_temporary(evaluation_root)
