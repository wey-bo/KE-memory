#!/usr/bin/env bash
# The corpus gate: absolute counts over the frozen sources, where absent data is a failure.
#
# This exists because the other two gates cannot establish these facts. Both allow corpus tests
# to skip when the archives are missing -- correctly, since a runner does not have 16 MB of frozen
# linguistic data -- but a skipped test proves nothing about the counts. So the reproducibility
# claim for source ingestion needs a gate where absence fails rather than skips.
#
# Run this on a host that holds the corpora. It is deliberately not part of the remote gate:
# uploading the archives to make CI green would be the wrong fix.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

datasets_root="${KE_DATASETS_ROOT:-/public/home/wwb/datasets}"
sources_root="$datasets_root/ontology-sources"

# Fail before pytest runs, so a missing corpus reports as a missing corpus rather than as a
# collection of skipped tests.
missing=()
for artifact in \
  "wordnet-3.0-nltk.zip" \
  "propbank-frames-3.4.0.tar.gz" \
  "schemaorg-30.0-current-https.jsonld"
do
  [[ -f "$sources_root/$artifact" ]] || missing+=("$artifact")
done

if (( ${#missing[@]} > 0 )); then
  echo "corpus_gate_failed: missing from $sources_root:" >&2
  printf '  %s\n' "${missing[@]}" >&2
  echo "This gate requires the frozen corpora. Set KE_DATASETS_ROOT to their root." >&2
  exit 1
fi

# -r a reports skips explicitly, which the next check reads. --no-header keeps the counts near
# the end of the output where a reader looks first.
output="$(KE_DATASETS_ROOT="$datasets_root" uv run pytest -q -r a --no-header \
  tests/integration/test_frozen_corpus_counts.py 2>&1)"
status=$?
echo "$output"
(( status == 0 )) || exit "$status"

# A green run whose tests all skipped would report nothing about the counts, which is the exact
# weakness this gate exists to close. The archives were verified present above, so a skip here
# means a test declined for some other reason and the gate has not done its job.
if grep -qE '[0-9]+ skipped' <<<"$output"; then
  echo "corpus_gate_failed: tests skipped although the corpora are present" >&2
  exit 1
fi
