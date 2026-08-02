"""Preregistered data boundaries for corpus-driven discovery.

The 32-item slice is retired as a test set: it has already been used for oracle validation
and regression, so any result on it is contaminated by construction. Discovery therefore
needs three disjoint splits, and the split rule has to be fixed before anyone looks at
results — otherwise the held-out set quietly becomes a tuning set.

The rule here is deterministic and auditable: questions are ordered by a hash of their id,
then partitioned. Nothing depends on file order or on anything a later change could perturb,
and the same corpus always produces the same split.

- ``discovery``: find problems, generate ontology candidates
- ``validation``: accept, modify or reject candidates
- ``held_out``: untouched until the ontology is frozen

Every item appearing in the retired slice is excluded from all three, so a candidate cannot
be validated on data the harness already trained its own fixtures against.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from enum import StrEnum
from typing import Annotated, Final

from pydantic import BaseModel, ConfigDict, Field, model_validator

NonEmptyString = Annotated[str, Field(min_length=1)]

# Fixed once. Changing it reshuffles every split, which would invalidate any prior discovery,
# so it is recorded in the artifact and treated as part of the frozen contract.
SPLIT_SALT: Final[str] = "ke-memory-discovery-v1"

DISCOVERY_FRACTION: Final[float] = 0.50
VALIDATION_FRACTION: Final[float] = 0.20
# The remainder is held out. Stated as a remainder rather than a third fraction so the three
# can never sum to something other than one.


class SplitError(ValueError):
    """A split was requested or constructed incorrectly."""


class Split(StrEnum):
    DISCOVERY = "discovery"
    VALIDATION = "validation"
    HELD_OUT = "held_out"


class SplitAssignment(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    question_id: NonEmptyString
    split: Split
    rank: int


class SplitPlan(BaseModel):
    """A reproducible partition, plus the exclusions that made it necessary."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    corpus_id: NonEmptyString
    salt: NonEmptyString
    excluded_question_ids: tuple[str, ...]
    assignments: tuple[SplitAssignment, ...]

    @model_validator(mode="after")
    def _validate_disjoint(self) -> SplitPlan:
        ids = [a.question_id for a in self.assignments]
        if len(ids) != len(set(ids)):
            raise SplitError("a question was assigned to more than one split")
        overlap = sorted(set(ids) & set(self.excluded_question_ids))
        if overlap:
            raise SplitError(
                f"excluded questions appear in a split: {overlap[:5]}; the retired slice "
                "must not reach discovery, validation or held-out data"
            )
        return self

    def ids_for(self, split: Split) -> tuple[str, ...]:
        return tuple(a.question_id for a in self.assignments if a.split is split)

    def summary(self) -> dict[str, object]:
        return {
            "corpus_id": self.corpus_id,
            "salt": self.salt,
            "excluded_count": len(self.excluded_question_ids),
            "counts": {
                str(split): len(self.ids_for(split)) for split in Split
            },
            "disjoint": True,
            "rule": (
                "questions are ranked by sha256(salt + question_id) and partitioned, so the "
                "split is reproducible and independent of file order"
            ),
        }


def _rank_key(salt: str, question_id: str) -> str:
    return hashlib.sha256(f"{salt}:{question_id}".encode()).hexdigest()


def plan_splits(
    corpus_id: str,
    question_ids: Sequence[str],
    *,
    excluded_question_ids: Sequence[str] = (),
    salt: str = SPLIT_SALT,
    discovery_fraction: float = DISCOVERY_FRACTION,
    validation_fraction: float = VALIDATION_FRACTION,
) -> SplitPlan:
    """Partition a corpus deterministically, excluding anything already used."""
    if not 0 < discovery_fraction < 1 or not 0 < validation_fraction < 1:
        raise SplitError("fractions must lie strictly between zero and one")
    if discovery_fraction + validation_fraction >= 1:
        raise SplitError("discovery and validation must leave a non-empty held-out set")

    excluded = set(excluded_question_ids)
    eligible = sorted({q for q in question_ids if q and q not in excluded})
    if not eligible:
        raise SplitError("no eligible questions remain after exclusions")

    ordered = sorted(eligible, key=lambda q: _rank_key(salt, q))
    discovery_end = int(len(ordered) * discovery_fraction)
    validation_end = discovery_end + int(len(ordered) * validation_fraction)
    if validation_end >= len(ordered):
        raise SplitError("the partition left no held-out questions")

    assignments: list[SplitAssignment] = []
    for rank, question_id in enumerate(ordered):
        if rank < discovery_end:
            split = Split.DISCOVERY
        elif rank < validation_end:
            split = Split.VALIDATION
        else:
            split = Split.HELD_OUT
        assignments.append(
            SplitAssignment(question_id=question_id, split=split, rank=rank)
        )

    return SplitPlan(
        corpus_id=corpus_id,
        salt=salt,
        excluded_question_ids=tuple(sorted(excluded)),
        assignments=tuple(assignments),
    )


def assert_held_out_untouched(
    plan: SplitPlan,
    inspected_question_ids: Sequence[str],
) -> None:
    """Fail if anything from the held-out set has been looked at.

    Called wherever discovery reports results. Without a mechanical check, "we did not look at
    held-out data" is an assertion about intent rather than a property of the run.
    """
    held_out = set(plan.ids_for(Split.HELD_OUT))
    touched = sorted(held_out & set(inspected_question_ids))
    if touched:
        raise SplitError(
            f"held-out questions were inspected: {touched[:5]}; the held-out set is "
            "unusable for a final result once it has informed any decision"
        )
