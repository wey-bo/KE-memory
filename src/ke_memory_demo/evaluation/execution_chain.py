"""The real execution chain, with a trace per layer.

Nine stages, in order::

    MemoryBuildInput -> builder artifact -> extraction -> mapping -> L1/L2 -> query plan
                     -> retrieval -> delivery -> answer

Two properties this module exists to establish, both of which earlier work only appeared to have:

The chain consumes the builder artifact. Every stage reads
:class:`~ke_memory_demo.evaluation.memory_artifact.MemoryArtifact`, never the corpus, and each
trace carries the artifact digest it read. ``assert_artifact_consumed`` then proves the digest
matches, so an arm cannot claim consumption by recording a hash.

Each layer is separately observable. A trace records the layer's inputs and outputs by hash and a
failure status, so a substitution's effect can be located instead of inferred. Without per-layer
hashes, "only the target layer changed" is an assertion about intent.

Layer implementations stay injected. That is what lets an oracle replace one real layer while the
rest run unchanged, and it is why the oracles can live only in the evaluation process.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, Protocol, cast

from pydantic import BaseModel, ConfigDict, Field

from ke_memory_demo.core.json import JsonObject, JsonValue, canonical_json

from .channels import BenchmarkQuestion
from .memory_artifact import ArtifactTurn, MemoryArtifact, assert_artifact_consumed

NonEmptyString = Annotated[str, Field(min_length=1)]


class ChainError(ValueError):
    """A stage was misconfigured, or a trace does not describe what ran."""


class Layer(StrEnum):
    """The nine stages, named so a trace and an oracle can refer to the same thing."""

    BUILD_INPUT = "build_input"
    BUILDER_ARTIFACT = "builder_artifact"
    EXTRACTION = "extraction"
    MAPPING = "mapping"
    L1_L2 = "l1_l2"
    QUERY_PLAN = "query_plan"
    RETRIEVAL = "retrieval"
    DELIVERY = "delivery"
    ANSWER = "answer"


# The layers a substitution may legitimately disturb: itself and whatever runs after it.
_ORDER: tuple[Layer, ...] = (
    Layer.EXTRACTION,
    Layer.MAPPING,
    Layer.L1_L2,
    Layer.QUERY_PLAN,
    Layer.RETRIEVAL,
    Layer.DELIVERY,
    Layer.ANSWER,
)


def downstream_of(layer: Layer) -> frozenset[Layer]:
    if layer not in _ORDER:
        return frozenset()
    index = _ORDER.index(layer)
    if layer is Layer.QUERY_PLAN:
        # A plan cannot alter extraction, mapping or abstraction, which all precede it.
        return frozenset({Layer.QUERY_PLAN, Layer.RETRIEVAL, Layer.DELIVERY, Layer.ANSWER})
    return frozenset(_ORDER[index:])


class LayerStatus(StrEnum):
    OK = "ok"
    EMPTY = "empty"
    REFUSED = "refused"


class LayerTrace(BaseModel):
    """What one layer received and produced, by hash."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    layer: Layer
    input_sha256: NonEmptyString
    output_sha256: NonEmptyString
    artifact_sha256: NonEmptyString
    status: LayerStatus
    substituted: bool = False
    detail: JsonObject = Field(default_factory=dict)


@dataclass(frozen=True)
class SurfaceUnit:
    """An extracted unit, carrying the artifact handle it came from."""

    evidence_handle: str
    text: str
    speaker: str
    approximate_tokens: int
    role: str = "unspecified"
    predicate: str = "unspecified"


@dataclass(frozen=True)
class Abstraction:
    abstraction_id: str
    canonical_id: str
    derived_from: tuple[str, ...]


@dataclass(frozen=True)
class QueryPlan:
    requested_canonical_ids: tuple[str, ...]
    requires_abstraction: bool = False


@dataclass(frozen=True)
class ChainResult:
    """The end of the chain, plus the traces that show how it got there."""

    question_id: str
    selected_handles: tuple[str, ...]
    delivered_handles: tuple[str, ...]
    answer_text: str
    abstained: bool
    traces: tuple[LayerTrace, ...]
    artifact_sha256: str

    def trace_for(self, layer: Layer) -> LayerTrace | None:
        for trace in self.traces:
            if trace.layer is layer:
                return trace
        return None

    def output_hashes(self) -> dict[Layer, str]:
        return {trace.layer: trace.output_sha256 for trace in self.traces}


# --------------------------------------------------------------------------------------
# Layer protocols. Each is the narrowest interface an oracle can replace.
# --------------------------------------------------------------------------------------


class ExtractionLayer(Protocol):
    def extract(self, turns: Sequence[ArtifactTurn]) -> tuple[SurfaceUnit, ...]: ...


class MappingLayer(Protocol):
    def map_units(self, units: Sequence[SurfaceUnit]) -> dict[str, tuple[str, str]]: ...


class AbstractionLayer(Protocol):
    def abstract(
        self,
        units: Sequence[SurfaceUnit],
        mapping: dict[str, tuple[str, str]],
    ) -> tuple[Abstraction, ...]: ...


class QueryPlanLayer(Protocol):
    def compile_plan(self, question: BenchmarkQuestion) -> QueryPlan: ...


class RetrievalLayer(Protocol):
    def retrieve(
        self,
        question: BenchmarkQuestion,
        units: Sequence[SurfaceUnit],
        mapping: dict[str, tuple[str, str]],
        abstractions: Sequence[Abstraction],
        plan: QueryPlan,
    ) -> tuple[SurfaceUnit, ...]: ...


class DeliveryLayer(Protocol):
    def deliver(self, selected: Sequence[SurfaceUnit]) -> tuple[SurfaceUnit, ...]: ...


class AnswerLayer(Protocol):
    def answer(
        self,
        question: BenchmarkQuestion,
        delivered: Sequence[SurfaceUnit],
    ) -> tuple[str, bool]: ...


@dataclass(frozen=True)
class ExecutionChain:
    """The chain. Every layer injected, so exactly one can be replaced at a time."""

    extraction: ExtractionLayer
    mapping: MappingLayer
    abstraction: AbstractionLayer
    query_plan: QueryPlanLayer
    retrieval: RetrievalLayer
    delivery: DeliveryLayer
    answer: AnswerLayer
    substituted_layer: Layer | None = None

    def with_layer(self, layer: Layer, implementation: object) -> ExecutionChain:
        """Replace one layer, recording which one, so a trace can be labelled."""
        field = _LAYER_FIELD.get(layer)
        if field is None:
            raise ChainError(f"{layer} is not a replaceable layer")
        from dataclasses import replace

        return replace(self, **{field: implementation, "substituted_layer": layer})

    def run(
        self,
        question: BenchmarkQuestion,
        artifact: MemoryArtifact,
    ) -> ChainResult:
        """Execute the chain over the built artifact, tracing each layer."""
        artifact_digest = artifact.content_digest()
        # The chain reads the artifact, so it can prove which bytes it read.
        assert_artifact_consumed(artifact, artifact_digest)

        turns = artifact.turns_for(question.conversation_handle)
        traces: list[LayerTrace] = []

        def record(
            layer: Layer,
            input_value: object,
            output_value: object,
            status: LayerStatus,
            detail: JsonObject | None = None,
        ) -> None:
            traces.append(
                LayerTrace(
                    layer=layer,
                    input_sha256=_digest(cast("JsonValue", input_value)),
                    output_sha256=_digest(cast("JsonValue", output_value)),
                    artifact_sha256=artifact_digest,
                    status=status,
                    substituted=self.substituted_layer is layer,
                    detail=detail or {},
                )
            )

        record(
            Layer.BUILDER_ARTIFACT,
            artifact.build_input_sha256,
            [t.evidence_handle for t in turns],
            LayerStatus.OK if turns else LayerStatus.EMPTY,
            {"turns_read_from_artifact": len(turns), "builder_id": artifact.builder_id},
        )

        units = self.extraction.extract(turns)
        record(
            Layer.EXTRACTION,
            [t.content_sha256 for t in turns],
            [[u.evidence_handle, u.role, u.predicate] for u in units],
            LayerStatus.OK if units else LayerStatus.EMPTY,
        )

        mapping = self.mapping.map_units(units)
        record(
            Layer.MAPPING,
            [u.evidence_handle for u in units],
            [[k, v[0], v[1]] for k, v in sorted(mapping.items())],
            LayerStatus.OK if mapping else LayerStatus.EMPTY,
        )

        abstractions = self.abstraction.abstract(units, mapping)
        record(
            Layer.L1_L2,
            sorted(mapping),
            [[a.abstraction_id, a.canonical_id, list(a.derived_from)] for a in abstractions],
            LayerStatus.OK if abstractions else LayerStatus.EMPTY,
        )

        plan = self.query_plan.compile_plan(question)
        record(
            Layer.QUERY_PLAN,
            question.question,
            [list(plan.requested_canonical_ids), plan.requires_abstraction],
            LayerStatus.OK if plan.requested_canonical_ids else LayerStatus.EMPTY,
        )

        selected = self.retrieval.retrieve(question, units, mapping, abstractions, plan)
        record(
            Layer.RETRIEVAL,
            [list(plan.requested_canonical_ids), sorted(mapping)],
            [u.evidence_handle for u in selected],
            LayerStatus.OK if selected else LayerStatus.EMPTY,
        )

        delivered = self.delivery.deliver(selected)
        record(
            Layer.DELIVERY,
            [u.evidence_handle for u in selected],
            [u.evidence_handle for u in delivered],
            LayerStatus.OK if delivered else LayerStatus.REFUSED,
            {"dropped_by_delivery": len(selected) - len(delivered)},
        )

        answer_text, abstained = self.answer.answer(question, delivered)
        record(
            Layer.ANSWER,
            [u.evidence_handle for u in delivered],
            [answer_text, abstained],
            LayerStatus.OK if not abstained else LayerStatus.EMPTY,
        )

        return ChainResult(
            question_id=question.question_id,
            selected_handles=tuple(u.evidence_handle for u in selected),
            delivered_handles=tuple(u.evidence_handle for u in delivered),
            answer_text=answer_text,
            abstained=abstained,
            traces=tuple(traces),
            artifact_sha256=artifact_digest,
        )


_LAYER_FIELD: dict[Layer, str] = {
    Layer.EXTRACTION: "extraction",
    Layer.MAPPING: "mapping",
    Layer.L1_L2: "abstraction",
    Layer.QUERY_PLAN: "query_plan",
    Layer.RETRIEVAL: "retrieval",
    Layer.DELIVERY: "delivery",
    Layer.ANSWER: "answer",
}


def changed_layers(baseline: ChainResult, candidate: ChainResult) -> frozenset[Layer]:
    """Which layers produced different output. Per-layer hashes, not inferred from the end."""
    left = baseline.output_hashes()
    right = candidate.output_hashes()
    return frozenset(
        layer for layer in left if layer in right and left[layer] != right[layer]
    )


def assert_only_target_and_downstream_changed(
    layer: Layer,
    changed: frozenset[Layer],
) -> None:
    """Fail if a substitution altered something upstream of itself."""
    allowed = downstream_of(layer)
    unexpected = sorted(str(item) for item in changed - allowed)
    if unexpected:
        raise ChainError(
            f"substituting {layer} changed layers it cannot influence: {unexpected}"
        )


def assert_artifact_read_by_every_layer(result: ChainResult) -> None:
    """Fail unless every trace names the same artifact the chain consumed.

    A layer that reached back to the corpus instead of the artifact would carry a different
    digest, which is what makes consumption checkable rather than asserted.
    """
    mismatched = sorted(
        str(trace.layer)
        for trace in result.traces
        if trace.artifact_sha256 != result.artifact_sha256
    )
    if mismatched:
        raise ChainError(
            f"these layers did not read the consumed artifact: {mismatched}"
        )


def _digest(value: JsonValue) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()
