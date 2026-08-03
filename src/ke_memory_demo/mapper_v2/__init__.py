"""Mapper v2: discriminative candidate scoring with a native abstain path."""

from __future__ import annotations

from .mapper import (
    GENERIC_TERM_SHARE,
    MAPPER_ID,
    MAPPER_VERSION,
    AbstainReason,
    STOPWORDS,
    CandidateV2,
    MapperV2,
    MappingRecordV2,
    assert_no_correction_gate,
    protected_alias_terms,
    terms,
)

__all__ = [
    "GENERIC_TERM_SHARE",
    "MAPPER_ID",
    "MAPPER_VERSION",
    "AbstainReason",
    "STOPWORDS",
    "CandidateV2",
    "MapperV2",
    "MappingRecordV2",
    "assert_no_correction_gate",
    "protected_alias_terms",
    "terms",
]
