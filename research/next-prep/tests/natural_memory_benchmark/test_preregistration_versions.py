"""Tests for the append-only preregistration version registry.

Five properties are asserted, each because violating it would let a rebinding
launder something it should not:

- v1's bytes and its original drift report are unchanged, so the historical
  record still says what it said.
- v2's 11 bindings self-verify against the current code.
- v1 and v2 cannot impersonate each other.
- an old run may only use v1, a future run only v2.
- the producer contract and extraction profile hashes do not move, because a
  preregistration refresh touches none of what they cover.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from tools.natural_memory_benchmark import typed_extractor_fresh_v3_authoring as authoring
from tools.natural_memory_benchmark.portable_immutability import sha256_bytes
from tools.natural_memory_benchmark.preregistration_versions import (
    REORG_BASELINE_COMMIT,
    V1_DIRECTORY,
    V2_DIRECTORY,
    CodeBindingDisposition,
    PreregistrationVersion,
    PreregistrationVersionRegistry,
    load_code_bindings,
    sha256_path,
)

ASSESSMENT_ROOT = (
    Path(__file__).resolve().parents[2] / "artifacts" / "automatic-extraction-assessment"
)
V1_PATH = ASSESSMENT_ROOT / V1_DIRECTORY / "preregistration.json"
V2_PATH = ASSESSMENT_ROOT / V2_DIRECTORY / "preregistration.json"
REGISTRY_PATH = ASSESSMENT_ROOT / V2_DIRECTORY / "version-registry.json"

# The v1 digest as frozen. Hard-coded so a rewrite of v1 fails here rather than
# being silently re-measured into agreement with itself.
V1_SHA256 = "183cf6fc2991361e5da57b17e06a5970f651000986d50b87e8af2e6796440204"


def _registry() -> PreregistrationVersionRegistry:
    return PreregistrationVersionRegistry.model_validate(
        json.loads(REGISTRY_PATH.read_bytes())
    )


def test_v1_bytes_are_unchanged() -> None:
    """v1 is append-only: registering v2 must not have touched it."""
    assert sha256_bytes(V1_PATH.read_bytes()) == V1_SHA256
    # The module constant still points at v1, so historical loading is unaffected.
    assert authoring.PREREGISTRATION_SHA256 == V1_SHA256


def test_v1_still_reports_its_original_drift() -> None:
    """The two preexisting drifted bindings must remain visible in v1.

    If v2's rebinding had been applied to v1, this drift would vanish and the
    record would claim a consistency that never existed at the baseline.
    """
    v1_bindings = load_code_bindings(V1_PATH)
    code_paths = authoring._preregistration_code_paths(authoring.WORKSPACE_ROOT)
    drifted = {
        name
        for name, bound in v1_bindings.items()
        if sha256_path(code_paths[name]) != bound
    }
    assert drifted, "v1 must still report drift against current code"

    registry = _registry()
    preexisting = {
        item.file_name
        for item in registry.dispositions
        if item.cause in {"preexisting_historical_drift", "preexisting_and_migration"}
    }
    assert preexisting <= drifted
    assert preexisting == {"typed_extractor_l1.py", "typed_extractor_l2.py"}


def test_v2_code_bindings_self_verify() -> None:
    """All 11 of v2's bindings must match the current bytes on disk."""
    registry = _registry()
    v2 = registry.version("v2")
    assert len(v2.code_sha256) == 11
    code_paths = authoring._preregistration_code_paths(authoring.WORKSPACE_ROOT)
    assert set(code_paths) == set(v2.code_sha256)
    for name, expected in sorted(v2.code_sha256.items()):
        assert sha256_path(code_paths[name]) == expected, name
    # And the registry's recorded digest must be the file's actual digest.
    assert v2.preregistration_sha256 == sha256_bytes(V2_PATH.read_bytes())


def test_v1_and_v2_cannot_impersonate_each_other() -> None:
    registry = _registry()
    v1, v2 = registry.version("v1"), registry.version("v2")
    assert v1.preregistration_sha256 != v2.preregistration_sha256
    assert v1.directory != v2.directory
    assert sha256_bytes(V1_PATH.read_bytes()) != sha256_bytes(V2_PATH.read_bytes())
    # v2 names the version it supersedes, by hash, so the chain is checkable.
    v2_payload = json.loads(V2_PATH.read_bytes())
    assert v2_payload["supersedes_preregistration_sha256"] == V1_SHA256
    # v1 carries no forward pointer in its bytes -- it predates v2 and was not edited.
    assert "supersedes_preregistration_sha256" not in json.loads(V1_PATH.read_bytes())


def test_registry_refuses_a_v2_that_reuses_the_v1_directory() -> None:
    """Writing v2 over v1's directory would destroy the historical record."""
    registry = _registry()
    v1, v2 = registry.version("v1"), registry.version("v2")
    with pytest.raises(ValidationError, match="own directory"):
        PreregistrationVersionRegistry(
            baseline_commit=REORG_BASELINE_COMMIT,
            versions=(v1, v2.model_copy(update={"directory": v1.directory})),
            dispositions=registry.dispositions,
        )


def test_registry_refuses_byte_identical_versions() -> None:
    """A v2 identical to v1 is not a new version, it is a duplicate claim.

    Without this, a rebinding that changed nothing could still be registered as
    superseding v1, implying the drift had been addressed when it had not.
    """
    registry = _registry()
    v1, v2 = registry.version("v1"), registry.version("v2")
    with pytest.raises(ValidationError, match="byte-identical"):
        PreregistrationVersionRegistry(
            baseline_commit=REORG_BASELINE_COMMIT,
            versions=(
                v1,
                v2.model_copy(
                    update={"preregistration_sha256": v1.preregistration_sha256}
                ),
            ),
            dispositions=registry.dispositions,
        )


def test_old_runs_use_v1_and_future_runs_use_v2() -> None:
    registry = _registry()
    assert registry.version("v1").usable_by == "historical_runs_only"
    assert registry.version("v1").superseded_by == "v2"
    assert registry.version("v2").usable_by == "future_runs_only"
    assert registry.version("v2").superseded_by is None


def test_registry_refuses_inverted_usability() -> None:
    """A future run must not be scored against the superseded bindings."""
    registry = _registry()
    v1, v2 = registry.version("v1"), registry.version("v2")
    with pytest.raises(ValidationError):
        PreregistrationVersionRegistry(
            baseline_commit=REORG_BASELINE_COMMIT,
            versions=(
                v1.model_copy(update={"usable_by": "future_runs_only"}),
                v2.model_copy(update={"usable_by": "historical_runs_only"}),
            ),
            dispositions=registry.dispositions,
        )


def test_every_bound_file_has_a_disposition_with_a_measured_cause() -> None:
    registry = _registry()
    assert len(registry.dispositions) == 11
    # 7 changed by this session's repairs, 2 unchanged, and 2 that had already
    # drifted at the baseline *and* changed again -- recorded as both causes rather
    # than folded into either one.
    assert registry.cause_counts() == {
        "no_drift": 2,
        "portable_guard_migration": 7,
        "preexisting_and_migration": 2,
    }
    assert sum(registry.cause_counts().values()) == 11
    for item in registry.dispositions:
        assert len(item.justification) >= 20, item.file_name


def test_a_cause_that_contradicts_its_measurement_is_refused() -> None:
    """The cause is not a free-text label: it must match the three hashes."""
    digest_a, digest_b = "a" * 64, "b" * 64
    with pytest.raises(ValidationError, match="no_drift contradicts"):
        CodeBindingDisposition(
            file_name="x.py",
            v1_bound_sha256=digest_a,
            sha256_at_baseline_commit=digest_a,
            sha256_now=digest_b,
            cause="no_drift",
            justification="claims nothing changed while the bytes clearly did",
        )
    with pytest.raises(ValidationError, match="migration drift must match at baseline"):
        CodeBindingDisposition(
            file_name="x.py",
            v1_bound_sha256=digest_a,
            sha256_at_baseline_commit=digest_b,
            sha256_now=digest_b,
            cause="portable_guard_migration",
            justification="blames the migration for drift that predates it",
        )


def test_preregistration_refresh_does_not_move_the_contract_or_profile_hash() -> None:
    """A preregistration binds source files; contracts bind prompt/schema/policy.

    These are separate scopes, and the frozen baseline record is the reference:
    if a rebinding moved either hash, the rebinding changed something it had no
    business changing.
    """
    baseline = json.loads(
        (
            Path("/public/home/wwb/KE_mem/ke-memory-demo/.runs/reorg-phase1-baseline")
            / "frozen-hashes.json"
        ).read_bytes()
    )
    assert baseline["profile_sha256"] == (
        "80a2f4723d801931dfce2239d7d9940292da59d6ccd16bdebadccbbdaefe7787"
    )
    assert baseline["producer_contract_production_sha256"].startswith("fa1bb7b4")
    assert baseline["producer_contract_qualification_sha256"].startswith("07d6e0dd")
    assert baseline["c_to_d_transfer_status"] == "not_yet_proven"

    # And the v2 preregistration must not carry contract or profile material at all.
    v2_payload = json.loads(V2_PATH.read_bytes())
    for forbidden in ("producer_contract_sha256", "profile_sha256"):
        assert forbidden not in v2_payload, (
            f"a preregistration must not bind {forbidden}: that is a contract concern"
        )


def test_version_must_bind_at_least_one_file() -> None:
    registry = _registry()
    with pytest.raises(ValidationError):
        PreregistrationVersion(
            version="v2",
            directory=V2_DIRECTORY,
            preregistration_sha256=registry.version("v2").preregistration_sha256,
            evaluation_id="typed-extractor-v3-fresh-hidden-v1",
            code_sha256={},
            usable_by="future_runs_only",
        )
