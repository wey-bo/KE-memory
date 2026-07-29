from __future__ import annotations

from pathlib import Path

from tools.ontology_memory_experiment.audit import validate_audit_directory


AUDIT_DIRECTORY = (
    Path("artifacts") / "ontology-memory-experiment" / "architecture-audit"
)


def test_frozen_official_architecture_audit_is_evidence_bounded() -> None:
    audit = validate_audit_directory(AUDIT_DIRECTORY)

    assert audit.system_commits == {
        "mem0": "d653b63fac6c8ad0ad84aead0912b366e705d269",
        "graphiti": "3bb2d0bba56f8e22311574c045452c420a012f49",
        "hindsight": "ed120a256d51d731085ec8aca724573a7f2f1e1c",
        "mempalace": "8ab251c452c43f2b07a76a28f2433e258307f571",
    }
    assert audit.claim_count >= 12
    assert audit.official_source_count >= 8


def test_audit_claims_are_graded_and_traceable() -> None:
    audit = validate_audit_directory(AUDIT_DIRECTORY)

    assert audit.unsupported_confirmed_gaps == []
    assert audit.invalid_source_snapshots == []
    assert audit.invalid_claims == []
    assert all(claim.excerpt for claim in audit.claims)
    assert all(claim.source_url.startswith("https://github.com/") for claim in audit.claims)
    assert {claim.grade for claim in audit.claims} <= {
        "confirmed_capability",
        "confirmed_gap",
        "architectural_risk",
        "class_level_evidence",
    }


def test_official_results_require_full_protocol_compatibility_for_direct_table() -> None:
    audit = validate_audit_directory(AUDIT_DIRECTORY)

    assert audit.invalid_direct_comparisons == []
    assert all(
        result.comparability_status != "direct_numeric_comparison"
        or result.protocol_compatible
        for result in audit.official_results
    )
