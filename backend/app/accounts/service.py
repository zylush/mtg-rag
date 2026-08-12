from __future__ import annotations

import asyncio
from collections.abc import Callable

from firebase_admin import auth as firebase_auth  # type: ignore[import-untyped]
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.auth import AuthenticatedUser
from app.db.models import ApplicationUser


class AccountDeletionService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        delete_firebase_user: Callable[[str], object] = firebase_auth.delete_user,
    ) -> None:
        self._session_factory = session_factory
        self._delete_firebase_user = delete_firebase_user

    async def delete(self, *, user: AuthenticatedUser) -> None:
        async with self._session_factory.begin() as session:
            await session.execute(
                delete(ApplicationUser).where(
                    ApplicationUser.firebase_uid == user.firebase_uid
                )
            )
        await asyncio.to_thread(self._delete_firebase_user, user.firebase_uid)
