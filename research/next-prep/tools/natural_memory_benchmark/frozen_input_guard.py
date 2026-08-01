"""The portable replacement for the duplicated ``_require_read_only`` guard.

Twenty-one modules defined that helper identically, and all of them read
``st_mode & 0o222`` to decide whether an input was frozen. That check does not
survive a clone: Git records only the executable bit, so a 0444 input arrives as
0644 and the guard rejects it. 237 of the 301 pre-migration failures were this.

The replacement separates two things the old helper conflated:

``require_frozen_input`` reads a *committed* file. Mode is not a property of the
file's history there, only of the last checkout, so it is not consulted; the
content hash is. Callers that already know the expected digest get a real
guarantee, and callers that do not at least get existence and regular-file
checks rather than a check that is guaranteed to fail on a fresh clone.

``require_locally_hardened`` reads a file *this process just wrote*. Mode there
describes the current run and is worth asserting, so it is kept.

Keeping both under one roof is the point: the previous single helper was applied
to both situations, which is how a meaningful local check became a portability
defect everywhere else.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

from .portable_immutability import (
    FROZEN_FILE_MODE,
    ImmutabilityViolation,
    sha256_bytes,
)


def require_regular_file(path: Path, label: str) -> Path:
    """Existence and regular-file checks that hold on any checkout.

    Rejects symlinks: a symlink can point at something the manifest never
    described, so following one silently would defeat content verification.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"{label} missing: {path}")
    if path.is_symlink():
        raise ValueError(f"{label} must not be a symlink: {path}")
    if not path.is_file():
        raise ValueError(f"{label} must be a regular file: {path}")
    return path


def require_frozen_input(
    path: Path,
    label: str,
    *,
    expected_sha256: str | None = None,
) -> bytes:
    """Read a committed input and verify it by content, never by mode.

    Deliberately accepts a 0644 file with the right bytes and rejects a 0444 file
    with the wrong ones -- the reverse of what the old guard did. Returns the
    verified bytes so a caller need not read the file again; a second read is a
    second chance to read something different.
    """
    path = require_regular_file(path, label)
    data = path.read_bytes()
    if expected_sha256 is not None:
        actual = sha256_bytes(data)
        if actual != expected_sha256:
            raise ImmutabilityViolation(
                "content_hash_mismatch",
                f"{label} at {path}: expected {expected_sha256}, found {actual}",
            )
    return data


def require_locally_hardened(path: Path, label: str) -> None:
    """Assert 0444 on a file this run just wrote.

    Valid only for output this process produced and has not handed to Git. Never
    use it on a committed input: that is the portability defect this module
    exists to remove.
    """
    path = require_regular_file(path, label)
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode != FROZEN_FILE_MODE:
        raise ValueError(
            f"{label} must have mode {oct(FROZEN_FILE_MODE)} immediately after "
            f"freezing, found {oct(mode)}: {path}"
        )


def require_descriptor_hardened(descriptor: int, label: str) -> None:
    """Same assertion against an open descriptor.

    Checking the descriptor rather than the path closes the window where a path
    is swapped between the check and the read.
    """
    opened = os.fstat(descriptor)
    if not stat.S_ISREG(opened.st_mode):
        raise ValueError(f"{label} must be a regular file")
    mode = stat.S_IMODE(opened.st_mode)
    if mode != FROZEN_FILE_MODE:
        raise ValueError(
            f"{label} must have mode {oct(FROZEN_FILE_MODE)}, found {oct(mode)}"
        )


def harden_local_file(path: Path) -> None:
    """Apply 0444 after writing, as local protection only.

    Defense in depth against a stray write in this working tree. Correctness
    never depends on it, because it does not survive a clone.
    """
    os.chmod(Path(path), FROZEN_FILE_MODE)


def is_locally_hardened(path: Path) -> bool:
    """Report the mode without deciding anything.

    For diagnostics and for tests that need to observe local hardening without
    making it a precondition for reading.
    """
    path = Path(path)
    return path.is_file() and stat.S_IMODE(path.stat().st_mode) == FROZEN_FILE_MODE
