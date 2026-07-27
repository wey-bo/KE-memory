"""Compatibility facade for the external ontology package."""

from ke_memory_ontology import (
    ElasticsearchConnection,
    ElasticsearchVocabulary,
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
    OntologyVocabulary,
)


__all__ = [
    "ElasticsearchConnection",
    "ElasticsearchVocabulary",
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
    "OntologyVocabulary",
]
