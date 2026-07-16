from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import heapq
from pathlib import Path
from typing import Protocol, TypeVar, cast
import unicodedata

from pydantic import BaseModel, ValidationError

from ke_memory_demo.core.json import JsonObject, JsonValue, canonical_json
from ke_memory_demo.domain import (
    AssertionRef,
    ConceptRef,
    CoverageEntry,
    CoverageStatus,
    Exchange,
    Expression,
    IndividualRef,
    KnowledgeEquation,
    Message,
    MessageRole,
    MessageSpan,
    OntologyBinding,
    OntologyBindingStatus,
    OntologyRole,
    OperatorApplication,
    OperatorRef,
    Speaker,
    content_id,
)
from ke_memory_demo.infra.telemetry import TraceContext
from ke_memory_demo.ontology import OntologyVocabulary

from .coverage import CoverageInvariantError, CoverageValidator
from .schemas import (
    UNRESOLVED_MARKER,
    DraftInformationUnit,
    DraftSpan,
    ProposalAssertionRef,
    ProposalConceptRef,
    ProposalExpression,
    ProposalIndividualRef,
    ProposalOperatorApplication,
    SurfaceCandidateBundle,
    TurnKEDraft,
    TurnKEOutput,
    TurnKEProposal,
    TurnExtractionResult,
)


TURN_KE_STAGE = "turn-ke-extracted"
_PROMPT_ROOT = Path(__file__).resolve().parents[3] / "prompts"

ModelRecordT = TypeVar("ModelRecordT", bound=BaseModel)


class StructuredCompletionClient(Protocol):
    async def complete(
        self,
        model_type: type[ModelRecordT],
        messages: Sequence[Mapping[str, object]],
        trace_context: TraceContext | Mapping[str, object],
    ) -> ModelRecordT: ...


class ExtractionInvariantError(ValueError):
    """Raised when model output violates the extraction trust boundary."""


@dataclass(frozen=True)
class _Candidate:
    bundle: SurfaceCandidateBundle
    binding: OntologyBinding


@dataclass(frozen=True)
class _ValidatedDraft:
    evidence_by_unit: Mapping[str, tuple[MessageSpan, ...]]
    coverage_by_message: Mapping[str, tuple[CoverageEntry, ...]]


class TurnKEExtractor:
    def __init__(
        self,
        model: StructuredCompletionClient,
        vocabulary: OntologyVocabulary,
        *,
        run_id: str,
    ) -> None:
        if not run_id:
            raise ValueError("run_id must not be empty")
        self._model = model
        self._vocabulary = vocabulary
        self._run_id = run_id

    async def extract(self, exchange: Exchange) -> TurnExtractionResult:
        draft_response = await self._model.complete(
            TurnKEDraft,
            self._draft_messages(exchange),
            self._trace(exchange, "turn-ke-draft"),
        )
        draft = _revalidate_model(TurnKEDraft, draft_response, "turn KE draft")
        validated_draft = self._validate_draft(exchange, draft)

        candidates = await self._resolve_candidates(draft)
        output_response = await self._model.complete(
            TurnKEOutput,
            self._binding_messages(exchange, draft, candidates),
            self._trace(exchange, "turn-ke-bind"),
        )
        output = _revalidate_model(TurnKEOutput, output_response, "turn KE output")
        return self._build_result(exchange, draft, validated_draft, candidates, output)

    def _draft_messages(self, exchange: Exchange) -> list[dict[str, object]]:
        payload: JsonObject = {
            "task": "draft_turn_knowledge_equations",
            "exchange": cast(JsonValue, exchange.model_dump(mode="json")),
        }
        return [
            {"role": "system", "content": _read_prompt("turn_ke/system.md")},
            {"role": "user", "content": _json_text(payload)},
        ]

    def _binding_messages(
        self,
        exchange: Exchange,
        draft: TurnKEDraft,
        candidates: Mapping[str, _Candidate],
    ) -> list[dict[str, object]]:
        payload: JsonObject = {
            "task": "bind_turn_knowledge_equations",
            "exchange_context": cast(JsonValue, exchange.model_dump(mode="json")),
            "validated_draft": cast(JsonValue, draft.model_dump(mode="json")),
            "candidate_bundles": [
                cast(JsonValue, candidate.bundle.model_dump(mode="json"))
                for _, candidate in sorted(candidates.items())
            ],
        }
        return [
            {"role": "system", "content": _read_prompt("turn_ke/system.md")},
            {"role": "user", "content": _json_text(payload)},
        ]

    def _trace(self, exchange: Exchange, operation: str) -> TraceContext:
        return TraceContext(
            operation=operation,
            metadata={"exchange_id": exchange.id, "run_id": self._run_id},
        )

    def _validate_draft(self, exchange: Exchange, draft: TurnKEDraft) -> _ValidatedDraft:
        messages = _messages_by_id(exchange)
        evidence_by_unit: dict[str, tuple[MessageSpan, ...]] = {}
        for unit in draft.information_units:
            evidence = tuple(
                self._validated_span(unit, span, messages) for span in unit.source_spans
            )
            evidence = _sorted_unique_spans(evidence, messages)
            actual_speaker = _speaker_for_evidence(evidence, messages)
            if unit.speaker is not actual_speaker:
                raise ExtractionInvariantError(
                    f"information unit {unit.key} speaker {unit.speaker.value} does not match "
                    f"its {actual_speaker.value} evidence"
                )
            for mention in unit.surface_mentions:
                if not normalize_surface(mention.surface_form):
                    raise ExtractionInvariantError(
                        f"information unit {unit.key} contains an empty normalized surface"
                    )
            evidence_by_unit[unit.key] = evidence

        unit_keys = set(evidence_by_unit)
        raw_coverage: dict[str, list[CoverageEntry]] = defaultdict(list)
        for entry in draft.coverage:
            if entry.message_id not in messages:
                raise ExtractionInvariantError(
                    f"draft coverage references unknown message {entry.message_id}"
                )
            raw_coverage[entry.message_id].append(
                CoverageEntry(
                    message_id=entry.message_id,
                    start_char=entry.start_char,
                    end_char=entry.end_char,
                    status=entry.status,
                    ke_ids=entry.unit_keys,
                )
            )

        coverage_by_message: dict[str, tuple[CoverageEntry, ...]] = {}
        try:
            for message in _messages_in_source_order(exchange):
                coverage_by_message[message.id] = CoverageValidator.validate(
                    message,
                    raw_coverage.get(message.id, ()),
                    known_references=unit_keys,
                )
        except CoverageInvariantError as error:
            raise ExtractionInvariantError(str(error)) from error

        return _ValidatedDraft(
            evidence_by_unit=evidence_by_unit,
            coverage_by_message=coverage_by_message,
        )

    def _validated_span(
        self,
        unit: DraftInformationUnit,
        span: DraftSpan,
        messages: Mapping[str, Message],
    ) -> MessageSpan:
        message = messages.get(span.message_id)
        if message is None:
            raise ExtractionInvariantError(
                f"information unit {unit.key} references unknown message {span.message_id}"
            )
        text = message.content[span.start_char : span.end_char]
        evidence = MessageSpan(
            message_id=span.message_id,
            start_char=span.start_char,
            end_char=span.end_char,
            text_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        )
        try:
            message.validate_span(evidence)
        except ValueError as error:
            raise ExtractionInvariantError(
                f"information unit {unit.key} has invalid evidence: {error}"
            ) from error
        return evidence

    async def _resolve_candidates(
        self,
        draft: TurnKEDraft,
    ) -> dict[str, _Candidate]:
        surface_details: dict[str, tuple[set[str], set[OntologyRole]]] = {}
        for unit in draft.information_units:
            for mention in unit.surface_mentions:
                normalized = normalize_surface(mention.surface_form)
                raw_forms, roles = surface_details.setdefault(normalized, (set(), set()))
                raw_forms.add(mention.surface_form)
                roles.add(mention.expected_role)

        queries = tuple(
            min(surface_details[normalized][0]) for normalized in sorted(surface_details)
        )
        bindings = await self._vocabulary.resolve_terms(queries) if queries else []

        if len(bindings) != len(queries):
            raise ExtractionInvariantError(
                "ontology resolver result count does not match requested surfaces"
            )
        returned: dict[str, OntologyBinding] = {}
        expected_normalized = set(surface_details)
        for query, binding in zip(queries, bindings, strict=True):
            expected = normalize_surface(query)
            normalized = normalize_surface(binding.surface_form)
            if normalized != expected:
                raise ExtractionInvariantError(
                    "ontology resolver result order does not match requested surfaces"
                )
            if normalized not in expected_normalized:
                raise ExtractionInvariantError(
                    f"ontology resolver returned an unrequested surface: {binding.surface_form}"
                )
            if normalized in returned:
                raise ExtractionInvariantError(
                    f"ontology resolver returned duplicate surface: {binding.surface_form}"
                )
            returned[normalized] = binding
        missing = sorted(expected_normalized.difference(returned))
        if missing:
            raise ExtractionInvariantError(f"ontology resolver omitted surface: {missing[0]}")

        candidates: dict[str, _Candidate] = {}
        for normalized in sorted(surface_details):
            raw_forms, expected_roles = surface_details[normalized]
            binding = returned[normalized]
            if normalize_surface(binding.normalized_surface) != normalized:
                raise ExtractionInvariantError(
                    f"ontology resolver normalized surface mismatch for {min(raw_forms)}"
                )
            offered_document_id = None
            offered_role = None
            if binding.status is OntologyBindingStatus.RESOLVED:
                offered_document_id = binding.document_id
                offered_role = binding.role
            bundle = SurfaceCandidateBundle(
                surface_form=min(raw_forms),
                normalized_surface=normalized,
                expected_roles=tuple(sorted(expected_roles, key=lambda role: role.value)),
                binding_status=binding.status,
                offered_document_id=offered_document_id,
                offered_role=offered_role,
            )
            candidates[normalized] = _Candidate(bundle=bundle, binding=binding)
        return candidates

    def _build_result(
        self,
        exchange: Exchange,
        draft: TurnKEDraft,
        validated_draft: _ValidatedDraft,
        candidates: Mapping[str, _Candidate],
        output: TurnKEOutput,
    ) -> TurnExtractionResult:
        units = {unit.key: unit for unit in draft.information_units}
        ordered_proposals = _topological_proposals(output.proposals, set(units))
        messages = _messages_by_id(exchange)
        equations_by_key: dict[str, KnowledgeEquation] = {}
        equation_ids_by_unit: dict[str, list[str]] = defaultdict(list)

        for proposal in ordered_proposals:
            evidence = _proposal_evidence(
                proposal,
                validated_draft.evidence_by_unit,
                messages,
            )
            allowed_mentions = _allowed_mentions(proposal, units)
            used_bindings: list[OntologyBinding] = []
            lhs = _build_expression(
                proposal.lhs,
                candidates,
                allowed_mentions,
                equations_by_key,
                used_bindings,
            )
            rhs = _build_expression(
                proposal.rhs,
                candidates,
                allowed_mentions,
                equations_by_key,
                used_bindings,
            )
            equation = KnowledgeEquation.create(
                level="turn",
                lhs=lhs,
                rhs=rhs,
                gloss=proposal.gloss,
                modality=proposal.modality,
                polarity=proposal.polarity,
                lifecycle=proposal.lifecycle,
                speaker=_speaker_for_evidence(evidence, messages),
                temporal=proposal.temporal,
                ontology_bindings=_sorted_unique_bindings(used_bindings),
                evidence_refs=evidence,
                confidence=proposal.confidence,
                produced_in_run_id=self._run_id,
                produced_in_stage=TURN_KE_STAGE,
            )
            equations_by_key[proposal.key] = equation
            for unit_key in proposal.information_unit_keys:
                equation_ids_by_unit[unit_key].append(equation.id)

        represented_units = {
            unit_key
            for coverage in validated_draft.coverage_by_message.values()
            for entry in coverage
            if entry.status is CoverageStatus.REPRESENTED
            for unit_key in entry.ke_ids
        }
        unrealized = sorted(
            unit_key for unit_key in represented_units if not equation_ids_by_unit[unit_key]
        )
        if unrealized:
            raise ExtractionInvariantError(
                f"represented information unit is not realized by a final KE: {unrealized[0]}"
            )

        equations = tuple(equations_by_key[item.key] for item in ordered_proposals)
        equation_ids = tuple(equation.id for equation in equations)
        if len(equation_ids) != len(set(equation_ids)):
            raise ExtractionInvariantError("duplicate final knowledge-equation IDs are not allowed")
        revisions = tuple(equation.revision for equation in equations)
        if len(revisions) != len(set(revisions)):
            raise ExtractionInvariantError(
                "duplicate final knowledge-equation revisions are not allowed"
            )

        coverage: list[CoverageEntry] = []
        known_equation_ids = set(equation_ids)
        for message in _messages_in_source_order(exchange):
            converted = tuple(
                CoverageEntry(
                    message_id=entry.message_id,
                    start_char=entry.start_char,
                    end_char=entry.end_char,
                    status=entry.status,
                    ke_ids=(
                        tuple(
                            sorted(
                                {
                                    equation_id
                                    for unit_key in entry.ke_ids
                                    for equation_id in equation_ids_by_unit[unit_key]
                                }
                            )
                        )
                        if entry.status is CoverageStatus.REPRESENTED
                        else ()
                    ),
                )
                for entry in validated_draft.coverage_by_message[message.id]
            )
            try:
                coverage.extend(
                    CoverageValidator.validate(
                        message,
                        converted,
                        known_references=known_equation_ids,
                    )
                )
            except CoverageInvariantError as error:
                raise ExtractionInvariantError(str(error)) from error

        try:
            return TurnExtractionResult(
                exchange_id=exchange.id,
                knowledge_equations=equations,
                coverage=tuple(coverage),
            )
        except ValidationError as error:
            raise ExtractionInvariantError("final turn extraction result is invalid") from error


def normalize_surface(surface_form: str) -> str:
    normalized = unicodedata.normalize("NFKC", surface_form)
    return " ".join(normalized.split()).casefold()


def _revalidate_model(
    model_type: type[ModelRecordT],
    value: object,
    label: str,
) -> ModelRecordT:
    if not isinstance(value, BaseModel):
        raise ExtractionInvariantError(f"{label} is not a validated model record")
    try:
        return model_type.model_validate(value.model_dump(mode="python"))
    except ValidationError as error:
        raise ExtractionInvariantError(f"{label} failed local schema validation") from error


def _read_prompt(relative_path: str) -> str:
    try:
        return (_PROMPT_ROOT / relative_path).read_text(encoding="utf-8")
    except OSError as error:
        raise ExtractionInvariantError(
            f"required extraction prompt is unavailable: {relative_path}"
        ) from error


def _json_text(value: JsonObject) -> str:
    return canonical_json(value).decode("utf-8")


def _messages_by_id(exchange: Exchange) -> dict[str, Message]:
    return {exchange.user.id: exchange.user, exchange.assistant.id: exchange.assistant}


def _messages_in_source_order(exchange: Exchange) -> tuple[Message, Message]:
    return tuple(sorted((exchange.user, exchange.assistant), key=lambda item: item.source_order))  # type: ignore[return-value]


def _sorted_unique_spans(
    spans: Sequence[MessageSpan],
    messages: Mapping[str, Message],
) -> tuple[MessageSpan, ...]:
    unique = {
        (span.message_id, span.start_char, span.end_char, span.text_hash): span for span in spans
    }
    return tuple(
        sorted(
            unique.values(),
            key=lambda span: (
                messages[span.message_id].source_order,
                span.start_char,
                span.end_char,
                span.text_hash,
            ),
        )
    )


def _speaker_for_evidence(
    evidence: Sequence[MessageSpan],
    messages: Mapping[str, Message],
) -> Speaker:
    roles = {messages[span.message_id].role for span in evidence}
    if roles == {MessageRole.USER}:
        return Speaker.USER
    if roles == {MessageRole.ASSISTANT}:
        return Speaker.ASSISTANT
    if roles == {MessageRole.USER, MessageRole.ASSISTANT}:
        return Speaker.DERIVED
    raise ExtractionInvariantError("turn knowledge equations require user or assistant evidence")


def _proposal_evidence(
    proposal: TurnKEProposal,
    evidence_by_unit: Mapping[str, tuple[MessageSpan, ...]],
    messages: Mapping[str, Message],
) -> tuple[MessageSpan, ...]:
    return _sorted_unique_spans(
        tuple(
            span
            for unit_key in proposal.information_unit_keys
            for span in evidence_by_unit[unit_key]
        ),
        messages,
    )


def _topological_proposals(
    proposals: Sequence[TurnKEProposal],
    unit_keys: set[str],
) -> tuple[TurnKEProposal, ...]:
    by_key = {proposal.key: proposal for proposal in proposals}
    dependencies: dict[str, set[str]] = {}
    dependents: dict[str, set[str]] = defaultdict(set)
    for proposal in proposals:
        unknown_units = sorted(set(proposal.information_unit_keys).difference(unit_keys))
        if unknown_units:
            raise ExtractionInvariantError(
                f"proposal {proposal.key} references unknown information unit {unknown_units[0]}"
            )
        referenced = _assertion_keys(proposal.lhs).union(_assertion_keys(proposal.rhs))
        dangling = sorted(referenced.difference(by_key))
        if dangling:
            raise ExtractionInvariantError(
                f"proposal {proposal.key} has dangling assertion key {dangling[0]}"
            )
        dependencies[proposal.key] = set(referenced)
        for dependency in referenced:
            dependents[dependency].add(proposal.key)

    ready = [key for key, values in dependencies.items() if not values]
    heapq.heapify(ready)
    ordered: list[TurnKEProposal] = []
    while ready:
        key = heapq.heappop(ready)
        ordered.append(by_key[key])
        for dependent in sorted(dependents[key]):
            dependencies[dependent].discard(key)
            if not dependencies[dependent]:
                heapq.heappush(ready, dependent)
    if len(ordered) != len(proposals):
        raise ExtractionInvariantError("proposal assertion references contain a cycle")
    return tuple(ordered)


def _assertion_keys(expression: ProposalExpression) -> set[str]:
    if isinstance(expression, ProposalAssertionRef):
        return {expression.assertion_key}
    if isinstance(expression, ProposalOperatorApplication):
        return {key for argument in expression.arguments for key in _assertion_keys(argument)}
    return set()


def _allowed_mentions(
    proposal: TurnKEProposal,
    units: Mapping[str, DraftInformationUnit],
) -> dict[str, set[OntologyRole]]:
    allowed: dict[str, set[OntologyRole]] = defaultdict(set)
    for unit_key in proposal.information_unit_keys:
        for mention in units[unit_key].surface_mentions:
            allowed[mention.surface_form].add(mention.expected_role)
    return dict(allowed)


def _build_expression(
    expression: ProposalExpression,
    candidates: Mapping[str, _Candidate],
    allowed_mentions: Mapping[str, set[OntologyRole]],
    equations_by_key: Mapping[str, KnowledgeEquation],
    used_bindings: list[OntologyBinding],
) -> Expression:
    if isinstance(expression, ProposalAssertionRef):
        equation = equations_by_key.get(expression.assertion_key)
        if equation is None:
            raise ExtractionInvariantError(
                f"assertion key {expression.assertion_key} was not built in topological order"
            )
        return AssertionRef(assertion_id=equation.id)
    if isinstance(expression, ProposalOperatorApplication):
        operator = _build_expression(
            expression.operator,
            candidates,
            allowed_mentions,
            equations_by_key,
            used_bindings,
        )
        if not isinstance(operator, OperatorRef):
            raise ExtractionInvariantError("application operator must have the operator role")
        return OperatorApplication(
            operator=operator,
            arguments=tuple(
                _build_expression(
                    argument,
                    candidates,
                    allowed_mentions,
                    equations_by_key,
                    used_bindings,
                )
                for argument in expression.arguments
            ),
        )

    role: OntologyRole
    if isinstance(expression, ProposalConceptRef):
        role = OntologyRole.CONCEPT
        expression_type = ConceptRef
    elif isinstance(expression, ProposalIndividualRef):
        role = OntologyRole.INDIVIDUAL
        expression_type = IndividualRef
    else:
        role = OntologyRole.OPERATOR
        expression_type = OperatorRef

    expected_roles = allowed_mentions.get(expression.surface_form)
    if expected_roles is None or role not in expected_roles:
        raise ExtractionInvariantError(
            f"expression role {role.value} does not match draft surface {expression.surface_form!r}"
        )
    normalized = normalize_surface(expression.surface_form)
    candidate = candidates.get(normalized)
    if candidate is None:
        raise ExtractionInvariantError(
            f"expression names an unoffered surface: {expression.surface_form}"
        )
    binding = candidate.binding
    if expression.candidate_id == UNRESOLVED_MARKER:
        term_id = content_id(f"unresolved-{role.value}", normalized)
    else:
        if (
            binding.status is OntologyBindingStatus.UNRESOLVED_ROLE
            and expression.candidate_id == binding.document_id
        ):
            raise ExtractionInvariantError(
                "an unresolved-role document cannot be selected as a typed term"
            )
        if (
            binding.status is not OntologyBindingStatus.RESOLVED
            or expression.candidate_id != binding.document_id
        ):
            raise ExtractionInvariantError(
                f"expression selected unoffered document ID {expression.candidate_id}"
            )
        if binding.role is not role:
            raise ExtractionInvariantError(
                f"offered document role {binding.role.value if binding.role else 'none'} "
                f"does not match expression role {role.value}"
            )
        term_id = expression.candidate_id

    used_bindings.append(_binding_for_surface(binding, expression.surface_form, normalized))
    return expression_type(term_id=term_id, label=expression.surface_form)


def _binding_for_surface(
    binding: OntologyBinding,
    surface_form: str,
    normalized_surface: str,
) -> OntologyBinding:
    data = binding.model_dump(mode="python")
    data["surface_form"] = surface_form
    data["normalized_surface"] = normalized_surface
    return OntologyBinding.model_validate(data)


def _sorted_unique_bindings(
    bindings: Sequence[OntologyBinding],
) -> tuple[OntologyBinding, ...]:
    unique: dict[bytes, OntologyBinding] = {}
    for binding in bindings:
        key = canonical_json(cast(JsonValue, binding.model_dump(mode="json")))
        unique[key] = binding
    return tuple(unique[key] for key in sorted(unique))
