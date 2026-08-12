from __future__ import annotations

import uuid

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.auth import AuthenticatedUser
from app.db.models import ApplicationUser


class PostgresUserRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get_or_create(self, user: AuthenticatedUser) -> uuid.UUID:
        insert_statement = insert(ApplicationUser).values(
            id=uuid.uuid4(),
            firebase_uid=user.firebase_uid,
            email=user.email,
        )
        statement = insert_statement.on_conflict_do_update(
            index_elements=[ApplicationUser.firebase_uid],
            set_={
                "email": func.coalesce(
                    insert_statement.excluded.email,
                    ApplicationUser.email,
                ),
                "updated_at": func.now(),
            },
        ).returning(ApplicationUser.id)
        async with self._session_factory.begin() as session:
            user_id: uuid.UUID = (await session.execute(statement)).scalar_one()
            return user_id
