# Repository Structure And CI/CD Foundation Implementation Plan

**Goal:** Separate core, service, and ontology packages while preserving compatibility and add a
repeatable CI/CD baseline.

**Architecture:** Keep the memory core under `src/ke_memory_demo`, move delivery adapters into
`service/ke_memory_service`, and move ontology adapters into `ontology/ke_memory_ontology`.
Compatibility modules preserve existing imports during migration.

**Tech Stack:** Python 3.12, Pydantic 2, FastAPI, SQLite, Hatchling, uv, pytest, Ruff, Pyright,
GitHub Actions, Docker.

---

### Task 1: Lock Package Boundaries

**Files:**
- Create: `tests/architecture/test_package_boundaries.py`
- Modify: `pyproject.toml`

1. Add failing tests for the three import roots and forbidden dependency directions.
2. Run the focused tests and verify RED.
3. Configure Hatch and Pyright for the three package roots.
4. Add minimal package initializers and verify GREEN.

### Task 2: Move Ontology Adapters

**Files:**
- Create: `ontology/ke_memory_ontology/`
- Modify: `src/ke_memory_demo/ontology/`
- Modify: `src/ke_memory_demo/online/keol_bridge.py`

1. Add tests importing ontology models, Elasticsearch adapter, and KEOL compiler from the new
   package.
2. Move the implementations and retain compatibility facades.
3. Run ontology, extraction, pipeline, snapshot, and KEOL contract tests.

### Task 3: Move Service Delivery

**Files:**
- Create: `service/ke_memory_service/api.py`
- Create: `service/ke_memory_service/runtime.py`
- Create: `service/ke_memory_service/mcp.py`
- Create: `service/ke_memory_service/identity.py`
- Modify: `src/ke_memory_demo/online/api.py`
- Modify: `src/ke_memory_demo/online/factory.py`

1. Add failing tests for new imports, MCP delegation, and principal registration.
2. Move API/runtime implementations and preserve old entry points as facades.
3. Implement an SDK-neutral MCP facade and deterministic in-memory principal registry.
4. Run focused service and API integration tests.

### Task 4: Add CI/CD Baseline

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `scripts/ci/check.sh`
- Create: `scripts/ci/verify_layout.py`
- Create: `Dockerfile`
- Create: `.dockerignore`
- Create: `Makefile`
- Modify: `README.md`

1. Add tests for layout validation and package installation.
2. Implement the vendor-neutral check script and GitHub workflow.
3. Add a locked, non-root production image with persistent state directory and healthcheck.
4. Document CI, packaging, service startup, and persistence expectations.

### Task 5: Full Verification

1. Run focused architecture/service/ontology tests.
2. Run the full pytest suite with fixed KEOL source.
3. Run Ruff and Pyright.
4. Build the wheel and inspect that all three packages are included.
5. Run `git diff --check` and secret-hygiene tests.

