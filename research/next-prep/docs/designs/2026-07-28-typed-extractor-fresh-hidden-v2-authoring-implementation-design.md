# Typed Extractor Fresh-Hidden V2 Authoring Implementation Design

## Status

Approved under the user's standing direction to execute subsequent stages
according to the agent's design without intermediate confirmation. This design
is recorded before the authoring module, test, implementation receipt, formal
evaluation root, hidden artifacts, or model request exists.

## Goal

Implement and freeze the exact deterministic authoring mechanism required by
the current fresh-hidden v2 preregistration while the formal evaluation root
remains absent. This stage proves the mechanism and its tests; it does not
materialize hidden source/public/authority/gold artifacts or call a model.

## Alternatives

1. Freeze only an empty authoring API. Rejected because it would not bind the
   actual 36-case semantic composition before hidden materialization.
2. Generate formal hidden files together with the implementation. Rejected
   because it collapses the preregistered implementation-receipt chronology.
3. Store all blueprints in a pure module, validate them in memory, and freeze a
   receipt before any formal hidden file exists. Selected because the exact
   content and semantics are hash-bound without prematurely creating the
   evaluation dataset.

## Architecture

`typed_extractor_fresh_v2_authoring.py` owns strict blueprint models, 24 L1
blueprints, 12 L2 blueprints, deterministic opaque IDs, in-memory rendering,
prior-data contamination checks, and receipt freeze/validation. It does not
provide a formal-evaluation write function in this stage.

The public validation seam is
`validate_fresh_v2_authoring_bundle(bundle, preregistration_path)`. Tests use
this seam with copied immutable bundle values; they do not mutate module-global
blueprint or path registries. The bundle includes the exact prereg input hashes
and a derived prior inventory so contamination enforcement is observable
without persisting hidden artifacts.

The L1 families and counts are exactly `explicit_event_roles`,
`condition_scope`, `modality_time`, `lifecycle_revision`,
`derivation_epistemic`, and `abstention_no_memory_controls`, four each. The L2
families are exactly `coreference_task_composition`,
`preference_state_aggregation`, `lifecycle_supersession`,
`multi_evidence_closure`, `abstraction_structured_claim_boundary`, and
`abstention_unresolved_controls`, two each. Every blueprint is used in stable
family/ordinal order. There is no random seed, selection, replacement, semantic
filter, or resampling path.

The renderer returns strict existing L1/L2 source, public, authority, gold, and
manifest models in memory. Public payloads exclude private family labels,
expected decisions, typed gold, authority, and exclusion inventories. Opaque
case/candidate/evidence/support/turn/session references derive from the frozen
namespace and private key using SHA-256.

## Validation And Contamination

The module validates evidence quotes and offsets, typed role/entity closure,
L1 derivation/lifecycle/operation provenance, L2 support/claim/closure/source
coverage, public/private ID parity, and exact family distribution. It builds a
prior inventory from the 47 preregistered dev, diagnostic, and fresh-v1 inputs
and rejects overlap in private/public IDs, evidence IDs, exact normalized source
text, or normalized semantic signatures.

Normalization is deterministic: Unicode NFKC, case-folding, whitespace
collapse, and stable canonical JSON for structured semantics. Semantic
signatures omit opaque IDs and evidence references but retain decision,
predicate/operator, roles/entities, qualifiers, time/lifecycle, L2 claims,
abstraction, and closure semantics.

## Implementation Receipt

`authoring-implementation-receipt.json` is written only under the current
prereg-v3 root. It is a strict immutable artifact binding:

- the prereg-v3 path, schema, SHA-256, mode, and frozen evaluation ID;
- authoring module and test SHA-256 values;
- relevant L1/L2 schema and IO dependency hashes;
- L1/L2 blueprint-manifest hashes and exact family/count contracts;
- the formal evaluation root and all expected hidden/model paths as absent;
- zero model requests and zero automatic memory, identity, membership,
  closure, revision, source-revision, snapshot, or aggregate writes.

Receipt time is a caller-supplied untrusted UTC label. Chronology evidence is
filesystem presence/absence plus SHA-256, not an external trusted timestamp.
The receipt writer fails if the prereg file is not the exact current read-only
artifact, if code/tests drift, if the receipt already differs, or if the formal
evaluation root or a model-run path exists.

## Testing

Tests first fail because the authoring module does not exist. Green tests cover
strict blueprint validation, exact family/order/counts, deterministic rendering,
public/private separation, evidence and reference closure, contamination
rejection, no formal writes, strict receipt schema, impossible timestamps,
hash drift, premature evaluation artifacts, immutable mode `0444`, and receipt
validation parity.

## Boundaries

- No formal hidden source/public/authority/gold/manifest or chronology file is
  created in this stage.
- No proposer/model request runs, and no API credential is read or persisted.
- The existing prereg-v2/v3 artifacts and protected candidate/guard artifacts
  remain byte-identical.
- No L1/L2, revision, source-revision, closure, identity, membership, snapshot,
  or aggregate write is authorized.
- `LONGMEMEVAL-6d550036` remains `structured_l2_identity_unresolved`.
- Passing the implementation-receipt gate authorizes only one-time formal
  hidden materialization in the next stage, not proposer execution or pipeline
  integration.
