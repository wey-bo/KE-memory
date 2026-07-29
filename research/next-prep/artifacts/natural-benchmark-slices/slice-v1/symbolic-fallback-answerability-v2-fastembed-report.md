# Symbolic Fallback Answerability v2 FastEmbed Report

Run: `run-20260726Tsymbolic-fallback-answerability-v2-fastembed`

Scope: BEAM / LoCoMo / LongMemEval slice-v1 only. This is a local project arm, not a Mem0/Graphiti/Hindsight/MemPalace/Zep rerun.

Arm definition: run `symbolic` first, classify guarded fallback eligibility, trigger FastEmbed fallback only for allowed missing-link cases, then apply a causal answerability gate to the final retrieved evidence. The gate blocks evidence when a causal/how question is only topically matched and the retrieved text does not establish the requested relation.

This run supersedes the earlier non-v2 answerability diagnostic artifact. That earlier diagnostic used an over-broad causal cue and incorrectly treated "How many projects have I led..." as causal because of `led`; v2 only treats `led to / lead to` as causal.

## Answerability gate v2

Implemented policy: `causal_gate_v1`.

The current gate is intentionally narrow:

- it is active only for causal/how questions with cues such as `influence`, `affect`, `impact`, `because`, `based on`, `caused`, or `led to`;
- it blocks topical overlap such as "UI/UX improved based on feedback" when no concrete feedback-to-change relation is present;
- it allows explicit causal evidence such as "feedback showed X, so I changed Y";
- it does not classify quantity questions like "How many projects have I led..." as causal.

This is still a rule-level approximation, not a full ontology compiler.

## Metrics

Top-k: symbolic 10, fallback 10.

| Metric | Dense reference | Symbolic v1 | Symbolic fallback taxonomy | Symbolic fallback + answerability v2 |
| --- | ---: | ---: | ---: | ---: |
| Items | 32 | 32 | 32 | 32 |
| Evidence Set Exact Match | 0.375 | 0.375 | 0.40625 | 0.4375 |
| All-Evidence@10 | 0.59375 | 0.625 | 0.65625 | 0.6875 |
| Mean Evidence Recall@10 | 0.6614583333333334 | 0.71875 | 0.75 | 0.78125 |
| Mean Evidence Precision@10 | 0.425 | 0.49409722222222224 | 0.5253472222222222 | 0.5565972222222222 |
| Abstention correctness | 0.0 | 0.5 | 0.5 | 1.0 |
| Critical false-positive count | 2 | 1 | 1 | 0 |
| Fallback trigger rate | 0.0 | 0.0 | 0.03125 | 0.03125 |
| Mean evidence token count | 2979.4375 | 1770.6875 | 2107.40625 | 2086.25 |
| Mean latency ms | 1747.1565250007188 | 74.58025312507743 | 129.4455822279872 | 131.47404843760313 |

`answer_exact_match` remains 0.0 because this arm does not generate answers; current scoring is retrieval/evidence focused.

## Decision counts

Fallback decision counts:

- `not_needed`: 30
- `blocked`: 1
- `triggered`: 1

Fallback reason candidate counts:

- `symbolic_nonempty`: 30
- `abstention_or_answerability_missing`: 1
- `lexical_predicate_missing_link`: 1

Answerability decision counts:

- `not_applicable`: 31
- `blocked`: 1

Answerability reason counts:

- `not_causal_question`: 31
- `causal_relation_missing`: 1

## Item audit

Blocked by answerability:

- `BEAM-100K-C001-abstention-001`
- Question: "How did the user feedback influence the UI/UX improvements I made before the public launch?"
- Previous symbolic evidence: `116`, `117`
- Reason: retrieved text mentions user feedback and UI/UX improvements, but does not state how feedback caused or shaped concrete changes.
- Final output: abstain with no retrieved evidence.

Fallback retained:

- `LONGMEMEVAL-6d550036`
- Reason: `lexical_predicate_missing_link`
- Final output: fallback retrieved the same four gold session evidence IDs as the previous taxonomy run.

## Interpretation

The remaining critical false positive from taxonomy v1 is removed without losing the one valid fallback recovery. On slice-v1, the local project arm now improves evidence exact match, recall, precision, abstention correctness, and critical false positives relative to dense reference.

This does not prove product superiority over mainstream memory systems. The comparison is only between local project arms on a 32-item slice. External systems were not rerun under this protocol.

## AMR-style ontology implication

This result supports the user's proposed direction: the next ontology layer can use an AMR-style predicate-argument/event graph as a compiler IR, but it must be extended with memory-specific fields.

The immediate requirements exposed by this run are:

- represent causal roles directly, not as token overlap;
- distinguish predicate senses such as `lead/manage` vs `lead-to/cause`;
- attach `answerable_by` or equivalent evidence-completeness constraints;
- preserve speaker/source/temporal/provenance fields through compilation into KEOL-compatible assertions.

Standard AMR/PENMAN alone is not enough; an AMR-style extended ontology IR is a reasonable next representation target.
