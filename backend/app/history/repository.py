from __future__ import annotations

from typing import Literal, cast
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.api.auth import AuthenticatedUser
from app.api.schemas import (
    CitationResponse,
    ConversationDetail,
    ConversationMessage,
    ConversationSummary,
)
from app.api.services import ResourceNotFoundError
from app.db.models import AnswerCitation, ApplicationUser, Conversation, Message


class SqlConversationService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def list(self, *, user: AuthenticatedUser) -> list[ConversationSummary]:
        async with self._session_factory() as session:
            conversations = (
                await session.execute(
                    select(Conversation)
                    .join(ApplicationUser, ApplicationUser.id == Conversation.user_id)
                    .where(ApplicationUser.firebase_uid == user.firebase_uid)
                    .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
                )
            ).scalars().all()
        return [
            ConversationSummary(
                id=conversation.id,
                title=conversation.title,
                updated_at=conversation.updated_at,
            )
            for conversation in conversations
        ]

    async def get(
        self, *, user: AuthenticatedUser, conversation_id: UUID
    ) -> ConversationDetail:
        async with self._session_factory() as session:
            conversation = (
                await session.execute(
                    select(Conversation)
                    .join(ApplicationUser, ApplicationUser.id == Conversation.user_id)
                    .where(
                        Conversation.id == conversation_id,
                        ApplicationUser.firebase_uid == user.firebase_uid,
                    )
                    .options(
                        selectinload(Conversation.messages)
                        .selectinload(Message.citations)
                        .selectinload(AnswerCitation.passage)
                    )
                )
            ).scalar_one_or_none()
        if conversation is None:
            raise ResourceNotFoundError

        messages = [
            ConversationMessage(
                id=message.id,
                role=cast(Literal["user", "assistant"], message.role),
                content=message.content,
                created_at=message.created_at,
                citations=[
                    CitationResponse(
                        passage_id=str(citation.passage_id),
                        claim=citation.claim,
                        label=str(
                            citation.passage.passage_metadata.get(
                                "citation_label", citation.passage.canonical_key
                            )
                        ),
                        url=str(citation.passage.passage_metadata.get("canonical_url", "")),
                    )
                    for citation in message.citations
                ],
            )
            for message in conversation.messages
        ]
        return ConversationDetail(id=conversation.id, title=conversation.title, messages=messages)

    async def delete(self, *, user: AuthenticatedUser, conversation_id: UUID) -> None:
        owner_id = select(ApplicationUser.id).where(
            ApplicationUser.firebase_uid == user.firebase_uid
        )
        async with self._session_factory.begin() as session:
            deleted = await session.execute(
                delete(Conversation)
                .where(
                    Conversation.id == conversation_id,
                    Conversation.user_id.in_(owner_id),
                )
                .returning(Conversation.id)
            )
            if deleted.scalar_one_or_none() is None:
                raise ResourceNotFoundError
