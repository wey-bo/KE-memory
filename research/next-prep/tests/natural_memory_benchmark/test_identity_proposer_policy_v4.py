from __future__ import annotations

import importlib
import json
import shutil
from pathlib import Path

import pytest

from tools.natural_memory_benchmark.io import canonical_json_bytes, load_json, sha256_file


V2_SOURCE = Path("artifacts/identity-memory-experiment/natural-v2/source-cases.json")
DIAGNOSTIC_SOURCE = Path(
    "artifacts/identity-memory-experiment/dev-repair-v4/diagnostic-source-cases.json"
)
DIAGNOSTIC_EVIDENCE = Path(
    "artifacts/identity-memory-experiment/dev-repair-v4/diagnostic-gold-evidence.json"
)
FRESH_V3_HIDDEN = Path(
    "artifacts/identity-memory-experiment/natural-v3-fresh/hidden-source-cases.json"
)
BASE_EVIDENCE = Path("artifacts/natural-benchmark-slices/slice-v1/gold-evidence.json")
WORKSPACE_ROOT = Path(".")
FORMAL_FILES = (
    "diagnostic-gold-evidence.json",
    "diagnostic-source-cases.json",
    "combined-gold-evidence.json",
    "source-cases.json",
    "public.json",
    "authority.json",
    "gold.json",
    "manifest.json",
    "preregistration.json",
)


def _module():
    try:
        return importlib.import_module(
            "tools.natural_memory_benchmark.identity_proposer_policy_v4"
        )
    except ModuleNotFoundError as exc:
        pytest.fail(f"identity proposer policy v4 module missing: {exc}")


def _replace_json(path: Path, payload: object) -> None:
    if path.exists():
        path.chmod(0o644)
    path.write_bytes(canonical_json_bytes(payload))


def test_prepare_identity_dev_v4_is_balanced_opaque_and_deterministic(tmp_path):
    module = _module()
    root = tmp_path / "dev-repair-v4"
    first = module.prepare_identity_dev_v4(
        V2_SOURCE,
        DIAGNOSTIC_SOURCE,
        DIAGNOSTIC_EVIDENCE,
        root,
        workspace_root=WORKSPACE_ROOT,
    )
    first_bytes = {name: (root / name).read_bytes() for name in FORMAL_FILES[2:]}
    second = module.prepare_identity_dev_v4(
        V2_SOURCE,
        DIAGNOSTIC_SOURCE,
        DIAGNOSTIC_EVIDENCE,
        root,
        workspace_root=WORKSPACE_ROOT,
    )

    assert first == second
    assert first_bytes == {name: (root / name).read_bytes() for name in FORMAL_FILES[2:]}
    assert first["case_count"] == 12
    assert first["dev_count"] == 12
    assert first["hidden_count"] == 0
    assert first["diagnostic_action_distribution"] == {
        "include": 2,
        "exclude": 2,
        "abstain": 2,
    }
    assert first["prior_hidden_evidence_overlap_count"] == 0
    public = load_json(root / "public.json")
    assert all(case["case_id"].startswith("case-") for case in public["cases"])
    assert all(
        mention["mention_id"].startswith("mention-")
        for case in public["cases"]
        for mention in case["mentions"]
    )
    assert all((root / name).stat().st_mode & 0o777 == 0o444 for name in FORMAL_FILES[2:])


def test_validate_identity_dev_v4_rejects_actor_and_action_drift(tmp_path):
    module = _module()
    source_path = tmp_path / "diagnostic-source.json"
    source = load_json(DIAGNOSTIC_SOURCE)
    source["cases"][0]["mentions"][0]["source_actor_id"] = "person:gina"
    _replace_json(source_path, source)
    source_path.chmod(0o444)
    with pytest.raises(ValueError, match="actor mismatch"):
        module.prepare_identity_dev_v4(
            V2_SOURCE,
            source_path,
            DIAGNOSTIC_EVIDENCE,
            tmp_path / "actor-drift",
            workspace_root=WORKSPACE_ROOT,
        )

    source = load_json(DIAGNOSTIC_SOURCE)
    source["cases"][0]["gold"]["expected_action"] = "exclude"
    source_path = tmp_path / "diagnostic-action-drift.json"
    _replace_json(source_path, source)
    source_path.chmod(0o444)
    with pytest.raises(ValueError, match="diagnostic action distribution"):
        module.prepare_identity_dev_v4(
            V2_SOURCE,
            source_path,
            DIAGNOSTIC_EVIDENCE,
            tmp_path / "action-drift",
            workspace_root=WORKSPACE_ROOT,
        )


def test_validate_identity_dev_v4_rejects_prior_hidden_evidence_overlap(tmp_path):
    module = _module()
    source = load_json(DIAGNOSTIC_SOURCE)
    hidden_case = load_json(FRESH_V3_HIDDEN)["cases"][3]
    hidden_case = json.loads(json.dumps(hidden_case))
    hidden_case["split"] = "dev"
    source["cases"][0] = hidden_case
    source_path = tmp_path / "diagnostic-overlap.json"
    _replace_json(source_path, source)
    source_path.chmod(0o444)

    evidence = load_json(BASE_EVIDENCE)
    diagnostic = load_json(DIAGNOSTIC_EVIDENCE)
    evidence["items"].update(diagnostic["items"])
    evidence["item_count"] = len(evidence["items"])
    evidence_path = tmp_path / "diagnostic-overlap-evidence.json"
    _replace_json(evidence_path, evidence)
    evidence_path.chmod(0o444)

    with pytest.raises(ValueError, match="prior hidden evidence overlap"):
        module.prepare_identity_dev_v4(
            V2_SOURCE,
            source_path,
            evidence_path,
            tmp_path / "overlap",
            workspace_root=WORKSPACE_ROOT,
        )


def test_formal_validation_rejects_nonformal_inputs_and_writable_files(tmp_path):
    module = _module()
    formal_root = Path("artifacts/identity-memory-experiment/dev-repair-v4")
    module.prepare_identity_dev_v4(
        V2_SOURCE,
        DIAGNOSTIC_SOURCE,
        DIAGNOSTIC_EVIDENCE,
        formal_root,
        workspace_root=WORKSPACE_ROOT,
    )
    copied_source = tmp_path / "diagnostic-source.json"
    shutil.copyfile(DIAGNOSTIC_SOURCE, copied_source)
    copied_source.chmod(0o444)
    with pytest.raises(ValueError, match="exact formal input paths"):
        module.validate_identity_dev_v4(
            V2_SOURCE,
            copied_source,
            DIAGNOSTIC_EVIDENCE,
            formal_root,
            workspace_root=WORKSPACE_ROOT,
        )

    # The second half previously chmod-ed the *committed* public.json to 0644 and
    # expected "must be read-only". Two problems: git preserves no write bit, so that
    # precondition cannot hold after a clone, and mutating tracked evidence to test a
    # guard damages the evidence. Content rejection is exercised on a copy instead.
    copied_root = tmp_path / "dev-repair-v4"
    shutil.copytree(WORKSPACE_ROOT / formal_root, copied_root)
    target = copied_root / "public.json"
    target.chmod(0o644)
    original = target.read_bytes()
    mutated = original.replace(b'"case_count"', b'"case_Count"', 1)
    assert len(mutated) == len(original) and mutated != original, (
        "the mutation must actually change a byte, or this test proves nothing"
    )
    target.write_bytes(mutated)

    with pytest.raises(ValueError):
        module.validate_identity_dev_v4(
            V2_SOURCE,
            DIAGNOSTIC_SOURCE,
            DIAGNOSTIC_EVIDENCE,
            copied_root,
            workspace_root=WORKSPACE_ROOT,
        )


def test_formal_preregistration_binds_prior_protected_hashes():
    module = _module()
    formal_root = Path("artifacts/identity-memory-experiment/dev-repair-v4")
    result = module.validate_identity_dev_v4(
        V2_SOURCE,
        DIAGNOSTIC_SOURCE,
        DIAGNOSTIC_EVIDENCE,
        formal_root,
        workspace_root=WORKSPACE_ROOT,
    )
    preregistration = load_json(formal_root / "preregistration.json")
    assert result["status"] == "valid"
    assert len(preregistration["protected_sha256"]) >= 25
    assert preregistration["diagnostic_source_sha256"] == sha256_file(DIAGNOSTIC_SOURCE)
    assert preregistration["diagnostic_evidence_sha256"] == sha256_file(DIAGNOSTIC_EVIDENCE)
