# Typed Extractor Fresh-V2 Authoring Receipt Supersession Design

## Status

Approved under the user's standing direction to execute subsequent stages
according to the agent's design without intermediate confirmation. This design
is recorded before creating any supersession receipt or formal hidden artifact.

## Incident And Goal

Another execution actor created the immutable
`authoring-implementation-receipt.json` at `2026-07-29 00:31:10 +0800` while
the second independent review still had an open Important finding. The file is
mode `0444`, SHA-256
`4bb2575d985126dfbd91d01a3111d3f4acb2ebe57c3bfd62b1d60ee847d7314d`,
and binds the pre-repair module SHA-256
`2a46b75d5932b7d6069aa49a72a75290d4392181d1bb1c8dcf1bb6e10b207b7d`.
The repaired module intentionally makes the original receipt fail with
`authoring receipt drift`. The formal evaluation root remains absent and no
model request or authoritative memory write is authorized.

The goal is to recover without deleting, overwriting, or treating the flawed
receipt as active authority.

## Alternatives

1. Delete or overwrite the original receipt. Rejected because it destroys the
   chronology and violates the immutable-artifact contract.
2. Supersede the entire preregistration with prereg-v4. Rejected because the
   preregistered evaluation composition, prompts, thresholds, and exclusions
   remain valid; only the post-prereg authoring implementation binding drifted.
3. Append one immutable v2 supersession receipt beside the original. Selected
   because it preserves the failed binding as audit evidence while making the
   corrected implementation the only active authoring authority.

## Contract

The new artifact is
`authoring-implementation-receipt-v2.json` with schema
`typed-extractor-fresh-v2-authoring-receipt-v2`. It records:

- the exact prereg-v3 path, schema, SHA-256, and `0444` mode;
- the original receipt path, SHA-256, `0444` mode, and schema;
- supersession reason
  `post_freeze_review_primary_literal_binding_repair`;
- current authoring module, test, dependency, and blueprint-manifest hashes;
- exact L1/L2 family counts and prior-input hashes;
- absent formal evaluation root, zero hidden artifacts, zero model requests,
  and zero automatic writes;
- unchanged pipeline and `LONGMEMEVAL-6d550036` boundaries.

The original receipt stays byte-identical. The v2 writer refuses to run unless
the original receipt has the exact frozen hash and mode, the current authoring
bundle validates, the formal root and model-run paths are absent, and the v2
path is absent or byte-identical. The writer never creates hidden data.

## Active Receipt Resolution

`validate_fresh_v2_active_authoring_receipt(...)` is the only receipt gate for
the future hidden materializer:

1. If the v2 receipt exists, validate the immutable predecessor hash and the
   v2 receipt against current code, tests, dependencies, blueprints, prereg,
   and absence boundaries; return v2 as active.
2. If v2 does not exist, validate v1 against current code. Any drift fails
   closed.

The future materializer must not call the v1 validator directly and must not
infer authority from file existence alone.

## Semantic Repair

Every emitted L2 primary claim must copy the public untyped candidate's exact
predicate, subject, and object/theme surfaces. The travel profile therefore
uses one aggregate claim with operator `aggregate_travel_profile`, sense
`preference.travel_profile`, both L1 support refs, abstraction
`preference_aggregation`, and closure `multi_evidence_set`. Per-turn rail and
lodging semantics remain separate in the L1 support pack.

## Verification And Boundaries

- Add RED/GREEN tests for the L2 literal binding and validator rejection.
- Add RED/GREEN tests for predecessor tampering, current hash drift,
  idempotence, immutable mode, active-receipt selection, and premature formal
  paths.
- Obtain a read-only re-review before freezing v2.
- Keep prereg-v3, the original receipt, candidate v3 queue, and guard artifacts
  byte-identical.
- Do not create formal hidden source/public/authority/gold/manifest/chronology
  files and do not call a proposer/model in this recovery stage.
- Do not authorize L1/L2, revision, source-revision, closure, identity,
  membership, snapshot, or aggregate writes.

