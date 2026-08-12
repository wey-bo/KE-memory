"""The portable source manifest, binding artifacts to the shards derived from them.

Deliberately not a reuse of `artifacts/ontology-sources/source-freeze.json`. That file
records 11,205 PropBank rolesets -- one short, because `frames/license.xml` was filtered out
by name despite being a real frameset -- and stores absolute host paths, which makes it
unusable as a portable input. The original artifacts and their digests are reused; the
manifest around them is rebuilt.

"Portable" means the manifest names no machine. An artifact is identified by its digest and
a stable logical name, so the same manifest describes the same corpus wherever it is
mounted. Where the file happens to live is a property of a run, not of the corpus, and
belongs in the run receipt.

The manifest binds four things together, because any one alone is insufficient to reproduce
a build: the source artifact digest, the normalized shard digests derived from it, the
parser and schema versions that did the deriving, and the record counts. Same digests plus
same parser version must yield the same shards -- and if the parser changes, the manifest
says so rather than silently describing different content under the same name.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from memory_assertion_v1.alignment.canonical_bytes import digest

NonEmptyString = Annotated[str, Field(min_length=1)]
Sha256Hex = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]

SourceName = Literal["wordnet", "propbank", "schema_org"]

# Bumped when a parser's output changes for unchanged input. The manifest records it so a
# shard digest mismatch can be attributed to a parser change rather than to a corrupt
# corpus.
PARSER_VERSION = "memory-assertion-v1-sources/1"
MANIFEST_SCHEMA_VERSION = "alignment-source-manifest/1"


class _ManifestRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SourceArtifact(_ManifestRecord):
    """One frozen input file, identified by content rather than by location.

    `logical_name` is the stable handle used in provenance references. `byte_size` is kept
    alongside the digest because a truncated download has a different digest but the size is
    what makes the failure obvious to a reader.
    """

    source: SourceName
    logical_name: NonEmptyString
    source_version: NonEmptyString
    artifact_sha256: Sha256Hex
    byte_size: Annotated[int, Field(gt=0)]


class SourceShard(_ManifestRecord):
    """A normalized shard of source records derived from one artifact.

    `record_count` and `shard_sha256` together are the reproducibility claim: re-running the
    named parser over the named artifact must produce this many records with this digest.
    """

    source: SourceName
    shard_path: NonEmptyString
    artifact_sha256: Sha256Hex
    parser_version: NonEmptyString
    record_count: Annotated[int, Field(ge=0)]
    shard_sha256: Sha256Hex


class SourceManifest(_ManifestRecord):
    """The binding of artifacts to shards, and the versions that connect them."""

    manifest_schema_version: Literal["alignment-source-manifest/1"] = MANIFEST_SCHEMA_VERSION
    artifacts: tuple[SourceArtifact, ...]
    shards: tuple[SourceShard, ...]

    def artifact_for(self, source: SourceName) -> SourceArtifact:
        for artifact in self.artifacts:
            if artifact.source == source:
                return artifact
        raise KeyError(f"no artifact for source {source!r}")

    def manifest_sha256(self) -> str:
        """Digest of this manifest's own canonical bytes.

        Computed on demand rather than stored: a stored digest of the containing document
        would have to be part of the document it describes, which is the cycle the hash
        graph forbids.
        """
        return digest(self.model_dump(mode="json"))


def build_manifest(
    artifacts: tuple[SourceArtifact, ...], shards: tuple[SourceShard, ...]
) -> SourceManifest:
    """Assemble a manifest with both lists in a stable order.

    Sorted here rather than trusting the caller: these arrays are semantically unordered, so
    their order must not depend on which source happened to be parsed first.
    """
    return SourceManifest(
        artifacts=tuple(sorted(artifacts, key=lambda item: (item.source, item.logical_name))),
        shards=tuple(sorted(shards, key=lambda item: (item.source, item.shard_path))),
    )
