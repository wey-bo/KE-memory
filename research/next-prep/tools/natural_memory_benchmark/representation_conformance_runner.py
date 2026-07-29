from __future__ import annotations

from pathlib import Path
from typing import Any

from .extended_amr_adapter import ExtendedAmrJsonAdapter
from .io import write_json_immutable, write_text_immutable
from .representation_contract import (
    REQUIRED_MEMORY_CAPABILITIES,
    CapabilityDeclaration,
    MemoryRepresentationBundle,
    NativeSemanticIrJsonAdapter,
    RepresentationProfile,
    assess_bundle_integrity,
    evaluate_adapter_conformance,
)
from .semantic_ir import evaluate_closure, execute_query
from .semantic_ir_slice_runner import build_real_slice_diagnostic_suite


def _reference_profile() -> RepresentationProfile:
    support = {
        "stable_identity": ("native", "semantic_ir.unit_id and bundle ids"),
        "raw_source_revision_binding": ("unsupported", "source revision hash and raw span verification pending"),
        "event_role_semantics": ("native", "Predicate and RoleBinding"),
        "evidence_traceability": ("native", "SourceBinding.evidence_spans"),
        "source_epistemics": ("native", "SourceBinding and EpistemicBinding"),
        "temporal_semantics": ("extension", "TimeBinding string fields; structured intervals pending"),
        "lifecycle_and_revision": ("unsupported", "lifecycle exists; immutable revision history pending"),
        "cross_layer_provenance": ("extension", "L2 source ids exist; structured L2 claims pending"),
        "structured_l2_semantics": ("unsupported", "L2 assertions are display strings rather than typed claims"),
        "evidence_closure": ("extension", "ClosureRecord; versioned spec/evaluation split pending"),
        "closure_evaluation_versioning": ("unsupported", "closure spec/evaluation versioning and stale detection pending"),
        "constraint_execution": ("extension", "focused executor; full time/modality/polarity execution pending"),
        "versioned_round_trip": ("native", "strict versioned Pydantic JSON bundle"),
        "guarded_fallback": ("native", "structural fallback policy in closure execution"),
    }
    return RepresentationProfile(
        representation_id="semantic-ir-native-reference-carrier",
        family="semantic_ir",
        format_version="memory-representation-bundle-v2",
        role="reference_carrier",
        capabilities=[
            CapabilityDeclaration(
                capability=capability,
                support_mode=support[capability][0],  # type: ignore[arg-type]
                location=support[capability][1],
            )
            for capability in REQUIRED_MEMORY_CAPABILITIES
        ],
    )


def _extended_amr_profile() -> RepresentationProfile:
    support = {
        "stable_identity": ("native", "stable graph, node, edge, unit, closure, and query ids"),
        "raw_source_revision_binding": (
            "unsupported",
            "raw source revision hash and verified source ledger binding pending",
        ),
        "event_role_semantics": ("native", "predicate, entity, and typed role graph edges"),
        "evidence_traceability": ("extension", "typed source and evidence annotations"),
        "source_epistemics": ("extension", "typed source and epistemic annotations"),
        "temporal_semantics": ("extension", "typed memory annotations; structured intervals pending"),
        "lifecycle_and_revision": (
            "unsupported",
            "lifecycle annotation exists; immutable revision records pending",
        ),
        "cross_layer_provenance": ("extension", "typed L2 derivation and source reference edges"),
        "structured_l2_semantics": (
            "unsupported",
            "L2 abstraction node still carries summary and display assertion strings",
        ),
        "evidence_closure": ("extension", "typed top-level closure records"),
        "closure_evaluation_versioning": (
            "unsupported",
            "closure policy/input revision and stale evaluation detection pending",
        ),
        "constraint_execution": ("sidecar", "representation-independent scoped query executor"),
        "versioned_round_trip": ("native", "strict graph payload and exact logical bundle decode"),
        "guarded_fallback": ("sidecar", "representation-independent closure fallback policy"),
    }
    return RepresentationProfile(
        representation_id="extended-amr-memory-graph-candidate-v1",
        family="extended_amr",
        format_version="extended-amr-memory-graph-v1",
        role="authoritative_candidate",
        capabilities=[
            CapabilityDeclaration(
                capability=capability,
                support_mode=support[capability][0],  # type: ignore[arg-type]
                location=support[capability][1],
            )
            for capability in REQUIRED_MEMORY_CAPABILITIES
        ],
    )


def build_real_slice_representation_bundle(
    root: Path,
    slice_id: str,
    results_path: Path,
) -> MemoryRepresentationBundle:
    cases = build_real_slice_diagnostic_suite(root, slice_id, results_path)
    l1_units = [unit for case in cases for unit in case.l1_units]
    l2_units = [unit for case in cases for unit in case.l2_units]
    query_plans = [case.plan for case in cases]
    materialized_closures = []
    for case in cases:
        query_result = execute_query(case.plan, case.l1_units, case.l2_units, case.closures)
        available_ids = set(query_result.matched_unit_ids)
        materialized_closures.extend(
            evaluate_closure(closure, available_ids) for closure in case.closures
        )
    return MemoryRepresentationBundle(
        bundle_id=f"{slice_id}-real-slice-representation-probes-v1",
        profile=_reference_profile(),
        l1_units=l1_units,
        l2_units=l2_units,
        closures=materialized_closures,
        query_plans=query_plans,
        query_unit_scopes={
            case.plan.query_id: [
                *[unit.unit_id for unit in case.l1_units],
                *[unit.unit_id for unit in case.l2_units],
            ]
            for case in cases
        },
        metadata={
            "scope": "hand-authored real slice representation probes",
            "slice_id": slice_id,
            "source_results": str(results_path),
            "item_ids": [case.item_id for case in cases],
        },
    )


def run_representation_conformance(
    root: Path,
    slice_id: str,
    results_path: Path,
    *,
    run_id: str,
) -> dict[str, Any]:
    bundle = build_real_slice_representation_bundle(root, slice_id, results_path)
    integrity = assess_bundle_integrity(bundle)
    adapter = NativeSemanticIrJsonAdapter(profile=bundle.profile)
    report = evaluate_adapter_conformance(adapter, bundle)
    extended_amr = evaluate_adapter_conformance(
        ExtendedAmrJsonAdapter(profile=_extended_amr_profile()),
        bundle,
    )
    return {
        "schema_version": "representation-conformance-run-v4",
        "run_id": run_id,
        "slice_id": slice_id,
        "scope": "representation conformance only; hand-authored IR; no model extraction; no final storage selection",
        "bundle": {
            "bundle_id": bundle.bundle_id,
            "profile": bundle.profile.model_dump(mode="json"),
            "integrity": integrity.model_dump(mode="json"),
        },
        "reference_carrier": report.model_dump(mode="json"),
        "extended_amr_candidate": extended_amr.model_dump(mode="json"),
        "interpretation": {
            "selected_storage": None,
            "keol_role": "optional adapter",
            "extended_amr_role": "authoritative candidate that has not passed all hard capabilities",
            "next_candidate": "complete missing contract capabilities or test another typed graph profile",
        },
    }


def render_representation_conformance_report(payload: dict[str, Any]) -> str:
    report = payload["reference_carrier"]
    unsupported = ", ".join(f"`{item}`" for item in report["unsupported_capabilities"]) or "none"
    extended_amr = payload["extended_amr_candidate"]
    amr_unsupported = (
        ", ".join(f"`{item}`" for item in extended_amr["unsupported_capabilities"]) or "none"
    )
    amr_failures = ", ".join(f"`{item}`" for item in extended_amr["hard_gate_failures"]) or "none"
    return "\n".join(
        [
            "# Representation Conformance Report",
            "",
            f"Run: `{payload['run_id']}`",
            "",
            "Scope: representation conformance only; hand-authored IR; no model extraction; no final storage selection.",
            "",
            "## Reference carrier",
            "",
            f"- Status: `{report['status']}`",
            f"- Exact round-trip: `{report['round_trip_exact']}`",
            f"- Query probes: `{report['query_probe_pass_count']}/{report['query_probe_count']}`",
            f"- Bundle integrity: `{report['integrity_valid']}`",
            f"- Authoritative ready: `{report['authoritative_ready']}`",
            f"- Unsupported authoritative capabilities: {unsupported}",
            "",
            "## Extended AMR candidate",
            "",
            f"- Status: `{extended_amr['status']}`",
            f"- Exact round-trip: `{extended_amr['round_trip_exact']}`",
            f"- Query probes: `{extended_amr['query_probe_pass_count']}/{extended_amr['query_probe_count']}`",
            f"- Bundle integrity: `{extended_amr['integrity_valid']}`",
            f"- Authoritative ready: `{extended_amr['authoritative_ready']}`",
            f"- Hard-gate failures: {amr_failures}",
            f"- Unsupported authoritative capabilities: {amr_unsupported}",
            "",
            "## Interpretation",
            "",
            "The native Semantic IR JSON is a passing reference carrier for these five probes, not the selected production database.",
            "It is not authoritative-ready because immutable revision history is still missing and several capabilities remain extensions rather than fully executed native semantics.",
            "The extended AMR graph preserves the same bundle and query results, but it is not authoritative-ready because four hard memory capabilities remain unsupported.",
            "KEOL, extended AMR, or another representation must pass the same complete contract before storage selection.",
            "",
        ]
    )


def run_representation_conformance_file(
    root: Path,
    slice_id: str,
    results_path: Path,
    output_path: Path,
    report_path: Path,
    *,
    run_id: str,
) -> dict[str, Any]:
    payload = run_representation_conformance(
        root,
        slice_id,
        results_path,
        run_id=run_id,
    )
    write_json_immutable(output_path, payload)
    write_text_immutable(report_path, render_representation_conformance_report(payload))
    return payload
