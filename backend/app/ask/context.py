from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, replace
from typing import Literal, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.services import ResourceNotFoundError
from app.db.models import ApplicationUser, Conversation, Message

ConversationRole = Literal["user", "assistant"]
CONTEXT_TRUNCATION_MARKER = "[...older context truncated...]"
_RETRIEVAL_SECTION_LABEL_LINE = re.compile(
    r"^(current question|prior user|prior assistant):(?=[ \t]*\r?$)",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass(frozen=True)
class ConversationContextMessage:
    message_id: uuid.UUID
    role: ConversationRole
    content: str


@dataclass(frozen=True)
class ConversationContext:
    messages: tuple[ConversationContextMessage, ...]
    tail_message_id: uuid.UUID | None
    truncated: bool = False


def render_conversation_context(
    messages: tuple[ConversationContextMessage, ...],
) -> str:
    return "\n\n".join(
        f"Prior {message.role}:\n{message.content}" for message in messages
    )


def _escape_retrieval_section_labels(content: str) -> str:
    return _RETRIEVAL_SECTION_LABEL_LINE.sub(r"\1;", content)


def build_conversation_context(
    messages: tuple[ConversationContextMessage, ...],
    *,
    tail_message_id: uuid.UUID | None,
    max_messages: int,
    max_characters: int,
) -> ConversationContext:
    if max_messages < 1 or max_characters < 1:
        raise ValueError("conversation context limits must be positive")

    bounded = list(messages[-max_messages:])
    truncated = len(bounded) != len(messages)
    while len(bounded) > 2 and len(render_conversation_context(tuple(bounded))) > max_characters:
        del bounded[:2]
        truncated = True

    if len(render_conversation_context(tuple(bounded))) > max_characters:
        truncated = True
        for index, message in enumerate(tuple(bounded)):
            rendered = render_conversation_context(tuple(bounded))
            if len(rendered) <= max_characters:
                break
            overflow = len(rendered) - max_characters
            keep = max(0, len(message.content) - overflow - len(CONTEXT_TRUNCATION_MARKER))
            bounded[index] = replace(
                message,
                content=(
                    f"{CONTEXT_TRUNCATION_MARKER}"
                    f"{message.content[-keep:] if keep else ''}"
                ),
            )

    rendered = render_conversation_context(tuple(bounded))
    while len(rendered) > max_characters and len(bounded) > 1:
        del bounded[0]
        truncated = True
        rendered = render_conversation_context(tuple(bounded))
    if len(rendered) > max_characters and bounded:
        message = bounded[0]
        label = f"Prior {message.role}:\n"
        if len(label) > max_characters:
            bounded.clear()
        else:
            available = max_characters - len(label)
            marker = CONTEXT_TRUNCATION_MARKER[:available]
            tail_characters = max(0, available - len(marker))
            bounded[0] = replace(
                message,
                content=(
                    f"{marker}"
                    f"{message.content[-tail_characters:] if tail_characters else ''}"
                ),
            )
        truncated = True

    return ConversationContext(
        messages=tuple(bounded),
        tail_message_id=tail_message_id,
        truncated=truncated,
    )


def render_retrieval_query(question: str, context: ConversationContext) -> str:
    if not context.messages:
        return question
    retrieval_sections = (
        f"Current question:\n{_escape_retrieval_section_labels(question)}",
        *(
            f"Prior user:\n{_escape_retrieval_section_labels(message.content)}"
            for message in context.messages
            if message.role == "user"
        ),
    )
    return "\n\n".join(
        section
        for section in retrieval_sections
        if section
    )


class PostgresConversationContextLoader:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        max_messages: int,
        max_characters: int,
    ) -> None:
        self._session_factory = session_factory
        self._max_messages = max_messages
        self._max_characters = max_characters

    async def load(
        self, *, firebase_uid: str, conversation_id: uuid.UUID
    ) -> ConversationContext:
        async with self._session_factory() as session:
            owned_conversation_id = await session.scalar(
                select(Conversation.id)
                .join(ApplicationUser, ApplicationUser.id == Conversation.user_id)
                .where(
                    Conversation.id == conversation_id,
                    ApplicationUser.firebase_uid == firebase_uid,
                )
            )
            if owned_conversation_id is None:
                raise ResourceNotFoundError

            result = await session.execute(
                select(Message.id, Message.role, Message.content)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at.desc(), Message.id.desc())
                .limit(self._max_messages + 1)
            )
            rows = result.all()

        tail_message_id = rows[0].id if rows else None
        messages = tuple(
            ConversationContextMessage(
                message_id=row.id,
                role=cast(ConversationRole, row.role),
                content=row.content,
            )
            for row in reversed(rows)
        )
        return build_conversation_context(
            messages,
            tail_message_id=tail_message_id,
            max_messages=self._max_messages,
            max_characters=self._max_characters,
        )
