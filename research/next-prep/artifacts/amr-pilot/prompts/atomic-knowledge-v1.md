Extract atomic semantic propositions from one English sentence.

Return exactly one JSON object with this shape and no Markdown or commentary:

{"schema_version":"amr-pilot-atomic-knowledge-v1","items":[{"knowledge_id":"K001","statement":"...","evidence_quote":"..."}],"representation_gaps":[]}

Use consecutive knowledge IDs starting at K001. Each item must state one complete proposition and include a verbatim non-empty evidence quote from the sentence. Preserve participant direction, polarity, modality, intent, time, quantity, conditions, causality, comparison, and clause relations. Keep names, dates, amounts, products, and places faithful to the sentence.

Do not infer unstated facts. Put any meaning that cannot be expressed as a complete atomic proposition in representation_gaps instead of silently discarding or inventing it.
