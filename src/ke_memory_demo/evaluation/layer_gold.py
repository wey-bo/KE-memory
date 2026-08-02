"""Per-layer gold artifacts for oracle substitution.

A review rejected the previous oracles for a precise reason: four of the five derived
their "gold" from the question's final evidence references. Filtering input by the answer's
evidence set is not extraction gold, and tagging those same units is not mapping gold —
both inject question relevance, which is the thing the pipeline is supposed to compute.
The L2 oracle was worse than incomplete: its abstraction was calculated and then never
consumed, so substituting it changed the trace and nothing that was scored.

Each layer therefore needs its own independently authored gold:

- ``extraction``: which surface units exist, with their roles
- ``mapping``: surface unit to canonical ontology id and sense
- ``l2``: abstractions with their derivations, which selection must consult
- ``query_plan``: a frozen QuerySlotPlan
- ``evidence_selection``: the gold evidence set

The 32-item regression slice carries none of the first four. So they are exercised on
synthetic fixtures, where the annotation can be authored honestly, and the slice run
reports only ``gold_evidence_selection``. Reinterpreting evidence refs as four kinds of
gold is what the review refused, and inventing the annotation would repeat it.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

NonEmptyString = Annotated[str, Field(min_length=1)]


class LayerGoldError(ValueError):
    """A layer-gold artifact is missing or malformed."""


class _Record(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ExtractionGoldUnit(_Record):
    """One surface unit L1 extraction should produce, with its role."""

    evidence_handle: NonEmptyString
    role: NonEmptyString
    predicate: NonEmptyString


class MappingGoldEntry(_Record):
    """The canonical ontology item and sense a surface unit should map to."""

    evidence_handle: NonEmptyString
    canonical_id: NonEmptyString
    sense: NonEmptyString


class L2GoldAbstraction(_Record):
    """A cross-unit abstraction with the units it derives from."""

    abstraction_id: NonEmptyString
    canonical_id: NonEmptyString
    derived_from: tuple[str, ...]

    @property
    def is_supported(self) -> bool:
        return bool(self.derived_from)


class QueryPlanGold(_Record):
    """A frozen plan: the canonical ids a correct compilation should request."""

    question_id: NonEmptyString
    requested_canonical_ids: tuple[str, ...]
    requires_abstraction: bool = False


class LayerGold(_Record):
    """All per-layer gold for one question, authored independently of the others.

    The validator enforces internal closure. A review found that a plan could name a
    different question, and that mapping or L2 could reference an evidence handle no
    extraction gold produced; both are silent inconsistencies that make an oracle score
    something other than what it claims.
    """

    question_id: NonEmptyString
    extraction: tuple[ExtractionGoldUnit, ...] = ()
    mapping: tuple[MappingGoldEntry, ...] = ()
    l2: tuple[L2GoldAbstraction, ...] = ()
    query_plan: QueryPlanGold | None = None

    @model_validator(mode="after")
    def _validate_closure(self) -> LayerGold:
        if self.query_plan is not None and self.query_plan.question_id != self.question_id:
            raise LayerGoldError(
                f"query-plan gold names question {self.query_plan.question_id!r} but this "
                f"bundle is for {self.question_id!r}"
            )

        extracted = {unit.evidence_handle for unit in self.extraction}
        if extracted:
            dangling_mapping = sorted(
                {e.evidence_handle for e in self.mapping} - extracted
            )
            if dangling_mapping:
                raise LayerGoldError(
                    f"mapping gold for {self.question_id} references handles no extraction "
                    f"gold produces: {dangling_mapping[:5]}"
                )
            dangling_l2 = sorted(
                {h for a in self.l2 for h in a.derived_from} - extracted
            )
            if dangling_l2:
                raise LayerGoldError(
                    f"L2 gold for {self.question_id} derives from handles no extraction gold "
                    f"produces: {dangling_l2[:5]}"
                )

        mapped_ids = {entry.canonical_id for entry in self.mapping}
        abstraction_ids = {a.canonical_id for a in self.l2} | {
            a.abstraction_id for a in self.l2
        }
        if self.query_plan is not None and (mapped_ids or abstraction_ids):
            unknown = sorted(
                set(self.query_plan.requested_canonical_ids) - mapped_ids - abstraction_ids
            )
            if unknown:
                raise LayerGoldError(
                    f"query-plan gold for {self.question_id} requests canonical ids that "
                    f"neither mapping nor L2 gold can supply: {unknown[:5]}"
                )
        if self.l2 and any(not a.derived_from for a in self.l2):
            raise LayerGoldError(
                f"L2 gold for {self.question_id} contains an abstraction with no derivation"
            )
        return self

    def has(self, layer: str) -> bool:
        if layer == "extraction":
            return bool(self.extraction)
        if layer == "mapping":
            return bool(self.mapping)
        if layer == "l2":
            return bool(self.l2)
        if layer == "query_plan":
            return self.query_plan is not None
        return False


class LayerGoldBundle(_Record):
    """Per-layer gold across a fixture set."""

    fixture_id: NonEmptyString
    entries: tuple[LayerGold, ...]

    def for_question(self, question_id: str) -> LayerGold | None:
        for entry in self.entries:
            if entry.question_id == question_id:
                return entry
        return None

    def covers(self, layer: str) -> bool:
        """Whether every entry carries gold for this layer.

        An oracle may only be reported for a layer this returns true for. Partial coverage
        would mean some questions silently fall back to the baseline stage while the run
        still claims the layer was substituted.
        """
        return bool(self.entries) and all(entry.has(layer) for entry in self.entries)
