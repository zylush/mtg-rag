from __future__ import annotations

import uuid
from datetime import datetime, date, timedelta

from sqlalchemy import delete, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql.dml import Insert

from app.db.models import AskAttempt, DailyUsage


def build_consume_success_statement(
    *, user_id: str | uuid.UUID, usage_date: date, daily_limit: int
) -> Insert:
    """Build one atomic quota increment; no returned row means quota exhausted."""
    if daily_limit < 1:
        raise ValueError("daily_limit must be positive")
    statement = insert(DailyUsage).values(
        id=uuid.uuid4(),
        user_id=user_id,
        usage_date=usage_date,
        successful_answers=1,
    )
    return statement.on_conflict_do_update(
        index_elements=[DailyUsage.user_id, DailyUsage.usage_date],
        set_={
            "successful_answers": DailyUsage.successful_answers + 1,
            "updated_at": func.now(),
        },
        where=DailyUsage.successful_answers < daily_limit,
    ).returning(DailyUsage.successful_answers)


class PostgresUsageRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def consume_success(
        self, user_id: uuid.UUID, usage_date: date, *, limit: int
    ) -> int | None:
        async with self._session_factory.begin() as session:
            result = await session.execute(
                build_consume_success_statement(
                    user_id=user_id,
                    usage_date=usage_date,
                    daily_limit=limit,
                )
            )
            return result.scalar_one_or_none()

    async def register_ask_attempt(
        self, user_id: uuid.UUID, *, now: datetime, limit: int
    ) -> bool:
        if limit < 1:
            raise ValueError("limit must be positive")
        cutoff = now - timedelta(minutes=1)
        async with self._session_factory.begin() as session:
            await session.execute(
                text(
                    "SELECT pg_advisory_xact_lock("
                    "hashtextextended(CAST(:user_id AS text), 0))"
                ),
                {"user_id": str(user_id)},
            )
            await session.execute(
                delete(AskAttempt).where(
                    AskAttempt.user_id == user_id,
                    AskAttempt.created_at < cutoff,
                )
            )
            count = await session.scalar(
                select(func.count(AskAttempt.id)).where(
                    AskAttempt.user_id == user_id,
                    AskAttempt.created_at >= cutoff,
                    AskAttempt.created_at <= now,
                )
            )
            if int(count or 0) >= limit:
                return False
            session.add(AskAttempt(user_id=user_id, created_at=now))
            return True

