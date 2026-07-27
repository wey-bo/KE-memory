#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

keol_source="${KEOL_SOURCE:-$repo_root/.deps/KEOL/src}"
if [[ ! -f "$keol_source/onto/models.py" ]]; then
  echo "KEOL_SOURCE must point to the pinned KEOL src directory" >&2
  exit 2
fi

export PYTHONPATH="$keol_source${PYTHONPATH:+:$PYTHONPATH}"

uv sync --frozen
uv run python scripts/ci/verify_layout.py
uv run pytest -q
uv run ruff check src service ontology tests scripts
uv run pyright
uv build
