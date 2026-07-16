from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal, Protocol, TypeVar, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from ke_memory_demo.core.ids import content_id
from ke_memory_demo.core.json import JsonObject, JsonValue, canonical_json
from ke_memory_demo.domain import (
    ConceptRef,
    Evidence,
    Expression,
    IndividualRef,
    Lifecycle,
    OntologyBinding,
    OntologyBindingStatus,
    OntologyRole,
    OperatorApplication,
    OperatorRef,
    TemporalMetadata,
)
from ke_memory_demo.extraction import normalize_surface
from ke_memory_demo.infra.telemetry import TraceContext
from ke_memory_demo.embedding import SearchHit


if TYPE_CHECKING:
    from .fusion import EvidenceCandidate
    from .matcher import KEMatchDecision
    from .symbolic import SymbolicCandidate


MAX_EVIDENCE_TOKENS = 8192
_PROMPT_PATH = Path(__file__).resolve().parents[3] / "prompts/query_ke/system.md"
NonEmptyString = Annotated[str, Field(min_length=1)]
ModelT = TypeVar("ModelT", bound=BaseModel)


class RetrievalInvariantError(ValueError):
    """A retrieval request or staged component violated the local contract."""


class QueryInvariantError(RetrievalInvariantError):
    """Query extraction or ontology binding violated its trust boundary."""


class _QueryRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class QueryConceptDraft(_QueryRecord):
    kind: Literal["concept"] = "concept"
    surface_form: NonEmptyString


class QueryIndividualDraft(_QueryRecord):
    kind: Literal["individual"] = "individual"
    surface_form: NonEmptyString


class QueryOperatorDraft(_QueryRecord):
    kind: Literal["operator"] = "operator"
    surface_form: NonEmptyString


class QueryOperatorApplicationDraft(_QueryRecord):
    kind: Literal["application"] = "application"
    operator: QueryOperatorDraft
    arguments: tuple[QueryDraftExpression, ...]


type QueryDraftExpression = Annotated[
    QueryConceptDraft
    | QueryIndividualDraft
    | QueryOperatorDraft
    | QueryOperatorApplicationDraft,
    Field(discriminator="kind"),
]


QueryOperatorApplicationDraft.model_rebuild()


class QueryKEDraft(_QueryRecord):
    lhs: QueryDraftExpression
    rhs: QueryDraftExpression
    gloss: NonEmptyString
    lifecycle: tuple[Lifecycle, ...] = ()
    temporal: TemporalMetadata = Field(default_factory=TemporalMetadata)

    @model_validator(mode="after")
    def _validate_lifecycle(self) -> QueryKEDraft:
        if len(self.lifecycle) != len(set(self.lifecycle)):
            raise ValueError("duplicate query lifecycle filters are not allowed")
        return self


class QueryKE(_QueryRecord):
    lhs: Expression
    rhs: Expression
    gloss: NonEmptyString
    lifecycle: tuple[Lifecycle, ...] = ()
    temporal: TemporalMetadata = Field(default_factory=TemporalMetadata)
    ontology_bindings: tuple[OntologyBinding, ...] = ()

    @model_validator(mode="after")
    def _validate_query(self) -> QueryKE:
        if len(self.lifecycle) != len(set(self.lifecycle)):
            raise ValueError("duplicate query lifecycle filters are not allowed")
        binding_keys = tuple(
            (
                item.normalized_surface,
                item.status,
                item.document_id,
                item.role,
            )
            for item in self.ontology_bindings
        )
        if len(binding_keys) != len(set(binding_keys)):
            raise ValueError("duplicate query ontology bindings are not allowed")
        return self


class QueryExtractionTrace(_QueryRecord):
    question_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    prompt_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    query_ke: QueryKE


class QueryTraceRecorder(Protocol):
    def record(self, trace: QueryExtractionTrace) -> None: ...


class InMemoryQueryTraceRecorder:
    def __init__(self) -> None:
        self._records: tuple[QueryExtractionTrace, ...] = ()

    @property
    def records(self) -> tuple[QueryExtractionTrace, ...]:
        return self._records

    def record(self, trace: QueryExtractionTrace) -> None:
        validated = QueryExtractionTrace.model_validate(trace.model_dump(mode="python"))
        self._records = (*self._records, validated)


class StructuredQueryClient(Protocol):
    async def complete(
        self,
        model_type: type[ModelT],
        messages: Sequence[Mapping[str, object]],
        trace_context: TraceContext | Mapping[str, object],
    ) -> ModelT: ...


class QueryVocabulary(Protocol):
    async def resolve_terms(
        self,
        surface_terms: Sequence[str],
    ) -> list[OntologyBinding]: ...


class EmbeddingClosureSource(Protocol):
    def source_fragments_for_hit(self, hit: SearchHit) -> tuple[object, ...]: ...


class _EmbeddingBackendPort(Protocol):
    def embed_query(self, question: str) -> object: ...


class _VectorIndexPort(Protocol):
    def search(self, query: object, *, limit: int) -> list[SearchHit]: ...


class QueryKEExtractor:
    def __init__(
        self,
        model: StructuredQueryClient,
        vocabulary: QueryVocabulary,
        *,
        run_id: str,
        trace_recorder: QueryTraceRecorder | None = None,
    ) -> None:
        if not run_id:
            raise QueryInvariantError("run_id must not be empty")
        self._model = model
        self._vocabulary = vocabulary
        self._run_id = run_id
        self._trace_recorder = trace_recorder or InMemoryQueryTraceRecorder()
        self._prompt = _read_prompt()
        self.prompt_sha256 = hashlib.sha256(self._prompt.encode("utf-8")).hexdigest()

    async def extract(self, question: str) -> QueryKE:
        if not question.strip():
            raise QueryInvariantError("question must not be empty")
        question_sha256 = hashlib.sha256(question.encode("utf-8")).hexdigest()
        payload: JsonObject = {"task": "extract_query_ke", "question": question}
        response = await self._model.complete(
            QueryKEDraft,
            (
                {"role": "system", "content": self._prompt},
                {"role": "user", "content": canonical_json(payload).decode("utf-8")},
            ),
            TraceContext(
                operation="query-ke-extract",
                metadata={
                    "run_id": self._run_id,
                    "question_sha256": question_sha256,
                    "prompt_sha256": self.prompt_sha256,
                },
            ),
        )
        draft = _revalidate(QueryKEDraft, response, "query KE draft")
        bindings = await self._resolve_bindings(draft)
        used_bindings: list[OntologyBinding] = []
        query_ke = QueryKE(
            lhs=_bind_expression(draft.lhs, bindings, used_bindings),
            rhs=_bind_expression(draft.rhs, bindings, used_bindings),
            gloss=draft.gloss,
            lifecycle=tuple(sorted(draft.lifecycle, key=lambda item: item.value)),
            temporal=draft.temporal,
            ontology_bindings=_unique_bindings(used_bindings),
        )
        self._trace_recorder.record(
            QueryExtractionTrace(
                question_sha256=question_sha256,
                prompt_sha256=self.prompt_sha256,
                query_ke=query_ke,
            )
        )
        return query_ke

    async def _resolve_bindings(
        self,
        draft: QueryKEDraft,
    ) -> dict[str, OntologyBinding]:
        surfaces: dict[str, set[str]] = {}
        for expression in (draft.lhs, draft.rhs):
            for surface_form, _role in _draft_atoms(expression):
                normalized = normalize_surface(surface_form)
                if not normalized:
                    raise QueryInvariantError("query expression contains an empty surface")
                surfaces.setdefault(normalized, set()).add(surface_form)
        queries = tuple(min(surfaces[key]) for key in sorted(surfaces))
        returned = await self._vocabulary.resolve_terms(queries) if queries else []
        if len(returned) != len(queries):
            raise QueryInvariantError(
                "ontology resolver result count does not match requested query surfaces"
            )
        by_surface: dict[str, OntologyBinding] = {}
        for query, binding in zip(queries, returned, strict=True):
            normalized = normalize_surface(query)
            if normalize_surface(binding.surface_form) != normalized:
                raise QueryInvariantError(
                    "ontology resolver result order does not match query surfaces"
                )
            if normalize_surface(binding.normalized_surface) != normalized:
                raise QueryInvariantError("ontology resolver normalized query surface mismatch")
            if normalized in by_surface:
                raise QueryInvariantError("ontology resolver returned duplicate query surface")
            by_surface[normalized] = binding
        return by_surface


class EmbeddingRetriever:
    _DERIVED_KINDS = frozenset(
        {"turn_ke", "session_summary", "session_ke", "aggregate_summary", "aggregate_ke"}
    )

    def __init__(
        self,
        backend: object,
        index: object,
        *,
        closure_source: EmbeddingClosureSource | None = None,
        limit: int = 20,
    ) -> None:
        if isinstance(limit, bool) or limit <= 0:
            raise RetrievalInvariantError("embedding candidate limit must be positive")
        self._backend = cast(_EmbeddingBackendPort, backend)
        self._index = cast(_VectorIndexPort, index)
        self._closure_source = closure_source
        self._limit = limit

    async def retrieve(self, *, question: str) -> tuple[EvidenceCandidate, ...]:
        from .fusion import EvidenceCandidate
        from .symbolic import SourceFragment

        if not question.strip():
            raise RetrievalInvariantError("question must not be empty")
        query_vector = self._backend.embed_query(question)
        hits = self._index.search(query_vector, limit=self._limit)
        candidates: list[EvidenceCandidate] = []
        for raw_hit in hits:
            hit = SearchHit.model_validate(raw_hit.model_dump(mode="python"))
            kind = hit.metadata.get("kind")
            derived = isinstance(kind, str) and kind in self._DERIVED_KINDS
            fragments: tuple[SourceFragment, ...] = ()
            if derived:
                if self._closure_source is None:
                    raise RetrievalInvariantError(
                        f"derived embedding hit has no raw closure source: {hit.document_id}"
                    )
                fragments = tuple(
                    SourceFragment.model_validate(item)
                    for item in self._closure_source.source_fragments_for_hit(hit)
                )
                if not fragments:
                    raise RetrievalInvariantError(
                        f"derived embedding hit has an empty raw closure: {hit.document_id}"
                    )
            record_ids = tuple(
                sorted({*hit.source_ke_ids, *hit.source_aggregate_ids})
            ) or (hit.document_id,)
            candidates.append(
                EvidenceCandidate(
                    candidate_id=hit.document_id,
                    text=hit.text,
                    score=hit.score,
                    channel="embedding",
                    source_exchange_ids=tuple(sorted(set(hit.source_exchange_ids))),
                    source_message_ids=tuple(sorted(set(hit.source_message_ids))),
                    source_session_ids=tuple(sorted(set(hit.source_session_ids))),
                    system_record_ids=record_ids,
                    derived=derived,
                    raw_closure=fragments,
                    metadata=dict(hit.metadata),
                )
            )
        return tuple(candidates)


class _SymbolicPath(Protocol):
    async def extract_query(self, question: str) -> QueryKE: ...

    async def retrieve(self, *, query_ke: QueryKE) -> Sequence[SymbolicCandidate]: ...


class _EmbeddingPath(Protocol):
    async def retrieve(self, *, question: str) -> Sequence[EvidenceCandidate]: ...


class _Matcher(Protocol):
    async def match(
        self,
        *,
        query_ke: QueryKE,
        symbolic_candidates: Sequence[SymbolicCandidate],
    ) -> Sequence[KEMatchDecision]: ...


class _Fusion(Protocol):
    def fuse(
        self,
        *,
        symbolic_candidates: Sequence[SymbolicCandidate],
        matches: Sequence[KEMatchDecision],
        embedding_candidates: Sequence[EvidenceCandidate],
        budget: int,
    ) -> Sequence[Evidence]: ...


class RetrievalCoordinator:
    def __init__(
        self,
        symbolic: object,
        embedding: object,
        matcher: object,
        fusion: object,
    ) -> None:
        self._symbolic = cast(_SymbolicPath, symbolic)
        self._embedding = cast(_EmbeddingPath, embedding)
        self._matcher = cast(_Matcher, matcher)
        self._fusion = cast(_Fusion, fusion)

    async def retrieve(
        self,
        question: str,
        evidence_budget_tokens: int = MAX_EVIDENCE_TOKENS,
    ) -> Sequence[Evidence]:
        if not question.strip():
            raise RetrievalInvariantError("question must not be empty")
        if (
            isinstance(evidence_budget_tokens, bool)
            or evidence_budget_tokens <= 0
            or evidence_budget_tokens > MAX_EVIDENCE_TOKENS
        ):
            raise RetrievalInvariantError(
                f"evidence budget must be between 1 and {MAX_EVIDENCE_TOKENS} tokens"
            )

        query_ke = await self._symbolic.extract_query(question)
        symbolic_candidates = await self._symbolic.retrieve(query_ke=query_ke)
        matches = await self._matcher.match(
            query_ke=query_ke,
            symbolic_candidates=symbolic_candidates,
        )
        embedding_candidates = await self._embedding.retrieve(question=question)
        return self._fusion.fuse(
            symbolic_candidates=symbolic_candidates,
            matches=matches,
            embedding_candidates=embedding_candidates,
            budget=evidence_budget_tokens,
        )


def _read_prompt() -> str:
    try:
        return _PROMPT_PATH.read_text(encoding="utf-8")
    except OSError as error:
        raise QueryInvariantError("required query KE prompt is unavailable") from error


def _revalidate(model_type: type[ModelT], value: object, label: str) -> ModelT:
    if not isinstance(value, BaseModel):
        raise QueryInvariantError(f"{label} is not a validated model record")
    try:
        return model_type.model_validate(value.model_dump(mode="python"))
    except ValidationError as error:
        raise QueryInvariantError(f"{label} failed local schema validation") from error


def _draft_atoms(
    expression: QueryDraftExpression,
) -> tuple[tuple[str, OntologyRole], ...]:
    if isinstance(expression, QueryOperatorApplicationDraft):
        return (
            (expression.operator.surface_form, OntologyRole.OPERATOR),
            *(
                item
                for argument in expression.arguments
                for item in _draft_atoms(argument)
            ),
        )
    if isinstance(expression, QueryConceptDraft):
        role = OntologyRole.CONCEPT
    elif isinstance(expression, QueryIndividualDraft):
        role = OntologyRole.INDIVIDUAL
    else:
        role = OntologyRole.OPERATOR
    return ((expression.surface_form, role),)


def _bind_expression(
    expression: QueryDraftExpression,
    bindings: Mapping[str, OntologyBinding],
    used_bindings: list[OntologyBinding],
) -> Expression:
    if isinstance(expression, QueryOperatorApplicationDraft):
        operator = _bind_expression(expression.operator, bindings, used_bindings)
        if not isinstance(operator, OperatorRef):
            raise QueryInvariantError("query application operator has the wrong role")
        return OperatorApplication(
            operator=operator,
            arguments=tuple(
                _bind_expression(argument, bindings, used_bindings)
                for argument in expression.arguments
            ),
        )
    if isinstance(expression, QueryConceptDraft):
        role = OntologyRole.CONCEPT
        expression_type = ConceptRef
    elif isinstance(expression, QueryIndividualDraft):
        role = OntologyRole.INDIVIDUAL
        expression_type = IndividualRef
    else:
        role = OntologyRole.OPERATOR
        expression_type = OperatorRef

    normalized = normalize_surface(expression.surface_form)
    binding = bindings.get(normalized)
    if binding is None:
        raise QueryInvariantError(f"query expression names an unresolved surface: {normalized}")
    if binding.status is OntologyBindingStatus.RESOLVED and binding.role is role:
        if binding.document_id is None:
            raise QueryInvariantError("resolved query binding is missing its document ID")
        term_id = binding.document_id
        used = _binding_for_surface(binding, expression.surface_form, normalized)
    else:
        term_id = content_id(f"unresolved-{role.value}", normalized)
        if binding.status is OntologyBindingStatus.RESOLVED:
            used = OntologyBinding(
                surface_form=expression.surface_form,
                normalized_surface=normalized,
                status=OntologyBindingStatus.UNRESOLVED,
            )
        else:
            used = _binding_for_surface(binding, expression.surface_form, normalized)
    used_bindings.append(used)
    return expression_type(term_id=term_id, label=expression.surface_form)


def _binding_for_surface(
    binding: OntologyBinding,
    surface_form: str,
    normalized_surface: str,
) -> OntologyBinding:
    values = binding.model_dump(mode="python")
    values["surface_form"] = surface_form
    values["normalized_surface"] = normalized_surface
    return OntologyBinding.model_validate(values)


def _unique_bindings(bindings: Sequence[OntologyBinding]) -> tuple[OntologyBinding, ...]:
    unique: dict[bytes, OntologyBinding] = {}
    for binding in bindings:
        key = canonical_json(cast(JsonValue, binding.model_dump(mode="json")))
        unique[key] = binding
    return tuple(unique[key] for key in sorted(unique))
