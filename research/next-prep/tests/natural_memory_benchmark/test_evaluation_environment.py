"""Tests for the evaluation dependency contract.

The rule under test is that a missing evaluation dependency *fails* rather than
skips. A skip would report green while leaving the source replay path
unverified, which is the specific outcome the install contract exists to
prevent.
"""

from __future__ import annotations

import builtins
import sys

import pytest

from tools.natural_memory_benchmark import evaluation_environment
from tools.natural_memory_benchmark.evaluation_environment import (
    REQUIRED_DUCKDB_VERSION,
    EvaluationDependencyMissing,
    describe_evaluation_environment,
    require_duckdb,
    verify_evaluation_environment,
)


def test_missing_duckdb_raises_instead_of_skipping(monkeypatch) -> None:
    real_import = builtins.__import__

    def blocked(name: str, *args: object, **kwargs: object) -> object:
        if name == "duckdb":
            raise ImportError("No module named 'duckdb'")
        return real_import(name, *args, **kwargs)

    monkeypatch.delitem(sys.modules, "duckdb", raising=False)
    monkeypatch.setattr(builtins, "__import__", blocked)

    with pytest.raises(EvaluationDependencyMissing) as error:
        require_duckdb()
    message = str(error.value)
    assert "evaluation dependency group" in message
    assert REQUIRED_DUCKDB_VERSION in message
    assert "conformance_not_verified" in message


def test_missing_dependency_is_not_a_skip_exception() -> None:
    """Guard against a future refactor turning the failure into a skip.

    A skip is invisible in a green summary, so this asserts the failure cannot be
    swallowed by ``pytest.raises(Skipped)`` or reported as a skip: the exception
    must be unrelated to pytest's skip signal in both directions.
    """
    from _pytest.outcomes import Skipped

    assert issubclass(EvaluationDependencyMissing, RuntimeError)
    assert not issubclass(EvaluationDependencyMissing, Skipped)
    assert not issubclass(Skipped, EvaluationDependencyMissing)

    # And a raised instance must not be collected as a skip by pytest.
    with pytest.raises(EvaluationDependencyMissing):
        raise EvaluationDependencyMissing("boom")


def test_environment_report_is_measured_not_declared() -> None:
    report = describe_evaluation_environment()
    assert report.duckdb_engine_version.lstrip("v").startswith(
        report.duckdb_module_version.split("+")[0]
    ), (report.duckdb_engine_version, report.duckdb_module_version)
    assert report.python_version == sys.version.split()[0]
    # Parquet decoding belongs to the DuckDB build, so its provenance is recorded.
    assert report.parquet_extension_install_mode in {
        "STATICALLY_LINKED",
        "REPOSITORY",
        "CUSTOM_PATH",
        "UNKNOWN",
    }


def test_version_mismatch_fails_closed(monkeypatch) -> None:
    """An unpinned reader makes a conformance result unreproducible."""
    real = describe_evaluation_environment()
    drifted = real.model_copy(update={"duckdb_module_version": "0.0.1"})
    monkeypatch.setattr(
        evaluation_environment, "describe_evaluation_environment", lambda: drifted
    )
    with pytest.raises(EvaluationDependencyMissing) as error:
        verify_evaluation_environment()
    assert REQUIRED_DUCKDB_VERSION in str(error.value)
    assert "0.0.1" in str(error.value)


def test_installed_version_satisfies_the_pin() -> None:
    """The live environment must match the declared contract."""
    report = verify_evaluation_environment()
    assert report.duckdb_module_version == REQUIRED_DUCKDB_VERSION


def test_pin_matches_pyproject() -> None:
    """A pin declared in two places drifts; assert they agree."""
    from pathlib import Path

    # Walk up rather than counting parents: this test file's depth changes when
    # tests are relocated, and a hard-coded index would then read the wrong file
    # or pass vacuously.
    start = Path(__file__).resolve()
    for candidate in start.parents:
        manifest = candidate / "pyproject.toml"
        if manifest.is_file() and "[project.scripts]" in manifest.read_text(
            encoding="utf-8"
        ):
            text = manifest.read_text(encoding="utf-8")
            break
    else:
        raise AssertionError(f"no root pyproject.toml found above {start}")
    assert f'duckdb=={REQUIRED_DUCKDB_VERSION}' in text, (
        "pyproject evaluation group must pin the same version as the code contract"
    )
    # And it must not have leaked into the shipped runtime dependencies.
    runtime_block = text.split("[project.scripts]")[0]
    assert "duckdb" not in runtime_block, (
        "duckdb must stay out of [project.dependencies]: the production wheel "
        "must not carry an evaluation reader"
    )
