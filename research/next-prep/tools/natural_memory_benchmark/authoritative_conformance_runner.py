from __future__ import annotations

from pathlib import Path
from typing import Any

from .authoritative_memory import (
    AuthoritativeQueryPlan,
    ClaimClosureContext,
    ClosureEvaluationInputs,
    ClosureSpec,
    ClosureEvaluation,
    MemoryRepresentationBundleV3,
    ProducerIdentity,
    QueryClosureContext,
    assess_authoritative_bundle_integrity,
    build_real_slice_authoritative_bundle,
    canonical_sha256,
    evaluate_closure_spec,
    execute_authoritative_query,
    is_closure_evaluation_fresh,
    matched_claim_ids_for_query,
    validate_authoritative_sources,
)
from .extended_amr_v2_adapter import ExtendedAmrV2JsonAdapter
from .io import canonical_json_bytes, write_json_immutable, write_text_immutable
from .representation_contract import (
    REQUIRED_MEMORY_CAPABILITIES,
    CapabilityDeclaration,
    RepresentationProfile,
)
from .semantic_ir_slice_runner import build_real_slice_diagnostic_suite


FROZEN_CORRECTNESS_EXPECTATIONS: dict[str, dict[str, Any]] = {
    "BEAM-100K-C001-abstention-001": {
        "matched_unit_ids": [
            "l1-beam-feedback-mentioned",
            "l1-beam-ui-ux-improvement-mentioned",
        ],
        "matched_claim_ids": [],
        "required_evidence_ids": [],
        "abstained": True,
        "closure_complete": False,
        "fallback_allowed": False,
        "reason": "missing_required_slot",
    },
    "LONGMEMEVAL-6d550036": {
        "matched_unit_ids": [
            "l1-led-project-1",
            "l1-led-project-2",
            "l1-led-project-3",
            "l1-led-project-4",
            "l2-longmemeval-led-project-count",
        ],
        "matched_claim_ids": ["claim-l2-longmemeval-led-project-count"],
        "required_evidence_ids": [
            "answer_ec904b3c_4",
            "answer_ec904b3c_2",
            "answer_ec904b3c_1",
            "answer_ec904b3c_3",
        ],
        "abstained": True,
        "closure_complete": True,
        "fallback_allowed": False,
        "reason": "structured_l2_identity_unresolved",
    },
    "BEAM-100K-C001-contradiction_resolution-001": {
        "matched_unit_ids": [
            "l1-flask-route-denial",
            "l1-flask-homepage-route-implementation",
        ],
        "matched_claim_ids": [],
        "required_evidence_ids": ["58", "24"],
        "abstained": False,
        "closure_complete": True,
        "fallback_allowed": False,
        "reason": "authoritative_query_complete",
    },
    "BEAM-100K-C001-knowledge_update-002": {
        "matched_unit_ids": [
            "l1-main-branch-commit-count-150",
            "l1-main-branch-commit-count-165",
        ],
        "matched_claim_ids": [],
        "required_evidence_ids": ["148", "182"],
        "abstained": False,
        "closure_complete": True,
        "fallback_allowed": False,
        "reason": "authoritative_query_complete",
    },
    "LONGMEMEVAL-gpt4_2655b836": {
        "matched_unit_ids": [
            "l1-car-first-service",
            "l1-car-first-post-service-issue",
            "l1-car-new-honda-civic-context",
        ],
        "matched_claim_ids": [],
        "required_evidence_ids": [
            "answer_4be1b6b4_2",
            "answer_4be1b6b4_3",
            "answer_4be1b6b4_1",
        ],
        "abstained": False,
        "closure_complete": True,
        "fallback_allowed": False,
        "reason": "authoritative_query_complete",
    },
}
FROZEN_CORRECTNESS_SHA256 = canonical_sha256(FROZEN_CORRECTNESS_EXPECTATIONS)
_PUBLIC_CORRECTNESS_KEYS = (
    "matched_unit_ids",
    "required_evidence_ids",
    "abstained",
    "closure_complete",
    "fallback_allowed",
    "reason",
)


def _reference_profile() -> RepresentationProfile:
    support = {
        "stable_identity": ("native", "v3 logical IDs and immutable content-derived revisions"),
        "raw_source_revision_binding": ("native", "artifact/source revision ledger and exact span hashes"),
        "event_role_semantics": ("native", "typed predicate and role bindings"),
        "evidence_traceability": ("native", "EvidenceSpanV2 -> SourceRecordRevision"),
        "source_epistemics": ("native", "typed source and epistemic bindings"),
        "temporal_semantics": ("extension", "typed TimeBinding; interval algebra remains pending"),
        "lifecycle_and_revision": ("native", "linear immutable unit revision chains"),
        "cross_layer_provenance": ("native", "derived unit revision and claim support links"),
        "structured_l2_semantics": ("native", "typed L2 claims and optional aggregate claims"),
        "evidence_closure": ("native", "executable closure specs and slot results"),
        "closure_evaluation_versioning": ("native", "claim/query contexts, input fingerprints and result hashes"),
        "constraint_execution": ("extension", "typed predicate/role/time/modality executor"),
        "versioned_round_trip": ("native", "strict v3 logical bundle"),
        "guarded_fallback": ("native", "closure fallback classification blocks structural gaps"),
    }
    return RepresentationProfile(
        representation_id="authoritative-memory-v3-reference-carrier",
        family="semantic_ir",
        format_version="memory-representation-bundle-v3",
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


def _extended_profile() -> RepresentationProfile:
    return RepresentationProfile(
        representation_id="extended-amr-memory-graph-candidate-v2",
        family="extended_amr",
        format_version="extended-amr-memory-graph-v2",
        role="authoritative_candidate",
        capabilities=[
            CapabilityDeclaration(
                capability=capability,
                support_mode="extension",
                location="typed Extended-AMR v2 graph or representation-independent executor",
            )
            for capability in REQUIRED_MEMORY_CAPABILITIES
        ],
    )


class NativeAuthoritativeJsonAdapter:
    def __init__(self, *, profile: RepresentationProfile) -> None:
        self.profile = profile

    def encode(self, bundle: MemoryRepresentationBundleV3) -> bytes:
        return canonical_json_bytes(bundle)

    def decode(self, payload: Any) -> MemoryRepresentationBundleV3:
        if isinstance(payload, dict):
            bundle = MemoryRepresentationBundleV3.model_validate(payload)
        elif isinstance(payload, str):
            bundle = MemoryRepresentationBundleV3.model_validate_json(payload)
        elif isinstance(payload, bytes):
            bundle = MemoryRepresentationBundleV3.model_validate_json(payload)
        else:
            raise TypeError(f"unsupported payload type: {type(payload).__name__}")
        report = assess_authoritative_bundle_integrity(bundle)
        if not report.valid:
            raise ValueError("authoritative bundle integrity invalid: " + "; ".join(report.errors))
        return bundle


def build_authoritative_conformance_bundle(
    root: Path,
    slice_id: str,
    results_path: Path,
) -> MemoryRepresentationBundleV3:
    bundle = build_real_slice_authoritative_bundle(
        root,
        slice_id,
        results_path,
        transaction_time="2026-07-27T12:00:00Z",
        producer=ProducerIdentity(
            workflow_run_id="run-authoritative-conformance-v5",
            producer_id="authoritative-memory-v3-migration",
            producer_version="1",
        ),
        query_answer_kinds={"LONGMEMEVAL-6d550036": "count"},
    )
    return bundle.model_copy(update={"profile": _reference_profile()})


def _find_spec(bundle: MemoryRepresentationBundleV3, closure_id: str, revision: int) -> ClosureSpec:
    spec = next(
        (
            item
            for item in bundle.closure_specs
            if item.closure_id == closure_id and item.revision == revision
        ),
        None,
    )
    if spec is None:
        raise ValueError(f"missing closure spec {closure_id}@{revision}")
    return spec


def _evaluation_fresh(bundle: MemoryRepresentationBundleV3, evaluation: ClosureEvaluation) -> tuple[bool, bool]:
    if isinstance(evaluation.context, QueryClosureContext):
        plan = next(
            plan for plan in bundle.query_plans if plan.query_id == evaluation.context.query_plan.query_id
        )
        spec = _find_spec(bundle, evaluation.closure_id, evaluation.spec_revision)
        inputs = ClosureEvaluationInputs.for_query(bundle, plan)
    else:
        l2 = next(unit for unit in bundle.l2_units if unit.unit_id == evaluation.context.l2_unit_id)
        claim = next(claim for claim in l2.structured_claims if claim.claim_id == evaluation.context.claim_id)
        spec = _find_spec(bundle, evaluation.closure_id, evaluation.spec_revision)
        inputs = ClosureEvaluationInputs.for_claim(bundle, l2, claim)
    recomputed = evaluate_closure_spec(spec, inputs)
    return is_closure_evaluation_fresh(evaluation, spec, inputs), evaluation.result_hash == recomputed.result_hash


def _expected_correctness(
    bundle: MemoryRepresentationBundleV3,
    root: Path,
    slice_id: str,
    results_path: Path,
) -> dict[str, dict[str, Any]]:
    cases = build_real_slice_diagnostic_suite(root, slice_id, results_path)
    frozen_ids = list(FROZEN_CORRECTNESS_EXPECTATIONS)
    case_ids = [case.plan.query_id for case in cases]
    plan_ids = [plan.query_id for plan in bundle.query_plans]
    if case_ids != frozen_ids:
        raise ValueError(f"diagnostic suite does not match frozen correctness IDs: {case_ids}")
    if plan_ids != frozen_ids:
        raise ValueError(f"authoritative query plans do not match frozen correctness IDs: {plan_ids}")
    return {
        query_id: {
            key: list(value) if isinstance(value, list) else value
            for key, value in expectation.items()
        }
        for query_id, expectation in FROZEN_CORRECTNESS_EXPECTATIONS.items()
    }


def _query_results(bundle: MemoryRepresentationBundleV3) -> dict[str, dict[str, Any]]:
    return {
        plan.query_id: execute_authoritative_query(plan, bundle).model_dump(mode="json")
        for plan in bundle.query_plans
    }


def _correctness_probes(
    bundle: MemoryRepresentationBundleV3,
    expected: dict[str, dict[str, Any]],
    results: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    query_results = results or _query_results(bundle)
    plans = {plan.query_id: plan for plan in bundle.query_plans}
    probes: list[dict[str, Any]] = []
    for query_id, expectation in expected.items():
        actual = query_results[query_id]
        comparable = {key: actual.get(key) for key in _PUBLIC_CORRECTNESS_KEYS}
        claim_ids = matched_claim_ids_for_query(plans[query_id], bundle)
        full_comparable = {**comparable, "matched_claim_ids": claim_ids}
        public_expected = {key: expectation[key] for key in _PUBLIC_CORRECTNESS_KEYS}
        probes.append(
            {
                "query_id": query_id,
                "passed": full_comparable == expectation,
                "expected": public_expected,
                "reference_result": comparable,
            }
        )
    return probes


def _active_l2_negative_gate_failures(bundle: MemoryRepresentationBundleV3) -> list[str]:
    active_l2 = next(
        (
            unit
            for unit in bundle.l2_units
            if unit.lifecycle == "active" and unit.closure_evaluation_id is not None
        ),
        None,
    )
    if active_l2 is None:
        return ["active_l2_closure_probe_missing"]
    evaluation = next(
        (
            item
            for item in bundle.closure_evaluations
            if item.evaluation_id == active_l2.closure_evaluation_id
        ),
        None,
    )
    if evaluation is None:
        return ["active_l2_closure_probe_missing"]

    def mutated_bundle(replacement: ClosureEvaluation) -> MemoryRepresentationBundleV3:
        return bundle.model_copy(
            update={
                "closure_evaluations": [
                    replacement if item.evaluation_id == replacement.evaluation_id else item
                    for item in bundle.closure_evaluations
                ]
            }
        )

    stale = evaluation.model_copy(
        update={"evaluator_version": f"{evaluation.evaluator_version}-stale-probe"}
    )
    stale_errors = assess_authoritative_bundle_integrity(mutated_bundle(stale)).errors
    incomplete = evaluation.model_copy(update={"complete": False})
    incomplete_errors = assess_authoritative_bundle_integrity(mutated_bundle(incomplete)).errors
    failures: list[str] = []
    if not any("stale closure evaluation" in error for error in stale_errors):
        failures.append("stale_active_l2_not_rejected")
    if not any("incomplete closure evaluation" in error for error in incomplete_errors):
        failures.append("incomplete_active_l2_not_rejected")
    return failures


def _closure_gate_results(bundle: MemoryRepresentationBundleV3) -> tuple[bool, bool]:
    checks: list[tuple[bool, bool]] = []
    try:
        checks = [_evaluation_fresh(bundle, evaluation) for evaluation in bundle.closure_evaluations]
    except (StopIteration, ValueError):
        return False, False
    return all(fresh for fresh, _ in checks), all(parity for _, parity in checks)


def _unsupported_capabilities(
    *,
    decoded_integrity_valid: bool,
    round_trip_exact: bool,
    source_valid: bool,
    query_probes: list[dict[str, Any]],
    correctness_probes: list[dict[str, Any]],
    closure_fresh: bool,
    closure_result_parity: bool,
    negative_gate_failures: list[str],
) -> list[str]:
    query_pass = bool(query_probes) and all(item["passed"] for item in query_probes)
    correctness_pass = bool(correctness_probes) and all(item["passed"] for item in correctness_probes)
    negative_pass = not negative_gate_failures
    fallback_pass = correctness_pass and all(
        not item["reference_result"].get("fallback_allowed", False)
        for item in correctness_probes
    )
    gates = {
        "stable_identity": decoded_integrity_valid and round_trip_exact,
        "raw_source_revision_binding": source_valid and decoded_integrity_valid and round_trip_exact,
        "event_role_semantics": query_pass and correctness_pass,
        "evidence_traceability": source_valid and decoded_integrity_valid,
        "source_epistemics": decoded_integrity_valid and round_trip_exact,
        "temporal_semantics": query_pass and correctness_pass,
        "lifecycle_and_revision": decoded_integrity_valid and round_trip_exact and negative_pass,
        "cross_layer_provenance": decoded_integrity_valid and round_trip_exact,
        "structured_l2_semantics": query_pass and correctness_pass and negative_pass,
        "evidence_closure": closure_fresh and closure_result_parity and negative_pass,
        "closure_evaluation_versioning": closure_fresh and closure_result_parity and negative_pass,
        "constraint_execution": query_pass and correctness_pass,
        "versioned_round_trip": round_trip_exact,
        "guarded_fallback": fallback_pass,
    }
    return [capability for capability in REQUIRED_MEMORY_CAPABILITIES if not gates[capability]]


def _carrier_report(
    adapter: Any,
    bundle: MemoryRepresentationBundleV3,
    expected: dict[str, dict[str, Any]],
    *,
    source_valid: bool,
) -> dict[str, Any]:
    failures: list[str] = []
    integrity = assess_authoritative_bundle_integrity(bundle)
    if not integrity.valid:
        failures.append("reference_bundle_integrity_invalid")
    if not source_valid:
        failures.append("raw_source_validation_invalid")
    try:
        encoded = adapter.encode(bundle)
        decoded = adapter.decode(encoded)
    except Exception as exc:
        return {
            "status": "fail",
            "integrity_valid": integrity.valid,
            "decoded_integrity_valid": False,
            "round_trip_exact": False,
            "query_probe_count": len(bundle.query_plans),
            "query_probe_pass_count": 0,
            "correctness_pass_count": 0,
            "correctness_probe_count": len(expected),
            "hard_gate_failures": [*failures, f"adapter_error:{type(exc).__name__}"],
            "unsupported_capabilities": list(REQUIRED_MEMORY_CAPABILITIES),
            "authoritative_ready": False,
            "error": str(exc),
        }
    decoded_integrity = assess_authoritative_bundle_integrity(decoded)
    if not decoded_integrity.valid:
        failures.append("decoded_bundle_integrity_invalid")
    round_trip_exact = canonical_json_bytes(bundle) == canonical_json_bytes(decoded)
    if not round_trip_exact:
        failures.append("round_trip_not_exact")
    reference_results = _query_results(bundle)
    decoded_results = _query_results(decoded)
    query_probes = [
        {
            "query_id": query_id,
            "passed": decoded_results.get(query_id) == result,
            "reference_result": result,
            "decoded_result": decoded_results.get(query_id, {}),
        }
        for query_id, result in reference_results.items()
    ]
    if any(not item["passed"] for item in query_probes):
        failures.append("query_semantics_changed")
    correctness_probes = _correctness_probes(decoded, expected, decoded_results)
    correctness_pass_count = sum(1 for item in correctness_probes if item["passed"])
    if correctness_pass_count != len(correctness_probes):
        failures.append("frozen_correctness_changed")
    negative_gate_failures = _active_l2_negative_gate_failures(decoded)
    failures.extend(negative_gate_failures)
    closure_fresh, closure_result_parity = _closure_gate_results(decoded)
    unsupported_capabilities = _unsupported_capabilities(
        decoded_integrity_valid=decoded_integrity.valid,
        round_trip_exact=round_trip_exact,
        source_valid=source_valid,
        query_probes=query_probes,
        correctness_probes=correctness_probes,
        closure_fresh=closure_fresh,
        closure_result_parity=closure_result_parity,
        negative_gate_failures=negative_gate_failures,
    )
    if unsupported_capabilities:
        failures.append("measured_capability_gate_failed")
    if any(
        item["query_id"] == "LONGMEMEVAL-6d550036"
        and item["reference_result"].get("reason") == "structured_l2_identity_unresolved"
        for item in correctness_probes
    ):
        failures.append("structured_l2_identity_unresolved")
    failures = list(dict.fromkeys(failures))
    return {
        "status": "pass" if not failures else "fail",
        "integrity_valid": integrity.valid,
        "decoded_integrity_valid": decoded_integrity.valid,
        "round_trip_exact": round_trip_exact,
        "query_probe_count": len(query_probes),
        "query_probe_pass_count": sum(1 for item in query_probes if item["passed"]),
        "query_probes": query_probes,
        "correctness_pass_count": correctness_pass_count,
        "correctness_probe_count": len(correctness_probes),
        "hard_gate_failures": failures,
        "unsupported_capabilities": unsupported_capabilities,
        "authoritative_ready": (
            not failures
            and not unsupported_capabilities
            and adapter.profile.role == "authoritative_candidate"
        ),
    }


def _workspace_root(root: Path, explicit_root: Path | None) -> Path:
    if explicit_root is not None:
        return explicit_root.resolve()
    resolved_root = root.resolve()
    if resolved_root.parent.name == "artifacts":
        return resolved_root.parent.parent
    return Path.cwd().resolve()


def run_authoritative_conformance(
    root: Path,
    slice_id: str,
    results_path: Path,
    *,
    run_id: str,
    workspace_root: Path | None = None,
) -> dict[str, Any]:
    bundle = build_authoritative_conformance_bundle(root, slice_id, results_path)
    source_report = validate_authoritative_sources(
        bundle,
        workspace_root=_workspace_root(root, workspace_root),
    )
    reference_results = _query_results(bundle)
    expected = _expected_correctness(bundle, root, slice_id, results_path)
    correctness_probes = _correctness_probes(bundle, expected, reference_results)
    reference_adapter = NativeAuthoritativeJsonAdapter(profile=bundle.profile)
    reference_carrier = _carrier_report(
        reference_adapter,
        bundle,
        expected,
        source_valid=source_report.valid,
    )
    amr_adapter = ExtendedAmrV2JsonAdapter(profile=_extended_profile())
    amr_carrier = _carrier_report(
        amr_adapter,
        bundle,
        expected,
        source_valid=source_report.valid,
    )
    fresh_count = 0
    stale_count = 0
    result_parity_count = 0
    for evaluation in bundle.closure_evaluations:
        fresh, result_parity = _evaluation_fresh(bundle, evaluation)
        fresh_count += int(fresh)
        stale_count += int(not fresh)
        result_parity_count += int(result_parity)
    return {
        "schema_version": "representation-conformance-run-v5",
        "run_id": run_id,
        "slice_id": slice_id,
        "scope": "authoritative v3 conformance; frozen hand-authored real slice; no model extraction or external memory rerun",
        "source_validation": source_report.model_dump(mode="json"),
        "closure_metrics": {
            "evaluation_count": len(bundle.closure_evaluations),
            "fresh_evaluation_count": fresh_count,
            "stale_evaluation_count": stale_count,
            "result_parity_pass_count": result_parity_count,
        },
        "correctness_probes": correctness_probes,
        "reference_carrier": reference_carrier,
        "extended_amr_v2": amr_carrier,
        "bundle": {
            "bundle_id": bundle.bundle_id,
            "profile": bundle.profile.model_dump(mode="json"),
            "integrity": assess_authoritative_bundle_integrity(bundle).model_dump(mode="json"),
        },
        "interpretation": {
            "selected_storage": None,
            "keol_role": "optional projection only",
            "extended_amr_role": "authoritative candidate under the same contract",
            "authority_blocker": "project identity/deduplication is unresolved for the count claim",
        },
    }


def render_authoritative_conformance_report(payload: dict[str, Any]) -> str:
    reference = payload["reference_carrier"]
    amr = payload["extended_amr_v2"]
    both_carriers_preserve_contract = all(
        carrier["round_trip_exact"]
        and carrier["query_probe_pass_count"] == carrier["query_probe_count"]
        and carrier["correctness_pass_count"] == carrier["correctness_probe_count"]
        for carrier in (reference, amr)
    )
    interpretation = (
        "Both carriers preserve the same typed v3 bundle and pass the five frozen correctness probes. The run is not a storage-selection or product-superiority result: authority remains blocked until project identity/deduplication is modeled well enough to support the requested count claim."
        if both_carriers_preserve_contract
        else "The carrier gates did not both pass. Inspect each carrier's round-trip, query, correctness, capability, and hard-gate results before drawing any representation conclusion."
    )
    lines = [
        "# Authoritative Memory Contract v5 Conformance Report",
        "",
        f"Run: `{payload['run_id']}`",
        "",
        "Scope: v3 authoritative contract over the frozen hand-authored real slice; no model extraction and no external memory rerun.",
        "",
        "## Source and closure gates",
        "",
        f"- Source validation: `{payload['source_validation']['valid']}`",
        f"- Source records replayed: `{payload['source_validation']['metrics']['source_record_replayed_count']}`",
        f"- Fresh closure evaluations: `{payload['closure_metrics']['fresh_evaluation_count']}/{payload['closure_metrics']['evaluation_count']}`",
        f"- Closure result parity: `{payload['closure_metrics']['result_parity_pass_count']}/{payload['closure_metrics']['evaluation_count']}`",
        "",
        "## Frozen correctness",
        "",
        f"- Probes passed: `{sum(1 for item in payload['correctness_probes'] if item['passed'])}/{len(payload['correctness_probes'])}`",
        "- The LongMemEval count probe deliberately abstains with `structured_l2_identity_unresolved`; its four evidence candidates are preserved, but the display count is not authoritative.",
        "",
        "## Carriers",
        "",
        f"- Native v3 round-trip: `{reference['round_trip_exact']}`; query parity `{reference['query_probe_pass_count']}/{reference['query_probe_count']}`; authoritative-ready `{reference['authoritative_ready']}`",
        f"- Extended-AMR v2 round-trip: `{amr['round_trip_exact']}`; query parity `{amr['query_probe_pass_count']}/{amr['query_probe_count']}`; authoritative-ready `{amr['authoritative_ready']}`",
        f"- Native hard-gate failures: `{reference['hard_gate_failures']}`",
        f"- Extended-AMR v2 hard-gate failures: `{amr['hard_gate_failures']}`",
        "",
        "## Interpretation",
        "",
        interpretation,
        "",
    ]
    return "\n".join(lines)


def run_authoritative_conformance_file(
    root: Path,
    slice_id: str,
    results_path: Path,
    output_path: Path,
    report_path: Path,
    *,
    run_id: str,
    workspace_root: Path | None = None,
) -> dict[str, Any]:
    payload = run_authoritative_conformance(
        root,
        slice_id,
        results_path,
        run_id=run_id,
        workspace_root=workspace_root,
    )
    write_json_immutable(output_path, payload)
    write_text_immutable(report_path, render_authoritative_conformance_report(payload))
    return payload
