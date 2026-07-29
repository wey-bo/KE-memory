# Identity Candidate Generation Integration Assessment Design

## Objective

Assess how frozen model proposals can enter the existing identity workflow as
non-authoritative review candidates without changing identity decisions,
snapshots, membership state, L2 memory, or query behavior.

This phase consumes the already frozen public payload, proposal payload, and
independent score output. It does not invoke a proposer and does not read
authority or gold directly. Authority-derived gate results are accepted only
through the frozen score artifact after its hashes are verified against the
public and proposal inputs.

## Non-Negotiable Boundaries

- Work only in the H100 workspace.
- Do not rerun external memory systems or access old Fusion Memory material.
- Do not change the core ontology, dynamic ontology extension, L1/L2
  extraction, question processing, symbolic retrieval, or guarded embedding
  fallback.
- Embeddings are never fact, identity, or membership authority.
- No automatic merge, membership, `IdentityDecision`, snapshot, aggregate, or
  L2 write is authorized.
- `LONGMEMEVAL-6d550036` remains
  `structured_l2_identity_unresolved`.
- Raw proposer quality and deterministic gate safety remain separate upstream
  measurements. This assessment must preserve both fields and must not infer
  proposer quality from gate safety.

## Existing Contract

`build_identity_snapshot` reads only `IdentityDecision` records whose status is
`accepted`. The proposal gate returns `GatedIdentityDecision`, a separate
non-authoritative model. There is no current path from a proposal or gated
decision to an accepted identity decision.

The integration assessment preserves that separation:

```text
frozen public + frozen proposals + frozen score
                    |
                    v
       immutable candidate review queue
                    |
                    v
         read-only compatibility report
```

Neither output is an identity bundle input.

## Chosen Approach

Add an offline bridge that maps every scored case to an immutable candidate
envelope. Each envelope contains:

- content-derived candidate ID;
- proposal and gated actions, gate reason, and disposition;
- public mention/evidence references;
- provisional entity or membership references for human review;
- hashes of the public case, proposal, and gated decision;
- authoritative-pipeline compatibility gaps;
- explicit false claims for every automatic write capability.

Disposition is intentionally narrower than authority:

- `eligible_for_manual_review`: the gate accepted a non-abstain action and the
  frozen public/proposal/score bindings are structurally complete;
- `gate_abstained`: the deterministic gate emitted abstain;
- `review_required`: the input is structurally mapped but cannot satisfy the
  normal review envelope without manual repair.

Eligibility means only that a human can review the candidate. It never means
that an identity or membership write is materializable.

## Compatibility Assessment

The tool also receives one existing identity scenario as a read-only guard
bundle. It computes a canonical state fingerprint and guarded collection counts
before and after candidate construction. The assessment passes the mutation
guard only when both fingerprints and all counts are identical.

Candidate compatibility is checked against current authoritative requirements:

- referenced entities must already have `EntityRecord` bindings;
- evidence must bind to L1 units and source revisions;
- an identity decision would require a dedicated evidence closure;
- membership changes have no authorized automatic write surface;
- abstentions do not materialize an action.

Missing bindings are reported as gaps. The bridge does not synthesize accepted
entities, decisions, closures, memberships, snapshots, aggregates, or L2 units
to make a candidate appear compatible.

## Input Integrity

Before mapping candidates, the tool validates:

- public, proposal, and score schemas;
- exact dataset, run, proposer, case, relation, action, and evidence alignment;
- exact case coverage with no duplicates;
- score `input_sha256.public` and `input_sha256.proposals` against supplied
  files;
- score-level raw-quality and gate-safety fields without combining them;
- an upstream score status that passed both independent gates.

The assessment deliberately does not accept authority or gold paths. That keeps
the proposer/scorer chronology intact and prevents a new side channel.

## Outputs

The runner writes three immutable, read-only files:

- `candidate-review-queue.json`;
- `assessment.json`;
- `report.md`.

The assessment reports mapping coverage, evidence binding coverage, existing
entity binding coverage, abstentions, manual-review eligibility, blocked writes,
zero automatic writes, and the before/after mutation guard. It separately
copies upstream raw proposer readiness and deterministic gate readiness.

The overall assessment may pass while integration readiness remains false. A
pass means the measurement and safety boundary worked; it does not mean the
candidate can be written into the authoritative pipeline.

## Rejected Alternatives

### Direct `IdentityDecision` Injection

Rejected because proposal and gate outputs do not carry the closure, producer,
transaction, supersession, and evidence bindings required by authoritative
identity decisions. Creating candidate or accepted decisions would also make
the review queue part of the runtime state surface.

### Runtime Model Invocation

Rejected because it couples nondeterministic generation to authoritative query
execution and weakens the already frozen proposer/scorer boundary.

### Automatic Gate-Accepted Writes

Rejected because deterministic gate safety is a safety measurement, not a
storage authorization. It also cannot substitute for raw proposer quality or
manual review.

## Exit Condition

This phase is complete when the fresh-v4 frozen run deterministically produces
the review queue and assessment, replay is byte-identical, the mutation guard is
unchanged, automatic write count is zero, formal outputs are read-only, and the
full natural-memory test suite plus existing validators pass.

