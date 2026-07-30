# Typed Extractor Fresh-V3 Proposer Freeze And Qualification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` or `superpowers:executing-plans` to
> implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for
> tracking. Execute inline in the existing worktree because parallel sessions
> own adjacent ontology, L1 admission/linking, and Query files.

**Goal:** Make exactly one public-only, no-history proposer request for each
fresh-v3 L1/L2 layer, freeze both proposal chains before scoring, and publish a
preregistered raw/gated qualification conclusion without retries or memory
writes.

**Architecture:** Add a v3-only proposer phase controller and independent
qualification module. Reuse the existing typed proposer/scorer logic, with
backward-compatible scorer parameters for the exact v3 manifest filename set
and thresholds, so no compatibility manifest is created. Commit and review all
code before either request.

**Tech Stack:** Python 3.12, Pydantic v2, pytest, canonical JSON/SHA-256, Git
plumbing, existing OpenAI-compatible API runners, immutable `0444` artifacts,
and Linux no-replace filesystem primitives.

## Global Constraints

- Work only in
  `/public/home/wwb/KE_mem/ke-memory-demo/.worktrees/next-prep-normalization-20260729`.
- Do not access the retired source workspace or create another worktree.
- Do not modify ontology, query, L1 admission/linking, runtime package,
  preregistration, authoring, materialization, identity, or authoritative-write
  files.
- Preserve materialization commit
  `703b990a883a0c1e28c2688949beb3b22c97ae65`, chronology SHA
  `fe3cfbd739de477d99089c4ed6f85322236e00deb9b405596f038366bee16cca`,
  active receipt SHA
  `c810f421d5a3b0726b862ec2f12c89e0d638e0747892637e2a32977587b7ef8c`,
  L1/L2 counts `24/18`, and all ten materialized payload bytes.
- Requested model alias is exactly `deepseek-chat`; response model is recorded
  from each raw response. Isolation is
  `fresh-agent-no-history-declarative` and proposer inputs are only the exact
  frozen layer prompt and public JSON.
- Freeze both dispatches before either request. Each layer receives at most one
  HTTP request. Do not retry transport, invalid JSON, semantic failure, or use
  a fallback/replacement model.
- Do not read authority/gold through a scorer until both proposal-freeze
  receipts validate. Never expose authority/gold to the proposer process.
- Raw proposer quality and deterministic gate safety remain separate. All
  preregistered quality metrics must equal `1.0`; raw critical false emission,
  gate intervention, and deterministic critical materialization must equal
  `0`.
- Keep automatic L1, L2, revision, source-revision, closure, identity,
  membership, snapshot, and aggregate writes at `0`; manual adjudication is not
  materialized, embedding is non-authoritative, and
  `LONGMEMEVAL-6d550036` remains `structured_l2_identity_unresolved`.
- Stop after the frozen qualification conclusion whether it passes, fails, or
  is incomplete. Do not continue to integration, closure, aggregation,
  benchmark expansion, repository cleanup, or external-system reruns.

---

### Task 1: Parameterize Exact Scorer Contracts

**Files:**

- Modify: `tools/natural_memory_benchmark/typed_extractor_l1.py`
- Modify: `tools/natural_memory_benchmark/typed_extractor_l2.py`
- Modify: `tests/natural_memory_benchmark/test_typed_extractor_l1.py`
- Modify: `tests/natural_memory_benchmark/test_typed_extractor_l2.py`

**Interfaces:**

- Add `manifest_output_names: tuple[str, ...]` as a keyword-only parameter to
  `score_l1_proposals` and `run_l1_scoring_file`, defaulting to the legacy
  three-file tuple `("authority-l1.json", "gold-l1.json", "public-l1.json")`.
- Add `manifest_output_names` and
  `required_thresholds: dict[str, float | int]` to `score_l2_proposals` and
  `run_l2_scoring_file`, defaulting to the existing three-file tuple and
  `L2_DEV_THRESHOLDS`.
- Fresh-v3 passes the corresponding four-file tuple including
  `source-cases-l1.json` or `source-cases-l2.json` and the exact preregistered
  L2 thresholds.

- [ ] **Step 1: Write failing exact-contract tests**

  Add tests proving the legacy defaults retain exact three-file/legacy-threshold
  behavior, while explicit v3 parameters accept the official four-file output
  map and exact-1.0 L2 thresholds. Add negative cases for an extra filename, a
  missing source filename, source hash drift, and one changed threshold.

  ```python
  V3_L1_OUTPUTS = (
      "authority-l1.json",
      "gold-l1.json",
      "public-l1.json",
      "source-cases-l1.json",
  )
  V3_L2_OUTPUTS = (
      "authority-l2.json",
      "gold-l2.json",
      "public-l2.json",
      "source-cases-l2.json",
  )
  ```

- [ ] **Step 2: Run the new tests and observe RED**

  ```bash
  cd research/next-prep
  PYTHONPATH=. ../../.venv/bin/python -m pytest -q -p no:cacheprovider \
    --basetemp /tmp/ke-memory-fresh-v3-scorer-red \
    tests/natural_memory_benchmark/test_typed_extractor_l1.py \
    tests/natural_memory_benchmark/test_typed_extractor_l2.py
  ```

  Expected: only the new calls fail because the scorer functions do not yet
  accept the explicit contract parameters.

- [ ] **Step 3: Implement the minimal backward-compatible parameters**

  Build `expected_output_hashes` from exactly `manifest_output_names`, reject
  path separators, duplicates, and names outside the layer's fixed four-name
  allowlist, and compare the complete dict to `manifest.output_sha256`. Compare
  L2 `manifest.thresholds` to a copied `required_thresholds` mapping. Thread the
  same values through each `run_*_scoring_file` wrapper. Do not relax any other
  proposal, provenance, raw-response, guard, or schema check.

- [ ] **Step 4: Run scorer tests to GREEN**

  Run the Step 2 command with basetemp
  `/tmp/ke-memory-fresh-v3-scorer-green`.

  Expected: zero failures, including all legacy scorer cases and the new v3
  exact-contract cases.

### Task 2: Implement The One-Shot Proposer Freeze Controller

**Files:**

- Create:
  `tools/natural_memory_benchmark/typed_extractor_fresh_v3_proposer_freeze.py`
- Create:
  `tests/natural_memory_benchmark/test_typed_extractor_fresh_v3_proposer_freeze.py`

**Interfaces:**

```python
def validate_fresh_v3_proposer_preflight(
    repository_root: Path,
    workspace_root: Path,
) -> dict[str, Any]: ...

def freeze_fresh_v3_dispatches(
    repository_root: Path,
    workspace_root: Path,
    run_label: str,
) -> dict[str, Any]: ...

def run_and_freeze_fresh_v3_layer(
    repository_root: Path,
    workspace_root: Path,
    layer: Literal["l1", "l2"],
    *,
    base_url: str,
    api_key: str,
    timeout_seconds: int,
    opener: Callable[..., Any] = urlopen,
) -> dict[str, Any]: ...

def validate_fresh_v3_proposal_freeze(
    repository_root: Path,
    workspace_root: Path,
    layer: Literal["l1", "l2"],
) -> dict[str, Any]: ...
```

- [ ] **Step 1: Write preflight and dispatch RED tests**

  Cover exact repository/workspace, materialization validator replay,
  chronology/receipt/prompt/public hashes, committed implementation bytes,
  candidate queue/live guard, parallel hashes, empty index, zero writes, exact
  absent model/result paths, strict UTC compact `run_label`, two deterministic
  run IDs, and both dispatches frozen before any opener call. Reject symlinks,
  writable inputs, unknown fields, coercive counts, drift, prior run paths, and
  authority/gold in an allowlist.

- [ ] **Step 2: Write one-request and failure RED tests**

  Use a fake opener with a call counter. For both layers assert the request has
  exactly two messages, contains the expected prompt/public payload, and does
  not contain authority/gold names or bytes. Assert success produces the exact
  five pre-score artifacts and modes, byte-replays proposals from raw response,
  and records request ordinal `1`. Assert transport, invalid JSON, invalid
  proposal metadata, partial coverage, and reference drift call the opener
  exactly once, preserve existing evidence, freeze a failure receipt, and never
  create provenance or a second run.

- [ ] **Step 3: Run the focused file and observe RED**

  ```bash
  cd research/next-prep
  PYTHONPATH=. ../../.venv/bin/python -m pytest -q -p no:cacheprovider \
    --basetemp /tmp/ke-memory-fresh-v3-proposer-freeze-red \
    tests/natural_memory_benchmark/test_typed_extractor_fresh_v3_proposer_freeze.py
  ```

  Expected: collection fails only because the controller module does not exist.

- [ ] **Step 4: Implement strict models and the read-only preflight**

  Add frozen, strict Pydantic models for successful and failed freeze receipts.
  Reuse the public materialization validator, bind the exact prompt/public/code
  hashes and protected state, verify committed blobs equal working bytes, and
  reject any pre-existing `model-runs`, score, qualification, report, or staging
  path before dispatch creation.

- [ ] **Step 5: Implement dispatch and one-shot freeze**

  Freeze both dispatches first through the existing L1/L2 dispatch writers.
  `run_and_freeze_fresh_v3_layer` chooses the existing layer API runner exactly
  once, uses a unique temporary parsed-proposal path outside the official root,
  calls the existing layer proposal freezer, reopens all artifacts, writes the
  canonical receipt last, and leaves no official staging path. It has no loop,
  retry branch, fallback model, or response-edit path. Failure handling writes
  a canonical immutable failure receipt without masking the primary exception.

- [ ] **Step 6: Run focused tests to GREEN**

  Run the Step 3 command with basetemp
  `/tmp/ke-memory-fresh-v3-proposer-freeze-green`.

  Expected: zero failures and fake opener request counts exactly `1` in every
  success/failure case that reaches transport.

### Task 3: Implement Independent Scoring And Qualification

**Files:**

- Create:
  `tools/natural_memory_benchmark/typed_extractor_fresh_v3_qualification.py`
- Create:
  `tests/natural_memory_benchmark/test_typed_extractor_fresh_v3_qualification.py`

**Interfaces:**

```python
def score_and_qualify_fresh_v3(
    repository_root: Path,
    workspace_root: Path,
    qualification_time: str,
) -> dict[str, Any]: ...

def freeze_incomplete_fresh_v3_qualification(
    repository_root: Path,
    workspace_root: Path,
    qualification_time: str,
) -> dict[str, Any]: ...

def validate_fresh_v3_qualification(
    repository_root: Path,
    workspace_root: Path,
) -> dict[str, Any]: ...
```

- [ ] **Step 1: Write phase-separation and qualification RED tests**

  Prove authority/gold paths are not opened until both successful proposal
  receipts validate. Reject one complete/one failed layer, writable or drifted
  proposer artifacts, request count other than one, response/proposal mismatch,
  prompt/public/hash drift, unknown run files, and any credential/model
  transport parameter. Use temporary authored fixtures to test perfect, raw
  failure, gate-intervention failure, and scorer failure without reading formal
  v3 gold in proposer tests.

- [ ] **Step 2: Assert exact qualification decisions**

  A perfect fixture must produce all L1 14 and L2 12 metrics at `1.0`, all
  three safety counts at `0`, both readiness fields true, both layers ready,
  and overall `qualified`. A single metric below `1.0` or one nonzero safety
  count must preserve the measured score and produce `not_qualified`. A failed
  proposer freeze must produce `incomplete_not_qualified` without invoking a
  scorer.

- [ ] **Step 3: Run the focused file and observe RED**

  ```bash
  cd research/next-prep
  PYTHONPATH=. ../../.venv/bin/python -m pytest -q -p no:cacheprovider \
    --basetemp /tmp/ke-memory-fresh-v3-qualification-red \
    tests/natural_memory_benchmark/test_typed_extractor_fresh_v3_qualification.py
  ```

  Expected: collection fails only because the qualification module is absent.

- [ ] **Step 4: Implement strict phase validation and scoring**

  Validate both proposal receipts first, then call the existing L1/L2 scoring
  wrappers with the exact four-file manifest tuples and preregistered
  thresholds. Write `score.json`, `error-analysis.json`, and `report.md` for
  each layer, followed by strict per-layer `qualification.json`. The module
  imports no API runner and accepts no credential or transport argument.

- [ ] **Step 5: Implement overall and incomplete conclusions**

  Freeze `overall-score.json`, `overall-report.md`, and
  `qualification-chronology.json` with exact proposal/score/qualification
  hashes, request counts, thresholds, materialization/Git/code/protected-state
  bindings, raw/gated separation, nine zero writes, manual adjudication false,
  and all unauthorized boundaries. The incomplete path records the immutable
  failure receipts and performs no authority/gold load.

- [ ] **Step 6: Run focused and adjacent tests to GREEN**

  ```bash
  cd research/next-prep
  PYTHONPATH=. ../../.venv/bin/python -m pytest -q -p no:cacheprovider \
    --basetemp /tmp/ke-memory-fresh-v3-qualification-green \
    tests/natural_memory_benchmark/test_typed_extractor_fresh_v3_qualification.py \
    tests/natural_memory_benchmark/test_typed_extractor_fresh_v3_proposer_freeze.py \
    tests/natural_memory_benchmark/test_typed_extractor_l1.py \
    tests/natural_memory_benchmark/test_typed_extractor_l2.py
  ```

  Expected: zero failures.

### Task 4: Review, Commit, And Pass The Pre-Request Gate

**Files:**

- Modify only the six implementation/test files from Tasks 1-3 plus this plan's
  execution checkboxes.

- [ ] **Step 1: Run an independent read-only review**

  Review the exact diff against the approved design. Fix every Critical or
  Important finding with a failing regression test first and repeat until both
  counts are zero.

- [ ] **Step 2: Run the complete pre-request gate**

  Run focused controller/qualification/scorer tests, phase-aware v3 tests,
  tracked typed tests, runtime tests, the correctly rooted tracked natural and
  knowledge suites with their exact existing allowlists, Ruff, compileall,
  tabnanny, diff, public materialization validator, canonical 11-file audit,
  credential scan, Git/index/blob checks, candidate queue/live guard, parallel
  hashes, model/result/staging absence, and nine zero-write checks.

- [ ] **Step 3: Commit implementation only**

  Explicitly stage the approved design/plan and six implementation/test files.
  Verify the cached path set exactly, then commit:

  ```bash
  git commit -m "Prepare fresh-v3 extraction qualification"
  ```

  Reopen committed blobs and rerun the focused/static/protected gate. The index
  must be empty and no official model-run path may exist.

### Task 5: Execute And Freeze Both One-Shot Proposers

- [ ] **Step 1: Reacquire the concurrency window**

  Require ontology/L1/query sessions to remain paused for filesystem and Git
  writes. Record HEAD, status, empty index, every parallel SHA, implementation
  blob/current-byte equality, public materialization validity, credential
  absence, exact model/result-path absence, guard/candidate hashes, and zero
  writes. Any drift invalidates the gate and stops before a request.

- [ ] **Step 2: Freeze both dispatches**

  Capture one current UTC compact run label and call
  `freeze_fresh_v3_dispatches` once. Validate both immutable dispatches and
  prove each allows only its prompt/public pair with requested model
  `deepseek-chat`.

- [ ] **Step 3: Run and freeze L1 exactly once**

  Invoke `run_and_freeze_fresh_v3_layer(..., layer="l1")` using runtime
  `OPENAI_BASE_URL`/`OPENAI_API_KEY` without printing them. Reopen and validate
  the exact five-file L1 proposal freeze. On any failure, preserve evidence,
  do not retry, and continue only to the independently allowed L2 opportunity
  if global protected state is still valid.

- [ ] **Step 4: Run and freeze L2 exactly once**

  Revalidate global protected state, then invoke the same function for `l2`.
  Reopen and validate its exact five-file proposal freeze. Never rerun either
  layer.

- [ ] **Step 5: Close the proposer phase**

  Record request counts `1/1` or the exact failed opportunity, response model
  identifiers, raw/proposal/provenance hashes, modes, allowed files, and frozen
  sequence. Confirm authority/gold have not been read by proposer code and no
  score/qualification path exists yet.

### Task 6: Score, Qualify, Audit, And Stop

- [ ] **Step 1: Enter the independent scorer phase**

  Start a new process with `OPENAI_API_KEY` and `OPENAI_BASE_URL` unset. If both
  proposal freezes are valid, call `score_and_qualify_fresh_v3` once with a
  caller-supplied UTC label. Otherwise call
  `freeze_incomplete_fresh_v3_qualification`; do not load authority/gold.

- [ ] **Step 2: Validate the conclusion**

  Reopen all proposer, score, error-analysis, report, qualification, overall,
  and chronology artifacts. Verify exact sets/hashes/modes, raw-response to
  proposal replay, score replay, exact thresholds, raw/gated separation,
  request counts, guard/protected state, credential zero, nine zero writes,
  manual adjudication false, and unresolved LongMemEval.

- [ ] **Step 3: Run the post-qualification gate**

  Rerun focused/phase-aware tests, tracked typed/runtime/natural/knowledge
  checks, Ruff, compileall, tabnanny, diff, credential scan, public validators,
  Git/protected/parallel hashes, and zero-write checks. Report all existing
  dependency/path allowlist gaps exactly; do not modify frozen history.

- [ ] **Step 4: Record and commit facts**

  Update only `README.md`, `AGENTS.md`, `安排.md`, this plan, and the formal
  fresh-v3 model-run/qualification artifacts. Explicitly verify the staged set
  excludes ontology/L1/query files, then commit with a message reflecting the
  actual conclusion.

- [ ] **Step 5: Stop**

  Report raw L1/L2 metrics, gate safety, response model, request counts,
  artifact hashes, and final qualification. Do not implement repairs or move
  into integration even when the result is qualified.

## Self-Review

- Spec coverage: committed implementation before requests, two one-shot
  public-only runs, proposal-before-scoring freeze, compatibility-free exact
  scoring, raw/gated qualification, failure preservation, audit, and stop
  boundary each have an explicit task.
- Placeholder scan: every path, interface, hash, count, model policy, retry
  rule, artifact set, threshold, command, and failure action is concrete.
- Type consistency: scorer parameter names and tuples match Tasks 1 and 3;
  proposer receipt validation is the only transition into scoring.
- Scope: no task modifies query, ontology, L1 admission/linking, authoritative
  storage, closure, aggregation, benchmark coverage, or external systems.

## Execution Record

The formal dispatch label was `20260730T061218Z`. Both immutable dispatches
were frozen before transport. L1 and L2 each used their single authorized HTTP
opportunity with requested alias `deepseek-chat`; request counts were `1/1`.
Both requests failed before raw response bytes existed with
`HTTPError: HTTP Error 403: Forbidden`. No retry or fallback was performed.

Because neither layer produced a raw response, no proposal, provenance, score,
error analysis, or layer qualification was created. The independent scorer did
not read authority or gold. All nine automatic write counts remained zero. The
overall conclusion frozen at `2026-07-30T06:13:39Z` is
`incomplete_not_qualified`: transport/authorization was incomplete and raw
automatic extraction quality remains unmeasured.

The L1/L2 failure receipt SHA-256 values are
`5bf32c6357ec856c5e5dfe741c0d048c685ec3fff13a51a3de06f912d99fa8aa` and
`a5645f0d863c49063a619a2823e53ff0b11d9bc292522bf61c2c3ffffdb6a21d`.
The overall score/report/qualification chronology SHA-256 values are
`28b0719b767328c45dde84ebe8a025b2747bb8a41acd6d4f67eb75eec6b9c8ef`,
`04b814d02c2715ba446f668628fcb2d7c6a4cae3bed77199da3cf0db0261e883`, and
`2a7d1653213ba74574cb2bb7fc1ee7394e22227ef0c5ab692f2a9438619420d0`.

A later public API probe, containing no evaluation data, established that the
runtime key is valid and can access `deepseek-v4-pro`; the service explicitly
returned `key_model_access_denied` for `deepseek-chat`. This diagnoses the 403
as model-alias authorization, not an invalid key. It does not alter the frozen
formal conclusion, and the original run may not be retried or overwritten.
