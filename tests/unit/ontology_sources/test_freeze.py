"""Freeze behaviour: independent digests, digests that move, and honest unavailability."""

from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path

import pytest

from ke_memory_demo.ontology_sources import (
    PROPBANK_PIN,
    SCHEMAORG_PIN,
    SOURCE_PINS,
    SourceFreezeEntry,
    UnavailableSource,
    WORDNET_PIN,
    acquire,
    file_sha256,
    load_schemaorg,
    load_wordnet,
    snapshot_sha256,
)
from ke_memory_demo.ontology_sources import freeze as freeze_module
from ke_memory_demo.ontology_sources.freeze import SourceFreezeManifest, freeze_sources
from ke_memory_demo.ontology_sources.registry import SourcePin

from .fixtures import (
    acquisition,
    write_propbank_archive,
    write_schemaorg_document,
    write_wordnet_archive,
)


def _staged_root(tmp_path: Path) -> tuple[Path, tuple[SourcePin, ...]]:
    """Write all three fixture archives and repin each source to its fixture digest."""
    root = tmp_path / "sources"
    root.mkdir()
    write_wordnet_archive(root / WORDNET_PIN.filename)
    write_propbank_archive(root / PROPBANK_PIN.filename)
    write_schemaorg_document(root / SCHEMAORG_PIN.filename)
    pins = tuple(
        replace(pin, expected_sha256=file_sha256(root / pin.filename))
        for pin in SOURCE_PINS
    )
    return root, pins


def _freeze_fixtures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> SourceFreezeManifest:
    root, pins = _staged_root(tmp_path)
    monkeypatch.setattr(freeze_module, "SOURCE_PINS", pins)
    return freeze_sources(root).manifest


def test_freeze_produces_one_independent_digest_per_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = _freeze_fixtures(tmp_path, monkeypatch)
    digests = manifest.digests()

    assert sorted(digests) == ["propbank", "schemaorg", "wordnet"]
    # Three distinct values, and no combined digest that would couple them.
    assert len(set(digests.values())) == 3
    assert manifest.combined_hash is None


def test_freeze_records_non_zero_parsed_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = _freeze_fixtures(tmp_path, monkeypatch)

    entries = [e for e in manifest.entries if isinstance(e, SourceFreezeEntry)]
    assert len(entries) == 3
    for entry in entries:
        assert entry.parsed_counts
        assert all(count > 0 for count in entry.parsed_counts.values()), entry.source


def test_a_source_digest_moves_when_its_own_content_changes(tmp_path: Path) -> None:
    """The property that makes the digest worth recording at all."""
    first = tmp_path / "a.jsonld"
    second = tmp_path / "b.jsonld"
    write_schemaorg_document(first)
    write_schemaorg_document(second, extra_classes=1)

    before = snapshot_sha256(load_schemaorg(first, acquisition(), release="30.0"))
    after = snapshot_sha256(load_schemaorg(second, acquisition(), release="30.0"))

    assert before != after


def test_a_source_digest_is_stable_for_identical_content(tmp_path: Path) -> None:
    document = tmp_path / "schemaorg.jsonld"
    write_schemaorg_document(document)

    first = snapshot_sha256(load_schemaorg(document, acquisition(), release="30.0"))
    second = snapshot_sha256(load_schemaorg(document, acquisition(), release="30.0"))

    assert first == second


def test_a_digest_moves_when_provenance_changes_not_only_content(tmp_path: Path) -> None:
    """Acquisition is inside the hashed body, so re-pinning to new bytes is visible."""
    archive = tmp_path / "wordnet.zip"
    write_wordnet_archive(archive)

    original = load_wordnet(archive, acquisition(sha256="a" * 64))
    repinned = load_wordnet(archive, acquisition(sha256="b" * 64))

    assert snapshot_sha256(original) != snapshot_sha256(repinned)


def test_one_source_changing_does_not_move_another_source_digest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, pins = _staged_root(tmp_path)
    monkeypatch.setattr(freeze_module, "SOURCE_PINS", pins)
    before = freeze_sources(root).manifest.digests()

    # Re-release schema.org with one extra class and repin only that source.
    write_schemaorg_document(root / SCHEMAORG_PIN.filename, extra_classes=3)
    changed = tuple(
        replace(pin, expected_sha256=file_sha256(root / pin.filename)) for pin in pins
    )
    monkeypatch.setattr(freeze_module, "SOURCE_PINS", changed)
    after = freeze_sources(root).manifest.digests()

    assert after["schemaorg"] != before["schemaorg"]
    assert after["wordnet"] == before["wordnet"]
    assert after["propbank"] == before["propbank"]


def test_a_missing_source_is_reported_unavailable_not_silently_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, pins = _staged_root(tmp_path)
    (root / PROPBANK_PIN.filename).unlink()
    monkeypatch.setattr(freeze_module, "SOURCE_PINS", pins)
    frozen = freeze_sources(root)

    assert "propbank" not in frozen.snapshots
    assert "propbank" not in frozen.manifest.digests()
    unavailable = frozen.manifest.unavailable()
    assert [entry.source.value for entry in unavailable] == ["propbank"]
    # The failure must be reproducible: a command and a reason, not just a flag.
    assert unavailable[0].commands_tried
    assert "no local copy" in unavailable[0].failure_mode
    # The other two still freeze; one gap does not void the whole manifest.
    assert sorted(frozen.manifest.digests()) == ["schemaorg", "wordnet"]


def test_bytes_that_do_not_match_the_pin_are_unavailable(tmp_path: Path) -> None:
    """A digest mismatch must never be parsed: the provenance would be false."""
    root = tmp_path / "sources"
    root.mkdir()
    write_wordnet_archive(root / WORDNET_PIN.filename)

    record = acquire(WORDNET_PIN, root)

    assert isinstance(record, UnavailableSource)
    assert "sha256 mismatch" in record.failure_mode
    assert WORDNET_PIN.expected_sha256 in record.failure_mode


def test_every_pin_resolves_to_an_immutable_coordinate() -> None:
    """A branch name would let the URL start returning different bytes."""
    for pin in SOURCE_PINS:
        assert len(pin.expected_sha256) == 64
        assert pin.url.startswith("https://")
        assert "refs/heads/" not in pin.url
        assert pin.licence
        assert pin.fetch_command


def test_the_loaders_do_not_depend_on_the_project_ontology() -> None:
    """What the literature says must be establishable without what we built on it.

    If these loaders imported ontology_v1, "we consulted WordNet" could no longer be
    checked independently of the ontology that cites it.
    """
    import ast

    package = Path(__file__).resolve().parents[3] / "src" / "ke_memory_demo" / "ontology_sources"
    offenders: dict[str, list[str]] = {}
    for path in sorted(package.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        found = sorted(
            name
            for node in ast.walk(tree)
            for name in _imported_names(node)
            if "ontology_v1" in name
        )
        if found:
            offenders[path.name] = found

    assert offenders == {}


def _imported_names(node: ast.AST) -> list[str]:
    if isinstance(node, ast.ImportFrom):
        return [node.module] if node.module else []
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    return []
