from __future__ import annotations

from datetime import UTC, datetime
import hashlib

import pytest

from ke_memory_demo.domain import (
    AssertionRef,
    ConceptRef,
    IndividualRef,
    KnowledgeEquation,
    MessageSpan,
    Modality,
    OperatorApplication,
    OperatorRef,
    Speaker,
)
from ke_memory_demo.online.admission import AdmissionPolicy
from ke_memory_demo.online.keol_bridge import KEOLBundleCompiler
from ke_memory_demo.online.models import MemoryNamespace

# KEOL is a private dependency, so a runner without credentials cannot import it. Skip
# at collection rather than failing: a bare `from onto.models import ...` aborts the
# whole session, which took the entire suite down with it on CI. The assertions below
# are untouched -- when KEOL is present these tests run exactly as before, and this
# file's own coverage is simply absent when it is not.
onto_models = pytest.importorskip(
    "onto.models", reason="KEOL is not available; run scripts/ci/check.sh with KEOL_SOURCE set"
)

Assertion = onto_models.Assertion
Concept = onto_models.Concept
Evidence = onto_models.Evidence
Individual = onto_models.Individual
Operator = onto_models.Operator
WorkflowRun = onto_models.WorkflowRun


RECORDED_AT = datetime(2026, 7, 26, 8, 0, tzinfo=UTC)


def test_compiler_emits_deterministic_closed_bundle_validated_by_fixed_keol_models() -> None:
    text = "I prefer concise answers with exact evidence."
    equation = _equation(text)
    compiler = KEOLBundleCompiler()
    namespace = MemoryNamespace(
        tenant_id="tenant-a",
        user_id="user-1",
        agent_id="assistant",
    )
    assessment = AdmissionPolicy().assess(equation)

    first = compiler.compile(
        namespace=namespace,
        equation=equation,
        assessment=assessment,
        source_messages={"message:user-1": text},
        recorded_at=RECORDED_AT,
    )
    second = compiler.compile(
        namespace=namespace,
        equation=equation,
        assessment=assessment,
        source_messages={"message:user-1": text},
        recorded_at=RECORDED_AT,
    )

    assert first == second
    assert len(first.concepts) == 1
    assert len(first.individuals) == 1
    assert len(first.operators) == 1
    assert len(first.assertions) == 1
    assert len(first.evidence) == 1
    assert len(first.workflow_runs) == 1

    concept = Concept.model_validate(first.concepts[0])
    individual = Individual.model_validate(first.individuals[0])
    operator = Operator.model_validate(first.operators[0])
    assertion = Assertion.model_validate(first.assertions[0])
    evidence = Evidence.model_validate(first.evidence[0])
    workflow_run = WorkflowRun.model_validate(first.workflow_runs[0])

    assert assertion.lhs.operator_id == operator.id
    assert assertion.lhs.arguments[0].term.id == individual.id
    assert assertion.rhs.id == concept.id
    assert assertion.evidence_ids == [evidence.id]
    assert assertion.workflow_run_id == workflow_run.id
    assert evidence.quote == text[2:24]
    assert evidence.content_hash == hashlib.sha256(evidence.quote.encode("utf-8")).hexdigest()
    assert assertion.metadata["source_status"] == "user_reported"
    assert assertion.metadata["tenant_id"] == "tenant-a"
    assert concept.metadata["source_term_id"] == "concept:concise-answer"

    first.validate_closed()


def test_compiler_rejects_missing_or_changed_exact_evidence() -> None:
    text = "I prefer concise answers with exact evidence."
    equation = _equation(text)
    compiler = KEOLBundleCompiler()
    namespace = MemoryNamespace(
        tenant_id="tenant-a",
        user_id="user-1",
        agent_id="assistant",
    )
    assessment = AdmissionPolicy().assess(equation)

    with pytest.raises(ValueError, match="missing source message"):
        compiler.compile(
            namespace=namespace,
            equation=equation,
            assessment=assessment,
            source_messages={},
            recorded_at=RECORDED_AT,
        )

    with pytest.raises(ValueError, match="span text_hash does not match"):
        compiler.compile(
            namespace=namespace,
            equation=equation,
            assessment=assessment,
            source_messages={"message:user-1": text.replace("concise", "long")},
            recorded_at=RECORDED_AT,
        )


def test_compiler_rejects_dangling_assertion_terms() -> None:
    equation = KnowledgeEquation.create(
        level="turn",
        lhs=AssertionRef(assertion_id="assertion:missing"),
        rhs=IndividualRef(term_id="individual:value", label="value"),
        gloss="A dangling nested assertion must not be persisted.",
        modality=Modality.FACT,
        polarity="positive",
        lifecycle="active",
        speaker=Speaker.USER,
        confidence=0.9,
        produced_in_run_id="run:test",
        produced_in_stage="turn-ke-extracted",
    )

    with pytest.raises(ValueError, match="dangling assertion term"):
        KEOLBundleCompiler().compile(
            namespace=MemoryNamespace(
                tenant_id="tenant-a",
                user_id="user-1",
                agent_id="assistant",
            ),
            equation=equation,
            assessment=AdmissionPolicy().assess(equation),
            source_messages={},
            recorded_at=RECORDED_AT,
        )


def _equation(text: str) -> KnowledgeEquation:
    quote = text[2:24]
    return KnowledgeEquation.create(
        level="turn",
        lhs=OperatorApplication(
            operator=OperatorRef(term_id="operator:prefers", label="prefers"),
            arguments=(IndividualRef(term_id="individual:user", label="user"),),
        ),
        rhs=ConceptRef(term_id="concept:concise-answer", label="concise answer"),
        gloss="The user prefers concise answers.",
        modality=Modality.PREFERENCE,
        polarity="positive",
        lifecycle="active",
        speaker=Speaker.USER,
        evidence_refs=(
            MessageSpan(
                message_id="message:user-1",
                start_char=2,
                end_char=24,
                text_hash=hashlib.sha256(quote.encode("utf-8")).hexdigest(),
            ),
        ),
        confidence=0.91,
        produced_in_run_id="run:test",
        produced_in_stage="turn-ke-extracted",
    )
