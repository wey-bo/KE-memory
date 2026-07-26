from __future__ import annotations

import pytest
from pydantic import ValidationError

from ke_memory_demo.domain import (
    IndividualRef,
    KnowledgeEquation,
    Modality,
    OperatorApplication,
    OperatorRef,
    Speaker,
)
from ke_memory_demo.online.admission import AdmissionPolicy
from ke_memory_demo.online.models import (
    AdmissionStatus,
    MemoryKind,
    MemoryNamespace,
    SourceStatus,
)


def test_namespace_normalizes_values_and_rejects_empty_segments() -> None:
    namespace = MemoryNamespace(
        tenant_id=" tenant-a ",
        user_id=" user-1 ",
        agent_id=" assistant ",
    )

    assert namespace.tenant_id == "tenant-a"
    assert namespace.user_id == "user-1"
    assert namespace.agent_id == "assistant"

    with pytest.raises(ValidationError, match="must not be blank"):
        MemoryNamespace(tenant_id="tenant-a", user_id="   ", agent_id="assistant")


def test_user_preference_is_admitted_without_conflating_confidence_and_trust() -> None:
    assessment = AdmissionPolicy().assess(
        _equation(
            modality=Modality.PREFERENCE,
            speaker=Speaker.USER,
            confidence=0.82,
            operator="prefers",
            gloss="The user prefers concise answers.",
        )
    )

    assert assessment.status is AdmissionStatus.ADMITTED
    assert assessment.memory_kind is MemoryKind.PREFERENCE
    assert assessment.source_status is SourceStatus.USER_REPORTED
    assert assessment.extraction_confidence == 0.82
    assert assessment.epistemic_trust == 0.75
    assert assessment.memory_utility == 0.9
    assert assessment.reasons == ("durable-user-preference",)


def test_user_plan_is_admitted_as_task_memory() -> None:
    assessment = AdmissionPolicy().assess(
        _equation(
            modality=Modality.PLAN,
            speaker=Speaker.USER,
            confidence=0.9,
            operator="plans",
            gloss="The user plans to deploy the service tomorrow.",
        )
    )

    assert assessment.status is AdmissionStatus.ADMITTED
    assert assessment.memory_kind is MemoryKind.TASK
    assert assessment.memory_utility == 0.95


def test_tool_observation_is_admitted_with_high_epistemic_trust() -> None:
    assessment = AdmissionPolicy().assess(
        _equation(
            modality=Modality.FACT,
            speaker=Speaker.TOOL,
            confidence=0.96,
            operator="current_status",
            gloss="The deployment status is succeeded.",
        )
    )

    assert assessment.status is AdmissionStatus.ADMITTED
    assert assessment.memory_kind is MemoryKind.STATE
    assert assessment.source_status is SourceStatus.TOOL_OBSERVED
    assert assessment.epistemic_trust == 0.95


def test_agent_generated_fact_remains_candidate() -> None:
    assessment = AdmissionPolicy().assess(
        _equation(
            modality=Modality.FACT,
            speaker=Speaker.ASSISTANT,
            confidence=0.99,
            operator="located_in",
            gloss="The user is located in Shanghai.",
        )
    )

    assert assessment.status is AdmissionStatus.CANDIDATE
    assert assessment.source_status is SourceStatus.AGENT_GENERATED
    assert assessment.epistemic_trust == 0.3
    assert assessment.reasons == ("agent-generated-fact-requires-confirmation",)


def test_low_confidence_user_fact_is_candidate_and_question_is_rejected() -> None:
    policy = AdmissionPolicy()

    low_confidence = policy.assess(
        _equation(
            modality=Modality.FACT,
            speaker=Speaker.USER,
            confidence=0.4,
            operator="works_at",
            gloss="The user works at Example Corp.",
        )
    )
    question = policy.assess(
        _equation(
            modality=Modality.QUESTION,
            speaker=Speaker.USER,
            confidence=0.9,
            operator="asks_about",
            gloss="Does the user work at Example Corp?",
        )
    )

    assert low_confidence.status is AdmissionStatus.CANDIDATE
    assert low_confidence.reasons == ("extraction-confidence-below-admission-threshold",)
    assert question.status is AdmissionStatus.REJECTED
    assert question.memory_kind is MemoryKind.OTHER
    assert question.reasons == ("question-or-hypothesis-is-not-durable-memory",)


def _equation(
    *,
    modality: Modality,
    speaker: Speaker,
    confidence: float,
    operator: str,
    gloss: str,
) -> KnowledgeEquation:
    subject = IndividualRef(term_id="individual:user", label="user")
    value = IndividualRef(term_id=f"individual:{operator}:value", label="value")
    return KnowledgeEquation.create(
        level="turn",
        lhs=OperatorApplication(
            operator=OperatorRef(term_id=f"operator:{operator}", label=operator),
            arguments=(subject,),
        ),
        rhs=value,
        gloss=gloss,
        modality=modality,
        polarity="positive",
        lifecycle="active",
        speaker=speaker,
        confidence=confidence,
        produced_in_run_id="test-run",
        produced_in_stage="turn-ke-extracted",
    )
