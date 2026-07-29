# AMR-style Ontology Extension Note

Status: design note for the next representation/compiler stage. Not implemented in the current natural benchmark slice runs.

## Decision

Use AMR as one candidate semantic representation family. Standard AMR is expected to be partial, while a contract-enriched AMR graph may serve as an intermediate form, an exchange form, or a physical persistence profile if it passes the representation conformance gates.

No final memory database or representation language is selected by this note. KEOL is an optional ontology/assertion adapter, not a mandatory backend.

The current evidence says shallow symbolic matching is better than dense-only retrieval on role binding and over-recall, but it is still too weak for causal answerability, contradiction/update closure, temporal reasoning, and exact multi-evidence boundaries. A stronger ontology layer should therefore preserve AMR's predicate-argument structure while adding memory-specific fields that standard AMR does not carry.

## Why standard AMR is insufficient

Standard AMR is mainly a sentence-level semantic graph. The memory system needs additional dimensions:

- source turn, speaker, and role provenance;
- confidence, extraction status, and epistemic status;
- temporal validity and update/supersession;
- contradiction and conflict links;
- multi-turn evidence closure;
- task/session lifecycle;
- answerability gates and abstention;
- stable export/import through the selected representation profile and any optional adapters.

Therefore, raw standard PENMAN is insufficient as the authority. An extended AMR profile remains viable if the additional memory semantics are validated, queryable, and losslessly round-trippable.

## Proposed extended representation

Core node types:

- `Entity`: person, organization, object, product, place, abstract item.
- `Event`: action or occurrence with AMR-like predicate roles.
- `State`: durable or temporary status.
- `Attribute`: property/value pair.
- `TimeAnchor`: explicit date, relative time, order, interval, recency.
- `EvidenceSpan`: raw text span with source unit ID.
- `SpeakerRole`: user, assistant, tool, simulator, named speaker.
- `EpistemicStatus`: user-reported, agent-generated, tool-observed, inferred, contradicted.
- `MemoryLifecycle`: active, superseded, forgotten, candidate, conflict.
- `Task`: cross-turn or cross-session high-level unit.

Core edge types:

- AMR-like: `ARG0`, `ARG1`, `ARG2`, `mod`, `name`, `location`, `time`, `manner`, `cause`, `purpose`, `condition`, `concession`.
- Memory-specific: `source_span`, `spoken_by`, `valid_during`, `supersedes`, `conflicts_with`, `supports`, `derived_from`, `same_as`, `normalized_to`, `requires_evidence`, `answerable_by`.

## Compiler path

```text
raw turn
  -> AMR-style semantic IR
  -> grounding and normalization
  -> representation-neutral memory contract
  -> selected persistence profile and optional adapters
  -> query slot plan
  -> graph/constraint execution
  -> slot completeness check
  -> guarded embedding fallback
  -> evidence-based answer
```

The IR may compile into KEOL-compatible assertions, an extended AMR graph, a typed property graph, or another selected profile. Every adapter must report projection loss and pass evidence, closure, lifecycle, and round-trip checks. KEOL is currently implemented only as an optional projection track.

## Immediate use in the current benchmark work

The next implementation should not attempt a full AMR parser. It should add the missing compiler categories exposed by slice-v1:

1. `answerability`: distinguish "evidence mentions X" from "evidence answers causal/how question about X".
2. `causal_relation`: model whether an event actually caused or influenced another event.
3. `temporal_order`: represent before/after/first/latest without letting dense retrieval decide.
4. `speaker_role_binding`: promote LoCoMo speaker binding from a rule into typed provenance.
5. `update_conflict`: distinguish current, old, contradicted, and superseded statements.
6. `evidence_closure`: represent why multiple evidence units are jointly required.

## Evaluation gates

An AMR-style extension is useful only if it improves the existing gates:

- lower critical false positives on abstention/causal/temporal/update items;
- higher complete evidence sets without increasing over-return;
- no fallback on temporal, negation, modality, or conflict failures;
- every generated assertion remains traceable to raw source IDs;
- no claim of superiority over external memory systems without matched reruns.

## 2026-07-26 slice-v1 update

The answerability v2 run confirms the first concrete use case for this IR: causal answerability cannot be solved safely by token overlap or dense retrieval alone. The system needed a gate that distinguishes "evidence mentions feedback and UI/UX" from "evidence states how feedback caused a concrete UI/UX change."

The same run also exposed a predicate-sense issue: `led` in "How many projects have I led..." must not be treated as causal `led to`. An AMR-style extended representation should therefore preserve predicate sense and typed roles before compiling into the selected profile or optional KEOL projection.

Current report: `artifacts/natural-benchmark-slices/slice-v1/symbolic-fallback-answerability-v2-fastembed-report.md`.

Follow-up representation design: `docs/designs/2026-07-27-event-role-evidence-closure-representation-design.md`.

## Current constraint

This note does not select a persistence schema. The current architecture-level requirement is the representation-agnostic contract in `docs/designs/2026-07-27-representation-agnostic-memory-contract-design.md`.
