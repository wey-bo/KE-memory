# Typed Extractor Fresh-V3 DeepSeek-V4-Pro Rerun Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce an independent, immutable `deepseek-v4-pro` L1/L2 extraction
qualification without changing the original fresh-v3 materialization or failed
`deepseek-chat` conclusion.

**Architecture:** Add one focused rerun controller which owns a sibling result
root and reuses existing API runners, proposal freezers, scorers, and strict
metric contracts. It binds the original frozen inputs by path/hash, freezes
both dispatches before transport, permits one request per layer, then scores in
a credential-free phase only after both proposal receipts validate.

**Tech Stack:** Python 3.12, Pydantic v2, pytest, canonical JSON/SHA-256, existing
OpenAI-compatible API runners, immutable `0444` files.

## Global Constraints

- Work only in the active extraction worktree.
- Preserve commit `252e3d9` and every byte under the original failed run.
- Requested model is exactly `deepseek-v4-pro`; response model is recorded.
- Model inputs are only the existing frozen prompt/public pair for each layer.
- L1 and L2 each receive one HTTP opportunity; no retry, fallback, or edit.
- Authority/gold are read only after both proposal receipts validate.
- Stop after qualification; all nine automatic write counts remain zero.
- Do not modify or stage ontology, query, L1 admission/linking, closure, runtime,
  packaging, cleanup, or integration files.

---

### Task 1: Rerun Controller Contract

**Files:**
- Create: `tools/natural_memory_benchmark/typed_extractor_fresh_v3_v4pro_rerun.py`
- Create: `tests/natural_memory_benchmark/test_typed_extractor_fresh_v3_v4pro_rerun.py`

**Interfaces:**
- `validate_v4pro_rerun_preflight(repository_root: Path, workspace_root: Path) -> dict[str, Any]`
- `freeze_v4pro_rerun_dispatches(repository_root: Path, workspace_root: Path, run_label: str) -> dict[str, Any]`
- `run_and_freeze_v4pro_layer(repository_root: Path, workspace_root: Path, layer: Literal["l1", "l2"], *, base_url: str, api_key: str, timeout_seconds: int, opener: Callable[..., Any] = urlopen) -> dict[str, Any]`
- `score_and_qualify_v4pro_rerun(repository_root: Path, workspace_root: Path, qualification_time: str) -> dict[str, Any]`
- `validate_v4pro_rerun(repository_root: Path, workspace_root: Path) -> dict[str, Any]`

- [ ] Write RED tests proving the original qualification replays, the sibling
  root must be absent, both dispatches freeze before the opener is called, the
  requested model is `deepseek-v4-pro`, allowed files contain only prompt/public,
  and old result bytes are unchanged.
- [ ] Add fake-opener success/failure tests. Assert exact request count `1`, raw
  response/proposal replay, immutable five-file success or two-file failure
  layouts, no retry, and no authority/gold path or bytes in the request.
- [ ] Add qualification tests using authored temporary fixtures. Assert scoring
  cannot start until both proposal receipts validate; exact-1.0/zero-count
  metrics yield `qualified`, measured failures yield `not_qualified`, and
  transport failure yields `incomplete_not_qualified` without scorer reads.
- [ ] Run the focused file and observe only missing-module/interface failures:

```bash
cd research/next-prep
PYTHONPATH=. ../../.venv/bin/python -m pytest -q -p no:cacheprovider \
  --basetemp /tmp/ke-memory-v4pro-rerun-red \
  tests/natural_memory_benchmark/test_typed_extractor_fresh_v3_v4pro_rerun.py
```

- [ ] Implement the smallest controller that satisfies those tests. Use the
  existing L1/L2 API runners and proposal freezers, existing scorer functions,
  canonical writers, and fresh-v3 metric name sets. Do not alter historical
  validators or generalize unrelated code.
- [ ] Run the focused file to green and run the existing proposer/qualification/
  L1/L2 scorer files. Expected: all selected tests pass.
- [ ] Run Ruff, compileall, tabnanny, `git diff --check`, credential scan, and
  verify the scoped diff contains only the controller, its test, this design,
  and this plan.
- [ ] Commit the reviewed implementation before any evaluation request with
  message `Prepare deepseek-v4-pro fresh-v3 rerun`.

### Task 2: Formal Proposer Runs

**Files:**
- Create only under
  `artifacts/automatic-extraction-assessment/typed-extractor-v3-fresh-hidden-v1-deepseek-v4-pro-rerun-v1/`

- [ ] Verify empty index, committed implementation bytes, old qualification
  replay, protected hashes, sibling-root absence, credential nonserialization,
  and zero writes.
- [ ] Capture one UTC run label and call `freeze_v4pro_rerun_dispatches` once.
  Reopen both dispatches before transport.
- [ ] Call `run_and_freeze_v4pro_layer` for L1 exactly once. Preserve evidence
  and do not retry on any failure.
- [ ] Revalidate protected state and call the L2 function exactly once. Preserve
  evidence and do not retry on any failure.
- [ ] Reopen both result directories and validate request counts, response
  models, raw/proposal replay, modes/hashes, allowed inputs, and absence of
  authority/gold/scoring artifacts.

### Task 3: Score, Record, And Stop

**Files:**
- Modify only: `README.md`, `AGENTS.md`, `安排.md`, this plan
- Create remaining score/qualification files only under the sibling result root

- [ ] In a new process with API credential/base URL variables unset, call
  `score_and_qualify_v4pro_rerun` once if both proposal freezes validate. If a
  proposal failed, freeze the independent incomplete conclusion without
  opening authority/gold.
- [ ] Run `validate_v4pro_rerun`, credential scan, exact file/mode/hash audit,
  focused extraction tests, Ruff, compileall, tabnanny, and diff checks.
- [ ] Record request counts, response models, all L1/L2 metrics, separate raw/
  gated readiness, qualification conclusion, artifact hashes, zero writes, and
  the no-integration boundary in the four extraction fact sources.
- [ ] Stage exactly the sibling result root, four fact sources, and this plan.
  Prove the staged set excludes ontology, query, and L1 admission/linking files.
- [ ] Commit with a message reflecting the actual measured conclusion and stop.

## Self-Review

- Every design requirement maps to a task; no placeholder or hidden repair step
  remains.
- The original root is read-only input/evidence and never an output target.
- The real API phase is separate from fake-opener implementation tests.
- Formal evaluation, not broad harness refinement, is the terminal deliverable.
