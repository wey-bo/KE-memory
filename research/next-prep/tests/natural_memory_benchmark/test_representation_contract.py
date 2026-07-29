from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from tools.natural_memory_benchmark.representation_contract import (
    REQUIRED_MEMORY_CAPABILITIES,
    CapabilityDeclaration,
    MemoryRepresentationBundle,
    NativeSemanticIrJsonAdapter,
    RepresentationProfile,
    assess_bundle_integrity,
    evaluate_adapter_conformance,
)
from tools.natural_memory_benchmark.semantic_ir import (
    ClosureRecord,
    EvidenceSpan,
    L1MemoryUnit,
    L2MemoryUnit,
    LinkBinding,
    Predicate,
    QuerySlotPlan,
    RoleBinding,
    SourceBinding,
)


def _profile() -> RepresentationProfile:
    return RepresentationProfile(
        representation_id="semantic-ir-native",
        family="semantic_ir",
        format_version="semantic-ir-v1",
        role="reference_carrier",
        capabilities=[
            CapabilityDeclaration(capability=capability, support_mode="native", location="semantic_ir")
            for capability in REQUIRED_MEMORY_CAPABILITIES
        ],
    )


def _source(evidence_id: str, text: str, *, turn_id: str, session_id: str) -> SourceBinding:
    return SourceBinding(
        speaker="user",
        source_status="user_reported",
        evidence_spans=[
            EvidenceSpan(
                evidence_id=evidence_id,
                turn_id=turn_id,
                session_id=session_id,
                char_start=0,
                char_end=len(text),
                text=text,
            )
        ],
    )


def _preference_unit(
    unit_id: str,
    evidence_id: str,
    value: str,
    *,
    lifecycle: str,
    links: LinkBinding | None = None,
) -> L1MemoryUnit:
    text = f"I prefer {value}."
    return L1MemoryUnit(
        unit_id=unit_id,
        kind="preference",
        predicate=Predicate(surface="prefer", sense="prefer-01", canonical_operator="prefers"),
        roles=[
            RoleBinding(role="ARG0", entity_id="user", role_name="experiencer"),
            RoleBinding(role="ARG1", entity_id=value, role_name="theme"),
        ],
        source=_source(evidence_id, text, turn_id=f"turn-{evidence_id}", session_id="session-1"),
        lifecycle=lifecycle,
        links=links or LinkBinding(),
        time={"valid_time": "2026-07-27", "transaction_time": "2026-07-27T12:00:00Z"},
    )


def _valid_bundle() -> MemoryRepresentationBundle:
    old = _preference_unit("l1-pref-old", "E-old", "tea", lifecycle="superseded")
    current = _preference_unit(
        "l1-pref-current",
        "E-current",
        "coffee",
        lifecycle="active",
        links=LinkBinding(supersedes=[old.unit_id]),
    )
    closure = ClosureRecord(
        closure_id="closure-current-preference",
        claim_or_query_id="query-current-preference",
        pattern="update_supersession",
        required_units=[
            {"unit_id": old.unit_id, "role": "previous_value"},
            {"unit_id": current.unit_id, "role": "current_value"},
        ],
        complete=True,
        reason="closure complete",
    )
    l2 = L2MemoryUnit(
        unit_id="l2-preference-profile",
        kind="preference_profile",
        abstracts=[old.unit_id, current.unit_id],
        summary="The user's current beverage preference is coffee.",
        assertions=["current_preference(user)=coffee"],
        closure_id=closure.closure_id,
        lifecycle="active",
        valid_time="2026-07-27",
        abstraction_method={"method": "rule_aggregate", "model_or_rule_version": "test-v1"},
        source_l1_units=[old.unit_id, current.unit_id],
        source_turns=["turn-E-old", "turn-E-current"],
        source_sessions=["session-1"],
    )
    query = QuerySlotPlan(
        query_id="query-current-preference",
        intent="preference_current",
        target_level="both",
        canonical_operator="prefers",
        closure_id=closure.closure_id,
    )
    return MemoryRepresentationBundle(
        bundle_id="bundle-preference",
        profile=_profile(),
        l1_units=[old, current],
        l2_units=[l2],
        closures=[closure],
        query_plans=[query],
        metadata={"scope": "test"},
    )


def test_bundle_rejects_duplicate_memory_unit_ids():
    bundle = _valid_bundle()

    with pytest.raises(ValidationError, match="duplicate memory unit ids"):
        MemoryRepresentationBundle(
            bundle_id="duplicate-units",
            profile=bundle.profile,
            l1_units=[bundle.l1_units[0], bundle.l1_units[0]],
            l2_units=[],
            closures=[],
            query_plans=[],
        )


def test_integrity_report_rejects_broken_cross_layer_and_incomplete_active_l2():
    bundle = _valid_bundle()
    broken_l2 = bundle.l2_units[0].model_copy(
        update={
            "abstracts": ["l1-missing"],
            "source_l1_units": ["l1-missing"],
            "closure_id": "closure-missing",
        }
    )
    broken = bundle.model_copy(update={"l2_units": [broken_l2]})

    report = assess_bundle_integrity(broken)

    assert report.valid is False
    assert "l2 l2-preference-profile references missing L1 unit l1-missing" in report.errors
    assert "l2 l2-preference-profile references missing closure closure-missing" in report.errors

    incomplete = bundle.closures[0].model_copy(update={"complete": False, "reason": "missing support"})
    incomplete_bundle = bundle.model_copy(update={"closures": [incomplete]})
    incomplete_report = assess_bundle_integrity(incomplete_bundle)
    assert "active l2 l2-preference-profile has incomplete closure closure-current-preference" in incomplete_report.errors


def test_integrity_report_rejects_conflicting_duplicate_evidence_definitions():
    bundle = _valid_bundle()
    conflicting = _preference_unit("l1-conflicting", "E-current", "water", lifecycle="active")
    conflicting = conflicting.model_copy(
        update={
            "source": conflicting.source.model_copy(
                update={
                    "evidence_spans": [
                        conflicting.source.evidence_spans[0].model_copy(
                            update={"turn_id": "turn-other", "text": "Different source text."}
                        )
                    ]
                }
            )
        }
    )
    candidate = bundle.model_copy(update={"l1_units": [*bundle.l1_units, conflicting]})

    report = assess_bundle_integrity(candidate)

    assert report.valid is False
    assert "evidence E-current has conflicting definitions" in report.errors


def test_native_semantic_ir_adapter_round_trips_and_preserves_query_results():
    bundle = _valid_bundle()

    report = evaluate_adapter_conformance(NativeSemanticIrJsonAdapter(profile=bundle.profile), bundle)

    assert report.status == "pass"
    assert report.integrity_valid is True
    assert report.round_trip_exact is True
    assert report.query_probe_count == 1
    assert report.query_probe_pass_count == 1
    assert report.hard_gate_failures == []


def test_lossy_adapter_fails_exact_round_trip_gate():
    bundle = _valid_bundle()

    class LossyAdapter(NativeSemanticIrJsonAdapter):
        def encode(self, value: MemoryRepresentationBundle) -> bytes:
            payload = json.loads(super().encode(value))
            payload["l1_units"][0]["predicate"]["sense"] = "unknown"
            return json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")

    report = evaluate_adapter_conformance(LossyAdapter(profile=bundle.profile), bundle)

    assert report.status == "fail"
    assert report.round_trip_exact is False
    assert "round_trip_not_exact" in report.hard_gate_failures


def test_incomplete_causal_closure_remains_abstained_after_round_trip():
    cause = L1MemoryUnit(
        unit_id="l1-feedback",
        kind="event",
        predicate=Predicate(surface="feedback", sense="feedback-observation", canonical_operator="mentions_feedback"),
        roles=[RoleBinding(role="ARG0", entity_id="user", role_name="source")],
        source=_source("E-feedback", "Feedback was collected.", turn_id="turn-feedback", session_id="session-2"),
    )
    effect = L1MemoryUnit(
        unit_id="l1-ui-change",
        kind="event",
        predicate=Predicate(surface="improved", sense="improvement/ui", canonical_operator="mentions_improvement"),
        roles=[RoleBinding(role="ARG1", entity_id="ui", role_name="theme")],
        source=_source("E-ui", "The UI was improved.", turn_id="turn-ui", session_id="session-2"),
    )
    closure = ClosureRecord(
        closure_id="closure-causal",
        claim_or_query_id="query-causal",
        pattern="causal_answerability",
        required_units=[
            {"unit_id": cause.unit_id, "role": "cause"},
            {"unit_id": effect.unit_id, "role": "effect"},
        ],
    )
    query = QuerySlotPlan(
        query_id="query-causal",
        intent="causal_how",
        target_level="L1",
        closure_id=closure.closure_id,
        required_closure_pattern="causal_answerability",
    )
    bundle = MemoryRepresentationBundle(
        bundle_id="bundle-causal",
        profile=_profile(),
        l1_units=[cause, effect],
        l2_units=[],
        closures=[closure],
        query_plans=[query],
    )

    report = evaluate_adapter_conformance(NativeSemanticIrJsonAdapter(profile=bundle.profile), bundle)

    assert report.status == "pass"
    assert report.query_probes[0].reference_result["abstained"] is True
    assert report.query_probes[0].reference_result["fallback_allowed"] is False
    assert report.query_probes[0].decoded_result == report.query_probes[0].reference_result
