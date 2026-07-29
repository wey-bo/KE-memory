# Symbolic Fallback FastEmbed Report

Run: `run-20260726Tsymbolic-fallback-fastembed`

Scope: BEAM / LoCoMo / LongMemEval slice-v1 only. This is a local project arm, not a Mem0/Graphiti/Hindsight/MemPalace/Zep rerun.

Arm definition: run `symbolic` first, then trigger dense fallback only when the symbolic result is empty and the item is not an abstention item. Fallback uses FastEmbed `BAAI/bge-small-en-v1.5` from local cache `qdrant/bge-small-en-v1.5-onnx-q@52398278842ec682c6f32300af41344b1c0b0bb2`. This v1 does not generate answers and does not append dense results to non-empty symbolic evidence sets.

Artifacts:

- Results: `symbolic-fallback-fastembed-results.json`
- Score: `symbolic-fallback-fastembed-score.json`
- Evidence corpus: `evidence-corpus.json`

## Overall metrics

Top-k: symbolic 10, fallback 10.

| Metric | Dense reference | Symbolic v1 | Symbolic fallback |
| --- | ---: | ---: | ---: |
| Items | 32 | 32 | 32 |
| Scoreable answer items | 30 | 30 | 30 |
| Manual-required answer items | 2 | 2 | 2 |
| Evidence Set Exact Match | 0.375 | 0.375 | 0.40625 |
| All-Evidence@10 | 0.59375 | 0.625 | 0.65625 |
| Mean Evidence Recall@10 | 0.6614583333333334 | 0.71875 | 0.75 |
| Mean Evidence Precision@10 | 0.425 | 0.49409722222222224 | 0.5253472222222222 |
| Abstention correctness | 0.0 | 0.5 | 0.5 |
| Critical false-positive count | 2 | 1 | 1 |
| Fallback trigger rate | 0.0 | 0.0 | 0.03125 |
| Mean evidence token count | 2979.4375 | 1770.6875 | 2107.40625 |
| Mean latency ms | 1747.1565250007188 | 74.58025312507743 | 131.16788945244195 |

`answer_exact_match=0.0` is expected for this run because this arm retrieves evidence only and does not generate answers.

## Breakdown

| Benchmark | n | Exact | All-Evidence@10 | Recall@10 | Precision@10 | Fallback rate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| BEAM | 10 | 0.1 | 0.4 | 0.65 | 0.31 | 0.0 |
| LoCoMo | 10 | 0.0 | 0.5 | 0.55 | 0.1711111111111111 | 0.0 |
| LongMemEval | 12 | 1.0 | 1.0 | 1.0 | 1.0 | 0.08333333333333333 |

LongMemEval remains inflated by the v1 source setup: `longmemeval_oracle.json` provides only oracle haystack sessions, so this is not comparable to full LongMemEval retrieval difficulty.

## Fallback trigger audit

Only one item triggered fallback:

- `LONGMEMEVAL-6d550036`, group `multi-session`, question: "How many projects have I led or am currently leading?"
- Symbolic result: empty.
- Fallback result: `answer_ec904b3c_2`, `answer_ec904b3c_1`, `answer_ec904b3c_4`, `answer_ec904b3c_3`.
- Gold evidence set: same four session IDs.

This is a useful missing-link recovery case: shallow symbolic matching was too conservative for `led/currently leading`, while dense retrieval recovered all evidence. It did not override a non-empty symbolic structural result.

## Gate interpretation for slice-v1

The slice-level retrieval gate is provisionally satisfied:

- `symbolic_fallback` Evidence Recall@10 is higher than dense reference: `0.75` vs `0.6614583333333334`.
- Critical false positives are lower than dense reference: `1` vs `2`.
- Fallback did not trigger on abstention items.
- No result loses evidence provenance; all retrieved IDs are evidence-corpus unit IDs that map back to raw source units.

However, this is not enough to authorize full benchmark claims. The fallback reason taxonomy is still coarse, and the one fallback item belongs to a multi-session group. Before a broader natural benchmark run, fallback eligibility should distinguish lexical/predicate missing-link recovery from structural reasoning failure in machine-readable metadata.

## Remaining failure patterns

- BEAM: still has one abstention false positive and multiple over-returned evidence sets in contradiction/update/temporal questions.
- LoCoMo: speaker binding helps, but same-speaker semantically similar turns still cause large evidence sets.
- Answer quality is unmeasured because no answerer or judge is attached.

## Interpretation

This run supports the architecture direction more strongly than `symbolic` alone: embedding fallback can improve recall without increasing structural false positives when it is gated behind symbolic failure. It does not prove product superiority or superiority over Mem0/Graphiti/Hindsight/MemPalace/Zep, which were not rerun.
