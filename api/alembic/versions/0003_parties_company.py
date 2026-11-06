"""Parties (shared by company/customer/vendor), company, addresses, contacts.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

from alembic_helpers import SCHEMA, apply_grants, audit_columns, uuid_pk

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PARTY_TYPES = ("company", "customer", "vendor")
ADDRESS_TYPES = ("registered", "billing", "warehouse", "shipping")


def upgrade() -> None:
    # --- party: identity shared by every kind of business partner -------------
    op.create_table(
        "party",
        uuid_pk(),
        sa.Column("party_type", sa.String(20), nullable=False),
        sa.Column("code", sa.String(20), nullable=False),
        sa.Column("legal_name", sa.String(200), nullable=False),
        sa.Column("trade_name", sa.String(200), nullable=True),
        sa.Column("tax_id", sa.String(30), nullable=True),
        # Normalised for duplicate detection: "ES-B12.345.678" == "esb12345678".
        sa.Column(
            "tax_id_norm",
            sa.String(30),
            sa.Computed(
                "NULLIF(upper(regexp_replace(tax_id, '[^A-Za-z0-9]', '', 'g')), '')", persisted=True
            ),
        ),
        sa.Column("eori", sa.String(17), nullable=True),
        sa.Column(
            "country_code", sa.CHAR(2), sa.ForeignKey(f"{SCHEMA}.country.code"), nullable=False
        ),
        sa.Column(
            "default_currency", sa.CHAR(3), sa.ForeignKey(f"{SCHEMA}.currency.code"), nullable=False
        ),
        *audit_columns(),
        sa.CheckConstraint(f"party_type IN {PARTY_TYPES!r}", name="ck_party_type"),
        sa.CheckConstraint("code ~ '^[A-Z0-9][A-Z0-9_-]{1,19}$'", name="ck_party_code"),
        sa.CheckConstraint(
            "eori IS NULL OR eori ~ '^[A-Z]{2}[A-Z0-9]{1,15}$'", name="ck_party_eori"
        ),
        sa.CheckConstraint("btrim(legal_name) <> ''", name="ck_party_legal_name"),
        sa.UniqueConstraint("code", name="uq_party_code"),
        # Target for composite FKs that pin a child to one party type.
        sa.UniqueConstraint("id", "party_type", name="uq_party_id_type"),
        schema=SCHEMA,
    )
    # One Tax ID per party type, inactive rows included (reactivate instead of re-creating).
    op.create_index(
        "uq_party_type_tax_id",
        "party",
        ["party_type", "tax_id_norm"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("tax_id_norm IS NOT NULL"),
    )
    op.create_index("ix_party_legal_name", "party", ["party_type", "legal_name"], schema=SCHEMA)

    # --- company: BVT's own legal entities -------------------------------------
    op.create_table(
        "company",
        sa.Column("party_id", sa.Uuid, primary_key=True),
        sa.Column("party_type", sa.String(20), nullable=False, server_default="company"),
        sa.Column("is_default", sa.Boolean, nullable=False, server_default=sa.false()),
        *audit_columns(),
        sa.CheckConstraint("party_type = 'company'", name="ck_company_party_type"),
        sa.ForeignKeyConstraint(
            ["party_id", "party_type"],
            [f"{SCHEMA}.party.id", f"{SCHEMA}.party.party_type"],
            name="fk_company_party",
            ondelete="CASCADE",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "uq_company_single_default",
        "company",
        ["is_default"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("is_default"),
    )

    # --- address --------------------------------------------------------------
    op.create_table(
        "address",
        uuid_pk(),
        sa.Column(
            "party_id",
            sa.Uuid,
            sa.ForeignKey(f"{SCHEMA}.party.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("address_type", sa.String(20), nullable=False),
        sa.Column("line1", sa.String(200), nullable=False),
        sa.Column("line2", sa.String(200), nullable=True),
        sa.Column("postal_code", sa.String(20), nullable=True),
        sa.Column("city", sa.String(100), nullable=False),
        sa.Column("region", sa.String(100), nullable=True),
        sa.Column(
            "country_code", sa.CHAR(2), sa.ForeignKey(f"{SCHEMA}.country.code"), nullable=False
        ),
        *audit_columns(),
        sa.CheckConstraint(f"address_type IN {ADDRESS_TYPES!r}", name="ck_address_type"),
        sa.CheckConstraint("btrim(line1) <> '' AND btrim(city) <> ''", name="ck_address_required"),
        schema=SCHEMA,
    )
    op.create_index("ix_address_party_id", "address", ["party_id"], schema=SCHEMA)

    # --- contact --------------------------------------------------------------
    op.create_table(
        "contact",
        uuid_pk(),
        sa.Column(
            "party_id",
            sa.Uuid,
            sa.ForeignKey(f"{SCHEMA}.party.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("role_title", sa.String(100), nullable=True),
        sa.Column("email", pg.CITEXT, nullable=True),
        sa.Column("phone", sa.String(40), nullable=True),
        sa.Column("is_primary", sa.Boolean, nullable=False, server_default=sa.false()),
        *audit_columns(),
        sa.CheckConstraint("btrim(name) <> ''", name="ck_contact_name"),
        sa.CheckConstraint(
            "email IS NULL OR (length(email) <= 254 AND email LIKE '%_@_%._%')",
            name="ck_contact_email",
        ),
        sa.CheckConstraint(
            "phone IS NULL OR phone ~ '^[0-9+() ./x-]{3,40}$'", name="ck_contact_phone"
        ),
        schema=SCHEMA,
    )
    op.create_index("ix_contact_party_id", "contact", ["party_id"], schema=SCHEMA)
    op.create_index(
        "uq_contact_one_primary",
        "contact",
        ["party_id"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("is_primary AND is_active"),
    )

    apply_grants()


def downgrade() -> None:
    for table in ("contact", "address", "company", "party"):
        op.drop_table(table, schema=SCHEMA)
