"""Gold isolation gate for the diagnostic harness.

Oracle substitution is only sound if gold cannot reach the code being measured. That
guarantee has to be structural, because the alternative is reviewer discipline, and a gold
import added to a mapper would look locally reasonable while quietly invalidating every
score the harness produces.

The rules:

- Only ``evaluation`` may import the gold-bearing modules. Production runtime, the mapper,
  extraction, retrieval, aggregation and the pipeline may not.
- Importing the pipeline must not load an oracle module at all, so an oracle cannot be
  reached from a production process even indirectly.
- A memory build input must be structurally incapable of carrying questions or gold, since
  a type-level guarantee is what two rounds of denylist filtering failed to provide.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPOSITORY_ROOT / "src" / "ke_memory_demo"

GOLD_BEARING_MODULES = (
    "ke_memory_demo.evaluation.channels",
    "ke_memory_demo.evaluation.layer_gold",
    "ke_memory_demo.evaluation.layer_oracles",
    "ke_memory_demo.evaluation.oracle_fixture",
    "ke_memory_demo.evaluation.benchmark_loaders",
    "ke_memory_demo.evaluation.regression_slice",
    "ke_memory_demo.evaluation.beam_adapter",
)

# Layers that run in production or perform the mapping under measurement. None of them may
# reach gold, directly or by re-export.
GOLD_FORBIDDEN_PACKAGES = (
    "extraction",
    "retrieval",
    "aggregation",
    "ontology",
    "pipeline",
    "storage",
    "online",
    "history",
    "snapshots",
)


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
    return found


def test_production_layers_never_import_gold_bearing_modules() -> None:
    offenders: list[str] = []
    for package in GOLD_FORBIDDEN_PACKAGES:
        package_dir = PACKAGE_ROOT / package
        if not package_dir.is_dir():
            continue
        for source in sorted(package_dir.rglob("*.py")):
            for imported in _imported_modules(source):
                if imported in GOLD_BEARING_MODULES:
                    offenders.append(f"{source.relative_to(REPOSITORY_ROOT)} imports {imported}")
    assert offenders == [], (
        "production and mapper layers must not import gold-bearing evaluation modules: "
        + "; ".join(offenders)
    )


def test_pipeline_import_does_not_load_gold_bearing_modules() -> None:
    """A production process must not reach gold even transitively."""
    probe = (
        "import sys\n"
        "import ke_memory_demo.pipeline\n"
        "import ke_memory_demo.pipeline.runtime\n"
        "leaked = sorted(\n"
        "    m for m in sys.modules\n"
        "    if m.endswith('evaluation.layer_oracles')\n"
        "    or m.endswith('evaluation.layer_gold')\n"
        "    or m.endswith('evaluation.channels')\n"
        "    or m.endswith('evaluation.oracle_fixture')\n"
        ")\n"
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
    assert result.stdout.strip() == "", (
        f"pipeline import loaded gold-bearing modules: {result.stdout.strip()}"
    )


def test_memory_build_input_cannot_carry_questions_or_gold() -> None:
    """The type-level guarantee two rounds of denylist filtering failed to provide."""
    from ke_memory_demo.evaluation.channels import MemoryBuildInput

    fields = set(MemoryBuildInput.model_fields)
    assert "questions" not in fields
    assert "gold" not in fields
    assert "labels" not in fields
    # extra="forbid" means a caller cannot add one either.
    assert MemoryBuildInput.model_config.get("extra") == "forbid"


def test_arms_accept_only_an_exact_question_type() -> None:
    """An isinstance guard admits a subclass carrying extra fields."""
    from ke_memory_demo.evaluation.channels import (
        BenchmarkQuestion,
        ChannelError,
        assert_is_question_only,
    )

    class SneakyQuestion(BenchmarkQuestion):
        answer: str = "secret"

    try:
        assert_is_question_only(
            SneakyQuestion(question_id="q", conversation_handle="c", question="q?")
        )
    except ChannelError:
        return
    raise AssertionError("a question subclass carrying an answer reached an arm")
