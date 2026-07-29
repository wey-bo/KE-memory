# Natural Identity Proposal-Only Contract

You are a fresh proposer with no inherited conversation history.

## Allowed input

Read exactly this dataset file and no other workspace file:

`/public/home/wwb/KE-mem/KE-memory-next-prep-20260727/artifacts/identity-memory-experiment/dev-repair-v3/public.json`

Do not read or inspect directories, source cases, mappings, preregistration, authority, gold, prior model runs, scorer code, scorer outputs, reports, plans, or documentation. The restriction is part of the experiment.

## Frozen decision policy

Policy SHA-256: `c0efc9a8a3919618e6074137f464b1178267b075d262244565bd63adf05dc476`

# Identity Proposal Policy v1

Use only the public case fields and quoted evidence. These proposals are candidates, not authoritative writes.

## Identity

- Propose `merge` only when the public evidence explicitly says the mentions are the same entity, both mentions have the same non-null source actor binding for a person, or direct anaphoric/possessive continuity unambiguously names one object.
- Same source item, thread, topic, concept type, lexical similarity, or repository/application context alone is insufficient for `merge`.
- Propose `keep_distinct` only when public evidence contains incompatible non-null source actor bindings, incompatible trusted identifiers stated in the quotes, or an explicit statement that the entities are distinct.
- Differences in surface, role, class, title, format, or time alone are insufficient for `keep_distinct` when both mentions could still denote one entity.
- If neither the positive nor negative identity condition is established, propose `abstain`.

## Membership

- Propose `include` when the public evidence explicitly binds the mentioned item to the query subject, including a matching non-null source actor binding or an explicit requested-member statement.
- Propose `exclude` when the public evidence explicitly binds the mentioned item to a different subject or explicitly states non-membership.
- Topic relevance, shared context, lexical similarity, or embedding-like similarity is insufficient for membership.
- If neither inclusion nor exclusion is established, propose `abstain`.

## Evidence and confidence

- Cite every case-local mention used by the decision and no mention from another case.
- A non-abstain action requires direct public evidence satisfying the corresponding rule.
- Use calibrated confidence. Do not use high confidence to compensate for missing identity or membership evidence.

## Output

Write proposal JSON to:

`/public/home/wwb/KE-mem/KE-memory-next-prep-20260727/.tmp/identity-proposer-stage/run-20260727T151500Z-claude-sonnet-4-6-dev-policy-v2/proposals.json`

Use this exact run metadata:

- `schema_version`: `natural-identity-proposals-v1`
- `run_id`: `run-20260727T151500Z-claude-sonnet-4-6-dev-policy-v2`
- `proposer_id`: `claude-sonnet-4-6`
- `proposer_version`: `2026-07-27-policy-v2`
- `dataset_id`: copy exactly from public input
- `case_count`: `6`

The top-level object contains `schema_version`, `dataset_id`, `run_id`, `proposer_id`, `proposer_version`, `case_count`, and `proposals`.

Each proposal contains exactly `case_id`, `relation_kind`, `action`, `confidence`, `evidence_mention_ids`, `reason_code`, `proposer_id`, `proposer_version`, and `run_id`. For identity, action is `merge`, `keep_distinct`, or `abstain`. For membership, action is `include`, `exclude`, or `abstain`. Evidence IDs must belong to the same public case. Produce exactly one proposal per public case with no duplicates or omissions.

Use only public semantic evidence. Do not infer meaning from opaque IDs or the dev/hidden split. Before finishing, parse the output and verify schema, metadata, coverage, action families, confidence bounds, and evidence IDs. Do not include commentary or Markdown in the JSON file.
