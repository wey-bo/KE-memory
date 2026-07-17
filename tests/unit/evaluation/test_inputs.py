from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from ke_memory_demo.core.json import JsonObject
from ke_memory_demo.domain import Conversation, Exchange, Message, MessageRole, Session
from ke_memory_demo.evaluation import (
    EvaluationPreflight,
    ExperimentManifest,
    GoldSourceStatus,
    PreflightCheckFailure,
    SourceCatalog,
    SourceMappingError,
    build_gold_source_mapping,
    normalize_question,
)
from ke_memory_demo.ontology import IndexIdentity
from ke_memory_demo.pipeline import (
    OntologyRunIdentity,
    PipelineRunManifest,
    PipelineStage,
)
from ke_memory_demo.pipeline.runtime import validate_evaluation_snapshot_contract
from ke_memory_demo.settings import EvaluationConcurrencySettings, load_settings


@pytest.mark.parametrize(
    ("raw", "field", "answer"),
    [
        (
            {
                "ideal_answer": "a",
                "ideal_response": "b",
                "answer": "c",
                "ideal_summary": "d",
                "expected_compliance": "e",
            },
            "ideal_answer",
            "a",
        ),
        ({"ideal_response": "b", "answer": "c"}, "ideal_response", "b"),
        ({"answer": "c"}, "answer", "c"),
        ({"ideal_summary": "d"}, "ideal_summary", "d"),
        ({"expected_compliance": "e"}, "expected_compliance", "e"),
    ],
)
def test_answer_priority(raw: JsonObject, field: str, answer: str) -> None:
    value: JsonObject = {"question": "q", "rubric": ["r"], **raw}
    normalized = normalize_question(
        value,
        conversation_id="conversation-1",
        category="knowledge_update",
        ordinal=0,
    )
    assert normalized.ideal_answer == answer
    assert normalized.original_answer_field == field


def test_gold_mapping_uses_only_unique_explicit_source_numbers() -> None:
    catalog = SourceCatalog.from_conversation(_conversation((8, 10, 12, 14)))
    mapping = build_gold_source_mapping(
        {
            "source_chat_ids": [8, [10, 12]],
            "conversation_references": ["Session 14"],
            "unapproved_numbers": [16, 18],
        },
        catalog,
        question_id="q-1",
    )
    assert mapping.status is GoldSourceStatus.MAPPED
    assert mapping.source_numbers == (8, 10, 12, 14)
    assert mapping.source_exchange_ids == catalog.resolve((8, 10, 12, 14))
    assert all("unapproved_numbers" not in path for path in mapping.matched_paths)


@pytest.mark.parametrize(
    ("raw", "raw_message_ids"),
    [
        ({"description": "No explicit source number here"}, (8,)),
        ({"conversation_references": ["chat_id: 8"]}, (8, 8)),
    ],
)
def test_gold_mapping_keeps_zero_or_ambiguous_sources_unmappable(
    raw: JsonObject,
    raw_message_ids: tuple[int, ...],
) -> None:
    catalog = SourceCatalog.from_conversation(_conversation(raw_message_ids))
    mapping = build_gold_source_mapping(raw, catalog, question_id="q-1")
    assert mapping.status is GoldSourceStatus.UNMAPPABLE
    assert mapping.source_exchange_ids == ()
    assert mapping.exclusion_reason is not None

    if mapping.source_numbers:
        with pytest.raises(SourceMappingError):
            catalog.resolve(mapping.source_numbers)


def test_manifest_hash_excludes_only_creation_time_and_hash() -> None:
    created_at = datetime(2026, 7, 17, 10, 0, tzinfo=UTC)
    first = _manifest(created_at)
    later = _manifest(created_at + timedelta(hours=1))

    assert first.content_hash == later.content_hash
    assert len(first.content_hash) == 64
    assert "api_key" not in ExperimentManifest.model_fields
    assert "headers" not in ExperimentManifest.model_fields
    assert "baseline" not in ExperimentManifest.model_fields
    assert "embedding_fingerprint" not in ExperimentManifest.model_fields
    with pytest.raises(ValidationError):
        first.run_id = "mutated"


def test_snapshot_contract_pins_the_fixed_dataset_hash(project_root: Path) -> None:
    settings = load_settings(project_root)
    manifest = PipelineRunManifest(
        run_id="run-1",
        stage=PipelineStage.KE_READY,
        parent_snapshot_id=None,
        code_commit="a" * 40,
        dataset_sha256="0" * 64,
        selected_directories=(4, 15, 17),
        ontology=OntologyRunIdentity(
            index=IndexIdentity(
                index_name="ontology",
                index_uuid="uuid-1",
                mapping_sha256="1" * 64,
            ),
            normalization_mode="bounded-best-effort",
        ),
        embedding_enabled=False,
        concurrency=settings.evaluation.concurrency,
        record_counts={},
    )

    with pytest.raises(PreflightCheckFailure, match="SnapshotContractMismatch"):
        validate_evaluation_snapshot_contract(manifest, (), settings)


@pytest.mark.asyncio
async def test_preflight_reports_all_failures_without_ingestion_or_secret_details() -> None:
    ports = _FakePreflightPorts()
    ports.fail("judge_model", "state_repo", "ontology_identity")

    report = await EvaluationPreflight(ports).run()

    assert report.ready is False
    assert [item.name for item in report.failed] == [
        "judge_model",
        "ontology_identity",
        "state_repo",
    ]
    assert ports.ingest_calls == 0
    rendered = report.model_dump_json()
    assert "Authorization" not in rendered
    assert "provider-secret-body" not in rendered


@pytest.mark.asyncio
async def test_preflight_reports_missing_environment_names_without_values() -> None:
    class MissingEnvironmentPorts:
        async def check(self, name: str) -> str:
            if name == "environment":
                raise PreflightCheckFailure(
                    "environment:missing=KE_MEMORY_ES_API_KEY,KE_MEMORY_WORK_API_KEY"
                )
            return f"{name}:ok"

    report = await EvaluationPreflight(MissingEnvironmentPorts()).run()

    [failure] = report.failed
    assert failure.detail == ("environment:missing=KE_MEMORY_ES_API_KEY,KE_MEMORY_WORK_API_KEY")


def _conversation(raw_message_ids: Sequence[int]) -> Conversation:
    conversation_id = "conversation-1"
    session_id = "session-1"
    exchanges = tuple(
        Exchange(
            id=f"exchange-{ordinal}",
            session_id=session_id,
            user=Message(
                id=f"user-{ordinal}",
                role=MessageRole.USER,
                content=f"user {ordinal}",
                source_order=ordinal * 2,
                source_metadata={"raw_message_id": raw_message_id},
            ),
            assistant=Message(
                id=f"assistant-{ordinal}",
                role=MessageRole.ASSISTANT,
                content=f"assistant {ordinal}",
                source_order=ordinal * 2 + 1,
                source_metadata={"raw_message_id": 1_000 + ordinal},
            ),
            global_ordinal=ordinal * 2,
        )
        for ordinal, raw_message_id in enumerate(raw_message_ids)
    )
    return Conversation(
        id=conversation_id,
        sessions=(
            Session(
                id=session_id,
                conversation_id=conversation_id,
                exchanges=exchanges,
            ),
        ),
    )


def _manifest(created_at: datetime) -> ExperimentManifest:
    return ExperimentManifest(
        run_id="run-1",
        code_commit="a" * 40,
        spec_sha256="b" * 64,
        plan_sha256="c" * 64,
        ke_ready_snapshot_id="d" * 40,
        dataset_sha256="e" * 64,
        selected_directories=(4, 15, 17),
        expected_sessions=13,
        expected_exchanges=385,
        expected_questions=60,
        question_manifest_sha256="f" * 64,
        gold_mapping_sha256="0" * 64,
        ontology=OntologyRunIdentity(
            index=IndexIdentity(
                index_name="ontology",
                index_uuid="uuid-1",
                mapping_sha256="1" * 64,
            ),
            normalization_mode="bounded-best-effort",
        ),
        work_model="gpt-5.4",
        work_base_url="https://work.invalid/v1",
        judge_model="deepseek-v4-pro",
        judge_base_url="https://judge.invalid/v1",
        answer_prompt_sha256="2" * 64,
        judge_prompt_sha256="3" * 64,
        embedding_enabled=False,
        concurrency=EvaluationConcurrencySettings(
            turn_workers=8,
            session_workers=4,
            question_workers=8,
            judge_workers=8,
        ),
        created_at=created_at,
    )


class _FakePreflightPorts:
    def __init__(self) -> None:
        self._failures: set[str] = set()
        self.ingest_calls = 0

    def fail(self, *names: str) -> None:
        self._failures.update(names)

    async def check(self, name: str) -> str:
        if name in self._failures:
            if name == "state_repo":
                raise PreflightCheckFailure("state_repo:PermissionError")
            raise RuntimeError("Authorization provider-secret-body")
        return f"{name}:ok"
