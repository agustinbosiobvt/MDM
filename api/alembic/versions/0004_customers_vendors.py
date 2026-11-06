"""Customers, vendors, Amazon vendor codes; international Tax ID normalisation.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from alembic_helpers import SCHEMA, apply_grants, audit_columns, uuid_pk

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STATUSES = ("active", "on_hold", "blocked")
ADDRESS_TYPES = ("registered", "billing", "warehouse", "shipping", "pickup", "factory")
CONTACT_ROLES = ("sales", "logistics", "quality", "other")

# Tax IDs are international (RFC, DE VAT, EIN...): for the duplicate check strip only
# spaces, dots and dashes, and compare case-insensitively. Nothing country-specific.
TAX_ID_NORM = r"NULLIF(upper(regexp_replace(tax_id, '[[:space:].-]', '', 'g')), '')"


def _partner_table(name: str, party_type: str, *extra: sa.Column[object]) -> None:
    op.create_table(
        name,
        sa.Column("party_id", sa.Uuid, primary_key=True),
        sa.Column("party_type", sa.String(20), nullable=False, server_default=party_type),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column(
            "payment_term_code",
            sa.String(20),
            sa.ForeignKey(f"{SCHEMA}.payment_term.code"),
            nullable=True,
        ),
        sa.Column(
            "incoterm_code", sa.CHAR(3), sa.ForeignKey(f"{SCHEMA}.incoterm.code"), nullable=True
        ),
        *extra,
        *audit_columns(),
        sa.CheckConstraint(f"party_type = '{party_type}'", name=f"ck_{name}_party_type"),
        sa.CheckConstraint(f"status IN {STATUSES!r}", name=f"ck_{name}_status"),
        sa.ForeignKeyConstraint(
            ["party_id", "party_type"],
            [f"{SCHEMA}.party.id", f"{SCHEMA}.party.party_type"],
            name=f"fk_{name}_party",
            ondelete="CASCADE",
        ),
        schema=SCHEMA,
    )
    op.create_index(f"ix_{name}_status", name, ["status"], schema=SCHEMA)


def upgrade() -> None:
    # --- Tax ID normalisation (recreate the generated column + its unique index) ---
    op.drop_index("uq_party_type_tax_id", table_name="party", schema=SCHEMA)
    op.drop_column("party", "tax_id_norm", schema=SCHEMA)
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

    # --- New address types (ship-to = shipping, pick-up, factory) ---------------
    op.drop_constraint("ck_address_type", "address", schema=SCHEMA, type_="check")
    op.create_check_constraint(
        "ck_address_type", "address", f"address_type IN {ADDRESS_TYPES!r}", schema=SCHEMA
    )

    # --- Contact role (used for vendor contacts) ----------------------------------
    op.add_column("contact", sa.Column("contact_role", sa.String(20), nullable=True), schema=SCHEMA)
    op.create_check_constraint(
        "ck_contact_role",
        "contact",
        f"contact_role IS NULL OR contact_role IN {CONTACT_ROLES!r}",
        schema=SCHEMA,
    )

    # --- Customers and vendors -------------------------------------------------------
    _partner_table("customer", "customer")
    _partner_table(
        "vendor",
        "vendor",
        sa.Column("lead_time_days", sa.Integer, nullable=True),
        sa.Column("moq", sa.Integer, nullable=True),
    )
    op.create_check_constraint(
        "ck_vendor_lead_time",
        "vendor",
        "lead_time_days IS NULL OR lead_time_days BETWEEN 0 AND 730",
        schema=SCHEMA,
    )
    op.create_check_constraint("ck_vendor_moq", "vendor", "moq IS NULL OR moq >= 1", schema=SCHEMA)

    # --- Amazon vendor codes (several parent/child pairs per customer) -------------
    op.create_table(
        "customer_vendor_code",
        uuid_pk(),
        sa.Column(
            "customer_id",
            sa.Uuid,
            sa.ForeignKey(f"{SCHEMA}.customer.party_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("parent_code", sa.String(20), nullable=False),
        sa.Column("child_code", sa.String(20), nullable=False),
        sa.Column(
            "destination_country",
            sa.CHAR(2),
            sa.ForeignKey(f"{SCHEMA}.country.code"),
            nullable=True,
        ),
        sa.Column("description", sa.String(100), nullable=True),
        *audit_columns(),
        sa.CheckConstraint("parent_code ~ '^[A-Z0-9_-]{2,20}$'", name="ck_vendor_code_parent"),
        sa.CheckConstraint("child_code ~ '^[A-Z0-9_-]{2,20}$'", name="ck_vendor_code_child"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_customer_vendor_code_customer", "customer_vendor_code", ["customer_id"], schema=SCHEMA
    )
    # A parent/child pair belongs to one customer (active rows only).
    op.create_index(
        "uq_vendor_code_pair",
        "customer_vendor_code",
        ["parent_code", "child_code"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("is_active"),
    )

    apply_grants()


def downgrade() -> None:
    op.drop_table("customer_vendor_code", schema=SCHEMA)
    op.drop_table("vendor", schema=SCHEMA)
    op.drop_table("customer", schema=SCHEMA)
    op.drop_constraint("ck_contact_role", "contact", schema=SCHEMA, type_="check")
    op.drop_column("contact", "contact_role", schema=SCHEMA)
    op.drop_constraint("ck_address_type", "address", schema=SCHEMA, type_="check")
    op.create_check_constraint(
        "ck_address_type",
        "address",
        "address_type IN ('registered', 'billing', 'warehouse', 'shipping')",
        schema=SCHEMA,
    )
    op.drop_index("uq_party_type_tax_id", table_name="party", schema=SCHEMA)
    op.drop_column("party", "tax_id_norm", schema=SCHEMA)
    op.add_column(
        "party",
        sa.Column(
            "tax_id_norm",
            sa.String(30),
            sa.Computed(
                "NULLIF(upper(regexp_replace(tax_id, '[^A-Za-z0-9]', '', 'g')), '')", persisted=True
            ),
        ),
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
