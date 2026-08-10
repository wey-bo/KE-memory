"""Upstream Ontology, Concept and Operator records.

These fields belong to the upstream Ontology Storage Specification. This profile does
not reinterpret any of them; it only requires that the ids match the upstream hash form
and that `canonical_name` satisfies the Canonical Symbol shape, which is a constraint on
an existing field rather than a second parallel one.

`supply` stays a plain mapping. Sibling namespaces are opaque to this profile -- but not
outside the hash: they travel with their shard into the canonical bytes, so a consumer
cannot drop or rewrite them and still claim the same `snapshot_id + sha256`. Keeping
them as raw values here is what preserves them.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from memory_assertion_v1.ids import ConceptId, OperatorId

CONCEPT_SYMBOL_PATTERN = r"^[A-Z][A-Za-z0-9]*$"
OPERATOR_SYMBOL_PATTERN = r"^[a-z][a-z0-9_]*$"
ONTOLOGY_ID_PATTERN = r"^ontology_[a-f0-9]{12}$"

OntologyId = Annotated[str, Field(pattern=ONTOLOGY_ID_PATTERN)]
ConceptSymbol = Annotated[str, Field(pattern=CONCEPT_SYMBOL_PATTERN)]
OperatorSymbol = Annotated[str, Field(pattern=OPERATOR_SYMBOL_PATTERN)]
NonEmptyString = Annotated[str, Field(min_length=1)]

ArtifactKind = Literal["ontology", "concepts", "operators"]


class _UpstreamRecord(BaseModel):
    """Frozen, and closed against unknown *top-level* fields.

    Closed at the top level because upstream fixes that set. Extension goes under
    `supply`, which is why that one field is an open mapping while its siblings are not.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")


class OntologyRecord(_UpstreamRecord):
    id: OntologyId
    canonical_name: ConceptSymbol
    description: NonEmptyString
    sources: tuple[NonEmptyString, ...]
    created_at: NonEmptyString
    version: NonEmptyString
    supply: dict[str, Any] = Field(default_factory=dict)


class ConceptRecord(_UpstreamRecord):
    id: ConceptId
    canonical_name: ConceptSymbol
    description: NonEmptyString
    sources: tuple[NonEmptyString, ...]
    created_at: NonEmptyString
    parents: tuple[ConceptId, ...] = ()
    abstraction_method: NonEmptyString | None = None
    supply: dict[str, Any] = Field(default_factory=dict)


class OperatorRecord(_UpstreamRecord):
    id: OperatorId
    canonical_name: OperatorSymbol
    description: NonEmptyString
    sources: tuple[NonEmptyString, ...]
    created_at: NonEmptyString
    input_concepts: tuple[ConceptId, ...]
    output_concept: ConceptId
    abstraction_method: NonEmptyString | None = None
    supply: dict[str, Any] = Field(default_factory=dict)
