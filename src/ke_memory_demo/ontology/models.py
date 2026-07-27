"""Compatibility import for :mod:`ke_memory_ontology.models`."""

from ke_memory_ontology.models import (
    ElasticsearchConnection,
    IndexIdentity,
    OntologyAuthenticationError,
    OntologyDriftError,
    OntologyError,
    OntologyHealth,
    OntologyNotFoundError,
    OntologyRelation,
    OntologySchemaError,
    OntologyTerm,
    OntologyUnavailableError,
)


__all__ = [
    "ElasticsearchConnection",
    "IndexIdentity",
    "OntologyAuthenticationError",
    "OntologyDriftError",
    "OntologyError",
    "OntologyHealth",
    "OntologyNotFoundError",
    "OntologyRelation",
    "OntologySchemaError",
    "OntologyTerm",
    "OntologyUnavailableError",
]
