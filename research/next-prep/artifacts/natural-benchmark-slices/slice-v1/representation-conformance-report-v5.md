# Authoritative Memory Contract v5 Conformance Report

Run: `run-authoritative-conformance-v5`

Scope: v3 authoritative contract over the frozen hand-authored real slice; no model extraction and no external memory rerun.

## Source and closure gates

- Source validation: `True`
- Source records replayed: `13`
- Fresh closure evaluations: `6/6`
- Closure result parity: `6/6`

## Frozen correctness

- Probes passed: `5/5`
- The LongMemEval count probe deliberately abstains with `structured_l2_identity_unresolved`; its four evidence candidates are preserved, but the display count is not authoritative.

## Carriers

- Native v3 round-trip: `True`; query parity `5/5`; authoritative-ready `False`
- Extended-AMR v2 round-trip: `True`; query parity `5/5`; authoritative-ready `False`
- Native hard-gate failures: `['structured_l2_identity_unresolved']`
- Extended-AMR v2 hard-gate failures: `['structured_l2_identity_unresolved']`

## Interpretation

Both carriers preserve the same typed v3 bundle and pass the five frozen correctness probes. The run is not a storage-selection or product-superiority result: authority remains blocked until project identity/deduplication is modeled well enough to support the requested count claim.
