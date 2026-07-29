# Identity Proposer Actor-Binding v4 Design

## Objective

Repair the fresh-v3 membership false-abstention category without using fresh-v3 hidden cases as development data. The v4 policy must first pass an independently authored actor-binding diagnostic dev slice. Only then may a new fresh-v4 hidden slice be authored and frozen.

## Non-Negotiable Boundaries

- Work only in the H100 workspace.
- Do not rerun external memory systems or access old Fusion Memory material.
- Do not change the core ontology, dynamic ontology extension, L1/L2 extraction, query processing, symbolic retrieval, or guarded embedding fallback.
- Embeddings are never identity, membership, or fact authority.
- Proposals remain non-authoritative; no automatic merge, membership, or L2 writes are authorized.
- `LONGMEMEVAL-6d550036` remains `structured_l2_identity_unresolved`.
- Fresh-v3 hidden content may be used only as frozen evaluation evidence and error classification. It may not supply v4 diagnostic cases, evidence units, prompt examples, or policy wording tied to its specific surface form.

## Chosen Approach

Use a combined 12-case dev slice:

- six unchanged opaque-v2 dev cases;
- six new diagnostic membership cases authored from independent source evidence;
- diagnostic action balance: two `include`, two `exclude`, two `abstain`;
- no evidence-unit combination overlap with opaque-v2 hidden or fresh-v3 hidden.

This keeps the existing scorer and deterministic authority gate unchanged. A policy-only edit was rejected because it would not add independent coverage. A separate second dev scorer was rejected because it would create two passing-run bindings and unnecessary chronology complexity.

## Diagnostic Data

The diagnostic source uses LoCoMo conversations outside `conv-26` for non-null actor bindings and unused BEAM evidence for null-actor abstention controls. A diagnostic evidence file preserves source text, source reference, speaker metadata, and raw-source replay coordinates.

The combined dev builder validates:

- exact frozen opaque-v2 source binding;
- diagnostic evidence against frozen LoCoMo/BEAM source snapshots;
- actor IDs against LoCoMo speaker names;
- six dev-only diagnostic cases;
- exact `2 include / 2 exclude / 2 abstain` distribution;
- zero prior-hidden case/evidence overlap;
- deterministic combined evidence and derived public/authority/gold artifacts;
- read-only formal files and protected prior-artifact hashes.

## Policy v4

Policy v4 retains all v3 identity rules. Membership decisions add a mandatory observable binding comparison before semantic fallback:

1. If the query subject and the required mention's `source_actor_id` are both non-null, compare the identifiers exactly.
2. Equal identifiers require `include`.
3. Unequal identifiers require `exclude`.
4. The proposer must not abstain from an exact non-null match or mismatch.
5. Null, mixed, or unavailable actor bindings still require explicit membership evidence or abstention.

This rule does not authorize storage. Authority/gold remain unavailable to the proposer and are read only by the independent scoring phase after proposals are frozen.

## Phase Order

1. Freeze diagnostic evidence, diagnostic source, and combined dev slice.
2. Author and freeze policy-v4 plus dev/final prompts.
3. Run one zero-history proposer message using only the frozen dev prompt and public JSON.
4. Freeze proposals, provenance, and transport receipt.
5. Score with unchanged authority gate and scorer.
6. If dev fails, classify false merge, false membership, false abstention, and evidence errors; remain on dev.
7. If dev passes, author fresh-v4 hidden cases without using policy-specific examples.
8. Freeze fresh-v4, run a new zero-history proposer, freeze proposals, then score.

## Gates

Dev and final runs use the existing proposal-quality thresholds:

- raw action accuracy at least `0.85`;
- critical false merge count `0`;
- critical false membership count `0`;
- raw abstention F1 at least `0.8`;
- proposal evidence exactness at least `0.95`.

Raw proposer quality and deterministic gate safety remain separately reported. A gated result cannot hide raw errors. Candidate-generation integration remains deferred unless the final run satisfies the complete contract.

## Audit Limitations

Zero-history isolation is enforced through a fresh proposer process, an allowlisted prompt/public contract, and a transport receipt. It remains a declarative execution boundary rather than a trusted external sandbox attestation. Filesystem chronology receipts are posthoc SHA-256/mtime audit evidence, not an external trusted timestamp.

