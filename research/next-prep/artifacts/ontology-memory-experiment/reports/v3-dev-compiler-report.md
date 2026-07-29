# V3 Automatic Compiler Dev Report

Date: 2026-07-25

## Decision

Status: dev-only compiler repair completed.

This is not a new hidden-set gate decision. The previous v2 hidden decision remains `fail` until a new hidden split is frozen and evaluated.

## What Changed

- Automatic temporal parsing now preserves a provenance/supersession closure for correction updates.
- Automatic query plans now use canonical predicates shared with the representation layer: `linked_to` and `sense_of`.
- Automatic multihop execution now binds `project` traversal targets without accepting unrelated project links.
- Symbolic execution excludes `rejected` and `obsolete` lifecycle records from normal active matching.
- Explicit absence records now dominate `require_explicit_absence` owner queries instead of allowing later owner claims to leak through the answer projection.
- Lexical context propagation links ledger/account-record turns to the original object and location while keeping later owner claims outside the absence evidence closure.

## Verification

Targeted TDD regression:

```powershell
D:\Anaconda\python.exe -m pytest tests\ontology_memory_experiment\test_executors.py -q --import-mode=importlib -p no:cacheprovider --basetemp .t\ome-v3-green-3
```

Result:

```text
12 passed in 0.28s
```

Ontology-memory module tests:

```powershell
D:\Anaconda\python.exe -m pytest tests\ontology_memory_experiment -q --import-mode=importlib -p no:cacheprovider --basetemp .t\ome-v3-module-2
```

Result:

```text
106 passed in 31.88s
```

Diagnostic dev grid:

```text
run_id: run-20260725T172000Z-v3-diagnostic-dev
rows: 432
errors: 0
verify-run: valid
```

Automatic diagnostic dev metrics:

| Arm | Evidence Set Exact Match | Answer | Constraint | Critical FP | Fallback |
| --- | ---: | ---: | ---: | ---: | ---: |
| B2 | 0.028 | 0.389 | 0.000 | 0.972 | 0.000 |
| O+ | 1.000 | 1.000 | 1.000 | 0.000 | 0.000 |
| O+E | 1.000 | 1.000 | 1.000 | 0.000 | 0.000 |

## Boundary

The diagnostic encoder is not the real dense model. A real dense dev rerun was attempted with `D:\Anaconda\python.exe`, but that environment currently lacks `fastembed`, so the real dense dev grid was not rerun in this pass.

Fallback remains vacuous: `O+E` still equals `O+` and no embedding fallback fired. The next experimental step is to freeze v3 fallback probes that trigger only on declared lexical/entity/predicate gaps, then run a new hidden decision set.
