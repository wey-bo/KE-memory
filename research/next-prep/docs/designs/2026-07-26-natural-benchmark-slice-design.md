# Natural Benchmark Small-Slice Design

Status: active implementation protocol after v5 controlled gate pass.

## Objective

This stage freezes a small, auditable natural benchmark slice for LoCoMo, BEAM, and LongMemEval before any local tuning on these benchmarks.

The purpose is not to claim product superiority. The purpose is to test whether the v5 symbol/ontology-first route that passed the controlled gate survives contact with real benchmark data, while keeping embeddings as fallback evidence recovery only.

## Scope boundary

- Local runs are allowed only for this project's own arms: dense reference, symbolic execution, and symbolic plus guarded fallback.
- Mem0, Graphiti, Hindsight, MemPalace, Zep, and other memory systems are not installed or rerun.
- Author-reported numbers from official sources remain `external_context_only` unless benchmark version, split, metric, answer model, judge, retrieval budget, and protocol are demonstrably compatible.
- A slice result cannot be extrapolated to full LoCoMo, BEAM, or LongMemEval.

## Frozen source snapshots

The first source pass uses three official raw artifacts:

| Benchmark | Source artifact | Official identity | Local path | Size | SHA-256 |
| --- | --- | --- | --- | ---: | --- |
| BEAM | `data/100K-00000-of-00001.parquet` | HF dataset commit `3205395e897e7318c7b094ef4e6047b9b82dbb03`; X-Linked-ETag `c0519be25907005ba873c927c50877471d550873039d96c041554d0075a78ace` | `artifacts/natural-benchmark-slices/raw/beam/100K-00000-of-00001.parquet` | 5,429,768 | `c0519be25907005ba873c927c50877471d550873039d96c041554d0075a78ace` |
| LoCoMo | `data/locomo10.json` | GitHub commit touching the file `cbfbc1dba6bc53d00625212a0f22d55ffee7c1fc`; Git blob SHA `d95b872480b413d935821fdc3c84f8a8f5f29e73` | `artifacts/natural-benchmark-slices/raw/locomo/locomo10.json` | 2,805,274 | `79fa87e90f04081343b8c8debecb80a9a6842b76a7aa537dc9fdf651ea698ff4` |
| LongMemEval | `longmemeval_oracle.json` | HF dataset commit `98d7416c24c778c2fee6e6f3006e7a073259d48f`; X-Linked-ETag `821a2034d219ab45846873dd14c14f12cfe7776e73527a483f9dac095d38620c` | `artifacts/natural-benchmark-slices/raw/longmemeval/longmemeval_oracle.json` | 15,388,478 | `821a2034d219ab45846873dd14c14f12cfe7776e73527a483f9dac095d38620c` |

The BEAM parquet is valid but current `pyarrow==19.0.0` fails on its nested encoding with `Repetition level histogram size mismatch`; DuckDB reads it successfully. The reader contract therefore records DuckDB as the required BEAM source reader.

## Slice v1 selection policy

The selection is deterministic and stratified by source-visible category fields. It does not inspect model outputs.

### BEAM 100K

Select 10 questions: the first 2 questions by `(conversation_id, category, source_order)` from each category:

- `abstention`;
- `contradiction_resolution`;
- `knowledge_update`;
- `multi_session_reasoning`;
- `temporal_reasoning`.

These categories directly stress absence, conflict, updates, cross-session composition, and time.

### LoCoMo

Select 10 questions: the first 2 questions by `(sample_id, qa_index)` from each raw `qa.category` value `1..5`.

Category `5` has `adversarial_answer` but no explicit gold `answer`. Those items remain in the slice as adversarial evidence probes, but answer correctness is `manual_required` until a human gold answer is added. They can still be used for evidence retrieval and false-positive analysis.

### LongMemEval

Select 12 questions: the first 2 questions by `question_id` order from each source `question_type`:

- `temporal-reasoning`;
- `multi-session`;
- `knowledge-update`;
- `single-session-user`;
- `single-session-assistant`;
- `single-session-preference`.

LongMemEval oracle already includes `answer`, `answer_session_ids`, `haystack_session_ids`, and `haystack_sessions`, so `longmemeval_oracle.json` is sufficient for the first slice protocol. The 264MB cleaned source file is not required for slice v1.

## Artifact contract

Slice artifacts live under `artifacts/natural-benchmark-slices/`:

```text
raw/
  beam/100K-00000-of-00001.parquet
  locomo/locomo10.json
  longmemeval/longmemeval_oracle.json
source-manifest.json
slice-v1/
  slice.json
  gold.json
external-results-ledger.json
```

`slice.json` contains only benchmark identity, question text, category, and source references. It must not contain answers, evidence IDs, rubrics, adversarial answers, or score labels.

`gold.json` contains answers, answer policy, evidence references, rubrics when available, and scoring caveats.

## Evaluation protocol

Local arms to run after slice freeze:

1. `dense_reference`: strong dense retrieval over raw evidence units, no symbolic constraint execution.
2. `symbolic`: ontology/KE-style compiled execution without embedding fallback.
3. `symbolic_fallback`: symbolic execution first, then guarded embedding fallback only for empty symbolic result, unresolved entity, uncovered predicate, or missing evidence slot.

The local report must include:

- Evidence Set Exact Match and Evidence Recall@K;
- answer correctness, with LoCoMo category 5 excluded from answer scoring until adjudicated;
- abstention correctness;
- critical false positives for contradiction, adversarial, update, and temporal items;
- fallback trigger rate and fallback reason;
- evidence token count and latency when available;
- representative failures with raw source references.

## Go/no-go interpretation

The slice can authorize a broader natural benchmark run only if all conditions hold:

- source manifest and slice/gold files validate hash bindings;
- at least 24 scoreable items remain after excluding manual-required answers;
- `symbolic_fallback` does not underperform `dense_reference` on Evidence Recall@K;
- structural false positives are lower than or equal to dense reference;
- embedding fallback does not trigger on structural-family items except for declared missing-link recovery;
- no item loses evidence provenance back to raw source IDs.

Failing this slice blocks broad LoCoMo / BEAM / LongMemEval execution and sends work back to representation, admission, query compilation, or answer generation analysis.
