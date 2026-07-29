# V3 Real Dense Report

Date: 2026-07-25

## Decision

Status: `fail`.

The v3 real dense run proves that guarded embedding fallback can recover the frozen lexical fallback probes with the real `fastembed` backend, but the automatic ontology pipeline still fails the pre-registered retained-gain gate. Do not advance to LoCoMo, BEAM, LongMemEval, or product-level fusion strategy from this result.

## Environment

- Python: `.venv-dense/Scripts/python.exe`
- Installed dense requirements: `fastembed==0.8.0`, `pydantic==2.10.3`, `psutil==7.0.0`
- Encoder provider: `fastembed`
- Backend model: `qdrant/bge-small-en-v1.5-onnx-q`
- Backend revision: `52398278842ec682c6f32300af41344b1c0b0bb2`
- Dimensions: 384
- Model cache state before load: `warm`

The initial sandboxed install failed with Windows socket permission error `WinError 10013`; dependencies were then installed into the workspace-local `.venv-dense` with approved network access. The base `D:\Anaconda\python.exe` environment remains without `fastembed`.

## Runs

### Dev

```text
run_id: run-20260725T190000Z-v3-real-dev
split: dev
rows: 468
errors: 0
verify-run: valid
model_load_latency_ms: 334.718
rss_load_delta_mib: 125.371
```

Automatic dev metrics:

| Arm | Evidence Set Exact Match | Answer | Constraint | Critical FP | Fallback |
| --- | ---: | ---: | ---: | ---: | ---: |
| B2 | 0.000 | 0.538 | 0.000 | 1.000 | 0.000 |
| O+ | 0.923 | 0.923 | 0.923 | 0.000 | 0.000 |
| O+E | 1.000 | 1.000 | 1.000 | 0.000 | 0.077 |

The single dev fallback probe `OME-S061` fails under automatic `O+` and passes under automatic `O+E`.

### Hidden

```text
run_id: run-20260725T192000Z-v3-real-hidden
split: hidden
rows: 1,836
errors: 0
verify-run: valid
model_load_latency_ms: 229.503
rss_load_delta_mib: 125.168
```

Oracle hidden metrics:

| Arm | Evidence Set Exact Match | Answer | Constraint | Critical FP | Fallback |
| --- | ---: | ---: | ---: | ---: | ---: |
| B2 | 0.000 | 0.621 | 0.000 | 1.000 | 0.000 |
| O- | 0.059 | 0.078 | 0.059 | 0.000 | 0.000 |
| O+ | 1.000 | 1.000 | 1.000 | 0.000 | 0.000 |
| O+E | 1.000 | 1.000 | 1.000 | 0.000 | 0.000 |

Automatic hidden metrics:

| Arm | Evidence Set Exact Match | Answer | Constraint | Critical FP | Fallback |
| --- | ---: | ---: | ---: | ---: | ---: |
| B2 | 0.072 | 0.686 | 0.000 | 0.895 | 0.000 |
| O- | 0.176 | 0.373 | 0.353 | 0.000 | 0.000 |
| O+ | 0.235 | 0.569 | 0.647 | 0.000 | 0.000 |
| O+E | 0.294 | 0.627 | 0.706 | 0.000 | 0.059 |

Fallback summary:

```text
overall fallback rate: 0.058823529411764705
structural-family fallback rate: 0.0
execution errors: 0
```

Hidden fallback probes:

| Arm | Probe ESEM | Probe Answer | Probe Constraint | Probe Fallback | Probe Critical FP |
| --- | ---: | ---: | ---: | ---: | ---: |
| O+ | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| O+E | 1.000 | 1.000 | 1.000 | 1.000 | 0.000 |

## Gate Report

Generated report: `artifacts/ontology-memory-experiment/reports/v3-real-hidden-gate-report.md`

```text
decision: fail
strong_dense_baseline: B2
structural_exact_match: pass
critical_false_positive_reduction: pass
distractor_500: pass
automatic_retained_gain: fail
lexical_recall: pass
fallback_limits: pass
```

The failed gate is:

```text
automatic_retained_gain: retained gain against B2 is 0.16339869281045752
```

## Interpretation

The core architectural claim remains supported only at the oracle/representation-capability level: a sufficiently typed ontology representation with exact execution beats dense retrieval and weak ontology ablations on controlled structural tasks.

The current automatic pipeline is still not adequate. The real `O+E` arm improves hidden Evidence Set Exact Match from 0.235 to 0.294 and solves all hidden fallback probes without structural fallback pollution, but that improvement is too narrow to justify moving to large memory benchmarks.

The next work should focus on automatic extraction and query compilation failures outside the lexical fallback probes, especially the hidden structural and temporal slices where oracle `O+` is perfect but automatic `O+` is not.
