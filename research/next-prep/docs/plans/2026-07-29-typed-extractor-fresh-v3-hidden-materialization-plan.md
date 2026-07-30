# Typed Extractor Fresh-V3 Hidden Materialization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking. Execute inline in the existing
> worktree because parallel sessions own adjacent L1 and Query files.

**Goal:** Atomically publish the exact preregistered fresh-v3 L1 24/L2 18
authored hidden dataset and its pre-model chronology without calling a model,
scoring proposals, or writing authoritative memory state.

**Architecture:** Add a standalone materializer that treats the committed
relocation receipt as an immutable phase-transition authority. It replays the
receipt's Git/authoring/protected-state bindings while binding exactly the two
new materialization files, stages ten canonical payloads and one chronology,
validates the full tree, and publishes it with
`renameat2(RENAME_NOREPLACE)`.

**Tech Stack:** Python 3.12, Pydantic v2, pytest, canonical JSON/SHA-256,
Git plumbing, `tempfile`, and Linux `renameat2(RENAME_NOREPLACE)`.

## Global Constraints

- Work only in
  `/public/home/wwb/KE_mem/ke-memory-demo/.worktrees/next-prep-normalization-20260729`.
- Do not create another worktree or read the retired source workspace.
- Do not modify preregistration, authoring module/test, relocation module/test,
  v1/v2 frozen artifacts, scorer, query, identity, L1 admission/linking, or
  runtime package files.
- The active receipt SHA-256 remains
  `c810f421d5a3b0726b862ec2f12c89e0d638e0747892637e2a32977587b7ef8c`.
- Materialize exactly L1 24 and L2 18 cases with all 8/9 family counts; do not
  filter, replace, resample, or add adjudications.
- Create no model-run, dispatch, raw-response, proposal, provenance, score,
  report, or pipeline path, and make no model request.
- Automatic L1, L2, revision, source-revision, closure, identity, membership,
  snapshot, and aggregate write counts remain exactly `0`.
- Manual identity adjudications remain unmaterialized; embedding remains
  non-authoritative; external memory systems are not rerun;
  `LONGMEMEVAL-6d550036` remains
  `structured_l2_identity_unresolved`.

---

### Task 1: Specify The Phase Transition And Observe RED

**Files:**

- Create:
  `tests/natural_memory_benchmark/test_typed_extractor_fresh_v3_materialization.py`
- Test target:
  `tools/natural_memory_benchmark/typed_extractor_fresh_v3_materialization.py`

**Interfaces:**

- Expects private transition helper
  `_validate_active_receipt_transition(Path, Path, *,
  require_evaluation_absent: bool) -> ActiveTransition`.
- Expects private chronology helper
  `_build_materialization_receipt(...) -> FreshV3MaterializationReceipt`.

- [x] **Step 1: Write approved-receipt and transition tests**

  Import the absent materializer module and define constants for the repository,
  workspace, official preregistration, active receipt, official evaluation
  root, and a test label `2026-07-29T15:00:00Z`. Assert the transition binds the
  fixed receipt SHA/schema, import commit, three Git blobs, current
  materializer/test hashes, path-neutral authoring binding, candidate queue,
  live guard, and exactly the two declared materialization paths.

  Add focused `_read_approved_receipt` tests that reject copied receipt files
  with wrong mode, noncanonical bytes, changed bytes, unknown fields, or
  coercive counts. The official receipt and all frozen inputs remain untouched.

- [x] **Step 2: Write strict chronology-builder tests**

  Build the pure fresh-v3 bundle, write its ten canonical payloads into a
  temporary tree, and call `_build_materialization_receipt`. Assert exact
  schema/status, `24/18`, family maps, Git/receipt/materializer bindings, output
  hashes, and all authorization fields:

  ```python
  assert chronology["schema_version"] == (
      "typed-extractor-fresh-v3-materialization-receipt-v1"
  )
  assert chronology["status"] == "frozen_pre_model"
  assert chronology["hidden_source_artifacts_created"] is True
  assert chronology["model_request_count"] == 0
  assert chronology["evaluation_result_write_count"] == 0
  assert set(chronology["automatic_write_counts"].values()) == {0}
  assert chronology["pipeline_integration_authorized"] is False
  assert chronology["manual_identity_adjudications_materialized"] is False
  assert chronology["longmemeval_status"] == (
      "structured_l2_identity_unresolved"
  )
  ```

- [x] **Step 3: Run the focused file and verify RED**

  Run from `research/next-prep`:

  ```bash
  PYTHONPATH=. ../../.venv/bin/python -m pytest -q -p no:cacheprovider \
    --basetemp /tmp/ke-memory-fresh-v3-materialization-red \
    tests/natural_memory_benchmark/test_typed_extractor_fresh_v3_materialization.py
  ```

  Expected: collection fails only because
  `typed_extractor_fresh_v3_materialization` does not exist. Confirm the formal
  evaluation root remains absent.

### Task 2: Implement Receipt Transition And Chronology Models

**Files:**

- Create:
  `tools/natural_memory_benchmark/typed_extractor_fresh_v3_materialization.py`
- Test:
  `tests/natural_memory_benchmark/test_typed_extractor_fresh_v3_materialization.py`

**Interfaces:**

- Produces strict `MaterializedArtifact`, `ActiveTransition`,
  `MaterializationSequence`, `AutomaticWriteCounts`, and
  `FreshV3MaterializationReceipt` models.
- Produces `_validate_active_receipt_transition`, `_layer_payloads`, and
  `_build_materialization_receipt` for Task 3.

- [x] **Step 1: Define constants and strict models**

  Add exact constants for receipt SHA, relative module/test paths, layer names,
  zero writes, schema/status, and `renameat2` flags. Use
  `ConfigDict(extra="forbid", frozen=True, strict=True)`. Validate timestamps
  with exact `%Y-%m-%dT%H:%M:%SZ` round-trip. Define artifact bindings with
  SHA-256, `size_bytes >= 1`, and mode `0444`.

- [x] **Step 2: Implement approved canonical receipt reading**

  `_read_approved_receipt(path)` must call the relocation module's strict
  regular-file reader, require mode `0444`, exact canonical bytes, exact
  approved SHA, and schema
  `typed-extractor-fresh-v3-authoring-receipt-v2`. It returns the parsed receipt,
  opened bytes, and opened stat for final inode/path revalidation.

- [x] **Step 3: Implement the phase-transition replay**

  `_validate_active_receipt_transition(repository_root, workspace_root,
  require_evaluation_absent)` must:

  1. validate lexical repository/workspace roots through relocation helpers;
  2. load the official preregistration and receipt;
  3. require the receipt's materialization path list to equal module/test;
  4. bind those two current regular non-symlink files by SHA-256;
  5. replay Git commit/blob/current-byte and normalized path bindings;
  6. rebuild the authoring bundle and compare code, dependency, blueprint,
     prior input, counts, and family maps to the receipt;
  7. rebuild protected state and compare queue/guard hashes and counts;
  8. require the official evaluation root absent only when the boolean is true;
  9. assert the opened receipt inode still matches its pathname.

  Return an immutable `ActiveTransition` containing the receipt and the two new
  materializer hashes. Do not call the original pre-implementation validator.

- [x] **Step 4: Implement layer mapping and chronology construction**

  Use this exact mapping:

  ```python
  LAYER_VALUES = {
      "l1": {
          "source-cases-l1.json": "source",
          "public-l1.json": "public",
          "authority-l1.json": "authority",
          "gold-l1.json": "gold",
          "manifest-l1.json": "manifest",
      },
      "l2": {
          "source-cases-l2.json": "source",
          "public-l2.json": "public",
          "authority-l2.json": "authority",
          "gold-l2.json": "gold",
          "manifest-l2.json": "manifest",
      },
  }
  ```

  The chronology includes logical normalized evaluation path, preregistration,
  active receipt, Git snapshot, materializer hashes, ten artifact bindings,
  family/manifest hashes, sequence claims, one true hidden-source transition,
  and every zero/false boundary from the design.

- [x] **Step 5: Run transition/model nodes to GREEN**

  Run only receipt-reader, transition, strict-model, and chronology-builder
  nodes. Expected: those nodes pass; publication nodes still fail because the
  writer/validator are absent. Confirm no formal evaluation root or staging
  path exists.

- [x] **Step 6: Commit the transition layer**

  ```bash
  git add \
    research/next-prep/tools/natural_memory_benchmark/typed_extractor_fresh_v3_materialization.py \
    research/next-prep/tests/natural_memory_benchmark/test_typed_extractor_fresh_v3_materialization.py
  git commit -m "Bind fresh-v3 materialization transition"
  ```

### Task 3: Implement Atomic Publication And Validation

**Files:**

- Modify:
  `tools/natural_memory_benchmark/typed_extractor_fresh_v3_materialization.py`
- Modify:
  `tests/natural_memory_benchmark/test_typed_extractor_fresh_v3_materialization.py`

**Interfaces:**

- Completes both public functions fixed by the design.
- Produces one exact staged tree and no-replace directory publication.

- [x] **Step 1: Write publication, atomicity, and drift tests**

  Add an exact-layout success test that calls
  `materialize_fresh_v3_hidden` in a temporary evaluation root and asserts:

  ```python
  assert result == {
      "status": "valid",
      "evaluation_id": "typed-extractor-v3-fresh-hidden-v1",
      "l1_case_count": 24,
      "l2_case_count": 18,
      "model_runs_present_at_freeze": False,
      "model_request_count": 0,
  }
  assert {path.name for path in evaluation_root.iterdir()} == {
      "chronology-receipt.json", "l1", "l2"
  }
  ```

  Compare all ten payloads with the pure authoring bundle and assert JSON mode
  `0444`, directory mode `0775`, exact family totals, and absent `model-runs`.
  Cover existing target, invalid UTC, injected publication failure,
  concurrently created target, stale sibling staging, protected-state drift,
  payload/mode/chronology drift, unregistered root/layer artifacts, and any
  `model-runs` path. Failures after staging preserve the current staging root
  for audit, which may be partial and is always non-authoritative; tests must
  prove cleanup never deletes through a replaceable pathname, never masks the
  primary failure, never touches stale siblings, and cannot redirect staging
  writes through a replaced parent or staging path.

- [x] **Step 2: Run the new nodes and verify RED**

  Expected: failures identify missing writer, validator, or publication helpers;
  all Task 2 transition/chronology tests remain green.

- [x] **Step 3: Implement canonical staging writes**

  Create a unique sibling directory with prefix
  `.<evaluation-name>.staging-` through an opened parent descriptor. Open the
  staging directory no-follow, then create and write `l1`, `l2`, and every JSON
  through directory descriptors with exclusive no-follow file creation. Set all
  JSON files to `0444` and layer/root directories to `0775`. Write
  `chronology-receipt.json` only after all ten payload bindings are available.

- [x] **Step 4: Implement complete-tree validation**

  `_validate_materialized_root` takes separate `artifact_root` and logical
  `evaluation_root`. It replays the active transition with evaluation absence
  disabled, rebuilds the authoring bundle, enforces exact root/layer sets and
  modes, compares every payload to canonical bytes, strict-parses chronology,
  rebuilds expected chronology using its untrusted label, rejects model paths,
  and returns:

  ```python
  {
      "status": "valid",
      "evaluation_id": "typed-extractor-v3-fresh-hidden-v1",
      "l1_case_count": 24,
      "l2_case_count": 18,
      "model_runs_present_at_freeze": False,
      "model_request_count": 0,
  }
  ```

- [x] **Step 5: Implement no-replace directory publication**

  Call libc `renameat2` with `_AT_FDCWD=-100` and
  `_RENAME_NOREPLACE=1`. Convert `EEXIST`/`ENOTEMPTY` to `FileExistsError` and
  all other errno values to `OSError`. Never fall back to `os.replace`.

- [x] **Step 6: Implement the public writer**

  Validate UTC, target absence, parent directory, and active transition before
  staging. Build/validate the bundle, stage all outputs, validate staging, then
  rerun active transition and staging validation immediately before publication.
  Publish once. On exception, verify that the staging pathname still names the
  originally opened directory inode, then preserve the potentially partial,
  non-authoritative staging tree for audit. Any chronology in failed staging is
  uncommitted intent. Do not unlink or rmdir through replaceable pathnames or
  let any preservation or descriptor cleanup error mask the primary exception.
  Return the validation result without calling a model.

- [x] **Step 7: Implement the public read-only validator**

  Resolve roots lexically and delegate to `_validate_materialized_root` with
  the official evaluation root as both artifact and logical root. It must not
  chmod, rewrite, delete, or create any path.

- [x] **Step 8: Run the full focused file to GREEN**

  Run the Task 1 command with a new basetemp. Expected: every materialization
  test passes and the official evaluation root remains absent.

- [x] **Step 9: Run adjacent phase tests and static checks**

  Run phase-aware authoring, relocation, and v3 prereg nodes, tracked typed
  tests, Ruff, compileall, tabnanny, and `git diff --check`. Receipt-authoring
  nodes that bind materialization-code absence are historical phase tests and
  must be deselected after the declared implementation files exist. Revalidate
  fixed receipt/Git/protected hashes and confirm candidate queue, official
  root, model paths, staging paths, credentials, and all automatic writes
  remain unchanged.

- [x] **Step 10: Commit the atomic materializer**

  ```bash
  git add \
    research/next-prep/tools/natural_memory_benchmark/typed_extractor_fresh_v3_materialization.py \
    research/next-prep/tests/natural_memory_benchmark/test_typed_extractor_fresh_v3_materialization.py
  git commit -m "Add atomic fresh-v3 materialization"
  ```

### Task 4: Review, Freeze Once, And Record Facts

**Files:**

- Generate:
  `artifacts/automatic-extraction-assessment/typed-extractor-v3-fresh-hidden-v1/`
- Modify after freeze: `README.md`, `AGENTS.md`, `安排.md`, and this plan.
- Modify `NORMALIZATION.md` only if the normalized active-stage statement
  requires a materialization fact.

**Interfaces:**

- Consumes the committed/reviewed materializer and fixed active receipt.
- Produces exactly ten frozen payloads and one chronology receipt.

- [x] **Step 1: Run an independent read-only review**

  Review the materializer/test commits against the design and this plan. Fix
  every Critical or Important finding with a failing regression test first,
  rerun its focused tests, and repeat review until no such finding remains.

- [x] **Step 2: Run the complete pre-freeze gate**

  Run focused materialization, authoring, relocation, prereg, phase-aware typed,
  runtime, static, exact transition, Git blob, candidate queue/live guard,
  credential, staging absence, official-root absence, and zero-write checks.
  Run the correctly rooted tracked natural and knowledge suites and report
  known normalization gaps separately without modifying frozen history.

- [x] **Step 3: Perform the only official materialization call**

  Call `materialize_fresh_v3_hidden` directly with exact repository/workspace,
  official evaluation root, and one valid current UTC label. Do not invoke CLI,
  proposer, scorer, API transport, materialization retry, or model command.

- [x] **Step 4: Run the complete post-freeze audit**

  Reopen all eleven files; validate exact SHA/size/mode, `24/18` counts, family
  maps, canonical replay, chronology/Git/receipt/materializer bindings, root
  and layer artifact sets, absent model/result paths, candidate queue/live
  guard, manual-adjudication false, unresolved LongMemEval, credentials, and
  zero writes. Run phase-aware tests and static checks again.

- [x] **Step 5: Update and commit fact sources**

  Record the caller-supplied label, chronology SHA, materializer/test SHA,
  output counts/modes, review result, pre/post gate results, and remaining
  authorization boundary. State that the next stage may separately design a
  no-history public-only proposer freeze; it does not authorize scoring,
  pipeline integration, or authoritative writes. Stage only materialization
  artifacts and these fact sources, then commit with:

  ```bash
  git commit -m "Materialize fresh-v3 hidden evaluation"
  ```

### Task 4 Execution Record

- Independent rereview: Critical `0`, Important `0`, Minor `0`; focused
  materialization `45 passed`.
- Pre-freeze gate: phase-aware prereg/authoring/snapshot
  `54 passed, 62 deselected`; tracked typed `255 passed, 1 deselected`;
  runtime `773 passed, 1 skipped`; tracked natural
  `775 passed, 24 allowlisted failures, 1 deselected`; knowledge retained the
  exact six allowed missing-`nltk` collection errors. Static, credential,
  protected-state, root/staging-absence, and zero-write checks passed.
- The only official call used caller-supplied label `2026-07-30T04:44:31Z` and
  published `artifacts/automatic-extraction-assessment/typed-extractor-v3-fresh-hidden-v1/`.
  The result was `valid`, with L1/L2 `24/18`, model requests `0`, and no model
  run at freeze.
- Chronology SHA-256 is
  `fe3cfbd739de477d99089c4ed6f85322236e00deb9b405596f038366bee16cca`;
  materializer module/test SHA-256 values are
  `1e134fcc005da9e10f9f5be95cf46f3451b39f16556b1a088c9f034d02f6bc7e` /
  `76f5e2377b153b68eef1d5a84be7a865af8a24cbf30b4e5adb7b49915646ab80`.
  All eleven JSON files are mode `0444`, root/layer directories are `0775`,
  and all ten payloads replay byte-identically.
- Post-freeze audit: the public validator and exact eleven-file audit passed;
  XML-derived full node IDs produced `61 passed, 100 deselected` across the
  four phase files. Ruff, compileall, tabnanny, diff, credential `0`, candidate
  queue/live guard, parallel hashes, and nine zero-write checks passed again.
- This record does not authorize a proposer or scorer. A separate no-history,
  public-only proposer-freeze/qualification design and implementation plan
  require explicit user approval before execution; pipeline integration and
  authoritative writes remain unauthorized.

## Self-Review

- Spec coverage: phase-transition binding, strict chronology, exact composition,
  atomic no-replace publication, fail-closed staging preservation,
  post-validation, review, and formal freeze each map to one task.
- Placeholder scan: every function, path, schema, count, mode, command, and
  failure behavior required for implementation is explicit.
- Type consistency: public signatures and private transition/validation inputs
  are identical across tasks; L1/L2 totals remain `24/18` throughout.
- Scope: no task calls a model, scores a proposal, changes shared pipelines, or
  performs an authoritative memory write.
