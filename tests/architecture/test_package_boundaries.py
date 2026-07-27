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
)
SERVICE_COMPATIBILITY_FACADES = {
    "src/ke_memory_demo/online/api.py",
    "src/ke_memory_demo/online/factory.py",
}


def test_layer_packages_are_importable() -> None:
    assert import_module("ke_memory_service")
    assert import_module("ke_memory_ontology")


def test_wheel_configuration_contains_all_layer_packages() -> None:
    with (ROOT / "pyproject.toml").open("rb") as stream:
        config = tomllib.load(stream)

    packages = config["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"]
    assert packages == [
        "src/ke_memory_demo",
        "service/ke_memory_service",
        "ontology/ke_memory_ontology",
    ]


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
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return {
        name
        for name in imports
        if name == "ke_memory_service" or name.startswith("ke_memory_service.")
    }
