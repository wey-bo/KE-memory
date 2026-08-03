"""Frozen models for the v3 annotation gold over the fresh 160-expression mapping set.

The round this package serves measures mapper v3 against ontology v2 *plus* the v3 additions, so
the only thing that changes structurally from the previous round is which id inventory a label may
name. Everything else is deliberately identical in spirit: no score, no candidate list, no
confidence number, and no field in which "what the mapper returned" could be recorded. A gold set
that can hold a mapper's answer stops being gold the first time someone fills that field in.

Four outcomes:

- :attr:`Outcome.CONCEPT` -- the combined ontology can represent what the expression attests.
  ``target_ids`` lists *every* applicable item, not the most salient one, because an utterance
  normally attests several things at once and collapsing that to one id scores a mapper as wrong
  for finding the rest.
- :attr:`Outcome.AMBIGUOUS` -- two or more items are defensible from the text alone. A claim about
  the text underdetermining the target, not a record of annotator hesitation.
- :attr:`Outcome.NONE` -- nothing with propositional memory value: backchannel, pleasantry,
  meta-talk about the assistant.
- :attr:`Outcome.OUT_OF_SCOPE` -- something real and memory-worthy that v2 *and* v3 together
  cannot express. ``would_require`` is mandatory, since an out-of-scope label with no stated
  requirement is indistinguishable from giving up, and this field is what measures the ceiling of
  the combined ontology rather than the mapper's recall.

``absorbed_by_v3`` is the one field this round adds. v3 exists to close four families that v2
could not express, so the gold has to say which labels rest on a v3 item; otherwise "v3 helped"
would be an inference from id prefixes at scoring time rather than a claim the annotator made.
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

# The five L1 items and two L2 items ontology v3 adds on top of the frozen v2 base. Held here so
# ``absorbed_by_v3`` is checkable against the actual addition set rather than against a hand
# maintained list of prefixes that would drift from the artifact.
V3_ADDED_IDS: Final[frozenset[str]] = frozenset(
    {
        "l1:event.activity_occurrence",
        "l1:predicate.hold_belief",
        "l1:predicate.hold_value",
        "l1:state.capability",
        "l1:state.ongoing_pursuit",
        "l2:abstraction.pursuit_profile",
        "l2:abstraction.value_commitment",
    }
)


class AnnotationError(ValueError):
    """An annotation record was built with content it must not carry."""


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Outcome(StrEnum):
    CONCEPT = "concept"
    AMBIGUOUS = "ambiguous"
    NONE = "none"
    OUT_OF_SCOPE = "out_of_scope"


# The outcomes that name ontology items, kept as a set so the record validator and the tests agree
# about which labels are id-bearing without restating the rule twice.
ID_BEARING: Final[frozenset[Outcome]] = frozenset({Outcome.CONCEPT, Outcome.AMBIGUOUS})


class AnnotationRecord(_Frozen):
    """One expression's label, decided from the text and the two ontology units alone.

    ``needs_second_opinion`` implements graded review: novel cases, genuine ambiguity, L2
    abstractions, multi-target labels and anything the annotator found hard are flagged and carry
    an adjudication note. Clear cases are labelled once and left alone, so the flag is a triage
    record rather than a confidence score.
    """

    expression_id: NonEmptyString
    outcome: Outcome
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
        # An ambiguity between one item is a concept label wearing a hedge: it would let the
        # annotator avoid committing while still scoring as having found something.
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
                    "this field is what measures the ceiling of v2 and v3 together"
                )
        elif self.would_require:
            raise AnnotationError(
                f"{self.expression_id} states a requirement but is not out of scope; only a "
                "coverage gap names what the combined ontology lacks"
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

    @property
    def absorbed_by_v3(self) -> tuple[str, ...]:
        """The v3 additions this label rests on, which v2 alone could not have expressed."""
        return tuple(t for t in self.target_ids if t in V3_ADDED_IDS)

    @property
    def is_multi_target(self) -> bool:
        return len(self.target_ids) > 1


class AnnotationGold(_Frozen):
    """Every label, bound to the digest of the set the annotator actually read.

    ``annotated_set_sha256`` is load-bearing. The fresh set was frozen before mapper v3 existed,
    and a gold set that does not name the digest it annotated could have been produced against a
    re-drawn set, which is exactly the re-freeze this evaluation design forbids.
    """

    artifact: Literal["fresh-mapping-set annotation gold"] = "fresh-mapping-set annotation gold"
    annotated_set_sha256: NonEmptyString
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

    def multi_target_records(self) -> tuple[AnnotationRecord, ...]:
        return tuple(r for r in self.records if r.is_multi_target)

    def targets_per_expression(self) -> dict[str, int]:
        """How many expressions carry 0, 1, 2, ... targets, keyed by count as a string.

        String keys because this goes straight into JSON, where an integer key would be coerced
        anyway and the coercion is better done where it can be seen.
        """
        distribution: dict[str, int] = {}
        for record in self.records:
            key = str(len(record.target_ids))
            distribution[key] = distribution.get(key, 0) + 1
        return dict(sorted(distribution.items(), key=lambda pair: int(pair[0])))

    def v3_absorbed_records(self) -> tuple[AnnotationRecord, ...]:
        """Labels that would have been unexpressible, or thinner, without the v3 additions."""
        return tuple(r for r in self.records if r.absorbed_by_v3)

    def v3_absorption_by_item(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for record in self.records:
            for target in record.absorbed_by_v3:
                counts[target] = counts.get(target, 0) + 1
        return dict(sorted(counts.items()))
