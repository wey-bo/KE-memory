from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .io import load_json, write_json_immutable


def _preview(text: str, *, limit: int = 220) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1] + "…"


def build_projection_trace_report(projection: dict[str, Any]) -> dict[str, Any]:
    evidence_by_id = {evidence["id"]: evidence for evidence in projection.get("evidence", [])}
    traces: list[dict[str, Any]] = []
    broken_refs: list[dict[str, str]] = []
    assertions_with_evidence = 0
    assertions_with_derived = 0

    for assertion in projection.get("assertions", []):
        evidence_trace = []
        for evidence_id in assertion.get("evidence_ids", []):
            evidence = evidence_by_id.get(evidence_id)
            if evidence is None:
                broken_refs.append({"assertion_id": assertion["id"], "evidence_id": evidence_id})
                continue
            evidence_trace.append(
                {
                    "evidence_id": evidence_id,
                    "semantic_ir_evidence_id": evidence.get("metadata", {}).get("semantic_ir_evidence_id"),
                    "source_file": evidence.get("source_file"),
                    "source_chunk_id": evidence.get("source_chunk_id"),
                    "quote_preview": _preview(evidence.get("quote", "")),
                    "content_hash": evidence.get("content_hash"),
                }
            )
        if evidence_trace:
            assertions_with_evidence += 1
        if assertion.get("derived_from_assertion_ids"):
            assertions_with_derived += 1
        traces.append(
            {
                "assertion_id": assertion["id"],
                "semantic_ir_unit_id": assertion.get("metadata", {}).get("semantic_ir_unit_id"),
                "semantic_ir_level": assertion.get("metadata", {}).get("semantic_ir_level"),
                "status": assertion.get("status"),
                "evidence_ids": list(assertion.get("evidence_ids", [])),
                "derived_from_assertion_ids": list(assertion.get("derived_from_assertion_ids", [])),
                "evidence_trace": evidence_trace,
                "missing_evidence_ids": [
                    evidence_id
                    for evidence_id in assertion.get("evidence_ids", [])
                    if evidence_id not in evidence_by_id
                ],
            }
        )

    return {
        "schema_version": "semantic-ir-keol-trace-report-v1",
        "scope": "Assertion -> Evidence -> source quote trace; no KEOL baseline mutation",
        "projection_schema_version": projection.get("schema_version"),
        "projection_metadata": projection.get("metadata", {}),
        "metrics": {
            "assertion_count": len(projection.get("assertions", [])),
            "assertions_with_evidence_count": assertions_with_evidence,
            "assertions_with_derived_provenance_count": assertions_with_derived,
            "broken_evidence_ref_count": len(broken_refs),
        },
        "broken_evidence_refs": broken_refs,
        "assertion_traces": traces,
    }


def render_projection_trace_markdown(payload: dict[str, Any]) -> str:
    metrics = payload["metrics"]
    lines = [
        "# Semantic IR KEOL Projection Trace Report",
        "",
        "Scope: Assertion -> Evidence -> source quote trace; no KEOL baseline mutation.",
        "",
        "## Metrics",
        "",
        f"- Assertions: {metrics['assertion_count']}",
        f"- Assertions with evidence: {metrics['assertions_with_evidence_count']}",
        f"- Assertions with derived provenance: {metrics['assertions_with_derived_provenance_count']}",
        f"- Broken evidence refs: {metrics['broken_evidence_ref_count']}",
        "",
        "## Sample traces",
        "",
    ]
    for trace in payload["assertion_traces"][:8]:
        lines.extend(
            [
                f"### {trace['assertion_id']}",
                "",
                f"- Semantic IR unit: `{trace['semantic_ir_unit_id']}`",
                f"- Level: `{trace['semantic_ir_level']}`",
                f"- Status: `{trace['status']}`",
                f"- Evidence refs: `{trace['evidence_ids']}`",
                f"- Derived from: `{trace['derived_from_assertion_ids']}`",
            ]
        )
        for evidence in trace["evidence_trace"][:2]:
            lines.append(
                f"- Evidence `{evidence['semantic_ir_evidence_id']}` from `{evidence['source_chunk_id']}`: {evidence['quote_preview']}"
            )
        lines.append("")
    if payload["broken_evidence_refs"]:
        lines.extend(["## Broken evidence refs", ""])
        for broken in payload["broken_evidence_refs"]:
            lines.append(f"- `{broken['assertion_id']}` -> `{broken['evidence_id']}`")
        lines.append("")
    lines.extend(
        [
            "## Interpretation",
            "",
            "This report verifies the projection's local provenance chain. It does not validate KEOL runtime ingestion, model extraction quality, or answer generation.",
            "",
        ]
    )
    return "\n".join(lines)


def write_projection_trace_report(
    projection_path: Path,
    output_path: Path,
    report_path: Path,
) -> dict[str, Any]:
    payload = build_projection_trace_report(load_json(projection_path))
    write_json_immutable(output_path, payload)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_projection_trace_markdown(payload), encoding="utf-8")
    return payload
