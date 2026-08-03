"""Third-party ontology sources, acquired at pinned versions and frozen with their digests.

WordNet 3.0, PropBank 3.4.0 and schema.org 30.0. Each is fetched once from an immutable
GitHub coordinate, verified against a recorded sha256, and parsed into a compact snapshot
that carries its own provenance. Nothing here imports ``ke_memory_demo.ontology_v1``: this
package answers "what does the published literature actually say", which must be
establishable without reference to what this project built on top of it.
"""

from __future__ import annotations

from ke_memory_demo.ontology_sources.freeze import (
    FrozenSources,
    MANIFEST_NAME,
    SourceFreezeEntry,
    SourceFreezeManifest,
    SourceSnapshot,
    freeze_sources,
)
from ke_memory_demo.ontology_sources.models import (
    PropBankRoleset,
    PropBankSnapshot,
    SchemaOrgSnapshot,
    SchemaOrgTerm,
    SourceAcquisition,
    SourceName,
    UnavailableSource,
    WordNetSnapshot,
    WordNetSynset,
    snapshot_sha256,
)
from ke_memory_demo.ontology_sources.propbank import load_propbank
from ke_memory_demo.ontology_sources.registry import (
    PROPBANK_PIN,
    RAW_ROOT,
    SCHEMAORG_PIN,
    SOURCE_PINS,
    SourcePin,
    WORDNET_PIN,
    acquire,
    file_sha256,
)
from ke_memory_demo.ontology_sources.schemaorg import load_schemaorg
from ke_memory_demo.ontology_sources.wordnet import load_wordnet

__all__ = [
    "MANIFEST_NAME",
    "PROPBANK_PIN",
    "PropBankRoleset",
    "PropBankSnapshot",
    "RAW_ROOT",
    "SCHEMAORG_PIN",
    "SOURCE_PINS",
    "SchemaOrgSnapshot",
    "SchemaOrgTerm",
    "SourceAcquisition",
    "SourceFreezeEntry",
    "SourceFreezeManifest",
    "SourceName",
    "SourcePin",
    "SourceSnapshot",
    "FrozenSources",
    "UnavailableSource",
    "WORDNET_PIN",
    "WordNetSnapshot",
    "WordNetSynset",
    "acquire",
    "file_sha256",
    "freeze_sources",
    "load_propbank",
    "load_schemaorg",
    "load_wordnet",
    "snapshot_sha256",
]
