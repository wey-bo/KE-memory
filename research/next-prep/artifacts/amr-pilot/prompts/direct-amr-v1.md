Convert one English sentence into one standard Abstract Meaning Representation graph.

Return exactly one PENMAN graph and nothing else. Do not use Markdown fences, commentary, JSON, or multiple top-level graphs.

Use standard AMR conventions, PropBank frames when available, and standard roles. Preserve every meaning licensed by the sentence that affects events, states, participant roles, polarity, modality, intent, time, quantity, conditions, causality, comparison, or clause relations. Preserve names, dates, amounts, products, and places exactly enough to recover their meaning.

Do not add background assumptions or information from outside the sentence. Do not encode provenance, confidence, evidence, lifecycle state, project fields, or evaluator metadata in the graph.
