# KE-memory Project Structure Reorganization Implementation Plan

**Goal:** Reorganize the workspace into explicit data, tools, artifacts, archive, and documentation areas without changing extraction semantics or deleting audit history.

**Architecture:** Keep the active `knowledge_pipeline/` package and `knowledge-extraction/` ledger stable. Move only root-level inputs, KEOL baseline machinery and outputs, approved documents, and invalidated v0.2 code; then update all path contracts and add a layout regression test.

**Tech Stack:** Python 3.13, pytest, PowerShell, JSON/Markdown artifacts.

---

### Task 1: Record the Current Baseline

**Files:**
- Read: `AGENTS.md`
- Read: `安排.md`
- Read: `memory实现方案汇报.pdf`
- Test: `tests/`

**Step 1:** Run the complete suite with a short writable workspace-local pytest base directory.

Run:

```powershell
D:\Anaconda\python.exe -m pytest tests -q -p no:cacheprovider --basetemp .t\b1
```

Expected: `238 passed` before migration.

### Task 2: Add the Directory Contract Test

**Files:**
- Create: `tests/test_project_layout.py`

**Step 1:** Assert that active data, tools, baseline artifacts, archived v0.2 files, and reference documents exist at their new paths.

**Step 2:** Assert that the corresponding clutter files no longer exist in the root directory.

**Step 3:** Run the test before migration.

Run:

```powershell
D:\Anaconda\python.exe -m pytest tests/test_project_layout.py -q -p no:cacheprovider --basetemp .t\layout-red
```

Expected: FAIL because the new layout does not exist yet.

### Task 3: Move Files Without Rewriting Content

**Files:**
- Move: `KE-test.json` -> `data/gold-candidates/KE-test.json`
- Move: `KE-test-config.md` -> `data/gold-candidates/KE-test-config.md`
- Move: `memory实现方案汇报.pdf` -> `docs/reference/memory实现方案汇报.pdf`
- Move: root KEOL Python tools -> `tools/keol_baseline/`
- Move: root KEOL views/config/report/run and four KEOL working directories -> `artifacts/keol-baseline/`
- Move: four invalidated v0.2 `.mjs` files -> `archive/legacy-ke-v0.2/`
- Move: root ontology design/plan and knowledge-first docs -> `docs/designs/` and `docs/plans/`

**Step 1:** Compute and retain a SHA-256 manifest for every moved file. The initial pre-move manifest failed before persistence because Windows PowerShell lacked `System.IO.Path.GetRelativePath`; retain this limitation in the final post-move manifest instead of claiming a before/after comparison.

**Step 2:** Validate every resolved source and destination is inside the workspace.

**Step 3:** Move exact paths and compare hashes after migration.

### Task 4: Update Runtime and Documentation Paths

**Files:**
- Modify: `knowledge_pipeline/cli.py`
- Modify: `tools/keol_baseline/*.py`
- Modify: `tests/test_keol_ke_test_adapter.py`
- Modify: `tests/test_export_keol_views.py`
- Modify: `tests/knowledge_pipeline/*.py`
- Modify: `tests/test_keyword_v3.py`
- Modify: `AGENTS.md`
- Modify: `安排.md`
- Modify: `docs/**/*.md`
- Create: `README.md`
- Create: `artifacts/keol-baseline/README.md`
- Create: `knowledge-extraction/README.md`
- Create: `.gitignore`

**Step 1:** Update imports and CLI defaults to the new paths.

**Step 2:** Update current-path documentation while preserving historical explanations.

**Step 3:** Add navigation documents that distinguish active results, baseline comparisons, and archives.

### Task 5: Verify and Clean Rebuildable Caches

**Files:**
- Remove if accessible: `__pycache__/`
- Remove if accessible: `.pytest_cache/`
- Remove: `.t/`
- Remove: `.tmp-test/`

**Step 1:** Run the layout test and relevant KEOL/path tests.

**Step 2:** Run the complete suite.

Run:

```powershell
D:\Anaconda\python.exe -m pytest tests -q -p no:cacheprovider --basetemp .t\final
```

Expected: all tests pass.

**Step 3:** Parse all JSON artifacts and scan text files for stale current-path references.

**Step 4:** Remove only reproducible caches and temporary test directories created by this reorganization.

Git commit steps are intentionally omitted because `.git` is empty and the workspace is not a valid repository.
