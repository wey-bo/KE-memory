from __future__ import annotations

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
