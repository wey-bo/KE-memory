"""Declare and verify the evaluation environment contract.

DuckDB reads the BEAM parquet that source replay resolves against, so source
validation -- part of the evidence chain -- cannot run without it. The dependency
is therefore required rather than optional *for conformance*, and its absence
must fail rather than skip: a skipped source-replay test leaves the data replay
path unverified while reporting green.

It stays out of the core runtime. The production wheel must not carry an
evaluation reader, so it is declared in the ``evaluation`` dependency group and
imported only by evaluation and conformance code.

A conformance result also names the reader that produced it. Parquet decoding
behaviour belongs to the DuckDB build, so the engine version and the parquet
extension's install mode are recorded alongside the Python version.
"""

from __future__ import annotations

import platform
import sys
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "evaluation-environment-report-v1"

# Pinned, not ranged: a range would let two conformance runs disagree while both
# claim to satisfy the contract. Must match pyproject's evaluation group.
REQUIRED_DUCKDB_VERSION = "1.5.5"


class EvaluationDependencyMissing(RuntimeError):
    """Raised when a required evaluation dependency is absent.

    Deliberately not ``pytest.skip``. The rule this enforces is that conformance
    either runs or fails; a skip would hide an unverified replay path behind a
    green summary.
    """


class EvaluationEnvironmentReport(BaseModel):
    """What actually produced a conformance result."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["evaluation-environment-report-v1"] = SCHEMA_VERSION
    python_version: str = Field(min_length=1)
    platform_machine: str = Field(min_length=1)
    platform_system: str = Field(min_length=1)
    duckdb_module_version: str = Field(min_length=1)
    duckdb_engine_version: str = Field(min_length=1)
    parquet_extension_install_mode: str = Field(min_length=1)


def require_duckdb() -> object:
    """Import DuckDB or fail with the install contract.

    The message names the group to install because the failure a reader most
    needs to act on is "this environment was never provisioned for conformance",
    not "module not found".
    """
    try:
        import duckdb
    except ImportError as error:
        raise EvaluationDependencyMissing(
            "DuckDB is required for evaluation and conformance (source replay reads "
            "BEAM parquet). Install the evaluation dependency group: "
            f"`uv pip install duckdb=={REQUIRED_DUCKDB_VERSION}`. "
            "Conformance must not be skipped when it is absent: the outcome is "
            "conformance_not_verified."
        ) from error
    return duckdb


def describe_evaluation_environment() -> EvaluationEnvironmentReport:
    """Measure the live environment. Never reports a declared value as observed."""
    duckdb = require_duckdb()
    connection = duckdb.connect()  # type: ignore[attr-defined]
    try:
        engine_version = connection.execute("SELECT version()").fetchone()[0]
        row = connection.execute(
            "SELECT install_mode FROM duckdb_extensions() "
            "WHERE extension_name = 'parquet'"
        ).fetchone()
        install_mode = row[0] if row else "UNKNOWN"
    finally:
        connection.close()
    return EvaluationEnvironmentReport(
        python_version=sys.version.split()[0],
        platform_machine=platform.machine(),
        platform_system=platform.system(),
        duckdb_module_version=duckdb.__version__,  # type: ignore[attr-defined]
        duckdb_engine_version=str(engine_version),
        parquet_extension_install_mode=str(install_mode),
    )


def verify_evaluation_environment() -> EvaluationEnvironmentReport:
    """Fail closed if the installed version is not the pinned one.

    An unpinned reader version makes a conformance result unreproducible, so a
    mismatch is a contract violation rather than a warning.
    """
    report = describe_evaluation_environment()
    if report.duckdb_module_version != REQUIRED_DUCKDB_VERSION:
        raise EvaluationDependencyMissing(
            f"evaluation contract pins duckdb=={REQUIRED_DUCKDB_VERSION} but "
            f"{report.duckdb_module_version} is installed; a conformance result "
            "must name the reader version that produced it"
        )
    return report
