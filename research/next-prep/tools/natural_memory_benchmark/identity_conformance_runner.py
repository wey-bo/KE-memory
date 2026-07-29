from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .extended_amr_v3_adapter import ExtendedAmrV3JsonAdapter
from .identity_resolution import (
    IdentityAwareMemoryBundleV4,
    assess_identity_bundle_integrity,
    build_identity_scenario_bundle,
    execute_identity_aware_query,
    identity_extended_amr_profile,
    identity_groups_for_scope,
    is_identity_closure_fresh,
    validate_identity_sources,
)
from .io import write_json_immutable, write_text_immutable


V5_RESULTS_SHA256 = "3ec6656c037200f8591fac44cd7e1e4bf2caa3aa9447f3fa5ba9854324d4cc33"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _false_merge_count(actual: list[list[str]], expected: list[list[str]]) -> int:
    expected_group = {
        entity_id: index
        for index, group in enumerate(expected)
        for entity_id in group
    }
    count = 0
    for group in actual:
        known = {expected_group[item] for item in group if item in expected_group}
        if len(known) > 1:
            count += 1
    return count


def _v5_regression(workspace_root: Path) -> dict[str, Any]:
    path = (
        workspace_root
        / "artifacts"
        / "natural-benchmark-slices"
        / "slice-v1"
        / "representation-conformance-results-v5.json"
    )
    if not path.exists():
        return {
            "v5_results_sha256": None,
            "v5_hash_preserved": False,
            "v5_longmemeval_abstention_preserved": False,
        }
    payload = _load(path)
    probe = next(
        (
            item
            for item in payload.get("correctness_probes", [])
            if item.get("query_id") == "LONGMEMEVAL-6d550036"
        ),
        None,
    )
    preserved = bool(
        probe
        and probe.get("expected", {}).get("abstained") is True
        and probe.get("expected", {}).get("reason") == "structured_l2_identity_unresolved"
        and probe.get("reference_result", {}).get("abstained") is True
        and probe.get("reference_result", {}).get("reason")
        == "structured_l2_identity_unresolved"
    )
    digest = _sha256(path)
    return {
        "v5_results_sha256": digest,
        "v5_hash_preserved": digest == V5_RESULTS_SHA256,
        "v5_longmemeval_abstention_preserved": preserved,
    }


def run_identity_conformance(
    experiment_root: Path,
    *,
    run_id: str,
    workspace_root: Path | None = None,
) -> dict[str, Any]:
    experiment_root = experiment_root.resolve()
    workspace_root = (workspace_root or Path.cwd()).resolve()
    manifest = _load(experiment_root / "gold-v1" / "manifest.json")
    source_path = experiment_root / "gold-v1" / "source-scenarios.json"
    gold_path = experiment_root / "gold-v1" / "gold.json"
    schemaorg_path = experiment_root / "schemaorg-selected-v30.json"
    source = _load(source_path)
    gold_payload = _load(gold_path)
    input_hashes = {
        "source": {
            "expected": manifest["source_sha256"],
            "actual": _sha256(source_path),
        },
        "gold": {
            "expected": manifest["gold_sha256"],
            "actual": _sha256(gold_path),
        },
        "schemaorg_reference": {
            "expected": manifest["schemaorg_reference_sha256"],
            "actual": _sha256(schemaorg_path),
        },
    }
    for item in input_hashes.values():
        item["matched"] = item["expected"] == item["actual"]
    gold = {item["scenario_id"]: item for item in gold_payload["items"]}
    adapter = ExtendedAmrV3JsonAdapter(profile=identity_extended_amr_profile())
    cases: list[dict[str, Any]] = []
    answerable_count = 0
    answerable_count_pass = 0
    evidence_pass = 0
    abstention_pass = 0
    false_merge_count = 0
    revision_total = 0
    revision_pass = 0
    closure_count = 0
    closure_fresh_count = 0
    fallback_count = 0
    native_round_trip_pass = 0
    amr_round_trip_pass = 0
    query_parity_pass = 0
    source_validation_pass = 0
    integrity_pass = 0

    for scenario in source["scenarios"]:
        scenario_id = scenario["scenario_id"]
        expected = gold[scenario_id]
        bundle = build_identity_scenario_bundle(experiment_root, scenario_id)
        integrity = assess_identity_bundle_integrity(bundle)
        source_validation = validate_identity_sources(bundle, workspace_root)
        native_decoded = IdentityAwareMemoryBundleV4.model_validate(bundle.model_dump(mode="json"))
        native_round_trip = native_decoded == bundle
        decoded = adapter.decode(adapter.encode(bundle))
        amr_round_trip = decoded == bundle
        native_result = execute_identity_aware_query(bundle.query_plans[0], bundle)
        decoded_result = execute_identity_aware_query(decoded.query_plans[0], decoded)
        query_parity = native_result == decoded_result
        actual_groups = identity_groups_for_scope(
            bundle.identity_snapshots[0], bundle.aggregate_claims[0].member_entity_ids
        )
        item_false_merges = _false_merge_count(
            actual_groups, expected["expected_canonical_groups"]
        )
        count_exact = native_result.aggregate_value == expected["expected_count"]
        evidence_exact = native_result.required_evidence_ids == expected["expected_evidence_ids"]
        abstention_correct = native_result.abstained is expected["expected_abstained"]
        closures_fresh = all(
            is_identity_closure_fresh(bundle, closure)
            for closure in bundle.identity_closures
        )
        revision_correct = True
        expected_superseded = expected.get("expected_superseded_decision")
        if expected_superseded:
            revision_total += 1
            revision_correct = expected_superseded in bundle.identity_snapshots[0].superseded_decision_ids
            revision_pass += int(revision_correct)
        if expected["expected_count"] is not None:
            answerable_count += 1
            answerable_count_pass += int(count_exact and not native_result.abstained)
        evidence_pass += int(evidence_exact)
        abstention_pass += int(abstention_correct)
        false_merge_count += item_false_merges
        closure_count += len(bundle.identity_closures)
        closure_fresh_count += sum(
            int(is_identity_closure_fresh(bundle, closure))
            for closure in bundle.identity_closures
        )
        fallback_count += int(native_result.fallback_allowed)
        native_round_trip_pass += int(native_round_trip)
        amr_round_trip_pass += int(amr_round_trip)
        query_parity_pass += int(query_parity)
        source_validation_pass += int(source_validation.valid)
        integrity_pass += int(integrity.valid)
        cases.append(
            {
                "scenario_id": scenario_id,
                "split": scenario["split"],
                "integrity_valid": integrity.valid,
                "source_validation_valid": source_validation.valid,
                "identity_closures_fresh": closures_fresh,
                "native_round_trip_exact": native_round_trip,
                "extended_amr_v3_round_trip_exact": amr_round_trip,
                "query_parity": query_parity,
                "count_exact": count_exact,
                "evidence_exact": evidence_exact,
                "abstention_correct": abstention_correct,
                "revision_correct": revision_correct,
                "critical_false_merge_count": item_false_merges,
                "expected": expected,
                "actual": {
                    "aggregate_value": native_result.aggregate_value,
                    "abstained": native_result.abstained,
                    "reason": native_result.reason,
                    "required_evidence_ids": native_result.required_evidence_ids,
                    "identity_groups": actual_groups,
                    "fallback_allowed": native_result.fallback_allowed,
                },
            }
        )
    scenario_count = len(cases)
    regressions = _v5_regression(workspace_root)
    metrics = {
        "critical_false_merge_count": false_merge_count,
        "answerable_count_exact_rate": answerable_count_pass / answerable_count,
        "evidence_set_exact_rate": evidence_pass / scenario_count,
        "abstention_correctness": abstention_pass / scenario_count,
        "revision_correctness": revision_pass / revision_total if revision_total else 1.0,
        "closure_freshness_rate": closure_fresh_count / closure_count,
        "structural_fallback_rate": fallback_count / scenario_count,
        "source_validation_rate": source_validation_pass / scenario_count,
        "integrity_rate": integrity_pass / scenario_count,
    }
    carriers = {
        "native_v4": {
            "round_trip_exact_rate": native_round_trip_pass / scenario_count,
        },
        "extended_amr_v3": {
            "round_trip_exact_rate": amr_round_trip_pass / scenario_count,
            "query_parity_rate": query_parity_pass / scenario_count,
        },
    }
    gates = manifest["pre_registered_gates"]
    gate_results = {
        "critical_false_merge": false_merge_count <= gates["critical_false_merge_max"],
        "answerable_count_exact": metrics["answerable_count_exact_rate"]
        == gates["answerable_count_exact"],
        "evidence_set_exact": metrics["evidence_set_exact_rate"] == gates["evidence_set_exact"],
        "abstention_correctness": metrics["abstention_correctness"]
        == gates["abstention_correctness"],
        "revision_correctness": metrics["revision_correctness"] == gates["revision_correctness"],
        "closure_freshness": metrics["closure_freshness_rate"] == gates["closure_freshness"],
        "native_round_trip": carriers["native_v4"]["round_trip_exact_rate"]
        == gates["native_round_trip"],
        "extended_amr_v3_round_trip": carriers["extended_amr_v3"]["round_trip_exact_rate"]
        == gates["extended_amr_v3_round_trip"],
        "query_parity": carriers["extended_amr_v3"]["query_parity_rate"]
        == gates["query_parity"],
        "structural_fallback_rate": metrics["structural_fallback_rate"]
        == gates["structural_fallback_rate"],
        "v5_longmemeval_abstention_regression": regressions[
            "v5_longmemeval_abstention_preserved"
        ]
        is gates["v5_longmemeval_abstention_regression"],
        "v5_artifact_hash_regression": regressions["v5_hash_preserved"],
        "source_validation": metrics["source_validation_rate"] == 1.0,
        "identity_integrity": metrics["integrity_rate"] == 1.0,
        "frozen_input_hashes": all(item["matched"] for item in input_hashes.values()),
    }
    status = "pass" if all(gate_results.values()) else "fail"
    return {
        "schema_version": "identity-conformance-run-v1",
        "run_id": run_id,
        "dataset_id": manifest["dataset_id"],
        "scope": "hand-authored identity contract and execution diagnostic; no model extraction or external memory rerun",
        "status": status,
        "identity_authoritative_ready": status == "pass",
        "scenario_count": scenario_count,
        "dev_count": sum(item["split"] == "dev" for item in cases),
        "hidden_count": sum(item["split"] == "hidden" for item in cases),
        "metrics": metrics,
        "carriers": carriers,
        "regressions": regressions,
        "gate_results": gate_results,
        "input_hashes": input_hashes,
        "cases": cases,
        "interpretation": {
            "extended_amr_role": "primary candidate carrier for the identity-aware contract",
            "selected_storage": None,
            "schemaorg_role": "advisory concept/property source only",
            "next_authorized_step": "larger natural identity slice or model-based identity proposal experiment",
            "claim_boundary": manifest["claim_boundary"],
        },
    }


def render_identity_conformance_report(payload: dict[str, Any]) -> str:
    metrics = payload["metrics"]
    carriers = payload["carriers"]
    lines = [
        "# Identity Resolution and Extended-AMR v3 Conformance Report",
        "",
        f"Run: `{payload['run_id']}`",
        "",
        f"Decision: `{payload['status']}`; identity-authoritative-ready: `{payload['identity_authoritative_ready']}`.",
        "",
        "## Frozen gates",
        "",
        f"- Scenarios: `{payload['scenario_count']}` (`{payload['dev_count']}` dev, `{payload['hidden_count']}` hidden)",
        f"- critical false merges: `{metrics['critical_false_merge_count']}`",
        f"- Answerable count exact: `{metrics['answerable_count_exact_rate']}`",
        f"- Evidence set exact: `{metrics['evidence_set_exact_rate']}`",
        f"- Abstention correctness: `{metrics['abstention_correctness']}`",
        f"- Revision correctness: `{metrics['revision_correctness']}`",
        f"- Identity closure freshness: `{metrics['closure_freshness_rate']}`",
        f"- Structural fallback rate: `{metrics['structural_fallback_rate']}`",
        "",
        "## Carriers",
        "",
        f"- Native v4 exact round-trip: `{carriers['native_v4']['round_trip_exact_rate']}`",
        f"- Extended-AMR v3 exact round-trip: `{carriers['extended_amr_v3']['round_trip_exact_rate']}`",
        f"- Extended-AMR v3 query parity: `{carriers['extended_amr_v3']['query_parity_rate']}`",
        "",
        "## Regression boundary",
        "",
        f"- Frozen v5 hash preserved: `{payload['regressions']['v5_hash_preserved']}`",
        f"- LongMemEval unresolved-identity abstention preserved: `{payload['regressions']['v5_longmemeval_abstention_preserved']}`",
        "",
        "## Interpretation",
        "",
        "This is a hand-authored identity contract diagnostic, not an automatic entity-linking benchmark. The pass shows that evidence-backed identity decisions, correction-safe snapshots, safe `count_distinct`, and Extended-AMR v3 parity are executable on the frozen cases. It does not select final storage or establish product or external-system superiority. The real LongMemEval count remains abstained in frozen v5 until independent membership and identity evidence is added.",
        "",
    ]
    return "\n".join(lines)


def run_identity_conformance_file(
    experiment_root: Path,
    output_path: Path,
    report_path: Path,
    *,
    run_id: str,
    workspace_root: Path | None = None,
) -> dict[str, Any]:
    payload = run_identity_conformance(
        experiment_root,
        run_id=run_id,
        workspace_root=workspace_root,
    )
    write_json_immutable(output_path, payload)
    write_text_immutable(report_path, render_identity_conformance_report(payload))
    return payload
