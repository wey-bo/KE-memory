from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ke_memory_demo.domain import (
    CoverageEntry,
    CoverageStatus,
    KnowledgeEquation,
    Modality,
    OntologyBindingStatus,
    OntologyRole,
    Polarity,
    Speaker,
    TemporalMetadata,
)


UNRESOLVED_MARKER = "__unresolved__"

NonEmptyString = Annotated[str, Field(min_length=1)]
NonNegativeInt = Annotated[int, Field(ge=0)]
Confidence = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


class _ExtractionRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class DraftSpan(_ExtractionRecord):
    message_id: NonEmptyString
    start_char: NonNegativeInt
    end_char: NonNegativeInt

    @model_validator(mode="after")
    def _validate_range(self) -> DraftSpan:
        if self.end_char <= self.start_char:
            raise ValueError("draft span must be a non-empty half-open range")
        return self


class DraftSurfaceMention(_ExtractionRecord):
    surface_form: NonEmptyString
    expected_role: OntologyRole


class DraftInformationUnit(_ExtractionRecord):
    key: NonEmptyString
    gloss: NonEmptyString
    modality: Modality
    polarity: Polarity
    speaker: Speaker
    temporal: TemporalMetadata = Field(default_factory=TemporalMetadata)
    surface_mentions: tuple[DraftSurfaceMention, ...] = ()
    source_spans: tuple[DraftSpan, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_unit(self) -> DraftInformationUnit:
        if self.speaker is Speaker.TOOL:
            raise ValueError("tool speaker information units are not supported")
        span_keys = tuple(
            (span.message_id, span.start_char, span.end_char) for span in self.source_spans
        )
        _reject_duplicates(span_keys, "draft source spans")
        mention_keys = tuple(
            (mention.surface_form, mention.expected_role) for mention in self.surface_mentions
        )
        _reject_duplicates(mention_keys, "draft surface mentions")
        return self


class DraftCoverageRange(_ExtractionRecord):
    message_id: NonEmptyString
    start_char: NonNegativeInt
    end_char: NonNegativeInt
    status: CoverageStatus
    unit_keys: tuple[NonEmptyString, ...] = ()

    @model_validator(mode="after")
    def _validate_range(self) -> DraftCoverageRange:
        if self.end_char <= self.start_char:
            raise ValueError("draft coverage must be a non-empty half-open range")
        _reject_duplicates(self.unit_keys, "draft coverage unit refs")
        if self.status is CoverageStatus.REPRESENTED and not self.unit_keys:
            raise ValueError("represented draft coverage requires unit refs")
        if self.status is not CoverageStatus.REPRESENTED and self.unit_keys:
            raise ValueError(f"{self.status.value} draft coverage forbids unit refs")
        return self


class TurnKEDraft(_ExtractionRecord):
    information_units: tuple[DraftInformationUnit, ...] = ()
    coverage: tuple[DraftCoverageRange, ...] = ()

    @model_validator(mode="after")
    def _validate_unique_keys(self) -> TurnKEDraft:
        _reject_duplicates(
            tuple(unit.key for unit in self.information_units),
            "information-unit keys",
        )
        return self


class ProposalConceptRef(_ExtractionRecord):
    kind: Literal["concept"] = "concept"
    surface_form: NonEmptyString
    candidate_id: NonEmptyString


class ProposalIndividualRef(_ExtractionRecord):
    kind: Literal["individual"] = "individual"
    surface_form: NonEmptyString
    candidate_id: NonEmptyString


class ProposalOperatorRef(_ExtractionRecord):
    kind: Literal["operator"] = "operator"
    surface_form: NonEmptyString
    candidate_id: NonEmptyString


class ProposalAssertionRef(_ExtractionRecord):
    kind: Literal["assertion"] = "assertion"
    assertion_key: NonEmptyString


class ProposalOperatorApplication(_ExtractionRecord):
    kind: Literal["application"] = "application"
    operator: ProposalOperatorRef
    arguments: tuple[ProposalExpression, ...]


type ProposalAtomicExpression = Annotated[
    ProposalConceptRef | ProposalIndividualRef | ProposalOperatorRef | ProposalAssertionRef,
    Field(discriminator="kind"),
]

type ProposalExpression = Annotated[
    ProposalConceptRef
    | ProposalIndividualRef
    | ProposalOperatorRef
    | ProposalAssertionRef
    | ProposalOperatorApplication,
    Field(discriminator="kind"),
]


ProposalOperatorApplication.model_rebuild()


class TurnKEProposal(_ExtractionRecord):
    key: NonEmptyString
    information_unit_keys: tuple[NonEmptyString, ...] = Field(min_length=1)
    lhs: ProposalExpression
    rhs: ProposalExpression
    gloss: NonEmptyString
    modality: Modality
    polarity: Polarity
    lifecycle: Literal["active", "uncertain"]
    temporal: TemporalMetadata = Field(default_factory=TemporalMetadata)
    confidence: Confidence

    @model_validator(mode="after")
    def _validate_unit_keys(self) -> TurnKEProposal:
        _reject_duplicates(self.information_unit_keys, "proposal information-unit refs")
        return self


class TurnKEOutput(_ExtractionRecord):
    proposals: tuple[TurnKEProposal, ...] = ()

    @model_validator(mode="after")
    def _validate_unique_keys(self) -> TurnKEOutput:
        _reject_duplicates(tuple(item.key for item in self.proposals), "proposal keys")
        return self


class SurfaceCandidateBundle(_ExtractionRecord):
    surface_form: NonEmptyString
    normalized_surface: NonEmptyString
    expected_roles: tuple[OntologyRole, ...] = Field(min_length=1)
    binding_status: OntologyBindingStatus
    offered_document_id: NonEmptyString | None = None
    offered_role: OntologyRole | None = None
    unresolved_marker: Literal["__unresolved__"] = UNRESOLVED_MARKER

    @model_validator(mode="after")
    def _validate_offer(self) -> SurfaceCandidateBundle:
        _reject_duplicates(self.expected_roles, "candidate expected roles")
        if self.binding_status is OntologyBindingStatus.RESOLVED:
            if self.offered_document_id is None or self.offered_role is None:
                raise ValueError("resolved candidate requires an offered document ID and role")
        elif self.offered_document_id is not None or self.offered_role is not None:
            raise ValueError("unresolved candidates may expose only the unresolved marker")
        return self


class TurnExtractionResult(_ExtractionRecord):
    exchange_id: NonEmptyString
    knowledge_equations: tuple[KnowledgeEquation, ...] = ()
    coverage: tuple[CoverageEntry, ...] = ()

    @model_validator(mode="after")
    def _validate_unique_records(self) -> TurnExtractionResult:
        _reject_duplicates(
            tuple(item.id for item in self.knowledge_equations),
            "knowledge-equation IDs",
        )
        _reject_duplicates(
            tuple(item.revision for item in self.knowledge_equations),
            "knowledge-equation revisions",
        )
        return self


class LifecycleMatchCandidate(_ExtractionRecord):
    old_ke_id: NonEmptyString
    new_ke_id: NonEmptyString
    old_revision: NonEmptyString
    new_revision: NonEmptyString
    subject_identity: NonEmptyString
    operator_identity: NonEmptyString
    modality: Modality
    old_polarity: Polarity
    new_polarity: Polarity
    old_lifecycle: NonEmptyString
    new_lifecycle: NonEmptyString
    old_temporal: TemporalMetadata
    new_temporal: TemporalMetadata
    old_gloss: NonEmptyString
    new_gloss: NonEmptyString
    old_produced_in_run_id: NonEmptyString
    new_produced_in_run_id: NonEmptyString


class LifecycleMatchDecision(_ExtractionRecord):
    old_ke_id: NonEmptyString
    new_ke_id: NonEmptyString
    decision: Literal["contradicts", "updates", "no_match"]
    confidence: Confidence
    reason: NonEmptyString
    explicit_retraction: bool = False

    @model_validator(mode="after")
    def _validate_retraction(self) -> LifecycleMatchDecision:
        if self.explicit_retraction and self.decision != "updates":
            raise ValueError("explicit_retraction is allowed only with updates")
        return self


class LifecycleMatchOutput(_ExtractionRecord):
    matches: tuple[LifecycleMatchDecision, ...] = ()

    @model_validator(mode="after")
    def _validate_unique_pairs(self) -> LifecycleMatchOutput:
        _reject_duplicates(
            tuple((item.old_ke_id, item.new_ke_id) for item in self.matches),
            "lifecycle matcher pairs",
        )
        return self


class LifecycleResult(_ExtractionRecord):
    decisions: tuple[LifecycleMatchDecision, ...] = ()
    appended_revisions: tuple[KnowledgeEquation, ...] = ()
    current_records: tuple[KnowledgeEquation, ...] = ()

    @model_validator(mode="after")
    def _validate_current_records(self) -> LifecycleResult:
        _reject_duplicates(
            tuple(item.id for item in self.current_records),
            "current knowledge-equation IDs",
        )
        return self


def _reject_duplicates(values: tuple[object, ...], label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"duplicate {label} are not allowed")
