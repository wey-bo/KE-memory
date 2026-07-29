# Typed Extractor V2 L1 Dev Proposer Contract V2

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
- `modality` is one of the allowed public vocabulary values.
- `polarity` is one of the allowed public vocabulary values.
- Local entity IDs are candidate-local, contiguous, ordered exactly
  `entity-01`, `entity-02`, and so on. Do not add entity types or global IDs.
- Every role contains `role`, `role_name`, and `local_entity_id`. Every role,
  condition, and scope local reference must resolve to `local_entities`.
- `time` always exists. Use only strings supported by public text; leave an
  unresolved `event_time` or `valid_time` null rather than guessing.
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
