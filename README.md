# KE Memory Demo

This repository runs a KE-only memory pipeline over the fixed BEAM subset. The primary order is
strict: Elasticsearch health, exact index identity pinning, input and structured-model preflight,
ingestion, Turn KE extraction, source-ordered lifecycle reconciliation, Session aggregation,
Conversation-local semantic DAG construction, and `ke-ready` preparation. The ontology identity is
re-read before every stage promotion.

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

## State Layout

Canonical artifacts are stored under
`<state-root>/runs/<run-id>/<stage>/` and committed to the separate Git repository at
`<state-root>/.git`. Checkpoints and disposable Conversation-scoped SQLite indexes live under the
ignored `checkpoints/` and `cache/` paths. Snapshots contain only ontology documents actually bound
to KEs, never the complete Elasticsearch vocabulary.

Embedding and baseline systems are not part of the primary run. The formal path indexes and
retrieves only current KEs plus aggregate nodes while retaining every KE revision in canonical
history for audit.
