# Next Prep Normalization Implementation Plan

**Goal:** Normalize the active KE-memory next-prep workspace into the ke-memory-demo repository without disrupting parallel sessions.

**Architecture:** Keep src, service, and ontology as the installable runtime package roots. Put migrated research and prototype material under research/next-prep. Reserve eval for future automatic evaluation logic only.

**Tech Stack:** Python 3.12 for ke-memory-demo runtime checks. Copied next-prep diagnostics currently use the H100 Python 3.13 prep environment.

---

### Task 1: Snapshot the shared prep workspace

- Copy source, tests, docs, data, gold, reports, and compact assessment artifacts from /public/home/wwb/KE-mem/KE-memory-next-prep-20260727.
- Exclude virtual environments, caches, temporary directories, Python bytecode, and artifacts/ontology-memory-experiment/runs/.
- Record concurrently changing or unreadable source paths in research/next-prep/NORMALIZATION.md.
- Verify eval is not created.

### Task 2: Keep root test discovery stable

- Restrict default pytest discovery to the existing top-level tests tree.
- Leave prep tests runnable explicitly from research/next-prep with PYTHONPATH=.
- Run the existing ke-memory-demo test suite from the branch worktree.

### Task 3: Commit local branch and continue isolated development

- Run focused prep checks for stable L1 linking/admission and Query tracks.
- Run core ke-memory-demo tests.
- Commit to local branch codex/next-prep-normalization-20260729.
- Continue development only in this branch unless another active session explicitly hands off its files.
