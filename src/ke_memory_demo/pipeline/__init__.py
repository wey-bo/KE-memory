from importlib import import_module
from typing import TYPE_CHECKING, cast

from .checkpoints import CheckpointStore
from .concurrency import BatchFailure, BatchOutcome, bounded_collect, bounded_ordered_map
from .models import (
    EVALUATION_ARTIFACT_REGISTRY,
    PIPELINE_ARTIFACT_REGISTRY,
    STAGE_PREDECESSOR,
    OntologyRunIdentity,
    PipelineRunManifest,
    PipelineStage,
    PipelineStageResult,
    SnapshotRef,
    SnapshotVerification,
)


if TYPE_CHECKING:
    from .runner import (
        MemoryPipeline,
        PipelineInvariantError,
        PipelinePreflightResult,
        PipelineRunResult,
    )
    from .runtime import RuntimeFactory, RuntimeInvariantError


_LAZY_EXPORTS = {
    "MemoryPipeline": ".runner",
    "PipelineInvariantError": ".runner",
    "PipelinePreflightResult": ".runner",
    "PipelineRunResult": ".runner",
    "RuntimeFactory": ".runtime",
    "RuntimeInvariantError": ".runtime",
}


def __getattr__(name: str) -> object:
    module_name = _LAZY_EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(module_name, __name__)
    value = cast(object, getattr(module, name))
    globals()[name] = value
    return value


__all__ = [
    "EVALUATION_ARTIFACT_REGISTRY",
    "PIPELINE_ARTIFACT_REGISTRY",
    "STAGE_PREDECESSOR",
    "BatchFailure",
    "BatchOutcome",
    "CheckpointStore",
    "MemoryPipeline",
    "OntologyRunIdentity",
    "PipelineInvariantError",
    "PipelinePreflightResult",
    "PipelineRunManifest",
    "PipelineRunResult",
    "RuntimeFactory",
    "RuntimeInvariantError",
    "PipelineStage",
    "PipelineStageResult",
    "SnapshotRef",
    "SnapshotVerification",
    "bounded_collect",
    "bounded_ordered_map",
]
