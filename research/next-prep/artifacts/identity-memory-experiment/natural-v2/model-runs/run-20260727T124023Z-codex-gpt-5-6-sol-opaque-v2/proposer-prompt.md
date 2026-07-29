# Natural Identity Proposal-Only Contract

You are a fresh proposer with no inherited conversation history.

## Allowed input

Read exactly this dataset file and no other workspace file:

`/public/home/wwb/KE-mem/KE-memory-next-prep-20260727/artifacts/identity-memory-experiment/natural-v2/public.json`

Do not read or inspect directories, v1 data, source cases, mappings, preregistration, authority, gold, reference artifacts, prior model runs, scorer code, scorer outputs, reports, plans, or documentation. The restriction is part of the experiment.

## Output

Write proposal JSON to:

`/public/home/wwb/KE-mem/KE-memory-next-prep-20260727/.tmp/opaque-v2-model-stage/proposals.json`

Use this exact run metadata:

- `schema_version`: `natural-identity-proposals-v1`
- `run_id`: `run-20260727T124023Z-codex-gpt-5-6-sol-opaque-v2`
- `proposer_id`: `codex-gpt-5.6-sol`
- `proposer_version`: `2026-07-27`
- `dataset_id`: copy exactly from public input
- `case_count`: `12`

The top-level object contains `schema_version`, `dataset_id`, `run_id`, `proposer_id`, `proposer_version`, `case_count`, and `proposals`.

Each proposal contains exactly:

- `case_id`: copy from its public case;
- `relation_kind`: copy from its public case;
- `action`: for identity use `merge`, `keep_distinct`, or `abstain`; for membership use `include`, `exclude`, or `abstain`;
- `confidence`: number from 0 through 1;
- `evidence_mention_ids`: only mention IDs belonging to that public case;
- `reason_code`: concise machine-readable snake_case rationale based only on public evidence;
- `proposer_id`, `proposer_version`, and `run_id`: exact values above.

Produce exactly one proposal for each of the 12 public cases, with no duplicate or missing case. A non-abstain proposal must include evidence. Do not infer meaning from opaque case or mention IDs. Use only the question, quotes, surfaces, source metadata, actor metadata, concepts, and relation fields present in public input.

Before finishing, parse your output and verify the schema, metadata, case coverage, action families, confidence bounds, and evidence IDs. Do not include commentary or Markdown in the JSON file.
