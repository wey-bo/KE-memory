# Identity Resolution and Extended-AMR v3 Conformance Report

Run: `run-20260727T080000Z-identity-v1`

Decision: `pass`; identity-authoritative-ready: `True`.

## Frozen gates

- Scenarios: `8` (`4` dev, `4` hidden)
- critical false merges: `0`
- Answerable count exact: `1.0`
- Evidence set exact: `1.0`
- Abstention correctness: `1.0`
- Revision correctness: `1.0`
- Identity closure freshness: `1.0`
- Structural fallback rate: `0.0`

## Carriers

- Native v4 exact round-trip: `1.0`
- Extended-AMR v3 exact round-trip: `1.0`
- Extended-AMR v3 query parity: `1.0`

## Regression boundary

- Frozen v5 hash preserved: `True`
- LongMemEval unresolved-identity abstention preserved: `True`

## Interpretation

This is a hand-authored identity contract diagnostic, not an automatic entity-linking benchmark. The pass shows that evidence-backed identity decisions, correction-safe snapshots, safe `count_distinct`, and Extended-AMR v3 parity are executable on the frozen cases. It does not select final storage or establish product or external-system superiority. The real LongMemEval count remains abstained in frozen v5 until independent membership and identity evidence is added.
