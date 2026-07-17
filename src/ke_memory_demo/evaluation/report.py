from __future__ import annotations

import csv
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
from collections.abc import Sequence
from typing import Literal, TypeAlias, cast

from pydantic import BaseModel, ConfigDict, model_validator

from ke_memory_demo.core.json import JsonObject, JsonValue

from .manifest import ExperimentManifest
from .models import (
    AggregateMetrics,
    BaselinePublicResult,
    EvaluationRun,
    EvaluationStatus,
    GoldSourceMapping,
    OperationUsageMetrics,
    ProbeQuestion,
    QuestionCategory,
    QuestionMetrics,
    ReportDocument,
    TurnKEAuditCase,
)


_FOCUS_CATEGORIES = (
    QuestionCategory.CONTRADICTION_RESOLUTION,
    QuestionCategory.KNOWLEDGE_UPDATE,
    QuestionCategory.EVENT_ORDERING,
    QuestionCategory.TEMPORAL_REASONING,
    QuestionCategory.MULTI_SESSION_REASONING,
    QuestionCategory.SUMMARIZATION,
)
DocumentName: TypeAlias = Literal["report.md", "question_results.csv", "metrics.json"]
_DOCUMENT_TYPES: dict[DocumentName, str] = {
    "metrics.json": "application/json",
    "question_results.csv": "text/csv; charset=utf-8",
    "report.md": "text/markdown; charset=utf-8",
}


class ReportInvariantError(ValueError):
    """Canonical evaluation records cannot form a deterministic report."""


class ReportInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    manifest: ExperimentManifest
    run: EvaluationRun
    questions: tuple[ProbeQuestion, ...]
    gold_mappings: tuple[GoldSourceMapping, ...]
    question_metrics: tuple[QuestionMetrics, ...]
    aggregate_metrics: tuple[AggregateMetrics, ...]
    operation_usage_metrics: tuple[OperationUsageMetrics, ...]
    baseline_public_results: tuple[BaselinePublicResult, ...]
    turn_ke_audits: tuple[TurnKEAuditCase, ...]

    @model_validator(mode="after")
    def _validate_identity(self) -> ReportInput:
        if self.manifest.content_hash != self.run.manifest_hash:
            raise ValueError("report manifest identity does not match the evaluation run")
        expected = self.run.expected_question_ids
        if tuple(sorted(item.id for item in self.questions)) != expected:
            raise ValueError("report questions do not match the evaluation run")
        if tuple(sorted(item.question_id for item in self.gold_mappings)) != expected:
            raise ValueError("report gold mappings do not match the evaluation run")
        metric_ids = tuple(sorted(item.question_id for item in self.question_metrics))
        if not set(metric_ids).issubset(expected):
            raise ValueError("report metrics contain an unexpected question")
        if self.run.status is EvaluationStatus.COMPLETE and metric_ids != expected:
            raise ValueError("complete report requires one metric for every question")
        if self.run.status is EvaluationStatus.INCOMPLETE and self.aggregate_metrics:
            raise ValueError("incomplete report cannot publish aggregate means")
        return self


class ReportWriter:
    @staticmethod
    def build(report_input: ReportInput) -> tuple[ReportDocument, ...]:
        data = ReportInput.model_validate(report_input)
        contents: dict[DocumentName, str] = {
            "metrics.json": _metrics_json(data),
            "question_results.csv": _question_csv(data),
            "report.md": _markdown(data),
        }
        return tuple(
            ReportDocument(
                name=name,
                media_type=_DOCUMENT_TYPES[name],
                sha256=hashlib.sha256(contents[name].encode("utf-8")).hexdigest(),
                content=contents[name],
            )
            for name in sorted(contents)
        )


def materialize_report_documents(
    documents: tuple[ReportDocument, ...],
    output_directory: Path,
) -> tuple[Path, ...]:
    validated = tuple(ReportDocument.model_validate(item) for item in documents)
    names = tuple(item.name for item in validated)
    if names != tuple(sorted(_DOCUMENT_TYPES)):
        raise ReportInvariantError("canonical report must contain exactly three sorted documents")
    output_directory.mkdir(parents=True, exist_ok=True)
    if output_directory.is_symlink() or not output_directory.is_dir():
        raise ReportInvariantError("report export path must be a real directory")
    paths: list[Path] = []
    for document in validated:
        destination = output_directory / document.name
        if destination.is_symlink():
            raise ReportInvariantError("report export destination must not be a symlink")
        descriptor, temporary = tempfile.mkstemp(
            dir=output_directory,
            prefix=f".{document.name}.",
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
                stream.write(document.content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, destination)
        except BaseException:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
            raise
        paths.append(destination)
    return tuple(paths)


def _markdown(data: ReportInput) -> str:
    run = data.run
    expected = len(run.expected_question_ids)
    heading = "# KE-only Evaluation Report"
    if run.status is EvaluationStatus.INCOMPLETE:
        heading += " (INCOMPLETE)"
    overall = _aggregate_by_scope(data.aggregate_metrics).get("overall")
    mapped_count = sum(item.status.value == "mapped" for item in data.gold_mappings)
    unmapped_count = len(data.gold_mappings) - mapped_count
    lines = [
        heading,
        "",
        "## Protocol",
        "",
        "This report covers the fixed KE-only BEAM evaluation. Embedding remained disabled, "
        "answers used KE evidence, and an independent Judge scored the frozen rubrics.",
        "",
        "## Completeness",
        "",
        f"- Status: `{run.status.value}`",
        f"- {len(run.answers)}/{expected} answers",
        f"- {len(run.judgements)}/{expected} Judge results",
        f"- {len(run.failures)} typed failures",
        f"- Gold source mappings: {mapped_count} mapped, {unmapped_count} explicit unmappable",
        "",
        "## Ontology Identity and Mode",
        "",
        f"- Index: `{data.manifest.ontology.index.index_name}`",
        f"- Index UUID: `{data.manifest.ontology.index.index_uuid}`",
        f"- Mapping SHA-256: `{data.manifest.ontology.index.mapping_sha256}`",
        f"- Normalization mode: `{data.manifest.ontology.normalization_mode}`",
        "- Retrieval mode: KE-only; embedding disabled",
        "",
        "## Concurrency",
        "",
        f"- Turn workers: {data.manifest.concurrency.turn_workers}",
        f"- Session workers: {data.manifest.concurrency.session_workers}",
        f"- Question workers: {data.manifest.concurrency.question_workers}",
        f"- Judge workers: {data.manifest.concurrency.judge_workers}",
        "",
        "Operation usage is grouped by the exact trace operation. A missing provider cost makes "
        "that operation's total cost unavailable rather than partially summed.",
        "",
    ]
    for usage in sorted(data.operation_usage_metrics, key=lambda item: item.operation):
        lines.append(
            f"- `{usage.operation}`: {usage.call_count} calls, {usage.input_tokens} input tokens, "
            f"{usage.output_tokens} output tokens, {_format_float(usage.latency_seconds)} seconds, "
            f"cost {_format_optional_float(usage.provider_cost)}"
        )
    lines.extend(
        [
            "",
            "## Answer Metrics",
            "",
        ]
    )
    if overall is None:
        lines.append(
            "Aggregate answer means are withheld because the run is incomplete; missing results "
            "are neither zero-filled nor removed from the expected denominator."
        )
    else:
        lines.extend(
            [
                f"- Answer rubric score: {_format_float(overall.answer_score_sum)}/"
                f"{overall.question_count} = {_format_float(overall.answer_score_mean)}",
                f"- Factual errors: {overall.factual_error_count}/{overall.question_count}",
                f"- Unsupported claims: {overall.unsupported_claim_count}/{overall.question_count}",
            ]
        )
    abstention_metrics = tuple(
        item for item in data.question_metrics if item.abstention_correct is not None
    )
    lines.append(
        f"- Abstention correctness: "
        f"{sum(item.abstention_correct is True for item in abstention_metrics)}/"
        f"{len(abstention_metrics)}"
    )
    lines.extend(["", "## Evidence and Citation Metrics", ""])
    if overall is None:
        lines.append("Only completed per-question diagnostics are present for this incomplete run.")
    else:
        lines.extend(
            [
                f"- Gold source recall: {_format_float(overall.source_recall_sum)}/"
                f"{overall.mapped_source_count} = "
                f"{_format_optional_float(overall.source_recall_mean)}",
                f"- Complete evidence: {overall.complete_evidence_count}/"
                f"{overall.mapped_source_count}",
                f"- Citation validity: {overall.citation_valid_count}/{overall.question_count}",
                f"- Citation traceability: {overall.citation_traceable_count}/"
                f"{overall.question_count}",
            ]
        )
    lines.extend(["", "## Six Focus Categories", ""])
    aggregate_by_scope = _aggregate_by_scope(data.aggregate_metrics)
    for category in _FOCUS_CATEGORIES:
        metric = aggregate_by_scope.get(f"category:{category.value}")
        if metric is None:
            lines.append(f"- `{category.value}`: unavailable while the run is incomplete")
        else:
            lines.append(
                f"- `{category.value}`: {_format_float(metric.answer_score_sum)}/"
                f"{metric.question_count} = {_format_float(metric.answer_score_mean)}"
            )
    lines.extend(["", "## Cross-Session Induction Cases", ""])
    cross_session = tuple(
        item for item in data.turn_ke_audits if item.audit_kind == "cross_session"
    )
    if not cross_session:
        lines.append("No deterministic cross-Session audit case was available.")
    for audit in cross_session:
        lines.append(
            f"- Conversation `{audit.conversation_id}`; Exchanges "
            f"{', '.join(f'`{item}`' for item in audit.exchange_ids)}; AggregateNodes "
            f"{', '.join(f'`{item}`' for item in audit.aggregate_ids)}"
        )
    lines.extend(["", "## Turn KE Raw-to-Form Audit", ""])
    for audit in data.turn_ke_audits:
        lines.extend(
            [
                f"### {audit.audit_kind}",
                "",
                f"Conversation `{audit.conversation_id}`; Exchanges "
                f"{', '.join(f'`{item}`' for item in audit.exchange_ids)}.",
                f"Coverage entries: {len(audit.coverage)}; Knowledge equations: "
                f"{len(audit.knowledge_equations)}; Aggregate closure: "
                f"{', '.join(audit.aggregate_ids) or 'none'}.",
                "",
            ]
        )
        for equation in audit.knowledge_equations:
            spans = ", ".join(
                f"`{span.message_id}[{span.start_char}:{span.end_char}]#{span.text_hash}`"
                for span in equation.evidence_refs
            )
            expression = {
                "lhs": cast(JsonValue, equation.lhs.model_dump(mode="json")),
                "rhs": cast(JsonValue, equation.rhs.model_dump(mode="json")),
            }
            lines.extend(
                [
                    f"- KE `{equation.id}`: {_markdown_text(equation.gloss)}",
                    f"  - Level/modality/lifecycle: `{equation.level.value}` / "
                    f"`{equation.modality.value}` / `{equation.lifecycle.value}`",
                    f"  - Expression: `{_json_text(expression).strip()}`",
                    f"  - Evidence spans: {spans or 'none'}",
                ]
            )
        lines.extend(
            [
                "",
                "```json",
                _json_text(list(audit.raw_records), pretty=True).rstrip("\n"),
                "```",
                "",
            ]
        )
    lines.extend(["## Failures", ""])
    if not run.failures:
        lines.append("No evaluation failures were recorded.")
    for failure in run.failures:
        lines.append(
            f"- `{failure.question_id}` / `{failure.stage}` / `{failure.error_type}`: "
            f"{_markdown_text(failure.message)}"
        )
    lines.extend(["", "## Public Baseline Appendix", ""])
    for record in sorted(data.baseline_public_results, key=_baseline_key):
        lines.extend(
            [
                f"### {record.system}: {record.dataset} / {record.split}",
                "",
                f"- Published metric: {_markdown_text(record.metric)}",
                f"- Published score: {_format_optional_float(record.score)}",
                f"- Statuses: {', '.join(f'`{item}`' for item in record.statuses)}",
                f"- Source: {record.source_url} at `{record.source_commit}`",
                f"- Retrieved: {record.retrieved_on.isoformat()}",
                f"- Vendor self-report: {'yes' if record.vendor_self_report else 'no'}",
                f"- Reproduction artifacts: {_markdown_text(record.reproduction_artifacts)}",
                f"- Notes: {_markdown_text(record.notes)}",
                "",
            ]
        )
    lines.extend(
        [
            "## Non-Comparability Warning",
            "",
            "不可直接比较: public results above retain their published datasets, splits, top-k, "
            "metrics, answer models, and evaluation protocols. They were not reproduced here, "
            "and this report does not average, normalize, order, or convert them against the "
            "KE-only result.",
            "",
            "## Limitations",
            "",
            "- Public baseline claims are a sourced appendix, not local reproductions.",
            "- Source recall and complete-evidence fields are undefined for explicitly unmappable gold.",
            "- Deterministic Turn KE examples support audit; they do not claim that KE replaces raw text.",
            "- An incomplete run is diagnostic only and cannot create an evaluation-complete snapshot.",
            "",
        ]
    )
    return "\n".join(lines)


def _question_csv(data: ReportInput) -> str:
    output = io.StringIO(newline="")
    fields = (
        "question_id",
        "conversation_id",
        "category",
        "answer_score",
        "satisfied_rubrics",
        "rubric_count",
        "factual_error",
        "unsupported_claim",
        "abstention_correct",
        "source_recall",
        "complete_evidence",
        "citation_valid",
        "citation_traceable",
        "source_session_count",
        "used_aggregate",
        "evidence_tokens",
        "work_input_tokens",
        "work_output_tokens",
        "work_latency_seconds",
        "work_provider_cost",
        "judge_input_tokens",
        "judge_output_tokens",
        "judge_latency_seconds",
        "judge_provider_cost",
    )
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for item in sorted(data.question_metrics, key=lambda metric: metric.question_id):
        writer.writerow(
            {
                "question_id": item.question_id,
                "conversation_id": item.conversation_id,
                "category": item.category.value,
                "answer_score": _csv_value(item.answer_score),
                "satisfied_rubrics": item.satisfied_rubrics,
                "rubric_count": item.rubric_count,
                "factual_error": _csv_value(item.factual_error),
                "unsupported_claim": _csv_value(item.unsupported_claim),
                "abstention_correct": _csv_value(item.abstention_correct),
                "source_recall": _csv_value(item.source_recall),
                "complete_evidence": _csv_value(item.complete_evidence),
                "citation_valid": _csv_value(item.citation_valid),
                "citation_traceable": _csv_value(item.citation_traceable),
                "source_session_count": item.source_session_count,
                "used_aggregate": _csv_value(item.used_aggregate),
                "evidence_tokens": item.evidence_tokens,
                "work_input_tokens": item.work_usage.input_tokens,
                "work_output_tokens": item.work_usage.output_tokens,
                "work_latency_seconds": _csv_value(item.work_usage.latency_seconds),
                "work_provider_cost": _csv_value(item.work_usage.provider_cost),
                "judge_input_tokens": item.judge_usage.input_tokens,
                "judge_output_tokens": item.judge_usage.output_tokens,
                "judge_latency_seconds": _csv_value(item.judge_usage.latency_seconds),
                "judge_provider_cost": _csv_value(item.judge_usage.provider_cost),
            }
        )
    return output.getvalue()


def _metrics_json(data: ReportInput) -> str:
    question_metrics = tuple(sorted(data.question_metrics, key=_question_metric_key))
    payload: JsonObject = {
        "aggregate_metrics": _model_records(data.aggregate_metrics),
        "baseline_public_results": _model_records(data.baseline_public_results),
        "completeness": {
            "answers": len(data.run.answers),
            "expected": len(data.run.expected_question_ids),
            "failures": len(data.run.failures),
            "judge_results": len(data.run.judgements),
            "status": data.run.status.value,
        },
        "manifest_hash": data.run.manifest_hash,
        "operation_usage_metrics": _model_records(data.operation_usage_metrics),
        "question_metrics": _model_records(question_metrics),
        "turn_ke_audits": _model_records(data.turn_ke_audits),
    }
    return _json_text(payload)


def _model_records(records: Sequence[BaseModel]) -> list[JsonValue]:
    return [cast(JsonValue, item.model_dump(mode="json")) for item in records]


def _question_metric_key(item: QuestionMetrics) -> str:
    return item.question_id


def _aggregate_by_scope(records: tuple[AggregateMetrics, ...]) -> dict[str, AggregateMetrics]:
    by_scope = {item.scope: item for item in records}
    if len(by_scope) != len(records):
        raise ReportInvariantError("aggregate metric scopes must be unique")
    return by_scope


def _baseline_key(item: BaselinePublicResult) -> tuple[str, str, str, str, float]:
    return (
        item.system,
        item.dataset,
        item.split,
        item.metric,
        item.score if item.score is not None else float("-inf"),
    )


def _json_text(value: object, *, pretty: bool = False) -> str:
    separators = None if pretty else (",", ":")
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2 if pretty else None,
            separators=separators,
            sort_keys=True,
        )
        + "\n"
    )


def _format_float(value: float) -> str:
    return format(value, ".10g")


def _format_optional_float(value: float | None) -> str:
    return "not available" if value is None else _format_float(value)


def _csv_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return _format_float(value)
    return str(value)


def _markdown_text(value: str) -> str:
    return value.replace("\n", " ").replace("|", "\\|")
