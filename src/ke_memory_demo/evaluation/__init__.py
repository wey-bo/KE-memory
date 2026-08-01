from .baseline_results import BaselineResultError, load_public_baseline_results
from .gold_sources import SourceCatalog, SourceMappingError, build_gold_source_mapping
from .judge import (
    JUDGE_MAX_OUTPUT_TOKENS,
    JUDGE_MODEL,
    JudgeInvariantError,
    JudgeModelOutput,
    JudgeService,
)
from .manifest import ExperimentManifest
from .metrics import (
    ComputedMetrics,
    MetricsInvariantError,
    QuestionMetricInput,
    aggregate_operation_usage,
    compute_metrics,
    compute_question_metrics,
    select_turn_ke_audits,
)
from .models import (
    AggregateMetrics,
    BaselinePublicResult,
    EvaluationFailure,
    EvaluationRun,
    EvaluationStatus,
    GoldSourceMapping,
    GoldSourceStatus,
    JudgeResult,
    OperationUsageMetrics,
    ProbeQuestion,
    QuestionAnswer,
    QuestionCategory,
    QuestionExecution,
    QuestionMetrics,
    ReportDocument,
    RubricJudgement,
    TurnKEAuditCase,
)
from .preflight import (
    EvaluationPreflight,
    PreflightCheck,
    PreflightCheckFailure,
    PreflightReport,
)
from .report import (
    ReportInput,
    ReportInvariantError,
    ReportWriter,
    materialize_report_documents,
)
from .questions import (
    QuestionNormalizationError,
    normalize_question,
    normalize_questions,
    question_manifest_sha256,
)
from .runner import EvaluationInvariantError, EvaluationRunner


__all__ = [
    "JUDGE_MAX_OUTPUT_TOKENS",
    "JUDGE_MODEL",
    "AggregateMetrics",
    "BaselinePublicResult",
    "BaselineResultError",
    "ComputedMetrics",
    "EvaluationPreflight",
    "EvaluationFailure",
    "EvaluationInvariantError",
    "EvaluationRun",
    "EvaluationRunner",
    "EvaluationStatus",
    "ExperimentManifest",
    "GoldSourceMapping",
    "GoldSourceStatus",
    "JudgeInvariantError",
    "JudgeModelOutput",
    "JudgeResult",
    "JudgeService",
    "MetricsInvariantError",
    "OperationUsageMetrics",
    "PreflightCheck",
    "PreflightCheckFailure",
    "PreflightReport",
    "ProbeQuestion",
    "QuestionAnswer",
    "QuestionCategory",
    "QuestionExecution",
    "QuestionMetrics",
    "QuestionMetricInput",
    "QuestionNormalizationError",
    "RubricJudgement",
    "ReportDocument",
    "ReportInput",
    "ReportInvariantError",
    "ReportWriter",
    "SourceCatalog",
    "SourceMappingError",
    "TurnKEAuditCase",
    "build_gold_source_mapping",
    "aggregate_operation_usage",
    "compute_metrics",
    "compute_question_metrics",
    "load_public_baseline_results",
    "materialize_report_documents",
    "normalize_question",
    "normalize_questions",
    "question_manifest_sha256",
    "select_turn_ke_audits",
]


# Register the evaluation artifact types into the contracts registry.
#
# This is the inverted edge: contracts used to reach *up* into evaluation through a
# deferred import, which hid a cycle from static reading. Now evaluation pushes its
# types down, so pipeline and snapshots can read the mapping without naming
# evaluation. Registration happens at import time, and reading before it raises.
def _register_evaluation_artifacts() -> None:
    from ke_memory_demo.contracts import EVALUATION_ARTIFACT_REGISTRY
    from ke_memory_demo.retrieval import QueryExtractionTrace, RetrievalTrace

    EVALUATION_ARTIFACT_REGISTRY.register(
        {
            "probe_questions": ProbeQuestion,
            "gold_source_mappings": GoldSourceMapping,
            "experiment_manifests": ExperimentManifest,
            "query_traces": QueryExtractionTrace,
            "retrieval_traces": RetrievalTrace,
            "question_answers": QuestionAnswer,
            "judge_results": JudgeResult,
            "evaluation_failures": EvaluationFailure,
            "evaluation_runs": EvaluationRun,
            "question_metrics": QuestionMetrics,
            "aggregate_metrics": AggregateMetrics,
            "operation_usage_metrics": OperationUsageMetrics,
            "baseline_public_results": BaselinePublicResult,
            "turn_ke_audits": TurnKEAuditCase,
            "report_documents": ReportDocument,
        }
    )


_register_evaluation_artifacts()
