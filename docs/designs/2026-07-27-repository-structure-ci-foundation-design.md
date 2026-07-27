# Repository Structure And CI/CD Foundation Design

Date: 2026-07-27

Status: implementation target

## Goal

Separate the durable memory core, service delivery, and ontology profiles without changing the
existing public behavior. Prepare the repository for repeatable testing, packaging, containers,
and persistent deployment.

## Boundaries

The repository will use three physical Python package roots:

```text
src/ke_memory_demo/             core memory domain and pipelines
service/ke_memory_service/      HTTP/MCP/runtime/identity delivery layer
ontology/ke_memory_ontology/    ontology contracts and representation adapters
```

The core owns extraction, admission, lifecycle, storage, retrieval, evidence, snapshots, and
representation-neutral ports. The service layer may depend on core and ontology packages. The
ontology layer may implement core ports, but must not depend on service code. Existing
`ke_memory_demo.online.api`, `ke_memory_demo.online.factory`, and `ke_memory_demo.ontology`
imports remain compatibility facades during this migration.

The old Fusion Memory repository remains out of scope. No code, tests, schemas, or algorithms are
read or reused from it.

## Service Layer

`ke_memory_service` owns the FastAPI application, runtime composition, and an SDK-neutral MCP
facade exposing add/search/context/get/correct/forget operations. It also defines principal
registration contracts for tenant, user, agent, and service identities. Registration persistence
and authentication enforcement remain explicit extension points rather than hidden defaults.

## Ontology Layer

`ke_memory_ontology` owns the existing Elasticsearch vocabulary adapter and the KEOL materialized
view compiler. KEOL remains a profile, not the canonical persistent schema. The semantic memory
core continues to retain raw evidence, provenance, lifecycle, and revisions independently of any
one ontology projection.

## CI/CD Foundation

CI uses one vendor-neutral entry point, `scripts/ci/check.sh`, which runs lock verification,
layout checks, unit/integration tests, Ruff, Pyright, and wheel build. GitHub Actions invokes the
same script. A multi-stage Dockerfile builds the locked production environment and runs the
service as a non-root user with a writable `/var/lib/ke-memory` volume.

The first deployment gate is intentionally offline: container health and persistence plumbing
must work without model or Elasticsearch credentials. Production extraction remains fail-closed.

## Acceptance Criteria

- New service and ontology imports work from an installed wheel.
- Existing import paths and API tests remain green.
- Package direction rules reject service imports from core and service imports from ontology.
- MCP facade delegates through the current service/retriever contracts without bypassing namespace
  or evidence rules.
- Principal registration has stable identity and duplicate-registration semantics.
- CI, wheel build, and offline container smoke use reproducible commands.

