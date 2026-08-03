"""The committed artifacts match the real acquired sources and re-derive their own digests.

These tests read ``artifacts/ontology-sources/`` only. They do not need the raw archives,
so they run on a checkout that has none -- which is the point of freezing parsed snapshots
instead of vendoring 16 MB of upstream data.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

import pytest

from ke_memory_demo.core.json import canonical_json
from ke_memory_demo.ontology_sources import MANIFEST_NAME, SourceName

ARTIFACT_DIR = Path("artifacts/ontology-sources")
# Published counts, used as an outside check that the parsers read the format correctly
# rather than merely producing a self-consistent number. WordNet 3.0's synset total is
# Princeton's own figure.
EXPECTED_WORDNET_SYNSETS = 117_659


@pytest.fixture
def artifact_dir(project_root: Path) -> Path:
    directory = project_root / ARTIFACT_DIR
    if not directory.is_dir():
        pytest.skip(f"{ARTIFACT_DIR} has not been built; run scripts/freeze_ontology_sources.py")
    return directory


def _load(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def test_all_three_sources_are_frozen(artifact_dir: Path) -> None:
    manifest = _load(artifact_dir / MANIFEST_NAME)
    statuses = {
        cast(str, entry["source"]): cast(str, entry["status"])
        for entry in cast(list[dict[str, Any]], manifest["entries"])
    }

    assert statuses == {
        SourceName.WORDNET.value: "acquired",
        SourceName.PROPBANK.value: "acquired",
        SourceName.SCHEMAORG.value: "acquired",
    }


def test_the_manifest_carries_three_independent_digests(artifact_dir: Path) -> None:
    manifest = _load(artifact_dir / MANIFEST_NAME)
    entries = cast(list[dict[str, Any]], manifest["entries"])
    digests = {
        cast(str, entry["source"]): cast(str, entry["snapshot_sha256"])
        for entry in entries
        if entry["status"] == "acquired"
    }

    assert len(digests) == 3
    assert len(set(digests.values())) == 3
    # An accidental combined hash is the specific failure this asserts against.
    assert manifest["combined_hash"] is None


def test_each_snapshot_re_derives_the_digest_it_claims(artifact_dir: Path) -> None:
    """Read the file, drop its freeze block, re-hash: the value must match."""
    manifest = _load(artifact_dir / MANIFEST_NAME)
    claimed = {
        cast(str, entry["source"]): cast(str, entry["snapshot_sha256"])
        for entry in cast(list[dict[str, Any]], manifest["entries"])
        if entry["status"] == "acquired"
    }

    for source, digest in claimed.items():
        payload = _load(artifact_dir / f"{source}.json")
        freeze = cast(dict[str, Any], payload.pop("freeze"))
        recomputed = hashlib.sha256(canonical_json(payload)).hexdigest()
        assert recomputed == digest, source
        assert freeze["sha256"] == digest, source


def test_every_acquisition_records_url_version_hash_and_licence(artifact_dir: Path) -> None:
    manifest = _load(artifact_dir / MANIFEST_NAME)

    for entry in cast(list[dict[str, Any]], manifest["entries"]):
        if entry["status"] != "acquired":
            continue
        acquisition = cast(dict[str, Any], entry["acquisition"])
        assert cast(str, acquisition["url"]).startswith("https://")
        assert acquisition["resolved_version"]
        assert len(cast(str, acquisition["raw_sha256"])) == 64
        assert cast(int, acquisition["raw_bytes"]) > 0
        assert acquisition["licence"]
        # Raw archives stay outside the repository, referenced by absolute path.
        assert cast(str, acquisition["raw_path"]).startswith("/")


def test_parsed_counts_are_non_zero_for_every_source(artifact_dir: Path) -> None:
    manifest = _load(artifact_dir / MANIFEST_NAME)

    for entry in cast(list[dict[str, Any]], manifest["entries"]):
        if entry["status"] != "acquired":
            continue
        counts = cast(dict[str, int], entry["parsed_counts"])
        assert counts, entry["source"]
        assert all(value > 0 for value in counts.values()), entry["source"]


def test_wordnet_snapshot_matches_the_published_release_size(artifact_dir: Path) -> None:
    snapshot = _load(artifact_dir / "wordnet.json")

    assert snapshot["release"] == "3.0"
    counts = cast(dict[str, int], snapshot["synset_count_by_pos"])
    assert sum(counts.values()) == EXPECTED_WORDNET_SYNSETS
    assert snapshot["lexname_count"] == 45
    assert snapshot["sample"]


def test_propbank_snapshot_holds_frames_and_rolesets(artifact_dir: Path) -> None:
    snapshot = _load(artifact_dir / "propbank.json")

    assert snapshot["release"] == "3.4.0"
    assert cast(int, snapshot["frame_file_count"]) > 7_000
    assert cast(int, snapshot["roleset_count"]) > cast(int, snapshot["predicate_count"])
    assert cast(int, snapshot["role_count"]) > cast(int, snapshot["roleset_count"])


def test_schemaorg_snapshot_holds_classes_and_properties(artifact_dir: Path) -> None:
    snapshot = _load(artifact_dir / "schemaorg.json")

    assert snapshot["release"] == "30.0"
    assert cast(int, snapshot["class_count"]) > 900
    assert cast(int, snapshot["property_count"]) > 1_400
    sample_ids = {
        cast(str, term["term_id"]) for term in cast(list[dict[str, Any]], snapshot["sample"])
    }
    assert "schema:Thing" in sample_ids
    assert "schema:Person" in sample_ids
