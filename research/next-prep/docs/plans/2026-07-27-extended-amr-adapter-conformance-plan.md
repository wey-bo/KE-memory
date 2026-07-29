# Extended AMR Adapter Conformance Implementation Plan

**Goal:** Implement a deterministic extended-AMR JSON graph adapter and evaluate it against the same representation contract and five scoped real-slice query probes.

**Architecture:** Encode each L1/L2 unit as an explicit graph with predicate/abstraction nodes, entity nodes, typed role/derivation edges, and validated memory annotations. Encode closures and query probes as typed top-level records. Decode the graph back into `MemoryRepresentationBundle` without storing an opaque copy of the original bundle.

**Tech Stack:** Python 3.13, Pydantic v2, deterministic JSON, existing representation conformance harness and pytest.

---

### Task 1: RED tests for graph shape and semantic roles

**Files:**
- Create: `tools/natural_memory_benchmark/extended_amr_adapter.py`
- Create: `tests/natural_memory_benchmark/test_extended_amr_adapter.py`

Write failing tests that require:

- payload schema `extended-amr-memory-graph-v1`;
- no opaque `l1_units` or `l2_units` copy in the payload;
- explicit predicate and entity nodes;
- explicit `ARG0`, `ARG1`, `condition`, and `concession` edges;
- polarity, modality, time, source, epistemic, lifecycle, and evidence annotations;
- exact bundle round-trip.

Run the focused test and confirm import failure.

### Task 2: Minimal encoder/decoder

Implement `ExtendedAmrJsonAdapter` with:

```python
class ExtendedAmrJsonAdapter:
    profile: RepresentationProfile
    def encode(self, bundle: MemoryRepresentationBundle) -> bytes: ...
    def decode(self, payload: Any) -> MemoryRepresentationBundle: ...
```

The decoder must reconstruct models from explicit graph nodes/edges and typed top-level records. Missing nodes, duplicate role edges, or absent annotations must fail Pydantic/bundle validation.

Run focused tests and confirm GREEN.

### Task 3: Real-slice conformance comparison

**Files:**
- Modify: `tools/natural_memory_benchmark/representation_conformance_runner.py`
- Modify: `tests/natural_memory_benchmark/test_representation_conformance_runner.py`

Add an `extended_amr_candidate` report. It must:

- round-trip exactly;
- preserve all five scoped query results;
- remain `authoritative_ready=false` until raw-source revision binding, immutable lifecycle revision, structured L2 semantics, and closure-evaluation versioning are implemented;
- make no quality, efficiency, or benchmark superiority claim.

Generate a new immutable conformance artifact version after verification.
