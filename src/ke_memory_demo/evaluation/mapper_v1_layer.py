"""Adapter installing mapper v1 into the chain's mapping slot.

The chain's mapping layer returns ``{handle: (canonical_id, sense)}``. Mapper v1 returns ranked
candidates with confidences, an ambiguity verdict and an unresolved status, which is strictly more
information. The adapter is the narrow place where that richer output is reduced to what the slot
accepts, and the reduction is recorded rather than hidden:

- an unresolved mapping contributes no entry, so the chain sees a genuine absence instead of a
  guess
- an ambiguous mapping still contributes its top candidate, because dropping it would silently
  convert ambiguity into missing data, but the alternatives ride in the sense field where the trace
  preserves them

Nothing here corrects a mapping. The adapter changes representation, not content.
"""

from __future__ import annotations

from collections.abc import Sequence

from ke_memory_demo.mapper_v1.mapper import (
    Layer as MapperLayer,
)
from ke_memory_demo.mapper_v1.mapper import (
    MapperInput,
    MapperV1,
    MappingRecord,
    Resolution,
)

from .channels import BenchmarkQuestion
from .execution_chain import QueryPlan, SurfaceUnit


class MapperV1MappingLayer:
    """The chain's mapping layer, backed by mapper v1 over the frozen ontology."""

    def __init__(self, mapper: MapperV1, *, layer: MapperLayer = MapperLayer.L1) -> None:
        self._mapper = mapper
        self._layer = layer
        self._last_records: tuple[MappingRecord, ...] = ()

    @property
    def last_records(self) -> tuple[MappingRecord, ...]:
        """The raw records from the most recent call, kept for reporting.

        The chain's slot cannot carry confidences or alternatives, so the unreduced output is
        retained here instead of being discarded at the boundary.
        """
        return self._last_records

    def resolution_counts(self) -> dict[str, int]:
        counts = {resolution.value: 0 for resolution in Resolution}
        for record in self._last_records:
            counts[record.resolution.value] += 1
        return counts

    def map_units(self, units: Sequence[SurfaceUnit]) -> dict[str, tuple[str, str]]:
        mapped: dict[str, tuple[str, str]] = {}
        records: list[MappingRecord] = []

        for index, unit in enumerate(units):
            # The mapper must not receive a handle that could disclose dataset identity, so the
            # expression id is a positional token rather than the evidence handle.
            record = self._mapper.map_expression(
                MapperInput(
                    expression_id=f"expr-{index:06d}",
                    speaker=unit.speaker or "unknown",
                    text=unit.text,
                ),
                self._layer,
            )
            records.append(record)
            if record.resolution is Resolution.UNRESOLVED:
                continue
            # Alternatives travel in the sense field: the slot holds one id, and discarding the
            # competing readings would make an ambiguous mapping indistinguishable from a confident
            # one.
            alternatives = "|".join(
                candidate.ontology_id for candidate in record.candidates[1:]
            )
            sense = record.top_sense or ""
            if alternatives:
                sense = f"{sense}#alt={alternatives}" if sense else f"#alt={alternatives}"
            mapped[unit.evidence_handle] = (record.top_ontology_id, sense)

        self._last_records = tuple(records)
        return mapped

class MapperV1QueryPlanLayer:
    """Compile a question through the same mapper, so plan and mapping share a vocabulary.

    Installing mapper v1 in the mapping slot alone drove selection to zero, and the cause was not the
    mapper: the planner still emitted ``lex:*`` terms while the mapper emitted ``l1:*`` ontology ids,
    so the two could never intersect. A mapper is only usable if the query side speaks the same
    vocabulary, which is why this layer exists rather than a translation shim.

    The question is an expression like any other here. It is passed as text with an opaque id, so the
    planner gains no access to gold, split or dataset identity.
    """

    def __init__(self, mapper: MapperV1, *, layer: MapperLayer = MapperLayer.L1) -> None:
        self._mapper = mapper
        self._layer = layer
        self._last_record: MappingRecord | None = None

    @property
    def last_record(self) -> MappingRecord | None:
        return self._last_record

    def compile_plan(self, question: BenchmarkQuestion) -> QueryPlan:
        record = self._mapper.map_expression(
            MapperInput(
                expression_id="expr-question",
                speaker="user",
                text=question.question,
            ),
            self._layer,
        )
        self._last_record = record
        if record.resolution is Resolution.UNRESOLVED:
            # An unsupported question is reported as an empty plan rather than guessed at, so the
            # executor's inability is visible instead of being converted into a wrong answer.
            return QueryPlan(requested_canonical_ids=(), requires_abstraction=False)
        # Every candidate is requested, not only the top one: a question legitimately touches
        # several ontology items, and narrowing to one here would discard recall the mapper found.
        return QueryPlan(
            requested_canonical_ids=tuple(
                candidate.ontology_id for candidate in record.candidates
            ),
            requires_abstraction=False,
        )



