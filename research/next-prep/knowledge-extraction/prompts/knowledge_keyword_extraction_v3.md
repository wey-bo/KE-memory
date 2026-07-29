# Atomic Knowledge Keyword Extraction v3

## Input Boundary

Extract keywords only from the supplied active knowledge records. Do not read or reuse old keyword outputs, KEOL outputs, custom KE outputs, or unsupplied dialogue. The supplied knowledge is already complete; keywords are retrieval terms, not rewritten facts.

Return JSON only and conform exactly to the supplied output contract. Cover every supplied knowledge ID exactly once and emit at least one keyword for each knowledge record.

## Atomic Keyword Rules

Extract short, atomic retrieval terms from the informative parts of `subject`, `predicate`, `object`, `statement`, and meaningful qualifier fields.

- A keyword is one concept, entity, action, event, property, relation, time term, or quantity term.
- Prefer one Chinese word or one established compound term, such as `休假`, `合伙人`, `工作交接`, `遗嘱`, or `退款`.
- Do not output a clause, sentence fragment, condition sentence, recommendation, summary, or subject-predicate-object combination.
- Split coordinated or compositional phrases into smaller terms when each part remains meaningful.
- A multiword proper name or a lexicalized compound is allowed only when it denotes one named entity or one established term.
- Normally emit 1-5 keywords per knowledge record. More are allowed only when the fact contains several independently useful retrieval terms.
- Do not emit extraction-control labels such as `asserted`, `advised`, `planned`, `negative`, `possible`, `user`, or `agent` unless the label itself is the subject matter of the knowledge.
- Dates, IDs, prices, product names, and personal names may be kept as unmapped keywords when they are important for retrieval.

`surface` must be an exact substring of `source_field`. `keyword` is the short normalized Chinese retrieval term. Use only the supplied `keyword_type`, `semantic_role`, and `source_field` enum values.

## WordNet Mapping Rules

Map a keyword to WordNet only when it expresses a common lexical concept with a clear English sense.

- Use WordNet 3.0 synset names such as `leave.n.01`.
- `wordnet_lemma` must be an actual lemma in that synset. Use the WordNet lemma spelling, including underscores for a lexicalized compound.
- `wordnet_pos` must match the synset: `n`, `v`, `a`, `s`, or `r`.
- `mapping_confidence` expresses confidence in the Chinese-term-to-sense choice, not whether the synset exists.
- Prefer the intended sense over the most frequent sense.
- Do not map proper names, IDs, dates, prices, product-specific labels, domain-specific phrases, or ambiguous terms merely to increase coverage.
- When no reliable WordNet concept exists, set `wordnet_synset`, `wordnet_lemma`, `wordnet_pos`, and `mapping_confidence` all to null. The keyword remains valid and must not be discarded.
- Never invent a synset or lemma. Every proposed mapping will be checked against local WordNet 3.0.

WordNet mapping is analogous to a reusable concept. An unmapped keyword is analogous to a knowledge-specific term that remains useful without being forced into the vocabulary.

## Evidence Rules

The keyword must remain traceable to the supplied knowledge:

- `surface` is copied exactly from the declared `source_field`.
- `keyword` may normalize wording but must not add information.
- Do not infer a keyword solely from outside knowledge.
- Preserve named entities and domain terms exactly enough to remain distinguishable.

## Forbidden Behavior

- No long phrases, clauses, summaries, advice, or complete facts as keywords.
- No fabricated WordNet synsets, lemmas, or mappings.
- No forced mapping for an uncertain or domain-specific term.
- No modality, polarity, provenance, or extraction-status labels as ordinary keywords.
- No reuse of old keyword files or their mappings.
- No text outside the JSON response.

## Final Self-Check

Before returning JSON, verify:

- every knowledge ID is present exactly once;
- every knowledge item has at least one short keyword;
- each `surface` occurs in its declared source field;
- each keyword denotes only one retrieval unit;
- all four WordNet fields are either complete or all null;
- every proposed synset and lemma is a real WordNet 3.0 mapping;
- uncertain, proper, literal, identifier, and domain-specific terms remain unmapped;
- keyword IDs use the supplied prefix and are contiguous from `0001`;
- the response contains JSON only.
