"""Frozen models for independent annotation gold over the natural-expression sample.

This package is the annotation line of a mapping-quality evaluation. Its whole value depends on
one property that no type can enforce and that the shapes here are arranged to make visible:
the labels were decided by reading the expression and the ontology, and *not* by reading a
mapper. So the models carry no score, no candidate list and no confidence number. A field for
"what the mapper returned" would let a later edit quietly turn gold into agreement measurement,
which is the failure mode this line exists to avoid.

Four outcomes, and the fourth is the point:

- :attr:`Outcome.CONCEPT` -- the ontology can represent what the expression attests.
- :attr:`Outcome.AMBIGUOUS` -- two or more items are defensible from the text alone. This is
  not "the annotator was unsure"; it is a claim that the text underdetermines the target, so a
  mapper picking either one is not wrong.
- :attr:`Outcome.NONE` -- nothing with propositional memory value: backchannel, pleasantry,
  meta-conversation about the assistant.
- :attr:`Outcome.OUT_OF_SCOPE` -- the expression attests something real and memory-worthy that
  ontology v2 cannot express. ``would_require`` is mandatory here, because an out-of-scope
  label without a stated requirement is indistinguishable from an annotator giving up, and it
  is this field that measures the ontology ceiling rather than the mapper's recall.

``target_ids`` is required for the two label kinds that name items and forbidden for the two
that do not. Allowing an empty concept label would admit "something maps here, unspecified",
which scores as coverage while committing to nothing.
"""

from __future__ import annotations

import hashlib
from enum import StrEnum
from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ke_memory_demo.core.json import canonical_json

NonEmptyString = Annotated[str, Field(min_length=1)]

L1_NAMESPACE: Final[str] = "l1:"
L2_NAMESPACE: Final[str] = "l2:"


class AnnotationError(ValueError):
    """An annotation record was built with content it must not carry."""


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Outcome(StrEnum):
    CONCEPT = "concept"
    AMBIGUOUS = "ambiguous"
    NONE = "none"
    OUT_OF_SCOPE = "out_of_scope"


# The outcomes that name ontology items. Kept as a set so the record validator and the test
# suite agree about which labels are id-bearing without restating the rule in two places.
ID_BEARING: Final[frozenset[Outcome]] = frozenset({Outcome.CONCEPT, Outcome.AMBIGUOUS})


class AnnotationRecord(_Frozen):
    """One expression's label, decided from the text and the ontology alone.

    ``needs_second_opinion`` implements the graded review the effort budget requires: novel
    cases, genuine ambiguity, L2 abstractions and anything the annotator found hard are
    flagged and carry an adjudication note. The clear ones are labelled once and left alone,
    so the flag is a triage record and not a confidence score.
    """

    expression_id: NonEmptyString
    outcome: Outcome
    # Why the ids are a tuple even for a single concept: an expression can attest several types
    # at once ("I bought three dogs a bed") and collapsing that to one id would score a mapper
    # as wrong for finding the rest.
    target_ids: tuple[NonEmptyString, ...] = ()
    sense: Annotated[str, Field(min_length=12)]
    needs_second_opinion: bool = False
    adjudication_note: str = ""
    would_require: str = ""

    @model_validator(mode="after")
    def _validate(self) -> AnnotationRecord:
        if self.outcome in ID_BEARING:
            if not self.target_ids:
                raise AnnotationError(
                    f"{self.expression_id} is labelled {self.outcome.value} but names no target; "
                    "an id-less concept label counts as coverage while committing to nothing"
                )
            for target in self.target_ids:
                if not target.startswith((L1_NAMESPACE, L2_NAMESPACE)):
                    raise AnnotationError(
                        f"{self.expression_id} names {target!r}, which is in neither layer's "
                        "namespace; a label must be checkable against a frozen unit"
                    )
            if len(set(self.target_ids)) != len(self.target_ids):
                raise AnnotationError(f"{self.expression_id} repeats a target id")
            if self.target_ids != tuple(sorted(self.target_ids)):
                raise AnnotationError(
                    f"{self.expression_id} lists targets out of order; sorting keeps the gold "
                    "hash independent of the order the annotator happened to think of them"
                )
        elif self.target_ids:
            raise AnnotationError(
                f"{self.expression_id} is labelled {self.outcome.value} but names "
                f"{len(self.target_ids)} target(s); only concept and ambiguous may point at items"
            )
        # An ambiguity between one item is a concept label wearing a hedge, and it would let the
        # annotator avoid committing while still being scored as having found something.
        if self.outcome is Outcome.AMBIGUOUS and len(self.target_ids) < 2:
            raise AnnotationError(
                f"{self.expression_id} is ambiguous between {len(self.target_ids)} item; "
                "ambiguity means the text underdetermines the choice between two or more"
            )
        if self.outcome is Outcome.OUT_OF_SCOPE:
            if len(self.would_require) < 20:
                raise AnnotationError(
                    f"{self.expression_id} is out of scope but does not say what would be "
                    "required; an unstated requirement is indistinguishable from giving up, and "
                    "this field is what measures the ontology ceiling"
                )
        elif self.would_require:
            raise AnnotationError(
                f"{self.expression_id} states a requirement but is not out of scope; only a "
                "coverage gap names what the ontology lacks"
            )
        if self.needs_second_opinion and len(self.adjudication_note) < 20:
            raise AnnotationError(
                f"{self.expression_id} is flagged for a second opinion with no adjudication "
                "note, so a reviewer would not know what to adjudicate"
            )
        if self.adjudication_note and not self.needs_second_opinion:
            raise AnnotationError(
                f"{self.expression_id} carries an adjudication note but is not flagged; a note "
                "on an unflagged record would never be read"
            )
        return self


class AnnotationGold(_Frozen):
    """Every label, bound to the sample digest the annotator actually read.

    ``sample_sha256`` is not decoration. The sample was frozen before any mapper existed, and a
    gold set that does not name the digest it annotated could have been produced against a
    re-drawn sample -- which is exactly the re-freeze this evaluation design forbids.
    """

    artifact: Literal["natural-expression annotation gold"] = (
        "natural-expression annotation gold"
    )
    sample_sha256: NonEmptyString
    annotated_against_ontology: NonEmptyString
    judge: Literal["not called"] = "not called"
    model_api_calls: Literal[0] = 0
    records: tuple[AnnotationRecord, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate(self) -> AnnotationGold:
        ids = [record.expression_id for record in self.records]
        if len(set(ids)) != len(ids):
            raise AnnotationError("an expression is labelled twice")
        if ids != sorted(ids):
            raise AnnotationError(
                "records must be sorted by expression id so the digest is stable"
            )
        return self

    @property
    def digest(self) -> str:
        """SHA-256 over the canonical gold, so any label change moves the hash."""
        return hashlib.sha256(canonical_json(self)).hexdigest()

    def counts_by_outcome(self) -> dict[str, int]:
        counts = {outcome.value: 0 for outcome in Outcome}
        for record in self.records:
            counts[record.outcome.value] += 1
        return counts

    def second_opinion_count(self) -> int:
        return sum(1 for record in self.records if record.needs_second_opinion)

    def named_ids(self) -> frozenset[str]:
        return frozenset(t for record in self.records for t in record.target_ids)

    def expression_ids(self) -> frozenset[str]:
        return frozenset(record.expression_id for record in self.records)

    def gaps(self) -> tuple[AnnotationRecord, ...]:
        return tuple(r for r in self.records if r.outcome is Outcome.OUT_OF_SCOPE)
