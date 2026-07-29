# Typed Extractor Diagnostic Public Contract V2

## Problem

The frozen L1 V6 and L2 V8 proposer prompts require public operator-kind and
operator-role bindings. L1 also requires modality, condition, scope, and time
policy catalogs. The frozen diagnostic v1 public payloads omit those catalogs,
and L1 also omits one emitted operator/sense. Two L2 gold closure values conflict
with the unchanged V8 rule that non-lifecycle multi-turn bundles use
`multi_evidence_set`.

Calling a model on v1 would mix an input-contract defect into proposer-quality
metrics. No v1 dispatch or model request was created.

## Decision

Keep both v1 roots immutable as preflight-rejected audit artifacts. Create L1
and L2 v2 roots with the same diagnostic-authored cases, new dataset IDs and new
opaque namespaces. Author all prompt-required catalogs explicitly in each v2
source. Do not derive catalogs from authority or gold at model-run time.

For L2 v2, change only the `emit-task-composition-release` and
`emit-state-summary` closure expectations from `temporal_chain` to
`multi_evidence_set`, including matching authority fields. This aligns the
diagnostic contract with frozen prompt V8; it does not change production closure
semantics.

## Validation

The adapters accept v1 and v2 explicitly. V2 validation rejects missing prompt
catalogs and rejects any emitted operator, sense, kind, role, qualifier operator,
or time binding not represented in the public catalog. It also enforces the V8
abstraction-to-closure mapping. Existing v1 replay must remain byte-identical.

The proposer still receives only frozen prompt plus public JSON. Proposals and
provenance freeze before scoring reads authority/gold. Raw proposer quality and
deterministic gate safety remain separate, and all authoritative writes remain
zero.

