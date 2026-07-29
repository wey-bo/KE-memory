# Representation Conformance Report

Run: `run-20260727Trepresentation-conformance-v1`

Scope: representation conformance only; hand-authored IR; no model extraction; no final storage selection.

## Reference carrier

- Status: `pass`
- Exact round-trip: `True`
- Query probes: `5/5`
- Bundle integrity: `True`
- Authoritative ready: `False`
- Unsupported authoritative capabilities: `lifecycle_and_revision`

## Interpretation

The native Semantic IR JSON is a passing reference carrier for these five probes, not the selected production database.
It is not authoritative-ready because immutable revision history is still missing and several capabilities remain extensions rather than fully executed native semantics.
KEOL, extended AMR, or another representation must be evaluated against the same contract before storage selection.
