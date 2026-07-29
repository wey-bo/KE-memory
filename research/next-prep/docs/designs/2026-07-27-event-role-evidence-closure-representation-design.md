# Event-Role-Evidence Closure Representation Design

Status: proposed design for the next representation/compiler stage after slice-v1 answerability v2.

## Objective

Define a minimal event-role-evidence closure representation for an ontology-first memory system. The representation must support two user-visible modeling layers:

1. `L1`: atomic extraction and storage for a single turn, sentence, or local text unit.
2. `L2`: cross-turn and cross-session abstraction after summary or aggregation.

This design defines logical memory semantics, not a fixed persistence language. AMR-style graphs, KEOL assertions, typed property graphs, or other formats may act as physical profiles if they pass the same evidence, lifecycle, closure, constraint-execution, and round-trip gates.

## Design judgment

The two-layer plan is suitable, but only if there is an explicit middle layer between L1 and L2:

```text
raw turn / sentence
  -> L1 atomic event-role graph
  -> linking / normalization / lifecycle / closure
  -> L2 cross-turn abstraction graph
  -> query slot plan
  -> symbolic graph execution
  -> slot completeness and answerability gate
  -> guarded embedding fallback
  -> evidence-based answer
```

Without the middle layer, L2 summaries will become lossy generated text. That would recreate the same failure mode as vector-plus-pseudo-ontology memory: plausible abstraction with weak evidence binding.

## Scope boundaries

In scope:

- event, state, preference, task, and attribute memory units;
- AMR-style predicate-argument roles;
- source provenance and evidence closure;
- speaker/source status, epistemic status, modality, polarity, temporal validity, conflict, supersession, and lifecycle;
- query-time answerability and evidence completeness checks;
- embedding fallback only for unresolved lexical/entity/evidence candidate gaps.

Out of scope for this design:

- treating unextended standard AMR/PENMAN as authoritative storage without passing the shared contract;
- full OWL/DL reasoning;
- rerunning Mem0, Graphiti, Hindsight, MemPalace, Zep, or other external memory systems;
- product superiority claims from slice-v1.

## Alternatives considered

### A. Standard AMR as database

Rejected. Standard AMR captures useful sentence-level predicate-argument structure, but lacks stable identity, provenance, speaker/source status, temporal validity, conflict/supersession, lifecycle, and evidence closure.

### B. KEOL-only assertions without AMR-style IR

Viable but too brittle for the current failures. Direct assertions can represent facts, but extraction/query compilation has trouble distinguishing predicate senses such as `lead/manage` vs `lead-to/cause`, and relation completeness such as "mentions feedback" vs "answers how feedback caused a change."

### C. Representation-neutral contract with pluggable profiles

Recommended. It uses AMR-like event roles where they help, adds memory-specific fields, and evaluates KEOL, extended AMR, or another typed representation as interchangeable profiles rather than preselecting a backend.

## L1: atomic event-role layer

L1 is the local extraction layer. Its unit is one sentence, clause, or single user-agent turn segment. It should be small enough to preserve source evidence accurately.

Minimum L1 record:

```json
{
  "unit_id": "l1_evt_...",
  "level": "L1",
  "kind": "event|state|preference|task|attribute",
  "predicate": {
    "surface": "led",
    "sense": "lead/manage",
    "canonical_operator": "managed_by|led_by|caused_by|prefers|status_of"
  },
  "roles": [
    {"role": "ARG0", "entity_id": "user", "role_name": "agent"},
    {"role": "ARG1", "entity_id": "project_x", "role_name": "theme"}
  ],
  "modality": "actual|planned|hypothetical|requested|recommended|denied",
  "polarity": "positive|negative",
  "time": {
    "event_time": null,
    "valid_time": null,
    "transaction_time": "extraction time"
  },
  "source": {
    "turn_id": "...",
    "session_id": "...",
    "speaker": "user|assistant|tool|simulator|named_speaker",
    "source_status": "user_reported|agent_generated|tool_observed|inferred",
    "evidence_spans": [{"evidence_id": "...", "char_start": 0, "char_end": 0}]
  },
  "epistemic": {
    "extraction_confidence": 0.0,
    "epistemic_trust": "high|medium|low",
    "memory_utility": "candidate|useful|low"
  },
  "links": {
    "same_as": [],
    "supersedes": [],
    "conflicts_with": [],
    "derived_from": []
  }
}
```

L1 must not silently merge across turns. If a later turn updates or contradicts an earlier turn, that is represented by lifecycle links, not by overwriting the old record.

## Middle layer: linking, normalization, lifecycle, and closure

The middle layer is the critical part of the design. It is not a user-visible memory level, but it prevents L1 and L2 from drifting apart.

Responsibilities:

- `entity_linking`: map mentions to stable entities, including aliases and speaker-bound entities.
- `predicate_sense`: distinguish operator senses, e.g. `lead/manage` vs `lead-to/cause`.
- `operator_normalization`: map predicates to stable canonical predicate identities; a KEOL adapter may separately map them to `Operator` IDs.
- `event_identity`: decide whether two events are same, related, or distinct.
- `temporal_normalization`: distinguish event time, valid time, and transaction/extraction time.
- `lifecycle`: active, superseded, conflicted, forgotten, candidate.
- `closure`: define which lower-level units are required for a higher-level claim or answer.
- `admission`: decide whether a record can become active memory or must remain candidate/review.

This layer is where current slice-v1 failures should be fixed. For example, `BEAM-100K-C001-abstention-001` should fail because its evidence mentions feedback and UI/UX, but closure cannot prove a causal relation from feedback observation to concrete change.

## Evidence closure

Evidence closure means the system knows what evidence set is required to support a memory claim or answer. It is stronger than returning any relevant evidence.

Closure record:

```json
{
  "closure_id": "closure_...",
  "claim_or_query_id": "...",
  "required_units": [
    {"unit_id": "l1_evt_a", "role": "cause"},
    {"unit_id": "l1_evt_b", "role": "effect"},
    {"unit_id": "l1_evt_c", "role": "temporal_anchor"}
  ],
  "optional_units": [],
  "missing_slots": [],
  "complete": true,
  "reason": "causal answer requires cause, effect, and linking relation"
}
```

Closure should support at least five patterns:

1. `single_fact`: one evidence unit fully supports the claim.
2. `multi_evidence_set`: all listed units are required.
3. `temporal_chain`: before/after/latest/current needs ordered evidence.
4. `update_supersession`: old and new facts plus update relation.
5. `causal_answerability`: cause/event observation, effect/change, and explicit causal link.

If `complete=false`, symbolic execution should abstain or call a guarded fallback only for missing lexical/evidence candidates. Dense retrieval must not override a structural missing slot.

## L2: cross-turn and cross-session abstraction layer

L2 records are derived abstractions. They are not raw facts unless every assertion points back to L1 and raw evidence.

Minimum L2 record:

```json
{
  "unit_id": "l2_task_...",
  "level": "L2",
  "kind": "task|preference_profile|project|habit|long_running_state|summary_event",
  "abstracts": ["l1_evt_1", "l1_evt_2"],
  "summary": "User is working on security hardening before public launch.",
  "assertions": ["ke_assertion_..."],
  "closure_id": "closure_...",
  "lifecycle": "active|superseded|conflicted|candidate",
  "valid_time": null,
  "abstraction_method": {
    "method": "summary_then_extract|cluster_then_extract|rule_aggregate",
    "model_or_rule_version": "...",
    "prompt_sha256": null
  },
  "provenance": {
    "source_l1_units": [],
    "source_turns": [],
    "source_sessions": []
  }
}
```

L2 should be allowed to introduce higher-level concepts such as `Task`, `Preference`, or `Project`, but every L2 record must expose its support chain:

```text
L2 abstraction -> closure -> L1 events/states -> EvidenceSpan -> raw turn
```

If that chain is broken, the L2 record is not admissible as active memory.

## Query execution

Natural-language queries should compile into a slot plan before retrieval:

```json
{
  "query_id": "...",
  "intent": "fact_lookup|multi_evidence|causal_how|temporal_latest|preference_current|task_status",
  "target_level": "L1|L2|both",
  "slots": {
    "entity": [],
    "predicate": [],
    "role_constraints": [],
    "time_constraints": [],
    "source_status_constraints": [],
    "required_closure_pattern": "causal_answerability"
  },
  "fallback_policy": {
    "allowed": ["unresolved_entity", "lexical_predicate_missing_link", "incomplete_evidence_slot"],
    "blocked": ["temporal_missing", "conflict_unresolved", "modality_mismatch", "answerability_missing"]
  }
}
```

Execution order:

1. compile query to slot plan;
2. link query entities and predicate senses;
3. execute symbolic graph constraints over L1/L2;
4. check closure completeness;
5. trigger embedding fallback only for permitted missing-link cases;
6. return answer evidence package, or abstain with missing-slot reason.

## Optional KEOL compatibility projection

The optional KEOL adapter projects the logical records into KEOL-compatible objects:

- `Entity`, `Event`, `State`, `Task`, `Preference` become `Individual` with Concept membership.
- `predicate.canonical_operator` becomes KEOL `Operator`.
- Role edges become `OperatorApplication` assertions where possible.
- `EvidenceSpan` becomes KEOL `Evidence`.
- `closure_id`, `source_status`, `valid_time`, `transaction_time`, `supersedes`, and `conflicts_with` live in assertion metadata or compatible extension fields until KEOL supports them directly.

The display string is not the source of truth. Raw text, evidence-backed semantic records, immutable provenance, and validated reference closure form the authoritative recovery chain. A KEOL JSON projection is one materialized view of that chain.

## Failure modes and controls

| Failure mode | Control |
| --- | --- |
| L2 summary invents facts | Require `derived_from`, closure, and raw evidence spans |
| AMR predicate too generic | Add predicate sense and canonical operator normalization |
| Dense retrieves topical but unanswerable evidence | Closure and answerability gate block result |
| Old preference overrides new preference | Lifecycle and valid-time/supersession execution |
| Multi-session answer returns partial evidence | `multi_evidence_set` closure requires all slots |
| Agent-generated advice treated as real fact | `source_status` and epistemic trust constraints |
| Standard AMR lacks memory semantics | Require the same memory contract from an extended AMR or another profile |

## Minimal implementation sequence

1. Define Pydantic/data contracts for L1 unit, L2 unit, closure, and query slot plan.
2. Build a small hand-authored diagnostic set from slice-v1 failure classes.
3. Implement deterministic symbolic execution over hand-authored IR.
4. Add compiler fixtures for:
   - `led/manage` vs `led-to/cause`;
   - feedback causal answerability;
   - multi-session evidence closure;
   - current preference after update;
   - task lifecycle status.
5. Compare against current `symbolic_fallback_answerability_v2` on the same slice items.
6. Only then consider model-based extraction into this IR.

## Evaluation gates

A first implementation can move forward only if it satisfies:

- every active L1/L2 record has raw evidence traceability;
- all L2 abstractions have complete `derived_from` chains;
- critical false positives remain 0 on slice-v1 abstention/causal items;
- fallback trigger rate on structural families remains 0;
- multi-evidence closure improves complete evidence set without reducing precision;
- no answer is generated without complete closure unless explicitly marked partial/uncertain.

## Open questions

1. Should L1 extraction store sentence-level units only, or turn-level grouped units with sentence spans?
2. Should L2 abstraction be created on every session close, only on query demand, or via periodic consolidation?
3. For each candidate profile, which capabilities are native, validated extensions, sidecars, or unsupported, and what projection loss remains?
4. How strict should admission be for agent-generated content?
5. Should answer generation be delayed until closure execution is stable, or implemented with a strict evidence-only judge in parallel?

## Current conclusion

The user's two-layer plan is suitable if the middle layer is explicit and testable. The next implementation should not expand natural benchmarks yet. It should first prove the shared contract on a small diagnostic set, then compare at least two physical profiles without assuming KEOL, AMR, or another format is the winner.

## Authoritative contract follow-up

The v3/v5 follow-up now makes the shared event-role-evidence contract authoritative independently of its carrier. Raw artifact/source revisions, exact evidence spans, immutable L1/L2 unit revisions, structured L2 claims, claim/query closure contexts, and closure-evaluation freshness are represented explicitly. Native v3 and Extended-AMR v2 both preserve this bundle through exact round-trip and reproduce the same five scoped query results. The five correctness expectations are independently frozen, include matched claim identity, and are combined with stale/incomplete active-L2 rejection rather than relying on positive round-trip parity alone.

The LongMemEval project-count case confirms why the middle identity/normalization layer is mandatory: four L1 lead/manage events still refer to four provisional project identities, while the human-facing display assertion says count=2. The authoritative result keeps all four evidence candidates and abstains with `structured_l2_identity_unresolved`. Correct identity resolution, deduplication, and aggregate construction remain upstream requirements; serialization parity cannot replace them.

No final persistence format has been selected. The current evidence verifies representation conformance, source/evidence closure, query consistency, and frozen correctness behavior. It does not prove AMR, KEOL, ontology memory, or this project superior to mainstream memory systems, and embedding fallback remains a guarded candidate-recovery mechanism rather than factual authority.

## Identity and concept-modeling follow-up

The middle layer now has an explicit identity contract rather than an implicit entity-linking step. It stores provisional and canonical entities, immutable identity decisions, decision-scoped evidence closure, correction/split supersession, and deterministic snapshots. L2 aggregate construction may consume this layer only through a fresh snapshot and an exact member/evidence closure; unresolved members force abstention instead of an estimated count.

Schema.org 30.0 is used as an advisory vocabulary for concept and property modeling. `Person`, `Organization`, `Project`, `Action`, `Event`, `Role`, `agent`, `object`, `result`, `startDate`, `endDate`, `identifier`, and `sameAs` provide useful comparison points, but all adopted mappings remain local, versioned, and executable. The broader local `memory:Project` concept is only `related` to `schema:Project`, and `schema:sameAs` cannot authorize a local identity merge.

Extended-AMR v3 is the principal carrier for this wave because standard AMR alone omits stable cross-session identity, immutable revision history, evidence closure, lifecycle, and aggregate authorization. The extension encodes concept, entity, decision, snapshot, aggregate, evidence, and supersession records explicitly while retaining AMR-style event-role structure. Its authority comes from passing the representation-neutral gate, not from AMR syntax.

The frozen `run-20260727T080000Z-identity-v1` hand-authored diagnostic passes all identity gates, including zero critical false merges and exact native/Extended-AMR query parity. This does not change the real LongMemEval project-count case: without independent evidence-backed membership and identity decisions, it must continue to return `structured_l2_identity_unresolved`. The next implementation wave should evaluate model-proposed identity candidates on a larger natural identity/membership slice before any automatic merge path is admitted.
