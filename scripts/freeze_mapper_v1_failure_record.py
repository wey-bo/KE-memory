"""Freeze the mapper v1 failure record and retire its 18 cases to regression use.

Two things are being locked here.

The failures are recorded as evidence rather than as a score. The interesting result is not 7 of 18;
it is that all four negative cases were mis-mapped, which means the mapper almost never declines an
irrelevant expression. That is a degenerate behaviour and it has to be removed before any fresh
benchmark, independently of what the accuracy figure looks like afterwards.

The 18 cases are retired as a qualification set. They were composed by reading ontology items, so
they are a controlled probe: they can show that a mapper stopped doing something it used to do, and
they cannot show how mapping performs on natural expression. Keeping them as a pass gate would let a
later mapper be tuned against the very cases that defined it.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from ke_memory_demo.core.json import canonical_json

VALIDATION_REPORT = Path("artifacts/mapper-v1/blind-validation-report.json")
RAW_RECORDS = Path("artifacts/mapper-v1/raw-mapping-records.json")
OUTPUT = Path("artifacts/mapper-v1/failure-record-frozen.json")


def main() -> int:
    report = json.loads(VALIDATION_REPORT.read_text(encoding="utf-8"))
    raw = json.loads(RAW_RECORDS.read_text(encoding="utf-8"))

    per_case = report["attribution"]["per_case"]
    failures = [case for case in per_case if not case["correct"]]

    negatives = [c for c in per_case if c["expected_outcome"] == "unresolved"]
    negatives_mismapped = [c for c in negatives if not c["correct"]]

    # Group failures by the classes their evidence admits, keeping every class rather than reducing
    # to one owner.
    by_class: dict[str, list[str]] = {}
    for case in failures:
        for name in case["possible_classes"]:
            by_class.setdefault(name, []).append(case["case_id"])

    record: dict[str, Any] = {
        "stage": "mapper-v1-failure-record",
        "status": "frozen",
        "mapper_identity": report["mapper_identity"],
        "mapper_freeze_hash": report["mapper_freeze_hash"],
        "source_reports": {
            "validation_report_sha256": hashlib.sha256(
                VALIDATION_REPORT.read_bytes()
            ).hexdigest(),
            "raw_records_sha256": hashlib.sha256(RAW_RECORDS.read_bytes()).hexdigest(),
        },
        "headline": {
            "correct": report["overall"]["correct"],
            "cases": report["overall"]["cases"],
            "negatives": len(negatives),
            "negatives_mismapped": len(negatives_mismapped),
            "negatives_mismapped_ids": [c["case_id"] for c in negatives_mismapped],
        },
        "primary_finding": {
            "defect": "the mapper almost never declines an irrelevant expression",
            "evidence": (
                f"{len(negatives_mismapped)} of {len(negatives)} negative cases were mapped to an "
                "ontology item when the correct behaviour was to decline"
            ),
            "why_it_matters": (
                "a mapper without a working abstain path cannot be measured on natural conversation, "
                "where most turns evoke nothing. Running a fresh benchmark first would reproduce a "
                "conclusion already in hand."
            ),
            "must_be_fixed_before": "any fresh benchmark, independently of the accuracy figure",
            "fix_scope": (
                "candidate generation, ranking, ambiguity handling and a native no-map/abstain path, "
                "derived from discovery data"
            ),
        },
        "failures_by_possible_class": {
            name: sorted(ids) for name, ids in sorted(by_class.items())
        },
        "failures": failures,
        "raw_records_preserved": {
            "note": (
                "the raw mapper output is retained unmodified so a later mapper can be compared "
                "against what this one actually produced"
            ),
            "record_count": len(raw["records"]),
        },
        "retirement": {
            "cases_retired": report["overall"]["cases"],
            "future_use": "regression only",
            "never_again": [
                "fresh qualification",
                "a pass gate for any mapper version",
                "a source of aliases, thresholds or special cases",
            ],
            "reason": (
                "the cases were composed by reading ontology items, which makes them a controlled "
                "probe. Tuning a later mapper against them would fit the probe rather than repair "
                "the mapper, and would leave natural mapping quality still unmeasured."
            ),
        },
        "what_this_does_not_establish": [
            "mapping quality on natural expression",
            "that the ontology is adequate; it is still a 67 and 20 item seed",
            "any production capability",
        ],
        "judge": "not called",
    }
    record["record_sha256"] = hashlib.sha256(
        canonical_json({k: v for k, v in record.items()})
    ).hexdigest()

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(record, indent=1, sort_keys=True), encoding="utf-8")

    head = record["headline"]
    print(f"frozen: {head['correct']}/{head['cases']} correct")
    print(
        f"primary finding: {head['negatives_mismapped']}/{head['negatives']} negatives mis-mapped "
        "(the mapper does not decline)"
    )
    print("failures by possible class (no forced owner):")
    for name, ids in record["failures_by_possible_class"].items():
        print(f"  {name:<38} {len(ids)}")
    print(f"retired to: {record['retirement']['future_use']}")
    print(f"record sha256: {record['record_sha256'][:16]}")
    print(f"artifact: {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
