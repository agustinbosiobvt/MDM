"""Foundation: extensions, lookups (seeded), app_user, audit_log.

Revision ID: 0001
Revises:
Create Date: 2026-10-16
"""

import csv
from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

from alembic_helpers import SCHEMA, apply_grants, audit_columns, uuid_pk

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SEED_DIR = Path(__file__).resolve().parents[1] / "seed"

ROLES = ("admin", "editor", "viewer")
PRICE_TYPES = [
    ("purchase", "Purchase price", "Price BVT pays the vendor", 10),
    ("domestic_cost", "Domestic cost", "Customer cost, domestic fulfilment (Amazon)", 20),
    ("import_cost", "Import cost", "Customer cost, direct import (Amazon)", 30),
    ("retailer_cost", "Retailer cost", "Price the retailer pays", 40),
    ("rrp", "RRP", "Recommended retail price, incl. VAT", 50),
    ("rrp_ex_vat", "RRP ex VAT", "Recommended retail price, excl. VAT", 60),
]
INCOTERMS_2020 = [
    ("EXW", "Ex Works"),
    ("FCA", "Free Carrier"),
    ("CPT", "Carriage Paid To"),
    ("CIP", "Carriage and Insurance Paid To"),
    ("DAP", "Delivered at Place"),
    ("DPU", "Delivered at Place Unloaded"),
    ("DDP", "Delivered Duty Paid"),
    ("FAS", "Free Alongside Ship"),
    ("FOB", "Free on Board"),
    ("CFR", "Cost and Freight"),
    ("CIF", "Cost, Insurance and Freight"),
]
PAYMENT_TERMS = [
    ("PREPAY", "Prepayment", 0),
    ("NET15", "Net 15 days", 15),
    ("NET30", "Net 30 days", 30),
    ("NET45", "Net 45 days", 45),
    ("NET60", "Net 60 days", 60),
    ("NET90", "Net 90 days", 90),
]


def _csv(name: str) -> list[dict[str, str]]:
    with (SEED_DIR / name).open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def upgrade() -> None:
    op.execute(f"CREATE EXTENSION IF NOT EXISTS citext WITH SCHEMA {SCHEMA}")
    op.execute(f"CREATE EXTENSION IF NOT EXISTS btree_gist WITH SCHEMA {SCHEMA}")

    # --- Users (needed first: every audited table references it) ------------
    op.create_table(
        "app_user",
        uuid_pk(),
        sa.Column("email", pg.CITEXT, nullable=False),
        sa.Column("display_name", sa.String(200), nullable=True),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        *audit_columns(),
        sa.UniqueConstraint("email", name="uq_app_user_email"),
        sa.CheckConstraint(f"role IN {ROLES!r}", name="ck_app_user_role"),
        sa.CheckConstraint("length(email) <= 254 AND email LIKE '%_@_%'", name="ck_app_user_email"),
        schema=SCHEMA,
    )

    # --- Lookups (natural code PKs) -------------------------------------------
    op.create_table(
        "country",
        sa.Column("code", sa.CHAR(2), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        *audit_columns(),
        sa.CheckConstraint("code ~ '^[A-Z]{2}$'", name="ck_country_code"),
        schema=SCHEMA,
    )
    op.create_table(
        "currency",
        sa.Column("code", sa.CHAR(3), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("minor_units", sa.SmallInteger, nullable=False),
        *audit_columns(),
        sa.CheckConstraint("code ~ '^[A-Z]{3}$'", name="ck_currency_code"),
        sa.CheckConstraint("minor_units BETWEEN 0 AND 4", name="ck_currency_minor_units"),
        schema=SCHEMA,
    )
    op.create_table(
        "price_type",
        sa.Column("code", sa.String(40), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("sort_order", sa.SmallInteger, nullable=False, server_default="100"),
        *audit_columns(),
        sa.CheckConstraint("code ~ '^[a-z][a-z0-9_]{1,39}$'", name="ck_price_type_code"),
        schema=SCHEMA,
    )
    op.create_table(
        "incoterm",
        sa.Column("code", sa.CHAR(3), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        *audit_columns(),
        sa.CheckConstraint("code ~ '^[A-Z]{3}$'", name="ck_incoterm_code"),
        schema=SCHEMA,
    )
    op.create_table(
        "payment_term",
        sa.Column("code", sa.String(20), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("days", sa.SmallInteger, nullable=True),
        *audit_columns(),
        sa.CheckConstraint("code ~ '^[A-Z0-9_]{2,20}$'", name="ck_payment_term_code"),
        sa.CheckConstraint("days IS NULL OR days BETWEEN 0 AND 365", name="ck_payment_term_days"),
        schema=SCHEMA,
    )

    # --- Audit log (append-only; no FK so it outlives anything it describes) --
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column(
            "occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("user_id", sa.Uuid, nullable=True),
        sa.Column("user_email", pg.CITEXT, nullable=True),
        sa.Column("entity", sa.String(60), nullable=False),
        sa.Column("entity_id", sa.String(64), nullable=True),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("old_values", pg.JSONB, nullable=True),
        sa.Column("new_values", pg.JSONB, nullable=True),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column("ip", pg.INET, nullable=True),
        schema=SCHEMA,
    )
    op.create_index("ix_audit_log_entity", "audit_log", ["entity", "entity_id"], schema=SCHEMA)
    op.create_index("ix_audit_log_occurred_at", "audit_log", ["occurred_at"], schema=SCHEMA)

    # --- Seeds ----------------------------------------------------------------
    meta = sa.MetaData(schema=SCHEMA)
    meta.reflect(
        op.get_bind(), only=["country", "currency", "price_type", "incoterm", "payment_term"]
    )
    t = meta.tables
    op.bulk_insert(t[f"{SCHEMA}.country"], _csv("countries.csv"))
    op.bulk_insert(
        t[f"{SCHEMA}.currency"],
        [{**r, "minor_units": int(r["minor_units"])} for r in _csv("currencies.csv")],
    )
    op.bulk_insert(
        t[f"{SCHEMA}.price_type"],
        [{"code": c, "name": n, "description": d, "sort_order": o} for c, n, d, o in PRICE_TYPES],
    )
    op.bulk_insert(t[f"{SCHEMA}.incoterm"], [{"code": c, "name": n} for c, n in INCOTERMS_2020])
    op.bulk_insert(
        t[f"{SCHEMA}.payment_term"],
        [{"code": c, "name": n, "days": d} for c, n, d in PAYMENT_TERMS],
    )

    apply_grants()


def downgrade() -> None:
    for table in (
        "audit_log",
        "payment_term",
        "incoterm",
        "price_type",
        "currency",
        "country",
        "app_user",
    ):
        op.drop_table(table, schema=SCHEMA)
    op.execute("DROP EXTENSION IF EXISTS btree_gist")
    op.execute("DROP EXTENSION IF EXISTS citext")
