from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


BenchmarkName = Literal["beam", "locomo", "longmemeval"]
AnswerPolicy = Literal["gold", "manual_required"]
EvaluationArm = Literal["dense_reference", "symbolic", "symbolic_fallback", "oracle"]
FallbackReason = Literal[
    "empty_symbolic_result",
    "unresolved_entity",
    "uncovered_predicate",
    "missing_evidence_slot",
    "lexical_predicate_missing_link",
    "incomplete_evidence_slot",
]


class SourceArtifact(StrictModel):
    benchmark: BenchmarkName
    source_id: str = Field(min_length=1)
    official_url: str = Field(min_length=1)
    frozen_identity: str = Field(min_length=1)
    local_path: str = Field(min_length=1)
    reader: Literal["duckdb", "json"]
    size_bytes: int = Field(ge=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class SourceManifest(StrictModel):
    schema_version: Literal["natural-benchmark-source-manifest-v1"] = "natural-benchmark-source-manifest-v1"
    sources: list[SourceArtifact] = Field(min_length=1)


class NaturalBenchmarkCandidate(StrictModel):
    benchmark: BenchmarkName
    item_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    source_index: int = Field(ge=0)
    source_ref: str = Field(min_length=1)
    question: str = Field(min_length=1)
    answer: str | None = None
    answer_policy: AnswerPolicy = "gold"
    evidence_refs: list[str] = Field(default_factory=list)
    slice_group: str = Field(min_length=1)
    category: str | int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_manual_required(self) -> "NaturalBenchmarkCandidate":
        if self.answer_policy == "gold" and self.answer is None:
            raise ValueError("gold candidates require an answer")
        if self.answer_policy == "manual_required" and self.answer is not None:
            raise ValueError("manual-required candidates must not carry a gold answer")
        return self

    def public_item(self) -> dict[str, Any]:
        data = {
            "benchmark": self.benchmark,
            "item_id": self.item_id,
            "source_id": self.source_id,
            "source_index": self.source_index,
            "source_ref": self.source_ref,
            "question": self.question,
            "slice_group": self.slice_group,
            "category": self.category,
        }
        return {key: value for key, value in data.items() if value is not None}

    def gold_item(self) -> dict[str, Any]:
        return {
            "benchmark": self.benchmark,
            "item_id": self.item_id,
            "source_id": self.source_id,
            "source_ref": self.source_ref,
            "slice_group": self.slice_group,
            "category": self.category,
            "answer": self.answer,
            "answer_policy": self.answer_policy,
            "evidence_refs": list(self.evidence_refs),
            "metadata": self.metadata,
        }


class SliceBundle(StrictModel):
    schema_version: Literal["natural-benchmark-slice-v1"] = "natural-benchmark-slice-v1"
    slice_id: str = Field(min_length=1)
    source_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    selection_policy: dict[str, Any]
    public_items: list[dict[str, Any]] = Field(min_length=1)
    gold_items: list[dict[str, Any]] = Field(min_length=1)


class PublicSliceArtifact(StrictModel):
    schema_version: Literal["natural-benchmark-slice-v1"] = "natural-benchmark-slice-v1"
    slice_id: str = Field(min_length=1)
    source_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    selection_policy: dict[str, Any]
    public_items: list[dict[str, Any]] = Field(min_length=1)


class GoldArtifact(StrictModel):
    schema_version: Literal["natural-benchmark-gold-v1"] = "natural-benchmark-gold-v1"
    slice_id: str = Field(min_length=1)
    source_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    items: list[dict[str, Any]] = Field(min_length=1)


class ResultItem(StrictModel):
    item_id: str = Field(min_length=1)
    predicted_answer: str | None = None
    retrieved_evidence_refs: list[str] = Field(default_factory=list)
    abstained: bool = False
    fallback_triggered: bool = False
    fallback_reason: FallbackReason | None = None
    critical_false_positive: bool = False
    latency_ms: float | None = Field(default=None, ge=0)
    evidence_token_count: int | None = Field(default=None, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResultsArtifact(StrictModel):
    schema_version: Literal["natural-benchmark-results-v1"] = "natural-benchmark-results-v1"
    slice_id: str = Field(min_length=1)
    source_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    run_id: str = Field(min_length=1)
    arm: EvaluationArm
    items: list[ResultItem]

    @model_validator(mode="after")
    def validate_fallback_contract(self) -> "ResultsArtifact":
        for item in self.items:
            if self.arm != "symbolic_fallback" and item.fallback_triggered:
                raise ValueError("fallback_triggered is only valid for symbolic_fallback")
            if item.fallback_triggered and item.fallback_reason is None:
                raise ValueError("fallback_reason is required when fallback_triggered=true")
            if not item.fallback_triggered and item.fallback_reason is not None:
                raise ValueError("fallback_reason requires fallback_triggered=true")
        return self


class ScoreReport(StrictModel):
    schema_version: Literal["natural-benchmark-score-report-v1"] = "natural-benchmark-score-report-v1"
    run_id: str = Field(min_length=1)
    slice_id: str = Field(min_length=1)
    source_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    arm: EvaluationArm
    metrics: dict[str, Any]


class EvidenceUnit(StrictModel):
    benchmark: BenchmarkName
    source_id: str = Field(min_length=1)
    unit_id: str = Field(min_length=1)
    source_ref: str = Field(min_length=1)
    text: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExternalResultEntry(StrictModel):
    system: str = Field(min_length=1)
    benchmark: str = Field(min_length=1)
    metric_name: str = Field(min_length=1)
    metric_value: float | str
    official_source_url: str = Field(min_length=1)
    version_or_retrieval_date: str = Field(min_length=1)
    source_identity: str = Field(min_length=1)
    comparability_status: Literal["contextual_only"] = "contextual_only"
    local_rerun: bool = False
    note: str = Field(min_length=1)


class ExternalResultsLedger(StrictModel):
    schema_version: Literal["natural-benchmark-external-results-ledger-v1"] = "natural-benchmark-external-results-ledger-v1"
    entries: list[ExternalResultEntry] = Field(min_length=1)
