"""Company tax registration number; drop the description of Amazon vendor codes.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from alembic_helpers import SCHEMA, apply_grants

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Free text, optional; printed on BVT's commercial invoices. Company only.
    op.add_column(
        "company", sa.Column("tax_registration_number", sa.String(50), nullable=True), schema=SCHEMA
    )
    op.drop_column("customer_vendor_code", "description", schema=SCHEMA)
    apply_grants()


def downgrade() -> None:
    op.add_column(
        "customer_vendor_code",
        sa.Column("description", sa.String(100), nullable=True),
        schema=SCHEMA,
    )
    op.drop_column("company", "tax_registration_number", schema=SCHEMA)
    apply_grants()
