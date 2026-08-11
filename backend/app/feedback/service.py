from __future__ import annotations

import uuid
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.auth import AuthenticatedUser
from app.api.services import ResourceNotFoundError
from app.db.models import ApplicationUser, Conversation, Feedback, Message


class SqlFeedbackService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def submit(
        self,
        *,
        user: AuthenticatedUser,
        answer_message_id: UUID,
        rating: int,
        comment: str | None,
    ) -> None:
        async with self._session_factory.begin() as session:
            owner = (
                await session.execute(
                    select(ApplicationUser.id)
                    .join(Conversation, Conversation.user_id == ApplicationUser.id)
                    .join(Message, Message.conversation_id == Conversation.id)
                    .where(
                        ApplicationUser.firebase_uid == user.firebase_uid,
                        Message.id == answer_message_id,
                        Message.role == "assistant",
                    )
                )
            ).scalar_one_or_none()
            if owner is None:
                raise ResourceNotFoundError

            statement = insert(Feedback).values(
                id=uuid.uuid4(),
                user_id=owner,
                answer_message_id=answer_message_id,
                rating=rating,
                comment=comment,
            )
            await session.execute(
                statement.on_conflict_do_update(
                    index_elements=[Feedback.user_id, Feedback.answer_message_id],
                    set_={"rating": rating, "comment": comment},
                )
            )

