"""Mapper v1: natural expression to frozen ontology.

Kept a separate package so its dependency edges are visible: it reads the frozen ontology units and
nothing from the evaluation layer, which is what keeps questions and gold structurally out of reach.
"""

from __future__ import annotations

from .mapper import (
    FORBIDDEN_INPUT_FIELDS,
    MAPPER_ID,
    MAPPER_VERSION,
    Candidate,
    FrozenOntology,
    Layer,
    MapperError,
    MapperInput,
    MapperV1,
    MappingRecord,
    Resolution,
    load_frozen_ontology,
)

__all__ = [
    "FORBIDDEN_INPUT_FIELDS",
    "MAPPER_ID",
    "MAPPER_VERSION",
    "Candidate",
    "FrozenOntology",
    "Layer",
    "MapperError",
    "MapperInput",
    "MapperV1",
    "MappingRecord",
    "Resolution",
    "load_frozen_ontology",
]
