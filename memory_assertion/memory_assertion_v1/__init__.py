"""Structural models for the memory-assertion/v1 semantic contract.

The authoritative contract is the specification package at `spec/memory-assertion-v1/`;
this package is its first runtime implementation. It covers **structural** validation
only: a document that constructs cleanly here is well-formed under the closed grammar of
five LeafTerms and one equation shape.

What that explicitly does not establish:

- **Reference resolution.** Whether a `concept_id` or `operator_id` exists in a given
  OntologySnapshot, and whether a scoped individual or assertion id resolves in its
  table, is unchecked here.
- **Type compatibility.** Matching arguments against an operator's ordered signature
  needs the Concept inheritance DAG and its disjointness constraints, which live in a
  snapshot. The specification says so directly: this cannot be decided from the schema
  alone.
- **Arity.** An operator's argument count is declared in a snapshot, not in this shape.
- **Truth, admission, lifecycle, conflict.** All outside this contract entirely.

So "structural validation implemented" is the claim this package supports, and no more.
A semantic validator, a production Canonical Text parser, a snapshot provisioner and an
NL2KE compiler remain unimplemented; the deliberately empty space where they would go is
not a placeholder for them.

This package depends on pydantic and nothing else in this repository. The dependency
runs one way on purpose: a contract that imported the runtime it constrains could not
also be the thing the runtime is migrated toward.
"""

from __future__ import annotations

from memory_assertion_v1.equation import KnowledgeEquation
from memory_assertion_v1.errors import StructuralContractError
from memory_assertion_v1.ids import ConceptId, OperatorId, RuntimeId
from memory_assertion_v1.literals import CanonicalLiteralValue, MoneyValue, QuantityValue
from memory_assertion_v1.terms import (
    AssertionRef,
    IndividualRef,
    LeafTerm,
    OntologyConceptRef,
    OntologyOperatorRef,
    OperatorApplication,
    TypedValue,
)

SEMANTIC_CONTRACT_VERSION = "memory-assertion/v1"

__all__ = [
    "SEMANTIC_CONTRACT_VERSION",
    "AssertionRef",
    "CanonicalLiteralValue",
    "ConceptId",
    "IndividualRef",
    "KnowledgeEquation",
    "LeafTerm",
    "MoneyValue",
    "OntologyConceptRef",
    "OntologyOperatorRef",
    "OperatorApplication",
    "OperatorId",
    "QuantityValue",
    "RuntimeId",
    "StructuralContractError",
    "TypedValue",
]
