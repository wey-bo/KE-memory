# Representation Conformance Harness Implementation Plan

**Goal:** Build a representation-agnostic conformance harness that tests whether Semantic IR, KEOL, extended AMR, or another format can losslessly preserve and execute the required memory semantics.

**Architecture:** Keep `semantic_ir.py` as the logical test carrier, not a mandatory database schema. Add a versioned bundle, capability profile, integrity validator, adapter round-trip protocol, and conformance report. Assess the native Semantic IR carrier and the existing KEOL projection independently.

**Tech Stack:** Python 3.13, Pydantic v2, pytest, deterministic JSON, existing natural benchmark diagnostic fixtures.

---

### Task 1: Representation profile and bundle contracts

**Files:**
- Create: `tools/natural_memory_benchmark/representation_contract.py`
- Create: `tests/natural_memory_benchmark/test_representation_contract.py`

**Step 1: Write failing tests**

Add tests that import:

```python
from tools.natural_memory_benchmark.representation_contract import (
    MemoryRepresentationBundle,
    RepresentationProfile,
    assess_bundle_integrity,
)
```

The tests must verify:

- duplicate L1/L2/closure/query IDs are rejected;
- L2 abstracts and provenance must reference existing L1 units;
- active L2 units require an existing complete closure;
- closure and query references must resolve;
- lifecycle links must resolve to existing memory units;
- conflicting duplicate evidence definitions are rejected.

**Step 2: Verify RED**

Run:

```powershell
D:\Anaconda\python.exe -m pytest tests\natural_memory_benchmark\test_representation_contract.py -q --import-mode=importlib -p no:cacheprovider --basetemp .t\bm-representation-contract-red
```

Expected: import error for `representation_contract`.

**Step 3: Implement minimal contracts**

Implement strict frozen Pydantic models:

```python
class CapabilityDeclaration(StrictModel):
    capability: MemoryCapability
    support_mode: SupportMode
    location: str

class RepresentationProfile(StrictModel):
    representation_id: str
    family: RepresentationFamily
    format_version: str
    role: RepresentationRole
    capabilities: list[CapabilityDeclaration]

class MemoryRepresentationBundle(StrictModel):
    schema_version: Literal["memory-representation-bundle-v2"]
    bundle_id: str
    profile: RepresentationProfile
    l1_units: list[L1MemoryUnit]
    l2_units: list[L2MemoryUnit]
    closures: list[ClosureRecord]
    query_plans: list[QuerySlotPlan]
    query_unit_scopes: dict[str, list[str]]
    metadata: dict[str, Any]
```

Add `assess_bundle_integrity(bundle) -> BundleIntegrityReport` and model-level uniqueness validation.

**Step 4: Verify GREEN**

Run the focused test command and expect pass.

### Task 2: Exact round-trip and semantic query equivalence

**Files:**
- Modify: `tools/natural_memory_benchmark/representation_contract.py`
- Modify: `tests/natural_memory_benchmark/test_representation_contract.py`

**Step 1: Write failing tests**

Add tests for:

- native deterministic JSON encode/decode is exact;
- dropping predicate sense fails round-trip conformance;
- dropping evidence metadata fails round-trip conformance;
- decoded query results equal reference query results for every query plan;
- incomplete causal closure still abstains and cannot trigger fallback after round-trip.

**Step 2: Verify RED**

Run the focused tests and confirm missing adapter/evaluator failures.

**Step 3: Implement minimal adapter protocol**

Add:

```python
class RepresentationAdapter(Protocol):
    profile: RepresentationProfile
    def encode(self, bundle: MemoryRepresentationBundle) -> Any: ...
    def decode(self, payload: Any) -> MemoryRepresentationBundle: ...

class NativeSemanticIrJsonAdapter:
    ...

def evaluate_adapter_conformance(
    adapter: RepresentationAdapter,
    bundle: MemoryRepresentationBundle,
) -> RepresentationConformanceReport:
    ...
```

The evaluator compares canonical JSON, runs `execute_query` before and after round-trip, and reports hard-gate failures without mutating the bundle.

**Step 4: Verify GREEN**

Run the focused tests and expect pass.

### Task 3: Real-slice reference bundle and report

**Files:**
- Create: `tools/natural_memory_benchmark/representation_conformance_runner.py`
- Create: `tests/natural_memory_benchmark/test_representation_conformance_runner.py`
- Modify: `tools/natural_memory_benchmark/cli.py`

**Step 1: Write failing tests**

Build a bundle from `build_real_slice_diagnostic_suite(...)` and assert:

- closures are materialized with `evaluate_closure` before persistence;
- the native carrier round-trips exactly;
- all five real-slice query probes reproduce their existing IR results;
- report scope explicitly says no model extraction and no final storage selection;
- CLI writes immutable JSON and Markdown artifacts.

**Step 2: Verify RED**

Run the new runner tests and confirm import/CLI failures.

**Step 3: Implement the runner**

Add:

```python
def build_real_slice_representation_bundle(...): ...
def run_representation_conformance(...): ...
def render_representation_conformance_report(...): ...
def run_representation_conformance_file(...): ...
```

Add CLI command `run-representation-conformance`.

**Step 4: Verify GREEN**

Run focused tests and expect pass.

### Task 4: KEOL optional-adapter assessment

**Files:**
- Create: `tools/natural_memory_benchmark/semantic_ir_keol_validate.py`
- Create: `tests/natural_memory_benchmark/test_semantic_ir_keol_validate.py`
- Modify: `tools/natural_memory_benchmark/cli.py`

**Step 1: Write failing tests**

Tests must verify:

- current projection parses with KEOL `Concept`, `Individual`, `Operator`, `Assertion`, `Evidence`, and `WorkflowRun` models;
- broken assertion/evidence/operator/individual references fail validation;
- KEOL remains `projection_only` because reverse decoding and exact round-trip are not implemented;
- metadata presence alone is not counted as native executable support.

**Step 2: Verify RED**

Run focused tests and confirm missing validator failures.

**Step 3: Implement minimal validation**

Load the local KEOL `models.py` by explicit path, validate each object with its native Pydantic class, then validate all cross-object references. Return a machine-readable adapter assessment instead of mutating the KEOL baseline.

**Step 4: Verify GREEN**

Run focused tests and expect pass.

### Task 5: Artifacts, status documents, and verification

**Files:**
- Create: `artifacts/natural-benchmark-slices/slice-v1/representation-conformance-results-v3.json`
- Create: `artifacts/natural-benchmark-slices/slice-v1/representation-conformance-report-v3.md`
- Create: `artifacts/natural-benchmark-slices/slice-v1/semantic-ir-keol-native-validation.json`
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `安排.md`

**Step 1: Generate formal artifacts**

Run the new CLI commands with fixed run IDs and immutable output paths.

**Step 2: Update status**

Record that:

- the architecture now uses a representation-agnostic capability contract;
- native Semantic IR is a reference carrier, not the selected database;
- KEOL is an optional projection adapter pending reverse round-trip and runtime query proof;
- extended AMR is the next candidate adapter;
- no model extraction or full benchmark claim is made in this wave.

**Step 3: Verify**

Run:

```powershell
D:\Anaconda\python.exe -m pytest tests\natural_memory_benchmark\test_representation_contract.py tests\natural_memory_benchmark\test_representation_conformance_runner.py tests\natural_memory_benchmark\test_semantic_ir_keol_validate.py -q --import-mode=importlib -p no:cacheprovider --basetemp .t\bm-representation-focused
D:\Anaconda\python.exe -m pytest tests\natural_memory_benchmark -q --import-mode=importlib -p no:cacheprovider --basetemp .t\bm-representation-all
D:\Anaconda\python.exe -m tools.natural_memory_benchmark.cli validate-slice --root artifacts\natural-benchmark-slices --slice-id slice-v1
D:\Anaconda\python.exe -m tools.natural_memory_benchmark.cli validate-ledger --path artifacts\natural-benchmark-slices\external-results-ledger.json
```

## Acceptance criteria

- No physical representation is silently treated as the architecture contract.
- Broken cross-layer, evidence, lifecycle, closure, or adapter references fail deterministically.
- Native Semantic IR JSON passes exact round-trip and semantic query equivalence on the five real-slice probes.
- KEOL projection is validated with native models and honestly classified by current capability.
- Embedding remains blocked from repairing structural closure failures.
- The report identifies extended AMR as a candidate to test, not a predetermined winner.
