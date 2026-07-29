from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from .io import write_json_immutable
from .semantic_ir import (
    ClosureRecord,
    L1MemoryUnit,
    L2MemoryUnit,
    RoleBinding,
    evaluate_closure,
    execute_query,
)
from .semantic_ir_slice_runner import build_real_slice_diagnostic_suite


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")
    return slug or "unnamed"


def _digest(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def _stable_id(prefix: str, *parts: str) -> str:
    return f"{prefix}_{_slug(parts[0])}_{_digest(*parts)[:12]}"


def _term(term_type: str, object_id: str) -> dict[str, Any]:
    return {"term_type": term_type, "id": object_id}


def _operator_application(operator_id: str, roles: list[RoleBinding], individual_ids: dict[str, str]) -> dict[str, Any]:
    source_roles = [role for role in roles if role.role == "ARG0"]
    if not source_roles and roles:
        source_roles = [roles[0]]
    return {
        "term_type": "operator_application",
        "operator_id": operator_id,
        "arguments": [
            {
                "role": role.role_name,
                "term": _term("individual", individual_ids[role.entity_id]),
            }
            for role in source_roles
        ],
    }


def _rhs_role(roles: list[RoleBinding]) -> RoleBinding:
    for role in roles:
        if role.role == "ARG1":
            return role
    return roles[-1]


def _status_from_lifecycle(lifecycle: str) -> str:
    return {
        "active": "active",
        "superseded": "deprecated",
        "conflicted": "rejected",
        "forgotten": "deprecated",
        "candidate": "rejected",
    }.get(lifecycle, "rejected")


def _role_payloads(roles: list[RoleBinding]) -> list[dict[str, str]]:
    return [
        {
            "entity_id": role.entity_id,
            "role": role.role,
            "role_name": role.role_name,
        }
        for role in roles
    ]


def project_semantic_ir_to_keol(
    l1_units: list[L1MemoryUnit],
    l2_units: list[L2MemoryUnit],
    closures: list[ClosureRecord],
    *,
    workflow_run_id: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    evidence_by_id: dict[str, dict[str, Any]] = {}
    operator_by_name: dict[str, dict[str, Any]] = {}
    individual_by_entity: dict[str, dict[str, Any]] = {}
    assertion_by_unit_id: dict[str, str] = {}
    assertions: list[dict[str, Any]] = []

    def ensure_evidence(unit: L1MemoryUnit) -> list[str]:
        evidence_ids: list[str] = []
        for span in unit.source.evidence_spans:
            evidence_id = _stable_id("evidence", span.evidence_id, span.text)
            if evidence_id not in evidence_by_id:
                evidence_by_id[evidence_id] = {
                    "id": evidence_id,
                    "slug": _slug(span.evidence_id),
                    "hash": _digest(span.evidence_id, span.text),
                    "evidence_type": "text_span",
                    "source_file": span.session_id,
                    "source_chunk_id": span.turn_id,
                    "quote": span.text,
                    "content_hash": _digest(span.text),
                    "metadata": {
                        "semantic_ir_evidence_id": span.evidence_id,
                        "semantic_ir_unit_id": unit.unit_id,
                        "turn_id": span.turn_id,
                        "session_id": span.session_id,
                        "char_start": span.char_start,
                        "char_end": span.char_end,
                    },
                }
            evidence_ids.append(evidence_id)
        return evidence_ids

    def ensure_operator(name: str, evidence_ids: list[str], *, source_kind: str = "extracted") -> str:
        operator_id = _stable_id("operator", name)
        if name not in operator_by_name:
            operator_by_name[name] = {
                "id": operator_id,
                "slug": _slug(name),
                "hash": _digest(name),
                "name": name,
                "operator_type": "relation",
                "created_from_evidence_ids": [],
                "workflow_run_id": workflow_run_id,
                "source_kind": source_kind,
                "metadata": {},
            }
        existing = operator_by_name[name]["created_from_evidence_ids"]
        for evidence_id in evidence_ids:
            if evidence_id not in existing:
                existing.append(evidence_id)
        return operator_id

    def ensure_individual(entity_id: str, evidence_ids: list[str]) -> str:
        individual_id = _stable_id("individual", entity_id)
        if entity_id not in individual_by_entity:
            individual_by_entity[entity_id] = {
                "id": individual_id,
                "slug": _slug(entity_id),
                "hash": _digest(entity_id),
                "name": entity_id,
                "individual_type": "semantic_ir_entity",
                "concept_ids": [],
                "evidence_ids": [],
                "metadata": {"semantic_ir_entity_id": entity_id},
            }
        existing = individual_by_entity[entity_id]["evidence_ids"]
        for evidence_id in evidence_ids:
            if evidence_id not in existing:
                existing.append(evidence_id)
        return individual_id

    for unit in l1_units:
        evidence_ids = ensure_evidence(unit)
        operator_id = ensure_operator(unit.predicate.canonical_operator, evidence_ids)
        role_individual_ids = {
            role.entity_id: ensure_individual(role.entity_id, evidence_ids)
            for role in unit.roles
        }
        rhs = _rhs_role(unit.roles)
        assertion_id = _stable_id("assertion", unit.unit_id)
        assertion_by_unit_id[unit.unit_id] = assertion_id
        assertions.append(
            {
                "id": assertion_id,
                "slug": _slug(unit.unit_id),
                "hash": _digest(unit.unit_id, unit.predicate.canonical_operator),
                "lhs": _operator_application(operator_id, unit.roles, role_individual_ids),
                "rhs": _term("individual", role_individual_ids[rhs.entity_id]),
                "confidence": unit.epistemic.extraction_confidence,
                "status": _status_from_lifecycle(unit.lifecycle),
                "evidence_ids": evidence_ids,
                "derived_from_assertion_ids": [],
                "workflow_run_id": workflow_run_id,
                "temporal_scope": unit.time.model_dump(),
                "metadata": {
                    "semantic_ir_unit_id": unit.unit_id,
                    "semantic_ir_level": "L1",
                    "semantic_ir_kind": unit.kind,
                    "predicate_surface": unit.predicate.surface,
                    "predicate_sense": unit.predicate.sense,
                    "canonical_operator": unit.predicate.canonical_operator,
                    "source_status": unit.source.source_status,
                    "speaker": unit.source.speaker,
                    "lifecycle": unit.lifecycle,
                    "modality": unit.modality,
                    "polarity": unit.polarity,
                    "role_bindings": _role_payloads(unit.roles),
                    "links": unit.links.model_dump(),
                },
            }
        )

    for unit in l2_units:
        derived_ids = [assertion_by_unit_id[source_id] for source_id in unit.source_l1_units if source_id in assertion_by_unit_id]
        evidence_ids = [
            evidence_id
            for l1 in l1_units
            if l1.unit_id in unit.source_l1_units
            for evidence_id in ensure_evidence(l1)
        ]
        operator_id = ensure_operator("semantic_ir_abstraction", evidence_ids, source_kind="inferred")
        source_entity_id = f"{unit.unit_id}_source"
        target_entity_id = unit.unit_id
        source_individual_id = ensure_individual(source_entity_id, evidence_ids)
        target_individual_id = ensure_individual(target_entity_id, evidence_ids)
        assertion_id = _stable_id("assertion", unit.unit_id)
        assertion_by_unit_id[unit.unit_id] = assertion_id
        assertions.append(
            {
                "id": assertion_id,
                "slug": _slug(unit.unit_id),
                "hash": _digest(unit.unit_id, unit.summary),
                "lhs": {
                    "term_type": "operator_application",
                    "operator_id": operator_id,
                    "arguments": [{"role": "source", "term": _term("individual", source_individual_id)}],
                },
                "rhs": _term("individual", target_individual_id),
                "confidence": 1.0,
                "status": _status_from_lifecycle(unit.lifecycle),
                "evidence_ids": list(dict.fromkeys(evidence_ids)),
                "derived_from_assertion_ids": derived_ids,
                "workflow_run_id": workflow_run_id,
                "temporal_scope": {"valid_time": unit.valid_time},
                "metadata": {
                    "semantic_ir_unit_id": unit.unit_id,
                    "semantic_ir_level": "L2",
                    "semantic_ir_kind": unit.kind,
                    "abstracts": list(unit.abstracts),
                    "assertions": list(unit.assertions),
                    "closure_id": unit.closure_id,
                    "summary": unit.summary,
                    "source_l1_units": list(unit.source_l1_units),
                    "source_turns": list(unit.source_turns),
                    "source_sessions": list(unit.source_sessions),
                    "abstraction_method": dict(unit.abstraction_method),
                },
            }
        )

    for closure in closures:
        derived_ids = [
            assertion_by_unit_id[requirement.unit_id]
            for requirement in closure.required_units
            if requirement.unit_id in assertion_by_unit_id
        ]
        evidence_ids = [
            evidence_id
            for l1 in l1_units
            if l1.unit_id in {requirement.unit_id for requirement in closure.required_units}
            for evidence_id in ensure_evidence(l1)
        ]
        operator_id = ensure_operator("semantic_ir_closure", evidence_ids, source_kind="inferred")
        closure_individual_id = ensure_individual(closure.closure_id, evidence_ids)
        complete_value = "closure_complete" if closure.complete else "closure_incomplete"
        complete_individual_id = ensure_individual(complete_value, evidence_ids)
        assertions.append(
            {
                "id": _stable_id("assertion", closure.closure_id),
                "slug": _slug(closure.closure_id),
                "hash": _digest(closure.closure_id, closure.pattern),
                "lhs": {
                    "term_type": "operator_application",
                    "operator_id": operator_id,
                    "arguments": [{"role": "closure", "term": _term("individual", closure_individual_id)}],
                },
                "rhs": _term("individual", complete_individual_id),
                "confidence": 1.0,
                "status": "active" if closure.complete else "rejected",
                "evidence_ids": list(dict.fromkeys(evidence_ids)),
                "derived_from_assertion_ids": derived_ids,
                "workflow_run_id": workflow_run_id,
                "temporal_scope": {},
                "metadata": {
                    "semantic_ir_unit_id": closure.closure_id,
                    "semantic_ir_level": "closure",
                    "claim_or_query_id": closure.claim_or_query_id,
                    "pattern": closure.pattern,
                    "required_units": [
                        {"role": requirement.role, "unit_id": requirement.unit_id}
                        for requirement in closure.required_units
                    ],
                    "optional_units": [
                        {"role": requirement.role, "unit_id": requirement.unit_id}
                        for requirement in closure.optional_units
                    ],
                    "missing_slots": [
                        {"role": requirement.role, "unit_id": requirement.unit_id}
                        for requirement in closure.missing_slots
                    ],
                    "complete": closure.complete,
                    "reason": closure.reason,
                },
            }
        )

    return {
        "schema_version": "semantic-ir-keol-projection-v2",
        "concepts": [],
        "individuals": list(individual_by_entity.values()),
        "operators": list(operator_by_name.values()),
        "assertions": assertions,
        "evidence": list(evidence_by_id.values()),
        "workflow_runs": [
            {
                "id": workflow_run_id,
                "slug": _slug(workflow_run_id),
                "hash": _digest(workflow_run_id),
                "workflow_name": "project_semantic_ir_to_keol",
                "status": "succeeded",
                "created_by": "natural_memory_benchmark",
                "model": "",
                "prompt_version": "",
                "pipeline_version": "semantic-ir-keol-projection-v2",
                "parameters": {},
                "metadata": {
                    "l1_unit_count": len(l1_units),
                    "l2_unit_count": len(l2_units),
                    "closure_count": len(closures),
                },
            }
        ],
        "metadata": metadata or {},
    }


def project_semantic_ir_slice_suite_to_keol(
    root: Path,
    slice_id: str,
    results_path: Path,
    *,
    workflow_run_id: str,
) -> dict[str, Any]:
    cases = build_real_slice_diagnostic_suite(root, slice_id, results_path)
    l1_units = [unit for case in cases for unit in case.l1_units]
    l2_units = [unit for case in cases for unit in case.l2_units]
    closures = []
    for case in cases:
        query_result = execute_query(case.plan, case.l1_units, case.l2_units, case.closures)
        available_ids = set(query_result.matched_unit_ids)
        closures.extend(evaluate_closure(closure, available_ids) for closure in case.closures)
    return project_semantic_ir_to_keol(
        l1_units,
        l2_units,
        closures,
        workflow_run_id=workflow_run_id,
        metadata={
            "scope": "optional adapter contract only; no KEOL baseline mutation; no model extraction",
            "slice_id": slice_id,
            "source_results": str(results_path),
            "case_count": len(cases),
            "item_ids": [case.item_id for case in cases],
        },
    )


def project_semantic_ir_slice_suite_to_keol_file(
    root: Path,
    slice_id: str,
    results_path: Path,
    output_path: Path,
    *,
    workflow_run_id: str,
) -> dict[str, Any]:
    payload = project_semantic_ir_slice_suite_to_keol(
        root,
        slice_id,
        results_path,
        workflow_run_id=workflow_run_id,
    )
    write_json_immutable(output_path, payload)
    return payload
