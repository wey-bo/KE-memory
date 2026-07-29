# Turn Knowledge Extraction

## Input Boundary
Process exactly one user message and its paired agent message. Do not use earlier turns, later turns, summaries, previous extraction output, old KEOL output, custom KE output, or any artifact from a prior implementation. The supplied source metadata is provenance, not additional dialogue context.

## Output Contract
Return JSON only, conforming exactly to the supplied `TurnPassOutput` JSON Schema. Emit `context_completions` first and then atomic `knowledge` items. Use the payload's exact `candidate_namespace`, `knowledge_id_prefix`, and `context_completion_id_prefix` when assigning IDs. Every evidence item must quote exact text and include the zero-based `occurrence_index` for that exact quote.

Synthetic example: with user `My desk is blue.` and agent `Noted.`, an explicit user fact may cite `My desk is blue.` at occurrence 0. This example is synthetic and is not drawn from KE-test.

## Completeness Checklist
Capture explicit user reports, requests, preferences, commitments, and observations; separately capture eligible agent-generated advice or claims. Complete only local references that this one turn supports. Leave ambiguity unresolved rather than inventing a completion. Split independent facts into atomic knowledge items.

## Evidence Rules
Use only exact substrings from the supplied user or agent message. Preserve the message side and occurrence index. The payload supplies explicit `tool_result_spans` resolved from the source-segments sidecar; each span includes the owning `marker_occurrence_index`, starts at the first non-whitespace character after that `[工具结果]`, and retains its explicit semantic end. Use `tool_observed` only when every cited Agent evidence span is wholly inside one supplied tool-result span. Use `agent_generated` only when every cited Agent span is wholly outside both supplied tool-result spans and literal tool marker spans. Do not infer a result boundary from punctuation, marker position, the next marker, or message end. A tool call is not proof of success. Do not cite paraphrases, source metadata, or any unavailable turn.

## Epistemic Rules
Facts from the user are `user_reported`. Agent advice, suggestions, plans, and unverified claims outside the supplied tool-result spans are `agent_generated`; they are not real-world facts merely because the agent said them. A tool result can be `tool_observed` only when the evidence is contained by a supplied explicit span and the result text establishes it. Text after that span returns to `agent_generated` eligibility. Keep unresolved references unresolved.

## Forbidden Behavior
Do not read, use, infer from, or reproduce old KEOL outputs, custom KE outputs, prior extraction outputs, or other turns. Do not create unsupported facts, fabricate evidence, treat a tool call as successful execution, add vocabulary IDs, or emit prose or markdown outside the JSON result.

## Final Self-Check
Verify the candidate and turn match the input; every ID has the required candidate-scoped format; every quote and occurrence index resolve exactly; every Agent evidence role agrees with the supplied `tool_result_spans`; context completions precede knowledge; each knowledge item is atomic; and the response is JSON only.
