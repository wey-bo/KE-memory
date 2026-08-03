"""Independent annotation gold for the fresh 160-expression mapping set (ontology v2 + v3).

The annotation line of the mapping-quality evaluation, kept as its own package so the separation
from the mapper line is structural rather than a convention. Nothing here imports ``mapper_v1``,
``mapper_v2`` or ``mapper_v3``, and the dependency gate holds that in place.
"""

from __future__ import annotations

from .annotations import (
    ANNOTATED_AGAINST_ONTOLOGY,
    ANNOTATED_SET_SHA256,
    GAP_CATEGORIES,
    build_annotation_gold,
)
from .loader import (
    load_combined_ontology_ids,
    load_gold,
    load_gold_digest,
    load_v2_ids,
    load_v3_added_ids,
    mapping_set_digest,
    mapping_set_expression_ids,
)
from .models import V3_ADDED_IDS, AnnotationGold, AnnotationRecord, Outcome

__all__ = [
    "ANNOTATED_AGAINST_ONTOLOGY",
    "ANNOTATED_SET_SHA256",
    "GAP_CATEGORIES",
    "V3_ADDED_IDS",
    "AnnotationGold",
    "AnnotationRecord",
    "Outcome",
    "build_annotation_gold",
    "load_combined_ontology_ids",
    "load_gold",
    "load_gold_digest",
    "load_v2_ids",
    "load_v3_added_ids",
    "mapping_set_digest",
    "mapping_set_expression_ids",
]
