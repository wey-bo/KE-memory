"""Dependency-direction gate for the shipped packages.

The reorganization is only meaningful if the layering it creates is enforced.
These tests read the actual import graph and fail when an edge points the wrong
way, so a later change cannot quietly reintroduce the coupling the split removed.

The rules, in dependency order (each layer may import those below it, never
above):

    core, domain          -- no intra-package dependencies
    infra, storage        -- may use core/domain
    extraction, retrieval, ontology, aggregation, answering, history, snapshots
    pipeline              -- orchestration
    evaluation            -- measures the pipeline; nothing may depend on it
    cli                   -- entry point, may use anything

``evaluation`` is the important one: it existed as a subpackage that
``pipeline`` imported directly *and* that imported ``pipeline`` back, a cycle
that made "core code does not depend on measurement" untrue. Measurement may
depend on the thing measured; the reverse makes the core untestable in isolation
and drags evaluation-only concerns into production paths.
"""

from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "src" / "ke_memory_demo"

# Lower index = lower layer. A module may import from its own layer or below.
#
# ``contracts`` sits at layer 2 because the data contracts reference aggregation and
# ontology records. It is deliberately *not* inside ``pipeline``: lower layers
# (snapshots in particular) legitimately need those shapes, and routing them through
# the orchestration layer above was what created two of the cycles this gate forbids.
LAYERS: tuple[tuple[str, ...], ...] = (
    ("core", "domain"),
    ("infra", "storage"),
    (
        "aggregation",
        "contracts",
        "embedding",
        "extraction",
        "retrieval",
        "ontology",
        "ontology_v1",
        "ontology_v2",
        "ontology_sources",
        "mapper_v1",
        "mapper_v2",
        "answering",
        "history",
        "snapshots",
        "ingestion",
        "online",
        "systems",
    ),
    ("pipeline",),
    ("evaluation",),
)

# Modules that sit outside the layering: entry points and shared settings.
UNLAYERED = {"cli", "settings", "__init__"}


def _layer_of(subpackage: str) -> int | None:
    for index, names in enumerate(LAYERS):
        if subpackage in names:
            return index
    return None


def _subpackage_of(path: Path) -> str:
    relative = path.relative_to(PACKAGE_ROOT)
    return relative.parts[0] if len(relative.parts) > 1 else relative.stem


def _imported_subpackages(path: Path) -> set[str]:
    """Every ``ke_memory_demo.<sub>`` this module imports, including inside functions.

    Deferred imports count: an import inside a function is still a dependency, and
    treating it otherwise is exactly how a cycle hides from a static check.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.startswith("ke_memory_demo."):
                found.add(node.module.split(".")[1])
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("ke_memory_demo."):
                    found.add(alias.name.split(".")[1])
    return found


def _module_paths() -> list[Path]:
    return [
        path
        for path in sorted(PACKAGE_ROOT.rglob("*.py"))
        if "__pycache__" not in path.parts
    ]


def _edges() -> dict[str, set[str]]:
    edges: dict[str, set[str]] = defaultdict(set)
    for path in _module_paths():
        source = _subpackage_of(path)
        for target in _imported_subpackages(path):
            if target != source:
                edges[source].add(target)
    return edges


def test_the_package_layout_is_what_the_gate_assumes() -> None:
    """Fail loudly if a subpackage appears that no layer claims.

    Without this, adding a subpackage would silently opt it out of the gate.
    """
    present = {
        path.relative_to(PACKAGE_ROOT).parts[0]
        for path in _module_paths()
        if len(path.relative_to(PACKAGE_ROOT).parts) > 1
    }
    claimed = {name for layer in LAYERS for name in layer}
    unclaimed = sorted(present - claimed - UNLAYERED)
    assert not unclaimed, (
        f"subpackages not assigned to a layer: {unclaimed}. Assign them in LAYERS "
        "rather than leaving them ungoverned."
    )


def test_no_layer_imports_a_higher_layer() -> None:
    violations: list[str] = []
    for source, targets in sorted(_edges().items()):
        source_layer = _layer_of(source)
        if source_layer is None:
            continue  # cli/settings are unlayered by design
        for target in sorted(targets):
            target_layer = _layer_of(target)
            if target_layer is None:
                continue
            if target_layer > source_layer:
                violations.append(
                    f"{source} (layer {source_layer}) imports "
                    f"{target} (layer {target_layer})"
                )
    assert not violations, "dependency direction violated:\n  " + "\n  ".join(violations)


def test_nothing_outside_evaluation_and_cli_depends_on_evaluation() -> None:
    """Measurement must not be a dependency of the thing it measures."""
    offenders = sorted(
        source
        for source, targets in _edges().items()
        if "evaluation" in targets and source not in {"evaluation", "cli"}
    )
    assert not offenders, (
        f"these depend on evaluation: {offenders}. Core code must not import "
        "measurement code -- move the shared piece down instead."
    )


def test_there_are_no_import_cycles_between_subpackages() -> None:
    edges = _edges()
    cycles: list[str] = []
    for source, targets in sorted(edges.items()):
        for target in sorted(targets):
            if source in edges.get(target, set()) and source < target:
                cycles.append(f"{source} <-> {target}")
    assert not cycles, "import cycles between subpackages:\n  " + "\n  ".join(cycles)


@pytest.mark.parametrize("layer_zero", LAYERS[0])
def test_the_lowest_layer_depends_on_nothing_internal(layer_zero: str) -> None:
    """core and domain must stay leaf packages, or every layer above is entangled."""
    targets = {
        target
        for target in _edges().get(layer_zero, set())
        if _layer_of(target) is not None
    }
    assert not targets - set(LAYERS[0]), (
        f"{layer_zero} must not import {sorted(targets - set(LAYERS[0]))}"
    )
