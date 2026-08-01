"""Classify each historical test failure into a single disposition.

The frozen ledger at ``.runs/reorg-phase1-baseline/historical-failure-ledger.json``
records 301 failing test IDs and per-category *counts*, but not the category of
each individual ID. Wave 7 needs per-entry justification, so this module
re-measures and assigns exactly one disposition per ID.

The ledger's own byte content is never rewritten. It stays as the pre-migration
diagnostic snapshot; this produces a separate disposition record that references
it by hash. Deciding a failure is archivable is a claim about a dead contract,
and a claim needs a reason attached to the specific test, not to a bucket.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "failure-disposition-record-v1"

# One disposition per failure. There is no "unclassified": the acceptance
# criterion is that none remain, so the classifier must either place an entry or
# mark it as requiring a human decision, which is itself a tracked state.
Disposition = Literal[
    "fixed_active_infrastructure",
    "fixed_active_contract",
    "install_contract_or_legitimate_skip",
    "archived_dead_contract",
    "needs_human_decision",
]

# Parametrized nodeids contain spaces and brackets ("...[case-a message b]"),
# so the id cannot be taken as the first whitespace-delimited token. pytest puts
# the optional reason after " - ", and a nodeid never contains that separator.
_FAILURE_LINE = re.compile(
    r"^(?:FAILED|ERROR)\s+(?P<test_id>.+?)(?:\s+-\s+(?P<detail>.*))?$"
)


class FailureDisposition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    test_id: str = Field(min_length=1)
    reason_category: str = Field(min_length=1)
    disposition: Disposition
    justification: str = Field(min_length=1)
    observed_detail: str = ""

    @model_validator(mode="after")
    def _archiving_needs_a_real_reason(self) -> FailureDisposition:
        if self.disposition == "archived_dead_contract" and len(self.justification) < 20:
            raise ValueError(
                f"archiving {self.test_id} requires a specific justification"
            )
        return self


class FailureDispositionRecord(BaseModel):
    """The full set of dispositions, bound to the snapshot it re-measures."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["failure-disposition-record-v1"] = SCHEMA_VERSION
    source_ledger_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_failure_ids_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    measured_at_commit: str = Field(min_length=7)
    dispositions: tuple[FailureDisposition, ...]

    @model_validator(mode="after")
    def _every_entry_is_placed(self) -> FailureDispositionRecord:
        ids = [item.test_id for item in self.dispositions]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate test_id in disposition record")
        if ids != sorted(ids):
            raise ValueError("dispositions must be sorted by test_id")
        return self

    def counts(self) -> dict[str, int]:
        return dict(Counter(item.disposition for item in self.dispositions))

    def reason_counts(self) -> dict[str, int]:
        return dict(Counter(item.reason_category for item in self.dispositions))


def parse_failure_report(text: str) -> dict[str, str]:
    """Extract ``test_id -> detail`` from a pytest ``-rf`` short summary.

    Only lines in the short-summary block are considered. Progress output and
    tracebacks can contain the same words and would otherwise inflate the count.
    """
    failures: dict[str, str] = {}
    in_summary = False
    for line in text.splitlines():
        if "short test summary info" in line:
            in_summary = True
            continue
        if not in_summary:
            continue
        if line.startswith("=") and "short test summary" not in line:
            break
        match = _FAILURE_LINE.match(line.strip())
        if match:
            failures[match.group("test_id")] = (match.group("detail") or "").strip()
    return failures


def classify_reason(detail: str) -> str:
    """Assign a root-cause category from the observed failure detail.

    Searches the whole detail, not just its first line, because a guard that
    fires early *masks* the behaviour under test: a ``pytest.raises`` expecting
    "receipt path changed" reports only "Regex pattern did not match" on its
    first line, while the real cause sits in the input it captured. Classifying
    on the first line alone attributed 43 such failures to assertion drift when
    30 were file-mode and 13 were hash drift.

    Child-process failures are the same problem one level down: the parent sees
    only a non-zero exit code, so the captured stderr must be searched too.
    """
    lowered = detail.lower()
    if "must be read-only" in lowered or "must have mode 0444" in lowered:
        return "file_mode_precondition"
    if "code hash drift" in lowered:
        return "preregistration_code_hash_drift"
    if "duckdb is required" in lowered:
        return "missing_optional_dependency_duckdb"
    if "future implementation artifact must be absent" in lowered:
        return "future_artifact_guard"
    if "must be absent" in lowered and "exists" in lowered:
        return "leftover_formal_artifact"
    return "needs_manual_inspection"


# Seven failures report an assertion that is a *consequence*, with no cause in
# their own text. Each was reproduced individually and its cause verified before
# being recorded here, so the attribution is measured rather than pattern-matched.
# Keyed by nodeid suffix because the run's nodeid prefix varies with rootdir.
_VERIFIED_BY_INSPECTION: dict[str, str] = {
    # `pytest.raises(match="mode|identity")` was satisfied by an unrelated error:
    # "fresh v3 authoring receipt must have mode 0444", reached before the staging
    # validation the test counts. Verified by calling the helper directly.
    "test_typed_extractor_fresh_v3_materialization.py::"
    "test_publish_rejects_mode_mutation_after_final_staging_validation[root]":
        "file_mode_precondition",
    "test_typed_extractor_fresh_v3_materialization.py::"
    "test_publish_rejects_mode_mutation_after_final_staging_validation[layer]":
        "file_mode_precondition",
    "test_typed_extractor_fresh_v3_materialization.py::"
    "test_publish_rejects_mode_mutation_after_final_staging_validation[file]":
        "file_mode_precondition",
    # source_validation.valid is False solely because every source revision replay
    # raises "DuckDB is required to read BEAM parquet". Verified by inspecting the
    # report's errors list.
    "test_authoritative_conformance_runner.py::"
    "test_v5_cli_resolves_sources_from_absolute_root_outside_workspace_cwd":
        "missing_optional_dependency_duckdb",
    "test_authoritative_conformance_runner.py::"
    "test_v5_conformance_separates_adapter_parity_from_frozen_correctness_and_authority":
        "missing_optional_dependency_duckdb",
    # These assert a formal evaluation root is absent, but the root was committed
    # as evidence after the test was written. Verified with `git ls-files`: both
    # targets are tracked. The assertion is stale, the artifacts are legitimate.
    "test_typed_extractor_fresh_v3_authoring.py::"
    "test_bundle_is_deterministic_and_creates_no_formal_artifact":
        "committed_evidence_contradicts_absence_assertion",
    "test_typed_extractor_fresh_v2_authoring.py::"
    "test_bundle_is_deterministic_and_does_not_mutate_formal_artifacts":
        "committed_evidence_contradicts_absence_assertion",
}


def classify_failure(nodeid: str, detail: str) -> str:
    """Classify one failure, preferring an individually verified attribution.

    A verified entry wins over the text heuristic because the heuristic reads a
    consequence: these seven report "assert 0 == 2" or "assert False is True",
    which names no cause at all.
    """
    for suffix, reason in _VERIFIED_BY_INSPECTION.items():
        if nodeid.endswith(suffix):
            return reason
    return classify_reason(detail)


_DISPOSITION_BY_REASON: dict[str, tuple[Disposition, str]] = {
    "file_mode_precondition": (
        "fixed_active_infrastructure",
        "Active test whose only defect was a non-portable read-only precondition; "
        "repaired by portable content-addressed verification, not archived.",
    ),
    "missing_optional_dependency_duckdb": (
        "install_contract_or_legitimate_skip",
        "Requires DuckDB to read BEAM parquet; resolved by declaring the install "
        "contract or by a guarded skip that states what is not covered.",
    ),
    "preregistration_code_hash_drift": (
        "fixed_active_contract",
        "Active contract binding drifted; repaired by rebinding the declared "
        "contract, never by loosening the assertion.",
    ),
    "future_artifact_guard": (
        "fixed_active_contract",
        "Guard asserting a future artifact is absent now sees it present; "
        "repaired at the guard or the artifact, whichever the contract says.",
    ),
    "leftover_formal_artifact": (
        "fixed_active_contract",
        "Test requires a formal artifact to be absent but a prior run left it; "
        "repaired by isolating the artifact root, not by relaxing the assertion.",
    ),
    "committed_evidence_contradicts_absence_assertion": (
        "fixed_active_contract",
        "Assertion that an evaluation root is absent is stale: the root was "
        "committed as evidence afterwards. Repaired at the assertion, since the "
        "frozen evidence is correct and must not be deleted to satisfy a test.",
    ),
    "needs_manual_inspection": (
        "needs_human_decision",
        "Reason not mechanically determinable from the failure detail; requires "
        "reading the test before any disposition is assigned.",
    ),
}


def build_disposition_record(
    *,
    failures: dict[str, str],
    source_ledger_sha256: str,
    source_failure_ids_sha256: str,
    measured_at_commit: str,
) -> FailureDispositionRecord:
    dispositions: list[FailureDisposition] = []
    for test_id in sorted(failures):
        detail = failures[test_id]
        reason = classify_failure(test_id, detail)
        disposition, justification = _DISPOSITION_BY_REASON[reason]
        dispositions.append(
            FailureDisposition(
                test_id=test_id,
                reason_category=reason,
                disposition=disposition,
                justification=justification,
                observed_detail=detail[:400],
            )
        )
    return FailureDispositionRecord(
        source_ledger_sha256=source_ledger_sha256,
        source_failure_ids_sha256=source_failure_ids_sha256,
        measured_at_commit=measured_at_commit,
        dispositions=tuple(dispositions),
    )


def compare_against_snapshot(
    *,
    snapshot_ids: tuple[str, ...],
    measured_ids: tuple[str, ...],
) -> dict[str, tuple[str, ...]]:
    """Separate resolved, still-failing and newly-failing tests.

    ``newly_failing`` is the one that blocks acceptance: the snapshot is allowed
    to shrink as failures are repaired, but a failure absent from the snapshot is
    damage introduced by this migration.
    """
    snapshot = set(snapshot_ids)
    measured = set(measured_ids)
    return {
        "resolved": tuple(sorted(snapshot - measured)),
        "still_failing": tuple(sorted(snapshot & measured)),
        "newly_failing": tuple(sorted(measured - snapshot)),
    }


def load_report(path: Path) -> dict[str, str]:
    return parse_failure_report(Path(path).read_text(encoding="utf-8", errors="replace"))


def load_structured_report(path: Path) -> dict[str, str]:
    """Read ``failure_report_plugin`` JSON into ``test_id -> message``.

    Preferred over ``load_report``: the plugin reads pytest's report objects, so
    nodeids are exact and every failure carries its crash message. Text parsing
    is kept only for reports captured before the plugin existed.
    """
    import json as _json

    payload = _json.loads(Path(path).read_text(encoding="utf-8"))
    return {item["nodeid"]: item.get("message", "") for item in payload["failures"]}
