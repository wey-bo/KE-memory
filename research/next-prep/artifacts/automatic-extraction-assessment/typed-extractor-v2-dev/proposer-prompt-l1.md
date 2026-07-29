# Typed Extractor V2 L1 Dev Proposer

Read only the frozen `public-l1.json` supplied with this prompt. Do not read or infer from authority, gold, manifests, prior proposals, reports, scorer output, historical error analysis, or any other file.

Return one JSON object with schema version `typed-extractor-l1-proposals-v1`. Copy the dataset ID, case count, case IDs, and candidate refs exactly. Supply the run ID, proposer ID, and proposer version specified by the dispatch request.

For every case choose exactly one decision:

- `emit_l1`: the public evidence supports a complete typed L1 candidate.
- `abstain`: the record may be memory-worthy, but a required semantic field cannot be resolved without unsupported inference.
- `no_memory`: the record is only a question, conversational control, or other content that should not become a memory candidate.

For `emit_l1`, include every field required by the public contract:

- kind: `event`, `state`, `preference`, `task`, or `attribute`;
- predicate surface, precise sense, and canonical operator;
- contiguous candidate-local IDs `entity-01`, `entity-02`, ... in first-use order;
- closed role, condition, and scope references to those local IDs;
- modality and polarity from the allowed vocabulary;
- event/valid time, leaving unresolved values null rather than guessing;
- typed derivation provenance and exact evidence IDs/speakers;
- exact lifecycle candidate refs and confirm/add operation refs supplied by public input.

Do not create global entity IDs, authoritative unit IDs, source revision IDs, revision numbers, closure IDs, identity decisions, membership decisions, transaction times, or automatic-write claims. Do not use embeddings, lexical similarity, WordNet, schema.org, Extended-AMR, or KEOL as factual or identity authority.

For `abstain` and `no_memory`, set `typed_candidate` to null. The reason code must be concise and must not encode hidden labels. Emit JSON only.
