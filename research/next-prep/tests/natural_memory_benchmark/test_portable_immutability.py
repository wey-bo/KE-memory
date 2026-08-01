"""Regression tests for portable immutability verification.

These exist because the previous guarantee did not survive a clone. The tests
therefore work the way a fresh clone does -- they write artifacts, drop the mode
bits to 0644, and demand verification still passes -- and then check that each
way of tampering fails with its own violation class.

Every test constructs its frozen set from scratch in a temporary directory. None
of them read the real frozen artifacts under ``artifacts/``: a test that mutates
evidence to prove mutation is detected has damaged the evidence.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tools.natural_memory_benchmark.portable_immutability import (
    FROZEN_FILE_MODE,
    FrozenArtifactEntryV1,
    FrozenSetManifestV1,
    ImmutabilityViolation,
    build_frozen_set_manifest,
    canonical_json_bytes,
    compute_entries_sha256,
    describe_frozen_file,
    freeze_json_set,
    require_frozen_set,
    scan_frozen_set,
    sha256_bytes,
    verify_frozen_set,
    write_frozen_file,
)

MANIFEST_NAME = "frozen-set-manifest.json"

_PAYLOADS: dict[str, object] = {
    "gold-l1.json": {"cases": [{"case_id": "a", "decision": "emit_l1"}]},
    "public-l1.json": {"cases": [{"case_id": "a", "text": "Coffee is drunk at noon."}]},
    "manifest-l1.json": {"dataset_id": "portable-test-v1", "case_count": 1},
}

_TYPES: dict[str, tuple[str, str]] = {
    "gold-l1.json": ("l1_gold", "typed-extractor-l1-gold-v1"),
    "public-l1.json": ("l1_public", "typed-extractor-l1-public-v1"),
    "manifest-l1.json": ("l1_manifest", "typed-extractor-l1-manifest-v1"),
}


def _freeze(root: Path) -> FrozenSetManifestV1:
    return freeze_json_set(
        root,
        frozen_set_id="portable-immutability-test-v1",
        payloads=dict(_PAYLOADS),
        artifact_types=dict(_TYPES),
    )


def _make_writable(root: Path) -> None:
    """Reproduce what a Git clone does to mode bits: everything becomes 0644."""
    for path in sorted(root.rglob("*")):
        if path.is_file():
            os.chmod(path, 0o644)


def _rewrite(path: Path, data: bytes) -> None:
    """Overwrite a frozen file, bypassing the writer, as tampering would."""
    os.chmod(path, 0o644)
    path.write_bytes(data)


def test_freeze_json_set_applies_read_only_mode_as_defense_in_depth(
    tmp_path: Path,
) -> None:
    _freeze(tmp_path / "set")
    for name in _PAYLOADS:
        mode = (tmp_path / "set" / name).stat().st_mode & 0o777
        assert mode == FROZEN_FILE_MODE, name
    assert (tmp_path / "set" / MANIFEST_NAME).stat().st_mode & 0o777 == FROZEN_FILE_MODE


def test_verification_passes_after_a_clone_drops_mode_bits(tmp_path: Path) -> None:
    """The point of the change: correct bytes at 0644 must verify."""
    root = tmp_path / "set"
    _freeze(root)
    _make_writable(root)

    for path in sorted(root.rglob("*")):
        if path.is_file():
            assert path.stat().st_mode & 0o222, f"precondition: {path} should be writable"

    verified = require_frozen_set(root, MANIFEST_NAME)
    assert set(verified) == set(_PAYLOADS)
    assert json.loads(verified["gold-l1.json"]) == _PAYLOADS["gold-l1.json"]


def test_verification_does_not_consult_inode_permissions(tmp_path: Path) -> None:
    """Wrong bytes at 0444 must fail; the old guard would have accepted them."""
    root = tmp_path / "set"
    _freeze(root)
    target = root / "gold-l1.json"
    original = target.read_bytes()
    # Same length so byte_count cannot be what rejects it -- the hash must.
    mutated = original.replace(b"emit_l1", b"emit_l2")
    assert len(mutated) == len(original) and mutated != original
    _rewrite(target, mutated)
    os.chmod(target, FROZEN_FILE_MODE)

    assert not target.stat().st_mode & 0o222, "precondition: file is read-only"
    with pytest.raises(ImmutabilityViolation) as error:
        require_frozen_set(root, MANIFEST_NAME)
    assert error.value.violation == "content_hash_mismatch"


def test_any_changed_byte_fails_closed(tmp_path: Path) -> None:
    root = tmp_path / "set"
    _freeze(root)
    _make_writable(root)
    target = root / "public-l1.json"
    original = target.read_bytes()
    # Same length, one byte different: byte_count cannot catch this, only the hash.
    mutated = original.replace(b"noon", b"nooN")
    assert len(mutated) == len(original) and mutated != original
    _rewrite(target, mutated)

    with pytest.raises(ImmutabilityViolation) as error:
        require_frozen_set(root, MANIFEST_NAME)
    assert error.value.violation == "content_hash_mismatch"
    assert "public-l1.json" in error.value.detail


def test_truncation_is_reported_as_a_byte_count_mismatch(tmp_path: Path) -> None:
    root = tmp_path / "set"
    _freeze(root)
    _make_writable(root)
    _rewrite(root / "gold-l1.json", b"{}\n")

    with pytest.raises(ImmutabilityViolation) as error:
        require_frozen_set(root, MANIFEST_NAME)
    assert error.value.violation == "byte_count_mismatch"


def test_deleting_a_frozen_file_fails_closed(tmp_path: Path) -> None:
    root = tmp_path / "set"
    _freeze(root)
    _make_writable(root)
    (root / "gold-l1.json").unlink()

    with pytest.raises(ImmutabilityViolation) as error:
        require_frozen_set(root, MANIFEST_NAME)
    assert error.value.violation == "frozen_file_missing"


def test_adding_an_undeclared_file_fails_closed(tmp_path: Path) -> None:
    """A hash-per-entry loop alone cannot see this; the directory scan can."""
    root = tmp_path / "set"
    _freeze(root)
    _make_writable(root)
    (root / "extra-l1.json").write_bytes(canonical_json_bytes({"smuggled": True}))

    with pytest.raises(ImmutabilityViolation) as error:
        require_frozen_set(root, MANIFEST_NAME)
    assert error.value.violation == "unexpected_file_in_frozen_set"
    assert error.value.detail == "extra-l1.json"


def test_replacing_a_file_with_a_differently_named_one_fails_closed(
    tmp_path: Path,
) -> None:
    root = tmp_path / "set"
    _freeze(root)
    _make_writable(root)
    data = (root / "gold-l1.json").read_bytes()
    (root / "gold-l1.json").unlink()
    (root / "gold-l1-renamed.json").write_bytes(data)

    with pytest.raises(ImmutabilityViolation) as error:
        require_frozen_set(root, MANIFEST_NAME)
    # Deletion is detected first: the entry loop runs before the scan.
    assert error.value.violation == "frozen_file_missing"


def test_removing_a_manifest_entry_invalidates_the_manifest(tmp_path: Path) -> None:
    """Tampering that hides a deletion by editing the manifest must also fail."""
    root = tmp_path / "set"
    manifest = _freeze(root)
    _make_writable(root)
    (root / "gold-l1.json").unlink()

    kept = tuple(e for e in manifest.entries if e.relative_path != "gold-l1.json")
    payload = manifest.model_dump(mode="json")
    payload["entries"] = [e.model_dump(mode="json") for e in kept]
    # entries_sha256 left describing the original list.
    _rewrite(root / MANIFEST_NAME, canonical_json_bytes(payload))

    with pytest.raises(ImmutabilityViolation) as error:
        require_frozen_set(root, MANIFEST_NAME)
    assert error.value.violation == "frozen_manifest_invalid"


def test_recomputing_entries_sha256_does_not_launder_a_removed_entry(
    tmp_path: Path,
) -> None:
    """Even a fully self-consistent shrunken manifest leaves the file behind."""
    root = tmp_path / "set"
    manifest = _freeze(root)
    _make_writable(root)

    kept = tuple(e for e in manifest.entries if e.relative_path != "gold-l1.json")
    forged = build_frozen_set_manifest(
        frozen_set_id=manifest.frozen_set_id, entries=kept
    )
    _rewrite(root / MANIFEST_NAME, canonical_json_bytes(forged))

    with pytest.raises(ImmutabilityViolation) as error:
        require_frozen_set(root, MANIFEST_NAME)
    assert error.value.violation == "unexpected_file_in_frozen_set"
    assert error.value.detail == "gold-l1.json"


def test_swapping_a_hash_in_the_manifest_invalidates_it(tmp_path: Path) -> None:
    root = tmp_path / "set"
    manifest = _freeze(root)
    _make_writable(root)
    payload = manifest.model_dump(mode="json")
    payload["entries"][0]["sha256"] = "0" * 64
    _rewrite(root / MANIFEST_NAME, canonical_json_bytes(payload))

    with pytest.raises(ImmutabilityViolation) as error:
        require_frozen_set(root, MANIFEST_NAME)
    assert error.value.violation == "frozen_manifest_invalid"


def test_frozen_target_cannot_be_overwritten_even_with_identical_bytes(
    tmp_path: Path,
) -> None:
    root = tmp_path / "set"
    data = canonical_json_bytes({"case_id": "a"})
    write_frozen_file(root, "gold-l1.json", data)

    with pytest.raises(ImmutabilityViolation) as error:
        write_frozen_file(root, "gold-l1.json", data)
    assert error.value.violation == "frozen_target_exists"

    with pytest.raises(ImmutabilityViolation) as error:
        write_frozen_file(root, "gold-l1.json", canonical_json_bytes({"case_id": "b"}))
    assert error.value.violation == "frozen_target_exists"
    assert (root / "gold-l1.json").read_bytes() == data


def test_a_populated_root_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "set"
    _freeze(root)
    with pytest.raises(ImmutabilityViolation) as error:
        _freeze(root)
    assert error.value.violation == "frozen_root_already_populated"


def test_failed_write_leaves_no_partial_file(tmp_path: Path, monkeypatch) -> None:
    """A crash mid-write must not leave a partial artifact to be verified later."""
    root = tmp_path / "set"

    def explode(*args: object, **kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(
        "tools.natural_memory_benchmark.portable_immutability.os.link", explode
    )
    with pytest.raises(OSError):
        write_frozen_file(root, "gold-l1.json", canonical_json_bytes({"a": 1}))

    assert not (root / "gold-l1.json").exists()
    assert scan_frozen_set(root) == (), "no partial file may survive"
