# Natural Identity Proposal-Only Contract

You are a fresh proposer with no inherited conversation history.

## Allowed input

Read exactly this dataset file and no other workspace file:

`/public/home/wwb/KE-mem/KE-memory-next-prep-20260727/artifacts/identity-memory-experiment/natural-v4-fresh/public.json`

Do not read or inspect directories, source cases, mappings, preregistration, authority, gold, prior model runs, scorer code, scorer outputs, reports, plans, or documentation. The restriction is part of the experiment.

## Frozen decision policy

Policy SHA-256: `788f174a9644a3375783e7f31f3f55c0a95aa8ab27d302a96cd34d2b7d0c6de6`

# Identity Proposal Policy v4.1

Use only the public case fields and quoted evidence. These proposals are candidates, not authoritative writes.

## Identity

- Evaluate identity in this order: first look for an authorized `merge` trigger, then an authorized `keep_distinct` trigger, and otherwise `abstain`.
- Propose `merge` only when the public evidence explicitly says the mentions are the same entity, both mentions have the same non-null source actor binding for a person, trusted identifiers explicitly match, or direct anaphoric/possessive wording unambiguously names one object.
- Direct anaphoric/possessive continuity requires observable coreference wording in the quoted evidence, such as a pronoun, possessive, `same`, or another explicit reference whose antecedent is unique. Repeated definite descriptions, occurrence in one source item, or related repository/application/branch context do not establish coreference.
- When mentions occur in different evidence units and have null actor bindings, abstain unless the quotes explicitly state same identity, share a trusted identifier, or contain the observable unambiguous coreference wording above.
- Do not use `direct_anaphoric_continuity` as a reason code unless that observable wording is present in the cited quotes.
- Same source item, thread, topic, concept type, lexical similarity, software stack, or repository/application context alone is insufficient for `merge`.
- Propose `keep_distinct` only when public evidence contains incompatible non-null source actor bindings, incompatible trusted identifiers stated in the quotes, or an explicit statement that the entities are distinct.
- Differences in surface, role, class, title, format, or time alone are insufficient for `keep_distinct` when both mentions could still denote one entity.
- If neither the positive nor negative identity condition is established, propose `abstain`.

## Membership

- Before semantic fallback, compare the public `query_subject_id` with every required mention's public `source_actor_id`.
- If the query subject and the required mention actor are both non-null and exactly equal, propose `include`; do not abstain from that exact match.
- If the query subject and the required mention actor are both non-null and unequal, propose `exclude`; do not abstain from that exact mismatch.
- When actor bindings are null, mixed across required mentions, or otherwise unavailable, propose `include` only when the public evidence explicitly binds the mentioned item to the query subject, including an explicit requested-member statement.
- A requested-member statement is explicit when the public question asks whether the named member is requested for the named group and the cited quote uses an imperative or request verb such as `include`, `add`, or `create` for that same member surface. The quote need not repeat the group name when the public case supplies that group context.
- Under the same null, mixed, or unavailable conditions, propose `exclude` only when the public evidence explicitly binds the mentioned item to a different subject or explicitly states non-membership.
- Topic relevance, shared context, lexical similarity, or embedding-like similarity is insufficient for membership.
- If neither inclusion nor exclusion is established, propose `abstain`.

## Evidence and confidence

- Cite every case-local mention used by the decision and no mention from another case.
- A non-abstain action requires direct public evidence satisfying the corresponding rule.
- Use calibrated confidence. Do not use high confidence to compensate for missing identity or membership evidence.

## Output

Write proposal JSON to:

`/public/home/wwb/KE-mem/KE-memory-next-prep-20260727/.tmp/identity-proposer-stage/run-20260728T031000Z-claude-sonnet-4-6-fresh-policy-v4-1/proposals.json`

Use this exact run metadata:

- `schema_version`: `natural-identity-proposals-v1`
- `run_id`: `run-20260728T031000Z-claude-sonnet-4-6-fresh-policy-v4-1`
- `proposer_id`: `claude-sonnet-4-6`
- `proposer_version`: `2026-07-28-policy-v4.1`
- `dataset_id`: copy exactly from public input
- `case_count`: `6`

The top-level object contains `schema_version`, `dataset_id`, `run_id`, `proposer_id`, `proposer_version`, `case_count`, and `proposals`.

Each proposal contains exactly `case_id`, `relation_kind`, `action`, `confidence`, `evidence_mention_ids`, `reason_code`, `proposer_id`, `proposer_version`, and `run_id`. For identity, action is `merge`, `keep_distinct`, or `abstain`. For membership, action is `include`, `exclude`, or `abstain`. Evidence IDs must belong to the same public case. Produce exactly one proposal per public case with no duplicates or omissions.

Use only public semantic evidence. Do not infer meaning from opaque IDs or the dev/hidden split. Before finishing, parse the output and verify schema, metadata, coverage, action families, confidence bounds, and evidence IDs. Do not include commentary or Markdown in the JSON file.
