#!/usr/bin/env bash
# Verify the memory-assertion/v1 specification package.
#
# The package moved into spec/memory-assertion-v1/ verbatim so that its own
# ROOT = Path(__file__).resolve().parents[1] keeps resolving to the subtree
# root. Everything here therefore runs with that directory as cwd, exactly as
# the package expects: its two test modules import themselves as `tools.*`.
#
# This checks the specification contract only. It does not exercise a semantic
# validator, a production Canonical Text parser, a Snapshot provisioner or an
# NL2KE compiler -- none of those are implemented.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
spec_root="$repo_root/spec/memory-assertion-v1"

cd "$spec_root"

python tools/validate_specifications.py
python -m unittest tools.test_validate_specifications tools.test_canonical_text_reference
