from __future__ import annotations

import ast
from importlib import import_module
from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOTS = (
    ROOT / "src" / "ke_memory_demo",
    ROOT / "service" / "ke_memory_service",
    ROOT / "ontology" / "ke_memory_ontology",
    ROOT / "memory_assertion" / "memory_assertion_v1",
)
SERVICE_COMPATIBILITY_FACADES = {
    "src/ke_memory_demo/online/api.py",
    "src/ke_memory_demo/online/factory.py",
}
# The memory-assertion/v1 contract layer must not import the runtime it constrains. The
# runtime is meant to migrate toward this contract, which it could not be if the contract
# depended on it.
CONTRACT_ROOT = ROOT / "memory_assertion"
FORBIDDEN_CONTRACT_IMPORTS = ("ke_memory_demo", "ke_memory_service", "ke_memory_ontology")


def test_layer_packages_are_importable() -> None:
    assert import_module("ke_memory_service")
    assert import_module("ke_memory_ontology")
    assert import_module("memory_assertion_v1")


def test_wheel_configuration_contains_all_layer_packages() -> None:
    with (ROOT / "pyproject.toml").open("rb") as stream:
        config = tomllib.load(stream)

    packages = config["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"]
    assert packages == [
        "src/ke_memory_demo",
        "service/ke_memory_service",
        "ontology/ke_memory_ontology",
        "memory_assertion/memory_assertion_v1",
    ]


def test_contract_layer_does_not_depend_on_the_runtime() -> None:
    """Asserted here as well as in verify_layout.py, and for a different reason.

    The script gates CI; this gates the test suite, which is what a developer runs before
    pushing. A dependency that only the remote catches is one that has already been
    written.
    """
    offenders = {
        path.relative_to(ROOT).as_posix(): sorted(names)
        for path in CONTRACT_ROOT.rglob("*.py")
        if (names := _runtime_imports(path))
    }
    assert offenders == {}


def test_python_package_directories_are_explicit() -> None:
    missing = sorted(
        {
            path.parent.relative_to(ROOT).as_posix()
            for package_root in PACKAGE_ROOTS
            for path in package_root.rglob("*.py")
            if path.name != "__init__.py"
            if not (path.parent / "__init__.py").is_file()
        }
    )
    assert missing == []


def test_core_and_ontology_do_not_depend_on_service_layer() -> None:
    offenders = {
        path.relative_to(ROOT).as_posix(): sorted(_service_imports(path))
        for root in (ROOT / "src", ROOT / "ontology")
        if root.exists()
        for path in root.rglob("*.py")
        if path.relative_to(ROOT).as_posix() not in SERVICE_COMPATIBILITY_FACADES
        if _service_imports(path)
    }
    assert offenders == {}


def _service_imports(path: Path) -> set[str]:
    return {
        name
        for name in _imports(path)
        if name == "ke_memory_service" or name.startswith("ke_memory_service.")
    }


def _runtime_imports(path: Path) -> set[str]:
    return {
        name
        for name in _imports(path)
        if name.split(".", 1)[0] in FORBIDDEN_CONTRACT_IMPORTS
    }


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports
