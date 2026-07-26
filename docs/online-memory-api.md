# Online Ontology Memory API

## Runtime

The online service is an A+B memory vertical slice:

- A: active tasks, workflow state, constraints, tool observations, corrections, and conflicts;
- B: durable preferences, user-reported facts, plans, and cross-session warmup context.

Start it from the repository root:

```bash
uv sync --frozen
uv run ke-memory-serve
```

`config/online.toml` controls the host, port, SQLite path, runtime mode, and the fixed KEOL commit.
`production` requires the environment variables referenced by `config/models.toml` and
`config/es_vocab.toml`. `offline` performs no model or ontology network calls and intentionally
returns no extracted KEs.

The service compiles JSON that is contract-tested against KEOL commit
`44631e64fd07c9b85f22e36035bf49c882dba592`. It does not modify the shared KEOL checkout.

## Write A Turn

`POST /v1/memory/turns`

```json
{
  "namespace": {
    "tenant_id": "tenant-a",
    "user_id": "user-1",
    "agent_id": "assistant"
  },
  "conversation_id": "conversation-1",
  "idempotency_key": "conversation-1:turn-12",
  "exchange": {
    "id": "exchange-12",
    "session_id": "session-2",
    "user": {
      "id": "message-23",
      "role": "user",
      "content": "I prefer concise answers.",
      "source_order": 0,
      "source_metadata": {}
    },
    "assistant": {
      "id": "message-24",
      "role": "assistant",
      "content": "Understood.",
      "source_order": 1,
      "source_metadata": {}
    },
    "events": [],
    "global_ordinal": 12,
    "source_metadata": {}
  },
  "recorded_at": "2026-07-26T14:00:00+00:00"
}
```

The transaction preserves the exact raw records and extraction audit before exposing admitted
durable memories. Repeating the same namespace and idempotency key with the same turn returns the
previous receipt. Reusing the key for changed content returns HTTP 409.

Admission rules are explicit:

- user preferences and plans are durable when extraction confidence is sufficient;
- tool observations have high epistemic trust and are durable state;
- Agent-generated facts remain candidates until confirmed;
- questions and hypotheses are not durable memory;
- extraction confidence, epistemic trust, and memory utility are stored independently.

## Search

`POST /v1/memory/search`

```json
{
  "namespace": {
    "tenant_id": "tenant-a",
    "user_id": "user-1",
    "agent_id": "assistant"
  },
  "query": {
    "text": "What response style does the user prefer?",
    "operator_terms": ["operator:prefers"],
    "entity_terms": ["individual:user"],
    "memory_kinds": ["preference"],
    "unresolved_slots": [],
    "limit": 10
  }
}
```

Symbolic execution is authoritative for namespace, current revision, tombstones, lifecycle,
modality, memory kind, valid time, entity IDs, operator IDs, and conflict visibility. A complete
symbolic result never invokes embeddings.

Dense fallback is allowed only when `unresolved_slots` contains `entity` or `predicate`. It ranks
only candidates that already passed authoritative symbolic filters. It cannot override time,
lifecycle, namespace, memory kind, modality, polarity, source status, or conflicts. When
`embedding.enabled = false`, unresolved lexical queries return without dense fallback.

## Warmup Context

`POST /v1/memory/context`

```json
{
  "namespace": {
    "tenant_id": "tenant-a",
    "user_id": "user-1",
    "agent_id": "assistant"
  },
  "limit_per_section": 10
}
```

The response groups active tasks, constraints, preferences, recent tool/state observations, and
conflicts. Every returned item contains its exact Evidence closure. Records without evidence are
not placed into warmup context.

## Correction

`POST /v1/memory/corrections`

The request supplies the target `memory_id`, a complete replacement `KnowledgeEquation`, the exact
source messages referenced by its spans, and `recorded_at`. The replacement must pass the same
admission gate. The repository appends the replacement, appends a superseded revision for the old
memory, links the two with `supersedes`, and commits the operation atomically.

## Get And Forget

Get a current memory:

```text
GET /v1/memory/{memory_id}?tenant_id=tenant-a&user_id=user-1&agent_id=assistant
```

Forget a current memory:

```text
DELETE /v1/memory/{memory_id}?tenant_id=tenant-a&user_id=user-1&agent_id=assistant&recorded_at=2026-07-26T14:10:00Z
```

Forgetting does not delete history. It appends a `retracted` revision, tombstones the current head,
and removes the record from normal search and context. Audit data remains in SQLite.

## Storage And Verification

The SQLite database uses WAL mode and foreign keys. A turn write commits raw records, extraction
assessments, KEOL bundle revisions, evidence, lifecycle transitions, and links in one transaction.
The test suite verifies forced mid-transaction failure leaves no partial turn or memory package.

Useful checks:

```bash
uv run pytest tests/unit/online tests/integration/test_online_memory_api.py -q
uv run ruff check src tests
uv run pyright
```

The service is an implementation, not evidence that ontology memory is universally superior.
The justified claim remains narrower: symbolic KE execution has a strong expected advantage on
constraint-heavy, temporal, provenance-sensitive, and correction-sensitive tasks. Promotion claims
still require a fresh hidden evaluation and A+B user-experience comparison.
