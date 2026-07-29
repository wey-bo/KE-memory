# Next-prep normalization notes

This directory is a normalized snapshot of the active KE-memory next-prep workspace:

- source: `/public/home/wwb/KE-mem/KE-memory-next-prep-20260727`
- target: `/public/home/wwb/KE_mem/ke-memory-demo/.worktrees/next-prep-normalization-20260729/research/next-prep`
- target branch: `codex/next-prep-normalization-20260729`
- target role: research and prototype preparation for the next KE-memory implementation

`research/next-prep/` is intentionally not an installable package root. The runtime repo layout remains:

```text
src/ke_memory_demo/             memory core
service/ke_memory_service/      HTTP/MCP delivery and runtime composition
ontology/ke_memory_ontology/    ontology/profile adapters
```

## Directory boundary

Migrated prep materials stay under `research/next-prep/`.

Do not place this snapshot under `eval/`. `eval/` is reserved for future automatic test/evaluation logic: stable runners, scorers, fixture adapters, and report generation that are promoted into the runtime repository after the end-to-end flow is ready.

## Copy policy

The migration copied docs, data, tests, tools, knowledge-extraction outputs, and compact artifacts that are useful for handoff and follow-up development.

The migration excluded local runtime or high-volume generated state:

- `.git/`, `.agents/`, `.codex/`
- `.venv*/`, `.fastembed-cache/`, `.hf-cache/`
- `.pytest_cache/`, `.tmp/`, `tmp/`, `__pycache__/`, `*.pyc`
- `artifacts/ontology-memory-experiment/runs/`

`artifacts/ontology-memory-experiment/runs/` was excluded because it was large generated run state, not because its conclusions are invalid. Reports and frozen gold remain in the snapshot where copied.

## Concurrent-source note

The source prep workspace is still being edited by other sessions. This snapshot is therefore a branch-local handoff point, not a live mirror.

Known concurrent/invalid source item omitted from this snapshot:

```text
artifacts/automatic-extraction-assessment/typed-extractor-v3-fresh-hidden-prereg-v1/authoring-implementation-receipt.json
```

At migration time this source file appeared as root-owned, 0-byte, mode `----------`, mtime 1970, and caused `rsync` code 24. It was excluded and should not be treated as an accepted receipt. Do not delete or repair it from this branch; let the active fresh-v3 authoring session finish and hand off a reviewed receipt.

## Parallel-session boundaries

Do not overwrite the active source-workspace tracks until their owning sessions hand off reviewed output:

- fresh-v3 authoring/receipt
- QuerySlotPlan/query compiler v2 work
- L1 ontology linking/admission work

This branch can continue with integration scaffolding, documentation, migration validation, and isolated development against the copied snapshot.

## Verification commands

Target repo baseline:

```bash
cd /public/home/wwb/KE_mem/ke-memory-demo/.worktrees/next-prep-normalization-20260729
PYTHONPATH=/public/home/wwb/KE_mem/KEOL-44631e6/src:$PWD/src:$PWD/service:$PWD/ontology   /public/home/wwb/KE_mem/ke-memory-demo/.venv/bin/python -m pytest -q   --import-mode=importlib -p no:cacheprovider   --basetemp /tmp/ke-memory-demo-normalization-baseline
```

Copied prep focused checks:

```bash
cd /public/home/wwb/KE_mem/ke-memory-demo/.worktrees/next-prep-normalization-20260729/research/next-prep
PYTHONPATH=. /public/home/wwb/KE-mem/KE-memory-next-prep-20260727/.venv-h100/bin/python -m pytest   tests/natural_memory_benchmark/test_l1_ontology_linking.py   tests/natural_memory_benchmark/test_l1_admission.py -q

PYTHONPATH=. /public/home/wwb/KE-mem/KE-memory-next-prep-20260727/.venv-h100/bin/python -m pytest   tests/natural_memory_benchmark/test_query_compiler_v2_proposal_eval.py   tests/natural_memory_benchmark/test_query_compiler_v2_proposal_eval_cli.py   tests/natural_memory_benchmark/test_query_compiler_v2_dev_qualification.py -q
```
