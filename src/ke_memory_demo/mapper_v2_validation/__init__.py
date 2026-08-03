"""Independent annotation gold for the natural-expression validation sample.

This is the annotation line of the mapping-quality evaluation, kept as its own package so the
separation from the mapper line is structural rather than a convention. Nothing here imports
``mapper_v1`` or ``mapper_v2``, and the dependency gate holds that in place.
"""

from __future__ import annotations

from .annotations import ANNOTATED_SAMPLE_SHA256, GAP_CATEGORIES, build_annotation_gold
from .loader import load_gold, load_gold_digest, load_ontology_ids, sample_expression_ids
from .models import AnnotationGold, AnnotationRecord, Outcome

__all__ = [
    "ANNOTATED_SAMPLE_SHA256",
    "GAP_CATEGORIES",
    "AnnotationGold",
    "AnnotationRecord",
    "Outcome",
    "build_annotation_gold",
    "load_gold",
    "load_gold_digest",
    "load_ontology_ids",
    "sample_expression_ids",
]
