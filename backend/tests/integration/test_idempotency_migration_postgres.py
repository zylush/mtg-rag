from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Connection, inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import Settings

ROOT = Path(__file__).resolve().parents[3]
MIGRATION = ROOT / "backend" / "migrations" / "versions" / "0002_ask_request_idempotency.py"


def _load_migration_module():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location(
        "ask_request_postgres_migration_0002", MIGRATION
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {MIGRATION}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _exercise_upgrade(connection: Connection) -> None:
    connection.execute(text("DROP TABLE ask_requests"))
    migration = _load_migration_module()
    migration.op = Operations(MigrationContext.configure(connection))

    migration.upgrade()

    inspector = inspect(connection)
    unique_constraints = {
        constraint["name"]: tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints("ask_requests")
    }
    check_constraints = {
        constraint["name"] for constraint in inspector.get_check_constraints("ask_requests")
    }
    indexes = {index["name"] for index in inspector.get_indexes("ask_requests")}
    assert unique_constraints["uq_ask_requests_user_id"] == (
        "user_id",
        "client_request_id",
    )
    assert check_constraints == {
        "ck_ask_requests_valid_response_state",
        "ck_ask_requests_valid_status",
    }
    assert "ix_ask_request_lease" in indexes


@pytest.mark.asyncio
@pytest.mark.integration
async def test_existing_0001_database_can_apply_idempotency_migration() -> None:
    engine = create_async_engine(Settings().database_url, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                await connection.run_sync(_exercise_upgrade)
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()
