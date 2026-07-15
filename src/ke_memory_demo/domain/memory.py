from __future__ import annotations

from collections.abc import Sequence
from enum import Enum
import hashlib
from typing import Annotated, Final, Literal, cast

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    model_validator,
)

from ke_memory_demo.core.ids import content_id
from ke_memory_demo.core.json import JsonObject, JsonValue, canonical_json

from .conversation import MessageSpan
from .expressions import Expression


SCHEMA_VERSION: Final = "ke-memory/v1"
_SKIP_IDENTITY_VALIDATION: Final = "skip_identity_validation"

NonEmptyString = Annotated[str, Field(min_length=1)]
NonNegativeInt = Annotated[int, Field(ge=0)]
PositiveInt = Annotated[int, Field(ge=1)]
Confidence = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]
Sha256Hex = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class KnowledgeLevel(str, Enum):
    TURN = "turn"
    SESSION = "session"
    AGGREGATE = "aggregate"


class Modality(str, Enum):
    FACT = "fact"
    BELIEF = "belief"
    PREFERENCE = "preference"
    GOAL = "goal"
    PLAN = "plan"
    INSTRUCTION = "instruction"
    HYPOTHESIS = "hypothesis"
    QUESTION = "question"


class Polarity(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    UNKNOWN = "unknown"


class Lifecycle(str, Enum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    CONTRADICTED = "contradicted"
    RETRACTED = "retracted"
    UNCERTAIN = "uncertain"


class Speaker(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
    DERIVED = "derived"


class CoverageStatus(str, Enum):
    REPRESENTED = "represented"
    CONTEXT_ONLY = "context_only"
    NON_MEMORY = "non_memory"
    EXTRACTION_FAILED = "extraction_failed"


class AggregateNodeKind(str, Enum):
    TASK = "Task"
    PROJECT = "Project"
    TOPIC = "Topic"
    GOAL = "Goal"
    EVENT_CHAIN = "EventChain"
    ENTITY_TIMELINE = "EntityTimeline"
    DECISION = "Decision"
    STATE = "State"
    CONSTRAINT = "Constraint"
    PREFERENCE = "Preference"
    PROCEDURE = "Procedure"
    PATTERN = "Pattern"
    ISSUE = "Issue"
    OTHER = "Other"


class OntologyRole(str, Enum):
    CONCEPT = "concept"
    INDIVIDUAL = "individual"
    OPERATOR = "operator"


class OntologyBindingStatus(str, Enum):
    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"
    UNRESOLVED_ROLE = "unresolved_role"


class _MemoryRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class TemporalMetadata(_MemoryRecord):
    mentioned_at: AwareDatetime | None = None
    event_time: AwareDatetime | None = None
    valid_from: AwareDatetime | None = None
    valid_to: AwareDatetime | None = None

    @model_validator(mode="after")
    def _validate_validity_order(self) -> TemporalMetadata:
        if (
            self.valid_from is not None
            and self.valid_to is not None
            and self.valid_to < self.valid_from
        ):
            raise ValueError("valid_to must not be earlier than valid_from")
        return self


class OntologyRelationRef(_MemoryRecord):
    relation_type: NonEmptyString
    target_id: NonEmptyString


class OntologyBinding(_MemoryRecord):
    surface_form: NonEmptyString
    normalized_surface: NonEmptyString
    status: OntologyBindingStatus
    document_id: NonEmptyString | None = None
    canonical_term: NonEmptyString | None = None
    role: OntologyRole | None = None
    source_type: NonEmptyString | None = None
    matched_alias: NonEmptyString | None = None
    aliases: tuple[NonEmptyString, ...] = ()
    relations: tuple[OntologyRelationRef, ...] = ()

    @model_validator(mode="after")
    def _validate_resolution_state(self) -> OntologyBinding:
        identity = (self.document_id, self.canonical_term, self.role)
        if self.status is OntologyBindingStatus.RESOLVED and any(
            value is None for value in identity
        ):
            raise ValueError("resolved binding requires document_id, canonical_term, and role")
        if self.status is OntologyBindingStatus.UNRESOLVED and any(
            value is not None for value in identity
        ):
            raise ValueError("unresolved binding forbids document_id, canonical_term, and role")
        if self.status is OntologyBindingStatus.UNRESOLVED_ROLE and (
            self.document_id is None or self.canonical_term is None or self.role is not None
        ):
            raise ValueError(
                "unresolved_role binding requires document_id and canonical_term and forbids role"
            )
        _reject_duplicate_keys(
            tuple((relation.relation_type, relation.target_id) for relation in self.relations),
            "ontology relation refs",
        )
        return self


class KnowledgeEquation(_MemoryRecord):
    id: NonEmptyString
    revision: Sha256Hex
    schema_version: Literal["ke-memory/v1"] = SCHEMA_VERSION
    level: KnowledgeLevel
    lhs: Expression
    rhs: Expression
    gloss: NonEmptyString
    modality: Modality
    polarity: Polarity
    lifecycle: Lifecycle
    speaker: Speaker
    temporal: TemporalMetadata = Field(default_factory=TemporalMetadata)
    ontology_bindings: tuple[OntologyBinding, ...] = ()
    evidence_refs: tuple[MessageSpan, ...] = ()
    derived_from: tuple[NonEmptyString, ...] = ()
    contradicts: tuple[NonEmptyString, ...] = ()
    supersedes: tuple[NonEmptyString, ...] = ()
    confidence: Confidence
    produced_in_run_id: NonEmptyString
    produced_in_stage: NonEmptyString

    @model_validator(mode="after")
    def _validate_references(self) -> KnowledgeEquation:
        _reject_duplicate_keys(
            tuple(
                (span.message_id, span.start_char, span.end_char, span.text_hash)
                for span in self.evidence_refs
            ),
            "evidence refs",
        )
        _reject_duplicate_strings(self.derived_from, "derived_from refs")
        _reject_duplicate_strings(self.contradicts, "contradicts refs")
        _reject_duplicate_strings(self.supersedes, "supersedes refs")
        return self

    @model_validator(mode="after")
    def _validate_identity(self, info: ValidationInfo) -> KnowledgeEquation:
        context = cast(dict[str, object] | None, info.context)
        if context is not None and context.get(_SKIP_IDENTITY_VALIDATION) is True:
            return self

        expected_id = content_id("ke", self._logical_payload())
        if self.id != expected_id:
            raise ValueError(f"logical ID does not match canonical payload: expected {expected_id}")
        expected_revision = self._revision_hash()
        if self.revision != expected_revision:
            raise ValueError("revision does not match the complete canonical record")
        return self

    @classmethod
    def create(
        cls,
        *,
        level: KnowledgeLevel | str,
        lhs: Expression,
        rhs: Expression,
        gloss: str,
        modality: Modality | str,
        polarity: Polarity | str,
        lifecycle: Lifecycle | str,
        speaker: Speaker | str,
        produced_in_run_id: str,
        produced_in_stage: str,
        temporal: TemporalMetadata | None = None,
        ontology_bindings: Sequence[OntologyBinding] = (),
        evidence_refs: Sequence[MessageSpan] = (),
        derived_from: Sequence[str] = (),
        contradicts: Sequence[str] = (),
        supersedes: Sequence[str] = (),
        confidence: float = 1.0,
    ) -> KnowledgeEquation:
        draft = cls.model_validate(
            {
                "id": f"ke:{'0' * 64}",
                "revision": "0" * 64,
                "schema_version": SCHEMA_VERSION,
                "level": level,
                "lhs": lhs,
                "rhs": rhs,
                "gloss": gloss,
                "modality": modality,
                "polarity": polarity,
                "lifecycle": lifecycle,
                "speaker": speaker,
                "temporal": temporal or TemporalMetadata(),
                "ontology_bindings": tuple(ontology_bindings),
                "evidence_refs": tuple(evidence_refs),
                "derived_from": tuple(derived_from),
                "contradicts": tuple(contradicts),
                "supersedes": tuple(supersedes),
                "confidence": confidence,
                "produced_in_run_id": produced_in_run_id,
                "produced_in_stage": produced_in_stage,
            },
            context={_SKIP_IDENTITY_VALIDATION: True},
        )
        with_id = draft.model_copy(update={"id": content_id("ke", draft._logical_payload())})
        return with_id.model_copy(update={"revision": with_id._revision_hash()})

    def transition(self, lifecycle: Lifecycle | str) -> KnowledgeEquation:
        transitioned = self.model_copy(update={"lifecycle": Lifecycle(lifecycle)})
        return transitioned.model_copy(update={"revision": transitioned._revision_hash()})

    def _logical_payload(self) -> JsonValue:
        return cast(
            JsonValue,
            self.model_dump(
                mode="json",
                include={
                    "schema_version",
                    "level",
                    "lhs",
                    "rhs",
                    "evidence_refs",
                    "derived_from",
                },
            ),
        )

    def _revision_hash(self) -> str:
        payload = cast(JsonValue, self.model_dump(mode="json", exclude={"revision"}))
        return hashlib.sha256(canonical_json(payload)).hexdigest()


class CoverageEntry(_MemoryRecord):
    message_id: NonEmptyString
    start_char: NonNegativeInt
    end_char: NonNegativeInt
    status: CoverageStatus
    ke_ids: tuple[NonEmptyString, ...] = ()

    @model_validator(mode="after")
    def _validate_coverage(self) -> CoverageEntry:
        if self.end_char <= self.start_char:
            raise ValueError("coverage entry must be a non-empty half-open range")
        _reject_duplicate_strings(self.ke_ids, "coverage KE refs")
        return self


class AggregateNode(_MemoryRecord):
    id: NonEmptyString
    node_kind: AggregateNodeKind
    title: NonEmptyString
    summary: NonEmptyString
    assertions: tuple[KnowledgeEquation, ...] = ()
    member_refs: tuple[NonEmptyString, ...] = ()
    derived_from: tuple[NonEmptyString, ...] = ()
    evidence_closure: tuple[MessageSpan, ...] = ()
    temporal_extent: TemporalMetadata = Field(default_factory=TemporalMetadata)
    confidence: Confidence
    revision: Sha256Hex
    depth: NonNegativeInt

    @model_validator(mode="after")
    def _validate_references(self) -> AggregateNode:
        _reject_duplicate_strings(tuple(item.id for item in self.assertions), "assertions")
        _reject_duplicate_strings(self.member_refs, "member_refs")
        _reject_duplicate_strings(self.derived_from, "derived_from refs")
        _reject_duplicate_keys(
            tuple(
                (span.message_id, span.start_char, span.end_char, span.text_hash)
                for span in self.evidence_closure
            ),
            "evidence closure refs",
        )
        return self


class Evidence(_MemoryRecord):
    evidence_id: NonEmptyString
    text: str
    source_exchange_ids: tuple[NonEmptyString, ...] = ()
    source_message_ids: tuple[NonEmptyString, ...] = ()
    system_record_ids: tuple[NonEmptyString, ...] = ()
    score: FiniteFloat
    rank: PositiveInt
    channel: NonEmptyString
    metadata: JsonObject = Field(default_factory=dict)
    token_count: NonNegativeInt

    @model_validator(mode="after")
    def _validate_id_tuples(self) -> Evidence:
        _reject_duplicate_strings(self.source_exchange_ids, "source exchange IDs")
        _reject_duplicate_strings(self.source_message_ids, "source message IDs")
        _reject_duplicate_strings(self.system_record_ids, "system record IDs")
        return self


def _reject_duplicate_strings(values: tuple[str, ...], label: str) -> None:
    _reject_duplicate_keys(values, label)


def _reject_duplicate_keys(values: tuple[object, ...], label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"duplicate {label} are not allowed")
