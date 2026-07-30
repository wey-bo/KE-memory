from __future__ import annotations

from pathlib import Path
from typing import Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .authoritative_memory import MemoryRepresentationBundleV3
from .git_memory_history import HistoryArtifact
from .query_compiler_v2 import (
    CompilerRegistryV1,
    QueryCompilationResultV1,
    QueryContextV1,
    QueryDraftProducer,
    compile_natural_query,
)
from .query_execution_snapshot_adapter import (
    build_query_execution_snapshot,
    execute_authoritative_query,
)
from .query_plan_v2_executor import QueryExecutionResultV3
from .turn_bundle import TurnBundleRevision


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class NaturalQueryExecutionRequestV1(StrictModel):
    schema_version: Literal["natural-query-execution-request-v1"] = (
        "natural-query-execution-request-v1"
    )
    question: str = Field(min_length=1)
    query_id: str = Field(min_length=1)
    query_time: str = Field(min_length=1)
    current_user_entity_id: str | None = None
    compiler_policy_revision: str = Field(min_length=1)


class NaturalQueryExecutionOutcomeV1(StrictModel):
    schema_version: Literal["natural-query-execution-outcome-v1"] = (
        "natural-query-execution-outcome-v1"
    )
    status: Literal["executed", "compile_abstained"]
    compilation: QueryCompilationResultV1
    execution: QueryExecutionResultV3 | None = None

    @model_validator(mode="after")
    def validate_status(self) -> "NaturalQueryExecutionOutcomeV1":
        if self.status == "executed":
            if self.compilation.status != "executable" or self.execution is None:
                raise ValueError("executed outcome requires compilation and execution")
        elif self.compilation.status != "abstain" or self.execution is not None:
            raise ValueError("compile abstention cannot contain execution")
        return self


def execute_natural_query(
    *,
    request: NaturalQueryExecutionRequestV1,
    repository_path: Path,
    bundle: MemoryRepresentationBundleV3,
    bundle_history_artifact: HistoryArtifact,
    turn_bundles: Sequence[TurnBundleRevision],
    registry: CompilerRegistryV1,
    producer: QueryDraftProducer,
    identity_snapshot_id: str | None = None,
) -> NaturalQueryExecutionOutcomeV1:
    validated_request = NaturalQueryExecutionRequestV1.model_validate(
        request.model_dump(mode="json")
    )
    bound_turn_bundles = list(turn_bundles)
    snapshot = build_query_execution_snapshot(
        repository_path=repository_path,
        bundle=bundle,
        bundle_history_artifact=bundle_history_artifact,
        turn_bundles=bound_turn_bundles,
        registry=registry,
        identity_snapshot_id=identity_snapshot_id,
    )
    context = QueryContextV1(
        query_id=validated_request.query_id,
        raw_query=validated_request.question,
        query_time=validated_request.query_time,
        current_user_entity_id=validated_request.current_user_entity_id,
        memory_view=snapshot.memory_view,
        ontology_revision=snapshot.ontology_revision,
        identity_revision=snapshot.identity_revision,
        compiler_policy_revision=validated_request.compiler_policy_revision,
    )
    compilation = compile_natural_query(
        question=validated_request.question,
        context=context,
        registry=registry,
        producer=producer,
    )
    if compilation.status == "abstain":
        return NaturalQueryExecutionOutcomeV1(
            status="compile_abstained",
            compilation=compilation,
        )
    if compilation.plan is None:
        raise ValueError("executable compilation is missing a plan")
    execution = execute_authoritative_query(
        repository_path=repository_path,
        bundle=bundle,
        bundle_history_artifact=bundle_history_artifact,
        turn_bundles=bound_turn_bundles,
        registry=registry,
        plan=compilation.plan,
        identity_snapshot_id=identity_snapshot_id,
    )
    return NaturalQueryExecutionOutcomeV1(
        status="executed",
        compilation=compilation,
        execution=execution,
    )
