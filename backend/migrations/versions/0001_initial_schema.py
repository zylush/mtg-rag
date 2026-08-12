"""Create the initial MTG RAG schema.

Revision ID: 0001
Revises: None
Create Date: 2026-08-12
"""
from collections.abc import Sequence

from alembic import op

from app.db import models  # noqa: F401
from app.db.base import Base

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "vector"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pg_trgm"')
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())

