# QuerySlotPlan Automatic Compiler Design

## Status and boundary

This design implements the user-approved boundary: the query compiler produces an
executable retrieval plan, evidence requirements, and explicit abstention. Natural-language
answer generation remains a downstream consumer and cannot repair or conceal compiler or
evidence-closure failures.

The compiler does not replace the existing `QuerySlotPlan`, `AuthoritativeQueryPlan`,
symbolic executor, identity resolver, or representation adapters. It adds a versioned,
representation-neutral compiler layer and lowers simple plans into the existing authoritative
query contract. Native, Extended-AMR, KEOL, relational, graph, lexical, and vector projections
remain physical execution profiles rather than query authorities.

All compiler outputs are non-authoritative plans. A deterministic gate is the only component
that can mark a plan executable. Embeddings may recover lexical/entity candidates, but cannot
bind identities, assert facts, resolve conflicts, perform counts, or produce final answers.

## Recommended architecture

Use a staged hybrid compiler:

```text
natural query + query context
  -> QueryDraft producer
  -> deterministic entity/predicate/time linker
  -> typed query AST
  -> deterministic QueryPlan gate
  -> CompiledQueryPlanV2 or explicit abstention
  -> symbolic execution against an authoritative Git memory ref
  -> evidence closure verification
  -> guarded lexical/entity fallback when allowed
  -> evidence bundle or abstention
```

The draft producer may be an LLM, but it only emits surface mentions, answer intent, variables,
predicate/role candidates, and unresolved slots. It cannot emit accepted stable entity IDs or
claim that a plan is executable. The program binds stable IDs from versioned registries and
records every resolution decision.

## Query context and version binding

Every compilation binds:

- the raw query and query time;
- the current speaker/user identity when available;
- an authoritative Git memory ref;
- ontology and identity-registry revisions;
- compiler policy and producer versions.

Event time, valid time, transaction time, and the Git memory ref remain distinct. Replaying the
same accepted plan against the same ref and registry revisions must be deterministic.

## Compiler-side data model

`QueryDraftV1` contains:

- raw question and intent candidate;
- target L1/L2 level candidate;
- answer kind and answer variable;
- surface predicate and entity mentions with exact character spans;
- pattern groups expressed with variables, not stable IDs;
- time, modality, polarity, lifecycle, source, conflict, and supersession candidates;
- explicitly unresolved slots;
- producer provenance.

`CompiledQueryPlanV2` contains:

- a closed answer specification;
- one or more OR pattern groups, each containing AND atoms;
- typed terms: stable entity, variable, or literal;
- predicate sense and canonical operator per atom;
- typed role bindings;
- exact temporal filters and latest/current ordering;
- lifecycle, source, modality, polarity, conflict, and supersession policies;
- aggregation and distinct-identity policy;
- evidence/closure policy;
- fallback policy;
- memory, ontology, identity, and compiler revision bindings;
- a deterministic plan hash.

Shared variables across atoms express graph traversal. OR is represented as multiple pattern
groups. This avoids embedding a database-specific graph query language in the canonical plan.

## Deterministic gate

The gate rejects or abstains when:

- any structural slot, predicate sense, canonical operator, or required entity is unresolved;
- the answer variable is already bound by the question;
- a role violates the linked predicate's domain/range policy;
- a count lacks `distinct_by=canonical_identity`;
- any counted identity remains unresolved;
- a latest/current query lacks valid-time ordering and lifecycle policy;
- explicit absence is inferred from an empty match rather than an absence closure;
- conflict or supersession semantics are unspecified where required;
- a multi-hop variable is disconnected or only appears once without being the answer;
- structural reasoning is delegated to embedding fallback;
- the plan is not bound to a memory ref and registry revisions.

Lexical predicate and entity-alias gaps may produce a blocked plan with
`fallback_allowed=true`. Structural, temporal, identity, conflict, modality, answerability, and
evidence-closure gaps always block fallback.

## V1 lowering

A V2 plan may lower to the existing `AuthoritativeQueryPlan` only when it has one conjunction
group, one atom, no OR, no multi-hop variable, no aggregation other than the already supported
count, and no unsupported ordering or absence policy. Lowering must preserve entity IDs,
predicate sense, operator, roles, time, modality, polarity, source status, lifecycle, closure
reference, answer kind, and fallback restrictions.

Complex V2 plans remain V2 and are executed by a later representation-neutral AST executor.
Adapters must demonstrate result, evidence, abstention, and round-trip parity before a physical
profile can claim support.

## Initial query families

The first compiler qualification covers:

1. single fact and role lookup;
2. current/latest state;
3. count-distinct with identity safety;
4. AND and OR;
5. multi-hop shared-variable traversal;
6. conflict and supersession;
7. evidence completeness and unanswerable/explicit-absence queries.

## Evaluation

Raw producer quality and deterministic gate safety are reported separately. Metrics include:

- draft schema validity and coverage;
- answer-kind, predicate, role, entity, time, modality, polarity, lifecycle, and source accuracy;
- pattern/variable and multi-hop exactness;
- unresolved-slot and fallback-reason accuracy;
- plan executable/abstain decision accuracy;
- critical false executable-plan count;
- execution denotation and Evidence Set Exact Match;
- evidence closure, abstention, and representation parity;
- deterministic replay at a fixed Git ref.

Development fixes may only use dev/diagnostic queries. A fresh-hidden compiler gate must freeze
the prompt, policy, registries, thresholds, scorer, and code hashes before hidden queries and
gold plans are created.

## Non-goals for the first implementation

- natural-language answer generation;
- automatic memory writes or identity decisions;
- database-specific SQL, Cypher, SPARQL, or vector query generation;
- unrestricted ontology expansion from query text;
- direct embedding answers;
- selection of the final physical memory representation.

