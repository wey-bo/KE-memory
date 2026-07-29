from __future__ import annotations

import json
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .io import canonical_json_bytes
from .semantic_ir import ClosureRecord, L1MemoryUnit, L2MemoryUnit, QuerySlotPlan, execute_query


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


MemoryCapability = Literal[
    "stable_identity",
    "raw_source_revision_binding",
    "event_role_semantics",
    "evidence_traceability",
    "source_epistemics",
    "temporal_semantics",
    "lifecycle_and_revision",
    "cross_layer_provenance",
    "structured_l2_semantics",
    "evidence_closure",
    "closure_evaluation_versioning",
    "constraint_execution",
    "versioned_round_trip",
    "guarded_fallback",
]
SupportMode = Literal["native", "extension", "sidecar", "unsupported"]
RepresentationFamily = Literal["semantic_ir", "extended_amr", "keol", "property_graph", "other"]
RepresentationRole = Literal["reference_carrier", "authoritative_candidate", "projection_only", "exchange"]


REQUIRED_MEMORY_CAPABILITIES: tuple[MemoryCapability, ...] = (
    "stable_identity",
    "raw_source_revision_binding",
    "event_role_semantics",
    "evidence_traceability",
    "source_epistemics",
    "temporal_semantics",
    "lifecycle_and_revision",
    "cross_layer_provenance",
    "structured_l2_semantics",
    "evidence_closure",
    "closure_evaluation_versioning",
    "constraint_execution",
    "versioned_round_trip",
    "guarded_fallback",
)


class CapabilityDeclaration(StrictModel):
    capability: MemoryCapability
    support_mode: SupportMode
    location: str = Field(min_length=1)


class RepresentationProfile(StrictModel):
    representation_id: str = Field(min_length=1)
    family: RepresentationFamily
    format_version: str = Field(min_length=1)
    role: RepresentationRole
    capabilities: list[CapabilityDeclaration]

    @model_validator(mode="after")
    def validate_unique_capabilities(self) -> "RepresentationProfile":
        names = [item.capability for item in self.capabilities]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise ValueError(f"duplicate capability declarations: {duplicates}")
        return self


class MemoryRepresentationBundle(StrictModel):
    schema_version: Literal["memory-representation-bundle-v2"] = "memory-representation-bundle-v2"
    bundle_id: str = Field(min_length=1)
    profile: RepresentationProfile
    l1_units: list[L1MemoryUnit]
    l2_units: list[L2MemoryUnit]
    closures: list[ClosureRecord]
    query_plans: list[QuerySlotPlan]
    query_unit_scopes: dict[str, list[str]] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_unique_ids(self) -> "MemoryRepresentationBundle":
        unit_ids = [unit.unit_id for unit in self.l1_units] + [unit.unit_id for unit in self.l2_units]
        duplicate_units = sorted({unit_id for unit_id in unit_ids if unit_ids.count(unit_id) > 1})
        if duplicate_units:
            raise ValueError(f"duplicate memory unit ids: {duplicate_units}")
        closure_ids = [closure.closure_id for closure in self.closures]
        duplicate_closures = sorted(
            {closure_id for closure_id in closure_ids if closure_ids.count(closure_id) > 1}
        )
        if duplicate_closures:
            raise ValueError(f"duplicate closure ids: {duplicate_closures}")
        query_ids = [plan.query_id for plan in self.query_plans]
        duplicate_queries = sorted({query_id for query_id in query_ids if query_ids.count(query_id) > 1})
        if duplicate_queries:
            raise ValueError(f"duplicate query ids: {duplicate_queries}")
        return self


class BundleIntegrityReport(StrictModel):
    schema_version: Literal["memory-representation-integrity-report-v1"] = (
        "memory-representation-integrity-report-v1"
    )
    bundle_id: str
    valid: bool
    errors: list[str]
    metrics: dict[str, int]


class QueryProbeComparison(StrictModel):
    query_id: str
    passed: bool
    reference_result: dict[str, Any]
    decoded_result: dict[str, Any]


class RepresentationConformanceReport(StrictModel):
    schema_version: Literal["memory-representation-conformance-report-v1"] = (
        "memory-representation-conformance-report-v1"
    )
    representation_id: str
    representation_role: RepresentationRole
    bundle_id: str
    status: Literal["pass", "fail"]
    integrity_valid: bool
    decoded_integrity_valid: bool
    round_trip_exact: bool
    query_probe_count: int
    query_probe_pass_count: int
    query_probes: list[QueryProbeComparison]
    hard_gate_failures: list[str]
    unsupported_capabilities: list[MemoryCapability]
    authoritative_ready: bool


def _duplicate_evidence_errors(bundle: MemoryRepresentationBundle) -> list[str]:
    definitions: dict[str, tuple[Any, ...]] = {}
    errors: list[str] = []
    for unit in bundle.l1_units:
        for span in unit.source.evidence_spans:
            definition = (
                span.turn_id,
                span.session_id,
                span.char_start,
                span.char_end,
                span.text,
            )
            existing = definitions.get(span.evidence_id)
            if existing is None:
                definitions[span.evidence_id] = definition
            elif existing != definition:
                errors.append(f"evidence {span.evidence_id} has conflicting definitions")
    return errors


def assess_bundle_integrity(bundle: MemoryRepresentationBundle) -> BundleIntegrityReport:
    errors: list[str] = []
    l1_by_id = {unit.unit_id: unit for unit in bundle.l1_units}
    l2_by_id = {unit.unit_id: unit for unit in bundle.l2_units}
    all_unit_ids = set(l1_by_id) | set(l2_by_id)
    closure_by_id = {closure.closure_id: closure for closure in bundle.closures}
    query_by_id = {plan.query_id: plan for plan in bundle.query_plans}

    errors.extend(_duplicate_evidence_errors(bundle))

    for unit in bundle.l1_units:
        for span in unit.source.evidence_spans:
            if span.char_end > len(span.text):
                errors.append(
                    f"evidence {span.evidence_id} char_end {span.char_end} exceeds quote length {len(span.text)}"
                )
        for link_name in ("same_as", "supersedes", "conflicts_with", "derived_from"):
            for target_id in getattr(unit.links, link_name):
                if target_id not in all_unit_ids:
                    errors.append(f"l1 {unit.unit_id} {link_name} references missing unit {target_id}")

    for unit in bundle.l2_units:
        for source_id in dict.fromkeys([*unit.abstracts, *unit.source_l1_units]):
            if source_id not in l1_by_id:
                errors.append(f"l2 {unit.unit_id} references missing L1 unit {source_id}")
        closure = closure_by_id.get(unit.closure_id)
        if closure is None:
            errors.append(f"l2 {unit.unit_id} references missing closure {unit.closure_id}")
        elif unit.lifecycle == "active" and not closure.complete:
            errors.append(f"active l2 {unit.unit_id} has incomplete closure {unit.closure_id}")

        source_units = [l1_by_id[source_id] for source_id in unit.source_l1_units if source_id in l1_by_id]
        expected_turns = {
            span.turn_id for source_unit in source_units for span in source_unit.source.evidence_spans
        }
        expected_sessions = {
            span.session_id for source_unit in source_units for span in source_unit.source.evidence_spans
        }
        missing_turns = sorted(expected_turns - set(unit.source_turns))
        missing_sessions = sorted(expected_sessions - set(unit.source_sessions))
        if missing_turns:
            errors.append(f"l2 {unit.unit_id} provenance misses source turns {missing_turns}")
        if missing_sessions:
            errors.append(f"l2 {unit.unit_id} provenance misses source sessions {missing_sessions}")

    for closure in bundle.closures:
        if closure.complete and closure.missing_slots:
            errors.append(f"closure {closure.closure_id} is complete but still has missing slots")
        for requirement in [*closure.required_units, *closure.optional_units]:
            if requirement.unit_id not in all_unit_ids:
                errors.append(
                    f"closure {closure.closure_id} references missing unit {requirement.unit_id}"
                )
        if closure.claim_or_query_id not in query_by_id and closure.claim_or_query_id not in all_unit_ids:
            errors.append(
                f"closure {closure.closure_id} references missing claim or query {closure.claim_or_query_id}"
            )

    for plan in bundle.query_plans:
        if plan.closure_id is not None:
            closure = closure_by_id.get(plan.closure_id)
            if closure is None:
                errors.append(f"query {plan.query_id} references missing closure {plan.closure_id}")
            elif plan.required_closure_pattern and plan.required_closure_pattern != closure.pattern:
                errors.append(
                    f"query {plan.query_id} closure pattern {plan.required_closure_pattern} does not match {closure.pattern}"
                )
    for query_id, scoped_unit_ids in bundle.query_unit_scopes.items():
        if query_id not in query_by_id:
            errors.append(f"query scope references missing query {query_id}")
        for unit_id in scoped_unit_ids:
            if unit_id not in all_unit_ids:
                errors.append(f"query scope {query_id} references missing unit {unit_id}")

    return BundleIntegrityReport(
        bundle_id=bundle.bundle_id,
        valid=not errors,
        errors=list(dict.fromkeys(errors)),
        metrics={
            "l1_unit_count": len(bundle.l1_units),
            "l2_unit_count": len(bundle.l2_units),
            "closure_count": len(bundle.closures),
            "query_plan_count": len(bundle.query_plans),
            "evidence_span_count": sum(len(unit.source.evidence_spans) for unit in bundle.l1_units),
        },
    )


class RepresentationAdapter(Protocol):
    profile: RepresentationProfile

    def encode(self, bundle: MemoryRepresentationBundle) -> Any: ...

    def decode(self, payload: Any) -> MemoryRepresentationBundle: ...


class NativeSemanticIrJsonAdapter:
    def __init__(self, *, profile: RepresentationProfile) -> None:
        self.profile = profile

    def encode(self, bundle: MemoryRepresentationBundle) -> bytes:
        return canonical_json_bytes(bundle)

    def decode(self, payload: Any) -> MemoryRepresentationBundle:
        if isinstance(payload, dict):
            return MemoryRepresentationBundle.model_validate(payload)
        if isinstance(payload, str):
            payload = payload.encode("utf-8")
        if isinstance(payload, bytes):
            return MemoryRepresentationBundle.model_validate_json(payload)
        raise TypeError(f"unsupported payload type: {type(payload).__name__}")


def _query_results(bundle: MemoryRepresentationBundle) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for plan in bundle.query_plans:
        scope = set(bundle.query_unit_scopes.get(plan.query_id, []))
        l1_units = [unit for unit in bundle.l1_units if not scope or unit.unit_id in scope]
        l2_units = [unit for unit in bundle.l2_units if not scope or unit.unit_id in scope]
        results[plan.query_id] = execute_query(plan, l1_units, l2_units, bundle.closures).model_dump(
            mode="json"
        )
    return results


def _unsupported_capabilities(profile: RepresentationProfile) -> list[MemoryCapability]:
    declared = {item.capability: item.support_mode for item in profile.capabilities}
    return [
        capability
        for capability in REQUIRED_MEMORY_CAPABILITIES
        if declared.get(capability, "unsupported") == "unsupported"
    ]


def evaluate_adapter_conformance(
    adapter: RepresentationAdapter,
    bundle: MemoryRepresentationBundle,
) -> RepresentationConformanceReport:
    failures: list[str] = []
    reference_integrity = assess_bundle_integrity(bundle)
    if not reference_integrity.valid:
        failures.append("reference_bundle_integrity_invalid")

    try:
        encoded = adapter.encode(bundle)
        decoded = adapter.decode(encoded)
    except Exception as exc:
        return RepresentationConformanceReport(
            representation_id=adapter.profile.representation_id,
            representation_role=adapter.profile.role,
            bundle_id=bundle.bundle_id,
            status="fail",
            integrity_valid=reference_integrity.valid,
            decoded_integrity_valid=False,
            round_trip_exact=False,
            query_probe_count=len(bundle.query_plans),
            query_probe_pass_count=0,
            query_probes=[],
            hard_gate_failures=[*failures, f"adapter_error:{type(exc).__name__}"],
            unsupported_capabilities=_unsupported_capabilities(adapter.profile),
            authoritative_ready=False,
        )

    decoded_integrity = assess_bundle_integrity(decoded)
    if not decoded_integrity.valid:
        failures.append("decoded_bundle_integrity_invalid")
    round_trip_exact = canonical_json_bytes(bundle) == canonical_json_bytes(decoded)
    if not round_trip_exact:
        failures.append("round_trip_not_exact")

    reference_results = _query_results(bundle)
    decoded_results = _query_results(decoded)
    query_probes = [
        QueryProbeComparison(
            query_id=query_id,
            passed=decoded_results.get(query_id) == result,
            reference_result=result,
            decoded_result=decoded_results.get(query_id, {}),
        )
        for query_id, result in reference_results.items()
    ]
    if any(not probe.passed for probe in query_probes):
        failures.append("query_semantics_changed")

    unsupported = _unsupported_capabilities(adapter.profile)
    authoritative_ready = not failures and not unsupported and adapter.profile.role == "authoritative_candidate"
    role_requires_all_capabilities = adapter.profile.role == "authoritative_candidate"
    if role_requires_all_capabilities and unsupported:
        failures.append("required_capability_unsupported")

    failures = list(dict.fromkeys(failures))
    return RepresentationConformanceReport(
        representation_id=adapter.profile.representation_id,
        representation_role=adapter.profile.role,
        bundle_id=bundle.bundle_id,
        status="pass" if not failures else "fail",
        integrity_valid=reference_integrity.valid,
        decoded_integrity_valid=decoded_integrity.valid,
        round_trip_exact=round_trip_exact,
        query_probe_count=len(query_probes),
        query_probe_pass_count=sum(1 for probe in query_probes if probe.passed),
        query_probes=query_probes,
        hard_gate_failures=failures,
        unsupported_capabilities=unsupported,
        authoritative_ready=authoritative_ready,
    )
