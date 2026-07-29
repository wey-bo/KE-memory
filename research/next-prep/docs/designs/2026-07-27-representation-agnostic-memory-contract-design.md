# Representation-Agnostic Memory Contract Design

Status: approved direction and implementation-ready after the user's clarification that KE, AMR, or another graph language may be used for extraction and persistence.

## Decision

No concrete representation language is the architecture-level source of truth.

KE is treated as one representation language and KEOL as one possible adapter/runtime. Standard AMR, extended AMR, a property graph, or another structured format may also be used. A format is acceptable only if it preserves and executes the required memory semantics.

The architecture therefore has four distinct layers:

```text
raw source ledger
  -> logical memory contract
  -> one or more physical representations
  -> representation-independent query and evidence conformance tests
```

The raw source ledger remains authoritative for recovery. The logical contract is normative for behavior, but it is not required to be the physical database schema. Physical representations must export a lossless conformance bundle and reproduce the required query/evidence behavior.

## Why the requirement is above KE

`Assertion(A, B)` is useful, but it does not by itself guarantee:

- predicate sense and event-role structure;
- speaker and source epistemic status;
- event, valid, and transaction time;
- conflicts, supersession, and lifecycle;
- L2 abstraction provenance;
- evidence closure and answerability;
- guarded fallback boundaries;
- lossless versioned round-trip.

The same is true of standard AMR. It provides strong sentence-level predicate-argument structure, but long-term memory requires additional identity, provenance, lifecycle, temporal, and closure semantics.

The selection question is therefore not "KE or AMR?" It is "which representation and extensions satisfy the complete memory contract with the best extraction quality, execution correctness, efficiency, and operational cost?"

## Hard capabilities

Every authoritative candidate must pass all of these gates:

1. `stable_identity`: memory units, entities, evidence, closures, and derived units have stable versioned IDs.
2. `raw_source_revision_binding`: evidence spans are verified against an immutable raw-source revision and content hash.
3. `event_role_semantics`: predicate sense and typed role bindings survive storage and retrieval.
4. `evidence_traceability`: every active L1 unit and every active L2 abstraction reaches raw evidence spans.
5. `source_epistemics`: speaker, source status, extraction confidence, epistemic trust, modality, and polarity are preserved.
6. `temporal_semantics`: event time, valid time, and transaction time are distinguishable.
7. `lifecycle_and_revision`: active, candidate, superseded, conflicted, and forgotten states plus immutable record revisions are preserved.
8. `cross_layer_provenance`: L2 abstractions point to L1 units, turns, sessions, and closure records.
9. `structured_l2_semantics`: L2 claims remain typed and executable rather than existing only as summary or display strings.
10. `evidence_closure`: single-fact, multi-evidence, temporal, update, and causal answerability closures are executable.
11. `closure_evaluation_versioning`: closure specs and evaluations record policy/input revisions and become stale when dependencies change.
12. `constraint_execution`: explicit roles, time, negation, modality, source status, and conflicts constrain results.
13. `versioned_round_trip`: encode/decode preserves the logical bundle without semantic loss.
14. `guarded_fallback`: embedding may recover allowed lexical/entity/evidence candidates but cannot override structural constraints or closure.

A format that misses any hard capability is `partial` or `projection_only`, not an authoritative memory representation.

## Support modes

Each capability is classified as:

- `native`: represented directly by the format/runtime;
- `extension`: represented by a defined extension that participates in validation and query execution;
- `sidecar`: preserved externally and joined by stable IDs;
- `unsupported`: absent or not executable.

`extension` and `sidecar` are acceptable only when lossless round-trip and reference integrity are tested. Metadata that is merely written but never validated or queried does not count as support.

## Reference conformance bundle

The current `semantic_ir.py` models are retained as a reference carrier for tests. They are not declared to be the final storage schema. A conformance bundle groups:

- representation profile and version;
- L1 units;
- L2 units;
- closure records;
- query plans used as semantic probes;
- source and run metadata.

The bundle validator must reject:

- duplicate unit or closure IDs;
- broken L1/L2/closure/query references;
- active L2 units with incomplete supporting closure;
- L2 turn/session provenance that does not match its L1 evidence;
- conflicting duplicate evidence definitions;
- lifecycle links to missing memory units;
- physical representations that cannot round-trip the bundle.

## Candidate representation roles

### Reference Semantic IR JSON

Role: conformance carrier and deterministic test oracle.

It can pass the logical contract if it validates references, round-trips exactly, and reproduces query results. Passing does not make it the selected production database.

### KEOL

Role: optional ontology/assertion adapter and candidate runtime.

The current projection stores several memory semantics in assertion metadata. Until native Pydantic validation, reference validation, reverse decoding, and query execution are demonstrated, it remains `projection_only` rather than the required persistence layer.

### Standard AMR

Role: sentence-level semantic parser or local graph representation.

Standard AMR is expected to be partial because it lacks several memory-specific capabilities. This is a hypothesis to test, not a reason to reject AMR-style extraction.

### Extended AMR

Role: next candidate adapter.

An extended AMR representation may add stable node IDs, evidence anchors, temporal/source/lifecycle annotations, cross-graph links, closure records, and L2 provenance. It must pass the same round-trip and query probes as every other candidate.

## Selection experiment

Representation selection uses hard gates first and soft metrics second.

Hard gates:

- zero broken evidence or provenance references;
- exact logical round-trip;
- exact semantic query result equivalence on the conformance probes;
- zero critical false positives;
- zero structural-family embedding fallback;
- correct abstention when closure is incomplete.

Soft metrics, compared only among hard-gate passers:

- model extraction accuracy by capability family;
- extraction latency and token cost;
- write and query latency;
- storage size and index cost;
- migration/versioning complexity;
- debugging and human-audit cost.

## Immediate implementation boundary

This wave implements the representation contract and conformance harness. It evaluates the native Semantic IR carrier and the current KEOL projection status. It does not select a final database, implement model extraction, or claim that AMR or KEOL is superior.

The next candidate implementation after this wave is an extended-AMR adapter over the same small probe bundle. Only after at least two candidates pass the same hard gates should efficiency decide the physical representation direction.

## Authoritative v3/v5 implementation status

The authoritative v3 bundle and the `extended-amr-memory-graph-v2` adapter now carry the same typed contract. The immutable v5 run `run-authoritative-conformance-v5` validates 13 replayed source records, 6/6 fresh closure evaluations, 6/6 recomputation-result parity checks, and 5/5 frozen correctness probes. The five independent expectations have canonical SHA-256 `cfebd096c369c4a982e9db0b09cb4b32a98cb165853f005cf52fe049a45d8659` and include matched claim identity. Stale/incomplete active-L2 mutations must be rejected, and correctness/capability gates are recomputed for each decoded carrier. Both carriers round-trip exactly and preserve 5/5 scoped query results.

This is not a storage-selection pass. The LongMemEval count probe retains four evidence candidates but abstains with `structured_l2_identity_unresolved` because project identity/deduplication is unresolved. That frozen correctness result keeps both carriers at `authoritative_ready=false`; display text cannot override it. Native v3 and Extended-AMR v2 are therefore validated carriers of the same contract, while KEOL remains an optional projection track and the final physical representation remains undecided.

The v5 result establishes contract, source, evidence-closure, query-parity, and correctness-gate behavior only. It does not establish model extraction quality, full benchmark performance, product value, or superiority over AMR, KEOL, vector memory, or external memory systems. Guarded embedding fallback remains subordinate to authoritative symbolic filtering and cannot supply facts or override unresolved structural constraints.

## Identity-contract follow-up

The next wave adds representation-neutral identity and aggregate records without changing the authoritative v3/v5 bundle or its frozen LongMemEval behavior. The logical extension includes a local concept registry, provisional/canonical entity records, immutable `merge`/`keep_distinct`/`reject_merge`/`split`/`abstain` decisions, scoped identity-evidence closures, deterministic identity snapshots, and evidence-complete aggregate claims. A `count_distinct` result is authoritative only when every counted L1 role binding is in the aggregate member set, every member resolves under a fresh snapshot, and the recomputed count and evidence set match the stored claim.

Schema.org 30.0 is frozen from official repository commit `f72e60b7f67578b4af9445fa20fc8ec3fe1c9b93` as an advisory concept source. External mappings record relation and version, but do not override local evidence or policy. In particular, local `memory:Project` maps to `schema:Project` as `related`, not `exact`, and `schema:sameAs` is not permission to merge local memory entities.

Native identity-aware v4 and `extended-amr-memory-graph-v3` carry the same identity records. The formal hand-authored diagnostic run `run-20260727T080000Z-identity-v1` passes with zero critical false merges; exact answerable counts, evidence sets, abstentions, revision handling, and closure freshness; zero structural fallback; and exact native/Extended-AMR round-trip and query parity. Results/report SHA-256 are `e7cc632ae20f6436156fcd9c777352eac0f8286e63cb24f42ddee05875ae633c` and `bc032cf6a5590a8d1f12adf5d523af9da65d599b66ceddac52667d213b920ae8`.

This pass sets `identity_authoritative_ready=true` only for the frozen identity-contract diagnostic. It does not resolve the real LongMemEval project identities: the v5 case must still abstain with `structured_l2_identity_unresolved`, retaining all four evidence candidates. The next evidence requirement is a larger pre-registered natural identity/membership slice and measurement of model-proposed candidate false-merge and abstention quality. Final physical storage remains undecided.
