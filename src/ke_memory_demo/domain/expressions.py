from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


NonEmptyString = Annotated[str, Field(min_length=1)]


class _ExpressionRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ConceptRef(_ExpressionRecord):
    kind: Literal["concept"] = "concept"
    term_id: NonEmptyString
    label: NonEmptyString


class IndividualRef(_ExpressionRecord):
    kind: Literal["individual"] = "individual"
    term_id: NonEmptyString
    label: NonEmptyString


class OperatorRef(_ExpressionRecord):
    kind: Literal["operator"] = "operator"
    term_id: NonEmptyString
    label: NonEmptyString


class AssertionRef(_ExpressionRecord):
    kind: Literal["assertion"] = "assertion"
    assertion_id: NonEmptyString


class OperatorApplication(_ExpressionRecord):
    kind: Literal["application"] = "application"
    operator: OperatorRef
    arguments: tuple[Expression, ...]


type AtomicExpression = Annotated[
    ConceptRef | IndividualRef | OperatorRef | AssertionRef,
    Field(discriminator="kind"),
]

type Expression = Annotated[
    ConceptRef | IndividualRef | OperatorRef | AssertionRef | OperatorApplication,
    Field(discriminator="kind"),
]


OperatorApplication.model_rebuild()
