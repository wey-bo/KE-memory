# Core Test Suite Slimming Design

## Goal

Reduce the maintenance and review cost of the tests produced by Core Tasks 1-9 while
preserving every distinct high-risk contract. There is no numeric deletion target. A test
is removed or merged only when another retained test proves the same behavior with the
same meaningful failure signal.

## Baseline

At Task 9 completion, the non-live suite contains 24 test files, about 12,427 lines, 400
test functions, and 586 collected passing cases plus one opt-in embedding skip. A full
offline run takes about 9.8-10.0 seconds; one required BEAM integration test accounts for
about 3.9 seconds. The primary problem is maintenance and review volume, not runtime.

The largest files are the semantic DAG, Elasticsearch adapter, structured LLM client,
session aggregation, Turn KE extraction, artifact store, lifecycle, embedding index, and
SQLite rebuild tests.

## Non-Goals

- Do not modify production code or observable behavior.
- Do not weaken acceptance counts, golden flows, contract tests, secret checks, or source
  provenance guarantees.
- Do not remove a case merely because it is slow or because a lower test count looks
  preferable.
- Do not access live model, Elasticsearch, network, or prohibited memory/fusion-memory
  projects.
- Do not turn several independently diagnosable contracts into an opaque mega-test.

## Retention Rules

Each retained test must protect at least one distinct contract, boundary, or failure mode.
Each removed test must name the retained test or parameterized case that supersedes it.

Keep separate tests when they distinguish any of the following:

- successful behavior versus fail-closed behavior;
- validation before side effects versus rollback after partial side effects;
- pre-commit failure versus post-commit cleanup failure;
- canonical, alias, unresolved, outage, drift, and schema-mismatch ontology outcomes;
- identity, revision, lifecycle, reference-level, provenance, temporal, or evidence-closure
  invariants;
- deterministic ordering, hashing, serialization, cache rebuild, or cross-process ownership;
- secret redaction at different trust boundaries;
- embedding path containment, fingerprint drift, numeric validity, and query/document
  separation;
- unit, contract, integration, and golden responsibilities that exercise different layers.

Merge tests when setup and expected behavior differ only by input values within one
equivalence class. Prefer one parameterized test with descriptive case IDs. Extract shared
fixtures only when they make the protected contract easier to see; do not hide important
inputs behind generic builders.

## Parallel Work Groups

The cleanup uses four mutually exclusive path groups:

1. Domain, ingestion, configuration, CLI, and secret hygiene:
   `tests/unit/domain`, `tests/unit/ingestion`, `tests/unit/test_settings.py`,
   `tests/unit/test_cli.py`, `tests/unit/test_secret_hygiene.py`, and
   `tests/unit/test_init_local_secrets.py`.
2. Infrastructure and ontology:
   `tests/unit/infra`, `tests/unit/ontology`, and `tests/contract/test_ontology_contract.py`.
3. Extraction and aggregation:
   `tests/unit/extraction` and `tests/unit/aggregation`.
4. Storage, embedding, and integration:
   `tests/unit/storage`, `tests/unit/embedding`, and `tests/integration`.

Up to three agents work concurrently because the root controller occupies one available
slot. Each agent edits only its assigned test paths, does not change production code, and
runs only its focused suite. Agents do not stage or commit concurrently in the shared
worktree. Each writes a report that lists retained contracts, merged/deleted cases, exact
focused test results, and any tests it deliberately left unchanged.

The root controller reviews all reports and diffs, resolves any overlap, runs the fourth
group if it was not part of the first wave, and creates one integrated cleanup commit.

## Verification Gate

Before the cleanup is accepted:

1. Confirm `git diff` contains test and cleanup-report changes only; production files are
   unchanged.
2. Confirm every deletion has a documented retained equivalent and every parameter set has
   descriptive IDs.
3. Run each affected focused suite after its edits.
4. Run the complete offline suite once after integration.
5. Run Ruff format/check, Pyright, `git diff --check`, and forbidden-reference/secret scans.
6. Compare collection and line-count metrics with the baseline as descriptive evidence,
   not as a pass/fail quota.
7. Obtain an independent review focused on lost contracts, over-compressed tests, and
   production-code drift.

## Failure Handling

If a focused or full-suite failure appears, restore the contract in the test design or fix
the cleanup edit; do not change production behavior to accommodate a slimmer suite. If two
tests initially appear redundant but fail for different root causes or at different state
boundaries, retain both. If an agent cannot identify a clear retained equivalent, it leaves
the test unchanged and records the uncertainty.

