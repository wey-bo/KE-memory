# Git-Backed Memory History Implementation Plan

**Goal:** Build an isolated local bare-Git authority layer for checkpointed memory history, deterministic replay, tombstones, and safe preparation of hard-purge repository epochs.

**Architecture:** Canonical memory artifacts are immutable JSON blobs in a bare Git repository. Checkpoints use Git plumbing and atomic compare-and-swap ref updates; online databases remain rebuildable projections. Permanent deletion prepares a separately verified repository epoch and never deletes the source repository automatically.

**Tech Stack:** Python 3.13, Pydantic v2, standard-library subprocess/pathlib/tempfile, Git 2.47 plumbing, pytest.

---

## Isolation Boundary

Create only:

- tools/natural_memory_benchmark/git_memory_history.py
- tools/natural_memory_benchmark/git_memory_history_cli.py
- tests/natural_memory_benchmark/test_git_memory_history.py

Do not modify active L2 files, central CLI, shared status documents, or frozen artifacts while the H100 Codex plugin is active.

The migrated workspace has an empty .git directory, so source-code commits and worktrees are unavailable. Preserve implementation evidence through focused RED/GREEN outputs and file hashes. Do not initialize or repair the workspace .git.

## Task 1: Artifact And Checkpoint Contracts

1. Write failing tests for payload SHA-256, path-safe IDs, deterministic paths, unique references, deterministic checkpoint IDs, and contiguous sequence metadata.
2. Run the focused test and confirm an import failure because the module is absent.
3. Implement strict models: HistoryArtifactReference, HistoryArtifact, CheckpointManifest, CheckpointReceipt, RepositoryMetadata, RepositoryState, HardPurgeRequest, and HardPurgeResult.
4. Implement make_history_artifact and make_checkpoint_manifest.
5. Re-run the focused tests.

## Task 2: Bare Repository Initialization

1. Add a failing test for a bare repository containing repository.json, one epoch record, sequence-zero state/current.json, and refs/heads/authoritative.
2. Implement GitMemoryHistoryRepository.initialize(repo_path, workspace_id, created_at).
3. Use hash-object, a temporary index, write-tree, commit-tree, and update-ref.
4. Verify deterministic metadata and genesis verification.

## Task 3: Closed TurnBundle Adapter

1. Add a failing test using real TurnBundleRevision, SourceRecordRevision, EvidenceSpan, L1 unit, and MemoryUnitRevision fixtures.
2. Implement make_turn_bundle_history_artifact.
3. Run validate_turn_bundle_closure before serialization.
4. Embed exact bundle, raw source revisions, and unit revisions.
5. Reject missing, extra, or inconsistent revisions.
6. Confirm a Git-only read returns exact raw text and L1 payload.

## Task 4: Checkpoint Publication And Verification

1. Add failing tests for first checkpoint, second checkpoint, byte-identical retry, stale expected head, immutable collision, and tamper detection.
2. Implement make_checkpoint, commit_checkpoint, read_artifact, read_state, and verify.
3. Publish with compare-and-swap update-ref.
4. Confirm failed publication never advances the ref.

## Task 5: Tombstone And Purge Epoch

1. Add a failing test proving tombstone append does not remove old bytes.
2. Add failing tests for a separately prepared purge repository.
3. Require exact source epoch and head.
4. Remove target and transitive dependents, preserve retained artifact bytes, and write a fingerprint-only purge manifest.
5. Verify the new epoch and confirm the source head is unchanged.
6. Reject an existing destination or stale source head.
7. Do not implement automatic source deletion, pointer switching, mirror deletion, or blob deletion.

## Task 6: Separate Manual CLI

1. Add failing parser and subprocess tests for init, commit, verify, show-state, and prepare-hard-purge.
2. Implement tools/natural_memory_benchmark/git_memory_history_cli.py.
3. Do not modify the central cli.py while L2 work is active.
4. Emit canonical JSON and return nonzero on contract or Git failure.

## Task 7: Verification And Handoff

Run:

    .venv-h100/bin/python -m pytest -p no:cacheprovider tests/natural_memory_benchmark/test_git_memory_history.py -q --basetemp=/tmp/ke-memory-git-history-focused

Run adjacent tests:

    .venv-h100/bin/python -m pytest -p no:cacheprovider tests/natural_memory_benchmark/test_turn_bundle.py tests/natural_memory_benchmark/test_authoritative_memory.py tests/natural_memory_benchmark/test_git_memory_history.py -q --basetemp=/tmp/ke-memory-git-history-adjacent

Compile:

    .venv-h100/bin/python -m compileall -q tools/natural_memory_benchmark/git_memory_history.py tools/natural_memory_benchmark/git_memory_history_cli.py

Record exact test counts, Git version, file SHA-256 values, the empty workspace .git state, untouched active L2 files, and current H100 Codex status.

Do not update README.md, AGENTS.md, or the shared scheduling document until the L2 task releases those shared files. Provide a handoff telling the server Codex plugin which isolated files to review and integrate.

## Completion Record

- Focused Git-history suite: 36 passed.
- Adjacent TurnBundle, authoritative-memory, and Git-history suite: 63 passed.
- Complete `tests/natural_memory_benchmark`: 364 passed after the server Codex shared-CLI repair.
- `compileall`, `tabnanny`, and the 100-character line scan: clean.
- Git runtime: 2.47.3.
- Workspace `.git`: still an empty directory; it was not initialized or repaired.
- Shared L1/L2 extraction files and central `cli.py`: not modified by this isolated task.
