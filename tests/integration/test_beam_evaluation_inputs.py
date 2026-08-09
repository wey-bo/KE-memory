from __future__ import annotations

from collections import Counter

from ke_memory_demo.domain import Conversation
from ke_memory_demo.evaluation import QuestionCategory, normalize_questions
from ke_memory_demo.ingestion import load_beam_subset

from fixtures.datasets import require_dataset


EXPECTED_ANSWER_FIELDS = {
    "ideal_answer": 6,
    "ideal_response": 6,
    "answer": 30,
    "ideal_summary": 6,
    "expected_compliance": 12,
}


def test_fixed_beam_evaluation_inputs_are_complete_stable_and_not_ingested() -> None:
    conversations = load_beam_subset(require_dataset("BEAM.zip"))
    questions = normalize_questions(conversations)

    assert len(questions) == 60
    assert Counter(question.category for question in questions) == {
        category: 6 for category in QuestionCategory
    }
    assert Counter(question.original_answer_field for question in questions) == (
        EXPECTED_ANSWER_FIELDS
    )
    assert all(
        count == 2
        for count in Counter(
            (question.conversation_id, question.category) for question in questions
        ).values()
    )
    assert tuple(question.id for question in questions) == tuple(
        question.id for question in normalize_questions(tuple(reversed(conversations)))
    )

    by_conversation = {conversation.id: conversation for conversation in conversations}
    for question in questions:
        record_content = _record_content(by_conversation[question.conversation_id])
        exchange_content = "\n".join(record_content)
        assert question.question not in exchange_content
        assert question.ideal_answer not in record_content
        assert all(item not in record_content for item in question.rubric)


def _record_content(conversation: Conversation) -> set[str]:
    return {
        record.content
        for session in conversation.sessions
        for exchange in session.exchanges
        for record in (exchange.user, *exchange.events, exchange.assistant)
    }
