"""Optional observations on each price-list line.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from alembic_helpers import SCHEMA, apply_grants

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "price_list_line",
        sa.Column("observations", sa.String(2000), nullable=True),
        schema=SCHEMA,
    )
    apply_grants()


def downgrade() -> None:
    op.drop_column("price_list_line", "observations", schema=SCHEMA)
    apply_grants()
