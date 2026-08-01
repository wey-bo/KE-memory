from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tools.natural_memory_benchmark import identity_proposal_fresh as fresh_module
from tools.natural_memory_benchmark.identity_proposal_fresh import (
    CASE_ID_RE,
    MENTION_ID_RE,
    derive_fresh_id,
    prepare_fresh_identity_slice,
    validate_fresh_identity_slice,
)
from tools.natural_memory_benchmark.io import (
    canonical_json_bytes,
    load_json,
    sha256_file,
)


V2_SOURCE = Path(
    "artifacts/identity-memory-experiment/natural-v2/source-cases.json"
)
FRESH_HIDDEN_SOURCE = Path(
    "artifacts/identity-memory-experiment/natural-v3-fresh/hidden-source-cases.json"
)
POLICY_FREEZE = Path(
    "artifacts/identity-memory-experiment/dev-repair-v3/policy-freeze-v3.json"
)
WORKSPACE_ROOT = Path(".")
GENERATED_FILES = (
    "source-cases.json",
    "opaque-id-map.json",
    "preregistration.json",
    "public.json",
    "authority.json",
    "gold.json",
    "manifest.json",
)
DEV_RUN_FILES = (
    "dispatch.json",
    "api-transport.json",
    "proposals.json",
    "provenance.json",
    "score.json",
    "report.md",
)


def _replace_json(path: Path, payload: object) -> None:
    path.chmod(0o644)
    path.write_bytes(canonical_json_bytes(payload))


def _refresh_manifest_and_preregistration(root: Path) -> None:
    manifest_path = root / "manifest.json"
    manifest = load_json(manifest_path)
    manifest["source_config_sha256"] = sha256_file(root / "source-cases.json")
    manifest["output_sha256"] = {
        name: sha256_file(root / name)
        for name in ("public.json", "authority.json", "gold.json")
    }
    _replace_json(manifest_path, manifest)

    preregistration_path = root / "preregistration.json"
    preregistration = load_json(preregistration_path)
    preregistration["files_sha256"] = {
        name: sha256_file(root / name)
        for name in (
            "source-cases.json",
            "opaque-id-map.json",
            "public.json",
            "authority.json",
            "gold.json",
            "manifest.json",
        )
    }
    _replace_json(preregistration_path, preregistration)


def _copy_hidden_source(tmp_path: Path) -> Path:
    target = tmp_path / "hidden-source-cases.json"
    shutil.copyfile(FRESH_HIDDEN_SOURCE, target)
    target.chmod(0o444)
    return target


def _copy_policy_run_bundle(tmp_path: Path) -> tuple[Path, Path]:
    policy_freeze = tmp_path / "dev-repair-v3" / "policy-freeze-v3.json"
    policy_freeze.parent.mkdir(parents=True)
    shutil.copyfile(POLICY_FREEZE, policy_freeze)
    policy_mtime = POLICY_FREEZE.stat().st_mtime_ns
    os.utime(policy_freeze, ns=(policy_mtime, policy_mtime))
    policy_freeze.chmod(0o444)

    frozen = load_json(POLICY_FREEZE)
    source_run = POLICY_FREEZE.parent / "model-runs" / frozen["dev_run_id"]
    target_run = policy_freeze.parent / "model-runs" / frozen["dev_run_id"]
    target_run.mkdir(parents=True)
    for name in DEV_RUN_FILES:
        target = target_run / name
        shutil.copyfile(source_run / name, target)
        source_mtime = (source_run / name).stat().st_mtime_ns
        os.utime(target, ns=(source_mtime, source_mtime))
        target.chmod(0o444)
    return policy_freeze, target_run


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "tools.natural_memory_benchmark.cli", *args],
        check=True,
        capture_output=True,
        text=True,
    )


def test_derive_fresh_id_is_stable_typed_and_namespace_sensitive():
    first = derive_fresh_id("namespace-a", "case", 1, "source-a")
    assert first == derive_fresh_id("namespace-a", "case", 1, "source-a")
    assert CASE_ID_RE.fullmatch(first)
    assert first != derive_fresh_id("namespace-b", "case", 1, "source-a")
    assert first != derive_fresh_id("namespace-a", "case", 2, "source-a")
    assert MENTION_ID_RE.fullmatch(
        derive_fresh_id("namespace-a", "mention", 1, "source-a")
    )


def test_prepare_fresh_slice_is_balanced_new_opaque_and_deterministic(tmp_path):
    root = tmp_path / "natural-v3-fresh"
    first = prepare_fresh_identity_slice(
        V2_SOURCE,
        FRESH_HIDDEN_SOURCE,
        root,
        policy_freeze_path=POLICY_FREEZE,
        workspace_root=WORKSPACE_ROOT,
    )
    first_bytes = {name: (root / name).read_bytes() for name in GENERATED_FILES}
    second = prepare_fresh_identity_slice(
        V2_SOURCE,
        FRESH_HIDDEN_SOURCE,
        root,
        policy_freeze_path=POLICY_FREEZE,
        workspace_root=WORKSPACE_ROOT,
    )

    assert first == second
    assert first_bytes == {name: (root / name).read_bytes() for name in GENERATED_FILES}
    assert first["case_count"] == 12
    assert first["dev_count"] == 6
    assert first["hidden_count"] == 6
    assert first["hidden_action_distribution"] == {
        "merge": 1,
        "keep_distinct": 1,
        "abstain_identity": 1,
        "include": 1,
        "exclude": 1,
        "abstain_membership": 1,
    }
    assert first["cross_session_hidden_count"] >= 2
    assert first["v2_id_overlap_count"] == 0
    assert first["v2_hidden_evidence_overlap_count"] == 0
    assert first["policy_chronology_valid"] is True

    public = load_json(root / "public.json")
    v2_public = load_json(V2_SOURCE.parent / "public.json")
    v2_ids = {
        item
        for case in v2_public["cases"]
        for item in [case["case_id"], *[m["mention_id"] for m in case["mentions"]]]
    }
    v3_ids = {
        item
        for case in public["cases"]
        for item in [case["case_id"], *[m["mention_id"] for m in case["mentions"]]]
    }
    assert not v2_ids & v3_ids
    assert all(CASE_ID_RE.fullmatch(case["case_id"]) for case in public["cases"])
    assert all(
        MENTION_ID_RE.fullmatch(mention["mention_id"])
        for case in public["cases"]
        for mention in case["mentions"]
    )
    assert all((root / name).stat().st_mode & 0o777 == 0o444 for name in GENERATED_FILES)


def test_prepare_rejects_policy_or_chronology_drift(tmp_path):
    # The first phase previously required the policy freeze to be mode 0444 and
    # expected "policy freeze must be read-only". Git preserves no write bit, so a
    # freeze arrives writable from any clone; a writable-but-unchanged freeze must be
    # accepted, and only changed bytes rejected. The second phase already covers the
    # changed-bytes case, so this asserts the acceptance side.
    writable_freeze = tmp_path / "dev-repair-v3" / "policy-freeze-v3.json"
    writable_freeze.parent.mkdir(parents=True)
    shutil.copyfile(POLICY_FREEZE, writable_freeze)
    source_run = POLICY_FREEZE.parent / "model-runs"
    shutil.copytree(source_run, writable_freeze.parent / "model-runs")
    writable_freeze.chmod(0o644)

    prepare_fresh_identity_slice(
        V2_SOURCE,
        FRESH_HIDDEN_SOURCE,
        tmp_path / "writable-policy",
        policy_freeze_path=writable_freeze,
        workspace_root=WORKSPACE_ROOT,
    )

    changed_freeze = tmp_path / "policy-freeze-changed.json"
    changed = load_json(POLICY_FREEZE)
    changed["policy_sha256"] = "0" * 64
    changed_freeze.write_bytes(canonical_json_bytes(changed))
    changed_freeze.chmod(0o444)
    with pytest.raises(ValueError, match="policy hash mismatch"):
        prepare_fresh_identity_slice(
            V2_SOURCE,
            FRESH_HIDDEN_SOURCE,
            tmp_path / "changed-policy",
            policy_freeze_path=changed_freeze,
            workspace_root=WORKSPACE_ROOT,
        )

    # The third phase originally back-dated the hidden source and expected "hidden
    # source predates policy freeze". That ordering was carried by mtime, which git
    # does not preserve, so it is asserted against the chronology receipt instead --
    # see test_prepare_rejects_dev_run_that_the_receipt_orders_after_hidden. What
    # remains checkable here is that a hidden source whose bytes differ from the
    # receipt's binding is refused.
    old_hidden = _copy_hidden_source(tmp_path)
    old_hidden.chmod(0o644)
    original = old_hidden.read_bytes()
    mutated = original.replace(b'"dataset_id"', b'"dataset_Id"', 1)
    assert len(mutated) == len(original) and mutated != original
    old_hidden.write_bytes(mutated)
    old_hidden.chmod(0o444)

    with pytest.raises(ValueError):
        prepare_fresh_identity_slice(
            V2_SOURCE,
            old_hidden,
            tmp_path / "old-hidden",
            policy_freeze_path=POLICY_FREEZE,
            workspace_root=WORKSPACE_ROOT,
        )


def test_prepare_rejects_dev_run_that_the_receipt_orders_after_hidden(tmp_path):
    """Ordering violations must be detected in the receipt, not in live mtimes.

    Was: back-date ``score.json`` past the hidden source and expect "passing dev run
    must predate hidden source". That worked only while mtime carried the ordering,
    which git does not preserve -- the check was already unsatisfiable at the
    reorganization baseline. The ordering now comes from the chronology receipt, so a
    violation is expressed by editing the receipt's recorded times, which is also
    what a tampered record would look like.
    """
    policy_freeze, dev_run = _copy_policy_run_bundle(tmp_path)
    hidden_source = _copy_hidden_source(tmp_path)
    formal_receipt = WORKSPACE_ROOT / fresh_module.FORMAL_CHRONOLOGY_RECEIPT_PATH
    receipt = load_json(formal_receipt)

    inverted = dict(receipt)
    inverted["policy_freeze"] = {
        **receipt["policy_freeze"],
        "path": str(policy_freeze.relative_to(tmp_path)),
    }
    inverted["hidden_source"] = {
        **receipt["hidden_source"],
        "path": str(hidden_source.relative_to(tmp_path)),
    }
    latest_dev = max(
        observation["mtime_ns"] for observation in receipt["dev_run_files"].values()
    )
    # Hidden source recorded as written *before* the dev run finished.
    inverted["hidden_source"]["mtime_ns"] = latest_dev - 1
    inverted["dev_run_files"] = {
        name: {**observation, "path": str((dev_run / name).relative_to(tmp_path))}
        for name, observation in receipt["dev_run_files"].items()
    }
    copied = tmp_path / "chronology-receipt-v3.json"
    copied.write_bytes(canonical_json_bytes(inverted))
    copied.chmod(0o444)

    with pytest.raises(ValueError, match="passing dev run must predate hidden source"):
        fresh_module._validate_chronology_receipt(
            copied,
            policy_freeze_path=policy_freeze,
            hidden_source_path=hidden_source,
            dev_run_root=dev_run,
            workspace_root=tmp_path,
            expected_sha256=sha256_file(copied),
        )


def test_frozen_chronology_receipt_detects_mtime_drift(tmp_path):
    receipt_path = getattr(fresh_module, "FORMAL_CHRONOLOGY_RECEIPT_PATH", None)
    receipt_hash = getattr(fresh_module, "FORMAL_CHRONOLOGY_RECEIPT_SHA256", None)
    validate_receipt = getattr(fresh_module, "_validate_chronology_receipt", None)
    assert isinstance(receipt_path, Path)
    assert isinstance(receipt_hash, str)
    assert callable(validate_receipt)

    formal_receipt = WORKSPACE_ROOT / receipt_path
    receipt = load_json(formal_receipt)
    policy_freeze, dev_run = _copy_policy_run_bundle(tmp_path)
    hidden_source = _copy_hidden_source(tmp_path)
    remapped = dict(receipt)
    remapped["policy_freeze"] = dict(receipt["policy_freeze"])
    remapped["policy_freeze"]["path"] = str(policy_freeze.relative_to(tmp_path))
    remapped["hidden_source"] = dict(receipt["hidden_source"])
    remapped["hidden_source"]["path"] = str(hidden_source.relative_to(tmp_path))
    remapped["dev_run_files"] = {
        name: {
            **observation,
            "path": str((dev_run / name).relative_to(tmp_path)),
        }
        for name, observation in receipt["dev_run_files"].items()
    }
    for observation, path in [
        (remapped["policy_freeze"], policy_freeze),
        (remapped["hidden_source"], hidden_source),
        *[
            (remapped["dev_run_files"][name], dev_run / name)
            for name in DEV_RUN_FILES
        ],
    ]:
        os.utime(path, ns=(observation["mtime_ns"], observation["mtime_ns"]))
    copied_receipt = tmp_path / "chronology-receipt-v3.json"
    copied_receipt.write_bytes(canonical_json_bytes(remapped))
    copied_receipt.chmod(0o444)
    copied_hash = sha256_file(copied_receipt)

    validated = validate_receipt(
        copied_receipt,
        policy_freeze_path=policy_freeze,
        hidden_source_path=hidden_source,
        dev_run_root=dev_run,
        workspace_root=tmp_path,
        expected_sha256=copied_hash,
        # This test restores the recorded mtimes on purpose, so it opts into the
        # strict check. The default is off because git preserves no mtime: a fresh
        # clone has arbitrary values, and demanding they match made the ordering
        # claim unverifiable everywhere.
        require_live_mtime=True,
    )
    assert validated["dev_run_complete_precedes_hidden_source"] is True

    score_path = dev_run / "score.json"
    score_path.chmod(0o644)
    os.utime(
        score_path,
        ns=(
            remapped["dev_run_files"]["score.json"]["mtime_ns"] + 1,
            remapped["dev_run_files"]["score.json"]["mtime_ns"] + 1,
        ),
    )
    score_path.chmod(0o444)
    with pytest.raises(ValueError, match="chronology receipt mtime mismatch"):
        validate_receipt(
            copied_receipt,
            policy_freeze_path=policy_freeze,
            hidden_source_path=hidden_source,
            dev_run_root=dev_run,
            workspace_root=tmp_path,
            expected_sha256=copied_hash,
            require_live_mtime=True,
        )

    # With the strict check off -- the default, and what a fresh clone gets -- the
    # perturbed mtime is not an error, because mtime carries no information there.
    # Ordering still comes from the receipt's recorded times.
    relaxed = validate_receipt(
        copied_receipt,
        policy_freeze_path=policy_freeze,
        hidden_source_path=hidden_source,
        dev_run_root=dev_run,
        workspace_root=tmp_path,
        expected_sha256=copied_hash,
    )
    assert relaxed["dev_run_complete_precedes_hidden_source"] is True


def test_formal_validation_rejects_nonformal_input_paths(tmp_path):
    policy_freeze, _ = _copy_policy_run_bundle(tmp_path)
    hidden_source = _copy_hidden_source(tmp_path)
    hidden_mtime = FRESH_HIDDEN_SOURCE.stat().st_mtime_ns
    os.utime(hidden_source, ns=(hidden_mtime, hidden_mtime))
    v2_source = tmp_path / "natural-v2-source-cases.json"
    shutil.copyfile(V2_SOURCE, v2_source)
    v2_source.chmod(0o444)

    with pytest.raises(
        ValueError,
        match="formal fresh validation requires exact formal input paths",
    ):
        validate_fresh_identity_slice(
            v2_source,
            hidden_source,
            Path("artifacts/identity-memory-experiment/natural-v3-fresh"),
            policy_freeze_path=policy_freeze,
            workspace_root=WORKSPACE_ROOT,
        )


def test_prepare_rejects_v2_hidden_evidence_reuse(tmp_path):
    hidden_path = _copy_hidden_source(tmp_path)
    hidden = load_json(hidden_path)
    v2 = load_json(V2_SOURCE)
    hidden["cases"][0] = v2["cases"][6]
    hidden["cases"][0]["case_id"] = "fresh-hidden-reused-evidence"
    _replace_json(hidden_path, hidden)
    hidden_path.chmod(0o444)

    with pytest.raises(ValueError, match="v2 hidden evidence overlap"):
        prepare_fresh_identity_slice(
            V2_SOURCE,
            hidden_path,
            tmp_path / "overlap",
            policy_freeze_path=POLICY_FREEZE,
            workspace_root=WORKSPACE_ROOT,
        )


def test_validate_rejects_coordinated_non_derived_id_and_gold_drift(tmp_path):
    root = tmp_path / "natural-v3-fresh"
    prepare_fresh_identity_slice(
        V2_SOURCE,
        FRESH_HIDDEN_SOURCE,
        root,
        policy_freeze_path=POLICY_FREEZE,
        workspace_root=WORKSPACE_ROOT,
    )
    mapping_path = root / "opaque-id-map.json"
    mapping = load_json(mapping_path)
    old_case_id = mapping["case_ids"][0]["v3"]
    replacement = "case-0000000000000000"
    mapping["case_ids"][0]["v3"] = replacement
    _replace_json(mapping_path, mapping)

    source_path = root / "source-cases.json"
    source = load_json(source_path)
    source["cases"][0]["case_id"] = replacement
    _replace_json(source_path, source)
    for name, collection in (
        ("public.json", "cases"),
        ("authority.json", "cases"),
        ("gold.json", "items"),
    ):
        path = root / name
        payload = load_json(path)
        item = next(entry for entry in payload[collection] if entry["case_id"] == old_case_id)
        item["case_id"] = replacement
        _replace_json(path, payload)
    _refresh_manifest_and_preregistration(root)
    with pytest.raises(ValueError, match="derived fresh case id"):
        validate_fresh_identity_slice(
            V2_SOURCE,
            FRESH_HIDDEN_SOURCE,
            root,
            policy_freeze_path=POLICY_FREEZE,
            workspace_root=WORKSPACE_ROOT,
        )

    root = tmp_path / "natural-v3-fresh-gold-drift"
    prepare_fresh_identity_slice(
        V2_SOURCE,
        FRESH_HIDDEN_SOURCE,
        root,
        policy_freeze_path=POLICY_FREEZE,
        workspace_root=WORKSPACE_ROOT,
    )
    gold_path = root / "gold.json"
    gold = load_json(gold_path)
    gold["items"][0]["expected_action"] = "abstain"
    _replace_json(gold_path, gold)
    _refresh_manifest_and_preregistration(root)
    with pytest.raises(ValueError, match="derived artifact semantic equivalence"):
        validate_fresh_identity_slice(
            V2_SOURCE,
            FRESH_HIDDEN_SOURCE,
            root,
            policy_freeze_path=POLICY_FREEZE,
            workspace_root=WORKSPACE_ROOT,
        )


def test_validate_rejects_mutated_formal_artifact(tmp_path):
    """A tampered slice artifact must be refused by content, not by mode.

    Was: chmod public.json to 0644 and expect "formal slice artifact must be
    read-only". Git preserves no write bit, so every fresh clone presents these
    artifacts writable and that precondition could never hold. The property that
    matters is that changed bytes are rejected.
    """
    root = tmp_path / "natural-v3-fresh"
    prepare_fresh_identity_slice(
        V2_SOURCE,
        FRESH_HIDDEN_SOURCE,
        root,
        policy_freeze_path=POLICY_FREEZE,
        workspace_root=WORKSPACE_ROOT,
    )
    target = root / "public.json"
    target.chmod(0o644)
    original = target.read_bytes()
    mutated = original.replace(b'"case_count"', b'"case_Count"', 1)
    assert len(mutated) == len(original) and mutated != original, (
        "the mutation must actually change a byte, or this test proves nothing"
    )
    target.write_bytes(mutated)

    with pytest.raises(ValueError):
        validate_fresh_identity_slice(
            V2_SOURCE,
            FRESH_HIDDEN_SOURCE,
            root,
            policy_freeze_path=POLICY_FREEZE,
            workspace_root=WORKSPACE_ROOT,
        )


def test_validate_accepts_writable_formal_artifacts_after_a_clone(tmp_path):
    """The inverse: unchanged bytes at clone mode must validate."""
    root = tmp_path / "natural-v3-fresh"
    prepare_fresh_identity_slice(
        V2_SOURCE,
        FRESH_HIDDEN_SOURCE,
        root,
        policy_freeze_path=POLICY_FREEZE,
        workspace_root=WORKSPACE_ROOT,
    )
    for path in root.rglob("*"):
        if path.is_file():
            path.chmod(0o644)

    validate_fresh_identity_slice(
        V2_SOURCE,
        FRESH_HIDDEN_SOURCE,
        root,
        policy_freeze_path=POLICY_FREEZE,
        workspace_root=WORKSPACE_ROOT,
    )


def test_cli_prepares_and_validates_fresh_slice(tmp_path):
    root = tmp_path / "natural-v3-fresh"
    prepared = _run_cli(
        "prepare-natural-identity-fresh-slice",
        "--v2-source",
        str(V2_SOURCE),
        "--hidden-source",
        str(FRESH_HIDDEN_SOURCE),
        "--output-root",
        str(root),
        "--policy-freeze",
        str(POLICY_FREEZE),
        "--workspace-root",
        ".",
    )
    assert '"case_count": 12' in prepared.stdout
    validated = _run_cli(
        "validate-natural-identity-fresh-slice",
        "--v2-source",
        str(V2_SOURCE),
        "--hidden-source",
        str(FRESH_HIDDEN_SOURCE),
        "--root",
        str(root),
        "--policy-freeze",
        str(POLICY_FREEZE),
        "--workspace-root",
        ".",
    )
    assert '"status": "valid"' in validated.stdout
