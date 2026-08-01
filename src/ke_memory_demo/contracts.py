from __future__ import annotations

from collections.abc import Iterator, Mapping
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ke_memory_demo.aggregation import SessionMemory
from ke_memory_demo.domain import KnowledgeEquation
from ke_memory_demo.infra.telemetry import ModelTrace
from ke_memory_demo.ontology import IndexIdentity, OntologyRelation, OntologyTerm
from ke_memory_demo.settings import EvaluationConcurrencySettings
from ke_memory_demo.storage import IndexStats


class PipelineStage(StrEnum):
    INGESTED = "ingested"
    TURN_KE_EXTRACTED = "turn-ke-extracted"
    SESSION_AGGREGATED = "session-aggregated"
    SEMANTIC_DAG_BUILT = "semantic-dag-built"
    KE_READY = "ke-ready"
    EVALUATION_COMPLETE = "evaluation-complete"


STAGE_PREDECESSOR: dict[PipelineStage, PipelineStage | None] = {
    PipelineStage.INGESTED: None,
    PipelineStage.TURN_KE_EXTRACTED: PipelineStage.INGESTED,
    PipelineStage.SESSION_AGGREGATED: PipelineStage.TURN_KE_EXTRACTED,
    PipelineStage.SEMANTIC_DAG_BUILT: PipelineStage.SESSION_AGGREGATED,
    PipelineStage.KE_READY: PipelineStage.SEMANTIC_DAG_BUILT,
    PipelineStage.EVALUATION_COMPLETE: PipelineStage.KE_READY,
}


class OntologyRunIdentity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    index: IndexIdentity
    normalization_mode: Literal["bounded-best-effort"]
    matched_document_ids: tuple[str, ...] = ()


class PipelineRunManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    stage: PipelineStage
    parent_snapshot_id: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")] | None
    code_commit: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    dataset_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    selected_directories: tuple[int, int, int]
    ontology: OntologyRunIdentity
    embedding_enabled: bool
    concurrency: EvaluationConcurrencySettings
    record_counts: dict[str, int]

    @model_validator(mode="after")
    def _ke_only(self) -> PipelineRunManifest:
        if self.embedding_enabled:
            raise ValueError("formal KE-only manifests must keep embedding disabled")
        return self


class PipelineStageResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    stage: PipelineStage
    snapshot_id: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    record_counts: dict[str, int]


class SnapshotRef(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    snapshot_id: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    run_id: str
    stage: PipelineStage
    stage_manifest_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class SnapshotVerification(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    snapshot_id: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    run_id: str
    stage: PipelineStage
    verified: Literal[True]
    stage_manifest_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


PIPELINE_ARTIFACT_REGISTRY: dict[str, type[BaseModel]] = {
    "pipeline_manifests": PipelineRunManifest,
    "ontology_terms": OntologyTerm,
    "ontology_relations": OntologyRelation,
    "session_memories": SessionMemory,
    "index_stats": IndexStats,
    "current_knowledge_equations": KnowledgeEquation,
    "model_traces": ModelTrace,
}


class _LazyArtifactRegistry(Mapping[str, type[BaseModel]]):
    """A registry populated by a higher layer at import time.

    The evaluation artifact map used to live here as a method with a deferred
    ``import ke_memory_demo.evaluation`` inside it. That made contracts depend on
    measurement while looking, to a static reader, like it did not -- the deferral
    hid the cycle rather than removing it.

    Now the direction is inverted: ``evaluation`` registers its artifact types into
    this object, and the layers below it (pipeline, snapshots) read the mapping
    without naming evaluation at all. Reading before registration raises rather
    than returning an empty map, so a missing registration is a loud failure and
    not a silently reduced artifact set.
    """

    def __init__(self, label: str) -> None:
        self._label = label
        self._entries: dict[str, type[BaseModel]] | None = None

    def register(self, entries: Mapping[str, type[BaseModel]]) -> None:
        if self._entries is not None and dict(self._entries) != dict(entries):
            raise RuntimeError(f"{self._label} already registered with different entries")
        self._entries = dict(entries)

    def _require(self) -> dict[str, type[BaseModel]]:
        if self._entries is None:
            raise RuntimeError(
                f"{self._label} has not been registered; import "
                "ke_memory_demo.evaluation before reading it"
            )
        return self._entries

    def __getitem__(self, key: str) -> type[BaseModel]:
        return self._require()[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._require())

    def __len__(self) -> int:
        return len(self._require())


EVALUATION_ARTIFACT_REGISTRY: _LazyArtifactRegistry = _LazyArtifactRegistry(
    "EVALUATION_ARTIFACT_REGISTRY"
)


_INGESTED_ARTIFACTS = frozenset(
    {
        "conversations",
        "exchanges",
        "messages",
        "model_traces",
        "ontology_relations",
        "ontology_terms",
        "pipeline_manifests",
        "sessions",
        "tool_events",
    }
)
_TURN_KE_EXTRACTED_ARTIFACTS = _INGESTED_ARTIFACTS | {
    "coverage",
    "current_knowledge_equations",
    "knowledge_equations",
}
_SESSION_AGGREGATED_ARTIFACTS = _TURN_KE_EXTRACTED_ARTIFACTS | {"session_memories"}
_SEMANTIC_DAG_BUILT_ARTIFACTS = _SESSION_AGGREGATED_ARTIFACTS | {"aggregates"}
_KE_READY_ARTIFACTS = _SEMANTIC_DAG_BUILT_ARTIFACTS | {"index_stats"}
_EVALUATION_ARTIFACTS = frozenset(
    {
        "aggregate_metrics",
        "baseline_public_results",
        "evaluation_failures",
        "evaluation_runs",
        "experiment_manifests",
        "gold_source_mappings",
        "judge_results",
        "operation_usage_metrics",
        "probe_questions",
        "query_traces",
        "question_answers",
        "question_metrics",
        "report_documents",
        "retrieval_traces",
        "turn_ke_audits",
    }
)

STAGE_ARTIFACT_ALLOWLIST: Mapping[PipelineStage, frozenset[str]] = {
    PipelineStage.INGESTED: _INGESTED_ARTIFACTS,
    PipelineStage.TURN_KE_EXTRACTED: _TURN_KE_EXTRACTED_ARTIFACTS,
    PipelineStage.SESSION_AGGREGATED: _SESSION_AGGREGATED_ARTIFACTS,
    PipelineStage.SEMANTIC_DAG_BUILT: _SEMANTIC_DAG_BUILT_ARTIFACTS,
    PipelineStage.KE_READY: _KE_READY_ARTIFACTS,
    PipelineStage.EVALUATION_COMPLETE: _KE_READY_ARTIFACTS | _EVALUATION_ARTIFACTS,
}
