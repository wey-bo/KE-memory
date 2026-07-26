# KE Memory Demo

This repository runs a KE-only memory pipeline over the fixed BEAM subset. The primary order is
strict: Elasticsearch health, exact index identity pinning, input and structured-model preflight,
ingestion, Turn KE extraction, source-ordered lifecycle reconciliation, Session aggregation,
Conversation-local semantic DAG construction, and `ke-ready` preparation. The ontology identity is
re-read before every stage promotion.

It also exposes an online ontology-led memory service for task/workflow agents and personal
long-term assistants. The online path preserves raw turns, keeps extraction confidence,
epistemic trust, and memory utility separate, compiles admitted records into closed KEOL bundles,
stores revisions atomically, executes symbolic queries first, and invokes dense retrieval only
for explicitly unresolved entity or predicate slots.

## Online Agent Memory

The default `config/online.toml` mode is `production`. It reuses the configured structured work
model, Elasticsearch ontology vocabulary, Turn KE extractor, and lifecycle maintainer. Startup
fails explicitly when required credentials are missing. To run without model or network calls,
set `mode = "offline"`; offline mode preserves raw turns but deliberately extracts no durable KE.

```bash
uv sync --frozen
uv run ke-memory-serve
```

The default service listens on `http://127.0.0.1:8787`. Its main endpoints are:

- `GET /healthz`
- `POST /v1/memory/turns`
- `POST /v1/memory/search`
- `POST /v1/memory/context`
- `POST /v1/memory/corrections`
- `GET /v1/memory/{memory_id}`
- `DELETE /v1/memory/{memory_id}`

SQLite/WAL is the authoritative single-host store. Every operation is scoped by
`tenant_id + user_id + agent_id`; normal reads expose only current, non-tombstoned records.
Corrections append a replacement and supersede the previous memory. Forgetting appends a
retracted revision and tombstones the head without editing raw turns or prior revisions.

See `docs/online-memory-api.md` for request examples and the complete trust, lifecycle, and
fallback contract.

## Local Configuration

Create `.env.local` with mode `0600` and these variable names:

```text
KE_MEMORY_WORK_API_KEY
KE_MEMORY_JUDGE_API_KEY
KE_MEMORY_ES_URL
KE_MEMORY_ES_INDEX
KE_MEMORY_ES_API_KEY
```

Do not commit `.env.local`. The primary pipeline does not require
`KE_MEMORY_EMBEDDING_PATH`; embedding is disabled in `config/models.toml`.

## KE-only Commands

All stage commands take `--run-id`, `--config-root`, and `--state-root`. A stage refuses to run when
its predecessor is absent.

```bash
uv run ke-memory preflight --run-id demo --config-root . --state-root ../ke-memory-state
uv run ke-memory ingest --run-id demo --config-root . --state-root ../ke-memory-state
uv run ke-memory extract-turn-ke --run-id demo --config-root . --state-root ../ke-memory-state
uv run ke-memory aggregate-session --run-id demo --config-root . --state-root ../ke-memory-state
uv run ke-memory build-semantic-dag --run-id demo --config-root . --state-root ../ke-memory-state
uv run ke-memory prepare-ke --run-id demo --config-root . --state-root ../ke-memory-state
```

`run-pipeline` executes the same sequence through `ke-ready`. `retrieve` requires a verified full
snapshot SHA and selects exactly one Conversation scope. `verify-snapshot` checks out the supplied
SHA and revalidates the canonical stage.

## KE-only Evaluation and Reports

The formal evaluator uses the fixed 60-question set and an independent Judge. A smoke run is
non-formal and cannot create an `evaluation-complete` snapshot.

```bash
uv run ke-memory evaluate preflight --run-id demo --snapshot-id <ke-ready-sha> \
  --config-root . --state-root ../ke-memory-state
uv run ke-memory evaluate smoke --run-id demo --snapshot-id <ke-ready-sha> \
  --config-root . --state-root ../ke-memory-state
uv run ke-memory evaluate run --run-id demo --snapshot-id <ke-ready-sha> \
  --config-root . --state-root ../ke-memory-state
uv run ke-memory evaluate report --run-id demo --snapshot-id <evaluation-complete-sha> \
  --state-root ../ke-memory-state
```

Only an exact complete 60/60 answer and Judge result set with the frozen 54 mapped and six explicit
unmappable gold records is promoted. Incomplete runs keep answer/Judge checkpoints and write an
explicitly incomplete diagnostic report under ignored `exports/<run-id>/incomplete/`; they never
create `evaluation-complete`. The `evaluate report` command accepts only a verified canonical
`evaluation-complete` snapshot and rechecks each document hash before materializing
`report.md`, `question_results.csv`, and `metrics.json` under ignored `exports/<run-id>/`.

`data/baselines/public_results.toml` is a sourced public-results appendix only. Its Mem0,
Graphiti, Hindsight, and MemPalace records remain not reproduced, not found, and/or not directly
comparable as recorded. The evaluator does not install or run baseline systems and does not
average, normalize, order, or convert their published metrics against the KE-only result.

## State Layout

Canonical artifacts are stored under
`<state-root>/runs/<run-id>/<stage>/` and committed to the separate Git repository at
`<state-root>/.git`. Checkpoints and disposable Conversation-scoped SQLite indexes live under the
ignored `checkpoints/`, `cache/`, and `exports/` paths. Snapshots contain only ontology documents
actually bound to KEs, never the complete Elasticsearch vocabulary.

Embedding and baseline systems are not part of the primary run. The formal path indexes and
retrieves only current KEs plus aggregate nodes while retaining every KE revision in canonical
history for audit.
