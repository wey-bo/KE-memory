from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .io import write_json_immutable
from .semantic_ir import (
    ClosureRecord,
    EvidenceSpan,
    L1MemoryUnit,
    L2MemoryUnit,
    Predicate,
    QueryResult,
    QuerySlotPlan,
    RoleBinding,
    SourceBinding,
    execute_query,
)


@dataclass(frozen=True)
class SemanticIrDiagnosticCase:
    case_id: str
    category: str
    description: str
    plan: QuerySlotPlan
    l1_units: list[L1MemoryUnit]
    l2_units: list[L2MemoryUnit]
    closures: list[ClosureRecord]
    expected: dict[str, Any]


def _span(evidence_id: str, text: str, *, turn_id: str | None = None, session_id: str = "session-1") -> EvidenceSpan:
    return EvidenceSpan(
        evidence_id=evidence_id,
        turn_id=turn_id or f"turn-{evidence_id}",
        session_id=session_id,
        char_start=0,
        char_end=len(text),
        text=text,
    )


def _source(evidence_id: str, text: str, *, session_id: str = "session-1") -> SourceBinding:
    return SourceBinding(
        speaker="user",
        source_status="user_reported",
        evidence_spans=[_span(evidence_id, text, session_id=session_id)],
    )


def _unit(
    unit_id: str,
    *,
    surface: str,
    sense: str,
    operator: str,
    evidence_id: str,
    text: str,
    lifecycle: str = "active",
    session_id: str = "session-1",
    roles: list[RoleBinding] | None = None,
) -> L1MemoryUnit:
    return L1MemoryUnit(
        unit_id=unit_id,
        kind="event",
        predicate=Predicate(surface=surface, sense=sense, canonical_operator=operator),
        roles=roles
        or [
            RoleBinding(role="ARG0", entity_id="user", role_name="agent"),
            RoleBinding(role="ARG1", entity_id=unit_id.replace("l1-", ""), role_name="theme"),
        ],
        source=_source(evidence_id, text, session_id=session_id),
        lifecycle=lifecycle,  # type: ignore[arg-type]
    )


def _case_result(case: SemanticIrDiagnosticCase) -> dict[str, Any]:
    result = execute_query(case.plan, case.l1_units, case.l2_units, case.closures)
    result_payload = result.model_dump()
    passed = all(result_payload.get(key) == expected for key, expected in case.expected.items())
    return {
        "case_id": case.case_id,
        "category": case.category,
        "description": case.description,
        "passed": passed,
        "expected": case.expected,
        "query_result": result_payload,
    }


def build_diagnostic_suite() -> list[SemanticIrDiagnosticCase]:
    led_project = _unit(
        "l1-led-migration",
        surface="led",
        sense="lead/manage",
        operator="led_by",
        evidence_id="E-led-migration",
        text="I led the migration project.",
    )
    caused_change = _unit(
        "l1-feedback-led-to-change",
        surface="led to",
        sense="led-to/cause",
        operator="caused_by",
        evidence_id="E-led-to-change",
        text="User feedback led to a checkout label change.",
    )
    feedback = _unit(
        "l1-feedback-observation",
        surface="feedback",
        sense="feedback-observation",
        operator="observed_by",
        evidence_id="E-feedback",
        text="The user feedback mentioned UI/UX concerns.",
    )
    ui_change = _unit(
        "l1-ui-change",
        surface="improved",
        sense="change/improve",
        operator="changed_by",
        evidence_id="E-ui-change",
        text="The UI/UX was improved before launch.",
    )
    dashboard = _unit(
        "l1-leading-dashboard",
        surface="leading",
        sense="lead/manage",
        operator="led_by",
        evidence_id="E-leading-dashboard",
        text="I am currently leading the dashboard project.",
        session_id="session-2",
    )
    old_pref = _unit(
        "l1-pref-old",
        surface="prefer",
        sense="prefer",
        operator="prefers",
        evidence_id="E-pref-old",
        text="I used to prefer tea.",
        lifecycle="superseded",
        roles=[RoleBinding(role="ARG0", entity_id="user", role_name="holder"), RoleBinding(role="ARG1", entity_id="tea", role_name="object")],
    )
    new_pref = _unit(
        "l1-pref-new",
        surface="prefer",
        sense="prefer",
        operator="prefers",
        evidence_id="E-pref-new",
        text="I now prefer coffee.",
        lifecycle="active",
        roles=[RoleBinding(role="ARG0", entity_id="user", role_name="holder"), RoleBinding(role="ARG1", entity_id="coffee", role_name="object")],
    )
    project_closure = ClosureRecord(
        closure_id="closure-projects",
        claim_or_query_id="query-projects",
        pattern="multi_evidence_set",
        required_units=[
            {"unit_id": "l1-led-migration", "role": "evidence"},
            {"unit_id": "l1-leading-dashboard", "role": "evidence"},
        ],
    )
    l2_project = L2MemoryUnit(
        unit_id="l2-projects-led",
        kind="project",
        abstracts=["l1-led-migration", "l1-leading-dashboard"],
        summary="User led one project and is currently leading another.",
        assertions=["ke-projects-led"],
        closure_id="closure-projects",
        lifecycle="active",
        source_l1_units=["l1-led-migration", "l1-leading-dashboard"],
        source_turns=["turn-E-led-migration", "turn-E-leading-dashboard"],
        source_sessions=["session-1", "session-2"],
    )

    return [
        SemanticIrDiagnosticCase(
            case_id="led_manage_vs_led_to_cause",
            category="predicate_sense",
            description="A project-leadership query must match lead/manage and ignore causal led-to.",
            plan=QuerySlotPlan(
                query_id="query-led-projects",
                intent="fact_lookup",
                target_level="L1",
                predicate_sense="lead/manage",
                canonical_operator="led_by",
            ),
            l1_units=[led_project, caused_change],
            l2_units=[],
            closures=[],
            expected={"matched_unit_ids": ["l1-led-migration"], "required_evidence_ids": ["E-led-migration"], "abstained": False},
        ),
        SemanticIrDiagnosticCase(
            case_id="led_to_cause_match",
            category="predicate_sense",
            description="A causal query must match led-to/cause and ignore lead/manage.",
            plan=QuerySlotPlan(
                query_id="query-led-to-cause",
                intent="causal_how",
                target_level="L1",
                predicate_sense="led-to/cause",
                canonical_operator="caused_by",
            ),
            l1_units=[led_project, caused_change],
            l2_units=[],
            closures=[],
            expected={"matched_unit_ids": ["l1-feedback-led-to-change"], "required_evidence_ids": ["E-led-to-change"], "abstained": False},
        ),
        SemanticIrDiagnosticCase(
            case_id="feedback_causal_answerability_missing_link",
            category="causal_answerability",
            description="Feedback and UI/UX change mentions are insufficient without a causal link unit.",
            plan=QuerySlotPlan(
                query_id="query-feedback-cause",
                intent="causal_how",
                target_level="L1",
                required_closure_pattern="causal_answerability",
                closure_id="closure-feedback-cause",
            ),
            l1_units=[feedback, ui_change],
            l2_units=[],
            closures=[
                ClosureRecord(
                    closure_id="closure-feedback-cause",
                    claim_or_query_id="query-feedback-cause",
                    pattern="causal_answerability",
                    required_units=[
                        {"unit_id": "l1-feedback-observation", "role": "cause"},
                        {"unit_id": "l1-ui-change", "role": "effect"},
                    ],
                )
            ],
            expected={"abstained": True, "closure_complete": False, "fallback_allowed": False, "reason": "missing causal answerability roles"},
        ),
        SemanticIrDiagnosticCase(
            case_id="multi_session_evidence_closure",
            category="evidence_closure",
            description="A cross-session project query must return the complete evidence set.",
            plan=QuerySlotPlan(
                query_id="query-projects",
                intent="multi_evidence",
                target_level="both",
                predicate_sense="lead/manage",
                canonical_operator="led_by",
                required_closure_pattern="multi_evidence_set",
                closure_id="closure-projects",
            ),
            l1_units=[led_project, dashboard],
            l2_units=[l2_project],
            closures=[project_closure],
            expected={
                "matched_unit_ids": ["l1-led-migration", "l1-leading-dashboard", "l2-projects-led"],
                "required_evidence_ids": ["E-led-migration", "E-leading-dashboard"],
                "closure_complete": True,
                "abstained": False,
            },
        ),
        SemanticIrDiagnosticCase(
            case_id="current_preference_supersession",
            category="lifecycle",
            description="Current preference queries must ignore superseded preference records.",
            plan=QuerySlotPlan(
                query_id="query-current-preference",
                intent="preference_current",
                target_level="L1",
                predicate_sense="prefer",
                canonical_operator="prefers",
                lifecycle="active",
            ),
            l1_units=[old_pref, new_pref],
            l2_units=[],
            closures=[],
            expected={"matched_unit_ids": ["l1-pref-new"], "required_evidence_ids": ["E-pref-new"], "abstained": False},
        ),
    ]


def _metrics(cases: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "case_count": len(cases),
        "pass_count": sum(1 for case in cases if case["passed"]),
        "fail_count": sum(1 for case in cases if not case["passed"]),
        "abstention_count": sum(1 for case in cases if case["query_result"]["abstained"]),
        "fallback_allowed_count": sum(1 for case in cases if case["query_result"]["fallback_allowed"]),
        "closure_complete_count": sum(1 for case in cases if case["query_result"]["closure_complete"]),
    }


def run_semantic_ir_diagnostics(*, run_id: str) -> dict[str, Any]:
    case_results = [_case_result(case) for case in build_diagnostic_suite()]
    return {
        "schema_version": "semantic-ir-diagnostic-results-v1",
        "run_id": run_id,
        "scope": "hand-authored IR diagnostics; no model extraction; no benchmark expansion",
        "cases": case_results,
        "metrics": _metrics(case_results),
    }


def render_semantic_ir_report(payload: dict[str, Any]) -> str:
    metrics = payload["metrics"]
    lines = [
        "# Semantic IR Diagnostic Report",
        "",
        f"Run: `{payload['run_id']}`",
        "",
        "Scope: hand-authored IR only; no model extraction; no benchmark expansion.",
        "",
        "## Metrics",
        "",
        f"- Passed: {metrics['pass_count']}/{metrics['case_count']}",
        f"- Abstentions: {metrics['abstention_count']}",
        f"- Fallback allowed: {metrics['fallback_allowed_count']}",
        f"- Closure complete: {metrics['closure_complete_count']}",
        "",
        "## Cases",
        "",
    ]
    for case in payload["cases"]:
        status = "PASS" if case["passed"] else "FAIL"
        result = case["query_result"]
        lines.extend(
            [
                f"### {case['case_id']}: {status}",
                "",
                case["description"],
                "",
                f"- Category: `{case['category']}`",
                f"- Matched units: `{result['matched_unit_ids']}`",
                f"- Evidence IDs: `{result['required_evidence_ids']}`",
                f"- Abstained: `{result['abstained']}`",
                f"- Reason: `{result['reason']}`",
                "",
            ]
        )
    lines.extend(
        [
            "## Interpretation",
            "",
            "The diagnostic suite confirms that the AMR-style semantic IR can represent predicate sense, closure completeness, and lifecycle constraints without dense retrieval.",
            "It specifically separates `led/manage` from `led-to/cause`, blocks feedback causal answerability when the causal link is missing, requires complete multi-session evidence, and ignores superseded preferences.",
            "",
            "This does not prove model extraction quality. The next step is to map real slice items into this IR and compare runner behavior against `symbolic_fallback_answerability_v2` before adding model-based extraction.",
            "",
        ]
    )
    return "\n".join(lines)


def run_semantic_ir_diagnostics_file(output_path: Path, report_path: Path, *, run_id: str) -> dict[str, Any]:
    payload = run_semantic_ir_diagnostics(run_id=run_id)
    write_json_immutable(output_path, payload)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_semantic_ir_report(payload), encoding="utf-8")
    return payload
