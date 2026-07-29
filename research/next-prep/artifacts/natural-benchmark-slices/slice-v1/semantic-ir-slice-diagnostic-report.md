# Real Slice Semantic IR Diagnostic Report

Run: `run-20260727Tsemantic-ir-real-slice`

Scope: hand-authored real slice IR only; no model extraction; no benchmark expansion.

## Metrics

- Passed: 5/5
- IR evidence exact: 5
- Existing evidence exact: 3
- IR evidence-exact improvements: 2
- Existing fallback triggered: 1
- IR fallback allowed: 0
- IR abstentions: 1

## Cases

### BEAM-100K-C001-abstention-001: PASS

Mentions of feedback and UI/UX improvement are not enough without a causal link.

- Category: `causal_answerability`
- Existing refs: `[]`
- Existing exact: `True`
- Existing fallback: `False`
- IR refs: `[]`
- IR exact: `True`
- IR abstained: `True`
- IR reason: `missing causal answerability roles`

### LONGMEMEVAL-6d550036: PASS

The current shallow symbolic arm needs embedding fallback for led/lead, while typed IR maps lead/manage directly.

- Category: `lexical_fallback_elimination`
- Existing refs: `['answer_ec904b3c_2', 'answer_ec904b3c_1', 'answer_ec904b3c_4', 'answer_ec904b3c_3']`
- Existing exact: `True`
- Existing fallback: `True`
- IR refs: `['answer_ec904b3c_4', 'answer_ec904b3c_2', 'answer_ec904b3c_1', 'answer_ec904b3c_3']`
- IR exact: `True`
- IR abstained: `False`
- IR reason: `closure complete`

### BEAM-100K-C001-contradiction_resolution-001: PASS

Conflict-sensitive evidence closure requires both the denial and the positive Flask route implementation evidence.

- Category: `conflict_evidence_closure`
- Existing refs: `['58', '66']`
- Existing exact: `False`
- Existing fallback: `False`
- IR refs: `['58', '24']`
- IR exact: `True`
- IR abstained: `False`
- IR reason: `closure complete`

### BEAM-100K-C001-knowledge_update-002: PASS

Update closure returns the previous count plus the current superseding count and excludes adjacent Git workflow distractors.

- Category: `update_supersession_closure`
- Existing refs: `['148', '149', '182']`
- Existing exact: `False`
- Existing fallback: `False`
- IR refs: `['148', '182']`
- IR exact: `True`
- IR abstained: `False`
- IR reason: `closure complete`

### LONGMEMEVAL-gpt4_2655b836: PASS

Temporal closure requires service anchor, first post-service issue, and vehicle context evidence.

- Category: `temporal_chain_closure`
- Existing refs: `['answer_4be1b6b4_2', 'answer_4be1b6b4_1', 'answer_4be1b6b4_3']`
- Existing exact: `True`
- Existing fallback: `False`
- IR refs: `['answer_4be1b6b4_2', 'answer_4be1b6b4_3', 'answer_4be1b6b4_1']`
- IR exact: `True`
- IR abstained: `False`
- IR reason: `closure complete`

## Interpretation

This diagnostic shows that the event-role-evidence IR can be aligned to real frozen slice items and can express the known answerability, lexical fallback, conflict, update, and temporal evidence-closure cases.
It is still hand-authored: it does not measure model extraction quality, does not generate final answers, and does not authorize full benchmark expansion.
