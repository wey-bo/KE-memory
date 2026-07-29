from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from tools.natural_memory_benchmark import (
    typed_extractor_fresh_v3_materialization as materialization,
)
from tools.natural_memory_benchmark.io import (
    canonical_json_bytes,
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
