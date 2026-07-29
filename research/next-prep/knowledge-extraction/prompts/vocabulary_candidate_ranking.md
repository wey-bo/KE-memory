# Vocabulary Candidate Ranking

## Input Boundary
Rank only the supplied vocabulary candidates for each supplied keyword. Do not read or use old KEOL outputs, custom KE outputs, previous outputs, or vocabulary records outside the supplied whitelist.

## Output Contract
Return JSON only, conforming exactly to the supplied ranking schema. A returned candidate ID must be exactly one of the supplied whitelist IDs.

Synthetic example: if the whitelist contains only `V_apple_fruit` and `V_apple_company`, a keyword about eating can rank only those supplied IDs. This example is synthetic and is not drawn from KE-test.

## Completeness Checklist
Evaluate each defensible supplied candidate, state mapping strength and basis, and leave selection null when the schema requires deferred selection.

## Evidence Rules
Use the supplied keyword and supplied candidate labels, descriptions, lemmas, and examples. Do not claim an external match or create a missing candidate.

## Epistemic Rules
Ranking is a candidate comparison, not a confirmed ontology assignment. Preserve ambiguity through scores and mapping kinds.

## Forbidden Behavior
Do not read, use, or reproduce old KEOL/custom KE outputs. Do not emit IDs outside the supplied whitelist, invent vocabulary records, or emit text outside JSON.

## Final Self-Check
Verify every ranked ID is whitelisted, each score and mapping is justified by supplied data, selection remains schema-compliant, and the response is JSON only.
