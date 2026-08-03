"""Mapper v3: construction evidence over the stable O_v3 namespace.

Separate from mapper_v2 so its predecessor stays readable as a measured result. Nothing here reads the
fresh validation set or its labels.
"""

from __future__ import annotations

from .mapper_v3 import (
    MAPPER_ID,
    MAPPER_VERSION,
    ExpressionInput,
    MapperV3,
    MapperV3Error,
    MappingResult,
    Outcome,
    UnresolvedReason,
)
from .frames import FrameGenerator, SemanticFrame, build_entries
from .constructions import (
    CONSTRUCTION_TO_ITEM_TYPES,
    Construction,
    ConstructionHit,
    detect,
    is_request_only,
    supported_item_types,
)

__all__ = [
    "CONSTRUCTION_TO_ITEM_TYPES",
    "MAPPER_ID",
    "MAPPER_VERSION",
    "ExpressionInput",
    "FrameGenerator",
    "MapperV3",
    "MapperV3Error",
    "MappingResult",
    "Outcome",
    "SemanticFrame",
    "UnresolvedReason",
    "build_entries",
    "Construction",
    "ConstructionHit",
    "detect",
    "is_request_only",
    "supported_item_types",
]
