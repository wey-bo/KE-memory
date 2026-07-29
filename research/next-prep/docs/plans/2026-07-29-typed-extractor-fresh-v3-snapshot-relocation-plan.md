# Typed Extractor Fresh-V3 Snapshot Relocation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking. Do not dispatch subagents for this
> plan because the user requires inline execution in the existing worktree.

**Goal:** Freeze one canonical fresh-v3 authoring implementation receipt in
the normalized Git snapshot while preserving the original preregistration
chronology and all zero-write boundaries.

**Architecture:** Add a standalone relocation adapter under
`research/next-prep` that proves the imported preregistration and reviewed
authoring files with a fixed ancestor commit plus exact Git blobs. The adapter
maps the historical absolute chronology to repository-relative normalized
paths, rebuilds the existing path-neutral authoring/protected-state bindings,
and publishes a strict receipt v2 through the existing chronology lock and
anonymous-inode no-replace writer.

**Tech Stack:** Python 3.12, Pydantic v2, Git plumbing commands, pytest,
canonical JSON/SHA-256 helpers, Linux `flock`/`O_TMPFILE`/`linkat` publication.

## Global Constraints

- Work only in
  `/public/home/wwb/KE_mem/ke-memory-demo/.worktrees/next-prep-normalization-20260729`.
- Use the existing worktree and branch; do not create another worktree or read
  the retired source workspace except for already frozen path strings.
- Do not modify the frozen preregistration, reviewed fresh-v3 authoring module,
  reviewed authoring test, v1/v2 chains, shared scorer/query/identity code, or
  runtime packages outside `research/next-prep`.
- Do not create the fresh-v3 evaluation root or materialization module/test,
  call a model, expose authority/gold to a proposer, or create proposal/score
  output.
- Automatic L1, L2, revision, source-revision, closure, identity, membership,
  snapshot, and aggregate write counts remain exactly `0`.
- Manual identity adjudications remain separate and unmaterialized;
  `LONGMEMEVAL-6d550036` remains
  `structured_l2_identity_unresolved`; embedding remains non-authoritative;
  external memory systems are not rerun.
- The original preregistration SHA-256 remains
  `183cf6fc2991361e5da57b17e06a5970f651000986d50b87e8af2e6796440204`.
- The fixed import commit is
  `00fa803ee44bcef5a299babb9a8e2b7ba9f994e4`; it must be an ancestor of
  `HEAD`.
- Formal receipt publication is no-clobber and canonical; mode `0444` is a
  local hardening measure, while commit/blob identity plus exact bytes is the
  durable recovery authority.

---

### Task 1: Prove The Git Snapshot And Relocation Mapping

**Files:**

- Create:
  `tests/natural_memory_benchmark/test_typed_extractor_fresh_v3_snapshot_receipt.py`
- Create:
  `tools/natural_memory_benchmark/typed_extractor_fresh_v3_snapshot_receipt.py`

**Interfaces:**

- Consumes: `repository_root: Path`, `workspace_root: Path`, fixed import
  commit, and three fixed repository-relative paths.
- Produces:
  `_build_git_snapshot_binding(repository_root, workspace_root) -> GitSnapshotBinding`.
- Produces:
  `_validate_relocation_paths(preregistration, repository_root, workspace_root,
  evaluation_root) -> RelocationPathBinding`.

- [ ] **Step 1: Write failing Git-binding tests**

  Add tests that first exercise a small real temporary Git repository, then the
  actual imported snapshot. The temporary repository test must initialize a
  commit, obtain its blob with `git rev-parse <commit>:<path>`, and assert that
  replacing the working file, using a non-ancestor commit, or supplying a
  different repository root fails closed. The formal test must assert these
  exact bindings:

  ```python
  EXPECTED_BLOBS = {
      "preregistration": "6433fef43d7c2d68f064d900ff28172f94b4968e",
      "authoring_module": "bbe36a908ce7210c2919bb66328d4d4275851fe9",
      "authoring_test": "d92a28b2dae92bc4ddeecaca05f7520b864f24c2",
  }

  binding = receipt_module._build_git_snapshot_binding(REPOSITORY, WORKSPACE)
  assert binding.snapshot_commit == SNAPSHOT_COMMIT
  assert {
      name: item.git_blob_oid for name, item in binding.files.items()
  } == EXPECTED_BLOBS
  ```

- [ ] **Step 2: Run the focused file and verify RED**

  Run from `research/next-prep`:

  ```bash
  PYTHONPATH=. ../../.venv/bin/python -m pytest -q \
    tests/natural_memory_benchmark/test_typed_extractor_fresh_v3_snapshot_receipt.py
  ```

  Expected: collection fails because
  `typed_extractor_fresh_v3_snapshot_receipt` does not exist.

- [ ] **Step 3: Implement minimal Git and path proof**

  Define strict frozen Pydantic models and Git helpers with these shapes:

  ```python
  class GitSnapshotFileBinding(StrictModel):
      repository_path: str
      workspace_path: str
      git_blob_oid: str = Field(pattern=r"^[0-9a-f]{40}$")
      sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
      size_bytes: int = Field(ge=1)

  class GitSnapshotBinding(StrictModel):
      evidence_kind: Literal["git-commit-blob-plus-sha256"]
      snapshot_commit: Literal[
          "00fa803ee44bcef5a299babb9a8e2b7ba9f994e4"
      ]
      snapshot_commit_is_ancestor: Literal[True]
      files: dict[str, GitSnapshotFileBinding]

  class RelocationPathBinding(StrictModel):
      original_preregistration_root: str
      original_evaluation_root: str
      normalized_repository_root: Literal["."]
      normalized_workspace_root: Literal["research/next-prep"]
      normalized_preregistration_path: str
      normalized_evaluation_root: str
  ```

  Run Git only through argument arrays. Require `git rev-parse
  --show-toplevel` to equal the lexical repository root, require the fixed
  commit to exist and satisfy `merge-base --is-ancestor`, read commit bytes
  with `git show <commit>:<path>`, and compare both fixed blob IDs and SHA-256
  bytes to regular non-symlink working files. Require `workspace_root` to equal
  `<repository_root>/research/next-prep`. Validate the old chronology strings
  exactly, but store only repository-relative normalized paths for the new
  location.

- [ ] **Step 4: Run the focused Git tests to GREEN**

  Run the same focused command. Expected: all Git-binding and mapping tests
  pass, with no formal receipt or evaluation artifact created.

- [ ] **Step 5: Commit the Git proof**

  ```bash
  git add \
    research/next-prep/tools/natural_memory_benchmark/typed_extractor_fresh_v3_snapshot_receipt.py \
    research/next-prep/tests/natural_memory_benchmark/test_typed_extractor_fresh_v3_snapshot_receipt.py
  git commit -m "Add fresh-v3 Git snapshot relocation proof"
  ```

### Task 2: Build A Strict Canonical Receipt V2

**Files:**

- Modify:
  `tools/natural_memory_benchmark/typed_extractor_fresh_v3_snapshot_receipt.py`
- Modify:
  `tests/natural_memory_benchmark/test_typed_extractor_fresh_v3_snapshot_receipt.py`

**Interfaces:**

- Consumes: verified Git/path bindings, frozen preregistration, reviewed
  authoring bundle, existing protected-state reconstruction, and current
  relocation adapter/test files.
- Produces:
  `build_fresh_v3_snapshot_relocation_receipt(repository_root, workspace_root,
  evaluation_root, receipt_time) -> FreshV3SnapshotRelocationReceipt`.

- [ ] **Step 1: Add failing strict-model and builder tests**

  Tests must assert schema
  `typed-extractor-fresh-v3-authoring-receipt-v2`, exact canonical JSON,
  L1/L2 counts `24/18`, all family counts, 39 prior inputs, the existing
  dependency/code/blueprint hashes, the candidate queue and live guard, the
  relocation adapter/test hashes, and every false/zero claim boundary. Mutated
  unknown fields, string-coerced counts, incorrect original path mapping,
  changed queue/guard bytes, or present evaluation/materialization paths must
  fail.

  ```python
  receipt = build_fresh_v3_snapshot_relocation_receipt(
      REPOSITORY, WORKSPACE, FORMAL_EVALUATION, RECEIPT_TIME
  )
  assert receipt.schema_version == (
      "typed-extractor-fresh-v3-authoring-receipt-v2"
  )
  assert receipt.authoring_binding.l1_case_count == 24
  assert receipt.authoring_binding.l2_case_count == 18
  assert receipt.automatic_write_counts == AUTOMATIC_WRITE_COUNTS
  assert receipt.model_request_count == 0
  ```

- [ ] **Step 2: Run the new nodes and verify RED**

  Expected: failures name the absent v2 receipt model/builder, not fixture or
  import errors.

- [ ] **Step 3: Implement the minimal receipt model and builder**

  Add a strict nested `PathNeutralAuthoringBinding` containing the full v1
  implementation contract except absolute current paths: preregistration
  SHA/schema/mode; authoring code, dependency, blueprint manifest, and prior
  input hashes; L1/L2 counts and family maps. Add top-level Git/path bindings,
  relocation adapter/test hashes, future absence, protected state, zero-write
  counts, and unchanged authorization flags.

  Build the semantic bundle only through
  `build_fresh_v3_authoring_bundle(preregistration_path)`. Reuse the existing
  dependency/code registries and protected-state reconstruction without
  calling the v1 `_validate_chronology_paths`. Parse `receipt_time` as the
  existing exact 2026 UTC label and reject all coercion or extra fields.

- [ ] **Step 4: Run builder tests to GREEN and re-run authoring tests**

  ```bash
  PYTHONPATH=. ../../.venv/bin/python -m pytest -q \
    tests/natural_memory_benchmark/test_typed_extractor_fresh_v3_snapshot_receipt.py \
    tests/natural_memory_benchmark/test_typed_extractor_fresh_v3_authoring.py
  ```

  Expected before formal freeze: new focused tests pass; existing authoring
  suite retains its phase-aware pre-receipt result.

- [ ] **Step 5: Commit the strict receipt builder**

  ```bash
  git add \
    research/next-prep/tools/natural_memory_benchmark/typed_extractor_fresh_v3_snapshot_receipt.py \
    research/next-prep/tests/natural_memory_benchmark/test_typed_extractor_fresh_v3_snapshot_receipt.py
  git commit -m "Build strict fresh-v3 relocation receipt"
  ```

### Task 3: Add No-Clobber Freeze And Exact Validation

**Files:**

- Modify:
  `tools/natural_memory_benchmark/typed_extractor_fresh_v3_snapshot_receipt.py`
- Modify:
  `tests/natural_memory_benchmark/test_typed_extractor_fresh_v3_snapshot_receipt.py`

**Interfaces:**

- Produces:
  `freeze_fresh_v3_snapshot_relocation_receipt(repository_root, workspace_root,
  evaluation_root, receipt_time) -> dict[str, Any]`.
- Produces:
  `validate_fresh_v3_snapshot_relocation_receipt(repository_root,
  workspace_root, evaluation_root) -> dict[str, Any]`.

- [ ] **Step 1: Write failing publication and validation tests**

  Cover anonymous-inode canonical publication in a temporary directory,
  identical idempotence, differing-target rejection, concurrent target
  appearance, symlink/noncanonical/unknown-field rejection, target inode
  replacement during validation, exact SHA reporting, Git-bound file drift,
  live guard rebuilding, and future artifact appearance. Snapshot formal
  files and assert tests do not write any hidden/model/authority/gold,
  identity/membership/closure/snapshot/aggregate output.

- [ ] **Step 2: Run the publication nodes and verify RED**

  Expected: failures identify the missing freeze/validate functions or the
  missing validation checks.

- [ ] **Step 3: Implement freeze and validation**

  Use `fresh_v3_chronology_lock(preregistration_path)` and the existing
  `_write_receipt_no_clobber` anonymous-inode writer. Before the final link,
  recheck preregistration inode, Git ancestry/blobs/current bytes, old/new path
  mapping, path-neutral implementation binding, relocation code hashes,
  candidate queue, live guard, and future absence; compare canonical bytes to
  the initially built receipt.

  Validation must read a regular non-symlink mode-`0444` receipt, strict-parse
  it, compare exact canonical bytes, rebuild the expected receipt using its
  caller-supplied time, compare complete model equality, verify the receipt
  pathname still references the opened inode, and return:

  ```python
  {
      "status": "valid",
      "active_receipt": "authoring-implementation-receipt.json",
      "schema_version": "typed-extractor-fresh-v3-authoring-receipt-v2",
      "l1_case_count": 24,
      "l2_case_count": 18,
      "evaluation_root_absent": True,
      "materialization_implementation_absent": True,
      "hidden_artifacts_created": False,
      "model_request_count": 0,
      "receipt_sha256": "<sha256-of-opened-canonical-bytes>",
  }
  ```

- [ ] **Step 4: Run focused and adjacent tests to GREEN**

  Run the new test, existing v3 authoring test, all fresh-v3 prereg tests, and
  the typed-extractor phase-aware subset. Expected: no failures, and no formal
  receipt has been produced by tests.

- [ ] **Step 5: Commit the freeze/validation implementation**

  ```bash
  git add \
    research/next-prep/tools/natural_memory_benchmark/typed_extractor_fresh_v3_snapshot_receipt.py \
    research/next-prep/tests/natural_memory_benchmark/test_typed_extractor_fresh_v3_snapshot_receipt.py
  git commit -m "Harden fresh-v3 relocation receipt publication"
  ```

### Task 4: Freeze, Audit, And Record The Formal Receipt

**Files:**

- Generate:
  `artifacts/automatic-extraction-assessment/typed-extractor-v3-fresh-hidden-prereg-v1/authoring-implementation-receipt.json`
- Modify: `NORMALIZATION.md`
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `安排.md`
- Modify: root `README.md` only if the branch-level snapshot status needs a
  one-line active-stage correction.
- Modify: this plan.
- Modify:
  `docs/plans/2026-07-29-typed-extractor-fresh-v3-preregistration-plan.md`
  only to replace its stale next-step statement with the completed receipt
  fact.

**Interfaces:**

- Consumes: committed relocation adapter/test, fixed imported commit/blobs,
  unchanged frozen inputs, absent evaluation/materialization paths.
- Produces: exactly one canonical mode-`0444` receipt v2; no other formal
  artifact.

- [ ] **Step 1: Run the complete pre-freeze gate**

  Run new focused tests, existing fresh-v3 authoring tests, adjacent prereg
  tests, phase-aware typed/natural/knowledge tests, `compileall`, `tabnanny`,
  `git diff --check`, fixed hash/blob checks, candidate queue/live guard
  reconstruction, credential scan, and explicit absence/zero-write checks.
  Stop on any failure; do not publish the receipt.

- [ ] **Step 2: Freeze exactly once**

  Invoke `freeze_fresh_v3_snapshot_relocation_receipt` directly with the
  current repository root, exact `research/next-prep` workspace, normalized
  future evaluation root, and one valid caller-supplied UTC label. Do not run
  any materializer or model command.

- [ ] **Step 3: Validate the exact formal artifact**

  Reopen and validate the receipt, record its SHA-256, byte size, mode, schema,
  commit/blob bindings, L1/L2 counts, and canonical-byte equality. Confirm the
  formal prereg root contains exactly preregistration plus receipt; confirm
  evaluation/materialization/model/proposal/score paths remain absent and all
  protected hashes/write counts remain unchanged.

- [ ] **Step 4: Update fact sources and completion checkboxes**

  Record the relocation rationale, exact receipt identity, Git recovery chain,
  verification counts, and remaining authorization boundary. Remove the stale
  duplicate preregistration item in `安排.md`. State that the next separately
  designed step may be one-time fresh-v3 hidden materialization, not proposer,
  scoring, pipeline integration, or authoritative writes.

- [ ] **Step 5: Run the complete post-freeze gate**

  Re-run validation and the same regression/static/audit commands, accounting
  only for any explicitly phase-aware pre-receipt test deselection. Verify no
  credentials or user-provided API key occur in tracked or generated files.

- [ ] **Step 6: Commit receipt and fact sources**

  ```bash
  git add \
    research/next-prep/artifacts/automatic-extraction-assessment/typed-extractor-v3-fresh-hidden-prereg-v1/authoring-implementation-receipt.json \
    research/next-prep/NORMALIZATION.md \
    research/next-prep/README.md \
    research/next-prep/AGENTS.md \
    research/next-prep/安排.md \
    research/next-prep/docs/plans/2026-07-29-typed-extractor-fresh-v3-preregistration-plan.md \
    research/next-prep/docs/plans/2026-07-29-typed-extractor-fresh-v3-snapshot-relocation-plan.md
  git commit -m "Freeze fresh-v3 snapshot relocation receipt"
  ```

## Self-Review

- Every design requirement maps to a task: fixed Git ancestry/blobs, old/new
  path mapping, path-neutral authoring binding, current relocation hashes,
  canonical atomic publication, strict validation, future absence, protected
  state, and zero-write/claim boundaries.
- The plan does not rewrite the preregistration or reviewed authoring files and
  does not introduce a hidden materializer, proposer, scorer, or runtime
  integration.
- Test phases explicitly preserve the formal no-write chronology before the
  one deliberate freeze.
- Function names, schema names, fixed commit/blob IDs, paths, and counts are
  consistent across all tasks.
- There are no deferred contract choices or implementation placeholders.
