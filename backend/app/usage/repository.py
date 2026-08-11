from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.sql.dml import Insert

from app.db.models import DailyUsage


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

