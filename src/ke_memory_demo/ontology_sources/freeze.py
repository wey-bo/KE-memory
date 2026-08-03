"""Build the three source snapshots and the manifest that freezes them.

The manifest carries one independent digest per source. There is deliberately no combined
hash: with three digests, a schema.org release moves exactly one line and a claim made
about WordNet last month is still checkable. With one, every claim expires together.

A source that is missing or whose bytes do not match its pin becomes an
:class:`~ke_memory_demo.ontology_sources.models.UnavailableSource` entry in the manifest.
The freeze still succeeds and still writes a file, because the reviewable fact is *which*
sources are backed by bytes, and hiding a gap behind a crash would lose that.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from ke_memory_demo.ontology_sources.models import (
    FrozenModel,
    HASH_SCOPE,
    NonEmptyString,
    PropBankSnapshot,
    SchemaOrgSnapshot,
    SourceAcquisition,
    SourceName,
    UnavailableSource,
    WordNetSnapshot,
    snapshot_sha256,
)
from ke_memory_demo.ontology_sources.propbank import load_propbank
from ke_memory_demo.ontology_sources.registry import (
    RAW_ROOT,
    SOURCE_PINS,
    SourcePin,
    acquire,
)
from ke_memory_demo.ontology_sources.schemaorg import load_schemaorg
from ke_memory_demo.ontology_sources.wordnet import load_wordnet

type SourceSnapshot = WordNetSnapshot | PropBankSnapshot | SchemaOrgSnapshot

MANIFEST_NAME: Final[str] = "source-freeze.json"

# The release each pin points at. Kept beside the dispatch that needs them rather than in
# the pin, because the pin identifies *bytes* and this names the upstream release those
# bytes belong to.
_PROPBANK_RELEASE: Final[str] = "3.4.0"
_SCHEMAORG_RELEASE: Final[str] = "30.0"


class SourceFreezeEntry(FrozenModel):
    """One manifest row: an acquired source and the digest of its snapshot."""

    status: Literal["acquired"] = "acquired"
    source: SourceName
    artifact: NonEmptyString
    snapshot_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    acquisition: SourceAcquisition
    # Whatever this source counts. Names differ per source, so this stays a free mapping
    # rather than a fixed schema that would force WordNet's counts onto PropBank.
    parsed_counts: dict[str, int]


class SourceFreezeManifest(BaseModel):
    """The manifest itself. Not frozen-hashed as a whole -- the per-source digests are."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    hash_scope: NonEmptyString = HASH_SCOPE
    combined_hash: None = Field(
        default=None,
        description=(
            "Always null. A single digest over all three sources would make a citation "
            "about one source expire when an unrelated source is re-released."
        ),
    )
    entries: tuple[SourceFreezeEntry | UnavailableSource, ...]

    def digests(self) -> dict[str, str]:
        """The independent per-source digests, keyed by source name."""
        return {
            entry.source.value: entry.snapshot_sha256
            for entry in self.entries
            if isinstance(entry, SourceFreezeEntry)
        }

    def unavailable(self) -> tuple[UnavailableSource, ...]:
        return tuple(e for e in self.entries if isinstance(e, UnavailableSource))


class FrozenSources(FrozenModel):
    """The result of a freeze run: the snapshots that parsed, plus the manifest."""

    snapshots: dict[str, SourceSnapshot]
    manifest: SourceFreezeManifest


def _wordnet_counts(snapshot: WordNetSnapshot) -> dict[str, int]:
    counts = {f"synsets_{pos}": n for pos, n in snapshot.synset_count_by_pos.items()}
    counts["synsets_total"] = snapshot.total_synsets
    counts["lexnames"] = snapshot.lexname_count
    return counts


def _propbank_counts(snapshot: PropBankSnapshot) -> dict[str, int]:
    return {
        "frame_files": snapshot.frame_file_count,
        "predicates": snapshot.predicate_count,
        "rolesets": snapshot.roleset_count,
        "roles": snapshot.role_count,
    }


def _schemaorg_counts(snapshot: SchemaOrgSnapshot) -> dict[str, int]:
    return {
        "graph_nodes": snapshot.graph_node_count,
        "classes": snapshot.class_count,
        "properties": snapshot.property_count,
        "enumeration_members": snapshot.enumeration_member_count,
    }


def _load(pin: SourcePin, acquisition: SourceAcquisition, root: Path) -> SourceSnapshot:
    """Dispatch on the pin's source, not on object identity.

    Identity would look tidier but breaks the moment a caller builds a pin with a different
    digest -- which is exactly what the tests do to exercise a re-release.
    """
    path = pin.path(root)
    if pin.source is SourceName.WORDNET:
        return load_wordnet(path, acquisition)
    if pin.source is SourceName.PROPBANK:
        return load_propbank(path, acquisition, release=_PROPBANK_RELEASE)
    return load_schemaorg(path, acquisition, release=_SCHEMAORG_RELEASE)


_COUNTERS: Final[dict[SourceName, Callable[[SourceSnapshot], dict[str, int]]]] = {
    SourceName.WORDNET: lambda s: _wordnet_counts(s)
    if isinstance(s, WordNetSnapshot)
    else {},
    SourceName.PROPBANK: lambda s: _propbank_counts(s)
    if isinstance(s, PropBankSnapshot)
    else {},
    SourceName.SCHEMAORG: lambda s: _schemaorg_counts(s)
    if isinstance(s, SchemaOrgSnapshot)
    else {},
}


def freeze_sources(root: Path = RAW_ROOT) -> FrozenSources:
    """Parse whatever is on disk at its pinned digest and build the manifest."""
    snapshots: dict[str, SourceSnapshot] = {}
    entries: list[SourceFreezeEntry | UnavailableSource] = []

    for pin in SOURCE_PINS:
        record = acquire(pin, root)
        if isinstance(record, UnavailableSource):
            entries.append(record)
            continue
        snapshot = _load(pin, record, root)
        counts = _COUNTERS[pin.source](snapshot)
        if not any(value > 0 for value in counts.values()):
            # A snapshot that parsed to all-zero counts is the silent-empty case the
            # review rejects, so it is reported as a failure instead of frozen.
            entries.append(
                UnavailableSource(
                    source=pin.source,
                    url=pin.url,
                    commands_tried=(pin.fetch_command,),
                    failure_mode="the pinned bytes parsed to zero items",
                )
            )
            continue
        snapshots[pin.source.value] = snapshot
        entries.append(
            SourceFreezeEntry(
                source=pin.source,
                artifact=f"{pin.source.value}.json",
                snapshot_sha256=snapshot_sha256(snapshot),
                acquisition=record,
                parsed_counts=counts,
            )
        )

    return FrozenSources(
        snapshots=snapshots, manifest=SourceFreezeManifest(entries=tuple(entries))
    )
