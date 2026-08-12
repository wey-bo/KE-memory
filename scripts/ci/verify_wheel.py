from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[2]
PACKAGE_NAMES = (
    "ke_memory_demo",
    "ke_memory_service",
    "ke_memory_ontology",
    "memory_assertion_v1",
)


def main() -> int:
    wheel = _latest_wheel(ROOT / "dist")
    failures = _missing_packages(wheel)
    if failures:
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory(prefix="ke-memory-wheel-") as temp_dir:
        result = subprocess.run(
            [sys.executable, "-I", "-c", _import_probe(), str(wheel)],
            cwd=temp_dir,
            check=False,
            text=True,
            capture_output=True,
        )
    if result.returncode != 0:
        print(result.stdout, end="", file=sys.stderr)
        print(result.stderr, end="", file=sys.stderr)
        return result.returncode

    print(f"wheel artifact valid: {wheel.name}")
    print(result.stdout, end="")
    return 0


def _latest_wheel(dist_dir: Path) -> Path:
    wheels = sorted(dist_dir.glob("*.whl"), key=lambda path: path.stat().st_mtime)
    if not wheels:
        raise SystemExit("no wheel artifact found under dist/")
    return wheels[-1].resolve()


def _missing_packages(wheel: Path) -> list[str]:
    with zipfile.ZipFile(wheel) as archive:
        members = set(archive.namelist())
    return [
        f"wheel is missing package: {package_name}"
        for package_name in PACKAGE_NAMES
        if f"{package_name}/__init__.py" not in members
    ]


def _import_probe() -> str:
    package_names = repr(PACKAGE_NAMES)
    return f"""
import importlib
from pathlib import Path
import sys

wheel = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(wheel))
for package_name in {package_names}:
    module = importlib.import_module(package_name)
    origin = Path(module.__file__).as_posix()
    if not origin.startswith(wheel.as_posix() + "/"):
        raise RuntimeError(f"{{package_name}} imported outside wheel: {{origin}}")
    print(f"imported {{package_name}} from {{origin}}")
"""


if __name__ == "__main__":
    raise SystemExit(main())
