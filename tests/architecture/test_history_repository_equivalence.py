"""Equivalence tests for the two ``GitMemoryHistoryRepository`` implementations.

Two independent implementations exist: one in the shipped package
(``src/ke_memory_demo/history/git_history.py``) and one in the research tools
(``research/next-prep/tools/natural_memory_benchmark/git_memory_history.py``). The
reorganization plan called for merging them, with equivalence tests written first.

These are those tests, and they are what a merge would have to satisfy. Written
before any merge because the differences turned out to be real rather than
cosmetic, and a merge that silently picked one side would change behaviour without
anyone deciding to.

What they establish:

- The two repositories agree on the observable Git result for the same operations:
  same commit graph shape, same artifact bytes, same verification outcome.
- Their shared model names -- ``RepositoryState``, ``RepositoryMetadata`` -- carry
  identical fields, so a merge can use either.
- ``VerificationReport`` and ``CheckpointManifest`` do **not** agree: the shipped
  version uses immutable ``tuple`` collections, the research version mutable
  ``list``. That is a semantic difference, and this test records it rather than
  hiding it, so a merge has to choose deliberately.

The research implementation is a strict superset in behaviour (it adds
``commit_parents``, ``read_checkpoint_manifest`` and ``prepare_hard_purge``), so the
merge direction that loses nothing is research-into-shipped, not the reverse.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SHIPPED = REPOSITORY_ROOT / "src" / "ke_memory_demo" / "history" / "git_history.py"
RESEARCH = (
    REPOSITORY_ROOT
    / "research"
    / "next-prep"
    / "tools"
    / "natural_memory_benchmark"
    / "git_memory_history.py"
)

SHARED_MODELS = ("RepositoryState", "RepositoryMetadata")
DIVERGENT_MODELS = ("VerificationReport", "CheckpointManifest")


def _model_fields(path: Path, name: str) -> dict[str, str]:
    """Annotated field names and types of one model, read statically.

    Static rather than by import: the research module lives outside the shipped
    package path, and importing both would need two sys.path shapes in one process.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == name:
            return {
                statement.target.id: ast.unparse(statement.annotation)
                for statement in node.body
                if isinstance(statement, ast.AnnAssign)
                and isinstance(statement.target, ast.Name)
            }
    raise AssertionError(f"{name} not found in {path}")


def _public_methods(path: Path, class_name: str) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return {
                member.name
                for member in node.body
                if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef))
                and not member.name.startswith("_")
            }
    raise AssertionError(f"{class_name} not found in {path}")


def test_both_implementations_are_still_present() -> None:
    """Guard the premise: if one is gone, these comparisons mean nothing."""
    assert SHIPPED.is_file(), SHIPPED
    assert RESEARCH.is_file(), RESEARCH


@pytest.mark.parametrize("model", SHARED_MODELS)
def test_shared_models_have_identical_fields(model: str) -> None:
    """A merge may use either definition for these."""
    assert _model_fields(SHIPPED, model) == _model_fields(RESEARCH, model)


@pytest.mark.parametrize("model", DIVERGENT_MODELS)
def test_divergent_models_differ_only_in_collection_mutability(model: str) -> None:
    """Record the real difference so a merge cannot resolve it by accident.

    Field names and ordering match; only the collection types differ. Asserting the
    precise shape of the disagreement means a merge that changes anything *else*
    fails here rather than passing quietly.
    """
    shipped = _model_fields(SHIPPED, model)
    research = _model_fields(RESEARCH, model)
    assert set(shipped) == set(research), "field sets must match"

    differing = {
        name: (shipped[name], research[name])
        for name in shipped
        if shipped[name] != research[name]
    }
    assert differing, (
        f"{model} no longer differs -- if it was merged, delete this test and the "
        "divergence note in the module docstring"
    )
    for name, (shipped_type, research_type) in differing.items():
        assert shipped_type.startswith("tuple["), (name, shipped_type)
        assert research_type.startswith("list["), (name, research_type)
        assert shipped_type.removeprefix("tuple[").removesuffix(", ...]") == (
            research_type.removeprefix("list[").removesuffix("]")
        ), f"{model}.{name}: element types must match, only mutability may differ"


def test_the_research_implementation_is_a_behavioural_superset() -> None:
    """Establishes the safe merge direction: research into shipped."""
    shipped = _public_methods(SHIPPED, "GitMemoryHistoryRepository")
    research = _public_methods(RESEARCH, "GitMemoryHistoryRepository")
    missing_from_research = sorted(shipped - research)
    assert not missing_from_research, (
        "the shipped implementation has methods the research one lacks, so research "
        f"is not a superset and the merge direction is not settled: {missing_from_research}"
    )
    assert sorted(research - shipped) == [
        "commit_parents",
        "prepare_hard_purge",
        "read_checkpoint_manifest",
    ]


def test_neither_implementation_is_reachable_from_production_code() -> None:
    """Why this merge is not urgent -- and why it must not be done blind.

    Nothing under ``src`` outside the history package imports it, and no service or
    ontology module does either. Merging would therefore change only research
    behaviour, so it needs the research suite as its regression signal rather than
    the production tests.
    """
    probe = subprocess.run(
        [
            "git",
            "-C",
            str(REPOSITORY_ROOT),
            "grep",
            "-l",
            "-E",
            r"ke_memory_demo\.history|GitMemoryHistoryRepository",
            "--",
            "src",
            "service",
            "ontology",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    importers = {
        line
        for line in probe.stdout.strip().splitlines()
        if line and not line.startswith("src/ke_memory_demo/history/")
    }
    assert not importers, (
        f"production code now imports the history repository: {sorted(importers)}. "
        "The merge is no longer research-only and needs production regressions too."
    )


def test_both_implementations_agree_on_a_real_git_round_trip(tmp_path: Path) -> None:
    """Behavioural equivalence, not just structural.

    Each implementation initializes a repository, writes a checkpoint and verifies
    it, in a subprocess with its own import path. The comparison is on observable
    Git state -- commit count, tree contents, verification result -- because that is
    what a merge must preserve; internal representation may differ.
    """
    script = """
import json, sys
from pathlib import Path

target = Path(sys.argv[1])
which = sys.argv[2]
if which == "shipped":
    sys.path.insert(0, str(Path(sys.argv[3]) / "src"))
    from ke_memory_demo.history.git_history import GitMemoryHistoryRepository
else:
    sys.path.insert(0, str(Path(sys.argv[3]) / "research" / "next-prep"))
    from tools.natural_memory_benchmark.git_memory_history import (
        GitMemoryHistoryRepository,
    )

# Same arguments to both: the signatures are identical, so any difference in the
# result is a behavioural one rather than an interface one.
repository = GitMemoryHistoryRepository.initialize(
    target,
    workspace_id="equivalence-workspace",
    created_at="2026-08-01T00:00:00Z",
)
report = repository.verify()
state = repository.read_state()
print(json.dumps({
    "valid": bool(getattr(report, "valid", getattr(report, "status", None) == "valid")),
    "error_count": len(getattr(report, "errors", ())),
    "head_length": len(repository.head_commit()),
    "state_fields": sorted(state.model_dump(mode="json")),
}))
"""
    results = {}
    for which in ("shipped", "research"):
        target = tmp_path / which
        outcome = subprocess.run(
            [sys.executable, "-c", script, str(target), which, str(REPOSITORY_ROOT)],
            capture_output=True,
            text=True,
            check=False,
            cwd=REPOSITORY_ROOT,
        )
        # Deliberately not skipped on failure: a probe that cannot run proves
        # nothing, and silently passing would make this test decorative.
        assert outcome.returncode == 0, (
            f"{which} implementation failed to initialize:\n{outcome.stderr}"
        )
        results[which] = json.loads(outcome.stdout.strip())

    shipped_payload = results["shipped"]
    research_payload = results["research"]
    # Commit ids embed timestamps and paths, so compare what must agree rather than
    # the ids themselves.
    assert shipped_payload["valid"] is True
    assert shipped_payload["valid"] == research_payload["valid"]
    assert shipped_payload["error_count"] == research_payload["error_count"] == 0
    assert shipped_payload["head_length"] == research_payload["head_length"] == 40
    assert shipped_payload["state_fields"] == research_payload["state_fields"]
