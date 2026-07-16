from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from enum import Enum
from pathlib import Path
from typing import Annotated, Literal, Protocol, TypeVar, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from ke_memory_demo.core.json import JsonObject, JsonValue, canonical_json
from ke_memory_demo.domain import (
    CoverageEntry,
    CoverageStatus,
    Expression,
    KnowledgeEquation,
    KnowledgeLevel,
    Lifecycle,
    Message,
    MessageSpan,
    Modality,
    Polarity,
    Session,
    Speaker,
)
from ke_memory_demo.extraction.coverage import CoverageInvariantError, CoverageValidator
from ke_memory_demo.infra.telemetry import TraceContext

from .validation import (
    AggregationInvariantError,
    authenticate_knowledge_equation,
    evidence_union,
    ontology_binding_union,
    records_by_id,
    sorted_unique_spans,
    span_key,
    temporal_envelope,
    validate_expression_authority,
)


SESSION_AGGREGATION_STAGE = "session-aggregated"
EMPTY_SESSION_SUMMARY = "No memory-bearing information."
_PROMPT_ROOT = Path(__file__).resolve().parents[3] / "prompts"

NonEmptyString = Annotated[str, Field(min_length=1)]
Confidence = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
ModelRecordT = TypeVar("ModelRecordT", bound=BaseModel)


class StructuredCompletionClient(Protocol):
    async def complete(
        self,
        model_type: type[ModelRecordT],
        messages: Sequence[Mapping[str, object]],
        trace_context: TraceContext | Mapping[str, object],
    ) -> ModelRecordT: ...


class _AggregationRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SessionItemKind(str, Enum):
    UNRESOLVED_CONFLICT = "unresolved_conflict"
    CONSTRAINT = "constraint"
    OPEN_QUESTION = "open_question"


class SessionKEProposal(_AggregationRecord):
    key: NonEmptyString
    lhs: Expression
    rhs: Expression
    gloss: NonEmptyString
    modality: Modality
    polarity: Polarity
    lifecycle: Literal["active", "uncertain"]
    confidence: Confidence
    derived_from: tuple[NonEmptyString, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_references(self) -> SessionKEProposal:
        _reject_duplicates(self.derived_from, "session proposal lower refs")
        return self


class SessionItemProposal(_AggregationRecord):
    key: NonEmptyString
    kind: SessionItemKind
    text: NonEmptyString
    derived_from: tuple[NonEmptyString, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_references(self) -> SessionItemProposal:
        _reject_duplicates(self.derived_from, "session item lower refs")
        return self


class SessionAggregationOutput(_AggregationRecord):
    summary: NonEmptyString
    proposals: tuple[SessionKEProposal, ...] = ()
    unresolved_conflicts: tuple[SessionItemProposal, ...] = ()
    constraints: tuple[SessionItemProposal, ...] = ()
    open_questions: tuple[SessionItemProposal, ...] = ()

    @model_validator(mode="after")
    def _validate_output(self) -> SessionAggregationOutput:
        _reject_duplicates(tuple(item.key for item in self.proposals), "session proposal keys")
        categories = (
            (
                self.unresolved_conflicts,
                SessionItemKind.UNRESOLVED_CONFLICT,
                "unresolved conflict",
            ),
            (self.constraints, SessionItemKind.CONSTRAINT, "constraint"),
            (self.open_questions, SessionItemKind.OPEN_QUESTION, "open question"),
        )
        item_keys: list[str] = []
        for items, expected_kind, label in categories:
            for item in items:
                if item.kind is not expected_kind:
                    raise ValueError(f"{label} output contains an item of the wrong kind")
                item_keys.append(item.key)
        _reject_duplicates(tuple(item_keys), "session item keys")
        return self


class SessionMemoryItem(_AggregationRecord):
    key: NonEmptyString
    kind: SessionItemKind
    text: NonEmptyString
    derived_from: tuple[NonEmptyString, ...] = Field(min_length=1)
    evidence_refs: tuple[MessageSpan, ...] = ()

    @model_validator(mode="after")
    def _validate_item(self) -> SessionMemoryItem:
        _reject_duplicates(self.derived_from, "session item lower refs")
        _reject_duplicates(tuple(span_key(span) for span in self.evidence_refs), "item evidence")
        if self.evidence_refs != tuple(sorted(self.evidence_refs, key=span_key)):
            raise ValueError("session item evidence refs must be sorted")
        return self


class SessionMemory(_AggregationRecord):
    session_id: NonEmptyString
    summary: NonEmptyString
    knowledge_equations: tuple[KnowledgeEquation, ...] = ()
    unresolved_conflicts: tuple[SessionMemoryItem, ...] = ()
    constraints: tuple[SessionMemoryItem, ...] = ()
    open_questions: tuple[SessionMemoryItem, ...] = ()
    source_turn_ke_ids: tuple[NonEmptyString, ...] = ()
    evidence_closure: tuple[MessageSpan, ...] = ()

    @model_validator(mode="after")
    def _validate_memory_shape(self) -> SessionMemory:
        ids = tuple(item.id for item in self.knowledge_equations)
        revisions = tuple(item.revision for item in self.knowledge_equations)
        _reject_duplicates(ids, "session KE logical IDs")
        _reject_duplicates(revisions, "session KE revisions")
        if ids != tuple(sorted(ids)):
            raise ValueError("session KEs must be sorted by logical ID")
        if any(item.level is not KnowledgeLevel.SESSION for item in self.knowledge_equations):
            raise ValueError("SessionMemory may contain only Session-level KEs")

        if self.source_turn_ke_ids != tuple(sorted(self.source_turn_ke_ids)):
            raise ValueError("source Turn-KE IDs must be sorted")
        _reject_duplicates(self.source_turn_ke_ids, "source Turn-KE IDs")
        source_ids = set(self.source_turn_ke_ids)
        for item in (*self.knowledge_equations, *self._items()):
            unknown = sorted(set(item.derived_from).difference(source_ids))
            if unknown:
                raise ValueError(f"session record cites unknown source Turn KE {unknown[0]}")

        categories = (
            (self.unresolved_conflicts, SessionItemKind.UNRESOLVED_CONFLICT),
            (self.constraints, SessionItemKind.CONSTRAINT),
            (self.open_questions, SessionItemKind.OPEN_QUESTION),
        )
        for items, expected_kind in categories:
            if any(item.kind is not expected_kind for item in items):
                raise ValueError("SessionMemory contains an item in the wrong typed category")
            keys = tuple(item.key for item in items)
            _reject_duplicates(keys, f"{expected_kind.value} item keys")
            if keys != tuple(sorted(keys)):
                raise ValueError(f"{expected_kind.value} items must be sorted by key")

        expected_closure = sorted_unique_spans(
            span
            for item in (*self.knowledge_equations, *self._items())
            for span in item.evidence_refs
        )
        if self.evidence_closure != expected_closure:
            raise ValueError("session evidence closure is not the exact assertion/item union")
        return self

    def _items(self) -> tuple[SessionMemoryItem, ...]:
        return (*self.unresolved_conflicts, *self.constraints, *self.open_questions)


class SessionAggregator:
    def __init__(
        self,
        model: StructuredCompletionClient,
        turn_kes: Sequence[KnowledgeEquation],
        coverage: Sequence[CoverageEntry],
        *,
        run_id: str,
    ) -> None:
        if not run_id:
            raise ValueError("run_id must not be empty")
        self._model = model
        self._turn_kes = tuple(turn_kes)
        self._coverage = tuple(coverage)
        self._run_id = run_id

    async def aggregate(self, session: Session) -> SessionMemory:
        messages = _session_messages(session)
        selected = self._select_and_validate_turn_kes(session, messages)
        selected_by_id = records_by_id(selected, label="selected Turn KE")
        normalized_coverage = self._validate_coverage(messages, set(selected_by_id))

        if not selected:
            return SessionMemory(
                session_id=session.id,
                summary=EMPTY_SESSION_SUMMARY,
                knowledge_equations=(),
                unresolved_conflicts=(),
                constraints=(),
                open_questions=(),
                source_turn_ke_ids=(),
                evidence_closure=(),
            )

        response = await self._model.complete(
            SessionAggregationOutput,
            self._messages(session, selected, normalized_coverage, messages),
            TraceContext(
                operation="session-memory-aggregate",
                metadata={"run_id": self._run_id, "session_id": session.id},
            ),
        )
        output = _validated_output(response)
        memory = self._build_memory(session, selected_by_id, output)
        validate_session_memory(memory, selected_by_id)
        return memory

    def _select_and_validate_turn_kes(
        self,
        session: Session,
        messages: Mapping[str, Message],
    ) -> tuple[KnowledgeEquation, ...]:
        session_message_ids = set(messages)
        selected: list[KnowledgeEquation] = []
        for equation in self._turn_kes:
            evidence_message_ids = {span.message_id for span in equation.evidence_refs}
            if not evidence_message_ids.intersection(session_message_ids):
                continue
            outside = sorted(evidence_message_ids.difference(session_message_ids))
            if outside:
                raise AggregationInvariantError(
                    f"Turn KE {equation.id} mixes session {session.id} with message {outside[0]}"
                )
            if equation.level is not KnowledgeLevel.TURN:
                raise AggregationInvariantError(
                    f"selected record {equation.id} is not a Turn-level KE"
                )
            for span in equation.evidence_refs:
                try:
                    messages[span.message_id].validate_span(span)
                except ValueError as error:
                    raise AggregationInvariantError(str(error)) from error
            authenticate_knowledge_equation(equation, label=f"Turn KE {equation.id}")
            selected.append(equation)
        selected.sort(key=lambda item: item.id)
        revisions = tuple(item.revision for item in selected)
        if len(revisions) != len(set(revisions)):
            raise AggregationInvariantError("duplicate selected Turn KE revision")
        return tuple(selected)

    def _validate_coverage(
        self,
        messages: Mapping[str, Message],
        selected_ids: set[str],
    ) -> tuple[CoverageEntry, ...]:
        by_message: dict[str, list[CoverageEntry]] = defaultdict(list)
        for entry in self._coverage:
            if entry.message_id in messages:
                by_message[entry.message_id].append(entry)
        normalized: list[CoverageEntry] = []
        for message_id in sorted(messages):
            try:
                normalized.extend(
                    CoverageValidator.validate(
                        messages[message_id],
                        by_message[message_id],
                        known_references=selected_ids,
                    )
                )
            except CoverageInvariantError as error:
                raise AggregationInvariantError(f"invalid final coverage: {error}") from error
        normalized_tuple = tuple(
            sorted(
                normalized,
                key=lambda item: (item.message_id, item.start_char, item.end_char),
            )
        )
        represented_ids = {
            reference
            for entry in normalized_tuple
            if entry.status is CoverageStatus.REPRESENTED
            for reference in entry.ke_ids
        }
        unrepresented = sorted(selected_ids.difference(represented_ids))
        if unrepresented:
            raise AggregationInvariantError(
                f"selected Turn KE is not represented by final coverage: {unrepresented[0]}"
            )
        return normalized_tuple

    def _messages(
        self,
        session: Session,
        selected: Sequence[KnowledgeEquation],
        coverage: Sequence[CoverageEntry],
        messages: Mapping[str, Message],
    ) -> list[dict[str, object]]:
        snippets: list[JsonValue] = []
        for span in sorted_unique_spans(
            span for equation in selected for span in equation.evidence_refs
        ):
            message = messages[span.message_id]
            snippets.append(
                {
                    "message_id": span.message_id,
                    "start_char": span.start_char,
                    "end_char": span.end_char,
                    "text_hash": span.text_hash,
                    "text": message.content[span.start_char : span.end_char],
                }
            )
        payload: JsonObject = {
            "task": "aggregate_session_memory",
            "session_id": session.id,
            "turn_knowledge_equations": [
                cast(JsonValue, item.model_dump(mode="json")) for item in selected
            ],
            "coverage_summaries": [
                cast(JsonValue, item.model_dump(mode="json")) for item in coverage
            ],
            "evidence_snippets": snippets,
        }
        try:
            prompt = (_PROMPT_ROOT / "session_aggregation/system.md").read_text(encoding="utf-8")
        except OSError as error:
            raise AggregationInvariantError(
                "required session aggregation prompt is unavailable"
            ) from error
        return [
            {"role": "system", "content": prompt},
            {"role": "user", "content": canonical_json(payload).decode("utf-8")},
        ]

    def _build_memory(
        self,
        session: Session,
        selected: Mapping[str, KnowledgeEquation],
        output: SessionAggregationOutput,
    ) -> SessionMemory:
        equations = tuple(
            sorted(
                (self._build_equation(proposal, selected) for proposal in output.proposals),
                key=lambda item: item.id,
            )
        )
        ids = tuple(item.id for item in equations)
        revisions = tuple(item.revision for item in equations)
        if len(ids) != len(set(ids)):
            raise AggregationInvariantError("duplicate Session KE logical ID")
        if len(revisions) != len(set(revisions)):
            raise AggregationInvariantError("duplicate Session KE revision")

        conflicts = self._build_items(output.unresolved_conflicts, selected)
        constraints = self._build_items(output.constraints, selected)
        questions = self._build_items(output.open_questions, selected)
        all_items = (*conflicts, *constraints, *questions)
        closure = sorted_unique_spans(
            span for item in (*equations, *all_items) for span in item.evidence_refs
        )
        return SessionMemory(
            session_id=session.id,
            summary=output.summary,
            knowledge_equations=equations,
            unresolved_conflicts=conflicts,
            constraints=constraints,
            open_questions=questions,
            source_turn_ke_ids=tuple(sorted(selected)),
            evidence_closure=closure,
        )

    def _build_equation(
        self,
        proposal: SessionKEProposal,
        selected: Mapping[str, KnowledgeEquation],
    ) -> KnowledgeEquation:
        cited_ids = tuple(sorted(proposal.derived_from))
        cited = _resolve_lower(cited_ids, selected, label=f"session proposal {proposal.key}")
        used_terms = validate_expression_authority(
            proposal.lhs,
            proposal.rhs,
            cited,
            cited_ids,
            label=f"session proposal {proposal.key}",
        )
        return KnowledgeEquation.create(
            level=KnowledgeLevel.SESSION,
            lhs=proposal.lhs,
            rhs=proposal.rhs,
            gloss=proposal.gloss,
            modality=proposal.modality,
            polarity=proposal.polarity,
            lifecycle=proposal.lifecycle,
            speaker=Speaker.DERIVED,
            temporal=temporal_envelope(item.temporal for item in cited),
            ontology_bindings=ontology_binding_union(used_terms, cited),
            evidence_refs=evidence_union(cited),
            derived_from=cited_ids,
            confidence=proposal.confidence,
            produced_in_run_id=self._run_id,
            produced_in_stage=SESSION_AGGREGATION_STAGE,
        )

    @staticmethod
    def _build_items(
        proposals: Sequence[SessionItemProposal],
        selected: Mapping[str, KnowledgeEquation],
    ) -> tuple[SessionMemoryItem, ...]:
        items: list[SessionMemoryItem] = []
        for proposal in sorted(proposals, key=lambda item: item.key):
            cited_ids = tuple(sorted(proposal.derived_from))
            cited = _resolve_lower(cited_ids, selected, label=f"session item {proposal.key}")
            items.append(
                SessionMemoryItem(
                    key=proposal.key,
                    kind=proposal.kind,
                    text=proposal.text,
                    derived_from=cited_ids,
                    evidence_refs=evidence_union(cited),
                )
            )
        return tuple(items)


def validate_session_memory(
    memory: SessionMemory,
    turn_kes: Mapping[str, KnowledgeEquation] | Sequence[KnowledgeEquation],
) -> None:
    try:
        SessionMemory.model_validate(memory.model_dump(mode="python"))
    except ValidationError as error:
        raise AggregationInvariantError("record is not a validated SessionMemory") from error
    lower = records_by_id(turn_kes, label="Turn KE")
    for equation in lower.values():
        authenticate_knowledge_equation(
            equation,
            label=f"source Turn KE {equation.id}",
        )
        if equation.level is not KnowledgeLevel.TURN:
            raise AggregationInvariantError(f"source record {equation.id} is not a Turn-level KE")
    missing_sources = sorted(set(memory.source_turn_ke_ids).difference(lower))
    if missing_sources:
        raise AggregationInvariantError(
            f"SessionMemory source Turn KE is missing: {missing_sources[0]}"
        )
    if set(memory.source_turn_ke_ids) != set(lower):
        raise AggregationInvariantError(
            "SessionMemory source Turn-KE IDs are not the exact selected input set"
        )
    for equation in memory.knowledge_equations:
        authenticate_knowledge_equation(equation, label=f"Session assertion {equation.id}")
        if equation.level is not KnowledgeLevel.SESSION:
            raise AggregationInvariantError("SessionMemory assertion has the wrong level")
        if equation.speaker is not Speaker.DERIVED:
            raise AggregationInvariantError("SessionMemory assertion must have derived speaker")
        if equation.lifecycle not in (Lifecycle.ACTIVE, Lifecycle.UNCERTAIN):
            raise AggregationInvariantError("SessionMemory assertion has an invalid lifecycle")
        if equation.produced_in_stage != SESSION_AGGREGATION_STAGE:
            raise AggregationInvariantError("SessionMemory assertion has the wrong stage")
        if equation.derived_from != tuple(sorted(equation.derived_from)):
            raise AggregationInvariantError("SessionMemory assertion lower refs must be sorted")
        cited_ids = equation.derived_from
        cited = _resolve_lower(cited_ids, lower, label=f"Session assertion {equation.id}")
        used_terms = validate_expression_authority(
            equation.lhs,
            equation.rhs,
            cited,
            cited_ids,
            label=f"Session assertion {equation.id}",
        )
        if equation.evidence_refs != evidence_union(cited):
            raise AggregationInvariantError("Session assertion evidence closure is not exact")
        if equation.ontology_bindings != ontology_binding_union(used_terms, cited):
            raise AggregationInvariantError("Session assertion ontology bindings are not exact")
        if equation.temporal != temporal_envelope(item.temporal for item in cited):
            raise AggregationInvariantError("Session assertion temporal envelope is not exact")

    memory_items = (
        *memory.unresolved_conflicts,
        *memory.constraints,
        *memory.open_questions,
    )
    for item in memory_items:
        if item.derived_from != tuple(sorted(item.derived_from)):
            raise AggregationInvariantError("SessionMemory item lower refs must be sorted")
        cited = _resolve_lower(item.derived_from, lower, label=f"Session item {item.key}")
        if item.evidence_refs != evidence_union(cited):
            raise AggregationInvariantError("Session item evidence closure is not exact")
    expected_closure = sorted_unique_spans(
        span for item in (*memory.knowledge_equations, *memory_items) for span in item.evidence_refs
    )
    if memory.evidence_closure != expected_closure:
        raise AggregationInvariantError("SessionMemory evidence closure is not exact")


def _validated_output(value: object) -> SessionAggregationOutput:
    if not isinstance(value, BaseModel):
        raise AggregationInvariantError("session model did not return a validated record")
    try:
        return SessionAggregationOutput.model_validate(value.model_dump(mode="python"))
    except (TypeError, ValidationError, ValueError) as error:
        raise AggregationInvariantError("session model output is not a validated record") from error


def _resolve_lower(
    references: Sequence[str],
    records: Mapping[str, KnowledgeEquation],
    *,
    label: str,
) -> tuple[KnowledgeEquation, ...]:
    missing = sorted(set(references).difference(records))
    if missing:
        raise AggregationInvariantError(f"{label} cites unknown lower record {missing[0]}")
    return tuple(records[reference] for reference in references)


def _session_messages(session: Session) -> dict[str, Message]:
    messages: dict[str, Message] = {}
    for exchange in session.exchanges:
        for message in (exchange.user, exchange.assistant):
            if message.id in messages:
                raise AggregationInvariantError(f"duplicate Session message ID {message.id}")
            messages[message.id] = message
    return messages


def _reject_duplicates(values: tuple[object, ...], label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"duplicate {label} are not allowed")
