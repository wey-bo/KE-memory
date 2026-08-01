from __future__ import annotations

import ast
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .models import NaturalBenchmarkCandidate


BEAM_SOURCE_ID = "beam-100K"
LOCOMO_SOURCE_ID = "locomo10"
LONGMEM_SOURCE_ID = "longmemeval-oracle"


BEAM_OFFICIAL_URL = "https://huggingface.co/datasets/Mohammadta/BEAM/blob/3205395e897e7318c7b094ef4e6047b9b82dbb03/data/100K-00000-of-00001.parquet"
LOCOMO_OFFICIAL_URL = "https://github.com/snap-research/locomo/blob/cbfbc1dba6bc53d00625212a0f22d55ffee7c1fc/data/locomo10.json"
LONGMEM_OFFICIAL_URL = "https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned/blob/98d7416c24c778c2fee6e6f3006e7a073259d48f/longmemeval_oracle.json"


def _flatten_refs(value: Any) -> list[str]:
    refs: list[str] = []
    if value is None:
        return refs
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        for child in value.values():
            refs.extend(_flatten_refs(child))
        return refs
    if isinstance(value, Sequence):
        for child in value:
            refs.extend(_flatten_refs(child))
        return refs
    return [str(value)]


def _metadata_without(item: Mapping[str, Any], excluded: set[str]) -> dict[str, Any]:
    return {key: value for key, value in item.items() if key not in excluded}


def _answer_policy_for(item: Mapping[str, Any], answer: str | None) -> str:
    if answer is None:
        return "manual_required"
    return "gold"


def _make_candidate(
    *,
    benchmark: str,
    item_id: str,
    source_id: str,
    source_index: int,
    source_ref: str,
    question: str,
    answer: str | None,
    evidence_refs: list[str],
    slice_group: str,
    category: str | int | None,
    metadata: dict[str, Any],
) -> NaturalBenchmarkCandidate:
    return NaturalBenchmarkCandidate(
        benchmark=benchmark,
        item_id=item_id,
        source_id=source_id,
        source_index=source_index,
        source_ref=source_ref,
        question=question,
        answer=answer,
        answer_policy=_answer_policy_for(metadata, answer),
        evidence_refs=evidence_refs,
        slice_group=slice_group,
        category=category,
        metadata=metadata,
    )


def _maybe_answer_from_item(item: Mapping[str, Any]) -> str | None:
    for key in ("answer", "ideal_answer", "ideal_response", "ideal_summary"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def load_beam_candidates(path: Path) -> list[NaturalBenchmarkCandidate]:
    # Routed through the evaluation contract so the failure names the install
    # group and can never degrade into a skip: an unread parquet means the source
    # replay path is unverified, which must not report green.
    from .evaluation_environment import require_duckdb

    duckdb = require_duckdb()

    connection = duckdb.connect()
    rows = connection.execute(
        "select conversation_id, probing_questions from read_parquet(?) order by cast(conversation_id as int)",
        [str(path)],
    ).fetchall()
    candidates: list[NaturalBenchmarkCandidate] = []
    source_index = 0
    for conversation_id, probing_questions in rows:
        groups = ast.literal_eval(probing_questions)
        for group_name, items in groups.items():
            for question_index, item in enumerate(items, start=1):
                answer = _maybe_answer_from_item(item)
                metadata = _metadata_without(
                    item,
                    {
                        "question",
                        "answer",
                        "ideal_answer",
                        "ideal_response",
                        "ideal_summary",
                        "source_chat_ids",
                        "conversation_references",
                    },
                )
                candidates.append(
                    _make_candidate(
                        benchmark="beam",
                        item_id=f"BEAM-100K-C{int(conversation_id):03d}-{group_name.replace('-', '_')}-{question_index:03d}",
                        source_id=BEAM_SOURCE_ID,
                        source_index=source_index,
                        source_ref=f"conversation_id={conversation_id};group={group_name};question_index={question_index}",
                        question=str(item["question"]),
                        answer=answer,
                        evidence_refs=_flatten_refs(item.get("source_chat_ids") or item.get("conversation_references")),
                        slice_group=str(group_name),
                        category=str(group_name),
                        metadata=metadata,
                    )
                )
                source_index += 1
    return candidates


def load_locomo_candidates(path: Path) -> list[NaturalBenchmarkCandidate]:
    data = json.loads(path.read_text(encoding="utf-8"))
    candidates: list[NaturalBenchmarkCandidate] = []
    source_index = 0
    for sample_index, sample in enumerate(data, start=1):
        qa_items = sample.get("qa")
        if not isinstance(qa_items, list):
            raise ValueError("LoCoMo sample is missing qa list")
        sample_id = sample.get("sample_id", sample_index)
        for qa_index, qa in enumerate(qa_items, start=1):
            question = qa["question"]
            category = qa["category"]
            answer = qa.get("answer")
            if category == 5:
                answer = None
            metadata = _metadata_without(
                qa,
                {"question", "answer", "evidence", "category", "adversarial_answer"},
            )
            if "adversarial_answer" in qa:
                metadata["adversarial_answer"] = qa["adversarial_answer"]
            candidates.append(
                _make_candidate(
                    benchmark="locomo",
                    item_id=f"LOCOMO-S{sample_index:02d}-Q{qa_index:03d}",
                    source_id=LOCOMO_SOURCE_ID,
                    source_index=source_index,
                    source_ref=f"sample_id={sample_id};qa_index={qa_index};category={category}",
                    question=str(question),
                    answer=None if category == 5 else str(answer),
                    evidence_refs=[str(ref) for ref in qa.get("evidence", [])],
                    slice_group=str(category),
                    category=category,
                    metadata=metadata,
                )
            )
            source_index += 1
    return candidates


def load_longmemeval_candidates(path: Path) -> list[NaturalBenchmarkCandidate]:
    data = json.loads(path.read_text(encoding="utf-8"))
    candidates: list[NaturalBenchmarkCandidate] = []
    source_index = 0
    for item in data:
        question_id = item["question_id"]
        question_type = item["question_type"]
        metadata = _metadata_without(
            item,
            {
                "question_id",
                "question_type",
                "question",
                "answer",
                "answer_session_ids",
                "haystack_session_ids",
                "haystack_sessions",
            },
        )
        candidates.append(
            _make_candidate(
                benchmark="longmemeval",
                item_id=f"LONGMEMEVAL-{question_id}",
                source_id=LONGMEM_SOURCE_ID,
                source_index=source_index,
                source_ref=f"question_id={question_id};question_type={question_type}",
                question=str(item["question"]),
                answer=str(item["answer"]),
                evidence_refs=[str(ref) for ref in item.get("answer_session_ids", [])],
                slice_group=str(question_type),
                category=str(question_type),
                metadata=metadata,
            )
        )
        source_index += 1
    return candidates
