from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from app.db import models  # noqa: F401
from app.db.base import Base

ROOT = Path(__file__).resolve().parents[3]
MIGRATION = ROOT / "backend" / "migrations" / "versions" / "0002_ask_request_idempotency.py"


def _load_migration_module():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("ask_request_migration_0002", MIGRATION)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {MIGRATION}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_upgrade_sql_matches_canonical_ask_request_metadata_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_migration_module()
    statements: list[str] = []
    monkeypatch.setattr(migration.op, "execute", statements.append)
    ask_requests = Base.metadata.tables["ask_requests"]
    unique_constraint = next(
        constraint
        for constraint in ask_requests.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    )

    migration.upgrade()

    normalized_statements = [" ".join(statement.split()) for statement in statements]
    assert migration.revision == "0002"
    assert migration.down_revision == "0001"
    assert unique_constraint.name == "uq_ask_requests_user_id"
    assert f"CONSTRAINT {unique_constraint.name}" in normalized_statements[0]
    assert "CREATE TABLE IF NOT EXISTS ask_requests" in normalized_statements[0]
    assert "CREATE INDEX IF NOT EXISTS ix_ask_request_lease" in normalized_statements[1]


def test_downgrade_is_scoped_to_the_idempotency_table(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_migration_module()
    statements: list[str] = []
    monkeypatch.setattr(migration.op, "execute", statements.append)

    migration.downgrade()

    assert statements == ["DROP TABLE IF EXISTS ask_requests"]
