"""Five-stage diagnostic pipeline where every stage affects the scored result.

The stage order is::

    extraction -> mapping -> l2 -> query_plan -> evidence_selection

Selection consumes the outputs of *all four* upstream stages. That is the correction a
review demanded: previously the L2 abstraction was computed and discarded, so substituting
it with gold changed the trace and left the score identical, which made the oracle
meaningless. Here, a plan may request an abstraction, and selection resolves it through the
L2 output, so better abstraction produces different selected evidence.

Baseline stages are lexical fixtures. Gold stages consume the per-layer artifacts in
:mod:`ke_memory_demo.evaluation.layer_gold`, never the question's final evidence set.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Protocol

from .channels import BenchmarkQuestion, PublicTurn
from .layer_gold import LayerGold

_WORD = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    {
        "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "did", "do",
        "does", "is", "are", "was", "were", "what", "when", "where", "which", "who", "how",
        "why", "my", "i", "me", "you", "it", "that", "this", "about", "before", "after",
        "any", "have", "has", "had", "can", "could", "would", "there", "their",
    }
)


def terms(text: str) -> set[str]:
    return {t for t in _WORD.findall(text.lower()) if t not in _STOPWORDS and len(t) > 2}


@dataclass(frozen=True)
class SurfaceUnit:
    """A unit produced by extraction, carrying whatever role it was assigned."""

    evidence_handle: str
    text: str
    role: str = "unspecified"
    predicate: str = "unspecified"
    approximate_tokens: int = 0


@dataclass(frozen=True)
class Abstraction:
    """An L2 abstraction and the units it derives from."""

    abstraction_id: str
    canonical_id: str
    derived_from: tuple[str, ...]


@dataclass(frozen=True)
class QueryPlan:
    """What a question compiled to.

    ``requested_canonical_ids`` is matched against the mapping output, and
    ``requires_abstraction`` routes selection through the L2 output. Without that second
    field a plan could never depend on abstraction, which is why the L2 oracle previously
    had no effect on anything scored.
    """

    requested_canonical_ids: tuple[str, ...]
    requires_abstraction: bool = False


@dataclass(frozen=True)
class StageTrace:
    """Per-stage output, so a substitution's effect can be located precisely."""

    units: tuple[SurfaceUnit, ...]
    mapping: dict[str, tuple[str, str]]
    abstractions: tuple[Abstraction, ...]
    plan: QueryPlan
    selected: tuple[SurfaceUnit, ...]

    @property
    def unit_handles(self) -> tuple[str, ...]:
        return tuple(u.evidence_handle for u in self.units)

    @property
    def selected_handles(self) -> tuple[str, ...]:
        return tuple(u.evidence_handle for u in self.selected)

    @property
    def abstraction_keys(self) -> tuple[str, ...]:
        return tuple(sorted(a.abstraction_id for a in self.abstractions))


class ExtractionStage(Protocol):
    def extract(self, turns: Sequence[PublicTurn]) -> tuple[SurfaceUnit, ...]: ...


class MappingStage(Protocol):
    def map_units(self, units: Sequence[SurfaceUnit]) -> dict[str, tuple[str, str]]: ...


class L2Stage(Protocol):
    def abstract(
        self,
        units: Sequence[SurfaceUnit],
        mapping: dict[str, tuple[str, str]],
    ) -> tuple[Abstraction, ...]: ...


class QueryPlanStage(Protocol):
    def compile_plan(self, question: BenchmarkQuestion) -> QueryPlan: ...


class SelectionStage(Protocol):
    def select(
        self,
        question: BenchmarkQuestion,
        units: Sequence[SurfaceUnit],
        mapping: dict[str, tuple[str, str]],
        abstractions: Sequence[Abstraction],
        plan: QueryPlan,
    ) -> tuple[SurfaceUnit, ...]: ...


@dataclass(frozen=True)
class DiagnosticPipeline:
    extraction: ExtractionStage
    mapping: MappingStage
    l2: L2Stage
    query_plan: QueryPlanStage
    evidence_selection: SelectionStage

    def run(
        self,
        question: BenchmarkQuestion,
        turns: Sequence[PublicTurn],
    ) -> StageTrace:
        units = self.extraction.extract(turns)
        mapping = self.mapping.map_units(units)
        abstractions = self.l2.abstract(units, mapping)
        plan = self.query_plan.compile_plan(question)
        selected = self.evidence_selection.select(question, units, mapping, abstractions, plan)
        return StageTrace(
            units=units,
            mapping=mapping,
            abstractions=abstractions,
            plan=plan,
            selected=selected,
        )

    def with_stage(self, field: str, stage: object) -> DiagnosticPipeline:
        return replace(self, **{field: stage})


# --------------------------------------------------------------------------------------
# Baseline (fixture) stages. Lexical, gold-free.
# --------------------------------------------------------------------------------------


class FixtureExtraction:
    def extract(self, turns: Sequence[PublicTurn]) -> tuple[SurfaceUnit, ...]:
        return tuple(
            SurfaceUnit(
                evidence_handle=t.evidence_handle,
                text=t.text,
                approximate_tokens=t.approximate_tokens,
            )
            for t in turns
            if t.text.strip()
        )


class FixtureMapping:
    """Map a unit to a canonical id derived from its most distinctive term."""

    def map_units(self, units: Sequence[SurfaceUnit]) -> dict[str, tuple[str, str]]:
        mapped: dict[str, tuple[str, str]] = {}
        for unit in units:
            unit_terms = sorted(terms(unit.text))
            if unit_terms:
                mapped[unit.evidence_handle] = (f"lex:{unit_terms[0]}", "surface")
        return mapped


class FixtureL2:
    """Group units sharing a canonical id into an abstraction."""

    def abstract(
        self,
        units: Sequence[SurfaceUnit],
        mapping: dict[str, tuple[str, str]],
    ) -> tuple[Abstraction, ...]:
        groups: dict[str, list[str]] = {}
        for handle, (canonical_id, _sense) in mapping.items():
            groups.setdefault(canonical_id, []).append(handle)
        return tuple(
            Abstraction(
                abstraction_id=f"abs:{canonical_id}",
                canonical_id=canonical_id,
                derived_from=tuple(sorted(handles)),
            )
            for canonical_id, handles in sorted(groups.items())
            if len(handles) > 1
        )


class FixtureQueryPlan:
    def compile_plan(self, question: BenchmarkQuestion) -> QueryPlan:
        return QueryPlan(
            requested_canonical_ids=tuple(f"lex:{t}" for t in sorted(terms(question.question))),
            requires_abstraction=False,
        )


class FixtureSelection:
    """Select units whose canonical id the plan requested.

    When the plan requires an abstraction, selection resolves it through the L2 output and
    takes the units that abstraction derives from. This is the path that makes the L2 stage
    matter to the score rather than only to the trace.
    """

    def __init__(self, max_units: int = 10) -> None:
        self._max_units = max_units

    def select(
        self,
        question: BenchmarkQuestion,
        units: Sequence[SurfaceUnit],
        mapping: dict[str, tuple[str, str]],
        abstractions: Sequence[Abstraction],
        plan: QueryPlan,
    ) -> tuple[SurfaceUnit, ...]:
        wanted = set(plan.requested_canonical_ids)
        by_handle = {u.evidence_handle: u for u in units}
        chosen: list[SurfaceUnit] = []

        if plan.requires_abstraction:
            for abstraction in abstractions:
                if abstraction.canonical_id in wanted or abstraction.abstraction_id in wanted:
                    for handle in abstraction.derived_from:
                        unit = by_handle.get(handle)
                        if unit is not None and unit not in chosen:
                            chosen.append(unit)

        if not chosen:
            for unit in units:
                entry = mapping.get(unit.evidence_handle)
                if entry is not None and entry[0] in wanted and unit not in chosen:
                    chosen.append(unit)

        return tuple(chosen[: self._max_units])


# --------------------------------------------------------------------------------------
# Gold stages. Each consumes its own layer's gold, never the final evidence set.
# --------------------------------------------------------------------------------------


class GoldExtraction:
    """Produce exactly the surface units extraction gold declares, with their roles."""

    def __init__(self, gold: LayerGold) -> None:
        self._gold = gold

    def extract(self, turns: Sequence[PublicTurn]) -> tuple[SurfaceUnit, ...]:
        by_handle = {t.evidence_handle: t for t in turns}
        produced: list[SurfaceUnit] = []
        for entry in self._gold.extraction:
            turn = by_handle.get(entry.evidence_handle)
            if turn is None:
                continue
            produced.append(
                SurfaceUnit(
                    evidence_handle=entry.evidence_handle,
                    text=turn.text,
                    role=entry.role,
                    predicate=entry.predicate,
                    approximate_tokens=turn.approximate_tokens,
                )
            )
        return tuple(produced)


class GoldMapping:
    """Assign the canonical id and sense mapping gold declares."""

    def __init__(self, gold: LayerGold) -> None:
        self._by_handle = {e.evidence_handle: (e.canonical_id, e.sense) for e in gold.mapping}

    def map_units(self, units: Sequence[SurfaceUnit]) -> dict[str, tuple[str, str]]:
        return {
            u.evidence_handle: self._by_handle[u.evidence_handle]
            for u in units
            if u.evidence_handle in self._by_handle
        }


class GoldL2:
    """Produce the abstractions and derivations L2 gold declares."""

    def __init__(self, gold: LayerGold) -> None:
        self._gold = gold

    def abstract(
        self,
        units: Sequence[SurfaceUnit],
        mapping: dict[str, tuple[str, str]],
    ) -> tuple[Abstraction, ...]:
        present = {u.evidence_handle for u in units}
        return tuple(
            Abstraction(
                abstraction_id=a.abstraction_id,
                canonical_id=a.canonical_id,
                derived_from=tuple(h for h in a.derived_from if h in present),
            )
            for a in self._gold.l2
        )


class GoldQueryPlan:
    """Emit the frozen plan query gold declares."""

    def __init__(self, gold: LayerGold) -> None:
        if gold.query_plan is None:
            raise ValueError("query-plan gold is absent for this question")
        self._plan = gold.query_plan

    def compile_plan(self, question: BenchmarkQuestion) -> QueryPlan:
        return QueryPlan(
            requested_canonical_ids=self._plan.requested_canonical_ids,
            requires_abstraction=self._plan.requires_abstraction,
        )


class GoldSelection:
    """Return exactly the gold evidence set."""

    def __init__(self, evidence_refs: Sequence[str]) -> None:
        self._refs = tuple(evidence_refs)

    def select(
        self,
        question: BenchmarkQuestion,
        units: Sequence[SurfaceUnit],
        mapping: dict[str, tuple[str, str]],
        abstractions: Sequence[Abstraction],
        plan: QueryPlan,
    ) -> tuple[SurfaceUnit, ...]:
        if not self._refs:
            # Gold naming no evidence is the correct answer for an abstention case.
            return ()
        by_handle = {u.evidence_handle: u for u in units}
        resolved: list[SurfaceUnit] = []
        for ref in self._refs:
            unit = by_handle.get(ref)
            if unit is not None and unit not in resolved:
                resolved.append(unit)
        return tuple(resolved)


class PipelineTurnSelector:
    """Adapt a five-stage pipeline to the two-argument selector an arm expects.

    An arm asks a selector for evidence given a question; the pipeline needs a mapping,
    abstractions and a plan first. Running the stages here means the arm and the oracle
    machinery share one implementation instead of two that can drift apart.
    """

    def __init__(self, pipeline: "DiagnosticPipeline") -> None:
        self._pipeline = pipeline

    def select(
        self,
        question: BenchmarkQuestion,
        available: Sequence[PublicTurn],
    ) -> tuple[PublicTurn, ...]:
        selected = self._pipeline.run(question, available).selected
        by_handle = {t.evidence_handle: t for t in available}
        # Stages work on SurfaceUnit; an arm accounts in PublicTurn, so map back by handle.
        return tuple(
            by_handle[u.evidence_handle] for u in selected if u.evidence_handle in by_handle
        )


def baseline_pipeline(max_units: int = 10) -> DiagnosticPipeline:
    return DiagnosticPipeline(
        extraction=FixtureExtraction(),
        mapping=FixtureMapping(),
        l2=FixtureL2(),
        query_plan=FixtureQueryPlan(),
        evidence_selection=FixtureSelection(max_units),
    )
