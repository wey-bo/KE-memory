"""Pydantic contracts exchanged between knowledge extraction pipeline passes."""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator


SourceStatus = Literal["user_reported", "agent_generated", "tool_observed"]
Derivation = Literal["explicit", "context_completed", "inferred"]
Modality = Literal[
    "asserted",
    "questioned",
    "requested",
    "preferred",
    "planned",
    "hypothetical",
    "possible",
    "advised",
    "committed",
    "claimed_completed",
    "observed",
]
Polarity = Literal["positive", "negative"]
CompletionKind = Literal[
    "coreference",
    "ellipsis",
    "role_resolution",
    "temporal_resolution",
    "pragmatic_inference",
    "unresolved",
]
OperationKind = Literal["confirm", "correct", "supersede", "conflict", "add"]
KeywordType = Literal[
    "entity",
    "concept",
    "action",
    "event",
    "property",
    "relation",
    "time",
    "quantity",
    "condition",
    "modality",
    "polarity",
]
KeywordKind = Literal["lexical", "literal", "identifier", "qualifier"]
PartOfSpeech = Literal["noun", "verb", "adjective", "adverb", "proper_noun", "other", "none"]
SemanticRole = Literal[
    "subject",
    "predicate",
    "object",
    "topic",
    "participant",
    "recipient",
    "instrument",
    "result",
    "attribute",
    "value",
    "time",
    "location",
    "condition",
    "modality",
    "polarity",
    "identifier",
    "other",
]
KeywordSourceField = Literal[
    "statement",
    "subject",
    "predicate",
    "object",
    "qualifiers.temporal",
    "qualifiers.conditions",
    "qualifiers.scope",
    "qualifiers.modality",
    "qualifiers.polarity",
]
LookupTarget = Literal["wordnet", "schema_org", "exact"]
KeywordDatatype = Literal[
    "date",
    "datetime",
    "time",
    "duration",
    "temporal_relation",
    "number",
    "currency",
    "percentage",
    "version",
    "code",
    "text",
    "identifier",
    "modality",
    "polarity",
    "condition",
    "other",
]
MappingKind = Literal["exact", "narrow", "broad", "related"]
WordNetPos = Literal["n", "v", "a", "s", "r"]
AtomicKeywordType = Literal[
    "entity",
    "concept",
    "action",
    "event",
    "property",
    "relation",
    "time",
    "quantity",
]

def _reject_blank_string(value: object) -> object:
    if isinstance(value, str) and not value.strip():
        raise ValueError("string must not be blank")
    return value


NonBlankStr = Annotated[str, BeforeValidator(_reject_blank_string), Field(min_length=1)]
NonEmptyStr = NonBlankStr
Probability = Annotated[float, Field(ge=0, le=1)]


def _require_unique(values: list[object], attribute: str, label: str) -> None:
    identifiers = [getattr(value, attribute) for value in values]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError(f"{label} must be unique")


class PipelineModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidenceDraft(PipelineModel):
    """A quoted source occurrence before character spans have been resolved."""

    turn_index: Annotated[int, Field(ge=0)]
    message: Literal["user", "agent"]
    occurrence_index: Annotated[int, Field(ge=0)]
    quote: NonEmptyStr


class OperationEvidenceDraft(EvidenceDraft):
    """Operation evidence with an explicit epistemic provenance role."""

    evidence_role: SourceStatus


class Evidence(EvidenceDraft):
    """A persisted evidence occurrence with its stable ID and source span."""

    evidence_id: NonEmptyStr
    candidate_id: NonEmptyStr
    evidence_role: SourceStatus
    start: Annotated[int, Field(ge=0)]
    end: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def end_must_not_precede_start(self) -> Evidence:
        if self.end < self.start:
            raise ValueError("end must be greater than or equal to start")
        return self


class Qualifiers(PipelineModel):
    modality: Modality
    polarity: Polarity
    temporal: list[NonEmptyStr] = Field(default_factory=list)
    conditions: list[NonEmptyStr] = Field(default_factory=list)
    scope: list[NonEmptyStr] = Field(default_factory=list)


class ContextCompletion(PipelineModel):
    completion_id: NonEmptyStr
    candidate_id: NonEmptyStr
    turn_index: Annotated[int, Field(ge=0)]
    kind: CompletionKind
    original_span: NonEmptyStr
    interpretation: NonEmptyStr
    evidence: list[EvidenceDraft] = Field(min_length=1)
    confidence: Probability
    ambiguity: bool


class KnowledgeDraft(PipelineModel):
    knowledge_id: NonEmptyStr
    candidate_id: NonEmptyStr
    statement: NonEmptyStr
    subject: NonEmptyStr
    predicate: NonEmptyStr
    object: NonBlankStr | None = None
    qualifiers: Qualifiers
    source_status: SourceStatus
    derivation: Derivation
    evidence: list[EvidenceDraft] = Field(min_length=1)
    inference_basis: NonBlankStr | None = None
    confidence: Probability

    @model_validator(mode="after")
    def validate_inference_basis(self) -> KnowledgeDraft:
        has_basis = self.inference_basis is not None and bool(self.inference_basis.strip())
        if self.derivation in {"context_completed", "inferred"} and not has_basis:
            raise ValueError("inference_basis is required for context_completed and inferred knowledge")
        if self.derivation == "explicit" and self.inference_basis is not None:
            raise ValueError("inference_basis must be omitted for explicit knowledge")
        return self


class Knowledge(KnowledgeDraft):
    evidence: list[Evidence] = Field(min_length=1)


class TurnPassOutput(PipelineModel):
    candidate_id: NonEmptyStr
    turn_index: Annotated[int, Field(ge=0)]
    context_completions: list[ContextCompletion] = Field(default_factory=list)
    knowledge: list[KnowledgeDraft] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_unique_ids(self) -> TurnPassOutput:
        _require_unique(self.context_completions, "completion_id", "context completion IDs")
        _require_unique(self.knowledge, "knowledge_id", "knowledge IDs")
        return self


class ReconciliationOperation(PipelineModel):
    operation_id: NonEmptyStr
    candidate_id: NonEmptyStr
    operation: OperationKind
    targets: list[NonEmptyStr] = Field(default_factory=list)
    replacement: NonBlankStr | None = None
    reason: NonEmptyStr
    evidence: list[OperationEvidenceDraft] = Field(min_length=1)
    confidence: Probability

    @model_validator(mode="after")
    def validate_operation_shape(self) -> ReconciliationOperation:
        if len(self.targets) != len(set(self.targets)):
            raise ValueError("targets must not contain duplicates")
        if self.operation == "confirm":
            valid = bool(self.targets) and self.replacement is None
        elif self.operation == "correct":
            valid = bool(self.targets) and self.replacement is not None
        elif self.operation == "supersede":
            valid = bool(self.targets)
        elif self.operation == "conflict":
            valid = len(self.targets) >= 2 and self.replacement is None
        else:  # add
            valid = not self.targets and self.replacement is not None
        if not valid:
            raise ValueError(f"invalid targets or replacement for {self.operation} operation")
        return self


class DialoguePassOutput(PipelineModel):
    candidate_id: NonEmptyStr
    new_knowledge: list[KnowledgeDraft] = Field(default_factory=list)
    operations: list[ReconciliationOperation] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_unique_ids(self) -> DialoguePassOutput:
        _require_unique(self.new_knowledge, "knowledge_id", "new knowledge IDs")
        _require_unique(self.operations, "operation_id", "operation IDs")
        return self


class KeywordDraft(PipelineModel):
    keyword_id: NonEmptyStr
    knowledge_id: NonEmptyStr
    surface: NonEmptyStr
    normalized_zh: NonEmptyStr
    query_lemma: NonEmptyStr
    keyword_kind: KeywordKind
    keyword_type: KeywordType
    semantic_role: SemanticRole
    source_field: KeywordSourceField
    part_of_speech: PartOfSpeech
    sense_key: NonBlankStr | None = None
    sense_hint: NonEmptyStr
    lookup_targets: list[LookupTarget] = Field(min_length=1)
    normalized_value: NonBlankStr | None = None
    datatype: KeywordDatatype | None = None
    unit: NonBlankStr | None = None
    translation_confidence: Probability

    @model_validator(mode="after")
    def validate_keyword_shape(self) -> KeywordDraft:
        if len(self.lookup_targets) != len(set(self.lookup_targets)):
            raise ValueError("lookup_targets must be unique")
        if self.keyword_kind == "lexical":
            if self.part_of_speech == "none":
                raise ValueError("lexical keyword part_of_speech must not be none")
            if self.sense_key is None:
                raise ValueError("lexical keyword sense_key is required")
            if not self.sense_key.replace("_", "").isalnum() or self.sense_key.lower() != self.sense_key:
                raise ValueError("lexical keyword sense_key must be lowercase snake_case")
            if any(value is not None for value in (self.normalized_value, self.datatype, self.unit)):
                raise ValueError("lexical keywords must not carry literal value fields")
            if not {"wordnet", "schema_org"}.intersection(self.lookup_targets):
                raise ValueError("lexical keywords must target wordnet or schema_org")
            token_limit = 6 if self.part_of_speech in {"noun", "proper_noun"} else 4
            if len(self.query_lemma.split()) > token_limit:
                raise ValueError("lexical query_lemma must be atomic")
        else:
            if self.part_of_speech != "none":
                raise ValueError("non-lexical keyword part_of_speech must be none")
            if self.sense_key is not None:
                raise ValueError("non-lexical keywords must not carry sense_key")
            if self.normalized_value is None or self.datatype is None:
                raise ValueError("non-lexical keywords require normalized_value and datatype")
            if set(self.lookup_targets) != {"exact"}:
                raise ValueError("non-lexical keywords must use exact lookup only")
        if self.keyword_kind == "identifier":
            if self.datatype != "identifier" or self.semantic_role != "identifier":
                raise ValueError("identifier keyword datatype and semantic_role must be identifier")
        if self.keyword_kind == "qualifier":
            expected = {
                "time": "time",
                "condition": "condition",
                "modality": "modality",
                "polarity": "polarity",
            }
            role = expected.get(self.keyword_type)
            if role is None or self.semantic_role != role:
                raise ValueError("qualifier keyword type and semantic_role are inconsistent")
            if self.datatype not in {"date", "datetime", "time", "duration", "temporal_relation", "condition", "modality", "polarity", "text", "other"}:
                raise ValueError("qualifier keyword datatype is inconsistent")
            if self.keyword_type == "time" and self.datatype != "temporal_relation":
                raise ValueError("time qualifier datatype must be temporal_relation")
        if self.keyword_kind == "literal" and self.keyword_type == "time":
            if self.datatype not in {"date", "datetime", "time", "duration"}:
                raise ValueError("time literal datatype must be date, datetime, time, or duration")
        return self


class KnowledgeKeywordOutput(PipelineModel):
    knowledge_id: NonEmptyStr
    keywords: list[KeywordDraft] = Field(default_factory=list)
    no_keyword_reason: NonBlankStr | None = None

    @model_validator(mode="after")
    def require_keywords_or_reason(self) -> KnowledgeKeywordOutput:
        has_keywords = bool(self.keywords)
        has_reason = self.no_keyword_reason is not None and bool(self.no_keyword_reason.strip())
        if has_keywords == has_reason:
            raise ValueError("keywords must contain items xor no_keyword_reason must be non-empty")
        return self


class KeywordPassOutput(PipelineModel):
    candidate_id: NonEmptyStr
    items: list[KnowledgeKeywordOutput] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_unique_ids(self) -> KeywordPassOutput:
        _require_unique(self.items, "knowledge_id", "knowledge IDs")
        keyword_ids = [keyword.keyword_id for item in self.items for keyword in item.keywords]
        if len(keyword_ids) != len(set(keyword_ids)):
            raise ValueError("keyword IDs must be unique")
        return self


class AtomicKeywordDraft(PipelineModel):
    """One short retrieval term with an optional verified WordNet sense."""

    keyword_id: NonEmptyStr
    knowledge_id: NonEmptyStr
    surface: NonEmptyStr
    keyword: NonEmptyStr
    keyword_type: AtomicKeywordType
    semantic_role: SemanticRole
    source_field: KeywordSourceField
    wordnet_synset: NonBlankStr | None = None
    wordnet_lemma: NonBlankStr | None = None
    wordnet_pos: WordNetPos | None = None
    mapping_confidence: Probability | None = None

    @model_validator(mode="after")
    def validate_atomic_keyword(self) -> AtomicKeywordDraft:
        mapped_fields = (
            self.wordnet_synset,
            self.wordnet_lemma,
            self.wordnet_pos,
            self.mapping_confidence,
        )
        if any(value is not None for value in mapped_fields) and not all(
            value is not None for value in mapped_fields
        ):
            raise ValueError("WordNet mapping fields must be all present or all null")
        term = self.keyword.strip()
        numeric_with_grouping = self.keyword_type == "quantity" and re.fullmatch(
            r"[0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]+)?[^,，。；！？;!?\r\n]*",
            term,
        )
        if any(character in term for character in "，。；！？;!?\r\n") or (
            "," in term and numeric_with_grouping is None
        ):
            raise ValueError("keyword must be an atomic keyword")
        limit = 24 if self.keyword_type in {"entity", "time", "quantity"} else 12
        if len(term) > limit:
            raise ValueError("keyword must be an atomic keyword")
        if any(marker in term for marker in ("如果", "因为", "所以", "但是", "并且", "然后", "从而", "以便")):
            raise ValueError("keyword must be an atomic keyword")
        if len(term.split()) > (4 if self.keyword_type == "entity" else 2):
            raise ValueError("keyword must be an atomic keyword")
        return self


class AtomicKnowledgeKeywordOutput(PipelineModel):
    knowledge_id: NonEmptyStr
    keywords: list[AtomicKeywordDraft] = Field(min_length=1)


class AtomicKeywordPassOutput(PipelineModel):
    candidate_id: NonEmptyStr
    items: list[AtomicKnowledgeKeywordOutput] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_unique_ids(self) -> AtomicKeywordPassOutput:
        _require_unique(self.items, "knowledge_id", "knowledge IDs")
        keyword_ids = [keyword.keyword_id for item in self.items for keyword in item.keywords]
        if len(keyword_ids) != len(set(keyword_ids)):
            raise ValueError("keyword IDs must be unique")
        return self


class VocabularyCandidate(PipelineModel):
    vocabulary: NonEmptyStr
    id: NonEmptyStr
    label: NonEmptyStr
    description: NonEmptyStr
    term_kind: str | None = None
    pos: str | None = None
    lemmas: list[NonEmptyStr] = Field(default_factory=list)
    examples: list[NonEmptyStr] = Field(default_factory=list)


class RankedCandidate(PipelineModel):
    id: NonEmptyStr
    mapping: MappingKind
    score: Probability
    match_basis: NonEmptyStr


class CandidateRanking(PipelineModel):
    keyword_id: NonEmptyStr
    ranked_items: list[RankedCandidate] = Field(default_factory=list)
    selected_candidate: Literal[None] = None
