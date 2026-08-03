"""The pinned coordinates of each source, and the check that a local file matches them.

This module is the single place where "which version did we freeze" is written down. The
URLs are all GitHub, and every one resolves to something immutable:

- WordNet is fetched as a git *blob* rather than a path on a branch. ``nltk_data``'s
  gh-pages branch moves weekly, but blob ``3c68cd20`` is content-addressed by git, so the
  URL cannot start returning different bytes.
- PropBank is a release tag tarball. GitHub regenerates tarballs, so the tag alone is not
  a byte guarantee -- the sha256 below is what actually pins it.
- schema.org is a blob for the same reason as WordNet.

``raw.githubusercontent.com`` and ``schema.org`` are both unreachable from this host, so
these routes go through ``api.github.com`` and ``codeload.github.com``, which are not.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Final

from ke_memory_demo.ontology_sources.models import (
    SourceAcquisition,
    SourceName,
    UnavailableSource,
)

# Outside the repository on purpose: these total ~16 MB and the constraint is to keep raw
# archives out of git. Only the parsed snapshots are committed.
RAW_ROOT: Final[Path] = Path("/public/home/wwb/datasets/ontology-sources")


@dataclass(frozen=True)
class SourcePin:
    """One source's immutable coordinates, independent of whether it is on disk yet."""

    source: SourceName
    filename: str
    url: str
    resolved_version: str
    expected_sha256: str
    licence: str
    retrieved_at: str
    # The command that produced the local file, recorded so a reviewer can re-run it and a
    # failure can be reported with the exact invocation that failed.
    fetch_command: str

    def path(self, root: Path = RAW_ROOT) -> Path:
        return root / self.filename


WORDNET_PIN: Final[SourcePin] = SourcePin(
    source=SourceName.WORDNET,
    filename="wordnet-3.0-nltk.zip",
    url=(
        "https://api.github.com/repos/nltk/nltk_data/git/blobs/"
        "3c68cd207844f071a5206f7fbed23e5c607ec02f"
    ),
    resolved_version=(
        "WordNet 3.0; nltk_data blob 3c68cd207844f071a5206f7fbed23e5c607ec02f "
        "(packages/corpora/wordnet.zip at gh-pages commit "
        "550b6625bcef1f2abff2ff770a5a0d272c9c6b2a)"
    ),
    expected_sha256="cbda5ea6eef7f36a97a43d4a75f85e07fccbb4f23657d27b4ccbc93e2646ab59",
    licence=(
        "WordNet 3.0 Licence (Princeton University); permissive, requires the copyright "
        "notice and disclaimer to be retained"
    ),
    retrieved_at="2026-08-03",
    fetch_command=(
        "curl -sS -H 'Accept: application/vnd.github.raw' -o wordnet-3.0-nltk.zip "
        "https://api.github.com/repos/nltk/nltk_data/git/blobs/"
        "3c68cd207844f071a5206f7fbed23e5c607ec02f"
    ),
)

PROPBANK_PIN: Final[SourcePin] = SourcePin(
    source=SourceName.PROPBANK,
    filename="propbank-frames-3.4.0.tar.gz",
    url="https://codeload.github.com/propbank/propbank-frames/tar.gz/refs/tags/v3.4.0",
    resolved_version=(
        "propbank-frames v3.4.0; tag commit 4087fa9ab5c40907c34ff91a56acc2cab1670145"
    ),
    expected_sha256="3a9d4d25d8f29b5f536452630e2dd83823ca230c45a3fabde785df21a21957dd",
    licence="Creative Commons Attribution-ShareAlike 4.0 International (CC BY-SA 4.0)",
    retrieved_at="2026-08-03",
    fetch_command=(
        "curl -sS -L -o propbank-frames-3.4.0.tar.gz "
        "https://codeload.github.com/propbank/propbank-frames/tar.gz/refs/tags/v3.4.0"
    ),
)

SCHEMAORG_PIN: Final[SourcePin] = SourcePin(
    source=SourceName.SCHEMAORG,
    filename="schemaorg-30.0-current-https.jsonld",
    url=(
        "https://api.github.com/repos/schemaorg/schemaorg/git/blobs/"
        "e69c25e9b6c3ab08557f80ad1c10dae0d6b25766"
    ),
    resolved_version=(
        "schema.org 30.0; blob e69c25e9b6c3ab08557f80ad1c10dae0d6b25766 "
        "(data/releases/30.0/schemaorg-current-https.jsonld at release v30.0, "
        "commit 420231f6bfac8372fc564abb121fae57ccb36a0c)"
    ),
    expected_sha256="4467fa19edcb1d7fb3c46c0adf3591b7f870c4a60b7838bdb61694fd02864cf6",
    licence="Creative Commons Attribution-ShareAlike 3.0 (CC BY-SA 3.0)",
    retrieved_at="2026-08-03",
    fetch_command=(
        "curl -sS -H 'Accept: application/vnd.github.raw' "
        "-o schemaorg-30.0-current-https.jsonld "
        "https://api.github.com/repos/schemaorg/schemaorg/git/blobs/"
        "e69c25e9b6c3ab08557f80ad1c10dae0d6b25766"
    ),
)

SOURCE_PINS: Final[tuple[SourcePin, ...]] = (WORDNET_PIN, PROPBANK_PIN, SCHEMAORG_PIN)


def file_sha256(path: Path) -> str:
    """Digest a file in chunks; these archives are large enough to matter on a FUSE mount."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def acquire(pin: SourcePin, root: Path = RAW_ROOT) -> SourceAcquisition | UnavailableSource:
    """Return an acquisition record if the pinned bytes are on disk, else why they are not.

    This never downloads. Fetching happens once, out of band, via ``pin.fetch_command``;
    keeping the loaders offline means a freeze run is reproducible and cannot silently
    pick up a newer upstream release.

    A digest mismatch is reported as unavailable rather than raising, because the review
    asks for the failure mode to be recorded. Parsing bytes that do not match the pin
    would produce a snapshot whose provenance is a lie.
    """
    path = pin.path(root)
    if not path.is_file():
        return UnavailableSource(
            source=pin.source,
            url=pin.url,
            commands_tried=(pin.fetch_command,),
            failure_mode=f"no local copy at {path}; the fetch command has not been run",
        )

    actual = file_sha256(path)
    if actual != pin.expected_sha256:
        return UnavailableSource(
            source=pin.source,
            url=pin.url,
            commands_tried=(pin.fetch_command, f"sha256sum {path}"),
            failure_mode=(
                f"sha256 mismatch: expected {pin.expected_sha256}, found {actual}; "
                "the local file is not the pinned release"
            ),
        )

    return SourceAcquisition(
        url=pin.url,
        resolved_version=pin.resolved_version,
        raw_sha256=actual,
        raw_bytes=path.stat().st_size,
        raw_path=str(path),
        licence=pin.licence,
        retrieved_at=pin.retrieved_at,
    )
