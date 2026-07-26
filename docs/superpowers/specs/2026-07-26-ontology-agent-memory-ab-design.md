# Ontology Agent Memory A+B Design

Date: 2026-07-26

Status: approved direction, implementation target

Target: `/public/home/wwb/KE_mem/ke-memory-demo/.worktrees/ontology-agent-memory-ab`

## 1. Goal

Build an online ontology-led memory module that serves both task agents (A) and personal
long-term assistants (B). The module must preserve raw turns, compile admitted memories into
KEOL-compatible ontology bundles, maintain updates and conflicts, and return evidence-backed
context through an HTTP API.

The product claim is deliberately narrow: outperform vector-first memory on constraint-heavy,
temporal, provenance-sensitive, and correction-sensitive workflows while retaining semantic
recall through guarded embedding fallback.

## 2. Architectural Decision

The system uses two planes:

1. The canonical plane is an append-only event and KE store. Raw messages and tool events are
   immutable. Every admitted memory is stored as a closed KEOL bundle containing the referenced
   Concept, Individual, Operator, Assertion, Evidence, and WorkflowRun records.
2. The derived plane contains searchable projections. Symbolic indexes are authoritative for
   identity, lifecycle, time, polarity, modality, task state, preferences, and constraints.
   Embeddings are consulted only when an entity or predicate slot remains unresolved.

SQLite in WAL mode is the first authoritative backend because this deployment is a single H100
host and must be runnable immediately. Repository boundaries must not expose SQLite-specific
types so PostgreSQL can replace it without changing the service contract.

## 3. Online Data Model

Every request is scoped by `tenant_id`, `user_id`, and `agent_id`. A turn also carries
`conversation_id`, `session_id`, and a caller-supplied idempotency key.

An online memory record contains:

- the original `KnowledgeEquation` extraction projection;
- a validated KEOL bundle and the canonical KEOL Assertion ID;
- `memory_kind`: task, goal, state, constraint, preference, profile, fact, event, procedure,
  or other;
- `source_status`: user_reported, agent_generated, tool_observed, or derived;
- separate extraction confidence, epistemic trust, and memory utility values;
- admission state and an explicit list of admission reasons;
- valid time and transaction time;
- lifecycle state plus supersedes, conflicts, and derived-from links;
- exact message spans and raw evidence hashes.

Agent-generated text is never promoted to a real-world fact by default. Tool observations receive
high epistemic trust. User statements may be durable preferences, plans, constraints, or reported
facts, but their source status remains visible.

## 4. Write Path

`POST /v1/memory/turns` performs one atomic transaction:

1. validate namespace, ordering, hashes, and idempotency;
2. preserve the raw user/assistant/tool records;
3. run the existing two-stage Turn KE extractor;
4. classify each KE for A+B memory kind and admission;
5. deterministically compile each admitted KE into a KEOL bundle;
6. reconcile current records conservatively as confirm, correct, supersede, conflict, or add;
7. commit raw events, memories, evidence, links, and the transaction log together;
8. enqueue or synchronously update derived search projections.

Failure before commit leaves no partial turn or KE package. Repeating the same idempotency key
with the same payload returns the prior result; a different payload is rejected.

## 5. Read Path

`POST /v1/memory/search` compiles a structured query and executes:

1. namespace and lifecycle filtering;
2. canonical entity/operator matching;
3. polarity, modality, time, task, preference, and constraint execution;
4. slot-completeness analysis;
5. guarded embedding fallback only for declared unresolved lexical slots;
6. evidence packing under a token budget.

`POST /v1/memory/context` returns a warmup package containing active tasks, current constraints,
durable preferences, recent state changes, unresolved conflicts, and exact supporting evidence.
It never returns an aggregate summary without its evidence closure.

## 6. User Control

The API provides explicit correction and forgetting:

- correction appends a replacement record and supersedes the selected current memory;
- forgetting creates a tombstone transaction and excludes the record from normal retrieval;
- historical/audit queries can still inspect prior revisions when authorized;
- no endpoint silently edits raw turns.

These controls are part of the A+B user experience contract, not administrative afterthoughts.

## 7. Service Surface

The first service exposes:

- `GET /healthz`
- `POST /v1/memory/turns`
- `POST /v1/memory/search`
- `POST /v1/memory/context`
- `POST /v1/memory/corrections`
- `DELETE /v1/memory/{memory_id}`
- `GET /v1/memory/{memory_id}`

The runtime has an explicit offline mode for deterministic tests. Production extraction requires
the configured structured model and ontology resolver; missing dependencies fail startup or the
specific operation instead of silently switching to heuristic extraction.

## 8. Verification Boundary

The implementation is accepted when:

- a preference survives across sessions with evidence;
- a task state update supersedes the old current state without deleting history;
- a tool observation and an agent suggestion receive different epistemic status;
- an atomic write rollback leaves neither the turn nor its KE records;
- exact symbolic results do not trigger embedding;
- unresolved lexical queries can trigger guarded fallback without structural-family fallback;
- correction and forgetting immediately affect normal retrieval;
- all existing 728 tests remain green and the new API integration suite passes.

The exposed v3 post-hoc hidden pass is only a regression signal. Product claims still require a
fresh v4 hidden set plus A+B task and user-experience evaluation.
