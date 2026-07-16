# Core Test Suite Slimming Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development with superpowers:dispatching-parallel-agents for the four disjoint workstreams. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce redundant Core Tasks 1-9 tests without changing production code or losing any distinct contract, boundary, or failure mode.

**Architecture:** Four agents audit and edit mutually exclusive test paths. Each workstream starts from a passing focused baseline, records a contract matrix, and changes only tests whose equivalent retained coverage is explicit. Agents do not stage or commit in the shared worktree; the root controller integrates all disjoint edits, runs one complete verification gate, obtains an independent review, and creates one cleanup commit.

**Tech Stack:** Python 3.12, pytest, pytest-asyncio, Ruff, Pyright, uv, Git.

**Design Spec:** `docs/superpowers/specs/2026-07-16-core-test-suite-slimming-design.md` at commit `e8effd9`.

## Global Constraints

- Modify tests only. No file under `src/`, `prompts/`, `config/`, or project metadata may change.
- Do not modify `tests/conftest.py`; shared-file edits would invalidate parallel isolation.
- There is no numeric deletion target. Leave a test unchanged unless its retained equivalent is explicit.
- Every removed test must name the retained test or parameterized case that protects the same contract and failure boundary.
- Preserve separately diagnosable success/failure, pre-side-effect/post-side-effect, pre-commit/post-commit, trust-boundary, provenance, lifecycle, temporal, deterministic, rollback, and security behaviors.
- Parameterize only cases with the same setup shape, execution path, assertion structure, and failure boundary. Use descriptive `ids=` values.
- Do not combine distinct unit, contract, integration, or golden responsibilities into one test.
- Do not change production behavior to make a slimmed test suite pass.
- Do not access live model, Elasticsearch, network, BEAM outside the existing fixture, `/public/home/wwb/memory`, or any fusion-memory project.
- Keep the live embedding test opt-in and offline. Default verification unsets `KE_MEMORY_EMBEDDING_PATH`.
- Agents edit only their assigned paths, run only focused tests, and do not stage or commit. The root controller alone runs the complete suite and commits.
- Reports live under `/public/home/wwb/KE_mem/ke-memory-demo/.git/worktrees/ke-memory-demo-implementation/sdd/test-slimming/` and are not committed.

## Baseline

- Full suite: 587 collected; `586 passed, 1 skipped`.
- Test files: 24.
- Test source: approximately 12,427 lines and 400 test functions.
- Group A: 127 collected.
- Group B: 172 collected.
- Group C: 194 collected.
- Group D: 94 collected, including the one opt-in live embedding skip.

---

### Task 1: Parallel Contract Audit and Test Slimming

**Files:**

Workstream A may modify only:
- `tests/unit/domain/test_conversation.py`
- `tests/unit/domain/test_knowledge_equation.py`
- `tests/unit/domain/test_system_protocol.py`
- `tests/unit/ingestion/test_beam_loader.py`
- `tests/unit/ingestion/test_exchange_builder.py`
- `tests/unit/test_settings.py`
- `tests/unit/test_cli.py`
- `tests/unit/test_secret_hygiene.py`
- `tests/unit/test_init_local_secrets.py`

Workstream B may modify only:
- `tests/unit/infra/test_llm.py`
- `tests/unit/infra/test_redaction.py`
- `tests/unit/ontology/test_elasticsearch_adapter.py`
- `tests/contract/test_ontology_contract.py`

Workstream C may modify only:
- `tests/unit/extraction/test_coverage.py`
- `tests/unit/extraction/test_lifecycle.py`
- `tests/unit/extraction/test_turn_ke.py`
- `tests/unit/aggregation/test_session.py`
- `tests/unit/aggregation/test_dag.py`

Workstream D may modify only:
- `tests/unit/storage/test_artifacts.py`
- `tests/unit/embedding/test_chunking.py`
- `tests/unit/embedding/test_index.py`
- `tests/integration/test_beam_subset.py`
- `tests/integration/test_local_embedding.py`
- `tests/integration/test_sqlite_rebuild.py`

**Interfaces:**
- Consumes: approved Core Tasks 1-9 behavior and the existing passing tests.
- Produces: a smaller behavior-equivalent test portfolio plus four contract-matrix reports.

- [ ] **Step 1: Record the cleanup base and confirm the shared worktree is clean**

Run:

```bash
git rev-parse HEAD
git status --short --branch
```

Expected: one base SHA is recorded in every workstream prompt; status contains only the branch header.

- [ ] **Step 2: Dispatch Workstreams A, B, and C concurrently**

Each agent receives one exact file list above and one report path:

```text
sdd/test-slimming/group-a-report.md
sdd/test-slimming/group-b-report.md
sdd/test-slimming/group-c-report.md
```

Each agent must perform Steps 3-8 for its own paths. The root controller performs no edits while these agents run.

- [ ] **Step 3: Prove the focused baseline is green before editing**

Workstream A:

```bash
uv run --offline pytest -q \
  tests/unit/domain tests/unit/ingestion tests/unit/test_settings.py \
  tests/unit/test_cli.py tests/unit/test_secret_hygiene.py \
  tests/unit/test_init_local_secrets.py
```

Expected before cleanup: `127 passed`.

Workstream B:

```bash
uv run --offline pytest -q \
  tests/unit/infra tests/unit/ontology tests/contract/test_ontology_contract.py
```

Expected before cleanup: `172 passed`.

Workstream C:

```bash
uv run --offline pytest -q tests/unit/extraction tests/unit/aggregation
```

Expected before cleanup: `194 passed`.

Workstream D:

```bash
env -u KE_MEMORY_EMBEDDING_PATH uv run --offline pytest -q \
  tests/unit/storage tests/unit/embedding tests/integration
```

Expected before cleanup: `93 passed, 1 skipped`.

- [ ] **Step 4: Build the contract matrix before changing tests**

The assigned report must contain one row per existing test function or parameterized family:

```markdown
| Existing test/family | Unique contract or failure boundary | Action | Retained equivalent |
| --- | --- | --- | --- |
| `test_name` | Exact behavior protected | keep | self |
| `test_old_name` | Same setup/path/assertion as `test_kept_name` | merge | `test_kept_name[case-id]` |
```

Allowed actions are exactly `keep`, `merge`, and `delete`. `merge` and `delete` require a concrete retained test and case ID. If the mapping is uncertain, use `keep`.

- [ ] **Step 5: Apply only evidence-backed test refactors**

- Replace near-identical functions only when the matrix shows identical setup, call path, assertion structure, and failure boundary.
- When parameterizing, retain the existing literal inputs and expected values verbatim and give every `pytest.param` a semantic `id=` that names the condition. Do not introduce a generic wrapper or a new test-only execution path.
- Remove helpers and fixtures only when no retained test references them.
- Keep distinct exception types, side-effect timing, retry attempts, lifecycle/reference levels, evidence ownership, and persistence rollback cases separate.
- Do not add broad loop-based tests whose first failure hides later case identity.

- [ ] **Step 6: Run the focused suite after edits**

Run the same command from Step 3 for the assigned workstream.

Expected: zero failures and no new warnings. The collected count may decrease; the report records before/after counts and explains every removed case.

- [ ] **Step 7: Run scoped formatting and lint checks**

Workstream A:

```bash
uv run --offline ruff format --check tests/unit/domain tests/unit/ingestion tests/unit/test_settings.py tests/unit/test_cli.py tests/unit/test_secret_hygiene.py tests/unit/test_init_local_secrets.py
uv run --offline ruff check tests/unit/domain tests/unit/ingestion tests/unit/test_settings.py tests/unit/test_cli.py tests/unit/test_secret_hygiene.py tests/unit/test_init_local_secrets.py
git diff --check -- tests/unit/domain tests/unit/ingestion tests/unit/test_settings.py tests/unit/test_cli.py tests/unit/test_secret_hygiene.py tests/unit/test_init_local_secrets.py
```

Workstream B:

```bash
uv run --offline ruff format --check tests/unit/infra tests/unit/ontology tests/contract/test_ontology_contract.py
uv run --offline ruff check tests/unit/infra tests/unit/ontology tests/contract/test_ontology_contract.py
git diff --check -- tests/unit/infra tests/unit/ontology tests/contract/test_ontology_contract.py
```

Workstream C:

```bash
uv run --offline ruff format --check tests/unit/extraction tests/unit/aggregation
uv run --offline ruff check tests/unit/extraction tests/unit/aggregation
git diff --check -- tests/unit/extraction tests/unit/aggregation
```

Workstream D:

```bash
uv run --offline ruff format --check tests/unit/storage tests/unit/embedding tests/integration
uv run --offline ruff check tests/unit/storage tests/unit/embedding tests/integration
git diff --check -- tests/unit/storage tests/unit/embedding tests/integration
```

Expected: every command exits 0.

- [ ] **Step 8: Complete the workstream report and stop without staging**

Append:

Under `## Result`, state the actual integer collected count and line count before and after,
the exact focused command and output summary, every changed file, every intentionally
unchanged test family with its reason, and the literal statement `Production files changed:
none`.

Run:

```bash
git status --short
```

Expected: only assigned test paths plus edits from other disjoint workstreams are visible. Do not use `git add` or `git commit`.

- [ ] **Step 9: Dispatch Workstream D after one parallel slot becomes available**

Use the exact Workstream D file list and `sdd/test-slimming/group-d-report.md`. Perform Steps 3-8 without modifying files owned by A-C.

### Task 2: Integrated Verification, Review, and Commit

**Files:**
- Modify only the test files changed by Task 1.
- Read reports: `sdd/test-slimming/group-{a,b,c,d}-report.md`.

**Interfaces:**
- Consumes: four disjoint cleanup diffs and contract matrices.
- Produces: one reviewed test-only commit preserving Core Tasks 1-9 behavior.

- [ ] **Step 1: Audit file ownership and deletion evidence**

Run:

```bash
git diff --name-only
git status --short
```

Expected: every changed tracked path starts with `tests/`; no `src/`, `prompts/`, `config/`, `pyproject.toml`, or lock file appears.

Read all four reports. For each `merge` or `delete` row, verify the named retained test/case exists in the resulting files. Restore any test whose equivalent cannot be demonstrated.

- [ ] **Step 2: Run the complete offline suite once**

Run:

```bash
env -u KE_MEMORY_EMBEDDING_PATH uv run --offline pytest -q
```

Expected: zero failures, exactly one opt-in live embedding skip, and no warnings. The pass count is descriptive and may be lower than 586.

- [ ] **Step 3: Run project-wide static and repository checks**

Run:

```bash
uv run --offline ruff format --check .
uv run --offline ruff check .
uv run --offline pyright
git diff --check
git grep -nE 'sk-[A-Za-z0-9]|/public/home/wwb/memory(/|$)|fusion-memory' -- tests
git status --short --branch
```

Expected: Ruff exits 0, Pyright reports `0 errors, 0 warnings, 0 informations`, diff check exits 0, the forbidden-reference/secret scan prints no matches and exits 1, and status contains only the intended test edits.

- [ ] **Step 4: Record descriptive before/after metrics**

Run:

```bash
find tests -type f -name 'test_*.py' -print0 | xargs -0 wc -l | tail -n 1
grep -RhoE '^((async )?def test_|[[:space:]]+(async )?def test_)' tests --include='test_*.py' | wc -l
env -u KE_MEMORY_EMBEDDING_PATH uv run --offline pytest --collect-only -q
```

Record total lines, function count, and collected count beside the baseline. Do not make further edits solely to improve these numbers.

- [ ] **Step 5: Commit the verified cleanup**

Run:

```bash
git add tests
git commit -m "test: slim core contract suite"
```

Do not add the SDD reports to Git. Confirm `git status --short --branch` contains only the branch header.

- [ ] **Step 6: Obtain an independent integrated review**

Generate one review package from the cleanup base through the cleanup commit. Give the reviewer the implementation plan and all four SDD report paths. The reviewer checks:

- every production path is untouched;
- each removal has a valid retained equivalent in the four reports;
- parameterization preserves descriptive failure identity;
- no distinct trust boundary, rollback point, error class, lifecycle/reference level, provenance rule, temporal rule, or integration responsibility was collapsed;
- the new suite remains readable and focused.

Critical or Important findings are fixed in tests only, followed by the affected focused suite and re-review.

- [ ] **Step 7: Run the post-review root verification and record progress**

Run:

```bash
env -u KE_MEMORY_EMBEDDING_PATH uv run --offline pytest -q
uv run --offline ruff format --check .
uv run --offline ruff check .
uv run --offline pyright
git diff --check
git status --short --branch
```

Expected: zero failures, one live embedding skip, clean static checks, and a clean worktree. Record the cleanup commit range and clean review in `sdd/progress.md`.
