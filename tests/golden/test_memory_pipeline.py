from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Literal, TypeVar, cast

import pytest
from pydantic import BaseModel

from ke_memory_demo.core.json import canonical_json
from ke_memory_demo.aggregation import (
    AggregateAssertionProposal,
    AggregateNodeProposal,
    AggregateSelectionOutput,
    SessionAggregationOutput,
    SessionKEProposal,
)
from ke_memory_demo.domain import (
    AggregateNode,
    AggregateNodeKind,
    ConceptRef,
    Conversation,
    CoverageStatus,
    IndividualRef,
    KnowledgeEquation,
    KnowledgeLevel,
    Lifecycle,
    MessageSpan,
    Modality,
    OntologyBinding,
    OntologyBindingStatus,
    OntologyRelationRef,
    OntologyRole,
    Polarity,
    RunScope,
    Speaker,
)
from ke_memory_demo.extraction import (
    DraftCoverageRange,
    DraftInformationUnit,
    DraftSpan,
    DraftSurfaceMention,
    LifecycleMatchDecision,
    LifecycleMatchOutput,
    ProposalConceptRef,
    ProposalIndividualRef,
    ProposalOperatorApplication,
    ProposalOperatorRef,
    TurnKEDraft,
    TurnKEOutput,
    TurnKEProposal,
    UNRESOLVED_MARKER,
)
from ke_memory_demo.ontology import (
    ElasticsearchVocabulary,
    IndexIdentity,
    OntologyHealth,
    OntologyRelation,
    OntologyTerm,
)
from ke_memory_demo.infra.llm import StructuredModelClient
from ke_memory_demo.infra.telemetry import (
    InMemoryTraceRecorder,
    ModelTrace,
    TraceContext,
    UsageRecord,
)
from ke_memory_demo.evaluation.stage import EvaluationStage
from ke_memory_demo.pipeline.ports import RuntimeContext
from ke_memory_demo.pipeline import (
    PIPELINE_ARTIFACT_REGISTRY,
    CheckpointStore,
    MemoryPipeline,
    PipelineInvariantError,
    PipelineStage,
    RuntimeFactory,
    RuntimeInvariantError,
)
from ke_memory_demo.pipeline.runner import (
    _validate_raw_evidence,  # pyright: ignore[reportPrivateUsage]
)
from ke_memory_demo.retrieval import KEMatchDecision, KEMatchOutput, MatchRelation, QueryKEDraft
from ke_memory_demo.retrieval.query import (
    QueryConceptDraft,
    QueryGroundingSpan,
    QueryIndividualDraft,
    QueryOperatorApplicationDraft,
    QueryOperatorDraft,
)
from ke_memory_demo.settings import (
    AggregationSettings,
    AppSettings,
    DatasetSettings,
    ElasticsearchFields,
    ElasticsearchRoles,
    ElasticsearchSettings,
    EmbeddingSettings,
    EvaluationConcurrencySettings,
    EvaluationSettings,
    ModelSettings,
    RetrievalSettings,
)
from ke_memory_demo.snapshots import GitSnapshotStore
from ke_memory_demo.storage import ArtifactStore
from ke_memory_demo.systems import KE_MEMORY_SYSTEM_ID


ModelT = TypeVar("ModelT", bound=BaseModel)
FIXTURE_PATH = Path(__file__).parent / "data/multi_session_conversation.json"
IDENTITY = IndexIdentity(
    index_name="golden-ontology",
    index_uuid="golden-uuid",
    mapping_sha256="a" * 64,
)
RUNTIME_QUESTION = "Does user prefers tea?"


def _normalized(value: str) -> str:
    return " ".join(value.split()).casefold()


def _document_id(value: str) -> str:
    return f"doc:{_normalized(value).replace(' ', '-')}"


_ROLES = {
    "user": OntologyRole.INDIVIDUAL,
    "tea": OntologyRole.CONCEPT,
    "prefers": OntologyRole.OPERATOR,
    "orion": OntologyRole.INDIVIDUAL,
    "has status": OntologyRole.OPERATOR,
    "blocked": OntologyRole.CONCEPT,
    "false": OntologyRole.CONCEPT,
    "unblocked": OntologyRole.CONCEPT,
    "has task": OntologyRole.OPERATOR,
    "launch checklist": OntologyRole.CONCEPT,
    "complete": OntologyRole.CONCEPT,
}


def _ontology_term(surface: str) -> OntologyTerm:
    normalized = _normalized(surface)
    relations = (
        (
            OntologyRelation(
                source_document_id=_document_id(normalized),
                relation_type="has-domain",
                target_id="projects",
            ),
        )
        if normalized == "orion"
        else ()
    )
    return OntologyTerm(
        document_id=_document_id(normalized),
        canonical_term=normalized,
        source_type=_ROLES[normalized].value,
        role=_ROLES[normalized],
        aliases=(f"{normalized} alias",),
        relations=relations,
    )


def _binding_from_term(surface: str, term: OntologyTerm) -> OntologyBinding:
    return OntologyBinding(
        surface_form=surface,
        normalized_surface=_normalized(surface),
        status=(
            OntologyBindingStatus.RESOLVED
            if term.role is not None
            else OntologyBindingStatus.UNRESOLVED_ROLE
        ),
        document_id=term.document_id,
        canonical_term=term.canonical_term,
        role=term.role,
        source_type=term.source_type,
        aliases=term.aliases,
        relations=tuple(
            OntologyRelationRef(
                relation_type=relation.relation_type,
                target_id=relation.target_id,
            )
            for relation in term.relations
        ),
    )


class FakeOntology:
    normalization_mode = "bounded-best-effort"

    def __init__(self, clock: list[str]) -> None:
        self.calls: list[str] = []
        self._clock = clock
        self.fetch_term_requests: list[tuple[str, ...]] = []
        self.fetch_relation_requests: list[tuple[str, ...]] = []
        self.identity = IDENTITY
        self.term_updates: dict[str, dict[str, object]] = {}
        self.fetch_term_mode: Literal["normal", "missing", "duplicate"] = "normal"

    async def health(self) -> OntologyHealth:
        self.calls.append("health")
        self._clock.append("ontology:health")
        return OntologyHealth(cluster_name="golden", status="green", timed_out=False)

    async def index_identity(self) -> IndexIdentity:
        self.calls.append("index_identity")
        self._clock.append("ontology:index_identity")
        return self.identity

    async def resolve_terms(self, surface_terms: Sequence[str]) -> list[OntologyBinding]:
        self.calls.append("resolve_terms")
        result: list[OntologyBinding] = []
        for surface in surface_terms:
            normalized = _normalized(surface)
            if normalized == "mystery-flux":
                result.append(
                    OntologyBinding(
                        surface_form=surface,
                        normalized_surface=normalized,
                        status=OntologyBindingStatus.UNRESOLVED,
                    )
                )
                continue
            result.append(_binding_from_term(surface, _ontology_term(normalized)))
        return result

    async def fetch_terms(self, document_ids: Sequence[str]) -> list[OntologyTerm]:
        self.calls.append("fetch_terms")
        self.fetch_term_requests.append(tuple(document_ids))
        terms = [self._fetched_term(document_id) for document_id in document_ids]
        if self.fetch_term_mode == "missing":
            return terms[:-1]
        if self.fetch_term_mode == "duplicate" and terms:
            return [*terms, terms[-1]]
        return terms

    async def fetch_relations(self, document_ids: Sequence[str]) -> list[OntologyRelation]:
        self.calls.append("fetch_relations")
        self.fetch_relation_requests.append(tuple(document_ids))
        return [
            relation
            for document_id in document_ids
            for relation in self._fetched_term(document_id).relations
        ]

    def _fetched_term(self, document_id: str) -> OntologyTerm:
        by_id = {_document_id(surface): surface for surface in _ROLES}
        term = _ontology_term(by_id[document_id])
        updates = self.term_updates.get(document_id)
        if updates is None:
            return term
        return OntologyTerm.model_validate({**term.model_dump(mode="python"), **updates})


@dataclass(frozen=True)
class _UnitSpec:
    key: str
    gloss: str
    modality: Modality
    polarity: Polarity
    lhs_surface: str
    operator_surface: str
    argument_surfaces: tuple[str, ...]


def _unit_specs(user_text: str) -> tuple[_UnitSpec, ...]:
    if user_text.startswith("I prefer tea"):
        return (
            _UnitSpec(
                "preference",
                "User prefers tea.",
                Modality.PREFERENCE,
                Polarity.POSITIVE,
                "user",
                "prefers",
                ("tea",),
            ),
            _UnitSpec(
                "status-blocked",
                "Orion project status is blocked by mystery-flux.",
                Modality.FACT,
                Polarity.POSITIVE,
                "orion",
                "has status",
                ("blocked", "mystery-flux"),
            ),
        )
    if user_text.startswith("The blocked Orion claim"):
        return (
            _UnitSpec(
                "status-contradiction",
                "The blocked Orion claim is false.",
                Modality.FACT,
                Polarity.NEGATIVE,
                "orion",
                "has status",
                ("false",),
            ),
            _UnitSpec(
                "status-unblocked",
                "Orion project status is unblocked.",
                Modality.FACT,
                Polarity.POSITIVE,
                "orion",
                "has status",
                ("unblocked",),
            ),
        )
    if user_text.startswith("For Orion"):
        return (
            _UnitSpec(
                "project-task",
                "Orion project task is the launch checklist.",
                Modality.PLAN,
                Polarity.POSITIVE,
                "orion",
                "has task",
                ("launch checklist",),
            ),
        )
    return (
        _UnitSpec(
            "status-complete",
            "Orion project status is complete.",
            Modality.FACT,
            Polarity.POSITIVE,
            "orion",
            "has status",
            ("complete",),
        ),
    )


class FakeWorkModel:
    def __init__(self, clock: list[str]) -> None:
        self._clock = clock
        self.embedding_calls = 0
        self.active_turn_calls = 0
        self.peak_turn_calls = 0
        self.lifecycle_new_glosses: list[tuple[str, ...]] = []
        self.dag_depths: list[int] = []

    @property
    def trace_records(self) -> tuple[ModelTrace, ...]:
        return (
            ModelTrace(
                context=TraceContext(
                    operation="golden-work",
                    metadata={"run_id": "golden-run"},
                ),
                transport_attempt=1,
                structured_request=1,
                latency_seconds=0.25,
                request={"messages": [{"content": "private prompt"}]},
                response={"choices": [{"content": "private response"}]},
                error=None,
                usage=UsageRecord(
                    request_id="golden-request",
                    model="golden-work",
                    latency_seconds=0.25,
                    input_tokens=4,
                    output_tokens=2,
                    total_tokens=6,
                ),
            ),
        )

    async def complete(
        self,
        model_type: type[ModelT],
        messages: Sequence[Mapping[str, object]],
        _trace_context: object,
    ) -> ModelT:
        payload = json.loads(str(messages[-1]["content"]))
        if payload["task"] == "pipeline_preflight":
            self._clock.append("model:preflight")
            return model_type.model_validate({"ready": True})
        if model_type is TurnKEDraft:
            self.active_turn_calls += 1
            self.peak_turn_calls = max(self.peak_turn_calls, self.active_turn_calls)
            self._clock.append("model:turn-draft")
            await asyncio.sleep(0)
            result = self._turn_draft(payload["exchange"])
            self.active_turn_calls -= 1
            return cast(ModelT, result)
        if model_type is TurnKEOutput:
            self._clock.append("model:turn-bind")
            return cast(ModelT, self._turn_output(payload))
        if model_type is LifecycleMatchOutput:
            return cast(ModelT, self._lifecycle_output(payload))
        if model_type is SessionAggregationOutput:
            return cast(ModelT, self._session_output(payload))
        if model_type is AggregateSelectionOutput:
            return cast(ModelT, self._dag_output(payload))
        if model_type is QueryKEDraft:
            return cast(ModelT, self._query_draft(payload))
        if model_type is KEMatchOutput:
            return cast(ModelT, self._match_output(payload))
        raise AssertionError(f"unexpected model type: {model_type.__name__}")

    async def embed(self, _texts: Sequence[str]) -> Sequence[Sequence[float]]:
        self.embedding_calls += 1
        raise AssertionError("embedding must remain disabled")

    @staticmethod
    def _query_draft(payload: dict[str, object]) -> QueryKEDraft:
        question = cast(str, payload["question"])
        assert question == RUNTIME_QUESTION

        def grounding(surface: str) -> QueryGroundingSpan:
            start = question.index(surface)
            return QueryGroundingSpan(start_char=start, end_char=start + len(surface))

        return QueryKEDraft(
            lhs=QueryIndividualDraft(
                surface_form="user",
                grounding_span=grounding("user"),
            ),
            rhs=QueryOperatorApplicationDraft(
                operator=QueryOperatorDraft(
                    surface_form="prefers",
                    grounding_span=grounding("prefers"),
                ),
                arguments=(
                    QueryConceptDraft(
                        surface_form="tea",
                        grounding_span=grounding("tea"),
                    ),
                ),
            ),
            gloss="User prefers tea.",
        )

    @staticmethod
    def _match_output(payload: dict[str, object]) -> KEMatchOutput:
        candidates = cast(list[dict[str, object]], payload["symbolic_candidates"])
        return KEMatchOutput(
            matches=tuple(
                KEMatchDecision(
                    candidate_id=cast(str, candidate["candidate_id"]),
                    match_type=MatchRelation.EXACT,
                    confidence=1,
                    reason="golden symbolic match",
                )
                for candidate in candidates
            )
        )

    @staticmethod
    def _turn_draft(exchange: dict[str, object]) -> TurnKEDraft:
        user = cast(dict[str, object], exchange["user"])
        assistant = cast(dict[str, object], exchange["assistant"])
        user_text = cast(str, user["content"])
        specs = _unit_specs(user_text)
        units = tuple(
            DraftInformationUnit(
                key=spec.key,
                gloss=spec.gloss,
                modality=spec.modality,
                polarity=spec.polarity,
                speaker=Speaker.USER,
                surface_mentions=(
                    DraftSurfaceMention(
                        surface_form=spec.lhs_surface,
                        expected_role=OntologyRole.INDIVIDUAL,
                    ),
                    DraftSurfaceMention(
                        surface_form=spec.operator_surface,
                        expected_role=OntologyRole.OPERATOR,
                    ),
                    *(
                        DraftSurfaceMention(
                            surface_form=surface,
                            expected_role=OntologyRole.CONCEPT,
                        )
                        for surface in spec.argument_surfaces
                    ),
                ),
                source_spans=(
                    DraftSpan(
                        message_id=cast(str, user["id"]),
                        start_char=0,
                        end_char=len(user_text),
                    ),
                ),
            )
            for spec in specs
        )
        return TurnKEDraft(
            information_units=units,
            coverage=(
                DraftCoverageRange(
                    message_id=cast(str, user["id"]),
                    start_char=0,
                    end_char=len(user_text),
                    status=CoverageStatus.REPRESENTED,
                    unit_keys=tuple(spec.key for spec in specs),
                ),
                DraftCoverageRange(
                    message_id=cast(str, assistant["id"]),
                    start_char=0,
                    end_char=len(cast(str, assistant["content"])),
                    status=CoverageStatus.CONTEXT_ONLY,
                ),
            ),
        )

    @staticmethod
    def _turn_output(payload: dict[str, object]) -> TurnKEOutput:
        exchange = cast(dict[str, object], payload["exchange_context"])
        user = cast(dict[str, object], exchange["user"])
        proposals: list[TurnKEProposal] = []
        for spec in _unit_specs(cast(str, user["content"])):
            proposals.append(
                TurnKEProposal(
                    key=spec.key,
                    information_unit_keys=(spec.key,),
                    lhs=ProposalIndividualRef(
                        surface_form=spec.lhs_surface,
                        candidate_id=_document_id(spec.lhs_surface),
                    ),
                    rhs=ProposalOperatorApplication(
                        operator=ProposalOperatorRef(
                            surface_form=spec.operator_surface,
                            candidate_id=_document_id(spec.operator_surface),
                        ),
                        arguments=tuple(
                            ProposalConceptRef(
                                surface_form=surface,
                                candidate_id=(
                                    UNRESOLVED_MARKER
                                    if _normalized(surface) == "mystery-flux"
                                    else _document_id(surface)
                                ),
                            )
                            for surface in spec.argument_surfaces
                        ),
                    ),
                    gloss=spec.gloss,
                    modality=spec.modality,
                    polarity=spec.polarity,
                    lifecycle="active",
                    confidence=0.9,
                )
            )
        return TurnKEOutput(proposals=tuple(proposals))

    def _lifecycle_output(self, payload: dict[str, object]) -> LifecycleMatchOutput:
        candidates = cast(list[dict[str, object]], payload["offered_pairs"])
        decisions: list[LifecycleMatchDecision] = []
        self.lifecycle_new_glosses.append(
            tuple(sorted({cast(str, candidate["new_gloss"]) for candidate in candidates}))
        )
        for candidate in candidates:
            old_gloss = cast(str, candidate["old_gloss"])
            new_gloss = cast(str, candidate["new_gloss"])
            decision: Literal["contradicts", "updates", "no_match"] = "no_match"
            reason = "independent statement"
            if new_gloss == "The blocked Orion claim is false." and "blocked" in old_gloss:
                decision = "contradicts"
                reason = "explicit contradiction"
            elif new_gloss == "Orion project status is unblocked." and "blocked" in old_gloss:
                decision = "updates"
                reason = "status update"
            elif new_gloss == "Orion project status is complete." and old_gloss.endswith(
                "is unblocked."
            ):
                decision = "updates"
                reason = "explicit project status update"
            decisions.append(
                LifecycleMatchDecision(
                    old_ke_id=cast(str, candidate["old_ke_id"]),
                    new_ke_id=cast(str, candidate["new_ke_id"]),
                    decision=decision,
                    confidence=0.95,
                    reason=reason,
                )
            )
        return LifecycleMatchOutput(matches=tuple(decisions))

    @staticmethod
    def _session_output(payload: dict[str, object]) -> SessionAggregationOutput:
        records = cast(list[dict[str, object]], payload["turn_knowledge_equations"])
        if cast(str, payload["session_id"]).endswith("a"):
            chosen = next(
                item
                for item in records
                if cast(str, item["gloss"]) == "Orion project status is unblocked."
            )
        else:
            chosen = next(
                item
                for item in records
                if cast(str, item["gloss"]) == "Orion project task is the launch checklist."
            )
        proposal = SessionKEProposal.model_validate(
            {
                "key": "session-project",
                "lhs": chosen["lhs"],
                "rhs": chosen["rhs"],
                "gloss": f"Session project memory for {payload['session_id']}",
                "modality": chosen["modality"],
                "polarity": chosen["polarity"],
                "lifecycle": "active",
                "confidence": 0.88,
                "derived_from": (cast(str, chosen["id"]),),
            }
        )
        return SessionAggregationOutput(
            summary=f"Memory for {payload['session_id']}",
            proposals=(proposal,),
        )

    def _dag_output(self, payload: dict[str, object]) -> AggregateSelectionOutput:
        depth = cast(Literal[1, 2], payload["depth"])
        self.dag_depths.append(depth)
        candidate = cast(list[dict[str, object]], payload["candidates"])[0]
        lowers = cast(list[dict[str, object]], candidate["lower_records"])
        first = lowers[0]
        member_refs = tuple(cast(list[str], candidate["member_refs"]))
        assertion = AggregateAssertionProposal.model_validate(
            {
                "key": "aggregate-project",
                "lhs": first["lhs"],
                "rhs": first["rhs"],
                "gloss": "Orion project memory spans sessions.",
                "modality": first["modality"],
                "polarity": first["polarity"],
                "lifecycle": "active",
                "confidence": 0.9,
                "derived_from": member_refs,
            }
        )
        proposal = AggregateNodeProposal(
            candidate_id=cast(str, candidate["id"]),
            depth=depth,
            member_refs=member_refs,
            node_kind=AggregateNodeKind.PROJECT,
            title="Orion project",
            summary="Cross-session Orion project state and task.",
            confidence=0.9,
            assertions=(assertion,),
        )
        return AggregateSelectionOutput(accepted=(proposal,))


@dataclass
class GoldenRuntime:
    pipeline: MemoryPipeline
    ontology: FakeOntology
    model: FakeWorkModel
    snapshots: GitSnapshotStore
    artifacts: ArtifactStore
    settings: AppSettings
    clock: list[str]

    @property
    def first_extract_call(self) -> int:
        return self.clock.index("model:turn-draft")

    @property
    def last_preflight_call(self) -> int:
        return self.clock.index("model:preflight")

    @property
    def embedding_calls(self) -> int:
        return self.model.embedding_calls


@pytest.fixture
def golden_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> GoldenRuntime:
    raw_fixture = FIXTURE_PATH.read_bytes()
    conversation = Conversation.model_validate_json(raw_fixture)
    archive_sha256 = hashlib.sha256(raw_fixture).hexdigest()
    settings = AppSettings(
        project_root=tmp_path,
        work=ModelSettings(
            model="golden-work",
            base_url="https://model.invalid/v1",
            api_key_env="GOLDEN_WORK_KEY",
            temperature=0,
            max_output_tokens=1024,
        ),
        judge=ModelSettings(
            model="golden-judge",
            base_url="https://judge.invalid/v1",
            api_key_env="GOLDEN_JUDGE_KEY",
            temperature=0,
            max_output_tokens=512,
        ),
        embedding=EmbeddingSettings(
            enabled=False,
            model="disabled",
            revision="b" * 40,
            local_path_env="GOLDEN_EMBEDDING_PATH",
            dimension=2,
            chunk_tokens=16,
            overlap_tokens=2,
            local_files_only=True,
        ),
        dataset=DatasetSettings(
            archive_path=FIXTURE_PATH,
            archive_sha256=archive_sha256,
            selected_directories=(1, 2, 3),
            expected_sessions=2,
            expected_exchanges=4,
            expected_questions=1,
        ),
        retrieval=RetrievalSettings(evidence_budget_tokens=128, answer_max_output_tokens=64),
        aggregation=AggregationSettings(max_semantic_depth=2),
        evaluation=EvaluationSettings(
            concurrency=EvaluationConcurrencySettings(
                turn_workers=2,
                session_workers=2,
                question_workers=2,
                judge_workers=2,
            )
        ),
        es=ElasticsearchSettings(
            endpoint_env="GOLDEN_ES_URL",
            index_env="GOLDEN_ES_INDEX",
            api_key_env="GOLDEN_ES_KEY",
            request_timeout_seconds=1,
            fields=ElasticsearchFields(
                canonical="term",
                type="type",
                aliases="aliases",
                relations="relations",
                relation_type="type",
                relation_target_id="target_id",
            ),
            roles=ElasticsearchRoles(
                concept=("concept",),
                individual=("individual",),
                operator=("operator",),
            ),
        ),
    )
    state_root = tmp_path / "state"
    artifacts = ArtifactStore(state_root, registry=PIPELINE_ARTIFACT_REGISTRY)
    snapshots = GitSnapshotStore.init(state_root, artifacts)
    clock: list[str] = []
    ontology = FakeOntology(clock)
    model = FakeWorkModel(clock)

    def load_fixture(_path: Path) -> list[Conversation]:
        return [conversation, Conversation(id="conversation-empty")]

    monkeypatch.setattr("ke_memory_demo.pipeline.runner.load_beam_subset", load_fixture)
    pipeline = MemoryPipeline(
        settings,
        artifacts,
        snapshots,
        CheckpointStore(state_root, "golden-run"),
        cast(ElasticsearchVocabulary, ontology),
        cast(StructuredModelClient, model),
        code_commit="c" * 40,
    )
    return GoldenRuntime(pipeline, ontology, model, snapshots, artifacts, settings, clock)


def _sample_span(conversation: Conversation) -> MessageSpan:
    message = conversation.sessions[0].exchanges[0].user
    return MessageSpan(
        message_id=message.id,
        start_char=0,
        end_char=len(message.content),
        text_hash=hashlib.sha256(message.content.encode("utf-8")).hexdigest(),
    )


def _sample_ke(
    conversation: Conversation,
    *,
    binding: OntologyBinding | None = None,
    evidence: bool = True,
) -> KnowledgeEquation:
    return KnowledgeEquation.create(
        level=KnowledgeLevel.TURN,
        lhs=IndividualRef(term_id="person:user", label="user"),
        rhs=ConceptRef(
            term_id=binding.document_id if binding and binding.document_id else "concept:tea",
            label="tea",
        ),
        gloss="User prefers tea.",
        modality=Modality.PREFERENCE,
        polarity=Polarity.POSITIVE,
        lifecycle=Lifecycle.ACTIVE,
        speaker=Speaker.USER,
        ontology_bindings=(binding,) if binding is not None else (),
        evidence_refs=(_sample_span(conversation),) if evidence else (),
        confidence=1,
        produced_in_run_id="golden-run",
        produced_in_stage=PipelineStage.TURN_KE_EXTRACTED.value,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "corruption",
    [
        "canonical_term",
        "source_type",
        "role",
        "aliases",
        "relations",
        "missing_term",
        "duplicate_term",
        "empty_ke_evidence",
        "empty_aggregate_evidence",
    ],
)
async def test_ke_ready_trust_gate_rejects_unauthenticated_records(
    golden_runtime: GoldenRuntime,
    corruption: str,
) -> None:
    conversation = Conversation.model_validate_json(FIXTURE_PATH.read_bytes())
    if corruption.startswith("empty_"):
        record: KnowledgeEquation | AggregateNode
        if corruption == "empty_ke_evidence":
            record = _sample_ke(conversation, evidence=False)
        else:
            record = AggregateNode(
                id="aggregate:empty-evidence",
                node_kind=AggregateNodeKind.TOPIC,
                title="Empty evidence",
                summary="This aggregate has no raw evidence closure.",
                confidence=1,
                revision="d" * 64,
                depth=1,
            )
        with pytest.raises(PipelineInvariantError):
            _validate_raw_evidence((conversation,), (record,))
        return

    binding = (await golden_runtime.ontology.resolve_terms(("tea",)))[0]
    assert binding.document_id is not None
    equation = _sample_ke(conversation, binding=binding)
    if corruption == "missing_term":
        golden_runtime.ontology.fetch_term_mode = "missing"
    elif corruption == "duplicate_term":
        golden_runtime.ontology.fetch_term_mode = "duplicate"
    else:
        updates: dict[str, object] = {
            "canonical_term": "contradictory tea",
            "source_type": "individual",
            "role": OntologyRole.INDIVIDUAL,
            "aliases": ("contradictory alias",),
            "relations": (
                OntologyRelation(
                    source_document_id=binding.document_id,
                    relation_type="contradicts",
                    target_id="tea",
                ),
            ),
        }
        golden_runtime.ontology.term_updates[binding.document_id] = {
            corruption: updates[corruption]
        }
    with pytest.raises(PipelineInvariantError):
        await golden_runtime.pipeline._fetch_bound_ontology(  # pyright: ignore[reportPrivateUsage]
            (equation,)
        )


@pytest.mark.asyncio
async def test_golden_pipeline_is_ontology_first_ke_only_and_traceable(
    golden_runtime: GoldenRuntime,
) -> None:
    result = await golden_runtime.pipeline.run_all()

    assert golden_runtime.ontology.calls[0] == "health"
    assert golden_runtime.ontology.calls[1] == "index_identity"
    assert golden_runtime.first_extract_call > golden_runtime.last_preflight_call
    assert golden_runtime.embedding_calls == 0
    assert result.stage is PipelineStage.KE_READY
    assert result.exchange_count == 4
    assert all(
        exchange.user.role.value == "user" and exchange.assistant.role.value == "assistant"
        for conversation in result.conversations
        for session in conversation.sessions
        for exchange in session.exchanges
    )
    tool_exchange = result.conversations[0].sessions[1].exchanges[0]
    assert [event.kind.value for event in tool_exchange.events] == ["tool_call", "tool_result"]
    assert result.semantic_dag.max_depth <= 2
    assert any(
        node.depth == 1 and len(node.evidence_closure) >= 2 for node in result.semantic_dag.nodes
    )
    current = result.find_current_ke("project status")
    assert current.supersedes
    assert result.resolve_raw_spans(current.id)
    history = tuple(
        golden_runtime.artifacts.read_jsonl(
            result.run_id,
            PipelineStage.KE_READY.value,
            "knowledge_equations",
            KnowledgeEquation,
        )
    )
    assert len(history) > len(result.current_knowledge_equations)
    assert any(item.modality is Modality.PREFERENCE for item in history)
    assert any(item.contradicts for item in history)
    assert any(
        binding.status is OntologyBindingStatus.UNRESOLVED
        for item in history
        for binding in item.ontology_bindings
    )
    assert len({item.id for item in result.current_knowledge_equations}) == len(
        result.current_knowledge_equations
    )
    bound_document_ids = tuple(
        sorted(
            {
                binding.document_id
                for item in history
                for binding in item.ontology_bindings
                if binding.document_id is not None
            }
        )
    )
    assert golden_runtime.ontology.fetch_term_requests == [bound_document_ids] * 2
    assert golden_runtime.ontology.fetch_relation_requests == [bound_document_ids] * 2
    assert golden_runtime.ontology.calls.count("index_identity") >= 6
    assert "Orion project status is unblocked." in golden_runtime.model.lifecycle_new_glosses[0]
    assert "Orion project status is complete." in golden_runtime.model.lifecycle_new_glosses[-1]
    assert golden_runtime.model.peak_turn_calls <= 2
    assert golden_runtime.model.dag_depths == sorted(golden_runtime.model.dag_depths)
    assert golden_runtime.snapshots.verify(
        result.snapshot_id,
        result.run_id,
        PipelineStage.KE_READY,
    ).verified
    for stage in tuple(PipelineStage)[:-1]:
        traces = tuple(
            golden_runtime.artifacts.read_jsonl(
                result.run_id,
                stage.value,
                "model_traces",
                ModelTrace,
            )
        )
        assert traces
        assert all(trace.request == {"provider_body": "redacted"} for trace in traces)
        assert all(trace.response in (None, {"provider_body": "redacted"}) for trace in traces)
        assert all(trace.error in (None, {"provider_body": "redacted"}) for trace in traces)


@pytest.mark.asyncio
async def test_runtime_factory_hydrates_isolated_conversations_from_exact_snapshot(
    golden_runtime: GoldenRuntime,
) -> None:
    result = await golden_runtime.pipeline.run_all()
    mutable_conversations = golden_runtime.artifacts.canonical_path(
        result.run_id,
        PipelineStage.KE_READY.value,
        "conversations",
    )
    mutable_conversations.write_bytes(
        canonical_json(Conversation(id="conversation-mutable-only")) + b"\n"
    )
    recorder = InMemoryTraceRecorder()
    factory = RuntimeFactory(
        settings=golden_runtime.settings,
        artifacts=golden_runtime.artifacts,
        snapshots=golden_runtime.snapshots,
        ontology=cast(ElasticsearchVocabulary, golden_runtime.ontology),
        work_model=cast(StructuredModelClient, golden_runtime.model),
        work_recorder=recorder,
        code_commit="c" * 40,
    )
    # _cumulative_evaluation_records moved to EvaluationStage with the evaluation
    # split, so the stage is composed here the way the CLI composes it: context and
    # narrow port, never the factory itself.
    stage = EvaluationStage(
        context=RuntimeContext(
            state_root=factory.artifacts.root,
            code_commit=factory.code_commit,
        ),
        port=factory,
        settings=factory.settings,
        artifacts=factory.artifacts,
        snapshots=factory.snapshots,
        ontology=factory.ontology,
        work_model=factory.work_model,
    )
    cumulative = stage._cumulative_evaluation_records(  # pyright: ignore[reportPrivateUsage]
        result.run_id,
        result.snapshot_id,
    )
    snapshot_conversations = cast(tuple[Conversation, ...], cumulative["conversations"])
    assert {item.id for item in snapshot_conversations} == {
        "conversation-golden",
        "conversation-empty",
    }

    golden_runtime.ontology.identity = IDENTITY.model_copy(
        update={"index_uuid": "drifted-golden-uuid"}
    )
    with pytest.raises(RuntimeInvariantError, match="ontology identity"):
        await factory.build_ke_systems(result.run_id, result.snapshot_id)
    golden_runtime.ontology.identity = IDENTITY

    systems = await factory.build_ke_systems(result.run_id, result.snapshot_id)
    assert set(systems) == {"conversation-golden", "conversation-empty"}
    assert systems["conversation-golden"] is not systems["conversation-empty"]

    populated_scope = RunScope(
        run_id=result.run_id,
        conversation_id="conversation-golden",
        system_id=KE_MEMORY_SYSTEM_ID,
    )
    empty_scope = RunScope(
        run_id=result.run_id,
        conversation_id="conversation-empty",
        system_id=KE_MEMORY_SYSTEM_ID,
    )
    populated_identity = await systems["conversation-golden"].prepare(populated_scope)
    empty_identity = await systems["conversation-empty"].prepare(empty_scope)
    populated_cache_id = populated_identity.metadata["runtime_cache_id"]
    empty_cache_id = empty_identity.metadata["runtime_cache_id"]
    assert isinstance(populated_cache_id, str)
    assert isinstance(empty_cache_id, str)
    assert populated_cache_id != empty_cache_id
    assert golden_runtime.artifacts.cache_path(populated_cache_id).is_file()
    assert golden_runtime.artifacts.cache_path(empty_cache_id).is_file()

    populated_evidence = await systems["conversation-golden"].retrieve(
        RUNTIME_QUESTION,
        512,
    )
    empty_evidence = await systems["conversation-empty"].retrieve(
        RUNTIME_QUESTION,
        512,
    )
    assert populated_evidence
    assert all(
        message_id.startswith("message-golden-")
        for evidence in populated_evidence
        for message_id in evidence.source_message_ids
    )
    assert empty_evidence == ()
    assert golden_runtime.model.embedding_calls == 0
