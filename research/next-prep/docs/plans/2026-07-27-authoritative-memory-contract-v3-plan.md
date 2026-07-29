# Authoritative Memory Contract v3 Implementation Plan

**Goal:** Build and verify a non-destructive v3 authoritative memory contract, Extended-AMR v2 representation, and immutable v5 conformance run over the existing five real-slice probes.

**Architecture:** Add new v3 models and execution beside the frozen v2 implementation. Deterministically migrate the real-slice v2 bundle into raw/source/unit revision ledgers, structured L2 claims, split closure specs/evaluations, and authoritative query plans; then encode the same logical bundle as explicit Extended-AMR v2 graphs and compare exact round-trip, query parity, source integrity, and closure freshness.

**Tech Stack:** Python 3.13, Pydantic v2, pytest, canonical JSON/SHA-256, existing natural benchmark artifact loaders and immutable writers.

---

The workspace has no valid Git repository, so worktree creation, commits, and SHA-based diff review are unavailable. The isolation substitute is append-only: v2/v4 code paths and artifacts remain readable and reproducible; new v3/v5 files use new names; reviewers inspect the exact changed file set.

### Task 1: Authoritative ledger and evidence contract

**Files:**
- Create: `tools/natural_memory_benchmark/authoritative_memory.py`
- Create: `tests/natural_memory_benchmark/test_authoritative_memory.py`

**Step 1: Write the failing ledger tests**

Add tests for deterministic artifact/source/unit revision IDs; exact evidence quote/hash/span binding; conflicting duplicate source revisions; linear two-revision history; cycle, branch, gap, wrong parent, bad payload hash, and non-leaf current-pointer rejection.

**Step 2: Run RED**

Run:

```powershell
& 'D:\Anaconda\python.exe' -m pytest tests\natural_memory_benchmark\test_authoritative_memory.py -q --basetemp=.tmp\v3-red-ledger
```

Expected: collection/import failure because v3 models and validators do not exist.

**Step 3: Implement the minimum ledger**

Implement strict models for `RawArtifactRevision`, `SourceRecordRevision`, `EvidenceSpanV2`, `SourceBindingV2`, `L1MemoryUnitV2`, `ProducerIdentity`, `MemoryUnitRevision`, and canonical hash/ID helpers. Keep resolver dispatch in the new v3 module so the frozen v2 evidence path is untouched.

**Step 4: Run GREEN**

Run the same focused command. Expected: all Task 1 tests pass.

### Task 2: Structured L2 claims and authoritative execution

**Files:**
- Modify: `tools/natural_memory_benchmark/authoritative_memory.py`
- Modify: `tests/natural_memory_benchmark/test_authoritative_memory.py`

**Step 1: Write failing semantic-query tests**

Cover operator/sense filtering, entity and exact role matching, modality mismatch, polarity mismatch, exact event/valid/transaction-time mismatch, constrained display-only L2 exclusion, matched-claim-only evidence return, duplicate claim IDs, and invalid claim support.

Add a regression proving `count(led_projects_by_user)=2` remains display-only when four provisional project identities are present.

**Step 2: Run RED**

Run the focused test file and confirm failures are missing structured L2/query behavior rather than setup errors.

**Step 3: Implement typed L2 and query models**

Implement `L2StructuredClaim`, optional typed aggregate semantics, `L2MemoryUnitV2`, `ExactTimeConstraint`, `AuthoritativeQueryPlan`, a shared semantic matcher, and `execute_authoritative_query`. Return L2 evidence only through matched pinned claim supports. A count query without identity-backed aggregate semantics must abstain with `structured_l2_identity_unresolved`.

**Step 4: Run GREEN and the v2 regression suite**

```powershell
& 'D:\Anaconda\python.exe' -m pytest tests\natural_memory_benchmark\test_authoritative_memory.py tests\natural_memory_benchmark\test_semantic_ir.py tests\natural_memory_benchmark\test_representation_contract.py -q --basetemp=.tmp\v3-green-l2
```

Expected: all selected tests pass and frozen v2 behavior remains unchanged.

### Task 3: Closure specs, evaluations, and freshness

**Files:**
- Modify: `tools/natural_memory_benchmark/authoritative_memory.py`
- Modify: `tests/natural_memory_benchmark/test_authoritative_memory.py`

**Step 1: Write failing closure tests**

Cover separate claim/query contexts; deterministic evaluation IDs and result hashes; explicit missing causal-link slot; stale detection after spec, policy/evaluator, target claim/query, query plan, context scope, available-unit, dependency revision/content, source revision, and slot-binding changes; no staleness from scope-external changes; stale evaluation cannot answer or trigger fallback; active L2 rejects query-context, missing, stale, or incomplete evaluation.

**Step 2: Run RED**

Run the focused file and confirm each test fails for missing closure behavior.

**Step 3: Implement closure evaluation**

Implement `ClosureSlotSpec`, `ClosureSpec`, `ClaimClosureContext`, `QueryClosureContext`, `ClosureSlotResult`, `DependencyFingerprint`, `ClosureEvaluation`, spec/evaluation builders, freshness assessment, recomputation-result parity, and bundle integrity integration.

**Step 4: Run GREEN**

Run the focused test file and confirm all closure tests pass.

### Task 4: Deterministic v2-to-v3 real-slice migration

**Files:**
- Modify: `tools/natural_memory_benchmark/authoritative_memory.py`
- Create: `tests/natural_memory_benchmark/test_authoritative_migration.py`

**Step 1: Write failing migration tests**

Cover two byte-identical migrations with fixed inputs; 13 L1, one L2, 13 unique source revisions, two referenced raw artifacts, revision-1-only creation, semantic `supersedes` preservation, explicit closure slots, safe non-count L2 claim, source resolver replay, five query results, and raw path/hash/size tamper rejection.

**Step 2: Run RED**

```powershell
& 'D:\Anaconda\python.exe' -m pytest tests\natural_memory_benchmark\test_authoritative_migration.py -q --basetemp=.tmp\v3-red-migration
```

Expected: migration API missing.

**Step 3: Implement migration and authoritative source validation**

Build artifact revisions from `source-manifest.json`, source revisions from `evidence-corpus.json`, L1/L2 revision 1 records, explicit structured L2 mappings, claim/query closure specs and freshly recomputed evaluations, and authoritative query plans. Require fixed transaction time and producer version; never use the wall clock. Ignore legacy materialized closure outcomes except as an optional parity diagnostic.

**Step 4: Run GREEN**

Run both authoritative test files. Expected: deterministic migration and source replay pass.

### Task 5: Extended-AMR v2 graph adapter

**Files:**
- Create: `tools/natural_memory_benchmark/extended_amr_v2_adapter.py`
- Create: `tests/natural_memory_benchmark/test_extended_amr_v2_adapter.py`

**Step 1: Write failing adapter tests**

Cover typed top-level ledgers/specs/evaluations and `current_revision_ids`; absence of opaque `l1_units`, `l2_units`, or unit-revision payload copies; explicit L1 predicate/role graph; explicit L2 claim/role/support graph; closure spec/evaluation reference edges; exact multi-revision round-trip; and malformed node, role, support, hash, policy, spec revision, or reference rejection.

**Step 2: Run RED**

Run the new adapter test file. Expected: adapter module missing.

**Step 3: Implement the minimal v2 adapter**

Encode every unit revision as an explicit graph and each revision header as typed metadata. Decode graphs back into revision payloads and run v3 integrity/freshness validation before returning a bundle.

**Step 4: Run GREEN**

Run authoritative plus adapter tests. Expected: exact round-trip and malformed-payload rejection pass.

### Task 6: V5 conformance and immutable artifacts

**Files:**
- Create: `tools/natural_memory_benchmark/authoritative_conformance_runner.py`
- Modify: `tools/natural_memory_benchmark/cli.py`
- Create: `tests/natural_memory_benchmark/test_authoritative_conformance_runner.py`
- Create: `artifacts/natural-benchmark-slices/slice-v1/representation-conformance-results-v5.json`
- Create: `artifacts/natural-benchmark-slices/slice-v1/representation-conformance-report-v5.md`

**Step 1: Write failing conformance tests**

Require exact native and Extended-AMR v2 round-trip, five scoped adapter-parity checks, five frozen correctness expectations, source/revision integrity metrics, closure fresh/stale/result-parity counts, hard failures for stale evaluation, active L2 without fresh claim closure, and unresolved count identity, capability promotion only after measured gates, and immutable replay/different-overwrite rejection.

**Step 2: Run RED**

Run the new conformance test file and confirm the v5 runner/CLI are absent.

**Step 3: Implement the v5 runner and CLI**

Build the authoritative bundle, validate the frozen raw sources, evaluate the native carrier and Extended-AMR v2, render the report, and write both outputs through immutable writers. Report unresolved display count semantics explicitly; do not force `authoritative_ready=true`.

**Step 4: Run GREEN and generate v5**

```powershell
& 'D:\Anaconda\python.exe' -m tools.natural_memory_benchmark.cli run-authoritative-conformance --root artifacts\natural-benchmark-slices --slice-id slice-v1 --results artifacts\natural-benchmark-slices\slice-v1\symbolic-fallback-answerability-v2-fastembed-results.json --output artifacts\natural-benchmark-slices\slice-v1\representation-conformance-results-v5.json --report artifacts\natural-benchmark-slices\slice-v1\representation-conformance-report-v5.md --run-id run-20260727T-authoritative-v5
```

Re-run the identical command to prove immutable replay.

### Task 7: Documentation and full verification

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `安排.md`
- Modify: `docs/designs/2026-07-27-representation-agnostic-memory-contract-design.md`
- Modify: `docs/designs/2026-07-27-event-role-evidence-closure-representation-design.md`

**Step 1: Update factual status**

Record implemented schema versions, exact test/artifact evidence, capability results, the display-count identity limitation, and the boundary between conformance and product/benchmark claims.

**Step 2: Run full fresh verification**

```powershell
New-Item -ItemType Directory -Force '.tmp' | Out-Null
& 'D:\Anaconda\python.exe' -m pytest tests\natural_memory_benchmark -q --basetemp=.tmp\v3-full
& 'D:\Anaconda\python.exe' -m tools.natural_memory_benchmark.cli validate-slice --root artifacts\natural-benchmark-slices --slice-id slice-v1
& 'D:\Anaconda\python.exe' -m tools.natural_memory_benchmark.cli validate-ledger --path artifacts\natural-benchmark-slices\external-results-ledger.json
```

Then parse the v5 JSON, verify required IDs/counts/hashes, replay the immutable generation command, and compare bytes.

**Step 3: Independent reviews**

Use one read-only specification reviewer and one read-only code-quality reviewer over the exact v3/v5 changed file list. Resolve every finding before reporting completion.
