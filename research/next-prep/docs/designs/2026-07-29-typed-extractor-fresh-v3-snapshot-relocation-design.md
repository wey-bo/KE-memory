# Typed Extractor Fresh-V3 Snapshot Relocation Design

## Status

Approved under the user's standing instruction to continue established designs
without an intermediate confirmation. This design replaces only the unfinished
fresh-v3 receipt publication step after the next-prep workspace was normalized
into the `ke-memory-demo` Git worktree.

## Goal

Freeze one reviewable fresh-v3 authoring implementation receipt in the
normalized `research/next-prep` snapshot without changing the frozen
preregistration, the reviewed authoring module/test, or any hidden evaluation
data.

## Facts And Constraints

- The frozen preregistration SHA-256 remains
  `183cf6fc2991361e5da57b17e06a5970f651000986d50b87e8af2e6796440204`.
- The reviewed authoring module/test SHA-256 values remain
  `c8ffb3f9466583ecad42049b200224ef038c9c85b6edaec73f2723944ebd8bad`
  and
  `ffba0281ca47d6e10781c06471c86367424780010e5cdeff458cba22f16db02a`.
- Git commit `00fa803ee44bcef5a299babb9a8e2b7ba9f994e4` introduced those exact
  files under `research/next-prep/`.
- The preregistration chronology truthfully records the original H100 absolute
  roots. Its bytes must not be rewritten to claim that it was frozen in the
  normalized repository.
- The invalid source-side zero-byte receipt was excluded during normalization
  and is not authority.
- The v3 evaluation root and v3 materialization module/test remain absent.
- This stage creates no hidden data, model request, proposal, score, memory
  revision, identity, membership, closure, snapshot, or aggregate write.

## Alternatives

1. **Git snapshot relocation receipt v2, selected.** Keep the original
   chronology as historical evidence and add an explicit mapping from its
   old absolute roots to the normalized relative paths. Bind the mapping to a
   fixed Git commit and fixed blob/file hashes.
2. **Rewrite the preregistration chronology, rejected.** This would invalidate
   the frozen preregistration SHA and retroactively misstate where it was
   frozen.
3. **Recreate the old path with a symlink or bind mount, rejected.** This would
   keep the new work dependent on the retired workspace and provide no durable
   Git recovery chain.

## Ownership

The relocation step adds:

- `tools/natural_memory_benchmark/typed_extractor_fresh_v3_snapshot_receipt.py`;
- `tests/natural_memory_benchmark/test_typed_extractor_fresh_v3_snapshot_receipt.py`;
- `artifacts/automatic-extraction-assessment/typed-extractor-v3-fresh-hidden-prereg-v1/authoring-implementation-receipt.json`;
- this design, its implementation plan, and completion fact-source updates.

It does not modify the preregistration JSON/module/test, the fresh-v3 authoring
module/test, any v1/v2 frozen chain, shared scorer/query/identity/authority
code, or runtime packages outside `research/next-prep`.

## Relocation Authority

The adapter accepts only the repository root and its exact
`research/next-prep` child. It verifies:

1. `git rev-parse --show-toplevel` equals the supplied repository root;
2. the fixed snapshot commit exists and is an ancestor of the current `HEAD`;
3. the preregistration, authoring module, and authoring test at the fixed
   commit have the expected Git blob IDs and SHA-256 bytes;
4. the current working files are regular non-symlink files whose bytes equal
   the fixed commit blobs;
5. all preregistered input/code hashes still validate through the existing
   path-neutral bundle builder;
6. the original chronology paths exactly equal the frozen old H100 paths;
7. the normalized paths exactly equal the repository-relative mapping encoded
   by this adapter;
8. the receipt, evaluation root, and materialization module/test have not
   appeared before publication.

The fixed commit proves the imported implementation identity. The receipt also
binds the current relocation adapter/test hashes because those files do not
exist in the imported commit.

## Receipt V2

The only formal artifact remains
`authoring-implementation-receipt.json`. Its schema is
`typed-extractor-fresh-v3-authoring-receipt-v2` and contains:

- the complete path-neutral implementation binding previously required by the
  v1 receipt;
- original preregistration/evaluation absolute paths;
- normalized repository-relative preregistration/evaluation paths;
- repository root evidence kind `git-commit-blob-plus-sha256`;
- fixed snapshot commit and Git blob IDs;
- relocation adapter/test SHA-256 values;
- exact blueprint, dependency, prior-input, candidate-queue, live-guard, and
  zero-write bindings;
- the unchanged claim boundaries for embedding, LongMemEval identity,
  pipeline integration, manual adjudications, and external systems.

The receipt time remains a caller-supplied untrusted UTC label. Filesystem
`0444` is applied at publication time, but Git blob identity plus canonical
bytes is the durable recovery authority because Git does not preserve read-only
permission bits.

## Publication And Validation

Publication uses a private named staging file in the receipt directory and
`renameat2(RENAME_NOREPLACE)` while holding the existing preregistration
chronology lock. Immediately before renaming, the adapter rebuilds the Git
relocation binding, implementation binding, live guard, candidate queue, and
future-absence checks and verifies the staging pathname against its open inode.
It then fsyncs the directory, closes the staging descriptor, reopens the
canonical mode-`0444` receipt, and verifies its bytes and inode identity.

The initial anonymous-inode design was rejected during execution. On the H100
JuiceFS mount, `O_TMPFILE` plus `linkat(AT_EMPTY_PATH)` returned success and the
target was readable while the anonymous descriptor remained open, but the
target decayed after descriptor close into an unreadable zero-byte ghost entry
with link count and mode both zero. A 30-file same-mount reproduction failed
30/30 after a one-second delayed read. The named-staging/no-replace design
retains no-clobber atomicity while avoiding that filesystem-specific false
success mode. Any receipt-specific named staging residue from an interrupted
publisher causes later publication to fail closed for manual inspection; the
publisher never deletes an unknown stale staging entry automatically.

Validation rejects symlinks, noncanonical JSON, unknown/coercive fields,
wrong Git ancestry/blob identity, dirty bound implementation files, changed
inputs, changed guard state, future artifacts, and receipt pathname
replacement during validation. It returns the SHA-256 of the exact bytes it
validated. A later materializer must pin that receipt SHA and validate it
inside the same chronology lock used for no-replace publication.

## Testing

Tests cover exact Git commit/blob bindings, original-to-normalized path mapping,
dirty or replaced bound files, non-ancestor and wrong-repository failures,
canonical receipt bytes, no-clobber/idempotent publication, target replacement,
future artifact rejection, live guard rebuilding, exact SHA reporting, and
zero hidden/model/authority writes. Existing fresh-v3 authoring focused tests
must remain green and byte-identical.

## Completion Boundary

Passing this relocation receipt gate authorizes only a separately designed,
one-time fresh-v3 hidden materialization. It does not authorize a proposer,
scoring, pipeline integration, identity or membership materialization, L1/L2
writes, benchmark expansion, or external memory-system reruns.
