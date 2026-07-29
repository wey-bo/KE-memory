# Identity Resolution, Schema.org-Informed Concepts, and Extended-AMR v3 Design

Status: frozen for implementation on 2026-07-27.

## Goal

Resolve the next blocker after authoritative memory contract v3/v5: evidence-backed entity identity, correction-safe deduplication, and safe `count_distinct` execution. Extended-AMR is the primary candidate carrier for this wave, while the authoritative identity and aggregate contract remains representation-independent.

This wave does not select a production database, perform model extraction, rerun external memory systems, or convert schema.org vocabulary into factual authority.

## Decisions

### Extended-AMR is the principal carrier

Extended-AMR v3 will explicitly encode local concepts, entity records, identity decisions, identity snapshots, and aggregate claims beside the existing event-role, revision, evidence, and closure graphs. Standard AMR remains insufficient because it does not natively carry stable cross-session identity, immutable decision history, evidence closure, or aggregate authorization.

### The authoritative contract remains carrier-neutral

Identity decisions and aggregate claims are logical records. Native v4 and Extended-AMR v3 must round-trip the same records and execute the same queries. An adapter cannot establish identity merely by preserving a `same-as` edge.

### Schema.org is an advisory concept source

The selected reference is schema.org release 30.0 from the official `schemaorg/schemaorg` repository at commit `f72e60b7f67578b4af9445fa20fc8ec3fe1c9b93`.

Relevant modeling patterns:

- `Person`, `Organization`, `Project`, `Action`, `Event`, and `Role` provide candidate type patterns.
- `agent`, `object`, and `result` align with event-role modeling.
- `startDate` and `endDate` inform time-bounded roles and events.
- `identifier` is a candidate external identifier pattern.
- `sameAs` is only an unambiguous external identity URL in schema.org. It is not a general-purpose permission to merge two local memory entities.
- schema.org 30.0 defines `Project` as a subtype of `Organization`. The local memory concept `memory:Project` is broader because it includes personal, class, research, and temporary work projects. Therefore the mapping is `related`, not `exact`.

Every adopted mapping records the external source/version, mapping relation, local constraints, and executable validation. Schema.org labels or ranges never override source evidence, local identity policy, lifecycle, or epistemic status.

## Logical records

### Concept registry

`ConceptRegistryEntry` defines one local canonical concept:

- stable `concept_id` and label;
- local parent concepts;
- external mappings with `exact`, `narrower`, `broader`, or `related` relation;
- allowed identity properties;
- executable constraints and source/version metadata.

The minimum registry contains local `Person`, `Organization`, `Project`, `Action`, `Event`, and `Role` concepts plus event-role properties. It is a schema and normalization input, not a fact store.

### Entity record

`EntityRecord` represents a provisional or canonical entity:

- stable local entity ID;
- local concept IDs;
- names and aliases;
- typed strong identifiers and external identity URLs;
- lifecycle and revision metadata;
- source L1 units and source revisions.

Names and aliases are candidate evidence only. A shared strong identifier can support a merge if namespace and scope match. A name collision never establishes identity.

### Identity decision

`IdentityDecision` is immutable and evidence-backed. Its action is one of:

- `merge`: multiple provisional entities resolve to one canonical entity;
- `keep_distinct`: entities are explicitly known to be different;
- `reject_merge`: a merge candidate is rejected by conflicting evidence;
- `split`: a previous merge is corrected and superseded;
- `abstain`: current evidence is insufficient to merge or separate safely.

Each decision records status, subjects, optional canonical entity, reason code, evidence L1 units, evidence source revisions, identity-closure ID/hash, producer, transaction time, and optional superseded decision. Accepted decisions form the active identity policy. Superseded decisions remain auditable but do not affect the current snapshot.

### Identity evidence closure

`IdentityEvidenceClosure` pins the exact evidence needed for a decision:

- decision ID;
- required L1 unit IDs and source revision IDs;
- unit payload and source content hashes;
- policy version;
- deterministic input fingerprint and result hash;
- completeness and reason code.

A closure becomes stale if a required unit revision, source revision, decision payload, or identity policy changes. Changes outside the decision scope do not make it stale.

### Identity snapshot

`IdentitySnapshot` is a deterministic materialization of active, fresh identity decisions. It contains:

- canonical entity mapping;
- explicit distinct pairs;
- unresolved groups;
- active decision IDs and closure hashes;
- deterministic input fingerprint and snapshot ID.

The builder rejects contradictory active policy, including a pair that is both merged and distinct, multiple incompatible canonical targets, or an accepted decision with incomplete/stale evidence closure.

### Safe aggregate claim

`IdentityAggregateClaim` authorizes `count_distinct` only when all of the following are explicit:

- the L2 structured claim and query it supports;
- exact member L1 units;
- source role whose entity is counted;
- identity snapshot ID;
- resolved member entity IDs and canonical entity IDs;
- decision IDs and evidence/source closure;
- computed value and deterministic aggregate hash.

Execution recomputes the member set from L1 role bindings and the referenced fresh identity snapshot. It must abstain when any member is unresolved, a distinctness conflict exists, the snapshot is stale, the member/evidence set is incomplete, or the stored value differs from the recomputed count.

The current frozen LongMemEval v5 case remains unchanged and continues to abstain with `structured_l2_identity_unresolved`. The new identity experiment may prove the contract on controlled and frozen diagnostics, but it must not rewrite the four real-slice events into two projects without independent evidence-backed membership and identity decisions.

## Native v4 bundle

`IdentityAwareMemoryBundleV4` extends the v3 authoritative bundle with:

- concept registry entries;
- entity records;
- identity decisions and closures;
- identity snapshots;
- identity-backed aggregate claims.

The v3 materialized L1/L2 views, revision ledgers, source records, closure evaluations, and query plans remain intact. Existing v3/v5 files and bytes are not modified.

## Extended-AMR v3

`extended-amr-memory-graph-v3` reuses the explicit v2 event-role/revision graphs and adds:

- concept nodes and external-mapping edges;
- entity nodes, concept-membership edges, identifier annotations, and provenance edges;
- identity-decision nodes with action/status/reason and evidence edges;
- supersession edges for corrected decisions;
- snapshot nodes with canonicalization, distinctness, and unresolved edges;
- aggregate nodes with member-role, snapshot, decision, claim, query, and evidence edges.

The payload must not copy an opaque native v4 bundle. Decode reconstructs the logical v4 records, validates identity closure and snapshot freshness, validates the aggregate, and then executes the query.

## Frozen diagnostic set

`artifacts/identity-memory-experiment/gold-v1/` contains four dev and four hidden hand-authored scenarios:

1. shared strong identifier across aliases;
2. same name but different entities;
3. rename with stable identity;
4. unresolved alias abstention;
5. explicit erroneous-merge rejection;
6. split correction superseding an earlier merge;
7. four evidence mentions resolving to two entities;
8. unrelated identity changes outside aggregate scope.

This is a deterministic contract/execution diagnostic, not an automatic entity-linking benchmark. Hidden labels are frozen before implementation to prevent post-result gate editing, but the hand-authored decision inputs are not claimed to be model-blind.

## Pre-registered gates

The wave passes only if all gates pass on the first frozen run:

- critical false merge count: `0`;
- answerable `count_distinct` value exact: `100%`;
- required evidence set exact: `100%`;
- unresolved-identity abstention correctness: `100%`;
- split/supersession revision correctness: `100%`;
- identity closure freshness and recomputation parity: `100%`;
- native v4 exact round-trip: `100%`;
- Extended-AMR v3 exact round-trip and query parity: `100%`;
- structural fallback trigger rate: `0`;
- frozen v3/v5 LongMemEval abstention regression remains unchanged.

Any failed hidden gate keeps `identity_authoritative_ready=false`. A pass authorizes a larger natural identity slice or model-based identity proposal experiment; it does not establish product superiority or final storage selection.

## Failure controls

| Failure | Control |
| --- | --- |
| Same label causes false merge | Labels are weak candidates; require accepted evidence-backed decision |
| `schema:sameAs` copied as local equality | Accept only typed external URL evidence under local policy |
| Old erroneous merge contaminates counts | Superseding split decision and fresh snapshot required |
| Aggregate hides unresolved members | Exact member units and canonical entities are mandatory |
| Adapter preserves data but changes behavior | Query parity and frozen correctness gates run after decode |
| Dense similarity decides identity | Embedding may propose candidates only; it cannot accept a decision |
| Unrelated revision invalidates everything | Fingerprints are scoped to decision and aggregate dependencies |

## Result boundary

This wave measures identity-contract completeness, correction-safe deduplication, aggregate execution, evidence closure, and carrier parity. It does not measure automatic identity proposal quality, end-to-end user experience, full LongMemEval accuracy, or superiority over Mem0, Graphiti, Hindsight, MemPalace, or other systems.
