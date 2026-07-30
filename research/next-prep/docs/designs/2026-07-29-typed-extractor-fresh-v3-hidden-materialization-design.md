# Typed Extractor Fresh-V3 Hidden Materialization Design

## Status

Approved under the user's standing instruction to execute subsequent stages
without intermediate confirmation. This design is recorded after the canonical
normalized-snapshot authoring receipt was committed and before the fresh-v3
evaluation root or materialization module/test exists.

## Goal

Materialize all preregistered fresh-v3 authored hidden cases exactly once: 24
L1 cases across eight families and 18 L2 cases across nine families. The stage
must not call a proposer/model, read the future authority/gold for scoring,
materialize a memory fact, or create any evaluation output beyond the frozen
source/public/authority/gold/manifest payloads and their chronology receipt.

## Alternatives

1. Write the ten payloads directly into the final evaluation root. Rejected
   because interruption can expose a partial formal dataset.
2. Generalize the fresh-v2 materializer into a shared framework. Rejected for
   this stage because it expands the change surface into a completed historical
   path and is not required to preserve the v3 receipt contract.
3. Add a standalone fresh-v3 materializer that stages and validates one complete
   directory before no-replace publication. Selected because it leaves every
   receipt-bound file byte-identical and gives the smallest auditable write
   surface.

## Architecture

Create
`tools/natural_memory_benchmark/typed_extractor_fresh_v3_materialization.py`
and its focused test. The module consumes the committed preregistration and
active relocation receipt but does not modify the preregistration, authoring
module/test, relocation module/test, scorer, query compiler, identity code, or
runtime packages.

The public interfaces are:

```python
def materialize_fresh_v3_hidden(
    repository_root: Path,
    workspace_root: Path,
    evaluation_root: Path,
    materialization_time: str,
) -> dict[str, Any]:
    ...


def validate_fresh_v3_hidden_materialization(
    repository_root: Path,
    workspace_root: Path,
    evaluation_root: Path,
) -> dict[str, Any]:
    ...
```

The writer validates the exact approved relocation receipt through a strict
phase-transition validator before creating a staging directory. It builds and
validates the pure authoring bundle, writes ten canonical payloads to a unique
sibling staging root, sets JSON modes to `0444`, builds the chronology receipt
last, validates the complete staging tree, revalidates the active receipt and
protected state, and publishes the directory with
`renameat2(RENAME_NOREPLACE)`. Root and layer directories use mode `0775` for
the later isolated proposer stage. Staging creation is anchored to an opened
parent directory descriptor; layer and JSON creation, writes, chmod, and fsync
remain descriptor-relative and no-follow until publication. Any
pre-publication error verifies the current staging pathname still names the
expected directory inode and then preserves the staging tree for audit. A
failure during writing may leave it partial; even a complete staging chronology
is uncommitted intent, not evidence that the transition succeeded. Linux
provides no inode-conditioned unlink/rmdir primitive, so failure handling never
deletes a replaceable pathname and cleanup errors never replace the primary
failure. Only the no-replace-published official root is authoritative.

## Active Receipt Binding

The approved active receipt is:

```text
artifacts/automatic-extraction-assessment/
typed-extractor-v3-fresh-hidden-prereg-v1/
authoring-implementation-receipt.json
```

Its required SHA-256 is
`c810f421d5a3b0726b862ec2f12c89e0d638e0747892637e2a32977587b7ef8c`,
schema is `typed-extractor-fresh-v3-authoring-receipt-v2`, and local mode is
`0444`. The receipt's original public validator was rerun successfully before
the materialization design/module/test existed and remains the historical
pre-implementation gate.

The public receipt validator cannot be called after implementation begins:
the receipt correctly records both materialization code paths as absent, while
this phase intentionally creates exactly those two files. The standalone
phase-transition validator therefore strictly reopens the approved canonical
receipt, checks its fixed SHA/mode, requires its declared materialization path
set to equal the new module/test paths, binds both new files by SHA-256, replays
the fixed Git commit/blob binding, rebuilds the path-neutral authoring binding
and protected state, and compares every unchanged field to the receipt. Before
publication it additionally requires the official evaluation root to remain
absent. Post-publication validation repeats the same checks except for the
intentional evaluation-root transition. This validation path does not relax
or mutate the historical receipt.

## Formal Layout

```text
typed-extractor-v3-fresh-hidden-v1/
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

The root must contain exactly these entries. It must not contain `model-runs`,
dispatch, raw response, proposal, provenance, score, report, adjudication,
memory-unit, revision, closure, identity, membership, snapshot, or aggregate
paths.

## Materialization Chronology

`chronology-receipt.json` uses schema
`typed-extractor-fresh-v3-materialization-receipt-v1` and status
`frozen_pre_model`. It records:

- caller-supplied untrusted UTC materialization label;
- preregistration path, schema, SHA-256, size, and mode;
- active relocation receipt path, schema, SHA-256, size, and mode;
- fixed import commit and three Git blob OIDs from the active receipt;
- materializer module/test SHA-256;
- all ten output SHA-256, size, and mode values;
- exact L1/L2 counts `24/18`, family maps, and manifest hashes;
- sequence claims for receipt validation before staging, payload validation
  before publication, receipt/protected-state revalidation immediately before
  publication, and absent model-run paths;
- model request and evaluation-result write counts of `0`;
- all nine automatic write counts of `0`;
- `pipeline_integration_authorized=false`,
  `manual_identity_adjudications_materialized=false`,
  `embedding_authority=false`, and
  `external_memory_systems_rerun=false`;
- `LONGMEMEVAL-6d550036=structured_l2_identity_unresolved`.

Filesystem mtime is not a trusted chronology source. Durable recovery is the
active receipt, Git commit/blob chain, exact canonical bytes, and chronology
content hashes.

## Validation And Failure Handling

The validator rebuilds the pure authoring bundle and requires byte-identical
canonical JSON for every payload. It checks exact artifact sets, file modes,
directory modes, chronology equality, case/family counts, manifest hashes,
receipt/Git/protected-state bindings, and absence of model or evaluation-result
paths outside the frozen payload set. Validation is read-only.

- Existing official root: fail before staging.
- Missing, writable, noncanonical, wrong-SHA, or drifted receipt: fail before
  staging.
- Materialization path set mismatch, symlink/non-regular module/test, or code
  hash drift: fail before staging.
- Git ancestry/blob/current-byte or protected-state drift: fail before staging.
- Invalid authored bundle or contamination: fail before staging.
- Staging write or validation failure: preserve the unique, potentially partial
  and non-authoritative staging root for audit after verifying its directory
  identity; do not delete by pathname.
- Parent/staging path replacement: descriptor-relative creation and writes do
  not follow the replacement; fail closed before publication.
- Concurrent target creation: `RENAME_NOREPLACE` fails and preserves the
  concurrently created target; preserve staging for audit.
- Post-publication drift: validator fails closed and never repairs artifacts.

## Testing And Freeze Gate

Tests are written before the module and must first fail because the module is
absent. Coverage includes exact payload bytes and sets, `24/18` counts, family
maps, modes, chronology fields, approved receipt binding, Git/protected-state
replay, invalid UTC, existing/concurrent target refusal, fail-closed staging
preservation, parent/staging exchange, cleanup-error precedence,
payload/chronology/mode drift, unregistered artifacts, model-run paths, and all
zero/false authorization boundaries.

Before the one-time official call, the materializer and test are committed and
independently reviewed with no open Critical or Important finding. The gate
also requires focused and phase-aware typed tests, runtime tests, static
checks, exact receipt transition validation, credential scan, candidate
queue/live guard, evaluation-root absence, staging-residue absence, and
zero-write audit. Known normalization dependency or frozen-path failures
remain separately reported and do not authorize historical artifact edits.

## Unchanged Boundaries

- Do not call DeepSeek, Codex, or any proposer/model in this stage.
- Do not score proposals or expose authority/gold to a proposer.
- Do not materialize the four manual identity adjudications.
- Do not authorize pipeline integration or automatic L1, L2, revision,
  source-revision, closure, identity, membership, snapshot, or aggregate
  writes.
- Embedding remains non-authoritative.
- Do not rerun external memory systems or access the retired Fusion Memory
  implementation.
- Keep `LONGMEMEVAL-6d550036` at
  `structured_l2_identity_unresolved`.

## Self-Review

- Placeholder scan: no placeholder marker or deferred contract choice remains.
- Consistency: paths, evaluation ID, receipt SHA/schema, counts, family totals,
  modes, and public function signatures agree across all sections.
- Scope: this design ends at one-time pre-model materialization and does not
  include proposer, scoring, qualification, pipeline integration, or memory
  writes.
- Failure behavior is fail-closed and every write is confined to one unique
  sibling staging directory plus one no-replace directory publication.
