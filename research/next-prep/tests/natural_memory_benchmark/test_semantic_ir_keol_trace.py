from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tools.natural_memory_benchmark.io import load_json
from tools.natural_memory_benchmark.semantic_ir_keol_trace import (
    build_projection_trace_report,
    render_projection_trace_markdown,
    write_projection_trace_report,
)


PROJECTION = Path("artifacts/natural-benchmark-slices/slice-v1/semantic-ir-keol-projection.json")


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "tools.natural_memory_benchmark.cli", *args],
        check=True,
        capture_output=True,
        text=True,
    )


def test_projection_trace_report_has_no_broken_evidence_links():
    projection = load_json(PROJECTION)

    report = build_projection_trace_report(projection)

    assert report["schema_version"] == "semantic-ir-keol-trace-report-v1"
    assert report["metrics"] == {
        "assertion_count": 19,
        "assertions_with_evidence_count": 19,
        "assertions_with_derived_provenance_count": 6,
        "broken_evidence_ref_count": 0,
    }
    assert len(report["assertion_traces"]) == 19
    first_l1 = next(trace for trace in report["assertion_traces"] if trace["semantic_ir_level"] == "L1")
    assert first_l1["evidence_trace"][0]["quote_preview"]
    assert first_l1["evidence_trace"][0]["source_chunk_id"]


def test_projection_trace_markdown_summarizes_scope_and_links():
    projection = load_json(PROJECTION)
    report = build_projection_trace_report(projection)

    markdown = render_projection_trace_markdown(report)

    assert "# Semantic IR KEOL Projection Trace Report" in markdown
    assert "Broken evidence refs: 0" in markdown
    assert "Assertion -> Evidence -> source quote" in markdown
    assert "no KEOL baseline mutation" in markdown


def test_cli_trace_semantic_ir_keol_projection_writes_json_and_markdown(tmp_path):
    output_path = tmp_path / "semantic-ir-keol-trace.json"
    report_path = tmp_path / "semantic-ir-keol-trace.md"

    result = _run_cli(
        "trace-semantic-ir-keol-projection",
        "--projection",
        str(PROJECTION),
        "--output",
        str(output_path),
        "--report",
        str(report_path),
    )

    assert "valid" in result.stdout
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    markdown = report_path.read_text(encoding="utf-8")
    assert payload["metrics"]["broken_evidence_ref_count"] == 0
    assert "Semantic IR KEOL Projection Trace Report" in markdown


def test_write_projection_trace_report_helper_writes_both_files(tmp_path):
    output_path = tmp_path / "trace.json"
    report_path = tmp_path / "trace.md"

    payload = write_projection_trace_report(PROJECTION, output_path, report_path)

    assert output_path.exists()
    assert report_path.exists()
    assert payload["metrics"]["assertion_count"] == 19
