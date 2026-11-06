"""Auth: server-side sessions and pending OIDC login state.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

from alembic_helpers import SCHEMA, apply_grants, audit_columns, uuid_pk

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Only SHA-256 hashes of the cookie/CSRF values are stored: a DB read
    # does not yield usable session tokens.
    op.create_table(
        "user_session",
        uuid_pk(),
        sa.Column("token_hash", sa.LargeBinary(32), nullable=False),
        sa.Column("csrf_hash", sa.LargeBinary(32), nullable=False),
        sa.Column(
            "user_id",
            sa.Uuid,
            sa.ForeignKey(f"{SCHEMA}.app_user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ip", pg.INET, nullable=True),
        sa.Column("user_agent", sa.String(400), nullable=True),
        *audit_columns(),
        sa.UniqueConstraint("token_hash", name="uq_user_session_token_hash"),
        schema=SCHEMA,
    )
    op.create_index("ix_user_session_user_id", "user_session", ["user_id"], schema=SCHEMA)
    op.create_index("ix_user_session_expires_at", "user_session", ["expires_at"], schema=SCHEMA)

    # One row per login attempt in flight; consumed (deleted) by the callback.
    op.create_table(
        "oauth_login_state",
        uuid_pk(),
        sa.Column("state_hash", sa.LargeBinary(32), nullable=False),
        sa.Column("browser_hash", sa.LargeBinary(32), nullable=False),
        sa.Column("nonce", sa.String(128), nullable=False),
        sa.Column("code_verifier", sa.String(128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        *audit_columns(),
        sa.UniqueConstraint("state_hash", name="uq_oauth_login_state_state_hash"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_oauth_login_state_expires_at", "oauth_login_state", ["expires_at"], schema=SCHEMA
    )

    apply_grants()


def downgrade() -> None:
    op.drop_table("oauth_login_state", schema=SCHEMA)
    op.drop_table("user_session", schema=SCHEMA)
