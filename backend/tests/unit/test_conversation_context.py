from __future__ import annotations

import uuid

import pytest

from app.ask.context import (
    CONTEXT_TRUNCATION_MARKER,
    ConversationContextMessage,
    build_conversation_context,
    render_conversation_context,
    render_retrieval_query,
)


def _message(index: int, role: str, content: str | None = None) -> ConversationContextMessage:
    return ConversationContextMessage(
        message_id=uuid.UUID(int=index + 1),
        role=role,  # type: ignore[arg-type]
        content=content or f"message {index}",
    )


def test_context_keeps_the_latest_messages_in_chronological_order() -> None:
    messages = tuple(
        _message(index, 'user' if index % 2 == 0 else 'assistant')
        for index in range(8)
    )

    context = build_conversation_context(
        messages,
        tail_message_id=messages[-1].message_id,
        max_messages=6,
        max_characters=10_000,
    )

    assert [message.message_id for message in context.messages] == [
        message.message_id for message in messages[-6:]
    ]
    assert context.tail_message_id == messages[-1].message_id
    assert context.truncated


def test_context_removes_old_exchanges_then_truncates_at_a_unicode_boundary() -> None:
    messages = (
        _message(0, 'user', 'old user ' + ('x' * 100)),
        _message(1, 'assistant', 'old answer ' + ('x' * 100)),
        _message(2, 'user', 'new user ' + ('\U0001f642' * 100)),
        _message(3, 'assistant', 'new answer ' + ('y' * 100)),
    )

    context = build_conversation_context(
        messages,
        tail_message_id=messages[-1].message_id,
        max_messages=6,
        max_characters=120,
    )
    rendered = render_conversation_context(context.messages)

    assert len(rendered) <= 120
    assert context.truncated
    assert CONTEXT_TRUNCATION_MARKER in rendered
    assert context.messages[-1].content.startswith(CONTEXT_TRUNCATION_MARKER)
    assert context.messages[-1].content.endswith('y')
    rendered.encode('utf-8')


def test_retrieval_query_projects_current_question_and_prior_user_only() -> None:
    messages = (
        _message(0, 'user', 'I control a creature named Slippery Bogle.'),
        _message(1, 'assistant', 'It has hexproof.'),
    )
    context = build_conversation_context(
        messages,
        tail_message_id=messages[-1].message_id,
        max_messages=6,
        max_characters=6_000,
    )

    query = render_retrieval_query('What if it loses that ability?', context)

    assert query.startswith('Current question:\nWhat if it loses that ability?')
    assert 'Prior user:' in query
    assert 'Slippery Bogle' in query
    assert 'Prior assistant:' not in query
    assert 'hexproof' not in query


def test_empty_context_is_stable_and_leaves_the_retrieval_question_unchanged() -> None:
    context = build_conversation_context(
        (),
        tail_message_id=None,
        max_messages=6,
        max_characters=6_000,
    )

    assert context.messages == ()
    assert context.tail_message_id is None
    assert not context.truncated
    assert render_retrieval_query("What is flying?", context) == "What is flying?"


def test_odd_message_sequence_retains_the_newest_messages_deterministically() -> None:
    messages = tuple(
        _message(index, "user" if index % 2 == 0 else "assistant")
        for index in range(7)
    )

    context = build_conversation_context(
        messages,
        tail_message_id=messages[-1].message_id,
        max_messages=3,
        max_characters=10_000,
    )

    assert context.messages == messages[-3:]
    assert context.truncated


def test_invalid_context_limits_are_rejected() -> None:
    with pytest.raises(ValueError, match="positive"):
        build_conversation_context(
            (),
            tail_message_id=None,
            max_messages=0,
            max_characters=6_000,
        )


def test_context_respects_a_limit_smaller_than_a_role_label() -> None:
    context = build_conversation_context(
        (_message(0, "user", "oversized"),),
        tail_message_id=uuid.uuid4(),
        max_messages=6,
        max_characters=1,
    )

    assert len(render_conversation_context(context.messages)) <= 1
    assert context.truncated
