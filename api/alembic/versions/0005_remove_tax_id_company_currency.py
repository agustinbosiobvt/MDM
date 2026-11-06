"""Spec corrections: remove Tax ID everywhere; currency only on customers and vendors.

- party.tax_id / tax_id_norm and the Tax ID uniqueness index are dropped.
- default_currency moves from party to customer and vendor (copied first); Company
  therefore has no currency at all.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from alembic_helpers import SCHEMA, apply_grants

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TAX_ID_NORM = r"NULLIF(upper(regexp_replace(tax_id, '[[:space:].-]', '', 'g')), '')"


def _party() -> sa.TableClause:
    return sa.table("party", sa.column("id"), sa.column("default_currency"), schema=SCHEMA)


def _ext(name: str) -> sa.TableClause:
    return sa.table(name, sa.column("party_id"), sa.column("default_currency"), schema=SCHEMA)


def upgrade() -> None:
    # Currency: party -> customer / vendor.
    for table in ("customer", "vendor"):
        op.add_column(
            table,
            sa.Column(
                "default_currency",
                sa.CHAR(3),
                sa.ForeignKey(f"{SCHEMA}.currency.code"),
                nullable=True,
            ),
            schema=SCHEMA,
        )
        ext, party = _ext(table), _party()
        op.execute(
            sa.update(ext)
            .values(default_currency=party.c.default_currency)
            .where(party.c.id == ext.c.party_id)
        )
        op.alter_column(table, "default_currency", nullable=False, schema=SCHEMA)
    op.drop_column("party", "default_currency", schema=SCHEMA)

    # Tax ID: gone, with its duplicate check.
    op.drop_index("uq_party_type_tax_id", table_name="party", schema=SCHEMA)
    op.drop_column("party", "tax_id_norm", schema=SCHEMA)
    op.drop_column("party", "tax_id", schema=SCHEMA)

    apply_grants()


def downgrade() -> None:
    op.add_column("party", sa.Column("tax_id", sa.String(30), nullable=True), schema=SCHEMA)
    op.add_column(
        "party",
        sa.Column("tax_id_norm", sa.String(30), sa.Computed(TAX_ID_NORM, persisted=True)),
        schema=SCHEMA,
    )
    op.create_index(
        "uq_party_type_tax_id",
        "party",
        ["party_type", "tax_id_norm"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("tax_id_norm IS NOT NULL"),
    )
    op.add_column(
        "party",
        sa.Column(
            "default_currency", sa.CHAR(3), sa.ForeignKey(f"{SCHEMA}.currency.code"), nullable=True
        ),
        schema=SCHEMA,
    )
    for table in ("customer", "vendor"):
        ext, party = _ext(table), _party()
        op.execute(
            sa.update(party)
            .values(default_currency=ext.c.default_currency)
            .where(party.c.id == ext.c.party_id)
        )
        op.drop_column(table, "default_currency", schema=SCHEMA)
    party = _party()
    op.execute(
        sa.update(party).values(default_currency="EUR").where(party.c.default_currency.is_(None))
    )
    op.alter_column("party", "default_currency", nullable=False, schema=SCHEMA)
    apply_grants()
