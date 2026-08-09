#!/usr/bin/env bash
# The checks that hold on any runner, with no private dependency and no dataset.
#
# KEOL is private: a runner without credentials cannot check it out, and the
# attempt is what failed the first remote CI run on main -- before a single check
# had executed. So the remote gate is this script, and it deliberately does not
# reference KEOL_SOURCE at all.
#
# What that costs is exactly one file: tests/contract/test_online_keol_bridge.py
# skips itself via importorskip, so its 3 tests do not run here. Everything else
# runs, including the full type check and the wheel contract. Use check.sh
# locally, with KEOL_SOURCE set, to cover those 3 as well.
#
# "Remote CI green" and "the KEOL bridge is verified" are therefore two separate
# claims. State them separately in a PR description; do not let this script's
# green stand in for the second.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

uv sync --frozen
uv run python scripts/ci/verify_layout.py
uv run pytest -q
uv run ruff check src service ontology tests scripts
uv run pyright
uv build
uv run python scripts/ci/verify_wheel.py
