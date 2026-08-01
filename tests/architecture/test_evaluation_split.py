"""Regressions for the evaluation/pipeline split.

The split removed a real dependency: ``pipeline`` no longer imports ``evaluation``.
These tests hold the boundary in place, because every property below can be
reintroduced by a change that looks locally reasonable.

- A pipeline-only process must not load the evaluation package. If it does, the
  layering is nominal only, and evaluation-only dependencies become production ones.
- ``EvaluationStage`` must not hold the runtime factory. Storing it would replace the
  removed import cycle with a service locator: the stage could reach any attribute,
  the coupling would vanish from its signature, and the dependency gate would pass
  while nothing had been decoupled.
- Evaluation-run state must not live on the factory. A production runtime holding
  judge clients and a token counter it never uses is state that can leak into a
  pipeline run and confuse teardown.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPOSITORY_ROOT / "src" / "ke_memory_demo"


def test_pipeline_only_import_does_not_load_evaluation() -> None:
    """Importing the pipeline must not pull in the evaluation package.

    Run in a subprocess: this process has already imported evaluation via other
    tests, so checking ``sys.modules`` in-process would prove nothing.
    """
    probe = (
        "import sys\n"
        "import ke_memory_demo.pipeline\n"
        "import ke_memory_demo.pipeline.runtime\n"
        "leaked = sorted(m for m in sys.modules if m.startswith('ke_memory_demo.evaluation'))\n"
        "print(','.join(leaked))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=REPOSITORY_ROOT,
        env={
            "PYTHONPATH": ":".join(
                str(REPOSITORY_ROOT / part) for part in ("src", "service", "ontology")
            ),
            "PATH": "/usr/bin:/bin",
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    leaked = [name for name in result.stdout.strip().split(",") if name]
    assert not leaked, (
        f"importing the pipeline loaded evaluation modules: {leaked}. The layers are "
        "separate only if a production import stays out of the measurement package."
    )


def test_evaluation_stage_does_not_store_the_runtime_factory() -> None:
    """The stage must take a context and a port, never the factory.

    Checked structurally rather than by attribute name: a factory stored under any
    name is the same design problem.
    """
    source = (PACKAGE_ROOT / "evaluation" / "stage.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    stage = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "EvaluationStage"
    )
    init = next(
        node
        for node in stage.body
        if isinstance(node, ast.FunctionDef) and node.name == "__init__"
    )
    parameters = {argument.arg for argument in init.args.kwonlyargs}
    assert "context" in parameters and "port" in parameters, parameters
    assert "factory" not in parameters, (
        "EvaluationStage must not accept the runtime factory; pass the narrow port"
    )
    # Checked against imported and referenced names rather than the file text, so the
    # docstring may explain the history without tripping the assertion.
    imported = {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    referenced = {
        node.id for node in ast.walk(stage) if isinstance(node, ast.Name)
    } | {node.attr for node in ast.walk(stage) if isinstance(node, ast.Attribute)}
    assert "RuntimeFactory" not in imported, (
        "EvaluationStage must not import RuntimeFactory -- holding it turns the "
        "removed cycle into a service locator"
    )
    assert "RuntimeFactory" not in referenced, (
        "EvaluationStage must not reference RuntimeFactory in its body"
    )


def test_the_stage_reaches_the_pipeline_only_through_the_port() -> None:
    """Every pipeline call the stage makes must go through ``self._port``."""
    source = (PACKAGE_ROOT / "evaluation" / "stage.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    stage = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "EvaluationStage"
    )
    forwarders = {"build_ke_systems", "_snapshot_records"}
    port_calls = 0
    for node in ast.walk(stage):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Attribute):
            if getattr(node.value, "attr", None) == "_port":
                port_calls += 1
                assert node.attr in {"build_ke_systems", "snapshot_records"}, (
                    f"stage calls port.{node.attr}, which the port does not declare"
                )
    assert port_calls >= len(forwarders), (
        "the stage should reach the pipeline through the port, not by other means"
    )


def test_evaluation_run_state_is_not_on_the_runtime_factory() -> None:
    """Judge clients, token counters and promoted ids belong to the stage."""
    source = (PACKAGE_ROOT / "pipeline" / "runtime.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    factory = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "RuntimeFactory"
    )
    init = next(
        node
        for node in factory.body
        if isinstance(node, ast.FunctionDef) and node.name == "__init__"
    )
    assigned = {
        target.attr
        for statement in ast.walk(init)
        if isinstance(statement, ast.Assign)
        for target in statement.targets
        if isinstance(target, ast.Attribute)
    }
    forbidden = {"_evaluation_clients", "_evaluation_snapshot_id"}
    assert not (assigned & forbidden), (
        f"RuntimeFactory still holds evaluation-run state: {sorted(assigned & forbidden)}"
    )


def test_factory_teardown_does_not_close_evaluation_clients() -> None:
    """Each object closes what it opened, so neither can close the other's clients."""
    source = (PACKAGE_ROOT / "pipeline" / "runtime.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    factory = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "RuntimeFactory"
    )
    aclose = next(
        node
        for node in factory.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "aclose"
    )
    body = ast.unparse(aclose)
    assert "_evaluation_clients" not in body, (
        "RuntimeFactory.aclose must not close clients it did not open"
    )


def test_from_paths_does_not_name_the_evaluation_registry() -> None:
    """The evaluation artifact set is injected by the composition root, not imported."""
    source = (PACKAGE_ROOT / "pipeline" / "runtime.py").read_text(encoding="utf-8")
    assert "EVALUATION_ARTIFACT_REGISTRY" not in source, (
        "pipeline runtime must not name the evaluation registry; the composition root "
        "passes it as extra_artifact_registry"
    )
    assert "extra_artifact_registry" in source


def test_runtime_context_is_immutable() -> None:
    """The context identifies the run being measured, so the stage cannot rewrite it."""
    import pytest
    from pydantic import ValidationError

    from ke_memory_demo.pipeline.ports import RuntimeContext

    context = RuntimeContext(state_root=Path("/tmp/state"), code_commit="a" * 40)
    with pytest.raises(ValidationError):
        context.code_commit = "b" * 40  # type: ignore[misc]


def test_the_runtime_factory_satisfies_the_evaluation_port() -> None:
    """Structural conformance, so the pipeline never imports the port to declare it."""
    from ke_memory_demo.pipeline.ports import EvaluationPort
    from ke_memory_demo.pipeline.runtime import RuntimeFactory

    for method in ("build_ke_systems", "snapshot_records"):
        assert hasattr(RuntimeFactory, method), method
        assert method in EvaluationPort.__annotations__ or hasattr(
            EvaluationPort, method
        ), method
