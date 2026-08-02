"""Concrete layers for the execution chain, and the oracles that replace them.

The layers here are lexical and deliberately modest. What matters is that they are *real layers of
the chain* rather than a fixture standing beside it: they read the builder artifact, they emit
traced output, and an oracle replaces one of them while the others run unchanged. A stronger
backend can be dropped into any single slot without touching the rest.

Each oracle substitutes exactly one layer and needs that layer's own gold. Reusing the question's
final evidence set as a stand-in for extraction or mapping gold injects question relevance, which
is the specific defect an earlier round was rejected for, so ``layer_gold`` supplies each layer
separately and a missing artifact raises rather than silently degrading.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from .channels import BenchmarkQuestion
from .execution_chain import (
    Abstraction,
    ChainError,
    ExecutionChain,
    Layer,
    QueryPlan,
    SurfaceUnit,
)
from .layer_gold import LayerGold
from .memory_artifact import ArtifactTurn

_WORD = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    {
        "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "did", "do",
        "does", "is", "are", "was", "were", "what", "when", "where", "which", "who", "how",
        "why", "my", "i", "me", "you", "it", "that", "this", "about", "any", "have", "has",
        "had", "can", "could", "would", "there", "their", "before", "after",
    }
)


def terms(text: str) -> set[str]:
    return {t for t in _WORD.findall(text.lower()) if t not in _STOPWORDS and len(t) > 2}


# --------------------------------------------------------------------------------------
# Baseline layers. Lexical, gold-free, reading the artifact.
# --------------------------------------------------------------------------------------


class LexicalExtraction:
    def extract(self, turns: Sequence[ArtifactTurn]) -> tuple[SurfaceUnit, ...]:
        return tuple(
            SurfaceUnit(
                evidence_handle=turn.evidence_handle,
                text=turn.text,
                speaker=turn.speaker,
                approximate_tokens=turn.approximate_tokens,
            )
            for turn in turns
            if turn.text.strip()
        )


class LexicalMapping:
    """Map each unit to canonical ids drawn from its content terms.

    Two decisions worth stating, because the first version got both wrong and produced a mapping
    that could never match a plan:

    Numeric tokens are dropped. Taking ``sorted(terms)[0]`` let digits win alphabetically, so
    almost every unit mapped to ``lex:000`` or similar and overlap with any question was empty.

    A unit maps to several ids, not one. A turn discusses more than one thing, and forcing a
    single canonical id per turn makes recall depend on which term happened to sort first.
    """

    def __init__(self, ids_per_unit: int = 8) -> None:
        self._ids_per_unit = ids_per_unit

    def map_units(self, units: Sequence[SurfaceUnit]) -> dict[str, tuple[str, str]]:
        mapped: dict[str, tuple[str, str]] = {}
        for unit in units:
            content = sorted(t for t in terms(unit.text) if not t.isdigit())
            if content:
                # The chain's mapping slot holds one id per handle, so the extra ids ride in the
                # sense field where retrieval can still read them.
                primary = content[0]
                mapped[unit.evidence_handle] = (
                    f"lex:{primary}",
                    "|".join(content[: self._ids_per_unit]),
                )
        return mapped


class LexicalAbstraction:
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


class LexicalQueryPlan:
    def compile_plan(self, question: BenchmarkQuestion) -> QueryPlan:
        return QueryPlan(
            requested_canonical_ids=tuple(f"lex:{t}" for t in sorted(terms(question.question))),
            requires_abstraction=False,
        )


class LexicalRetrieval:
    """Select units whose canonical id the plan asked for, resolving abstractions when asked.

    The abstraction branch is what makes the L1/L2 layer matter to the outcome. Without it, a
    perfect abstraction changes a trace and nothing that is scored.
    """

    def __init__(self, max_units: int = 10) -> None:
        self._max_units = max_units

    def retrieve(
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
            scored: list[tuple[int, int, SurfaceUnit]] = []
            for index, unit in enumerate(units):
                entry = mapping.get(unit.evidence_handle)
                if entry is None:
                    continue
                # A unit's ids are its primary id plus the terms carried in the sense field.
                unit_ids = {entry[0]} | {f"lex:{t}" for t in entry[1].split("|") if t}
                overlap = len(wanted & unit_ids)
                if overlap:
                    scored.append((overlap, -index, unit))
            scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
            chosen = [unit for _score, _order, unit in scored]

        return tuple(chosen[: self._max_units])


class BudgetedDelivery:
    """Drop what does not fit the delivery budget, so selection and delivery stay separable."""

    def __init__(self, budget_tokens: int = 24_576, max_units: int = 64) -> None:
        self._budget_tokens = budget_tokens
        self._max_units = max_units

    def deliver(self, selected: Sequence[SurfaceUnit]) -> tuple[SurfaceUnit, ...]:
        kept: list[SurfaceUnit] = []
        total = 0
        for unit in selected[: self._max_units]:
            if total + unit.approximate_tokens > self._budget_tokens:
                break
            kept.append(unit)
            total += unit.approximate_tokens
        return tuple(kept)


class DeterministicAnswer:
    """Answer from what was delivered, with no model call.

    Nothing derived from this may be reported under a formal answer metric: a stub cannot
    establish correctness, so the chain records the text and leaves correctness unknown.
    """

    def answer(
        self,
        question: BenchmarkQuestion,
        delivered: Sequence[SurfaceUnit],
    ) -> tuple[str, bool]:
        if not delivered:
            return ("There is no information in the provided context.", True)
        return (f"Answer grounded in {len(delivered)} evidence units.", False)


def baseline_chain(
    *,
    delivery_budget_tokens: int = 24_576,
    max_selected_units: int = 10,
) -> ExecutionChain:
    return ExecutionChain(
        extraction=LexicalExtraction(),
        mapping=LexicalMapping(),
        abstraction=LexicalAbstraction(),
        query_plan=LexicalQueryPlan(),
        retrieval=LexicalRetrieval(max_selected_units),
        delivery=BudgetedDelivery(delivery_budget_tokens),
        answer=DeterministicAnswer(),
    )


# --------------------------------------------------------------------------------------
# Oracle layers. Each consumes its own layer's gold, never the final evidence set.
# --------------------------------------------------------------------------------------

# Shared key so a substituted mapping and a substituted plan still speak to each other. Without
# it a perfect layer emits a vocabulary its neighbours cannot read, and appears to make results
# worse, which is an artefact rather than a finding.
GOLD_RELEVANT_KEY = "gold:relevant"


class GoldExtractionLayer:
    def __init__(self, gold: LayerGold) -> None:
        self._gold = gold

    def extract(self, turns: Sequence[ArtifactTurn]) -> tuple[SurfaceUnit, ...]:
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
                    speaker=turn.speaker,
                    approximate_tokens=turn.approximate_tokens,
                    role=entry.role,
                    predicate=entry.predicate,
                )
            )
        return tuple(produced)


class GoldMappingLayer:
    def __init__(self, gold: LayerGold) -> None:
        self._by_handle = {e.evidence_handle: (e.canonical_id, e.sense) for e in gold.mapping}

    def map_units(self, units: Sequence[SurfaceUnit]) -> dict[str, tuple[str, str]]:
        return {
            u.evidence_handle: self._by_handle[u.evidence_handle]
            for u in units
            if u.evidence_handle in self._by_handle
        }


class GoldAbstractionLayer:
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


class GoldQueryPlanLayer:
    def __init__(self, gold: LayerGold) -> None:
        if gold.query_plan is None:
            raise ChainError("query-plan gold is absent for this question")
        self._plan = gold.query_plan

    def compile_plan(self, question: BenchmarkQuestion) -> QueryPlan:
        return QueryPlan(
            requested_canonical_ids=self._plan.requested_canonical_ids,
            requires_abstraction=self._plan.requires_abstraction,
        )


class GoldRetrievalLayer:
    """Return exactly the gold evidence set."""

    def __init__(self, evidence_refs: Sequence[str]) -> None:
        self._refs = tuple(evidence_refs)

    def retrieve(
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


LAYER_FOR_ORACLE: dict[str, Layer] = {
    "gold_extraction": Layer.EXTRACTION,
    "gold_memory_mapping": Layer.MAPPING,
    "gold_l2_abstraction": Layer.L1_L2,
    "gold_query_plan": Layer.QUERY_PLAN,
    "gold_evidence_selection": Layer.RETRIEVAL,
}
