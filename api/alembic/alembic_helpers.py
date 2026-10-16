"""Shared helpers for migrations: common columns and the DB privilege policy.

`apply_grants()` describes the *desired* privileges for the whole schema and is
called at the end of every migration, so grants never drift from this file.
"""

import sqlalchemy as sa
from alembic import op

SCHEMA = "mdm"
APP_ROLE = "mdm_app"
READONLY_ROLE = "mdm_readonly"

# Default for mdm_app on every table: SELECT, INSERT, UPDATE (no DELETE, no DDL).
# Tables listed here get exactly these privileges instead.
APP_PRIVILEGE_OVERRIDES: dict[str, str] = {
    "audit_log": "INSERT",  # append-only: no SELECT/UPDATE/DELETE for the app
    "alembic_version": "",  # the app has no business with migration state
}

# Tables where mdm_app may also DELETE (session cleanup, temp import data,
# Admin hard delete). Never audit_log or price list tables.
APP_DELETE_TABLES: frozenset[str] = frozenset()


def audit_columns() -> list[sa.Column[object]]:
    """created/updated metadata, soft-delete flag and optimistic-lock version."""
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("created_by", sa.Uuid, sa.ForeignKey(f"{SCHEMA}.app_user.id"), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("updated_by", sa.Uuid, sa.ForeignKey(f"{SCHEMA}.app_user.id"), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
    ]


def uuid_pk() -> sa.Column[object]:
    return sa.Column("id", sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()"))


def apply_grants() -> None:
    s, app, ro = SCHEMA, APP_ROLE, READONLY_ROLE
    op.execute(f"REVOKE ALL ON SCHEMA {s} FROM PUBLIC")
    op.execute(f"GRANT USAGE ON SCHEMA {s} TO {app}, {ro}")
    op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA {s} FROM {app}, {ro}")
    op.execute(f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA {s} FROM {app}, {ro}")
    op.execute(f"REVOKE ALL ON ALL FUNCTIONS IN SCHEMA {s} FROM PUBLIC")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA {s} TO {app}")
    op.execute(f"GRANT USAGE ON ALL SEQUENCES IN SCHEMA {s} TO {app}")
    op.execute(f"GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA {s} TO {app}, {ro}")
    for table, privs in APP_PRIVILEGE_OVERRIDES.items():
        _if_table_exists(table, f"REVOKE ALL ON {s}.{table} FROM {app}")
        if privs:
            _if_table_exists(table, f"GRANT {privs} ON {s}.{table} TO {app}")
    for table in sorted(APP_DELETE_TABLES):
        _if_table_exists(table, f"GRANT DELETE ON {s}.{table} TO {app}")
    op.execute(f"GRANT SELECT ON ALL TABLES IN SCHEMA {s} TO {ro}")
    _if_table_exists("alembic_version", f"REVOKE ALL ON {s}.alembic_version FROM {ro}")


def _if_table_exists(table: str, statement: str) -> None:
    op.execute(
        f"DO $$ BEGIN IF to_regclass('{SCHEMA}.{table}') IS NOT NULL THEN "
        f"EXECUTE '{statement}'; END IF; END $$"
    )
