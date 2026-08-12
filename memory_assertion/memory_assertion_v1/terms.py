"""The five LeafTerms and the operator application that combines them.

The shape of this module *is* the contract's central prohibition. `LeafTerm` is a
closed union of five leaf shapes and `OperatorApplication` is not one of them, so a
nested application cannot be constructed at all -- there is no runtime check to forget,
and no way to express the thing the contract forbids.

This is the point where memory-assertion/v1 and the older ke_contract_v1 diverge
irreconcilably. There, `OperatorApplication` was recursive and arguments were bound to
roles (`bindings` with `role_id`). Here arguments are positional, roles do not exist,
and propositions are composed through an explicit `assertion_ref` rather than by
nesting. A term graph is therefore always flat, and every composition is a named,
referable thing.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from memory_assertion_v1.ids import ConceptId, OperatorId, RuntimeId
from memory_assertion_v1.literals import CanonicalLiteralValue


class _TermRecord(BaseModel):
    """Frozen and closed, like every record in this contract.

    Frozen because a term carries the identity of an assertion: if it could be mutated,
    "the same KE" would stop meaning anything, and a hash taken over it would describe a
    state that no longer exists. Closed (`extra="forbid"`) because an unrecognised field
    is how a superseded contract's vocabulary -- `role_id`, `polarity`, `modality` --
    would otherwise ride along unnoticed.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")


class IndividualRef(_TermRecord):
    """A reference to an individual, resolved against a scope.

    The scope is not decoration: `local` resolves only within the declarations of the
    current hypothesis, `canonical` only against shared bindings. Resolving one against
    the other's table is what would let a per-request placeholder be mistaken for an
    established entity.
    """

    kind: Literal["individual_ref"] = "individual_ref"
    scope: Literal["local", "canonical"]
    individual_id: RuntimeId


class TypedValue(_TermRecord):
    """A literal, typed by the Concept that gives it meaning.

    `concept_id` is the type identity; the contract deliberately has no separate
    top-level ValueType, so there is one place a type can come from.
    """

    kind: Literal["typed_value"] = "typed_value"
    concept_id: ConceptId
    canonical_value: CanonicalLiteralValue


class AssertionRef(_TermRecord):
    """A reference to another assertion, candidate or canonical.

    This is how propositions compose, in place of nesting. `candidate` resolves within
    the current hypothesis's candidate table, `canonical` against admitted assertions --
    and keeping them apart is what stops a proposal from being read as an admitted fact.
    """

    kind: Literal["assertion_ref"] = "assertion_ref"
    scope: Literal["candidate", "canonical"]
    assertion_id: RuntimeId


class OntologyConceptRef(_TermRecord):
    """A Concept mentioned as a term rather than used as a type."""

    kind: Literal["ontology_concept_ref"] = "ontology_concept_ref"
    concept_id: ConceptId


class OntologyOperatorRef(_TermRecord):
    """An Operator mentioned as a term rather than applied."""

    kind: Literal["ontology_operator_ref"] = "ontology_operator_ref"
    operator_id: OperatorId


LeafTerm = Annotated[
    IndividualRef | TypedValue | AssertionRef | OntologyConceptRef | OntologyOperatorRef,
    Field(discriminator="kind"),
]
"""The five leaf shapes, discriminated by `kind`.

Discriminated rather than a plain union so an unknown `kind` is rejected for being
unknown, rather than reported as five separate failures to match. It also means a
`value_ref` placeholder -- the shipped invalid vector -- fails on its discriminator
instead of needing a rule of its own.
"""


class OperatorApplication(_TermRecord):
    """An operator applied to positional leaf arguments.

    Arguments are positional and each is a `LeafTerm`, so nesting is unrepresentable.
    Their order is the operator's ordered signature; arity and type compatibility are
    checked against a snapshot by the semantic validator, which this layer is not.

    An empty `arguments` list is structurally allowed here because arity belongs to the
    operator's declaration in a snapshot, not to this shape. Rejecting it would put an
    arity rule in the one place that cannot know the arity.
    """

    kind: Literal["operator_application"] = "operator_application"
    operator_id: OperatorId
    arguments: tuple[LeafTerm, ...]
