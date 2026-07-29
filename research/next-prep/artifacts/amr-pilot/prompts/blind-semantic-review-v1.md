Review blinded semantic representations against approved semantic checklists.

You receive one JSON bundle containing approved checklists and blinded candidate outputs. Candidate route names are intentionally absent. Evaluate every candidate independently; do not rank candidates against each other and do not infer a route from the representation format.

For every gold item, assign exactly one outcome:

- `supported`: the candidate preserves the complete proposition, including participant direction, scope, polarity, modality, time, quantity, condition, causality, and identity constraints that matter to the statement.
- `omitted`: the proposition is absent or too underspecified to recover, but the candidate does not assert a contradictory version.
- `incorrect`: the candidate contradicts, reverses, or materially changes the proposition, including role reversal, wrong scope, wrong polarity, wrong time or quantity, changed condition or cause, or incorrect identity/coreference.

Record every candidate claim that is not licensed by any gold item and violates a forbidden inference as a hallucination. Use `importance: "critical"` and `weight: 2` for a role, polarity, modality, time, quantity, condition, causality, identity, or core-event error. Use `importance: "ordinary"` and `weight: 1` only for a non-critical unsupported detail. Do not count harmless representation labels, formatting differences, or semantically equivalent decompositions as hallucinations.

Return exactly one JSON object and no Markdown or commentary:

{"schema_version":"amr-pilot-blind-review-result-v1","reviewer_id":"REVIEWER_ID","items":[{"blind_id":"BLIND-000000000000","sample_id":"AMR-S001","judgments":[{"item_id":"AMR-S001-G001","outcome":"supported"}],"hallucinations":[{"statement":"...","importance":"critical","weight":2}]}]}

The result must contain every blinded candidate in the bundle exactly once. Each candidate must cover every gold item for its sample exactly once. Keep `blind_id`, `sample_id`, and `item_id` unchanged.
