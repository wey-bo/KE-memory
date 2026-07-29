# Typed Extractor V2 Diagnostic Prompt Repair V1 Plan

**Status:** completed; diagnostic-only; fresh-hidden v2 preregistration only.

## Frozen Baseline

- L1 run: `run-20260728T120704Z-deepseek-chat-official-typed-l1-dev-repair-v2`
- L2 run: `run-20260728T120705Z-deepseek-chat-official-typed-l2-dev-repair-v2`
- Both requested `deepseek-chat`; both responses identify `deepseek-v4-flash`.
- False emission, false abstention, critical materialization, and evidence errors
  are zero in both layers.
- L1 strict failure: one `role_or_local_entity_error`; all other exact metrics
  are `1.0`, with zero gate interventions.
- L2 strict failures: one `abstraction_error`, one `structured_claim_error`, and
  one gate intervention; all other exact metrics are `1.0`.

## Task 1: L1 Explicit Participant Decomposition

- Freeze a new diagnostic prompt derived only from L1 V6 plus this baseline's
  diagnostic error.
- Require an explicit `with X` participant to become a separate local entity
  when the selected operator exposes a `participant` role. Apply the same
  evidence-only rule to explicit `for X` beneficiary and `to X` recipient
  phrases without inferring unstated participants.
- Add a pre-submit audit that every public operator-role binding required by the
  selected operator is represented by a distinct, exact-source local entity
  whenever its participant is explicitly present.
- Re-run only the immutable L1 diagnostic public input with a new no-history
  request, then freeze before scoring.

## Task 2: L2 Abstraction Dominance

- Freeze a new diagnostic prompt derived only from L2 V8 plus this baseline's
  diagnostic errors.
- Select `state_summary` when repeated supports describe persistence of the same
  state and the resolved L2 kind is `long_running_state`; do not fall back to
  `coreference_resolution` merely because the later wording refers back to the
  earlier state.
- Select `preference_aggregation` for a compatible multi-support preference
  profile before considering coreference.
- Preserve the existing lifecycle and task-composition precedence rules.

## Task 3: L2 Operator-Sense Pair Closure

- Create a new versioned diagnostic public contract containing explicit
  `operator_sense_bindings`; do not mutate the frozen v2 public input.
- Require every structured claim's operator/sense pair to occur in that catalog.
  A resolved archive coreference claim must use
  `archive_document|document.archive_coreference`, never the L1 support sense
  `document.archive_request`.
- Add proposal validation tests that reject catalog-external or mismatched
  operator/sense pairs before scoring.

## Task 4: Strict Requalification

- Run one new no-history request per repaired layer using public-only input.
- Freeze raw response, proposals, and provenance before authority/gold scoring.
- Require every configured strict metric to equal `1.0`, raw critical false
  emissions to equal `0`, gate interventions to equal `0`, guard fingerprints
  and counts to remain unchanged, and all automatic writes to remain `0`.
- Report raw proposer quality separately from deterministic gate safety.
- Only a dual strict pass authorizes preregistration of fresh-hidden v2. It does
  not authorize pipeline integration or authoritative L1/L2 writes.

## Final Result

- L2 final run: `run-20260728T123925Z-deepseek-chat-official-typed-l2-dev-repair-v9` under the versioned v3 public contract. Every strict metric is `1.0`; gate intervention and critical counts are zero.
- L1 V7, V8, and V9 remain immutable failed diagnostic runs. Their raw errors were reported independently from gate safety.
- L1 final run: `run-20260728T130544Z-deepseek-chat-official-typed-l1-dev-repair-v10`. Every strict metric is `1.0`; gate intervention and critical counts are zero.
- Both layers now pass raw proposer quality, deterministic gate safety, and strict dev-repair qualification. This authorizes only a separate fresh-hidden v2 preregistration. It does not create hidden cases, authorize pipeline integration, or authorize any L1/L2/revision/closure/identity/membership write.
