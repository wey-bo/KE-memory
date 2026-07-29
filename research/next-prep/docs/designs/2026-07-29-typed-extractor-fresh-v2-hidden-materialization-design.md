# Typed Extractor Fresh-V2 Hidden Materialization Design

## Status

Approved under the user's standing instruction to execute subsequent stages
without intermediate confirmation. This design is recorded after the active
authoring receipt was frozen and before the formal evaluation root exists.

## Goal

Materialize the preregistered 24 L1 and 12 L2 authored hidden cases exactly
once, without running a proposer/model and without creating any authoritative
memory write. The published root must be complete, immutable at the file
level, reproducible from the active authoring receipt, and safe against a
partial-write failure.

## Alternatives

1. Write the ten formal JSON files directly into the final evaluation root.
   Rejected because a process failure could leave a partial formal dataset.
2. Add materialization functions to the receipt-bound authoring module.
   Rejected because changing that module would invalidate the active receipt.
3. Add a standalone materializer that stages and atomically publishes one
   complete root. Selected because it preserves the active receipt while
   making publication all-or-nothing on the current filesystem.

## Architecture

Create `tools/natural_memory_benchmark/typed_extractor_fresh_v2_materialization.py`.
It imports the pure bundle builder from the frozen authoring module but does
not modify that module or its test.

The public writer is:

```python
def materialize_fresh_v2_hidden(
    preregistration_path: Path,
    evaluation_root: Path,
    workspace_root: Path,
    materialization_time: str,
) -> dict[str, Any]:
    ...
```

The public validator is:

```python
def validate_fresh_v2_hidden_materialization(
    preregistration_path: Path,
    evaluation_root: Path,
    workspace_root: Path,
) -> dict[str, Any]:
    ...
```

The writer must refuse an existing evaluation root. Before creating any
staging directory it calls `validate_fresh_v2_active_authoring_receipt` with
the official absent evaluation root. It then builds and validates the exact
authoring bundle, creates a unique sibling staging directory, writes the five
L1 and five L2 payloads, freezes each file to mode `0444`, writes the
materialization receipt last, validates the staging root, and atomically
renames the staging directory to the official evaluation root. Any exception
before publication removes only the exact staging directory.

## Formal Layout

```text
typed-extractor-v2-fresh-hidden-v2/
  chronology-receipt.json
  l1/
    source-cases-l1.json
    public-l1.json
    authority-l1.json
    gold-l1.json
    manifest-l1.json
  l2/
    source-cases-l2.json
    public-l2.json
    authority-l2.json
    gold-l2.json
    manifest-l2.json
```

No `model-runs`, proposals, provenance, score, report, adjudication, L1/L2
unit, closure, identity, membership, revision, snapshot, or aggregate path is
created in this stage.

## Materialization Receipt

`chronology-receipt.json` uses schema
`typed-extractor-fresh-v2-materialization-receipt-v1` and status
`frozen_pre_model`. It records:

- the exact prereg-v3 path, SHA-256, and mode `0444`;
- the exact active v2 authoring receipt path, schema, SHA-256, mode `0444`,
  predecessor SHA-256, and supersession reason;
- caller-supplied untrusted UTC materialization label;
- materializer module/test SHA-256;
- all ten output SHA-256 values and exact mode `0444`;
- L1/L2 case counts `24/12`, family counts, and manifest hashes;
- the sequence claims `active_receipt_validated_before_staging`,
  `outputs_validated_before_atomic_publish`, and
  `model_runs_absent_at_publish`;
- zero automatic write counts, `pipeline_integration_authorized=false`, and
  `LONGMEMEVAL-6d550036=structured_l2_identity_unresolved`.

The chronology deliberately does not use filesystem mtime as a trusted
ordering source. Its authority is the active receipt plus content hashes and
the materializer's fail-closed sequence.

## Validation

The post-publication validator cannot call the pre-materialization active
receipt validator because the formal root now exists. Instead it validates
the frozen v2 receipt file and chronology binding, recomputes current
authoring code/test/dependency hashes against the receipt, rebuilds the pure
bundle, requires canonical byte equality for all ten payloads, rechecks
manifest hashes and exact `0444` modes, and rejects any `model-runs` path.

It also requires the formal root and both layer directories to be writable
directories for the later proposer stage while every frozen JSON remains
read-only. Validation never creates or modifies files.

## Failure Handling

- Existing final root: fail before any write.
- Missing, writable, invalid, or drifted active receipt: fail before staging.
- Bundle or contamination failure: fail before staging.
- Staging write/validation failure: remove only the unique staging directory.
- Atomic publish failure: remove only the staging directory; final root must
  remain absent.
- Post-publication drift: validator fails closed; it never rewrites artifacts.

## Testing And Review

Tests must first fail with the materializer module absent. Coverage includes
exact output bytes, counts, modes, receipt binding, active-receipt invocation,
existing-root refusal, receipt/code/manifest drift, model-run rejection,
staging cleanup on injected publish failure, idempotence refusal, and zero
write boundaries. An independent read-only review with no Critical/Important
finding is required before the one-time official materialization.

## Unchanged Boundaries

- Do not run DeepSeek, Codex, or any proposer/model in this stage.
- Do not materialize the four manual identity adjudications.
- Do not rerun external memory systems or access old Fusion Memory.
- Embeddings are not authority.
- Do not authorize pipeline integration or any automatic L1/L2, revision,
  source-revision, closure, identity, membership, snapshot, or aggregate write.

