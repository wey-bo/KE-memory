from __future__ import annotations

import ast
from pathlib import Path
import sys
import tomllib


ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOTS = (
    "src/ke_memory_demo",
    "service/ke_memory_service",
    "ontology/ke_memory_ontology",
    "memory_assertion/memory_assertion_v1",
)
SERVICE_COMPATIBILITY_FACADES = {
    "src/ke_memory_demo/online/api.py",
    "src/ke_memory_demo/online/factory.py",
}
# The memory-assertion/v1 contract layer depends on pydantic and nothing else in this
# repository. The direction is the point: the runtime is meant to migrate toward this
# contract, and a contract that imported the runtime it constrains could not serve as
# that target. So this is checked rather than merely intended.
CONTRACT_ROOT = "memory_assertion"
FORBIDDEN_CONTRACT_IMPORTS = ("ke_memory_demo", "ke_memory_service", "ke_memory_ontology")


def main() -> int:
    failures: list[str] = []
    with (ROOT / "pyproject.toml").open("rb") as stream:
        config = tomllib.load(stream)
    configured = config["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"]
    if configured != list(PACKAGE_ROOTS):
        failures.append(f"wheel packages do not match architecture: {configured}")

    for package_root in PACKAGE_ROOTS:
        if not (ROOT / package_root / "__init__.py").is_file():
            failures.append(f"missing package root: {package_root}")

    for root_name in ("src", "ontology"):
        for path in (ROOT / root_name).rglob("*.py"):
            relative = path.relative_to(ROOT).as_posix()
            if relative in SERVICE_COMPATIBILITY_FACADES:
                continue
            imports = _imports(path)
            if any(_is_service_import(name) for name in imports):
                failures.append(f"forbidden service dependency: {relative}")

    for path in (ROOT / CONTRACT_ROOT).rglob("*.py"):
        relative = path.relative_to(ROOT).as_posix()
        for name in _imports(path):
            root = name.split(".", 1)[0]
            if root in FORBIDDEN_CONTRACT_IMPORTS:
                failures.append(f"contract layer depends on the runtime: {relative} -> {name}")

    if failures:
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1
    print("repository layout valid")
    return 0


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def _is_service_import(name: str) -> bool:
    return name == "ke_memory_service" or name.startswith("ke_memory_service.")


if __name__ == "__main__":
    raise SystemExit(main())
