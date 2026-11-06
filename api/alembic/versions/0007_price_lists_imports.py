"""Price lists (inside customers/vendors), lines, multi-currency prices, the import
pipeline (jobs, issues, mapping templates) and an empty exchange_rate table.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

from alembic_helpers import SCHEMA, apply_grants, audit_columns, uuid_pk

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FK = f"{SCHEMA}."


def upgrade() -> None:
    # --- price_list (header; one row per imported version) -----------------------
    op.create_table(
        "price_list",
        uuid_pk(),
        sa.Column("party_id", sa.Uuid, nullable=False),
        sa.Column("party_type", sa.String(20), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("currency", sa.CHAR(3), sa.ForeignKey(FK + "currency.code"), nullable=False),
        sa.Column("valid_from", sa.Date, nullable=False),
        sa.Column("valid_to", sa.Date, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("supersedes_id", sa.Uuid, sa.ForeignKey(FK + "price_list.id"), nullable=True),
        sa.Column("source_file_name", sa.String(255), nullable=False),
        sa.Column("source_file_sha256", sa.CHAR(64), nullable=False),
        sa.Column("source_sheet", sa.String(100), nullable=True),
        sa.Column("source_metadata", pg.JSONB, nullable=True),
        sa.Column(
            "imported_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("imported_by", sa.Uuid, sa.ForeignKey(FK + "app_user.id"), nullable=True),
        sa.Column("notes", sa.String(1000), nullable=True),
        sa.Column("line_count", sa.Integer, nullable=False, server_default="0"),
        *audit_columns(),
        sa.CheckConstraint("party_type IN ('customer', 'vendor')", name="ck_price_list_party_type"),
        sa.CheckConstraint("status IN ('draft', 'active', 'expired')", name="ck_price_list_status"),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from", name="ck_price_list_dates"
        ),
        sa.CheckConstraint("source_file_sha256 ~ '^[0-9a-f]{64}$'", name="ck_price_list_sha256"),
        # Only customers and vendors own price lists; history can't be deleted with the party.
        sa.ForeignKeyConstraint(
            ["party_id", "party_type"],
            [FK + "party.id", FK + "party.party_type"],
            name="fk_price_list_party",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("party_id", "revision", name="uq_price_list_revision"),
        schema=SCHEMA,
    )
    op.create_index("ix_price_list_party", "price_list", ["party_id", "status"], schema=SCHEMA)
    # One Active list per owner + currency + overlapping period.
    op.execute(
        f"""ALTER TABLE {SCHEMA}.price_list ADD CONSTRAINT ex_price_list_one_active
        EXCLUDE USING gist (
            party_id WITH =, currency WITH =, daterange(valid_from, valid_to, '[]') WITH &&
        ) WHERE (status = 'active')"""
    )

    # --- price_list_line ------------------------------------------------------------
    op.create_table(
        "price_list_line",
        uuid_pk(),
        sa.Column(
            "price_list_id",
            sa.Uuid,
            sa.ForeignKey(FK + "price_list.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_row", sa.Integer, nullable=False),
        sa.Column("ean", sa.String(20), nullable=True),
        sa.Column("upc", sa.String(20), nullable=True),
        sa.Column("asin", sa.String(20), nullable=True),
        sa.Column("vendor_sku", sa.String(100), nullable=True),
        sa.Column("description", sa.String(1000), nullable=True),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("brand", sa.String(100), nullable=True),
        sa.Column("case_pack_qty", sa.Integer, nullable=True),
        sa.Column("moq", sa.Integer, nullable=True),
        sa.Column("uom", sa.String(20), nullable=True),
        sa.Column(
            "country_of_origin", sa.CHAR(2), sa.ForeignKey(FK + "country.code"), nullable=True
        ),
        sa.Column("hs_code", sa.String(20), nullable=True),
        sa.Column("dimensions", pg.JSONB, nullable=True),
        sa.Column("dup_key", sa.CHAR(64), nullable=False),
        sa.Column("issues", pg.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("raw_row", pg.JSONB, nullable=False),
        *audit_columns(),
        sa.CheckConstraint(
            "ean IS NOT NULL OR upc IS NOT NULL OR asin IS NOT NULL", name="ck_line_product_key"
        ),
        sa.CheckConstraint("case_pack_qty IS NULL OR case_pack_qty >= 0", name="ck_line_case_pack"),
        sa.CheckConstraint("moq IS NULL OR moq >= 0", name="ck_line_moq"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_line_list_row", "price_list_line", ["price_list_id", "source_row"], schema=SCHEMA
    )
    op.create_index(
        "ix_line_list_brand", "price_list_line", ["price_list_id", "brand"], schema=SCHEMA
    )
    op.create_index(
        "ix_line_list_category", "price_list_line", ["price_list_id", "category"], schema=SCHEMA
    )
    op.create_index(
        "ix_line_list_dup", "price_list_line", ["price_list_id", "dup_key"], schema=SCHEMA
    )
    op.create_index("ix_line_ean", "price_list_line", ["ean"], schema=SCHEMA)
    op.create_index("ix_line_asin", "price_list_line", ["asin"], schema=SCHEMA)

    # --- price_list_line_price (several prices, each with its own currency) ----------
    op.create_table(
        "price_list_line_price",
        uuid_pk(),
        sa.Column(
            "line_id",
            sa.Uuid,
            sa.ForeignKey(FK + "price_list_line.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "price_type", sa.String(40), sa.ForeignKey(FK + "price_type.code"), nullable=False
        ),
        sa.Column("amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("currency", sa.CHAR(3), sa.ForeignKey(FK + "currency.code"), nullable=False),
        sa.Column("source_column", sa.String(10), nullable=True),
        *audit_columns(),
        sa.CheckConstraint("amount >= 0", name="ck_price_amount"),
        sa.UniqueConstraint("line_id", "price_type", "currency", name="uq_line_price"),
        schema=SCHEMA,
    )

    # --- import templates (saved column mappings per customer/vendor) -----------------
    op.create_table(
        "import_template",
        uuid_pk(),
        sa.Column(
            "party_id", sa.Uuid, sa.ForeignKey(FK + "party.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("file_type", sa.String(10), nullable=False),
        sa.Column("sheet_name", sa.String(100), nullable=True),
        sa.Column("header_row", sa.Integer, nullable=False),
        sa.Column("data_start_row", sa.Integer, nullable=False),
        sa.Column("mapping", pg.JSONB, nullable=False),
        sa.Column("header_fingerprint", sa.CHAR(64), nullable=False),
        *audit_columns(),
        sa.CheckConstraint("file_type IN ('xlsx', 'csv')", name="ck_import_template_file_type"),
        schema=SCHEMA,
    )
    op.create_index(
        "uq_import_template_name",
        "import_template",
        ["party_id", "name"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("is_active"),
    )

    # --- import jobs and their issues (temporary working data) ----------------------
    op.create_table(
        "import_job",
        uuid_pk(),
        sa.Column(
            "party_id", sa.Uuid, sa.ForeignKey(FK + "party.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="uploaded"),
        sa.Column("original_name", sa.String(255), nullable=False),
        sa.Column("stored_name", sa.String(64), nullable=True),
        sa.Column("file_type", sa.String(10), nullable=False),
        sa.Column("size_bytes", sa.Integer, nullable=False),
        sa.Column("sha256", sa.CHAR(64), nullable=False),
        sa.Column(
            "template_id",
            sa.Uuid,
            sa.ForeignKey(FK + "import_template.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("settings", pg.JSONB, nullable=True),
        sa.Column("summary", pg.JSONB, nullable=True),
        sa.Column(
            "price_list_id",
            sa.Uuid,
            sa.ForeignKey(FK + "price_list.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        *audit_columns(),
        sa.CheckConstraint(
            "status IN ('uploaded', 'validated', 'committed', 'cancelled', 'expired')",
            name="ck_import_job_status",
        ),
        schema=SCHEMA,
    )
    op.create_index("ix_import_job_party", "import_job", ["party_id"], schema=SCHEMA)
    op.create_table(
        "import_issue",
        uuid_pk(),
        sa.Column(
            "import_job_id",
            sa.Uuid,
            sa.ForeignKey(FK + "import_job.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_row", sa.Integer, nullable=True),
        sa.Column("severity", sa.String(10), nullable=False),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("column_ref", sa.String(10), nullable=True),
        sa.Column("message", sa.String(500), nullable=False),
        *audit_columns(),
        sa.CheckConstraint("severity IN ('warning', 'error')", name="ck_import_issue_severity"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_import_issue_job",
        "import_issue",
        ["import_job_id", "severity", "source_row"],
        schema=SCHEMA,
    )

    # --- exchange rates: created empty, for later margin/FX work (no rates imported) --
    op.create_table(
        "exchange_rate",
        uuid_pk(),
        sa.Column("rate_date", sa.Date, nullable=False),
        sa.Column("from_ccy", sa.CHAR(3), sa.ForeignKey(FK + "currency.code"), nullable=False),
        sa.Column("to_ccy", sa.CHAR(3), sa.ForeignKey(FK + "currency.code"), nullable=False),
        sa.Column("rate", sa.Numeric(20, 10), nullable=False),
        sa.Column("source", sa.String(100), nullable=False),
        *audit_columns(),
        sa.CheckConstraint("rate > 0", name="ck_exchange_rate_positive"),
        sa.UniqueConstraint("rate_date", "from_ccy", "to_ccy", "source", name="uq_exchange_rate"),
        schema=SCHEMA,
    )

    apply_grants()


def downgrade() -> None:
    for table in (
        "exchange_rate",
        "import_issue",
        "import_job",
        "import_template",
        "price_list_line_price",
        "price_list_line",
        "price_list",
    ):
        op.drop_table(table, schema=SCHEMA)
