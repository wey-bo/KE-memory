# External Author-Reported Benchmark Context

## Interpretation boundary

This report records benchmark values published by the system authors in version-frozen official sources. None of these systems was installed or rerun in this project. The values below are **not local scores**, are **not results of the controlled ontology-memory capability experiment**, and are **not direct numeric comparators** for its `B0`/`B1`/`B2`/`O-`/`O+`/`O+E` arms.

The sources use different benchmark variants, answer models, judges, retrieval depths, context budgets, and metrics. In particular, MemPalace reports retrieval recall rather than end-to-end question-answering accuracy. Values are therefore kept in source-specific tables and must not be combined into a cross-system leaderboard.

## Frozen source scope

| System or paper | Frozen identity | Official source used | Status in this project |
| --- | --- | --- | --- |
| Mem0 | commit `d653b63fac6c8ad0ad84aead0912b366e705d269` | [`docs/core-concepts/memory-evaluation.mdx`](https://github.com/mem0ai/mem0/blob/d653b63fac6c8ad0ad84aead0912b366e705d269/docs/core-concepts/memory-evaluation.mdx) | Author-reported context only; not rerun |
| Hindsight | commit `ed120a256d51d731085ec8aca724573a7f2f1e1c` | [Agent Memory Benchmark post](https://github.com/vectorize-io/hindsight/blob/ed120a256d51d731085ec8aca724573a7f2f1e1c/hindsight-docs/blog/2026-03-23-agent-memory-benchmark.mdx); [BEAM post](https://github.com/vectorize-io/hindsight/blob/ed120a256d51d731085ec8aca724573a7f2f1e1c/hindsight-docs/blog/2026-04-02-beam-sota.md) | Author-reported context only; not rerun |
| MemPalace | commit `8ab251c452c43f2b07a76a28f2433e258307f571` | [`website/reference/benchmarks.md`](https://github.com/Cozy-ctrl/mempalace/blob/8ab251c452c43f2b07a76a28f2433e258307f571/website/reference/benchmarks.md) | Author-reported retrieval context only; not rerun |
| Zep paper | arXiv `2501.13956v1`, 2025-01-20 | [Zep: A Temporal Knowledge Graph Architecture for Agent Memory](https://arxiv.org/pdf/2501.13956v1) | Paper-reported context only; not rerun |
| Graphiti repository context | commit `3bb2d0bba56f8e22311574c045452c420a012f49` | [Frozen Graphiti tree](https://github.com/getzep/graphiti/tree/3bb2d0bba56f8e22311574c045452c420a012f49) | Architecture provenance only; the Zep paper scores are not scores for this repository commit |

The frozen MemPalace audit identity is `Cozy-ctrl/mempalace`; the repository may also be presented under the `MemPalace/mempalace` organization name. The immutable commit above is the identity used here.

The earlier local `official-results-ledger.json` did not record these numeric tables and must not be cited as their source. The numbers in this report come from the frozen official documents listed above.

## Mem0

The frozen Mem0 document reports end-to-end benchmark scores from one retrieval call followed by one answer, with no agentic loop. Unless otherwise noted, it uses a `top_200` retrieval budget. The reported values are from the managed Mem0 platform and average fewer than 7,000 context tokens per query.

| Benchmark | Author-reported score | Mean tokens per query |
| --- | ---: | ---: |
| LoCoMo | 92.5 | 6,956 |
| LongMemEval | 94.4 | 6,787 |
| BEAM 1M | 64.1 | 6,719 |
| BEAM 10M | 48.6 | 6,914 |

Selected category results reported in the same source:

| Benchmark | Category | Score |
| --- | --- | ---: |
| LoCoMo | single-hop | 91.2 |
| LoCoMo | multi-hop | 91.3 |
| LoCoMo | open-domain | 72.7 |
| LoCoMo | temporal | 92.0 |
| LongMemEval | single-session user | 98.6 |
| LongMemEval | single-session assistant | 98.2 |
| LongMemEval | single-session preference | 96.7 |
| LongMemEval | knowledge update | 93.6 |
| LongMemEval | temporal reasoning | 97.0 |
| LongMemEval | multi-session | 88.0 |

The BEAM 10M breakdown is especially relevant as external failure context, but still does not diagnose the cause of an error or prove an ontology remedy:

| BEAM 10M category | Score |
| --- | ---: |
| preference following | 90.4 |
| instruction following | 82.5 |
| information extraction | 56.3 |
| knowledge update | 75.0 |
| multi-session reasoning | 26.1 |
| summarization | 46.9 |
| temporal reasoning | 16.3 |
| event ordering | 20.2 |
| abstention | 40.0 |
| contradiction resolution | 32.5 |

Mem0 explicitly states that these results use proprietary managed-platform optimizations not available in the open-source SDK, so open-source users should not expect identical values. It also reports a `+/-1` point interval due to judge inconsistency. Answer and judge models are described as varying in the evaluation interface rather than frozen here to the local experiment's model stack.

## Hindsight

The frozen Hindsight Agent Memory Benchmark post reports Hindsight `v0.4.19` in single-query mode: one retrieval call, then direct answer generation. Its metric is benchmark answer accuracy, not retrieval recall.

| Agent Memory Benchmark dataset | Author-reported accuracy |
| --- | ---: |
| LoComo | 92.0% |
| LongMemEval | 94.6% |
| LifeBench | 71.5% |
| PersonaMem | 86.6% |

The separate frozen Hindsight BEAM post reports:

| BEAM tier | Hindsight author-reported score |
| --- | ---: |
| 100K | 73.4% |
| 500K | 71.1% |
| 1M | 73.9% |
| 10M | 64.1% |

The same Hindsight post quotes the following comparison values. They are reproduced only as third-party context from that post, not as locally verified or locally rerun scores for those systems:

| BEAM tier | Honcho | LIGHT baseline | RAG baseline |
| --- | ---: | ---: | ---: |
| 100K | 63.0% | 35.8% | 32.3% |
| 500K | 64.9% | 35.9% | 33.0% |
| 1M | 63.1% | 33.6% | 30.7% |
| 10M | 40.6% | 26.6% | 24.9% |

The Hindsight values cannot be merged with Mem0's values merely because some benchmark names overlap. The frozen posts do not establish equality of benchmark snapshot, answer model, judge, retrieval budget, or token budget with Mem0 or with this project's controlled experiment.

## MemPalace

MemPalace explicitly defines its headline metric as **retrieval recall**: whether the labeled session appears in the top-K retrieved sessions. It also explicitly warns that this is not end-to-end QA accuracy. These values must therefore remain separate from Mem0, Hindsight, and Zep accuracy results.

LongMemEval results:

| Evaluation set and mode | Metric | Author-reported value | LLM use |
| --- | --- | ---: | --- |
| Full 500, raw vector search over verbatim sessions | R@5 | 96.6% | None |
| Full 500, hybrid v4 | R@5 | 98.6% | None |
| Full 500, hybrid v4 + `minimax-m2.7` rerank | R@5 | 99.2% | Reranker |
| Clean held-out 450, hybrid v4 | R@5 | **98.4%** | None |
| Clean held-out 450, hybrid v4 | R@10 | 99.8% | None |
| Clean held-out 450, hybrid v4 | NDCG@10 | 0.938 | None |

The source calls the held-out `98.4% R@5` the generalizable headline. It notes that the full-500 hybrid result includes 50 development questions used to tune targeted fixes.

LoCoMo contains 1,986 questions across 10 conversations in this source:

| Mode | Metric | Author-reported value |
| --- | --- | ---: |
| Session retrieval, no rerank, top-10 | R@10 | 60.3% |
| Hybrid v5, no rerank, top-10 | R@10 | 88.9% |

The source explicitly withdraws an earlier `100%` top-50 headline because each conversation contains only 19-32 sessions; retrieving 50 returns every session and makes retrieval trivial.

Other retrieval results reported by MemPalace are `92.9%` average recall on its 250-item ConvoMem sample and `80.3% R@5` overall on MemBench, where the noisy category is `43.4%`. These are additional benchmark contexts, not substitutes for QA evaluation.

## Zep and Graphiti paper context

The Zep paper evaluates a Zep service powered by Graphiti. Its results are tied to arXiv `2501.13956v1`, not to the later frozen Graphiti repository commit. The paper uses BGE-m3 for embedding and reranking, `gpt-4o-mini-2024-07-18` for graph construction, and the listed answer models. Experiments were run from December 2024 through January 2025.

Deep Memory Retrieval (DMR) results:

| Memory condition | Answer model | Author-reported accuracy |
| --- | --- | ---: |
| MemGPT, result reported from the MemGPT paper | `gpt-4-turbo` | 93.4% |
| Full conversation | `gpt-4-turbo` | 94.4% |
| Session summaries | `gpt-4-turbo` | 78.6% |
| Zep | `gpt-4-turbo` | 94.8% |
| Full conversation | `gpt-4o-mini` | 98.0% |
| Session summaries | `gpt-4o-mini` | 88.0% |
| Zep | `gpt-4o-mini` | 98.2% |

For DMR, Zep retrieves the top 10 nodes and edges before answer generation. The paper cautions that each DMR conversation contains only 60 messages and fits easily in current model context windows; it therefore treats DMR as a limited memory test.

LongMemEval-S results:

| Memory condition | Answer model | Score | Mean latency | Latency IQR | Average context |
| --- | --- | ---: | ---: | ---: | ---: |
| Full context | `gpt-4o-mini` | 55.4% | 31.3 s | 8.76 s | 115k tokens |
| Zep | `gpt-4o-mini` | 63.8% | 3.20 s | 1.31 s | 1.6k tokens |
| Full context | `gpt-4o` | 60.2% | 28.9 s | 6.01 s | 115k tokens |
| Zep | `gpt-4o` | 71.2% | 2.58 s | 0.684 s | 1.6k tokens |

The paper describes these as relative accuracy improvements of `15.2%` for `gpt-4o-mini` and `18.5%` for `gpt-4o`, with approximately `90%` lower latency. GPT-4o with the LongMemEval question-specific prompts was used to evaluate answers. These are paper-reported relative changes, not percentage-point deltas and not locally validated latency measurements.

## Comparability matrix

| Source | Primary reported output | Important protocol distinction | Directly comparable to the controlled capability experiment? |
| --- | --- | --- | --- |
| Mem0 | End-to-end benchmark score/accuracy | Managed platform, proprietary optimizations, normally `top_200`, one retrieval call, varying answer/judge configuration, under 7,000 mean tokens | No |
| Hindsight AMB/BEAM | End-to-end answer accuracy | Hindsight `v0.4.19`; single-query AMB mode; source-specific BEAM tiers and evaluation stack | No |
| MemPalace | Retrieval R@5/R@10 and NDCG@10 | Measures labeled-session retrieval, not final answer correctness; held-out and development-inclusive results differ | No |
| Zep paper | DMR and LongMemEval-S answer accuracy plus latency/context | Paper-era Zep service, specified answer models and GPT-4o judge; DMR is only 60 messages; LongMemEval-S averages 115k full context | No |
| Local controlled arms | Evidence-set, constraint, false-positive, abstention, answer, and efficiency metrics | Paired synthetic capability probes with `L0-L3` and `E0-E2` ablations under a frozen local protocol | Not a named-system benchmark |

The main incompatibilities are:

1. **Metric:** retrieval recall is not QA accuracy; neither is equivalent to Evidence Set Exact Match, Constraint Satisfaction Rate, or Critical False Positive Rate.
2. **Benchmark identity:** LoCoMo/LoComo, LongMemEval/LongMemEval-S, AMB wrappers, and BEAM 100K/500K/1M/10M are distinct datasets, variants, or scales unless protocol identity is demonstrated.
3. **Models and judges:** answer and judge models materially affect end-to-end scores and are not normalized across the frozen sources.
4. **Retrieval and context budget:** `top_200`, top-10, R@5/R@10, 1.6k tokens, 7k tokens, and 115k full context expose different evidence budgets.
5. **Product surface:** managed-service optimizations, open-source commits, and paper-era services are not interchangeable implementations.

## Allowed use in this experiment

These results may be used to establish external performance context, select failure families worth probing, and check whether local architecture-class risks align with categories that authors identify as difficult. They do not show that a named system has the hypothesized representation gap, and they do not show that an ontology would fix any published failure.

No system in this report receives a local score. No value above is a direct comparator to `O+`, `O-`, the dense/hybrid controlled arms, or their automatic-extraction variants. Any later direct comparison requires protocol-compatible benchmark version, split, metric, answer model, judge, retrieval/context budget, and system version; otherwise it must remain labeled `external_context_only`.
