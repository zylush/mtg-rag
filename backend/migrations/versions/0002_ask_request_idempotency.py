"""Add durable ask-request idempotency records.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-24
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Revision 0001 creates from live metadata, so a brand-new database may already
    # contain this table before Alembic reaches 0002. IF NOT EXISTS keeps both fresh
    # bootstrap and upgrades from an existing 0001 database safe.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ask_requests (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES application_users(id) ON DELETE CASCADE,
            client_request_id UUID NOT NULL,
            claim_token UUID NOT NULL,
            request_hash VARCHAR(64) NOT NULL,
            status VARCHAR(16) NOT NULL,
            response JSONB NULL,
            lease_expires_at TIMESTAMPTZ NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_ask_requests_user_id
                UNIQUE (user_id, client_request_id),
            CONSTRAINT ck_ask_requests_valid_status
                CHECK (status IN ('in_progress', 'completed')),
            CONSTRAINT ck_ask_requests_valid_response_state
                CHECK (
                    (status = 'in_progress' AND response IS NULL)
                    OR (status = 'completed' AND response IS NOT NULL)
                )
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_ask_request_lease
        ON ask_requests (status, lease_expires_at)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ask_requests")
