"""Where the frozen corpora live, and how a test declines to run without one.

Overridable so the suite is runnable off this host: tests that read a corpus resolve
their paths through here and skip when the file is absent, rather than embedding one
machine's layout as a precondition. Two BEAM tests did embed it, which is what failed
the remote gate 48 seconds in -- the path simply does not exist on a runner.

Absent is a skip, not a pass and not a failure. The assertions that do run are
unchanged: sizes and SHA-256 digests are still checked in full. A corpus test that
relaxed its checks to survive a missing file would report green while verifying
nothing, which is worse than not running.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

DATASETS_ROOT = Path(os.environ.get("KE_DATASETS_ROOT", "/public/home/wwb/datasets"))


def dataset_path(*parts: str) -> Path:
    """Resolve a path under the dataset root without asserting it exists."""
    return DATASETS_ROOT.joinpath(*parts)


def require_dataset(*parts: str) -> Path:
    """Resolve a dataset path, skipping the calling test when it is not present."""
    path = dataset_path(*parts)
    if not path.exists():
        pytest.skip(f"dataset not present: {path} (set KE_DATASETS_ROOT to the corpus root)")
    return path
