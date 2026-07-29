from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .io import load_json, write_json_immutable
from .semantic_ir import (
    ClosureRecord,
    EvidenceSpan,
    L1MemoryUnit,
    L2MemoryUnit,
    LinkBinding,
    Predicate,
    QuerySlotPlan,
    RoleBinding,
    SourceBinding,
    execute_query,
)


@dataclass(frozen=True)
class RealSliceSemanticIrCase:
    item_id: str
    category: str
    description: str
    plan: QuerySlotPlan
    l1_units: list[L1MemoryUnit]
    l2_units: list[L2MemoryUnit]
    closures: list[ClosureRecord]
    expected: dict[str, Any]
    public_item: dict[str, Any]
    gold_item: dict[str, Any]
    existing_result: dict[str, Any]


def _by_item_id(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {item["item_id"]: item for item in items}


def _load_bundle(root: Path, slice_id: str, results_path: Path) -> dict[str, Any]:
    slice_payload = load_json(root / slice_id / "slice.json")
    gold_payload = load_json(root / slice_id / "gold.json")
    corpus_payload = load_json(root / slice_id / "evidence-corpus.json")
    results_payload = load_json(results_path)
    return {
        "public": _by_item_id(slice_payload["public_items"]),
        "gold": _by_item_id(gold_payload["items"]),
        "corpus": corpus_payload["items"],
        "results": _by_item_id(results_payload["items"]),
    }


def _unit(corpus: dict[str, list[dict[str, Any]]], item_id: str, unit_id: str) -> dict[str, Any]:
    for unit in corpus[item_id]:
        if str(unit["unit_id"]) == unit_id:
            return unit
    raise KeyError(f"missing corpus unit for {item_id}: {unit_id}")


def _session_id(unit: dict[str, Any], item_id: str) -> str:
    source_ref = str(unit.get("source_ref", ""))
    for part in source_ref.split(";"):
        if part.startswith("session_id="):
            return part.split("=", 1)[1]
        if part.startswith("session_index="):
            return f"session-{part.split('=', 1)[1]}"
    return item_id


def _source_binding(unit: dict[str, Any], item_id: str) -> SourceBinding:
    text = unit["text"]
    metadata = unit.get("metadata", {})
    role = metadata.get("role")
    speaker = "assistant" if role == "assistant" else "user"
    source_status = "agent_generated" if speaker == "assistant" else "user_reported"
    return SourceBinding(
        speaker=speaker,
        source_status=source_status,
        evidence_spans=[
            EvidenceSpan(
                evidence_id=str(unit["unit_id"]),
                turn_id=str(unit.get("source_ref") or unit["unit_id"]),
                session_id=_session_id(unit, item_id),
                char_start=0,
                char_end=len(text),
                text=text,
            )
        ],
    )


def _l1(
    corpus: dict[str, list[dict[str, Any]]],
    item_id: str,
    unit_id: str,
    *,
    l1_id: str,
    kind: str,
    surface: str,
    sense: str,
    operator: str,
    roles: list[RoleBinding],
    lifecycle: str = "active",
    links: LinkBinding | None = None,
) -> L1MemoryUnit:
    unit = _unit(corpus, item_id, unit_id)
    return L1MemoryUnit(
        unit_id=l1_id,
        kind=kind,  # type: ignore[arg-type]
        predicate=Predicate(surface=surface, sense=sense, canonical_operator=operator),
        roles=roles,
        source=_source_binding(unit, item_id),
        lifecycle=lifecycle,  # type: ignore[arg-type]
        links=links or LinkBinding(),
    )


def _case_abstention(bundle: dict[str, Any]) -> RealSliceSemanticIrCase:
    item_id = "BEAM-100K-C001-abstention-001"
    corpus = bundle["corpus"]
    feedback = _l1(
        corpus,
        item_id,
        "116",
        l1_id="l1-beam-feedback-mentioned",
        kind="event",
        surface="feedback",
        sense="feedback-observation",
        operator="mentions_feedback",
        roles=[
            RoleBinding(role="ARG0", entity_id="user", role_name="source"),
            RoleBinding(role="ARG1", entity_id="feedback", role_name="topic"),
        ],
    )
    improvement = _l1(
        corpus,
        item_id,
        "117",
        l1_id="l1-beam-ui-ux-improvement-mentioned",
        kind="event",
        surface="UI/UX improvements",
        sense="improvement/ui-ux",
        operator="mentions_improvement",
        roles=[
            RoleBinding(role="ARG0", entity_id="user", role_name="agent"),
            RoleBinding(role="ARG1", entity_id="ui_ux", role_name="theme"),
        ],
    )
    closure = ClosureRecord(
        closure_id="closure-beam-feedback-ui-ux-causal-answerability",
        claim_or_query_id=item_id,
        pattern="causal_answerability",
        required_units=[
            {"unit_id": feedback.unit_id, "role": "cause"},
            {"unit_id": improvement.unit_id, "role": "effect"},
        ],
    )
    return RealSliceSemanticIrCase(
        item_id=item_id,
        category="causal_answerability",
        description="Mentions of feedback and UI/UX improvement are not enough without a causal link.",
        plan=QuerySlotPlan(
            query_id=item_id,
            intent="causal_how",
            target_level="L1",
            required_closure_pattern="causal_answerability",
            closure_id=closure.closure_id,
        ),
        l1_units=[feedback, improvement],
        l2_units=[],
        closures=[closure],
        expected={
            "required_evidence_ids": [],
            "abstained": True,
            "closure_complete": False,
            "fallback_allowed": False,
        },
        public_item=bundle["public"][item_id],
        gold_item=bundle["gold"][item_id],
        existing_result=bundle["results"][item_id],
    )


def _case_led_projects(bundle: dict[str, Any]) -> RealSliceSemanticIrCase:
    item_id = "LONGMEMEVAL-6d550036"
    corpus = bundle["corpus"]
    evidence_ids = ["answer_ec904b3c_4", "answer_ec904b3c_2", "answer_ec904b3c_1", "answer_ec904b3c_3"]
    units = [
        _l1(
            corpus,
            item_id,
            evidence_id,
            l1_id=f"l1-led-project-{idx}",
            kind="event",
            surface="led",
            sense="lead/manage",
            operator="led_by",
            roles=[
                RoleBinding(role="ARG0", entity_id="user", role_name="leader"),
                RoleBinding(role="ARG1", entity_id=f"project_{idx}", role_name="project"),
            ],
        )
        for idx, evidence_id in enumerate(evidence_ids, start=1)
    ]
    closure = ClosureRecord(
        closure_id="closure-longmemeval-led-projects",
        claim_or_query_id=item_id,
        pattern="multi_evidence_set",
        required_units=[{"unit_id": unit.unit_id, "role": "evidence"} for unit in units],
    )
    l2 = L2MemoryUnit(
        unit_id="l2-longmemeval-led-project-count",
        kind="project",
        abstracts=[unit.unit_id for unit in units],
        summary="The user has led or is leading two projects, supported by four sessions.",
        assertions=["count(led_projects_by_user)=2"],
        closure_id=closure.closure_id,
        lifecycle="active",
        source_l1_units=[unit.unit_id for unit in units],
        source_turns=[unit.source.evidence_spans[0].turn_id for unit in units],
        source_sessions=[unit.source.evidence_spans[0].session_id for unit in units],
    )
    return RealSliceSemanticIrCase(
        item_id=item_id,
        category="lexical_fallback_elimination",
        description="The current shallow symbolic arm needs embedding fallback for led/lead, while typed IR maps lead/manage directly.",
        plan=QuerySlotPlan(
            query_id=item_id,
            intent="multi_evidence",
            target_level="both",
            predicate_sense="lead/manage",
            canonical_operator="led_by",
            required_closure_pattern="multi_evidence_set",
            closure_id=closure.closure_id,
        ),
        l1_units=units,
        l2_units=[l2],
        closures=[closure],
        expected={
            "required_evidence_ids": evidence_ids,
            "abstained": False,
            "closure_complete": True,
            "fallback_allowed": False,
        },
        public_item=bundle["public"][item_id],
        gold_item=bundle["gold"][item_id],
        existing_result=bundle["results"][item_id],
    )


def _case_contradiction(bundle: dict[str, Any]) -> RealSliceSemanticIrCase:
    item_id = "BEAM-100K-C001-contradiction_resolution-001"
    corpus = bundle["corpus"]
    denial_id = "l1-flask-route-denial"
    implementation_id = "l1-flask-homepage-route-implementation"
    denial = _l1(
        corpus,
        item_id,
        "58",
        l1_id=denial_id,
        kind="state",
        surface="never written Flask routes or handled HTTP requests",
        sense="denial/prior-experience",
        operator="flask_route_experience_status",
        roles=[RoleBinding(role="ARG0", entity_id="user", role_name="experiencer")],
        lifecycle="conflicted",
        links=LinkBinding(conflicts_with=[implementation_id]),
    )
    implementation = _l1(
        corpus,
        item_id,
        "24",
        l1_id=implementation_id,
        kind="event",
        surface="implemented basic homepage route with Flask",
        sense="implementation/flask-route",
        operator="flask_route_experience_status",
        roles=[RoleBinding(role="ARG0", entity_id="user", role_name="developer")],
        lifecycle="conflicted",
        links=LinkBinding(conflicts_with=[denial_id]),
    )
    closure = ClosureRecord(
        closure_id="closure-beam-flask-route-contradiction",
        claim_or_query_id=item_id,
        pattern="multi_evidence_set",
        required_units=[
            {"unit_id": denial.unit_id, "role": "conflicting_denial"},
            {"unit_id": implementation.unit_id, "role": "conflicting_positive"},
        ],
    )
    return RealSliceSemanticIrCase(
        item_id=item_id,
        category="conflict_evidence_closure",
        description="Conflict-sensitive evidence closure requires both the denial and the positive Flask route implementation evidence.",
        plan=QuerySlotPlan(
            query_id=item_id,
            intent="fact_lookup",
            target_level="L1",
            canonical_operator="flask_route_experience_status",
            required_closure_pattern="multi_evidence_set",
            closure_id=closure.closure_id,
        ),
        l1_units=[denial, implementation],
        l2_units=[],
        closures=[closure],
        expected={
            "required_evidence_ids": ["58", "24"],
            "abstained": False,
            "closure_complete": True,
            "fallback_allowed": False,
        },
        public_item=bundle["public"][item_id],
        gold_item=bundle["gold"][item_id],
        existing_result=bundle["results"][item_id],
    )


def _case_commit_update(bundle: dict[str, Any]) -> RealSliceSemanticIrCase:
    item_id = "BEAM-100K-C001-knowledge_update-002"
    corpus = bundle["corpus"]
    old_id = "l1-main-branch-commit-count-150"
    new_id = "l1-main-branch-commit-count-165"
    old_count = _l1(
        corpus,
        item_id,
        "148",
        l1_id=old_id,
        kind="attribute",
        surface="150 commits",
        sense="quantity/merged-commit-count",
        operator="main_branch_merged_commit_count",
        roles=[
            RoleBinding(role="ARG0", entity_id="main_branch", role_name="subject"),
            RoleBinding(role="ARG1", entity_id="150_commits", role_name="value"),
        ],
        lifecycle="superseded",
    )
    new_count = _l1(
        corpus,
        item_id,
        "182",
        l1_id=new_id,
        kind="attribute",
        surface="165 commits",
        sense="quantity/merged-commit-count",
        operator="main_branch_merged_commit_count",
        roles=[
            RoleBinding(role="ARG0", entity_id="main_branch", role_name="subject"),
            RoleBinding(role="ARG1", entity_id="165_commits", role_name="value"),
        ],
        lifecycle="active",
        links=LinkBinding(supersedes=[old_id]),
    )
    closure = ClosureRecord(
        closure_id="closure-beam-main-branch-commit-count-update",
        claim_or_query_id=item_id,
        pattern="update_supersession",
        required_units=[
            {"unit_id": old_count.unit_id, "role": "previous_value"},
            {"unit_id": new_count.unit_id, "role": "current_value"},
        ],
    )
    return RealSliceSemanticIrCase(
        item_id=item_id,
        category="update_supersession_closure",
        description="Update closure returns the previous count plus the current superseding count and excludes adjacent Git workflow distractors.",
        plan=QuerySlotPlan(
            query_id=item_id,
            intent="temporal_latest",
            target_level="L1",
            canonical_operator="main_branch_merged_commit_count",
            required_closure_pattern="update_supersession",
            closure_id=closure.closure_id,
        ),
        l1_units=[old_count, new_count],
        l2_units=[],
        closures=[closure],
        expected={
            "required_evidence_ids": ["148", "182"],
            "abstained": False,
            "closure_complete": True,
            "fallback_allowed": False,
        },
        public_item=bundle["public"][item_id],
        gold_item=bundle["gold"][item_id],
        existing_result=bundle["results"][item_id],
    )


def _case_car_temporal(bundle: dict[str, Any]) -> RealSliceSemanticIrCase:
    item_id = "LONGMEMEVAL-gpt4_2655b836"
    corpus = bundle["corpus"]
    service = _l1(
        corpus,
        item_id,
        "answer_4be1b6b4_2",
        l1_id="l1-car-first-service",
        kind="event",
        surface="first service",
        sense="maintenance/first-service",
        operator="car_service_issue_context",
        roles=[RoleBinding(role="ARG1", entity_id="honda_civic", role_name="vehicle")],
    )
    issue = _l1(
        corpus,
        item_id,
        "answer_4be1b6b4_3",
        l1_id="l1-car-first-post-service-issue",
        kind="event",
        surface="GPS system not functioning correctly",
        sense="issue/gps-not-functioning",
        operator="car_service_issue_context",
        roles=[RoleBinding(role="ARG1", entity_id="gps_system", role_name="issue")],
    )
    car_context = _l1(
        corpus,
        item_id,
        "answer_4be1b6b4_1",
        l1_id="l1-car-new-honda-civic-context",
        kind="attribute",
        surface="new silver Honda Civic",
        sense="vehicle/context",
        operator="car_service_issue_context",
        roles=[RoleBinding(role="ARG1", entity_id="honda_civic", role_name="vehicle")],
    )
    closure = ClosureRecord(
        closure_id="closure-longmemeval-car-first-issue-after-service",
        claim_or_query_id=item_id,
        pattern="temporal_chain",
        required_units=[
            {"unit_id": service.unit_id, "role": "service_anchor"},
            {"unit_id": issue.unit_id, "role": "first_issue_after_anchor"},
            {"unit_id": car_context.unit_id, "role": "vehicle_context"},
        ],
    )
    return RealSliceSemanticIrCase(
        item_id=item_id,
        category="temporal_chain_closure",
        description="Temporal closure requires service anchor, first post-service issue, and vehicle context evidence.",
        plan=QuerySlotPlan(
            query_id=item_id,
            intent="temporal_latest",
            target_level="L1",
            canonical_operator="car_service_issue_context",
            required_closure_pattern="temporal_chain",
            closure_id=closure.closure_id,
        ),
        l1_units=[service, issue, car_context],
        l2_units=[],
        closures=[closure],
        expected={
            "required_evidence_ids": ["answer_4be1b6b4_2", "answer_4be1b6b4_3", "answer_4be1b6b4_1"],
            "abstained": False,
            "closure_complete": True,
            "fallback_allowed": False,
        },
        public_item=bundle["public"][item_id],
        gold_item=bundle["gold"][item_id],
        existing_result=bundle["results"][item_id],
    )


def build_real_slice_diagnostic_suite(root: Path, slice_id: str, results_path: Path) -> list[RealSliceSemanticIrCase]:
    bundle = _load_bundle(root, slice_id, results_path)
    return [
        _case_abstention(bundle),
        _case_led_projects(bundle),
        _case_contradiction(bundle),
        _case_commit_update(bundle),
        _case_car_temporal(bundle),
    ]


def _evidence_exact(expected: list[str], actual: list[str]) -> bool:
    return set(expected) == set(actual)


def _case_result(case: RealSliceSemanticIrCase) -> dict[str, Any]:
    query_result = execute_query(case.plan, case.l1_units, case.l2_units, case.closures)
    ir_payload = query_result.model_dump()
    gold_refs = list(case.gold_item.get("evidence_refs", []))
    existing_refs = list(case.existing_result.get("retrieved_evidence_refs", []))
    ir_refs = list(ir_payload["required_evidence_ids"])
    expected = case.expected
    passed = (
        ir_payload["abstained"] == expected["abstained"]
        and ir_payload["closure_complete"] == expected["closure_complete"]
        and ir_payload["fallback_allowed"] == expected["fallback_allowed"]
        and ir_refs == expected["required_evidence_ids"]
        and _evidence_exact(gold_refs, ir_refs)
    )
    return {
        "item_id": case.item_id,
        "category": case.category,
        "description": case.description,
        "question": case.public_item["question"],
        "passed": passed,
        "gold": {
            "answer_policy": case.gold_item.get("answer_policy"),
            "evidence_refs": gold_refs,
        },
        "existing": {
            "retrieved_evidence_refs": existing_refs,
            "evidence_exact": _evidence_exact(gold_refs, existing_refs),
            "abstained": bool(case.existing_result.get("abstained", False)),
            "fallback_triggered": bool(case.existing_result.get("fallback_triggered", False)),
            "fallback_reason": case.existing_result.get("fallback_reason"),
        },
        "ir": {
            "matched_unit_ids": ir_payload["matched_unit_ids"],
            "required_evidence_ids": ir_refs,
            "evidence_exact": _evidence_exact(gold_refs, ir_refs),
            "abstained": ir_payload["abstained"],
            "closure_complete": ir_payload["closure_complete"],
            "fallback_allowed": ir_payload["fallback_allowed"],
            "reason": ir_payload["reason"],
        },
    }


def _metrics(cases: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "case_count": len(cases),
        "pass_count": sum(1 for case in cases if case["passed"]),
        "fail_count": sum(1 for case in cases if not case["passed"]),
        "ir_evidence_exact_count": sum(1 for case in cases if case["ir"]["evidence_exact"]),
        "existing_evidence_exact_count": sum(1 for case in cases if case["existing"]["evidence_exact"]),
        "ir_evidence_exact_improvement_count": sum(
            1 for case in cases if case["ir"]["evidence_exact"] and not case["existing"]["evidence_exact"]
        ),
        "existing_fallback_triggered_count": sum(1 for case in cases if case["existing"]["fallback_triggered"]),
        "ir_fallback_allowed_count": sum(1 for case in cases if case["ir"]["fallback_allowed"]),
        "ir_abstention_count": sum(1 for case in cases if case["ir"]["abstained"]),
        "ir_closure_complete_count": sum(1 for case in cases if case["ir"]["closure_complete"]),
    }


def run_real_slice_semantic_ir_diagnostics(
    root: Path,
    slice_id: str,
    results_path: Path,
    *,
    run_id: str,
) -> dict[str, Any]:
    case_results = [_case_result(case) for case in build_real_slice_diagnostic_suite(root, slice_id, results_path)]
    return {
        "schema_version": "semantic-ir-real-slice-diagnostic-results-v1",
        "run_id": run_id,
        "slice_id": slice_id,
        "source_results": str(results_path),
        "scope": "hand-authored real slice IR; no model extraction; no benchmark expansion",
        "cases": case_results,
        "metrics": _metrics(case_results),
    }


def render_real_slice_semantic_ir_report(payload: dict[str, Any]) -> str:
    metrics = payload["metrics"]
    lines = [
        "# Real Slice Semantic IR Diagnostic Report",
        "",
        f"Run: `{payload['run_id']}`",
        "",
        "Scope: hand-authored real slice IR only; no model extraction; no benchmark expansion.",
        "",
        "## Metrics",
        "",
        f"- Passed: {metrics['pass_count']}/{metrics['case_count']}",
        f"- IR evidence exact: {metrics['ir_evidence_exact_count']}",
        f"- Existing evidence exact: {metrics['existing_evidence_exact_count']}",
        f"- IR evidence-exact improvements: {metrics['ir_evidence_exact_improvement_count']}",
        f"- Existing fallback triggered: {metrics['existing_fallback_triggered_count']}",
        f"- IR fallback allowed: {metrics['ir_fallback_allowed_count']}",
        f"- IR abstentions: {metrics['ir_abstention_count']}",
        "",
        "## Cases",
        "",
    ]
    for case in payload["cases"]:
        status = "PASS" if case["passed"] else "FAIL"
        lines.extend(
            [
                f"### {case['item_id']}: {status}",
                "",
                case["description"],
                "",
                f"- Category: `{case['category']}`",
                f"- Existing refs: `{case['existing']['retrieved_evidence_refs']}`",
                f"- Existing exact: `{case['existing']['evidence_exact']}`",
                f"- Existing fallback: `{case['existing']['fallback_triggered']}`",
                f"- IR refs: `{case['ir']['required_evidence_ids']}`",
                f"- IR exact: `{case['ir']['evidence_exact']}`",
                f"- IR abstained: `{case['ir']['abstained']}`",
                f"- IR reason: `{case['ir']['reason']}`",
                "",
            ]
        )
    lines.extend(
        [
            "## Interpretation",
            "",
            "This diagnostic shows that the event-role-evidence IR can be aligned to real frozen slice items and can express the known answerability, lexical fallback, conflict, update, and temporal evidence-closure cases.",
            "It is still hand-authored: it does not measure model extraction quality, does not generate final answers, and does not authorize full benchmark expansion.",
            "",
        ]
    )
    return "\n".join(lines)


def run_real_slice_semantic_ir_diagnostics_file(
    root: Path,
    slice_id: str,
    results_path: Path,
    output_path: Path,
    report_path: Path,
    *,
    run_id: str,
) -> dict[str, Any]:
    payload = run_real_slice_semantic_ir_diagnostics(root, slice_id, results_path, run_id=run_id)
    write_json_immutable(output_path, payload)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_real_slice_semantic_ir_report(payload), encoding="utf-8")
    return payload
