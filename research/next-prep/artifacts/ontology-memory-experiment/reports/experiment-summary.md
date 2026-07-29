# Ontology-Oriented Memory Capability Experiment Summary

## Decision

The pre-registered hidden-set gate decision is **fail**.

The experiment establishes a strong representation/execution ceiling for a sufficiently typed ontology, but the current automatic representation and query compiler retains only 22.9% of that advantage over the strongest dense arm. This is below the pre-registered 70% requirement. The result supports continued research on ontology-first memory, but it does not support promoting the current automatic pipeline into the main memory architecture.

## Frozen Scope

- Language: English.
- Base scenarios: 60, with 12 development and 48 hidden scenarios.
- Families: roles/polarity/modality/quantity; temporal updates/conflicts/provenance; conjunction/exact-set/multihop; synonymy/sense/external/unanswerable.
- Distractor scales: 0, 50, and 500 per base scenario; 33,000 distractor records in total.
- Arms: `B0`, `B1`, `B2`, `O-`, `O+`, and `O+E` on oracle and automatic tracks.
- Evidence budget: 51 whitespace tokens for every arm.
- Dense model: `qdrant/bge-small-en-v1.5-onnx-q` at revision `52398278842ec682c6f32300af41344b1c0b0bb2`, upstream `BAAI/bge-small-en-v1.5` at revision `5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`, 384 dimensions.
- Other memory systems were not installed or rerun.

Frozen v2 input hashes:

| Artifact | SHA-256 |
| --- | --- |
| Source scenarios | `9000e27ea5362b8c0a354846fe0559f9e3f259ddd55ec378934964b7750b5df9` |
| Gold | `781cb32ea1fd1f4a805304f39877a5df5e5523df771bf68f3d4a043aad0a7bdb` |
| Distractors | `574090bcd0bc5785c1bb7fdd5882e0fee32ba45c8fc66ce43472151831289217` |
| Oracle query plans | `d9518d26ca67f4f69bb1e337b43939636b893d1d6a8201c1e350b83fb5822847` |
| Oracle representations | `cf49d3c78ea8834c9f2c2f279f31bacf7cafdae0f1cb8b5fede212b1d5218f41` |

## Executed Runs

| Purpose | Run ID | Scenarios | Result rows | Errors |
| --- | --- | ---: | ---: | ---: |
| Full diagnostic grid | `run-20260725T140000Z-diagnostic` | 60 | 2,160 | 0 |
| Real-model smoke with resource metadata | `run-20260725T142000Z-real-smoke` | 2 | 72 | 0 |
| Real-model development split | `run-20260725T143000Z-real-dev` | 12 | 432 | 0 |
| Real-model hidden split | `run-20260725T150000Z-real-hidden` | 48 | 1,728 | 0 |

All four listed runs passed `verify-run`. The hidden run is the decision run. It encoded 31,120 unique texts, recorded 132,896 cache hits, loaded from a warm cache in 236.0 ms, and increased process RSS by 124.9 MiB during model load. The observed command wall time was 1,071.2 seconds. Per-arm dense latency includes shared-cache lock contention and task ordering, so it is not a clean standalone throughput benchmark.

## Hidden Results

The strongest dense baseline selected by the frozen tie rule is `B2`.

| Track / arm | Evidence Set Exact Match | Answer correctness | Constraint satisfaction | Critical false-positive rate |
| --- | ---: | ---: | ---: | ---: |
| Oracle `B2` | 0.000 | 0.597 | 0.000 | 1.000 |
| Oracle `O-` | 0.062 | 0.083 | 0.062 | 0.000 |
| Oracle `O+` | 1.000 | 1.000 | 1.000 | 0.000 |
| Oracle `O+E` | 1.000 | 1.000 | 1.000 | 0.000 |
| Automatic `B2` | 0.021 | 0.729 | 0.000 | 0.972 |
| Automatic `O-` | 0.188 | 0.375 | 0.375 | 0.000 |
| Automatic `O+` | 0.250 | 0.562 | 0.500 | 0.000 |
| Automatic `O+E` | 0.250 | 0.562 | 0.500 | 0.000 |

The answer metric alone is misleading here. Automatic `B2` answers more questions correctly than automatic `O+`, but nearly always returns an incorrect evidence set, violates the structural constraint metric, and selects a critical negative on 97.2% of repeated observations. The ontology track protects evidence precision and constraints, but its current automatic extraction loses too much recall and completeness.

Automatic `O+` by family:

| Family | Evidence Set Exact Match | Answer correctness | Constraint satisfaction |
| --- | ---: | ---: | ---: |
| Roles/polarity/modality/quantity | 1.000 | 1.000 | 1.000 |
| Temporal updates/conflicts/provenance | 0.000 | 0.917 | 1.000 |
| Conjunction/exact-set/multihop | 0.000 | 0.000 | 0.000 |
| Synonymy/sense/external/unanswerable | 0.000 | 0.333 | 0.000 |

The temporal family often recovers the final yes/no state but not the complete provenance and supersession evidence package. The path family lacks a complete normalized multihop relation chain. The lexical family lacks alias/sense closure and reliable explicit-absence evidence. These are representation/compiler gaps, not failures of the deterministic executor ceiling.

## Gate Results

| Gate | Status | Interpretation |
| --- | --- | --- |
| Structural exact match | Pass | All three structural families exceed both `B2` and `O-` by at least 15 percentage points on the oracle track. |
| Critical false-positive reduction | Pass | Oracle `O+` reduces the critical false-positive rate from `B2`'s 1.0 to 0.0. |
| 500-distractor robustness | Pass | Oracle `O+` remains at 1.0 exact match; its gain over `B2` is 1.0. |
| Automatic retained gain | **Fail** | `(0.250 - 0.021) / (1.000 - 0.000) = 0.229`, below 0.70. |
| Lexical recall protection | Pass by the formal rule | Oracle `O+E` does not fall below `B2`, but no fallback was triggered. |
| Fallback limits | Pass by the formal rule | Overall and structural fallback rates are both 0.0. This is a safety result, not evidence of fallback benefit. |

The two fallback-related passes are vacuous for efficacy: `O+E` never triggered embedding fallback and is identical to `O+`. This experiment therefore does not establish that embedding fallback improves the ontology system. It only establishes that the inactive fallback did not contaminate precision.

## What This Establishes

1. A sufficiently expressive typed representation plus exact execution can decisively outperform dense ranking on the controlled structural families, including under 500 distractors.
2. A deliberately incomplete ontology (`O-`) collapses on the required primitive. This directly supports the user's distinction between an ontology and a pseudo-ontology that merely stores graph-shaped data.
3. Dense retrieval can produce plausible answers while returning structurally wrong evidence. Evidence correctness, constraint satisfaction, temporal validity, provenance, and conflict handling must be first-class acceptance metrics.
4. The current automatic ontology pipeline is not yet good enough. Its 22.9% retained gain is a stop signal for architecture promotion, not a reason to abandon the ontology-first hypothesis.

## What This Does Not Establish

- It does not prove superiority over Mem0, Hindsight, MemPalace, Graphiti, or any other named system. Those systems were not rerun under this protocol.
- It does not show end-to-end gains on LoCoMo, LongMemEval, or BEAM.
- It does not select KE, AMR, WordNet, triples, or another physical syntax as the final storage representation.
- It does not validate embedding fallback benefit because the fallback trigger rate was zero.
- It does not measure production extraction cost, LLM token cost, storage growth, ontology maintenance cost, or answer-generation latency.
- The scenarios are controlled English templates. They demonstrate capability classes, not natural-dialogue prevalence.

## Next Decision

Do not proceed directly to a large benchmark run. First build a v3 automatic compiler experiment using only the development split and generic rules, with three explicit acceptance targets:

1. preserve complete temporal provenance/supersession evidence;
2. compile normalized conjunction and multihop relation chains;
3. represent alias/sense/absence gaps and pre-register cases that actually trigger guarded embedding fallback.

Refreeze the automatic compiler and a new hidden split before re-evaluation. Only if automatic retained gain reaches at least 70% and fallback benefit is non-vacuous should the project move to LoCoMo, LongMemEval, and BEAM. External author-reported results remain contextual and are recorded separately in `external-context.md`.
