#!/usr/bin/env bash
# Verify the evaluation environment contract, then run the source-replay and
# conformance tests that depend on it.
#
# The dependency is required rather than optional here: source validation is part
# of the evidence chain, so a missing reader must fail this job. A skip would
# report green while leaving the data replay path unverified, which is the exact
# outcome the install contract exists to prevent.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

research_root="$repo_root/research/next-prep"
if [[ ! -d "$research_root/tools/natural_memory_benchmark" ]]; then
  echo "conformance_not_verified: research tools not present at $research_root" >&2
  exit 2
fi

cd "$research_root"

# Reuse an existing interpreter when one is provided. `uv run --project` would
# otherwise create a per-worktree .venv. The reason to avoid that is checkout
# isolation, not disk: the environments here are hardlinked to one shared store, so
# an extra one costs about 29 MB rather than its apparent 4.8G. A build environment
# still does not belong inside a checkout, which is reason enough.
# CI sets nothing and gets a fresh managed environment, which is correct there.
# In a worktree, repo_root is the worktree rather than the checkout that owns the
# environment, so resolve the main root via the shared git dir.
main_root="$repo_root"
if common_dir="$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null)"; then
  main_root="$(dirname "$common_dir")"
fi

if [[ -n "${CONFORMANCE_PYTHON:-}" ]]; then
  python_cmd=("$CONFORMANCE_PYTHON")
elif [[ -x "$main_root/.venv/bin/python" ]]; then
  python_cmd=("$main_root/.venv/bin/python")
elif [[ -x "$repo_root/.venv/bin/python" ]]; then
  python_cmd=("$repo_root/.venv/bin/python")
else
  python_cmd=(uv run --project "$repo_root" --group evaluation python)
fi

# Report the measured environment before running anything, so a conformance
# result in the log names the reader version that produced it.
"${python_cmd[@]}" -c '
import json
from tools.natural_memory_benchmark.evaluation_environment import (
    verify_evaluation_environment,
)

print(json.dumps(verify_evaluation_environment().model_dump(mode="json"), indent=2))
'

# The files hosting the tests that could not run without the reader, taken from
# the frozen disposition record rather than chosen by hand.
"${python_cmd[@]}" -m pytest \
  tests/natural_memory_benchmark/test_evaluation_environment.py \
  tests/natural_memory_benchmark/test_authoritative_conformance_runner.py \
  tests/natural_memory_benchmark/test_authoritative_migration.py \
  tests/natural_memory_benchmark/test_evidence_corpus.py \
  tests/natural_memory_benchmark/test_loaders.py \
  tests/natural_memory_benchmark/test_slices.py \
  tests/natural_memory_benchmark/test_scoring.py \
  tests/natural_memory_benchmark/test_cli.py \
  -q -p no:cacheprovider
