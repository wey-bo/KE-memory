# Symbolic Fallback Taxonomy FastEmbed Report

Run: `run-20260726Tsymbolic-fallback-taxonomy-fastembed`

Scope: BEAM / LoCoMo / LongMemEval slice-v1 only. This is a local project arm, not a Mem0/Graphiti/Hindsight/MemPalace/Zep rerun.

Arm definition: run `symbolic` first, classify fallback eligibility, then trigger FastEmbed fallback only for allowed taxonomy reasons. This version records `fallback_decision`, `fallback_reason_candidate`, and `fallback_allowed` in every result item metadata. It does not generate answers and does not append dense evidence to non-empty symbolic results.

## Taxonomy v1

Allowed fallback:

- `lexical_predicate_missing_link`: symbolic produced no evidence, the item is not abstention, and no temporal/conflict/update structural cue blocks fallback.
- `unresolved_entity`: reserved for a later entity-linker failure mode.
- `incomplete_evidence_slot`: reserved for a later slot-completeness checker.

Blocked fallback:

- `abstention_or_answerability_missing`: abstention item with empty symbolic result.
- `temporal_negation_modality_conflict_mismatch`: temporal/negation/modality/conflict class must not be repaired by dense retrieval alone.
- `structural_reasoning_failure`: contradiction/update/adversarial structural failure must go back to symbolic representation/query compilation.

## Metrics

Top-k: symbolic 10, fallback 10.

| Metric | Dense reference | Symbolic v1 | Symbolic fallback taxonomy |
| --- | ---: | ---: | ---: |
| Items | 32 | 32 | 32 |
| Evidence Set Exact Match | 0.375 | 0.375 | 0.40625 |
| All-Evidence@10 | 0.59375 | 0.625 | 0.65625 |
| Mean Evidence Recall@10 | 0.6614583333333334 | 0.71875 | 0.75 |
| Mean Evidence Precision@10 | 0.425 | 0.49409722222222224 | 0.5253472222222222 |
| Abstention correctness | 0.0 | 0.5 | 0.5 |
| Critical false-positive count | 2 | 1 | 1 |
| Fallback trigger rate | 0.0 | 0.0 | 0.03125 |
| Mean evidence token count | 2979.4375 | 1770.6875 | 2107.40625 |
| Mean latency ms | 1747.1565250007188 | 74.58025312507743 | 129.4455822279872 |

Fallback decision counts:

- `not_needed`: 30
- `blocked`: 1
- `triggered`: 1

Fallback reason candidate counts:

- `symbolic_nonempty`: 30
- `abstention_or_answerability_missing`: 1
- `lexical_predicate_missing_link`: 1

## Trigger audit

Triggered:

- `LONGMEMEVAL-6d550036`, group `multi-session`, question: "How many projects have I led or am currently leading?"
- Reason: `lexical_predicate_missing_link`.
- Symbolic result: empty.
- Fallback result: `answer_ec904b3c_2`, `answer_ec904b3c_1`, `answer_ec904b3c_4`, `answer_ec904b3c_3`.
- Gold evidence set: same four session IDs.

Blocked:

- `BEAM-100K-C001-abstention-002`, group `abstention`.
- Reason: `abstention_or_answerability_missing`.
- Symbolic result: empty; fallback did not run.

## Interpretation

The taxonomy does not change the score relative to the earlier guarded fallback v1, but it changes the safety contract: fallback is now machine-auditable instead of being a generic "empty symbolic result" rule.

This still leaves one critical false positive: `BEAM-100K-C001-abstention-001` has non-empty symbolic evidence about UI/UX feedback, but the question asks for a causal influence answer that the evidence does not support. That failure is not a fallback problem; it requires an answerability/causal-relation gate.

## AMR-style ontology implication

The taxonomy points to the next representation need. The symbolic layer needs typed event/predicate roles, causality, temporal anchors, polarity, modality, source speaker, and evidence closure. A standard single-sentence AMR graph is not enough by itself, but an AMR-style extended ontology can be a useful compiler IR between raw text and KEOL-style assertions.
