# Identity Candidate Generation Integration Assessment Implementation Plan

> **For agentic workers:** Execute with TDD and preserve all frozen identity
> proposal artifacts.

**Goal:** Convert frozen proposal and score artifacts into a non-authoritative,
immutable candidate review queue and measure compatibility with the existing
identity pipeline while proving zero authoritative mutation.

**Architecture:** Add a benchmark-only assessment module and CLI. The module
reads frozen public/proposal/score artifacts, builds review envelopes, compares
them with a read-only identity guard bundle, and writes a queue, assessment, and
report. It does not modify `identity_resolution.py` or construct
`IdentityDecision` records.

**Tech Stack:** Python 3.13, Pydantic 2.10.3, pytest 8.3.4, canonical JSON,
SHA-256, existing immutable writers and identity scenario builder.

## Global Constraints

- H100 only; no external-system reruns or old Fusion Memory access.
- No proposer invocation and no direct authority/gold input in this phase.
- No automatic merge, membership, decision, closure, snapshot, aggregate, or
  L2 writes.
- Embedding remains non-authoritative.
- Raw proposer quality and deterministic gate safety remain separately visible.
- `LONGMEMEVAL-6d550036` remains unresolved.

---

### Task 1: Define Review Queue and Integrity Contract

**Files:**
- Create: `tests/natural_memory_benchmark/test_identity_candidate_assessment.py`
- Create: `tools/natural_memory_benchmark/identity_candidate_assessment.py`

- [x] Write failing tests for candidate dispositions, content-derived hashes,
  input SHA binding, exact case/evidence alignment, and rejection of failed
  upstream gates.
- [x] Run focused tests and confirm failure because the module is absent.
- [x] Implement the strict input and review queue models plus pure queue builder.
- [x] Run focused tests to green.

### Task 2: Prove Zero Authoritative Mutation

**Files:**
- Modify: `tests/natural_memory_benchmark/test_identity_candidate_assessment.py`
- Modify: `tools/natural_memory_benchmark/identity_candidate_assessment.py`

- [x] Write failing tests for before/after bundle fingerprints and guarded
  counts covering entities, decisions, closures, snapshots, aggregates, and L2
  units.
- [x] Add compatibility gap measurement without creating authoritative records.
- [x] Assert zero automatic writes and false claim-boundary flags for every
  candidate and top-level output.
- [x] Run focused tests to green.

### Task 3: Add Immutable Runner, Report, and CLI

**Files:**
- Modify: `tools/natural_memory_benchmark/identity_candidate_assessment.py`
- Modify: `tools/natural_memory_benchmark/cli.py`
- Modify: `tests/natural_memory_benchmark/test_identity_candidate_assessment.py`

- [x] Write failing tests for deterministic immutable output, read-only file
  modes, report wording, CLI output, and tamper rejection.
- [x] Implement `assess-identity-candidate-generation` with explicit public,
  proposals, score, experiment root, scenario ID, queue, output, and report
  arguments.
- [x] Keep raw proposer readiness and gate safety as separate report lines.
- [x] Run focused and CLI tests to green.

### Task 4: Run the Frozen Fresh-v4 Assessment

**Files:**
- Create: `artifacts/identity-memory-experiment/candidate-generation-assessment-v3/candidate-review-queue.json`
- Create: `artifacts/identity-memory-experiment/candidate-generation-assessment-v3/assessment.json`
- Create: `artifacts/identity-memory-experiment/candidate-generation-assessment-v3/report.md`

- [x] Run only against the frozen fresh-v4 public/proposals/score artifacts.
- [x] Use an existing identity scenario only as a read-only mutation guard and
  compatibility target.
- [x] Replay all outputs byte-identically and confirm mode `0444`.
- [x] Record exact hashes, metrics, compatibility gaps, and limitations.

### Task 5: Regression Verification and Stage Closeout

- [x] Run focused tests and full `tests/natural_memory_benchmark`.
- [x] Re-run v1, opaque-v2, fresh-v3, dev-v4, fresh-v4, slice, and ledger
  validators.
- [x] Confirm protected fresh-v4 proposal/score/report hashes are unchanged.
- [x] Update `README.md`, `AGENTS.md`, `安排.md`, and this plan with final status
  and the next authorized stage.

Formal fresh-v4 assessment used guard scenario
`ID-DEV-004-unresolved-alias`. It produced four
`eligible_for_manual_review` candidates and two `gate_abstained` candidates.
Case/mention mapping rates were `1.0`; existing entity, L1 evidence, source
revision, and evidence-chain binding rates were all `0.0`. Four attempted non-abstain authoritative
writes were blocked, automatic authoritative writes were `0`, and
authoritative materialization ready count was `0`. The guard fingerprint stayed
`0f00f17b9ed5bd95921ecc2734d29692872e2c4be85c351eee3d2214f8133242`
before and after. Review added duplicate public case/mention rejection, a strict
outer score contract, score-metric consistency checks, subject-reference
binding counts, unique L1-to-source evidence-chain validation, explicit false
claims for every protected write surface, and immediate read-only freezing of
partial outputs. The v1/v2 freezes remain immutable review audit evidence.
Final v3 queue/assessment/report SHA-256 were
`518ead9de8627a9a4384df8cdd9b8728a21fcf797f6b0f3d208dfcb28ac41c0f`,
`49ef708c77561680703e578de140a9d664a0a774dd48dfda0af038bbdc09c7cf`,
and `a4ab8ac584bfde78469244c42e8adc63cd79eecbe14a6eb27f636b9fd74f1b3b`.
Final fresh verification: focused assessment `16 passed`, all identity tests
`82 passed`, full `tests/natural_memory_benchmark` `219 passed`, and
`compileall` exited `0`. Natural-v1, opaque-v2, fresh-v3, dev-v4, fresh-v4,
slice-v1, and ledger validators all returned `valid`; protected fresh-v4
proposal/score/report hashes remained unchanged and mode `0444`.
