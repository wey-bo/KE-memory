# Symbolic Baseline v1 Report

Run: `run-20260726Tsymbolic-v1`

Scope: BEAM / LoCoMo / LongMemEval slice-v1 only. This is a local project arm, not a Mem0/Graphiti/Hindsight/MemPalace/Zep rerun.

Arm definition: deterministic symbolic retrieval over `slice.json` questions and `evidence-corpus.json` candidate units. It uses token normalization, conservative stopword/stem handling, limited lexical expansions, numeric cues, phrase cues, and LoCoMo speaker/name role binding. It does not read `gold.json`, does not generate answers, and does not trigger embedding fallback.

Artifacts:

- Results: `symbolic-results.json`
- Score: `symbolic-score.json`
- Evidence corpus: `evidence-corpus.json`

## Overall metrics

Top-k: 10

| Metric | Dense reference | Symbolic v1 |
| --- | ---: | ---: |
| Items | 32 | 32 |
| Scoreable answer items | 30 | 30 |
| Manual-required answer items | 2 | 2 |
| Evidence Set Exact Match | 0.375 | 0.375 |
| All-Evidence@10 | 0.59375 | 0.625 |
| Mean Evidence Recall@10 | 0.6614583333333334 | 0.71875 |
| Mean Evidence Precision@10 | 0.425 | 0.49409722222222224 |
| Abstention correctness | 0.0 | 0.5 |
| Critical false-positive count | 2 | 1 |
| Mean evidence token count | 2979.4375 | 1770.6875 |
| Mean latency ms | 1747.1565250007188 | 74.58025312507743 |

`answer_exact_match=0.0` is expected for this run because `symbolic` currently performs retrieval only and does not generate answers.

## Breakdown

| Benchmark | n | Exact | All-Evidence@10 | Recall@10 | Precision@10 |
| --- | ---: | ---: | ---: | ---: | ---: |
| BEAM | 10 | 0.1 | 0.4 | 0.65 | 0.31 |
| LoCoMo | 10 | 0.0 | 0.5 | 0.55 | 0.1711111111111111 |
| LongMemEval | 12 | 0.9166666666666666 | 0.9166666666666666 | 0.9166666666666666 | 0.9166666666666666 |

LongMemEval remains inflated by the v1 source setup: `longmemeval_oracle.json` provides only oracle haystack sessions, so this is not comparable to full LongMemEval retrieval difficulty.

## What this shows

Symbolic v1 improves evidence selectivity over the dense reference on this slice: higher recall, higher precision, lower token count, and one fewer critical false positive. The strongest improvement is LoCoMo, where speaker/name binding helps with personal-role questions that dense retrieval handles poorly.

This is not yet evidence that the ontology memory system is strong enough. Symbolic v1 is still a shallow rule/slot baseline, not full KEOL extraction or typed query execution.

## Main failure patterns

- BEAM abstention still has one critical false positive: the question asks how feedback influenced UI/UX improvements, while the retrieved turns only mention UI/UX being improved based on feedback. This requires answerability/causal-relation modeling, not just lexical matching.
- BEAM contradiction/update/multisession items still over-return adjacent or repeated implementation turns. This shows evidence-boundary and conflict/update closure are not solved by token-level symbolic matching.
- LoCoMo role binding improves recall but still over-returns same-speaker semantically similar turns. Speaker binding alone is a weak ontology.
- LoCoMo adversarial category-5 items remain unsuitable for answer correctness until human gold answers are added.
- LongMemEval misses the "projects led/currently leading" item because the conservative singleton-token guard prevents a weak lexical match. This is a likely case for guarded fallback or stronger predicate compilation.

## Interpretation

The empirical vulnerability of the dense/vector path is still visible: it over-recovers plausible evidence, fails abstention, and has weak role/entity binding. Symbolic v1 partly repairs those issues, but it also proves that "pseudo-ontology" or shallow symbolic matching is insufficient. The next useful test is `symbolic_fallback`: run symbolic first, then trigger dense fallback only for empty symbolic result, unresolved entity, uncovered predicate, or missing evidence slot, while forbidding fallback on structural-family false positives.
