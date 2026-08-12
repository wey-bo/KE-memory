"""Identifier types for the memory-assertion/v1 structural contract.

Three distinct id shapes, kept as distinct types because the contract treats them as
distinct. Ontology ids are content-addressed hashes assigned upstream and are never
minted here; runtime ids name things that exist only within one request or one
memory system.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

CONCEPT_ID_PATTERN = r"^concept_[a-f0-9]{12}$"
OPERATOR_ID_PATTERN = r"^operator_[a-f0-9]{12}$"
RUNTIME_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$"

ConceptId = Annotated[str, Field(pattern=CONCEPT_ID_PATTERN)]
"""An upstream Concept hash id.

Deliberately not a free string: `canonical_name` is a Canonical Symbol, not an
identity, and accepting `Person` where `concept_72c9781aa03b` belongs is the confusion
the hash ids exist to prevent.
"""

OperatorId = Annotated[str, Field(pattern=OPERATOR_ID_PATTERN)]
"""An upstream Operator hash id. Same reasoning as :data:`ConceptId`."""

RuntimeId = Annotated[str, Field(pattern=RUNTIME_ID_PATTERN, min_length=1, max_length=255)]
"""An individual or assertion id resolved against a scope rather than an ontology.

The pattern requires a leading alphanumeric, so a leading separator cannot produce
ids that differ only by punctuation.
"""
