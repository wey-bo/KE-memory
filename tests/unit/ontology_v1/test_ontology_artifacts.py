"""The written artifacts say what the builders produce.

A freeze whose artifact and builder disagree is worse than no freeze: the hash in the file is
what gets cited, and the code is what gets used. These tests write to a temporary directory
rather than asserting against ``artifacts/ontology-v1/``, so they check the round trip without
depending on a committed file being current.
"""

from __future__ import annotations

import json
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType

from ke_memory_demo.core.json import canonical_json
from ke_memory_demo.ontology_v1 import build_foundation_ontology, sha256_of

REPO_ROOT = Path(__file__).resolve().parents[3]
BUILD_SCRIPT = REPO_ROOT / "scripts" / "build_foundation_ontology_v1.py"

UNITS = ("o_l1", "o_l2", "m_l1_to_l2", "decisions", "provenance")


def _load_build_script() -> ModuleType:
    """Load the build script by path, as ``scripts`` is not an importable package.

    An earlier version used ``pytest.importorskip`` and skipped the whole file, which meant
    these tests asserted nothing while appearing to pass. Loading by path fails loudly if the
    script moves, which is the behaviour worth having.
    """
    spec = spec_from_file_location("build_foundation_ontology_v1", BUILD_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build_artifacts(destination: Path) -> None:
    script = _load_build_script()
    ontology = build_foundation_ontology()
    destination.mkdir(parents=True, exist_ok=True)
    for unit in UNITS:
        script._write(destination / f"{unit}.json", script._unit_payload(ontology, unit))


def test_each_artifact_carries_the_digest_of_its_own_unit(tmp_path: Path) -> None:
    _build_artifacts(tmp_path)
    expected = build_foundation_ontology().hashes()
    by_unit = {
        "o_l1": "o_l1_sha256",
        "o_l2": "o_l2_sha256",
        "m_l1_to_l2": "m_l1_to_l2_sha256",
        "decisions": "decisions_sha256",
        "provenance": "provenance_sha256",
    }
    for unit, key in by_unit.items():
        payload = json.loads((tmp_path / f"{unit}.json").read_text(encoding="utf-8"))
        assert payload["freeze"]["unit"] == unit
        assert payload["freeze"]["sha256"] == expected[key]


def test_an_artifacts_digest_excludes_its_own_freeze_block(tmp_path: Path) -> None:
    """Otherwise the hash would cover a field derived from the hash, which cannot be checked."""
    _build_artifacts(tmp_path)
    ontology = build_foundation_ontology()
    payload = json.loads((tmp_path / "o_l1.json").read_text(encoding="utf-8"))
    recorded = payload.pop("freeze")["sha256"]

    assert recorded == ontology.l1.digest
    # The remaining body is exactly the unit's model dump, so re-hashing it reproduces the
    # digest without the build script being involved.
    assert canonical_json(payload) == canonical_json(ontology.l1)
    assert sha256_of(ontology.l1) == recorded


def test_every_unit_is_written(tmp_path: Path) -> None:
    _build_artifacts(tmp_path)
    written = sorted(path.name for path in tmp_path.glob("*.json"))
    assert written == sorted(f"{unit}.json" for unit in UNITS)


def test_no_artifact_declares_a_combined_ontology_hash(tmp_path: Path) -> None:
    """A single digest localises nothing; five hashes are the point."""
    _build_artifacts(tmp_path)
    for unit in UNITS:
        payload = json.loads((tmp_path / f"{unit}.json").read_text(encoding="utf-8"))
        assert "combined_hash" not in payload["freeze"]
        assert payload["freeze"]["judge_dependency"].startswith("none")
