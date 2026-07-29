Convert one validated atomic-knowledge JSON object into one standard Abstract Meaning Representation graph.

Return exactly one PENMAN graph and nothing else. Do not use Markdown fences, commentary, JSON, or multiple top-level graphs.

Use only the supplied atomic propositions. Use standard AMR conventions, PropBank frames when available, and standard roles. Preserve participant direction, polarity, modality, intent, time, quantity, conditions, causality, comparison, and clause relations represented by the supplied propositions. Preserve names, dates, amounts, products, and places.

Do not reconstruct or assume an unseen source sentence. Do not add background assumptions. Do not encode provenance, confidence, evidence, lifecycle state, project fields, or evaluator metadata in the graph.
