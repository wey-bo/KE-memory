# Knowledge Keyword Extraction v2

## Input Boundary

Extract keyword occurrences only from the supplied active knowledge records and their supplied fields. The knowledge records already preserve the facts, so keywords must not restate or summarize whole facts. Do not read or use old keyword outputs, old KEOL outputs, custom KE outputs, previous outputs, or unsupplied dialogue.

## Output Contract

Return JSON only and conform exactly to the supplied output contract. Every knowledge item must contain at least one `lexical` keyword plus complete qualifier coverage.

Each keyword is one occurrence and must use exactly one `keyword_kind`:

- `lexical`: an atomic entity, concept, action, event, property, or relation term suitable for WordNet or schema.org lookup.
- `literal`: a typed date, time, duration, number, currency, percentage, version, code value, or other concrete value. Use exact lookup only.
- `identifier`: an order ID, item ID, path-like ID, account ID, or other instance identifier. Use exact lookup only.
- `qualifier`: a temporal, condition, or modality marker used to distinguish retrieval scope. Use exact lookup only.

For a `lexical` keyword:

- Use a base English `query_lemma`, not a translated sentence.
- Noun and proper-noun lemmas may contain at most six space-separated words. Verb, adjective, adverb, relation, and other lemmas may contain at most four.
- Never combine subject, predicate, object, negation, condition, time, and modality into one lemma.
- Provide `part_of_speech`, a lowercase snake_case `sense_key`, and a concise English `sense_hint` that disambiguates the intended meaning.
- Use only `wordnet`, `schema_org`, or both as lookup targets. Add `exact` only when exact name matching is also useful.
- Leave `normalized_value`, `datatype`, and `unit` null.

For `literal`, `identifier`, and `qualifier` keywords:

- Set `part_of_speech` to `none` and `sense_key` to null.
- Provide a normalized machine-readable `normalized_value` and an appropriate `datatype`.
- Use `lookup_targets: ["exact"]` only.
- An identifier must use `datatype: "identifier"` and `semantic_role: "identifier"`.

Use only these `semantic_role` values:

`subject`, `predicate`, `object`, `topic`, `participant`, `recipient`, `instrument`, `result`, `attribute`, `value`, `time`, `location`, `condition`, `modality`, `polarity`, `identifier`, `other`.

## Completeness Checklist

For every knowledge item:

1. Extract the most informative atomic lexical terms from the subject, predicate, object, or statement. Prefer user-provided content, but include agent or tool knowledge when the supplied record contains it.
2. Cover the semantic frame, not merely the topic. Extract the core domain participant or object plus the meaningful action, relation, state, direction, or property that distinguishes the knowledge. Generic `user`, `agent`, `request`, `suggest`, `provide`, and `goal` terms do not count unless their identity is materially relevant. A knowledge item without a literal or identifier should normally have at least two lexical keywords; a single lexical keyword requires that the fact truly contains only one domain term plus non-lexical qualifiers.
3. Emit one or more entries covering every value in `qualifiers.temporal` using `source_field: "qualifiers.temporal"` and `semantic_role: "time"`. Split concrete values from temporal relations: dates, clock times, durations, and numeric periods are `literal`; `before`, `after`, `past`, `future`, `current`, `recent`, `within`, `since`, `until`, and recurrence are separate `qualifier` entries with `datatype: "temporal_relation"`. Preserve both parts of expressions such as `past two months`, `within six months`, or `before May 15`.
4. Emit one qualifier entry covering every value in `qualifiers.conditions` using `keyword_type: "condition"`, `semantic_role: "condition"`, and `source_field: "qualifiers.conditions"`. In addition, extract meaningful entities, concepts, actions, events, properties, and relations inside the condition as separate lexical keywords from the same source field.
5. Emit exactly one modality qualifier using the exact supplied modality value, `keyword_type: "modality"`, `semantic_role: "modality"`, `source_field: "qualifiers.modality"`, `normalized_value` equal to the supplied modality, and `datatype: "modality"`.
6. When `qualifiers.polarity` is `negative`, emit exactly one polarity qualifier with `keyword_type: "polarity"`, `semantic_role: "polarity"`, `source_field: "qualifiers.polarity"`, `normalized_value: "negative"`, and `datatype: "polarity"`. Positive polarity is the default and must not create a redundant qualifier.
7. Cover every value in `qualifiers.scope`. Classify IDs as `identifier`, typed values as `literal`, and meaningful named concepts or participants as `lexical`.
8. Do not duplicate the same normalized term with the same sense and role inside one knowledge item. Repeated occurrences across different knowledge items are allowed and will be canonicalized later.
9. Reuse the same `sense_key` only when `query_lemma`, `part_of_speech`, and `keyword_type` express the same lexical sense. Never reuse a relation sense key for a property or concept, and do not invent a new sense key for an already-used identical sense.

## Evidence Rules

The `surface` must be an exact substring of the declared `source_field`. `normalized_zh` may normalize spacing and wording but must preserve the same meaning. Do not fabricate a source phrase or claim an external vocabulary match.

The allowed source fields are:

`statement`, `subject`, `predicate`, `object`, `qualifiers.temporal`, `qualifiers.conditions`, `qualifiers.scope`, `qualifiers.modality`, `qualifiers.polarity`.

## Epistemic Rules

Keywords are retrieval aids, not new facts or ontology commitments. Preserve the supplied modality through the mandatory modality qualifier. Do not turn advice, requests, possibilities, plans, claims, or tool observations into asserted facts.

## Forbidden Behavior

- Do not emit vocabulary IDs or claim that a WordNet/schema.org candidate has already matched.
- Do not emit clause-like lexical lemmas such as `research does not support fixed learning style classification`.
- Do not put dates, prices, percentages, versions, code, or IDs into a lexical keyword.
- Do not invent free-form semantic roles.
- Do not reuse old keyword, KEOL, or custom KE outputs.
- Do not emit text outside JSON.

## Final Self-Check

Before returning JSON, verify:

- every knowledge ID is covered exactly once;
- every item has at least one lexical keyword;
- all temporal, condition, modality, negative polarity, and scope qualifier values are covered;
- lexical lemmas are atomic and have a valid `sense_key`;
- non-lexical values use exact lookup and typed normalized values;
- every surface is traceable to its declared source field;
- keyword IDs are contiguous in the supplied namespace;
- the response contains JSON only.
