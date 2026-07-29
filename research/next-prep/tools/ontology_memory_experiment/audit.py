"""Offline validation for the frozen official architecture-audit artifacts."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ALLOWED_GRADES = {
    "confirmed_capability",
    "confirmed_gap",
    "architectural_risk",
    "class_level_evidence",
}

REQUIRED_COMMITS = {
    "mem0": "d653b63fac6c8ad0ad84aead0912b366e705d269",
    "graphiti": "3bb2d0bba56f8e22311574c045452c420a012f49",
    "hindsight": "ed120a256d51d731085ec8aca724573a7f2f1e1c",
    "mempalace": "8ab251c452c43f2b07a76a28f2433e258307f571",
}


@dataclass(frozen=True)
class AuditClaim:
    claim_id: str
    grade: str
    source_url: str
    excerpt: str


@dataclass(frozen=True)
class OfficialResult:
    system: str
    comparability_status: str
    protocol_compatible: bool


@dataclass(frozen=True)
class AuditSummary:
    system_commits: dict[str, str]
    claims: list[AuditClaim]
    official_source_count: int
    official_results: list[OfficialResult]
    invalid_claims: list[str]
    invalid_source_snapshots: list[str]
    unsupported_confirmed_gaps: list[str]
    invalid_direct_comparisons: list[str]

    @property
    def claim_count(self) -> int:
        return len(self.claims)


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _is_official_github_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme == "https" and parsed.netloc in {
        "github.com",
        "raw.githubusercontent.com",
        "api.github.com",
    }


def validate_audit_directory(directory: Path) -> AuditSummary:
    """Validate evidence grades, frozen refs, and result comparability offline."""
    source_manifest = _load_json(directory / "source-manifest.json")
    capability_matrix = _load_json(directory / "capability-matrix.json")
    gap_ledger = _load_json(directory / "gap-hypothesis-ledger.json")
    results_ledger = _load_json(directory / "official-results-ledger.json")

    system_commits: dict[str, str] = {}
    source_ids: set[str] = set()
    source_text_by_id: dict[str, str] = {}
    invalid_claims: list[str] = []
    invalid_source_snapshots: list[str] = []
    unsupported_confirmed_gaps: list[str] = []
    source_count = 0
    for system in source_manifest.get("systems", []):
        system_id = system.get("system")
        commit = system.get("frozen_commit")
        if system_id not in REQUIRED_COMMITS or commit != REQUIRED_COMMITS[system_id]:
            invalid_claims.append(f"invalid frozen commit for {system_id}")
            continue
        system_commits[system_id] = commit
        for source in system.get("sources", []):
            source_count += 1
            source_id = source.get("source_id")
            source_ids.add(source_id)
            artifact_path = source.get("artifact_path")
            snapshot_path = directory / artifact_path if isinstance(artifact_path, str) else None
            if snapshot_path is None or not snapshot_path.is_file():
                invalid_source_snapshots.append(str(source_id))
            else:
                content = snapshot_path.read_bytes()
                expected_hash = source.get("content_hash")
                actual_hash = f"sha256:{hashlib.sha256(content).hexdigest()}"
                if expected_hash != actual_hash:
                    invalid_source_snapshots.append(str(source_id))
                try:
                    source_text_by_id[str(source_id)] = content.decode("utf-8")
                except UnicodeDecodeError:
                    invalid_source_snapshots.append(str(source_id))
                else:
                    if source.get("excerpt") not in source_text_by_id[str(source_id)]:
                        invalid_source_snapshots.append(str(source_id))
            if not (
                isinstance(source.get("excerpt"), str)
                and source["excerpt"].strip()
                and _is_official_github_url(source.get("canonical_url", ""))
                and _is_official_github_url(source.get("retrieval_url", ""))
                and source.get("immutable_ref") == commit
            ):
                invalid_claims.append(f"invalid source {source_id}")

    claims: list[AuditClaim] = []
    for record in capability_matrix.get("claims", []) + gap_ledger.get("hypotheses", []):
        claim = AuditClaim(
            claim_id=record.get("claim_id", record.get("hypothesis_id", "")),
            grade=record.get("grade", ""),
            source_url=record.get("source_url", ""),
            excerpt=record.get("excerpt", ""),
        )
        claims.append(claim)
        if (
            not claim.claim_id
            or claim.grade not in ALLOWED_GRADES
            or not claim.excerpt.strip()
            or not _is_official_github_url(claim.source_url)
            or record.get("source_id") not in source_ids
            or claim.excerpt not in source_text_by_id.get(record.get("source_id"), "")
        ):
            invalid_claims.append(claim.claim_id or "unnamed claim")
        if claim.grade == "confirmed_gap" and not record.get("explicit_unimplemented"):
            unsupported_confirmed_gaps.append(claim.claim_id)

    official_results: list[OfficialResult] = []
    invalid_direct_comparisons: list[str] = []
    for record in results_ledger.get("results", []):
        result = OfficialResult(
            system=record.get("system", ""),
            comparability_status=record.get("comparability_status", ""),
            protocol_compatible=record.get("protocol_compatible", False),
        )
        official_results.append(result)
        if (
            result.comparability_status == "direct_numeric_comparison"
            and not result.protocol_compatible
        ):
            invalid_direct_comparisons.append(result.system)

    return AuditSummary(
        system_commits=system_commits,
        claims=claims,
        official_source_count=source_count,
        official_results=official_results,
        invalid_claims=invalid_claims,
        invalid_source_snapshots=invalid_source_snapshots,
        unsupported_confirmed_gaps=unsupported_confirmed_gaps,
        invalid_direct_comparisons=invalid_direct_comparisons,
    )
