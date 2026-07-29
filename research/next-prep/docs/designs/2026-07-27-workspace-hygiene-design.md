# Workspace Hygiene and Conservative Cleanup Design

Status: approved by user direction and frozen for implementation on 2026-07-27.

## Core impact

`none`

This wave changes no base ontology, dynamic ontology extension interface, L1/L2 extraction stage, question processing, symbolic retrieval, guarded embedding fallback, formal gold, or experiment result.

## Problem

The workspace has accumulated several generations of pytest basetemp directories, isolated replay directories, staging data, downloaded source copies, a duplicate virtual environment, and a duplicate model cache. The first inventory found about 4.1 GiB total, including roughly 2.58 GiB under test/replay roots and another 348 MiB under `tmp/`.

## Approaches considered

1. Delete or compress old formal experiment runs. This releases more space but weakens auditability and can break documented paths. Rejected for this wave.
2. Conservatively remove only reproducible temporary roots and prevent recurrence. This releases most of the accidental growth without touching formal evidence. Selected.
3. Externalize `.venv-dense` and model caches. This saves additional space but changes environment bootstrap and warm-cache assumptions. Deferred.

## Cleanup policy

The cleaner may remove only top-level directories whose names are explicitly allowed:

- `.t`
- `.tmp`
- `.pytest_cache`
- `.pytest-tmp-*`
- `t`
- `t2`
- selected one-level children of `tmp/`: `ontology-venv`, ontology gold/audit staging directories, `pdfs`, `amr-pilot-review`, `amr-pilot-staging`, and `ontology-audit-source-check`

It must refuse nested paths, paths outside the resolved workspace, symlink/reparse-point targets, and every non-allowlisted name. Before deletion it freezes an inventory with file count and byte count. At apply time it recomputes those values and refuses a changed target, preventing an inventory/apply race.

Two `tmp/` children are explicitly retained in this wave: `amr-pilot-sources` preserves optional offline source replay, and `ontology-model-cache` remains the current ontology CLI default. Unknown future `tmp/` children are also retained until classified.

The following remain protected:

- `artifacts/`
- `data/`
- `docs/`
- `archive/`
- `knowledge-extraction/`
- `knowledge_pipeline/`
- `tools/`
- `tests/`
- `.venv-dense/`
- `.fastembed-cache/`
- `.hf-cache/`

## Verification

The wave requires:

- RED/GREEN tests for allowlist discovery, protected paths, inventory drift rejection, deletion, and CLI output;
- a frozen pre-cleanup inventory and post-cleanup report under `artifacts/project-structure/`;
- full test suites using an external basetemp after cleanup;
- natural slice, ledger, identity proposal, identity v1, and authoritative v5 validation/hash checks;
- a second inventory showing no remaining allowlisted cleanup target.

## Claim boundary

This is workspace hygiene, not experiment pruning. Formal historical runs remain in place. Any later compression or removal under `artifacts/ontology-memory-experiment/` requires a separate referenced-run audit and explicit decision.
