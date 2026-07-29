# L1 Ontology Linking and Admission Design

Status: approved implementation boundary for the independent dev-v1 diagnostic.

## Goal

Add a representation-independent middle layer between `TypedL1Candidate` and any
authoritative L1 revision:

```text
TypedL1Candidate
  -> versioned local ontology linking proposals
  -> LinkedL1Candidate
  -> deterministic admission
  -> AdmissionDecision and proposed revision action
```

This wave does not create `MemoryUnitRevision`, mutate identity state, connect L2,
create fresh-hidden data, select a physical representation, or modify any extractor,
query, identity, authority, shared CLI, or frozen artifact.

## Alternatives

### Modify `TypedLocalEntity`

Rejected. Adding `concept_ids`, canonical identity, or ontology revision to the frozen
extractor model would change the Local L1 proposal contract and collide with the active
fresh-v3 track.

### Reuse identity records as the linking schema

Rejected. `identity_resolution.py` has useful precedent, but its registry is scoped to
identity and aggregate diagnostics. Reusing it directly would couple lexical sense
selection to identity authority and still would not represent unresolved concept
candidates, provisional ontology extension proposals, or predicate-role constraints.

### Independent linking and admission wrapper

Selected. The wrapper preserves the original candidate byte-for-byte in a linked
envelope, uses a separate local ontology registry, consumes identity records only as
explicit admission inputs, and never writes authority state.

## Local ontology registry

`OntologyRegistry` is a deterministic, local, versioned schema input. It contains:

- stable local `concept_id` values and parent relationships;
- aliases used only for candidate generation;
- versioned WordNet 3.0 and schema.org 30.0 advisory mappings;
- local predicate-sense/operator constraints by semantic role;
- `registry_id`, `version`, `revision`, and a canonical `registry_hash`.

The dev-v1 registry includes `memory:Entity`, `memory:Person`,
`memory:Consumable`, `memory:Ingredient`, `memory:Beverage`,
`memory:TeaBeverage`, `memory:CoffeeBeverage`, `memory:MilkBeverage`, and
`memory:DairyIngredient`. The executable hierarchy includes:

```text
memory:Beverage
  <- memory:TeaBeverage
  <- memory:CoffeeBeverage
  <- memory:MilkBeverage

memory:Ingredient
  <- memory:DairyIngredient
```

Every external mapping is explicitly advisory-only and carries source, version,
external ID, relation, and authority flags fixed to false. A WordNet synset or
schema.org term can support a candidate, but cannot establish a local fact, mint a
canonical ID, merge identities, or authorize admission.

Registry validation rejects duplicate concepts, missing parents, cycles, duplicate
rules, unknown rule concepts, and a mismatched canonical registry hash. Subtype closure
is computed only over local concept IDs.

## Linking records

The new layer defines the required public records:

- `ConceptLinkProposal`: selected or unresolved local concept candidates, context and
  role basis, advisory mappings, and optional extension proposal.
- `EntityLinkProposal`: category versus individual interpretation, local concept types,
  optional externally supplied canonical entity ID, identity status, and candidates.
- `PredicateLinkProposal`: exact binding of source predicate surface, sense, canonical
  operator, matching local rule, and evidence.
- `LinkedL1Candidate`: the original `TypedL1Candidate`, its canonical hash, the complete
  link proposals, exact `EvidenceSpanV2` values, unresolved candidates, registry
  version/revision/hash, and its own canonical hash.
- `AdmissionDecision`: `accept`, `reject`, or `abstain`, deterministic reasons, all input
  hashes and evidence bindings, and a non-writing proposed revision action.

All link evidence identifies an `EvidenceSpanV2` and records a finite basis such as
predicate-role compatibility, local alias, demonstrative instance reference, or
external advisory candidate. Link evidence is not a replacement for raw evidence.

Unknown terms produce a `ProvisionalConceptExtensionProposal` with a proposal ID,
surface, context, and suggested existing parents. The proposal has no field capable of
holding a new canonical concept ID. It therefore cannot pretend that an extension has
already been admitted.

## Category and instance semantics

A role can denote a category or an individual:

- `prefer(theme=coffee)` links the value to the local
  `memory:CoffeeBeverage` concept. It has no canonical entity ID.
- `drink(theme=this cup of coffee)` links the mention to an individual only when the
  caller supplies a resolved canonical entity record. Its type includes
  `memory:CoffeeBeverage`. The cup/container reading is recorded as context and is not
  treated as a lexical alias for coffee.
- `drink(theme=milk)` selects `memory:MilkBeverage`.
- `add_ingredient(theme=milk, destination=coffee)` selects
  `memory:DairyIngredient` for the theme and `memory:CoffeeBeverage` for the
  destination.

The same surface is never resolved by string match alone. Candidate generation first
finds local lexical candidates, then applies predicate sense, canonical operator, role,
and local subtype constraints. If these do not select exactly one admissible local
concept, the result remains unresolved or becomes an extension proposal.

Canonical entity IDs are never generated by the linker. An individual proposal may
only repeat an ID from an explicit `CanonicalEntityBinding` supplied by a caller. Missing
or mismatched identity evidence remains unresolved and causes admission to fail closed.

Local alias matching is exact after case and whitespace normalization. The only dev-v1
multi-token reduction is the explicit demonstrative container form `this|that|the cup
of <exact alias>`. Residual modifiers, negation, possessives, and unknown compounds such
as `mystery coffee`, `almond milk`, `not coffee`, or `my coffee` remain unresolved.

## Deterministic admission

Admission consumes a `LinkedL1Candidate`, the exact current `OntologyRegistry`, and an
`AdmissionContext`. The context binds source revisions, canonical entity bindings,
epistemic source, transaction time, known lifecycle targets, and a versioned policy.
It also carries the referenced `RawArtifactRevision` values so the decision can pin the
artifact content hash through source revision to evidence span. Canonical entity bindings
pin an identity snapshot ID/revision/hash plus identity registry revision/hash. Admission
also requires the complete current `IdentitySnapshotAuthority`, recomputes its hash, and
checks canonical membership and concept types. A naked entity ID or self-declared
`resolved` flag is not trusted. `SourceEpistemicBinding` pins speaker and source status to
each exact source revision, preventing assistant or tool evidence from being relabeled as
user-reported.

Checks run in this order:

1. Recompute the source candidate, linked envelope, and registry hashes. Re-run the
   deterministic linker over the exact candidate, registry, evidence, and identity
   inputs and require the entire linked envelope to match.
2. Verify exact evidence closure: evidence IDs and speakers match the source candidate;
   every span quote hash is correct; every span coordinates exactly into a supplied
   `SourceRecordRevision`; every source revision points to a supplied raw artifact
   revision; every link cites a bound span.
3. Require an exact predicate rule and local predicate-role-type compatibility using
   subtype closure.
4. Reject external-only or nonexistent local concept IDs and advisory mappings used as
   authority.
5. Require category/individual shape consistency and fresh resolved identity evidence
   for every individual.
6. Check modality and polarity under policy. Hypothetical preferences abstain; the
   modality is never silently upgraded to actual.
7. Check source epistemics and speaker compatibility. Agent-generated content cannot be
   promoted to a real-world fact by this layer.
8. Check event/valid time shape and require a valid transaction time without inventing
   missing event time.
9. Check lifecycle, conflict, correction, and supersession references against the
   supplied known-revision set.
10. Return a decision and proposed action without invoking an authority constructor or
    persistence API.

Invalid or tampered bindings are `reject`. Incomplete but potentially resolvable input,
including ambiguity, extension-required concepts, hypothetical modality, unresolved
identity, or missing lifecycle targets, is `abstain`. A complete input is `accept`.

The proposed action is one of `create`, `correction`, `lifecycle_update`, or `none`.
It contains no committed revision ID and has `automatic_write=false`.

## Determinism and replay

Canonical hashes use the existing canonical JSON encoding. List ordering is normalized
where order is not semantic, while source local-entity order remains unchanged. The
linked envelope embeds the exact source candidate and evidence spans; replay additionally
requires the registry and admission context whose hashes/revisions are recorded in the
decision. `admission_context_hash` covers the full policy, source epistemics, raw/source
revisions, identity authority records, lifecycle targets, registry bindings, and
transaction time. Non-semantic collections are sorted before hashing; local-entity order
remains semantic.

Running linking and admission twice on identical logical inputs must produce identical
Pydantic values and canonical bytes.

## Diagnostic assessment

The dev-v1 authored diagnostic contains no fresh-v2/v3 hidden content or identifiers.
It covers:

1. preference for coffee as a concept;
2. drinking a specific cup as an individual typed CoffeeBeverage;
3. drinking milk as MilkBeverage;
4. adding milk to coffee as DairyIngredient plus CoffeeBeverage;
5. a hypothetical preference that must abstain;
6. an unknown drink that requires an ontology extension proposal and must abstain;
7. the same `milk` surface under different predicate senses;
8. an individual whose identity remains unresolved and must abstain.

The assessment reports linking exact match, hierarchy consistency, sense accuracy,
decision exact match, abstention correctness, critical false admission count, evidence
exact match, and the
automatic L1/L2/identity/membership/closure/revision/snapshot/aggregate write counts.
The write counts must all be zero.

## Result boundary

A passing dev diagnostic proves only deterministic contract behavior on authored cases.
It does not authorize pipeline integration, fresh-hidden creation, authoritative writes,
L2 consumption, final representation selection, product claims, or comparison claims
against external memory systems.
