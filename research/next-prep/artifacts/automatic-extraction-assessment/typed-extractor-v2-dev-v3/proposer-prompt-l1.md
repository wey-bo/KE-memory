# Typed Extractor V2 L1 Dev Proposer Contract V4

You are a fresh proposer with no inherited conversation history.

## Allowed Input

Read only the frozen `public-l1.json` supplied by the dispatch request. Do not
read or infer from authority, gold, manifests, source cases, prior proposals,
reports, scorer code or output, historical error analysis, or any other file.

## Output Metadata

Write one JSON object to the temporary output path supplied by the dispatch
request. Use these exact top-level keys and no others:

- `schema_version`: exactly `typed-extractor-l1-proposals-v1`
- `dataset_id`: copy exactly from public input
- `run_id`: copy exactly from the dispatch request
- `proposer_id`: copy exactly from the dispatch request
- `proposer_version`: copy exactly from the dispatch request
- `case_count`: copy exactly from public input
- `proposals`: exactly one record for every public case

Each proposal record uses exactly these keys:

"confidence" "case_id" "candidate_ref" "decision" "typed_candidate" "reason_code"

`case_id` and `candidate_ref` must be copied from the same public case.
`confidence` is required for every decision and must be a number from 0 through
1. `reason_code` must be a concise snake_case code based only on public input.

## Decisions

- `emit_l1`: public evidence supports a complete typed L1 candidate.
- `abstain`: the record may be memory-worthy, but a required semantic field
  cannot be resolved without unsupported inference.
- `no_memory`: the record is only a question, conversational control, or other
  content that should not become a memory candidate.

For `abstain` and `no_memory`, `typed_candidate` must be null. For `emit_l1`,
`typed_candidate` must use the exact object contract below.

## Exact Typed Candidate Contract

Use every key shown below and no additional keys. Replace example values using
only the public case. Empty lists and null time values are valid when supported.

```json
{
  "kind": "event",
  "predicate": {
    "surface": "public predicate surface",
    "sense": "precise predicate sense",
    "canonical_operator": "canonical_operator_name"
  },
  "local_entities": [
    {
      "local_entity_id": "entity-01",
      "surface": "publicly supported surface"
    }
  ],
  "roles": [
    {
      "role": "semantic_role",
      "role_name": "human-readable role name",
      "local_entity_id": "entity-01"
    }
  ],
  "modality": "actual",
  "polarity": "positive",
  "time": {
    "event_time": null,
    "valid_time": null
  },
  "condition_bindings": [
    {
      "operator": "condition operator",
      "value": "publicly supported condition",
      "local_entity_ids": ["entity-01"]
    }
  ],
  "scope_bindings": [
    {
      "operator": "scope operator",
      "value": "publicly supported scope",
      "local_entity_ids": ["entity-01"]
    }
  ],
  "derivation": {
    "method": "explicit",
    "basis": null,
    "evidence_ids": ["evidence-id-copied-from-public"]
  },
  "evidence_bindings": [
    {
      "evidence_id": "evidence-id-copied-from-public",
      "speaker": "user"
    }
  ],
  "lifecycle": {
    "lifecycle": "active",
    "replacement_candidate_ref": null,
    "replaces_candidate_refs": [],
    "supersedes_candidate_refs": [],
    "conflicts_with_candidate_refs": []
  },
  "operation_provenance": {
    "confirmed_by_operation_refs": [],
    "added_by_operation_refs": []
  }
}
```

The exact nested contract keys include:

"local_entities" "local_entity_id" "role_name" "time" "condition_bindings" "scope_bindings" "derivation" "evidence_bindings" "lifecycle" "operation_provenance"

## Semantic And Reference Rules

- `kind` is one of `event`, `state`, `preference`, `task`, or `attribute`.
- `predicate.canonical_operator` must be copied exactly from the public
  `canonical_operators` catalog. `predicate.sense` must be copied exactly from
  the public `predicate_senses` catalog. Select by meaning; if no catalog entry
  fits without semantic distortion, abstain.
- After selecting the canonical operator, set `kind` from the matching public
  `operator_kind_bindings` entry. Kind describes the canonical proposition,
  not whether its modality is planned, requested, actual, or hypothetical.
- Each `role` and `role_name` pair must be copied exactly from a public
  `operator_role_bindings` entry whose first component matches the selected
  canonical operator. Split only at `|`, omit the operator component from the
  output, and include every participant or value required by that operator.
  The display role name describes the bound entity, not the overall action.
- `modality` is one of the allowed public vocabulary values and must follow the
  public `modality_policy`. In particular, a complete explicit causal
  hypothesis may use `possible_causal_hypothesis|hypothetical`, while a generic
  possibility or classification with no supported typed modality must abstain
  with reason code `unsupported_source_modality`. Do not silently convert every
  public `possible` qualifier to `hypothetical`.
- `polarity` is one of the allowed public vocabulary values.
- Local entity IDs are candidate-local, contiguous, ordered exactly
  `entity-01`, `entity-02`, and so on. Do not add entity types or global IDs.
  Always copy local entity surfaces exactly from public subject, object, or an
  explicit participant mention inside a public qualifier. Never put an
  ISO-normalized value in a local entity surface.
- Every role contains `role`, `role_name`, and `local_entity_id`. Every role,
  condition, and scope local reference must resolve to `local_entities`. A
  qualifier clause is not automatically a local entity: qualifier bindings
  reference the participant entities mentioned inside the clause. Only use the
  whole qualifier clause as an entity when the clause itself is the semantic
  referent. Every explicit participant mentioned inside a condition must have a
  local entity and must appear in that condition's `local_entity_ids` even when
  it has no predicate role.
- Condition operators must be copied exactly from public
  `condition_operators`; scope operators must be copied exactly from public
  `scope_operators`. Do not emit generic operator names such as `condition` or
  `scope` when the catalogs specify `when` or `applies_to`.
- `time` always exists. Use only strings supported by public text; leave an
  unresolved `event_time` or `valid_time` null rather than guessing. Follow the
  public `time_policy`: normalize a fully resolved calendar date to ISO-8601
  `YYYY-MM-DD`; an `unresolved_deictic_time` such as a speaking-day reference
  with no recoverable calendar date must remain null and must not be copied as
  raw text. Apply any matching public `operator_time_bindings`: a time-anchor
  assertion writes the normalized object date to `valid_time`, while the local
  date entity surface remains exact source text.
- `derivation.method` is `explicit`, `context_completed`, or `inferred`.
  Explicit derivation requires null `basis`; non-explicit derivation requires a
  concise non-null basis. Its evidence IDs must also appear in
  `evidence_bindings`.
- Evidence IDs and speakers must be copied exactly from the public case.
- Lifecycle candidate refs and confirm/add operation refs may only be copied
  from the same public case. Preserve supplied lifecycle and operation
  provenance exactly when emitting.
- Do not create authoritative unit IDs, source revision IDs, revision numbers,
  closure IDs, identity decisions, membership decisions, transaction times, or
  automatic-write claims.
- Do not use embeddings, lexical similarity, WordNet, schema.org,
  Extended-AMR, or KEOL as factual or identity authority.

Before finishing, parse the staged JSON and verify exact metadata, all required
keys, no extra keys, 100 percent case coverage, confidence bounds, contiguous
local IDs, closed references, allowed vocabularies, and public-only evidence,
lifecycle, and operation references. Emit JSON only.
