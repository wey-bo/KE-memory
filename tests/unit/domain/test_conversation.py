from __future__ import annotations

import hashlib

import pytest
from pydantic import ValidationError

from ke_memory_demo.core.json import JsonObject, JsonValue
from ke_memory_demo.domain.conversation import (
    Conversation,
    Exchange,
    Message,
    MessageRole,
    MessageSpan,
    Session,
    ToolEvent,
    ToolEventKind,
)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _message(
    message_id: str,
    role: MessageRole,
    content: str,
    source_order: int,
) -> Message:
    return Message(id=message_id, role=role, content=content, source_order=source_order)


def _exchange(
    exchange_id: str = "exchange-1",
    global_ordinal: int = 0,
    *,
    session_id: str = "session-1",
    user_id: str = "message-u",
    assistant_id: str = "message-a",
    event_ids: tuple[str, str] = ("event-call", "event-result"),
) -> Exchange:
    return Exchange(
        id=exchange_id,
        session_id=session_id,
        user=_message(user_id, MessageRole.USER, "run it", 0),
        events=(
            ToolEvent(
                id=event_ids[0],
                kind=ToolEventKind.TOOL_CALL,
                content='{"name":"run"}',
                source_order=1,
            ),
            ToolEvent(
                id=event_ids[1],
                kind=ToolEventKind.TOOL_RESULT,
                content='{"ok":true}',
                source_order=2,
            ),
        ),
        assistant=_message(assistant_id, MessageRole.ASSISTANT, "done", 3),
        global_ordinal=global_ordinal,
    )


def test_message_and_tool_event_enums_have_exact_values() -> None:
    assert [role.value for role in MessageRole] == ["user", "assistant"]
    assert [kind.value for kind in ToolEventKind] == ["tool_call", "tool_result"]


def test_message_preserves_unicode_content_and_computes_utf8_hash() -> None:
    content = "  Tea \u2615\ufe0f\n\u7b2c\u4e8c\u884c  "

    message = Message(id="message-1", role=MessageRole.USER, content=content, source_order=0)

    assert message.content == content
    assert message.content_hash == _sha256(content)


def test_message_verifies_a_supplied_content_hash() -> None:
    content = "exact source text"

    message = Message(
        id="message-1",
        role=MessageRole.USER,
        content=content,
        source_order=0,
        content_hash=_sha256(content),
    )

    assert message.content_hash == _sha256(content)
    with pytest.raises(ValidationError, match="content_hash"):
        Message(
            id="message-1",
            role=MessageRole.USER,
            content=content,
            source_order=0,
            content_hash="0" * 64,
        )


def test_tool_event_computes_and_verifies_its_content_hash() -> None:
    content = '{"query":"tea"}'
    event = ToolEvent(
        id="event-1",
        kind=ToolEventKind.TOOL_CALL,
        content=content,
        source_order=1,
    )

    assert event.content_hash == _sha256(content)
    with pytest.raises(ValidationError, match="content_hash"):
        ToolEvent(
            id="event-1",
            kind=ToolEventKind.TOOL_CALL,
            content=content,
            source_order=1,
            content_hash="f" * 64,
        )


def test_message_validates_unicode_code_point_span_and_exact_text_hash() -> None:
    message = Message(id="message-1", role=MessageRole.USER, content="A\U0001f375B", source_order=0)
    span = MessageSpan(
        message_id=message.id,
        start_char=1,
        end_char=2,
        text_hash=_sha256("\U0001f375"),
    )

    message.validate_span(span)


def test_span_rejects_out_of_range_offsets() -> None:
    message = Message(id="m1", role=MessageRole.USER, content="abc", source_order=0)
    span = MessageSpan(message_id="m1", start_char=0, end_char=4, text_hash="b" * 64)

    with pytest.raises(ValueError, match="outside message"):
        message.validate_span(span)


def test_span_rejects_wrong_message_and_substring_hash() -> None:
    message = Message(id="message-1", role=MessageRole.USER, content="abc", source_order=0)

    with pytest.raises(ValueError, match="different message"):
        message.validate_span(
            MessageSpan(message_id="message-2", start_char=0, end_char=1, text_hash=_sha256("a"))
        )
    with pytest.raises(ValueError, match="text_hash"):
        message.validate_span(
            MessageSpan(message_id="message-1", start_char=0, end_char=1, text_hash="0" * 64)
        )


@pytest.mark.parametrize(
    ("start_char", "end_char"),
    [(-1, 1), (0, 0), (2, 1)],
)
def test_span_must_be_a_non_empty_half_open_range(start_char: int, end_char: int) -> None:
    with pytest.raises(ValidationError):
        MessageSpan(
            message_id="message-1",
            start_char=start_char,
            end_char=end_char,
            text_hash="a" * 64,
        )


def test_exchange_preserves_event_order_as_an_immutable_tuple() -> None:
    exchange = Exchange.model_validate(
        {
            "id": "exchange-1",
            "session_id": "session-1",
            "user": _message("message-u", MessageRole.USER, "run it", 0),
            "events": [
                ToolEvent(
                    id="event-1",
                    kind=ToolEventKind.TOOL_CALL,
                    content="call",
                    source_order=1,
                ),
                ToolEvent(
                    id="event-2",
                    kind=ToolEventKind.TOOL_RESULT,
                    content="result",
                    source_order=2,
                ),
            ],
            "assistant": _message("message-a", MessageRole.ASSISTANT, "done", 3),
            "global_ordinal": 4,
        }
    )

    assert isinstance(exchange.events, tuple)
    assert [event.id for event in exchange.events] == ["event-1", "event-2"]
    with pytest.raises(ValidationError):
        exchange.global_ordinal = 5


def test_exchange_validates_roles_and_strict_source_ordering() -> None:
    with pytest.raises(ValidationError, match="user role"):
        Exchange(
            id="exchange-1",
            session_id="session-1",
            user=_message("message-u", MessageRole.ASSISTANT, "wrong", 0),
            assistant=_message("message-a", MessageRole.ASSISTANT, "done", 1),
            global_ordinal=0,
        )

    with pytest.raises(ValidationError, match="assistant role"):
        Exchange(
            id="exchange-1",
            session_id="session-1",
            user=_message("message-u", MessageRole.USER, "start", 0),
            assistant=_message("message-a", MessageRole.USER, "wrong", 1),
            global_ordinal=0,
        )

    with pytest.raises(ValidationError, match="source order"):
        Exchange(
            id="exchange-1",
            session_id="session-1",
            user=_message("message-u", MessageRole.USER, "start", 0),
            events=(
                ToolEvent(
                    id="event-2",
                    kind=ToolEventKind.TOOL_RESULT,
                    content="second",
                    source_order=2,
                ),
                ToolEvent(
                    id="event-1",
                    kind=ToolEventKind.TOOL_CALL,
                    content="first",
                    source_order=1,
                ),
            ),
            assistant=_message("message-a", MessageRole.ASSISTANT, "done", 3),
            global_ordinal=0,
        )


def test_session_validates_exchange_ownership_and_ordinal_order() -> None:
    first = _exchange("exchange-1", global_ordinal=0)
    second = _exchange("exchange-2", global_ordinal=1)

    session = Session(
        id="session-1",
        conversation_id="conversation-1",
        exchanges=(first, second),
    )

    assert session.exchanges == (first, second)
    with pytest.raises(ValidationError, match="ordinal order"):
        Session(
            id="session-1",
            conversation_id="conversation-1",
            exchanges=(second, first),
        )
    with pytest.raises(ValidationError, match="belongs to session"):
        Session(
            id="another-session",
            conversation_id="conversation-1",
            exchanges=(first,),
        )


def test_conversation_keeps_probing_questions_separate_and_copies_json_inputs() -> None:
    exchange = _exchange()
    source_values: list[JsonValue] = ["source"]
    question_values: list[JsonValue] = ["gold"]
    source_metadata: JsonObject = {"values": source_values}
    probing_question: JsonObject = {"answers": question_values}

    conversation = Conversation.model_validate(
        {
            "id": "conversation-1",
            "sessions": [
                Session(
                    id="session-1",
                    conversation_id="conversation-1",
                    exchanges=(exchange,),
                )
            ],
            "probing_questions": [probing_question],
            "source_metadata": source_metadata,
        }
    )
    source_values.append("mutated")
    question_values.append("mutated")

    assert isinstance(conversation.sessions, tuple)
    assert isinstance(conversation.probing_questions, tuple)
    assert conversation.source_metadata == {"values": ["source"]}
    assert conversation.probing_questions == ({"answers": ["gold"]},)


def test_conversation_validates_session_ownership_and_unique_ids() -> None:
    session = Session(id="session-1", conversation_id="other", exchanges=())

    with pytest.raises(ValidationError, match="belongs to conversation"):
        Conversation(id="conversation-1", sessions=(session,))

    matching = Session(id="session-1", conversation_id="conversation-1", exchanges=())
    with pytest.raises(ValidationError, match="duplicate session"):
        Conversation(id="conversation-1", sessions=(matching, matching))


def test_conversation_requires_global_ordinals_to_increase_across_sessions() -> None:
    first = _exchange(
        "exchange-1",
        global_ordinal=2,
        session_id="session-1",
        user_id="message-u-1",
        assistant_id="message-a-1",
        event_ids=("event-call-1", "event-result-1"),
    )
    second = _exchange(
        "exchange-2",
        global_ordinal=1,
        session_id="session-2",
        user_id="message-u-2",
        assistant_id="message-a-2",
        event_ids=("event-call-2", "event-result-2"),
    )
    sessions = (
        Session(id="session-1", conversation_id="conversation-1", exchanges=(first,)),
        Session(id="session-2", conversation_id="conversation-1", exchanges=(second,)),
    )

    with pytest.raises(ValidationError, match="global ordinal order"):
        Conversation(id="conversation-1", sessions=sessions)


def test_conversation_rejects_duplicate_exchange_ids_across_sessions() -> None:
    first = _exchange(
        "exchange-shared",
        global_ordinal=0,
        session_id="session-1",
        user_id="message-u-1",
        assistant_id="message-a-1",
        event_ids=("event-call-1", "event-result-1"),
    )
    second = _exchange(
        "exchange-shared",
        global_ordinal=1,
        session_id="session-2",
        user_id="message-u-2",
        assistant_id="message-a-2",
        event_ids=("event-call-2", "event-result-2"),
    )
    sessions = (
        Session(id="session-1", conversation_id="conversation-1", exchanges=(first,)),
        Session(id="session-2", conversation_id="conversation-1", exchanges=(second,)),
    )

    with pytest.raises(ValidationError, match="duplicate exchange"):
        Conversation(id="conversation-1", sessions=sessions)


def test_conversation_rejects_duplicate_message_ids_across_exchanges_and_roles() -> None:
    first = _exchange(
        "exchange-1",
        global_ordinal=0,
        assistant_id="message-shared",
        event_ids=("event-call-1", "event-result-1"),
    )
    second = _exchange(
        "exchange-2",
        global_ordinal=1,
        user_id="message-shared",
        assistant_id="message-a-2",
        event_ids=("event-call-2", "event-result-2"),
    )
    session = Session(
        id="session-1",
        conversation_id="conversation-1",
        exchanges=(first, second),
    )

    with pytest.raises(ValidationError, match="duplicate message"):
        Conversation(id="conversation-1", sessions=(session,))


def test_conversation_rejects_duplicate_tool_event_ids_across_exchanges_and_kinds() -> None:
    first = _exchange(
        "exchange-1",
        global_ordinal=0,
        user_id="message-u-1",
        assistant_id="message-a-1",
        event_ids=("event-shared", "event-result-1"),
    )
    second = _exchange(
        "exchange-2",
        global_ordinal=1,
        user_id="message-u-2",
        assistant_id="message-a-2",
        event_ids=("event-call-2", "event-shared"),
    )
    session = Session(
        id="session-1",
        conversation_id="conversation-1",
        exchanges=(first, second),
    )

    with pytest.raises(ValidationError, match="duplicate tool event"):
        Conversation(id="conversation-1", sessions=(session,))


def test_conversation_models_reject_extra_fields() -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        Message.model_validate(
            {
                "id": "message-1",
                "role": "user",
                "content": "hello",
                "source_order": 0,
                "unexpected": True,
            }
        )
