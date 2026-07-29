# Representation Conformance Report

Run: `run-20260727Trepresentation-conformance-v4`

Scope: representation conformance only; hand-authored IR; no model extraction; no final storage selection.

## Reference carrier

- Status: `pass`
- Exact round-trip: `True`
- Query probes: `5/5`
- Bundle integrity: `True`
- Authoritative ready: `False`
- Unsupported authoritative capabilities: `raw_source_revision_binding`, `lifecycle_and_revision`, `structured_l2_semantics`, `closure_evaluation_versioning`

## Extended AMR candidate

- Status: `fail`
- Exact round-trip: `True`
- Query probes: `5/5`
- Bundle integrity: `True`
- Authoritative ready: `False`
- Hard-gate failures: `required_capability_unsupported`
- Unsupported authoritative capabilities: `raw_source_revision_binding`, `lifecycle_and_revision`, `structured_l2_semantics`, `closure_evaluation_versioning`

## Interpretation

The native Semantic IR JSON is a passing reference carrier for these five probes, not the selected production database.
It is not authoritative-ready because immutable revision history is still missing and several capabilities remain extensions rather than fully executed native semantics.
The extended AMR graph preserves the same bundle and query results, but it is not authoritative-ready because four hard memory capabilities remain unsupported.
KEOL, extended AMR, or another representation must pass the same complete contract before storage selection.
