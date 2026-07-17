from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
import hashlib
from typing import cast

from ke_memory_demo.core.ids import content_id
from ke_memory_demo.core.json import JsonObject, JsonValue, canonical_json
from ke_memory_demo.domain import Conversation

from .models import OriginalAnswerField, ProbeQuestion, QuestionCategory


_ANSWER_FIELDS: tuple[OriginalAnswerField, ...] = (
    "ideal_answer",
    "ideal_response",
    "answer",
    "ideal_summary",
    "expected_compliance",
)
_NORMALIZED_FIELDS = frozenset(
    {"question", "rubric", "category", "category_ordinal", *_ANSWER_FIELDS}
)
_CATEGORY_ORDER = {category: ordinal for ordinal, category in enumerate(QuestionCategory)}


class QuestionNormalizationError(ValueError):
    """A probing question cannot satisfy the frozen BEAM evaluation contract."""


def question_manifest_sha256(questions: Sequence[ProbeQuestion]) -> str:
    ordered = tuple(
        sorted(
            (ProbeQuestion.model_validate(item) for item in questions),
            key=lambda item: item.id,
        )
    )
    payload = cast(JsonValue, [item.model_dump(mode="json") for item in ordered])
    return hashlib.sha256(canonical_json(payload)).hexdigest()


def normalize_question(
    raw: JsonObject,
    *,
    conversation_id: str,
    category: QuestionCategory | str,
    ordinal: int,
) -> ProbeQuestion:
    if not conversation_id:
        raise QuestionNormalizationError("conversation ID must not be empty")
    try:
        normalized_category = QuestionCategory(category)
    except ValueError:
        raise QuestionNormalizationError(f"unknown question category: {category!r}") from None
    if isinstance(ordinal, bool) or ordinal < 0:
        raise QuestionNormalizationError("question ordinal must be a nonnegative integer")

    question = _required_text(raw.get("question"), field="question")
    rubric_value = raw.get("rubric")
    if not isinstance(rubric_value, list) or not rubric_value:
        raise QuestionNormalizationError("question rubric must be a nonempty list")
    rubric = tuple(
        _required_text(item, field=f"rubric[{index}]") for index, item in enumerate(rubric_value)
    )
    answer_field, ideal_answer = _select_answer(raw)
    identity: JsonObject = {
        "conversation_id": conversation_id,
        "category": normalized_category.value,
        "ordinal": ordinal,
        "question": question,
    }
    return ProbeQuestion(
        id=content_id("probe_question", identity),
        conversation_id=conversation_id,
        category=normalized_category,
        ordinal=ordinal,
        question=question,
        ideal_answer=ideal_answer,
        original_answer_field=answer_field,
        rubric=rubric,
        raw_metadata={key: value for key, value in raw.items() if key not in _NORMALIZED_FIELDS},
    )


def normalize_questions(conversations: Sequence[Conversation]) -> tuple[ProbeQuestion, ...]:
    ordered_conversations = tuple(sorted(conversations, key=_conversation_sort_key))
    conversation_ids = tuple(conversation.id for conversation in ordered_conversations)
    if len(conversation_ids) != len(set(conversation_ids)):
        raise QuestionNormalizationError("duplicate Conversation IDs are not allowed")

    normalized: list[ProbeQuestion] = []
    for conversation in ordered_conversations:
        conversation_questions: list[ProbeQuestion] = []
        for raw in conversation.probing_questions:
            category = raw.get("category")
            ordinal = raw.get("category_ordinal")
            if not isinstance(category, str):
                raise QuestionNormalizationError("question category provenance is missing")
            if isinstance(ordinal, bool) or not isinstance(ordinal, int):
                raise QuestionNormalizationError("question ordinal provenance is missing")
            conversation_questions.append(
                normalize_question(
                    raw,
                    conversation_id=conversation.id,
                    category=category,
                    ordinal=ordinal,
                )
            )
        _validate_conversation_questions(conversation.id, conversation_questions)
        normalized.extend(
            sorted(
                conversation_questions,
                key=lambda item: (_CATEGORY_ORDER[item.category], item.ordinal, item.id),
            )
        )

    identifiers = tuple(question.id for question in normalized)
    if len(identifiers) != len(set(identifiers)):
        raise QuestionNormalizationError("duplicate deterministic question IDs are not allowed")
    return tuple(normalized)


def _select_answer(raw: JsonObject) -> tuple[OriginalAnswerField, str]:
    for field in _ANSWER_FIELDS:
        value = raw.get(field)
        if value is None or value == "":
            continue
        return field, _required_text(value, field=field)
    raise QuestionNormalizationError("question has no supported nonempty ideal answer")


def _required_text(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise QuestionNormalizationError(f"{field} must be a nonempty string")
    return value


def _conversation_sort_key(conversation: Conversation) -> tuple[int, str]:
    directory_id = conversation.source_metadata.get("beam_directory_id")
    if isinstance(directory_id, bool) or not isinstance(directory_id, int):
        directory_id = 2**63 - 1
    return directory_id, conversation.id


def _validate_conversation_questions(
    conversation_id: str,
    questions: Sequence[ProbeQuestion],
) -> None:
    counts = Counter(question.category for question in questions)
    if counts != Counter({category: 2 for category in QuestionCategory}):
        raise QuestionNormalizationError(
            f"Conversation {conversation_id} must have two questions in every category"
        )
    for category in QuestionCategory:
        ordinals = tuple(
            sorted(question.ordinal for question in questions if question.category is category)
        )
        if ordinals != (0, 1):
            raise QuestionNormalizationError(
                f"Conversation {conversation_id} category {category.value} must use ordinals 0,1"
            )
