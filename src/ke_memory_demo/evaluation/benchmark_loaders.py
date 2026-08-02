"""LoCoMo and LongMemEval loaders producing the three-channel split.

Both benchmarks arrive as a single JSON file interleaving conversation content with
questions and answers. Each loader separates them so a memory build receives only
:class:`MemoryBuildInput`, which has no question field at all.

Two source-specific hazards, both found in review:

- LongMemEval names answer-bearing sessions ``answer_*``, so a raw session id discloses
  gold. Public session handles are opaque ordinals and raw ids stay in gold metadata.
- Public metadata is allowlisted, so dataset-identifying fields such as ``benchmark``,
  ``split`` and ``question_type`` never reach the build input. They would let a mapper
  special-case a dataset, which the plan forbids.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from .channels import (
    BenchmarkId,
    HandleMint,
    BenchmarkQuestion,
    ChannelError,
    GoldChannel,
    GoldLabels,
    LoadedBenchmark,
    MemoryBuildInput,
    PublicConversation,
    PublicSession,
    PublicTurn,
    QuestionChannel,
)


class BenchmarkSourceError(ChannelError):
    """A benchmark source file is missing, unreadable or malformed."""


def _turn(handle: str, speaker: str, text: str) -> PublicTurn:
    return PublicTurn(
        evidence_handle=handle,
        speaker=speaker,
        text=text,
        approximate_tokens=max(1, (len(text) + 3) // 4),
    )


def load_locomo(path: Path) -> LoadedBenchmark:
    """Load LoCoMo, preserving each utterance as an addressable turn.

    LoCoMo has no assistant role: two people converse. Every utterance becomes one turn so
    nothing is merged away, and each keeps its ``dia_id`` as its evidence handle so gold
    references resolve.
    """
    payload = _read_json(path)
    if not isinstance(payload, list):
        raise BenchmarkSourceError("LoCoMo source must be a JSON array of conversations")

    conversations: list[PublicConversation] = []
    questions: list[BenchmarkQuestion] = []
    labels: list[GoldLabels] = []
    # A handle such as "locomo-conv-26" names the dataset outright, so handles are minted
    # opaque and the controller keeps the translation.
    mint = HandleMint()

    for index, raw in enumerate(cast(list[Any], payload)):
        entry = cast(dict[str, Any], raw)
        sample_id = str(entry.get("sample_id") or f"locomo-{index}")
        source_handle = f"locomo-{sample_id}"
        handle = mint.mint("conversation", source_handle)
        body = cast(dict[str, Any], entry.get("conversation") or {})

        sessions: list[PublicSession] = []
        for ordinal, session_key in enumerate(_ordered_session_keys(body)):
            turns = [cast(dict[str, Any], t) for t in cast(list[Any], body[session_key])]
            built = tuple(
                _turn(
                    mint.mint(
                        "turn",
                        f"{source_handle}::{t.get('dia_id') or f'{session_key}-{i}'}",
                    ),
                    str(t.get("speaker") or "unknown"),
                    str(t.get("text") or ""),
                )
                for i, t in enumerate(turns)
                if str(t.get("text") or "").strip()
            )
            if built:
                sessions.append(
                    PublicSession(
                        session_handle=mint.mint("session", f"{source_handle}::{session_key}"),
                        turns=built,
                        metadata={"public_session_ordinal": ordinal},
                    )
                )

        if not sessions:
            continue
        conversations.append(
            PublicConversation(conversation_handle=handle, sessions=tuple(sessions))
        )

        for qa_index, raw_qa in enumerate(cast(list[Any], entry.get("qa") or [])):
            qa = cast(dict[str, Any], raw_qa)
            category = str(qa.get("category", ""))
            question_id = f"{source_handle}--q{qa_index}"
            questions.append(
                BenchmarkQuestion(
                    question_id=question_id,
                    conversation_handle=handle,
                    question=str(qa.get("question") or "").strip() or "(missing question)",
                )
            )
            labels.append(
                GoldLabels(
                    question_id=question_id,
                    conversation_handle=handle,
                    answer=str(qa.get("answer", "")),
                    category=category,
                    evidence_refs=tuple(
                        opaque
                        for e in cast(list[Any], qa.get("evidence") or ())
                        if (opaque := mint.opaque_for(f"{source_handle}::{e}")) is not None
                    ),
                    # Category 5 lacks sufficient official answer gold.
                    requires_manual_review=category == "5",
                    metadata={"locomo_category": category},
                )
            )

    return _assemble(BenchmarkId.LOCOMO, path, conversations, questions, labels)


def load_longmemeval(path: Path) -> LoadedBenchmark:
    """Load LongMemEval, one conversation per question, with opaque session handles."""
    payload = _read_json(path)
    if not isinstance(payload, list):
        raise BenchmarkSourceError("LongMemEval source must be a JSON array of questions")

    conversations: list[PublicConversation] = []
    questions: list[BenchmarkQuestion] = []
    labels: list[GoldLabels] = []
    split = path.stem
    mint = HandleMint()

    for raw in cast(list[Any], payload):
        entry = cast(dict[str, Any], raw)
        question_id = str(entry.get("question_id") or "")
        if not question_id:
            raise BenchmarkSourceError("LongMemEval entry is missing question_id")
        source_handle = f"longmemeval-{question_id}"
        handle = mint.mint("conversation", source_handle)

        haystack = [
            cast(list[Any], s) for s in cast(list[Any], entry.get("haystack_sessions") or [])
        ]
        raw_ids = [str(s) for s in cast(list[Any], entry.get("haystack_session_ids") or [])]
        answer_sessions = {str(s) for s in cast(list[Any], entry.get("answer_session_ids") or [])}

        sessions: list[PublicSession] = []
        opaque_by_raw: dict[str, str] = {}
        for ordinal, turns in enumerate(haystack):
            raw_id = raw_ids[ordinal] if ordinal < len(raw_ids) else f"session_{ordinal}"
            opaque = mint.mint("session", f"{source_handle}::{raw_id}")
            opaque_by_raw[raw_id] = opaque
            typed = [cast(dict[str, Any], t) for t in turns]
            built = tuple(
                _turn(
                    mint.mint("turn", f"{source_handle}::{raw_id}::{i}"),
                    str(t.get("role") or "unknown"),
                    str(t.get("content") or ""),
                )
                for i, t in enumerate(typed)
                if str(t.get("content") or "").strip()
            )
            if built:
                sessions.append(
                    PublicSession(
                        session_handle=opaque,
                        turns=built,
                        metadata={"public_session_ordinal": ordinal},
                    )
                )

        if not sessions:
            continue
        conversations.append(
            PublicConversation(conversation_handle=handle, sessions=tuple(sessions))
        )
        questions.append(
            BenchmarkQuestion(
                question_id=question_id,
                conversation_handle=handle,
                question=str(entry.get("question") or "").strip() or "(missing question)",
            )
        )
        labels.append(
            GoldLabels(
                question_id=question_id,
                conversation_handle=handle,
                answer=str(entry.get("answer", "")),
                category=str(entry.get("question_type", "")),
                # Gold names sessions. Selection is scored at turn level, so the scorer
                # expands a session handle to its turns rather than the loader flattening
                # it, which keeps the gold artifact faithful to the source.
                evidence_refs=tuple(
                    opaque_by_raw[raw]
                    for raw in sorted(answer_sessions)
                    if raw in opaque_by_raw
                ),
                metadata=cast(
                    "dict[str, Any]",
                    {
                        "question_date": str(entry.get("question_date", "")),
                        "split": split,
                        "oracle_haystack": "oracle" in split,
                        "raw_answer_session_ids": sorted(answer_sessions),
                    },
                ),
            )
        )

    return _assemble(BenchmarkId.LONGMEMEVAL, path, conversations, questions, labels)


def _assemble(
    benchmark: BenchmarkId,
    path: Path,
    conversations: list[PublicConversation],
    questions: list[BenchmarkQuestion],
    labels: list[GoldLabels],
) -> LoadedBenchmark:
    build_input = MemoryBuildInput(
        conversations=tuple(conversations),

    )
    return LoadedBenchmark(
        benchmark=benchmark,
        build_input=build_input,
        questions=QuestionChannel(benchmark=benchmark, questions=tuple(questions)),
        gold=GoldChannel(benchmark=benchmark, labels=tuple(labels)),
        # Controller-side only: never visible to a memory build.
        source_identity={
            "loader_id": f"{benchmark}-loader",
            "loader_version": "3",
            "source_path": str(path),
        },
    )


def _ordered_session_keys(body: dict[str, Any]) -> list[str]:
    keys = [
        key
        for key, value in body.items()
        if key.startswith("session_")
        and not key.endswith("_date_time")
        and isinstance(value, list)
    ]

    def sort_key(key: str) -> tuple[int, str]:
        suffix = key.removeprefix("session_")
        return (int(suffix), key) if suffix.isdigit() else (10**6, key)

    return sorted(keys, key=sort_key)


def _read_json(path: Path) -> object:
    try:
        with path.open("r", encoding="utf-8") as stream:
            return json.load(stream)
    except FileNotFoundError as exc:
        raise BenchmarkSourceError(f"benchmark source not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise BenchmarkSourceError(f"benchmark source is not valid JSON: {path}") from exc
    except OSError as exc:
        raise BenchmarkSourceError(f"unable to read benchmark source {path}") from exc

