from __future__ import annotations

import importlib
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from .io import load_json, write_json_immutable
from .semantic_ir import execute_query
from .semantic_ir_slice_runner import build_real_slice_diagnostic_suite


def _load_keol_modules(keol_root: Path) -> tuple[Any, Any]:
    src = (keol_root / "src").resolve()
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    models = importlib.import_module("onto.models")
    validator = importlib.import_module("onto.validator")
    models_path = Path(models.__file__).resolve()
    if src not in models_path.parents:
        raise ImportError(f"loaded onto.models from unexpected path: {models_path}")
    return models, validator


def build_expected_closure_states(
    root: Path,
    slice_id: str,
    results_path: Path,
) -> dict[str, bool]:
    expected: dict[str, bool] = {}
    for case in build_real_slice_diagnostic_suite(root, slice_id, results_path):
        result = execute_query(case.plan, case.l1_units, case.l2_units, case.closures)
        for closure in case.closures:
            expected[closure.closure_id] = result.closure_complete
    return expected


def _closure_parity(
    projection: dict[str, Any],
    expected_closure_states: dict[str, bool] | None,
) -> dict[str, Any]:
    projected = {
        assertion.get("metadata", {}).get("semantic_ir_unit_id"): bool(
            assertion.get("metadata", {}).get("complete", False)
        )
        for assertion in projection.get("assertions", [])
        if assertion.get("metadata", {}).get("semantic_ir_level") == "closure"
    }
    expected = expected_closure_states or {}
    mismatches = [
        {
            "closure_id": closure_id,
            "expected_complete": complete,
            "projected_complete": projected.get(closure_id),
        }
        for closure_id, complete in expected.items()
        if projected.get(closure_id) != complete
    ]
    return {
        "expected_count": len(expected),
        "projected_count": len(projected),
        "expected_complete_count": sum(1 for value in expected.values() if value),
        "projected_complete_count": sum(1 for value in projected.values() if value),
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
    }


def validate_keol_projection(
    projection: dict[str, Any],
    keol_root: Path,
    *,
    expected_closure_states: dict[str, bool] | None = None,
) -> dict[str, Any]:
    models, validator = _load_keol_modules(keol_root)
    ontology_payload = {
        "concepts": projection.get("concepts", []),
        "individuals": projection.get("individuals", []),
        "operators": projection.get("operators", []),
        "assertions": projection.get("assertions", []),
        "evidence": projection.get("evidence", []),
        "workflow_runs": projection.get("workflow_runs", []),
    }
    ontology = models.OntologyResult.model_validate(ontology_payload)
    native_report = validator.validate_ontology(ontology)
    issue_payloads = [issue.model_dump(mode="json") for issue in native_report.issues]
    warning_counts = Counter(
        issue["code"] for issue in issue_payloads if issue["severity"] == "warning"
    )
    error_counts = Counter(
        issue["code"] for issue in issue_payloads if issue["severity"] == "error"
    )
    parity = _closure_parity(projection, expected_closure_states)
    blocking_warning_codes = {
        "agent_ontology.missing",
        "assertion.unknown_status",
        "individual.no_concepts",
        "operator.no_description",
    }
    present_blocking_warnings = sorted(blocking_warning_codes & set(warning_counts))
    gate_failures: list[str] = []
    if native_report.error_count:
        gate_failures.append("native_validation_errors")
    if parity["mismatch_count"]:
        gate_failures.append("closure_parity_mismatch")
    if present_blocking_warnings:
        gate_failures.append("blocking_native_warnings")
    gate_failures.extend(["reverse_round_trip_unimplemented", "runtime_constraint_execution_unproven"])

    return {
        "schema_version": "semantic-ir-keol-native-validation-v1",
        "projection_schema_version": projection.get("schema_version"),
        "keol_models_path": str(Path(models.__file__).resolve()),
        "classification": "projection_only",
        "record_shape_valid": native_report.error_count == 0,
        "native_model_error_count": native_report.error_count,
        "native_model_warning_count": native_report.warning_count,
        "error_code_counts": dict(sorted(error_counts.items())),
        "warning_code_counts": dict(sorted(warning_counts.items())),
        "native_issues": issue_payloads,
        "object_counts": {
            key: len(ontology_payload[key])
            for key in ("concepts", "individuals", "operators", "assertions", "evidence", "workflow_runs")
        },
        "closure_parity": parity,
        "reverse_round_trip_supported": False,
        "runtime_constraint_execution_proven": False,
        "authoritative_ready": False,
        "adapter_gate_failures": gate_failures,
        "scope": "optional KEOL adapter validation; no KEOL baseline mutation",
    }


def validate_keol_projection_file(
    projection_path: Path,
    keol_root: Path,
    output_path: Path,
    *,
    root: Path | None = None,
    slice_id: str | None = None,
    results_path: Path | None = None,
) -> dict[str, Any]:
    expected = None
    if root is not None and slice_id is not None and results_path is not None:
        expected = build_expected_closure_states(root, slice_id, results_path)
    payload = validate_keol_projection(
        load_json(projection_path),
        keol_root,
        expected_closure_states=expected,
    )
    write_json_immutable(output_path, payload)
    return payload

