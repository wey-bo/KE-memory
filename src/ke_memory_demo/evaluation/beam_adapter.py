"""BEAM adapter onto the three-channel split.

``ingestion.beam`` is the production loader and attaches probing questions, with their
rubrics, directly to each ``Conversation``. That shape predates the channel split and
cannot be handed to a memory build: a rubric is the grading key.

This adapter is the seam. It reuses the production loader unchanged, then converts its
domain objects into channel types, sending questions to the question channel and rubrics to
gold. Message ids become evidence handles so gold references stay resolvable.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from ke_memory_demo.ingestion import load_beam_subset

from .channels import (
    BenchmarkId,
    HandleMint,
    BenchmarkQuestion,
    GoldChannel,
    GoldLabels,
    LoadedBenchmark,
    MemoryBuildInput,
    PublicConversation,
    PublicSession,
    PublicTurn,
    QuestionChannel,
)


def load_beam(archive_path: Path) -> LoadedBenchmark:
    """Load the fixed BEAM subset and split it into the three channels."""
    source_conversations = load_beam_subset(archive_path)

    conversations: list[PublicConversation] = []
    questions: list[BenchmarkQuestion] = []
    labels: list[GoldLabels] = []
    # BEAM ids name the dataset and directory, so handles are minted opaque.
    mint = HandleMint()

    for conversation in source_conversations:
        sessions: list[PublicSession] = []
        for ordinal, session in enumerate(conversation.sessions):
            turns: list[PublicTurn] = []
            for exchange in session.exchanges:
                for message in (exchange.user, exchange.assistant):
                    if not message.content.strip():
                        continue
                    turns.append(
                        PublicTurn(
                            evidence_handle=mint.mint("turn", message.id),
                            speaker=str(message.role.value),
                            text=message.content,
                            approximate_tokens=max(1, (len(message.content) + 3) // 4),
                        )
                    )
            if turns:
                sessions.append(
                    PublicSession(
                        session_handle=mint.mint("session", session.id),
                        turns=tuple(turns),
                        metadata={"public_session_ordinal": ordinal},
                    )
                )

        if not sessions:
            continue
        conversations.append(
            PublicConversation(
                conversation_handle=mint.mint("conversation", conversation.id),
                sessions=tuple(sessions),
            )
        )

        for ordinal, raw in enumerate(conversation.probing_questions):
            question = cast(dict[str, Any], raw)
            prompt = str(question.get("question") or "").strip()
            if not prompt:
                continue
            question_id = f"{conversation.id}--q{ordinal:03d}"
            questions.append(
                BenchmarkQuestion(
                    question_id=question_id,
                    conversation_handle=mint.mint("conversation", conversation.id),
                    question=prompt,
                )
            )
            labels.append(
                GoldLabels(
                    question_id=question_id,
                    conversation_handle=mint.mint("conversation", conversation.id),
                    category=str(question.get("category") or ""),
                    # A BEAM rubric is the scoring criterion, so it is gold. Leaving it on
                    # the conversation would hand the grading key to the arm.
                    rubrics=tuple(
                        str(item)
                        for item in cast(list[Any], question.get("rubric") or ())
                        if str(item)
                    ),
                    metadata={"category_ordinal": ordinal},
                )
            )

    build_input = MemoryBuildInput(
        conversations=tuple(conversations),

    )
    return LoadedBenchmark(
        benchmark=BenchmarkId.BEAM,
        build_input=build_input,
        questions=QuestionChannel(benchmark=BenchmarkId.BEAM, questions=tuple(questions)),
        gold=GoldChannel(benchmark=BenchmarkId.BEAM, labels=tuple(labels)),
        source_identity={"loader_id": "beam-adapter", "loader_version": "3"},
    )
