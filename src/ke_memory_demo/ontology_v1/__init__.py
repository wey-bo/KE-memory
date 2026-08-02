"""Foundation ontology v1: three independently hashed freeze units and their derivation map.

``O_L1`` is the atomic layer, ``O_L2`` the cross-turn abstraction layer, and ``M_L1_to_L2``
the only place the two vocabularies meet. The freeze models live in :mod:`.models`, the
authored content in :mod:`.l1_content`, :mod:`.l2_content` and :mod:`.mapping_content`, and
the candidate ledger and provenance snapshot in :mod:`.decisions`.

This package makes no model or judge call and does nothing at runtime. KEOL's role here is
offline construction and normalization: the units are immutable once hashed, so a coverage
gap has to be recorded as an uncovered expression rather than closed by expanding the
vocabulary online.
"""

from __future__ import annotations

from .decisions import ONTOLOGY_VERSION, build_foundation_ontology, build_ledger, build_provenance
from .l1_content import O_L1_VERSION, build_o_l1
from .l2_content import O_L2_VERSION, build_o_l2
from .mapping_content import M_VERSION, build_m_l1_to_l2
from .models import (
    CandidateDecision,
    Constraint,
    DecisionLedger,
    DerivationEntry,
    DerivationKind,
    Disposition,
    FoundationOntology,
    L1Freeze,
    L1Item,
    L1ItemType,
    L2Freeze,
    L2Item,
    L2ItemType,
    MappingFreeze,
    OntologyFreezeError,
    OntologyItem,
    OntologyRoleKind,
    Provenance,
    ProvenanceSnapshot,
    Relation,
    RelationKind,
    RoleSlot,
    SourceKind,
    SourceSnapshot,
    UncoveredExpression,
    sha256_of,
)


__all__ = [
    "CandidateDecision",
    "Constraint",
    "DecisionLedger",
    "DerivationEntry",
    "DerivationKind",
    "Disposition",
    "FoundationOntology",
    "L1Freeze",
    "L1Item",
    "L1ItemType",
    "L2Freeze",
    "L2Item",
    "L2ItemType",
    "MappingFreeze",
    "M_VERSION",
    "ONTOLOGY_VERSION",
    "O_L1_VERSION",
    "O_L2_VERSION",
    "OntologyFreezeError",
    "OntologyItem",
    "OntologyRoleKind",
    "Provenance",
    "ProvenanceSnapshot",
    "Relation",
    "RelationKind",
    "RoleSlot",
    "SourceKind",
    "SourceSnapshot",
    "UncoveredExpression",
    "build_foundation_ontology",
    "build_ledger",
    "build_m_l1_to_l2",
    "build_o_l1",
    "build_o_l2",
    "build_provenance",
    "sha256_of",
]
