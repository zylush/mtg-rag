from datetime import date

from sqlalchemy.dialects import postgresql

from app.usage.repository import build_consume_success_statement


def test_successful_answer_quota_increment_is_one_atomic_postgres_statement() -> None:
    statement = build_consume_success_statement(
        user_id="00000000-0000-0000-0000-000000000001",
        usage_date=date(2026, 8, 12),
        daily_limit=20,
    )
    compiled = str(statement.compile(dialect=postgresql.dialect())).lower()

    assert "insert into daily_usage" in compiled
    assert "on conflict" in compiled
    assert "successful_answers <" in compiled
    assert "returning daily_usage.successful_answers" in compiled

