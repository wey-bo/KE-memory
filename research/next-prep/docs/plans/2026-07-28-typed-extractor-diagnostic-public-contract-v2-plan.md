# Typed Extractor Diagnostic Public Contract V2 Implementation Plan

> **For agentic workers:** Execute inline with TDD. This workspace is not a Git
> repository, so Git worktrees and commits do not apply.

**Goal:** Replace the unusable diagnostic v1 public contracts with immutable v2
contracts before sending the one-shot unchanged-prompt DeepSeek baselines.

**Architecture:** Generalize the existing L1/L2 diagnostic adapters to explicit
v1/v2 dataset configurations while preserving v1 replay. V2 sources carry
authored prompt-complete catalogs and use new opaque namespaces.

## Global Constraints

- Preserve both v1 roots byte-for-byte and read-only.
- Do not touch query compiler/executor work.
- Do not create fresh-hidden v2 or any authoritative write path.
- Do not send a model request until both v2 roots validate and replay.

### Task 1: Prompt-contract validation

- [x] Add failing L1/L2 tests for missing required v2 public catalogs.
- [x] Add explicit v2 dataset/schema/namespace support and minimal validators.
- [x] Verify the new tests pass and all existing v1 tests remain green.

### Task 2: Freeze corrected diagnostic roots

- [x] Author full v2 sources with explicit catalogs.
- [x] Align the two L2 closure expectations with frozen prompt V8.
- [x] Prepare, validate, chmod, and byte-replay both v2 roots.

### Task 3: Unchanged-prompt model baselines

- [x] Copy frozen L1 V6 and L2 V8 prompts byte-for-byte.
- [x] Freeze public-only no-history dispatches for `deepseek-chat`.
- [x] Send one official request per layer using a process-only credential.
- [x] Freeze raw response, proposals, and provenance before scoring.
- [x] Score and run strict diagnostic qualification separately per layer.
- [x] Classify errors and write the next diagnostic-only prompt-repair plan.

### Task 4: Final audit and facts update

- [x] Run focused and regression verification.
- [x] Verify protected hashes, zero writes, unresolved LongMemEval, immutable
  manual adjudications, and absence of key material.
- [x] Update `README.md`, `AGENTS.md`, and `安排.md` with the measured result.
