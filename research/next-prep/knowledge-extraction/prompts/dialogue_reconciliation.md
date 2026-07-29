# Dialogue Reconciliation

## Input Boundary
Reconcile only the complete supplied conversation and its supplied immutable A-stage records. The first pass is immutable: never rewrite an A-stage record or its evidence. Do not read or use old KEOL outputs, custom KE outputs, prior implementation output, old dialogue outputs, or unsupplied turns.

## Output Contract
Return JSON only, conforming exactly to the supplied reconciliation schema. Treat A-stage records as immutable; express changes only as `confirm`, `correct`, `supersede`, `conflict`, or `add` operations. Use the exact `D_<candidate_namespace>_<index:03d>` prefix supplied by the payload for `new_knowledge` IDs and the exact `R_<candidate_namespace>_<index:03d>` prefix for operation IDs. Start each index at 001 and keep it contiguous. `replacement` is an ID reference, never an embedded knowledge object. A `correct` or `add` replacement must reference an ID in `new_knowledge`; a `supersede` replacement may reference an active same-candidate A-stage record or new dialogue knowledge.

Synthetic example: a new message that explicitly revises `delivery Tuesday` to `delivery Wednesday` may produce a `correct` operation. This example is synthetic and is not drawn from KE-test.

## Completeness Checklist
Identify each supported correction, supersession, conflict, or genuinely cross-turn addition. Confirm only when dialogue-level evidence materially confirms an A-stage record; do not mechanically confirm every fact. Every new dialogue knowledge record must be referenced exactly once as the replacement of a `correct`, `supersede`, or `add` operation. Retain uncertainty when evidence does not decide among alternatives.

## Evidence Rules
Every operation and every new knowledge record must cite exact source quotes using the supplied `turn_index`, `message` (`user` or `agent`), `occurrence_index`, and `quote`. Each conversation turn supplies explicit `tool_result_spans` from the source-segments sidecar; each span includes its unique `marker_occurrence_index`, exact post-marker start, and explicit semantic end. Operation evidence must also include `evidence_role` as exactly `user_reported`, `agent_generated`, or `tool_observed`; this role is required on every operation evidence item. Quotes must be exact substrings of that message in that turn. Do not infer result boundaries from punctuation, marker position, the next marker, or message end. Do not invent support or use unstated historical context.

Operation evidence item example: `{"turn_index": 2, "message": "agent", "occurrence_index": 0, "quote": "preference saved", "evidence_role": "tool_observed"}`.

## Epistemic Rules
Do not mutate A-stage facts. Distinguish user reports, agent-generated content, and observed tool results. `user_reported` evidence is user-only; `agent_generated` evidence is agent-only and wholly outside the supplied tool-result spans and literal marker spans; `tool_observed` evidence is agent-only and wholly inside a supplied tool-result span. Text after a supplied tool-result span is not tool-observed merely because it follows `[工具结果]`. A tool call or marker alone does not establish completion. Operation evidence may mix roles when every cited span declares and satisfies its own role.

## Forbidden Behavior
Do not read, use, or reproduce old KEOL/custom KE outputs or old dialogue outputs. Do not silently edit A-stage records, infer unprovided turns, create unsupported or cross-candidate references, embed replacements, add single-turn restatements, or output prose outside JSON. `confirm`, `correct`, and `supersede` targets must be A-stage IDs; only `conflict` may also target D-stage IDs. Assign each A-stage target at most one of `confirm`, `correct`, or `supersede`. A conflict must not include an ID corrected or superseded in the same output. A supersede replacement must not reference itself, an ID targeted by `correct` or `supersede`, or form a replacement chain or cycle.

## Final Self-Check
Verify every change is one of the five permitted operations, A-stage is unchanged, IDs use the supplied namespace and contiguous prefixes, every target and replacement resolves within the candidate, terminal state assignments and supersede replacements satisfy the no-chain policy, every new dialogue knowledge record has exactly one replacing operation, every operation evidence item declares the correct `evidence_role`, every Agent evidence span agrees with the supplied `tool_result_spans`, all evidence is exact, and the response is JSON only.
