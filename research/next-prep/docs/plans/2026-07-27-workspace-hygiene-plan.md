# Workspace Hygiene Implementation Plan

**Goal:** Remove reproducible workspace-local temporary data with a strict allowlist, preserve all formal artifacts, and prevent the same growth pattern from recurring.

**Architecture:** Add a standalone hygiene CLI that inventories top-level cleanup targets, freezes their sizes, and applies deletion only when the current target exactly matches the plan. Update ignore rules, generate before/after records, and verify the complete memory benchmark surface from an external basetemp.

**Tech Stack:** Python 3.13 standard library, pytest, canonical JSON/SHA-256, PowerShell verification.

---

## TODO 1: Write RED tests

Create `tests/test_workspace_hygiene.py` covering:

1. only allowlisted top-level directories are discovered;
2. protected roots and nested lookalikes are retained;
3. plans include deterministic file/byte counts and `core_impact=none`;
4. apply removes exact planned targets;
5. apply rejects target drift and non-allowlisted paths;
6. CLI inventory and clean commands write canonical JSON.

Run with a repository-local short basetemp and confirm the module import fails before implementation.

## TODO 2: Implement the hygiene CLI

Create `tools/workspace_hygiene.py` with:

- strict top-level allowlist discovery;
- a second explicit allowlist for classified one-level `tmp/` children;
- path containment and reparse-point checks;
- deterministic inventory;
- drift-checked recursive cleanup;
- immutable canonical plan/report writers;
- `inventory` and `clean` commands.

Run focused GREEN tests.

## TODO 3: Prevent recurrence

Update `.gitignore` for `.tmp/`, `.pytest-tmp-*/`, `t/`, `t2/`, `.venv*/`, `.fastembed-cache/`, and `.hf-cache/` while preserving existing entries.

## TODO 4: Apply conservative cleanup

1. Generate `artifacts/project-structure/2026-07-27-workspace-cleanup-plan.json`.
2. Record authoritative v5, identity v1, and natural proposal hashes.
3. Apply the exact frozen cleanup plan.
4. Generate `artifacts/project-structure/2026-07-27-workspace-cleanup-report.json`.
5. Re-inventory the workspace and record released bytes.

## TODO 5: Verify

Run focused hygiene tests and the existing ontology/natural/knowledge tests with a basetemp under `C:\tmp`, so verification does not repopulate the workspace. Revalidate formal slices and ledgers, then compare all protected hashes.

## TODO 6: Continue isolated proposer experiment

Only after cleanup verification, dispatch a fresh subagent that receives `public.json` and the frozen proposer output contract, with an explicit prohibition on reading `authority.json`, `gold.json`, `source-cases.json`, or prior score/report files.

No Git commit/worktree steps apply because this workspace is not a usable Git repository.
