"""Tests for the portable frozen-input guard.

The behaviour that matters is the inversion: correct bytes at 0644 must be
accepted, wrong bytes at 0444 must be rejected. The old guard did the opposite,
which is why a fresh clone could not verify anything.

The mode assertion is not deleted -- it is narrowed to output this process just
wrote, where mode is a real property of the current run rather than an artifact
of the last checkout.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tools.natural_memory_benchmark.frozen_input_guard import (
    harden_local_file,
    is_locally_hardened,
    require_descriptor_hardened,
    require_frozen_input,
    require_locally_hardened,
    require_regular_file,
)
from tools.natural_memory_benchmark.portable_immutability import (
    ImmutabilityViolation,
    sha256_bytes,
)

_CONTENT = b'{"case_id":"a","decision":"emit_l1"}\n'


def _committed_input(tmp_path: Path, *, mode: int = 0o644) -> Path:
    """A file as a fresh clone would present it: right bytes, mode not preserved."""
    path = tmp_path / "gold-l1.json"
    path.write_bytes(_CONTENT)
    os.chmod(path, mode)
    return path


def test_correct_bytes_at_clone_mode_are_accepted(tmp_path: Path) -> None:
    """The 237-failure case: 0644 plus the right content must verify."""
    path = _committed_input(tmp_path)
    assert path.stat().st_mode & 0o222, "precondition: writable, as after a clone"
    data = require_frozen_input(
        path, "gold input", expected_sha256=sha256_bytes(_CONTENT)
    )
    assert data == _CONTENT


def test_wrong_bytes_at_frozen_mode_are_rejected(tmp_path: Path) -> None:
    """The inverse the old guard got wrong: 0444 does not make content correct."""
    path = _committed_input(tmp_path, mode=0o644)
    path.write_bytes(b'{"case_id":"a","decision":"emit_l2"}\n')
    os.chmod(path, 0o444)
    assert not path.stat().st_mode & 0o222, "precondition: read-only"

    with pytest.raises(ImmutabilityViolation) as error:
        require_frozen_input(
            path, "gold input", expected_sha256=sha256_bytes(_CONTENT)
        )
    assert error.value.violation == "content_hash_mismatch"


def test_verification_without_an_expected_digest_still_checks_the_file(
    tmp_path: Path,
) -> None:
    """No digest available is weaker, but must not be weaker than the old guard."""
    missing = tmp_path / "absent.json"
    with pytest.raises(FileNotFoundError):
        require_frozen_input(missing, "gold input")

    path = _committed_input(tmp_path)
    assert require_frozen_input(path, "gold input") == _CONTENT


def test_symlinked_input_is_refused(tmp_path: Path) -> None:
    """A symlink can point at bytes no manifest described."""
    real = _committed_input(tmp_path)
    link = tmp_path / "link.json"
    link.symlink_to(real)
    with pytest.raises(ValueError, match="must not be a symlink"):
        require_frozen_input(link, "gold input")


def test_directory_is_refused(tmp_path: Path) -> None:
    target = tmp_path / "a-directory"
    target.mkdir()
    with pytest.raises(ValueError, match="must be a regular file"):
        require_regular_file(target, "gold input")


def test_local_hardening_is_asserted_on_freshly_written_output(
    tmp_path: Path,
) -> None:
    """Mode is kept where it is real: output this run produced."""
    path = tmp_path / "receipt.json"
    path.write_bytes(_CONTENT)
    with pytest.raises(ValueError, match="must have mode 0o444"):
        require_locally_hardened(path, "receipt")

    harden_local_file(path)
    require_locally_hardened(path, "receipt")
    assert is_locally_hardened(path)


def test_descriptor_hardening_closes_the_path_swap_window(tmp_path: Path) -> None:
    path = tmp_path / "staged.json"
    path.write_bytes(_CONTENT)
    harden_local_file(path)
    descriptor = os.open(path, os.O_RDONLY)
    try:
        require_descriptor_hardened(descriptor, "staged receipt")
        # Swapping the path now cannot fool a descriptor-based check.
        replacement = tmp_path / "other.json"
        replacement.write_bytes(b"{}\n")
        os.chmod(replacement, 0o644)
        os.replace(replacement, path)
        require_descriptor_hardened(descriptor, "staged receipt")
    finally:
        os.close(descriptor)


def test_descriptor_hardening_rejects_a_writable_descriptor(tmp_path: Path) -> None:
    path = tmp_path / "staged.json"
    path.write_bytes(_CONTENT)
    descriptor = os.open(path, os.O_RDONLY)
    try:
        with pytest.raises(ValueError, match="must have mode"):
            require_descriptor_hardened(descriptor, "staged receipt")
    finally:
        os.close(descriptor)


def test_is_locally_hardened_reports_without_deciding(tmp_path: Path) -> None:
    """Diagnostics must be able to observe mode without gating on it."""
    path = tmp_path / "artifact.json"
    path.write_bytes(_CONTENT)
    assert is_locally_hardened(path) is False
    harden_local_file(path)
    assert is_locally_hardened(path) is True
    assert is_locally_hardened(tmp_path / "absent.json") is False
