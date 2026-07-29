# Dense Reference FastEmbed Report

Run: `run-20260726Tdense-reference-fastembed`

Scope: BEAM / LoCoMo / LongMemEval slice-v1 only. This is a local project arm, not a Mem0/Graphiti/Hindsight/MemPalace/Zep rerun.

Encoder: FastEmbed `BAAI/bge-small-en-v1.5`, source cache snapshot `qdrant/bge-small-en-v1.5-onnx-q@52398278842ec682c6f32300af41344b1c0b0bb2`, 384 dimensions. The model was run from `.venv-dense` with `FASTEMBED_CACHE_PATH=.fastembed-cache` and `HF_HUB_OFFLINE=1` after the model files were cached.

Artifacts:

- Results: `dense-reference-fastembed-results.json`
- Score: `dense-reference-fastembed-score.json`
- Evidence corpus: `evidence-corpus.json`

## Overall metrics

Top-k: 10

| Metric | Value |
| --- | ---: |
| Items | 32 |
| Scoreable answer items | 30 |
| Manual-required answer items | 2 |
| Evidence Set Exact Match | 0.375 |
| All-Evidence@10 | 0.59375 |
| Mean Evidence Recall@10 | 0.6614583333333334 |
| Mean Evidence Precision@10 | 0.425 |
| Abstention correctness | 0.0 |
| Critical false-positive count | 2 |
| Mean evidence token count | 2979.4375 |
| Mean latency ms, embedding amortized | 1747.1565250007188 |

`answer_exact_match=0.0` is expected for this run because `dense_reference` currently performs retrieval only and does not generate answers.

## Breakdown

| Benchmark | n | Exact | All-Evidence@10 | Recall@10 | Precision@10 |
| --- | ---: | ---: | ---: | ---: | ---: |
| BEAM | 10 | 0.0 | 0.5 | 0.6166666666666667 | 0.12 |
| LoCoMo | 10 | 0.0 | 0.2 | 0.3 | 0.04 |
| LongMemEval | 12 | 1.0 | 1.0 | 1.0 | 1.0 |

LongMemEval's perfect retrieval score is not comparable to full LongMemEval retrieval difficulty in this v1 setup: `longmemeval_oracle.json` gives only oracle haystack sessions for selected questions, so the candidate corpus lacks the larger distractor set.

## Main failure pattern

- BEAM: dense retrieval often includes all required contradiction/temporal evidence but returns many extra top-10 items; multi-session aggregation misses some required turns.
- LoCoMo: dense retrieval performs poorly on personal/social questions because many dialogue turns are semantically similar and entity/role binding is weak.
- Abstention: dense retrieval returns plausible-looking evidence even when gold evidence is empty, causing 2 critical false positives.

## Interpretation

This baseline confirms the expected architecture gap: dense retrieval is useful for evidence recovery but weak at abstention, role binding, and exact evidence-set control. It is not a product-quality answer system and does not compare against external memory systems.
