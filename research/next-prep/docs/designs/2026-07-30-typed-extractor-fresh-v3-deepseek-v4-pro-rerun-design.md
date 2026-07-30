# Typed Extractor Fresh-V3 DeepSeek-V4-Pro Rerun Design

## Status

Approved by the user on 2026-07-30 after the original `deepseek-chat` run was
frozen as `incomplete_not_qualified`. The user explicitly authorized a new
formal test with `deepseek-v4-pro`. This design does not reopen, retry, append
to, or overwrite the original qualification.

## Goal

Measure fresh-v3 automatic L1/L2 extraction quality by issuing exactly one
public-only, no-history request per layer with the available
`deepseek-v4-pro` model, freezing both proposal chains before scoring, and
publishing an independent raw/gated qualification conclusion. Stop after that
conclusion.

## Root Cause And Basis

The original requested alias `deepseek-chat` failed twice with HTTP 403 before
raw response bytes existed. A probe containing no evaluation data proved that
the runtime key is valid: model listing and a minimal `deepseek-v4-pro` request
returned HTTP 200, while `deepseek-chat` returned
`key_model_access_denied`. Commit `252e3d9` records the immutable original
failure and its `incomplete_not_qualified` conclusion.

## Isolation

The rerun uses a sibling result root:

```text
artifacts/automatic-extraction-assessment/
  typed-extractor-v3-fresh-hidden-v1-deepseek-v4-pro-rerun-v1/
```

The original evaluation root remains unchanged. The rerun result root stores
only its dispatch, raw response, proposals, provenance, receipts, scores,
reports, qualifications, and overall chronology. It references the original
read-only prompt/public/materialization files by exact path and SHA-256 rather
than copying or regenerating hidden inputs. Scoring reads the unchanged
authority/gold only after both proposal-freeze receipts validate.

The new chronology binds commit `252e3d9`, the old overall chronology and
failure receipts, the original materialization chronology, exact input hashes,
the rerun controller and tests, and all generated result hashes.

## Execution Contract

1. Validate that the original materialization and failed qualification replay,
   all source inputs remain immutable, protected parallel files have not
   drifted, the Git index is empty, and the sibling result root is absent.
2. Freeze L1 and L2 dispatches before any model call. Each dispatch identifies
   requested model `deepseek-v4-pro`, the exact prompt/public pair, no history,
   and no authority/gold access.
3. Execute one L1 and one L2 request. There is no retry, fallback, replacement
   model, response edit, or second run. Preserve a failure receipt if either
   operation fails.
4. On two valid proposal freezes, start a separate credential-free scoring
   phase against the original frozen authority/gold and existing preregistered
   thresholds.
5. Freeze raw proposer metrics, deterministic gate safety, layer decisions,
   and the overall conclusion. Keep all nine automatic write counts at zero.
6. Validate and commit the result, then stop without integration, query,
   ontology, closure, aggregation, benchmark expansion, cleanup, or packaging.

## Qualification

The metric contract remains identical to the original fresh-v3 preregistration:
all 14 L1 and 12 L2 raw quality metrics must equal `1.0`; raw critical false
emission, gate intervention, and deterministic critical false materialization
must each equal `0`. Raw proposer quality and deterministic gate safety are
reported separately.

The result is `qualified` only when both layers satisfy both contracts. Any
measured metric failure is `not_qualified`; a transport or proposal-freeze
failure is `incomplete_not_qualified`. A result authorizes no authoritative
memory write or pipeline integration.

## Minimal Implementation

Add one rerun-specific controller and focused tests. Reuse the existing request,
proposal-freeze, scorer, and qualification data models where their contracts
match. Parameterize only the locations/model identifiers that differ; do not
generalize unrelated harness behavior or alter historical validators. The
controller owns the sibling layout and its replay validator so the old root
continues to validate independently.

## Verification

Before transport, run focused fake-opener tests plus the existing fresh-v3
controller/qualification/scorer tests. After scoring, run the rerun validator,
credential scan, mode/hash audit, focused extraction tests, static checks, and
staged-set audit. Existing dependency/path failures outside this focused scope
do not block the user-prioritized formal measurement unless they show drift in
the extraction contract or protected state.

## Self-Review

- No placeholder, retry, fallback, hidden tuning, or overwrite path remains.
- Original and rerun conclusions have separate immutable roots and chronology.
- The model replacement is explicit; results apply to `deepseek-v4-pro`, not
  to the originally preregistered unavailable alias.
- Scope is restricted to extraction evaluation and its fact sources.
