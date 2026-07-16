from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import json
from typing import Literal, TypeVar, cast

import pytest
from pydantic import BaseModel, ValidationError

from ke_memory_demo.domain import (
    CoverageStatus,
    Exchange,
    Message,
    MessageRole,
    Modality,
    OntologyBinding,
    OntologyBindingStatus,
    OntologyRole,
    Polarity,
    Speaker,
    ToolEvent,
    ToolEventKind,
    content_id,
)
from ke_memory_demo.extraction import (
    UNRESOLVED_MARKER,
    DraftCoverageRange,
    DraftInformationUnit,
    DraftSpan,
    DraftSurfaceMention,
    ExtractionInvariantError,
    ProposalAssertionRef,
    ProposalConceptRef,
    ProposalIndividualRef,
    ProposalOperatorApplication,
    ProposalOperatorRef,
    TurnKEDraft,
    TurnKEExtractor,
    TurnKEOutput,
    TurnKEProposal,
)
from ke_memory_demo.infra.telemetry import TraceContext
from ke_memory_demo.ontology import (
    IndexIdentity,
    OntologyHealth,
    OntologyRelation,
    OntologyTerm,
)


ModelT = TypeVar("ModelT", bound=BaseModel)


class FakeModel:
    def __init__(self, draft: TurnKEDraft, output: TurnKEOutput) -> None:
        self.draft = draft
        self.output = output
        self.calls: list[tuple[type[BaseModel], Sequence[Mapping[str, object]], TraceContext]] = []

    async def complete(
        self,
        model_type: type[ModelT],
        messages: Sequence[Mapping[str, object]],
        trace_context: TraceContext | Mapping[str, object],
    ) -> ModelT:
        context = (
            trace_context
            if isinstance(trace_context, TraceContext)
            else TraceContext.model_validate(trace_context)
        )
        self.calls.append((cast(type[BaseModel], model_type), messages, context))
        if model_type is TurnKEDraft:
            return cast(ModelT, self.draft)
        if model_type is TurnKEOutput:
            return cast(ModelT, self.output)
        raise AssertionError(f"unexpected model type: {model_type}")


class FakeVocabulary:
    def __init__(
        self,
        bindings: Mapping[str, OntologyBinding],
        *,
        results: Sequence[OntologyBinding] | None = None,
    ) -> None:
        self.bindings = dict(bindings)
        self.results = tuple(results) if results is not None else None
        self.calls: list[tuple[str, ...]] = []

    async def resolve_terms(self, surface_terms: Sequence[str]) -> list[OntologyBinding]:
        self.calls.append(tuple(surface_terms))
        if self.results is not None:
            return list(self.results)
        return [self.bindings[surface] for surface in surface_terms]

    async def health(self) -> OntologyHealth:
        raise AssertionError("health must not be called during extraction")

    async def index_identity(self) -> IndexIdentity:
        raise AssertionError("index_identity must not be called during extraction")

    async def fetch_terms(self, document_ids: Sequence[str]) -> list[OntologyTerm]:
        raise AssertionError(f"fetch_terms must not be called: {document_ids}")

    async def fetch_relations(self, document_ids: Sequence[str]) -> list[OntologyRelation]:
        raise AssertionError(f"fetch_relations must not be called: {document_ids}")


def _exchange() -> Exchange:
    return Exchange(
        id="exchange-7",
        session_id="session-1",
        user=Message(
            id="user-1",
            role=MessageRole.USER,
            content="triangle special theorem",
            source_order=0,
        ),
        events=(
            ToolEvent(
                id="tool-1",
                kind=ToolEventKind.TOOL_RESULT,
                content='{"verbatim": "tool context"}',
                source_order=1,
            ),
        ),
        assistant=Message(
            id="assistant-1",
            role=MessageRole.ASSISTANT,
            content="Noted.",
            source_order=2,
        ),
        global_ordinal=3,
    )


def _draft() -> TurnKEDraft:
    return TurnKEDraft(
        information_units=(
            DraftInformationUnit(
                key="unit-triangle",
                gloss="The user prefers triangle.",
                modality=Modality.PREFERENCE,
                polarity=Polarity.POSITIVE,
                speaker=Speaker.USER,
                surface_mentions=(
                    DraftSurfaceMention(
                        surface_form="triangle", expected_role=OntologyRole.CONCEPT
                    ),
                ),
                source_spans=(DraftSpan(message_id="user-1", start_char=0, end_char=8),),
            ),
            DraftInformationUnit(
                key="unit-special",
                gloss="The user mentions a special theorem.",
                modality=Modality.FACT,
                polarity=Polarity.POSITIVE,
                speaker=Speaker.USER,
                surface_mentions=(
                    DraftSurfaceMention(
                        surface_form="special theorem",
                        expected_role=OntologyRole.CONCEPT,
                    ),
                ),
                source_spans=(DraftSpan(message_id="user-1", start_char=9, end_char=24),),
            ),
        ),
        coverage=(
            DraftCoverageRange(
                message_id="user-1",
                start_char=0,
                end_char=8,
                status=CoverageStatus.REPRESENTED,
                unit_keys=("unit-triangle",),
            ),
            DraftCoverageRange(
                message_id="user-1",
                start_char=8,
                end_char=9,
                status=CoverageStatus.NON_MEMORY,
            ),
            DraftCoverageRange(
                message_id="user-1",
                start_char=9,
                end_char=24,
                status=CoverageStatus.REPRESENTED,
                unit_keys=("unit-special",),
            ),
            DraftCoverageRange(
                message_id="assistant-1",
                start_char=0,
                end_char=6,
                status=CoverageStatus.CONTEXT_ONLY,
            ),
        ),
    )


def _output(
    *,
    triangle_candidate: str = "c7",
    triangle_kind: Literal["concept", "individual"] = "concept",
) -> TurnKEOutput:
    triangle_ref = (
        ProposalConceptRef(surface_form="triangle", candidate_id=triangle_candidate)
        if triangle_kind == "concept"
        else ProposalIndividualRef(surface_form="triangle", candidate_id=triangle_candidate)
    )
    return TurnKEOutput(
        proposals=(
            TurnKEProposal(
                key="ke-triangle",
                information_unit_keys=("unit-triangle",),
                lhs=triangle_ref,
                rhs=triangle_ref,
                gloss="The user prefers triangle.",
                modality=Modality.PREFERENCE,
                polarity=Polarity.POSITIVE,
                lifecycle="active",
                confidence=0.95,
            ),
            TurnKEProposal(
                key="ke-special",
                information_unit_keys=("unit-special",),
                lhs=ProposalConceptRef(
                    surface_form="special theorem",
                    candidate_id=UNRESOLVED_MARKER,
                ),
                rhs=ProposalConceptRef(
                    surface_form="special theorem",
                    candidate_id=UNRESOLVED_MARKER,
                ),
                gloss="The user mentions a special theorem.",
                modality=Modality.FACT,
                polarity=Polarity.POSITIVE,
                lifecycle="uncertain",
                confidence=0.7,
            ),
        )
    )


def _bindings() -> dict[str, OntologyBinding]:
    return {
        "special theorem": OntologyBinding(
            surface_form="special theorem",
            normalized_surface="special theorem",
            status=OntologyBindingStatus.UNRESOLVED,
        ),
        "triangle": OntologyBinding(
            surface_form="triangle",
            normalized_surface="triangle",
            status=OntologyBindingStatus.RESOLVED,
            document_id="c7",
            canonical_term="Triangle",
            role=OntologyRole.CONCEPT,
            source_type="mathematical_concept",
        ),
    }


@pytest.mark.asyncio
async def test_extractor_accepts_only_es_candidates_and_preserves_unresolved() -> None:
    model = FakeModel(_draft(), _output())
    vocabulary = FakeVocabulary(_bindings())

    result = await TurnKEExtractor(
        model,
        vocabulary,
        run_id="run-7",
    ).extract(_exchange())

    document_ids = {
        binding.document_id
        for ke in result.knowledge_equations
        for binding in ke.ontology_bindings
        if binding.document_id is not None
    }
    assert document_ids == {"c7"}
    assert any(
        binding.status.value == "unresolved"
        for ke in result.knowledge_equations
        for binding in ke.ontology_bindings
    )
    unresolved_id = content_id("unresolved-concept", "special theorem")
    assert any(
        getattr(ke.lhs, "term_id", None) == unresolved_id for ke in result.knowledge_equations
    )
    assert result.exchange_id == "exchange-7"
    assert vocabulary.calls == [("special theorem", "triangle")]

    triangle_ke = next(ke for ke in result.knowledge_equations if ke.modality.value == "preference")
    assert getattr(triangle_ke.lhs, "term_id", None) == "c7"
    assert triangle_ke.produced_in_run_id == "run-7"
    assert triangle_ke.produced_in_stage == "turn-ke-extracted"
    assert triangle_ke.evidence_refs[0].text_hash == hashlib.sha256(b"triangle").hexdigest()


@pytest.mark.asyncio
async def test_extractor_uses_deterministic_non_secret_traces_and_verbatim_tool_context() -> None:
    model = FakeModel(_draft(), _output())

    await TurnKEExtractor(
        model,
        FakeVocabulary(_bindings()),
        run_id="run-7",
    ).extract(_exchange())

    assert [call[2] for call in model.calls] == [
        TraceContext(
            operation="turn-ke-draft",
            metadata={"exchange_id": "exchange-7", "run_id": "run-7"},
        ),
        TraceContext(
            operation="turn-ke-bind",
            metadata={"exchange_id": "exchange-7", "run_id": "run-7"},
        ),
    ]
    assert [call[0] for call in model.calls] == [TurnKEDraft, TurnKEOutput]
    for _, messages, _ in model.calls:
        payload_message = next(message for message in messages if message["role"] == "user")
        payload = json.loads(str(payload_message["content"]))
        exchange_context = payload.get("exchange", payload.get("exchange_context"))
        assert exchange_context["events"][0]["content"] == '{"verbatim": "tool context"}'


@pytest.mark.asyncio
async def test_invalid_draft_fails_before_ontology_resolution() -> None:
    invalid = TurnKEDraft(
        information_units=_draft().information_units,
        coverage=tuple(entry for entry in _draft().coverage if entry.start_char != 8),
    )
    model = FakeModel(invalid, _output())
    vocabulary = FakeVocabulary(_bindings())

    with pytest.raises(ExtractionInvariantError, match="gap"):
        await TurnKEExtractor(model, vocabulary, run_id="run-7").extract(_exchange())

    assert vocabulary.calls == []
    assert len(model.calls) == 1


@pytest.mark.asyncio
async def test_invalid_evidence_span_fails_before_ontology_resolution() -> None:
    draft = _draft()
    invalid_unit = draft.information_units[0].model_copy(
        update={"source_spans": (DraftSpan(message_id="user-1", start_char=0, end_char=99),)}
    )
    invalid = TurnKEDraft(
        information_units=(invalid_unit, draft.information_units[1]),
        coverage=draft.coverage,
    )
    model = FakeModel(invalid, _output())
    vocabulary = FakeVocabulary(_bindings())

    with pytest.raises(ExtractionInvariantError, match="invalid evidence|outside"):
        await TurnKEExtractor(model, vocabulary, run_id="run-7").extract(_exchange())

    assert vocabulary.calls == []
    assert len(model.calls) == 1


@pytest.mark.asyncio
async def test_unknown_draft_coverage_unit_fails_before_ontology_resolution() -> None:
    draft = _draft()
    invalid_coverage = draft.coverage[0].model_copy(update={"unit_keys": ("missing-unit",)})
    invalid = TurnKEDraft(
        information_units=draft.information_units,
        coverage=(invalid_coverage, *draft.coverage[1:]),
    )
    model = FakeModel(invalid, _output())
    vocabulary = FakeVocabulary(_bindings())

    with pytest.raises(ExtractionInvariantError, match="unknown reference"):
        await TurnKEExtractor(model, vocabulary, run_id="run-7").extract(_exchange())

    assert vocabulary.calls == []
    assert len(model.calls) == 1


@pytest.mark.asyncio
async def test_unknown_proposal_unit_fails_after_binding_pass() -> None:
    invalid_proposal = (
        _output().proposals[0].model_copy(update={"information_unit_keys": ("missing-unit",)})
    )
    model = FakeModel(
        _draft(),
        TurnKEOutput(proposals=(invalid_proposal, _output().proposals[1])),
    )
    vocabulary = FakeVocabulary(_bindings())

    with pytest.raises(ExtractionInvariantError, match="unknown information unit"):
        await TurnKEExtractor(model, vocabulary, run_id="run-7").extract(_exchange())

    assert vocabulary.calls == [("special theorem", "triangle")]
    assert len(model.calls) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    ["missing", "extra", "wrong_order", "normalized", "duplicate"],
)
async def test_inconsistent_resolver_output_fails_before_binding_pass(case: str) -> None:
    normal = _bindings()
    special = normal["special theorem"]
    triangle = normal["triangle"]
    if case == "missing":
        results = (special,)
    elif case == "extra":
        results = (
            special,
            triangle,
            OntologyBinding(
                surface_form="square",
                normalized_surface="square",
                status=OntologyBindingStatus.UNRESOLVED,
            ),
        )
    elif case == "wrong_order":
        results = (triangle, special)
    elif case == "normalized":
        results = (
            special,
            triangle.model_copy(update={"normalized_surface": "wrong"}),
        )
    else:
        results = (special, special)
    model = FakeModel(_draft(), _output())
    vocabulary = FakeVocabulary(normal, results=results)

    with pytest.raises(
        ExtractionInvariantError,
        match="count|order|normalized|duplicate|omitted|unrequested",
    ):
        await TurnKEExtractor(model, vocabulary, run_id="run-7").extract(_exchange())

    assert vocabulary.calls == [("special theorem", "triangle")]
    assert len(model.calls) == 1


@pytest.mark.asyncio
async def test_unoffered_document_id_is_rejected() -> None:
    model = FakeModel(_draft(), _output(triangle_candidate="fabricated-id"))

    with pytest.raises(ExtractionInvariantError, match="unoffered"):
        await TurnKEExtractor(
            model,
            FakeVocabulary(_bindings()),
            run_id="run-7",
        ).extract(_exchange())


@pytest.mark.asyncio
async def test_expression_kind_must_match_surface_role() -> None:
    model = FakeModel(_draft(), _output(triangle_kind="individual"))
    vocabulary = FakeVocabulary(_bindings())

    with pytest.raises(ExtractionInvariantError, match="role"):
        await TurnKEExtractor(
            model,
            vocabulary,
            run_id="run-7",
        ).extract(_exchange())

    assert vocabulary.calls == [("special theorem", "triangle")]
    assert len(model.calls) == 2


@pytest.mark.asyncio
async def test_unresolved_role_document_cannot_be_selected_as_a_typed_term() -> None:
    bindings = _bindings()
    bindings["triangle"] = OntologyBinding(
        surface_form="triangle",
        normalized_surface="triangle",
        status=OntologyBindingStatus.UNRESOLVED_ROLE,
        document_id="roleless-7",
        canonical_term="Triangle",
        source_type="ambiguous",
    )
    model = FakeModel(_draft(), _output(triangle_candidate="roleless-7"))

    with pytest.raises(ExtractionInvariantError, match="unresolved-role"):
        await TurnKEExtractor(
            model,
            FakeVocabulary(bindings),
            run_id="run-7",
        ).extract(_exchange())


@pytest.mark.asyncio
async def test_unresolved_role_binding_is_retained_when_marker_is_selected() -> None:
    bindings = _bindings()
    bindings["triangle"] = OntologyBinding(
        surface_form="triangle",
        normalized_surface="triangle",
        status=OntologyBindingStatus.UNRESOLVED_ROLE,
        document_id="roleless-7",
        canonical_term="Triangle",
        source_type="ambiguous",
    )
    result = await TurnKEExtractor(
        FakeModel(_draft(), _output(triangle_candidate=UNRESOLVED_MARKER)),
        FakeVocabulary(bindings),
        run_id="run-7",
    ).extract(_exchange())

    triangle_ke = next(ke for ke in result.knowledge_equations if ke.modality.value == "preference")
    assert getattr(triangle_ke.lhs, "term_id", None) == content_id(
        "unresolved-concept",
        "triangle",
    )
    assert triangle_ke.ontology_bindings[0].status.value == "unresolved_role"
    assert triangle_ke.ontology_bindings[0].document_id == "roleless-7"
    assert getattr(triangle_ke.lhs, "term_id", None) != "roleless-7"


@pytest.mark.asyncio
async def test_normalized_raw_variants_share_lookup_but_preserve_labels_and_bindings() -> None:
    wide_triangle = "ＴＲＩＡＮＧＬＥ"
    exchange = Exchange(
        id="variant-exchange",
        session_id="session-1",
        user=Message(
            id="variant-user",
            role=MessageRole.USER,
            content=f"Triangle {wide_triangle}",
            source_order=0,
        ),
        assistant=Message(
            id="variant-assistant",
            role=MessageRole.ASSISTANT,
            content="",
            source_order=1,
        ),
        global_ordinal=4,
    )
    draft = TurnKEDraft(
        information_units=(
            DraftInformationUnit(
                key="ascii-unit",
                gloss="ASCII triangle",
                modality=Modality.FACT,
                polarity=Polarity.POSITIVE,
                speaker=Speaker.USER,
                surface_mentions=(
                    DraftSurfaceMention(
                        surface_form="Triangle",
                        expected_role=OntologyRole.CONCEPT,
                    ),
                ),
                source_spans=(DraftSpan(message_id="variant-user", start_char=0, end_char=8),),
            ),
            DraftInformationUnit(
                key="wide-unit",
                gloss="Wide triangle",
                modality=Modality.FACT,
                polarity=Polarity.POSITIVE,
                speaker=Speaker.USER,
                surface_mentions=(
                    DraftSurfaceMention(
                        surface_form=wide_triangle,
                        expected_role=OntologyRole.CONCEPT,
                    ),
                ),
                source_spans=(DraftSpan(message_id="variant-user", start_char=9, end_char=17),),
            ),
        ),
        coverage=(
            DraftCoverageRange(
                message_id="variant-user",
                start_char=0,
                end_char=8,
                status=CoverageStatus.REPRESENTED,
                unit_keys=("ascii-unit",),
            ),
            DraftCoverageRange(
                message_id="variant-user",
                start_char=8,
                end_char=9,
                status=CoverageStatus.NON_MEMORY,
            ),
            DraftCoverageRange(
                message_id="variant-user",
                start_char=9,
                end_char=17,
                status=CoverageStatus.REPRESENTED,
                unit_keys=("wide-unit",),
            ),
        ),
    )
    output = TurnKEOutput(
        proposals=tuple(
            TurnKEProposal(
                key=key,
                information_unit_keys=(unit_key,),
                lhs=ProposalConceptRef(surface_form=raw, candidate_id="c7"),
                rhs=ProposalConceptRef(surface_form=raw, candidate_id="c7"),
                gloss=f"Remember {raw}",
                modality=Modality.FACT,
                polarity=Polarity.POSITIVE,
                lifecycle="active",
                confidence=0.9,
            )
            for key, unit_key, raw in (
                ("ascii-ke", "ascii-unit", "Triangle"),
                ("wide-ke", "wide-unit", wide_triangle),
            )
        )
    )
    vocabulary = FakeVocabulary(
        {
            "Triangle": OntologyBinding(
                surface_form="Triangle",
                normalized_surface="triangle",
                status=OntologyBindingStatus.RESOLVED,
                document_id="c7",
                canonical_term="Triangle",
                role=OntologyRole.CONCEPT,
                source_type="mathematical_concept",
            )
        }
    )

    result = await TurnKEExtractor(
        FakeModel(draft, output),
        vocabulary,
        run_id="run-variants",
    ).extract(exchange)

    assert vocabulary.calls == [("Triangle",)]
    by_label = {
        getattr(equation.lhs, "label", ""): equation for equation in result.knowledge_equations
    }
    assert set(by_label) == {"Triangle", wide_triangle}
    for raw, equation in by_label.items():
        assert getattr(equation.lhs, "term_id", None) == "c7"
        assert equation.ontology_bindings[0].surface_form == raw
        assert equation.ontology_bindings[0].normalized_surface == "triangle"


@pytest.mark.asyncio
async def test_fan_in_combines_all_unit_evidence_and_coverage_into_one_ke() -> None:
    output = TurnKEOutput(
        proposals=(
            TurnKEProposal(
                key="combined",
                information_unit_keys=("unit-triangle", "unit-special"),
                lhs=ProposalConceptRef(surface_form="triangle", candidate_id="c7"),
                rhs=ProposalConceptRef(
                    surface_form="special theorem",
                    candidate_id=UNRESOLVED_MARKER,
                ),
                gloss="Triangle relates to the special theorem.",
                modality=Modality.FACT,
                polarity=Polarity.POSITIVE,
                lifecycle="active",
                confidence=0.85,
            ),
        )
    )

    result = await TurnKEExtractor(
        FakeModel(_draft(), output),
        FakeVocabulary(_bindings()),
        run_id="run-7",
    ).extract(_exchange())

    equation = result.knowledge_equations[0]
    assert tuple((span.start_char, span.end_char) for span in equation.evidence_refs) == (
        (0, 8),
        (9, 24),
    )
    assert all(
        entry.ke_ids == (equation.id,)
        for entry in result.coverage
        if entry.status is CoverageStatus.REPRESENTED
    )


@pytest.mark.asyncio
async def test_fan_out_maps_one_unit_to_every_realizing_final_ke_id() -> None:
    base = _output().proposals[0]
    dependent = TurnKEProposal(
        key="ke-triangle-derived",
        information_unit_keys=("unit-triangle",),
        lhs=ProposalAssertionRef(assertion_key=base.key),
        rhs=ProposalConceptRef(surface_form="triangle", candidate_id="c7"),
        gloss="Derived triangle assertion.",
        modality=Modality.FACT,
        polarity=Polarity.POSITIVE,
        lifecycle="active",
        confidence=0.8,
    )
    output = TurnKEOutput(proposals=(dependent, base, _output().proposals[1]))

    result = await TurnKEExtractor(
        FakeModel(_draft(), output),
        FakeVocabulary(_bindings()),
        run_id="run-7",
    ).extract(_exchange())

    triangle_equations = tuple(
        equation
        for equation in result.knowledge_equations
        if equation.evidence_refs[0].start_char == 0
    )
    assert len(triangle_equations) == 2
    triangle_coverage = next(
        entry
        for entry in result.coverage
        if entry.start_char == 0 and entry.status is CoverageStatus.REPRESENTED
    )
    assert triangle_coverage.ke_ids == tuple(sorted(equation.id for equation in triangle_equations))


@pytest.mark.asyncio
async def test_nested_expressions_attach_each_applicable_binding_once() -> None:
    exchange = Exchange(
        id="nested-exchange",
        session_id="session-1",
        user=Message(
            id="nested-user",
            role=MessageRole.USER,
            content="Alice likes triangle",
            source_order=0,
        ),
        assistant=Message(
            id="nested-assistant",
            role=MessageRole.ASSISTANT,
            content="",
            source_order=1,
        ),
        global_ordinal=5,
    )
    draft = TurnKEDraft(
        information_units=(
            DraftInformationUnit(
                key="nested-unit",
                gloss="Alice likes triangle.",
                modality=Modality.FACT,
                polarity=Polarity.POSITIVE,
                speaker=Speaker.USER,
                surface_mentions=(
                    DraftSurfaceMention(
                        surface_form="Alice", expected_role=OntologyRole.INDIVIDUAL
                    ),
                    DraftSurfaceMention(surface_form="likes", expected_role=OntologyRole.OPERATOR),
                    DraftSurfaceMention(
                        surface_form="triangle", expected_role=OntologyRole.CONCEPT
                    ),
                ),
                source_spans=(DraftSpan(message_id="nested-user", start_char=0, end_char=20),),
            ),
        ),
        coverage=(
            DraftCoverageRange(
                message_id="nested-user",
                start_char=0,
                end_char=20,
                status=CoverageStatus.REPRESENTED,
                unit_keys=("nested-unit",),
            ),
        ),
    )
    nested_application = ProposalOperatorApplication(
        operator=ProposalOperatorRef(surface_form="likes", candidate_id="o1"),
        arguments=(
            ProposalIndividualRef(surface_form="Alice", candidate_id="i1"),
            ProposalConceptRef(surface_form="triangle", candidate_id="c1"),
        ),
    )
    output = TurnKEOutput(
        proposals=(
            TurnKEProposal(
                key="nested-ke",
                information_unit_keys=("nested-unit",),
                lhs=ProposalIndividualRef(surface_form="Alice", candidate_id="i1"),
                rhs=ProposalOperatorApplication(
                    operator=ProposalOperatorRef(surface_form="likes", candidate_id="o1"),
                    arguments=(
                        ProposalConceptRef(surface_form="triangle", candidate_id="c1"),
                        nested_application,
                    ),
                ),
                gloss="Alice likes triangle recursively.",
                modality=Modality.FACT,
                polarity=Polarity.POSITIVE,
                lifecycle="active",
                confidence=0.9,
            ),
        )
    )
    vocabulary = FakeVocabulary(
        {
            "Alice": OntologyBinding(
                surface_form="Alice",
                normalized_surface="alice",
                status=OntologyBindingStatus.RESOLVED,
                document_id="i1",
                canonical_term="Alice",
                role=OntologyRole.INDIVIDUAL,
                source_type="person",
            ),
            "likes": OntologyBinding(
                surface_form="likes",
                normalized_surface="likes",
                status=OntologyBindingStatus.RESOLVED,
                document_id="o1",
                canonical_term="likes",
                role=OntologyRole.OPERATOR,
                source_type="relation",
            ),
            "triangle": OntologyBinding(
                surface_form="triangle",
                normalized_surface="triangle",
                status=OntologyBindingStatus.RESOLVED,
                document_id="c1",
                canonical_term="Triangle",
                role=OntologyRole.CONCEPT,
                source_type="mathematical_concept",
            ),
        }
    )

    result = await TurnKEExtractor(
        FakeModel(draft, output),
        vocabulary,
        run_id="run-nested",
    ).extract(exchange)

    assert vocabulary.calls == [("Alice", "likes", "triangle")]
    bindings = result.knowledge_equations[0].ontology_bindings
    assert len(bindings) == 3
    assert {binding.document_id for binding in bindings} == {"i1", "o1", "c1"}


@pytest.mark.asyncio
async def test_binding_prompt_contains_safe_context_and_only_selectable_candidates() -> None:
    bindings = _bindings()
    bindings["special theorem"] = OntologyBinding(
        surface_form="special theorem",
        normalized_surface="special theorem",
        status=OntologyBindingStatus.UNRESOLVED_ROLE,
        document_id="roleless-private-id",
        canonical_term="Special theorem",
        source_type="ambiguous",
    )
    model = FakeModel(_draft(), _output())

    await TurnKEExtractor(
        model,
        FakeVocabulary(bindings),
        run_id="run-7",
    ).extract(_exchange())

    binding_message = model.calls[1][1][1]
    content = str(binding_message["content"])
    payload = json.loads(content)
    bundles = payload["candidate_bundles"]
    assert {bundle["offered_document_id"] for bundle in bundles} == {None, "c7"}
    assert {bundle["unresolved_marker"] for bundle in bundles} == {UNRESOLVED_MARKER}
    assert "roleless-private-id" not in content
    assert payload["exchange_context"]["events"][0]["content"] == ('{"verbatim": "tool context"}')
    assert payload["validated_draft"] == _draft().model_dump(mode="json")


@pytest.mark.asyncio
async def test_assertion_references_are_resolved_in_topological_order() -> None:
    output = TurnKEOutput(
        proposals=(
            TurnKEProposal(
                key="dependent",
                information_unit_keys=("unit-triangle",),
                lhs=ProposalAssertionRef(assertion_key="base"),
                rhs=ProposalConceptRef(surface_form="triangle", candidate_id="c7"),
                gloss="A claim about the base assertion.",
                modality=Modality.FACT,
                polarity=Polarity.POSITIVE,
                lifecycle="active",
                confidence=0.8,
            ),
            TurnKEProposal(
                key="base",
                information_unit_keys=("unit-triangle",),
                lhs=ProposalConceptRef(surface_form="triangle", candidate_id="c7"),
                rhs=ProposalConceptRef(surface_form="triangle", candidate_id="c7"),
                gloss="The base assertion.",
                modality=Modality.FACT,
                polarity=Polarity.POSITIVE,
                lifecycle="active",
                confidence=0.9,
            ),
            TurnKEProposal(
                key="special",
                information_unit_keys=("unit-special",),
                lhs=ProposalConceptRef(
                    surface_form="special theorem",
                    candidate_id=UNRESOLVED_MARKER,
                ),
                rhs=ProposalConceptRef(
                    surface_form="special theorem",
                    candidate_id=UNRESOLVED_MARKER,
                ),
                gloss="The special theorem.",
                modality=Modality.FACT,
                polarity=Polarity.POSITIVE,
                lifecycle="active",
                confidence=0.7,
            ),
        )
    )

    result = await TurnKEExtractor(
        FakeModel(_draft(), output),
        FakeVocabulary(_bindings()),
        run_id="run-7",
    ).extract(_exchange())

    base, dependent, _special = result.knowledge_equations
    assert dependent.lhs.kind == "assertion"
    assert dependent.lhs.assertion_id == base.id


@pytest.mark.asyncio
@pytest.mark.parametrize("reference", ["missing", "dependent"])
async def test_dangling_and_cyclic_assertion_references_are_rejected(reference: str) -> None:
    output = TurnKEOutput(
        proposals=(
            TurnKEProposal(
                key="dependent",
                information_unit_keys=("unit-triangle",),
                lhs=ProposalAssertionRef(assertion_key=reference),
                rhs=ProposalConceptRef(surface_form="triangle", candidate_id="c7"),
                gloss="Invalid assertion reference.",
                modality=Modality.FACT,
                polarity=Polarity.POSITIVE,
                lifecycle="active",
                confidence=0.5,
            ),
            _output().proposals[1],
        )
    )

    with pytest.raises(ExtractionInvariantError, match="dangling|cycle"):
        await TurnKEExtractor(
            FakeModel(_draft(), output),
            FakeVocabulary(_bindings()),
            run_id="run-7",
        ).extract(_exchange())


@pytest.mark.asyncio
async def test_every_represented_unit_must_be_realized_by_a_final_ke() -> None:
    output = TurnKEOutput(proposals=(_output().proposals[0],))

    with pytest.raises(ExtractionInvariantError, match="not realized"):
        await TurnKEExtractor(
            FakeModel(_draft(), output),
            FakeVocabulary(_bindings()),
            run_id="run-7",
        ).extract(_exchange())


def test_draft_models_are_frozen_tuple_backed_and_forbid_extra_fields() -> None:
    draft = _draft()
    assert isinstance(draft.information_units, tuple)
    assert isinstance(draft.information_units[0].source_spans, tuple)

    with pytest.raises(ValidationError, match="frozen"):
        draft.coverage = ()  # type: ignore[misc]
    with pytest.raises(ValidationError, match="Extra inputs"):
        DraftSpan.model_validate(
            {"message_id": "user-1", "start_char": 0, "end_char": 1, "hash": "bad"}
        )


def test_turn_output_rejects_duplicate_proposal_keys_and_unsupported_lifecycle() -> None:
    with pytest.raises(ValidationError, match="duplicate"):
        TurnKEOutput(proposals=(_output().proposals[0], _output().proposals[0]))

    proposal = _output().proposals[0].model_dump(mode="python")
    proposal["lifecycle"] = "superseded"
    with pytest.raises(ValidationError, match="active|uncertain"):
        TurnKEProposal.model_validate(proposal)
