"""Alembic environment. Always runs as mdm_migrator (MIGRATION_DATABASE_URL).

`alembic -x db_url=...` overrides the URL (used by the test suite).
"""

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parent))  # alembic_helpers

from app.config import REPO_ROOT, require_ssl_unless_local

SCHEMA = "mdm"

config = context.config
if config.config_file_name and not config.attributes.get("skip_logging"):
    fileConfig(config.config_file_name, disable_existing_loggers=False)


def _url() -> str:
    url = (
        config.attributes.get("db_url")  # set programmatically by the test suite
        or context.get_x_argument(as_dictionary=True).get("db_url")
        or os.environ.get("MIGRATION_DATABASE_URL")
    )
    if not url:
        from dotenv import dotenv_values  # pydantic-settings dependency

        url = dotenv_values(REPO_ROOT / ".env").get("MIGRATION_DATABASE_URL")
    if not url:
        raise SystemExit("MIGRATION_DATABASE_URL is not set")
    return require_ssl_unless_local(url)


def run_migrations_online() -> None:
    engine = create_engine(_url())
    with engine.connect() as conn:
        # The version table lives in mdm, so the schema must exist first.
        conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}"))
        # Extensions (citext, btree_gist) are installed into mdm, so resolve types there.
        conn.execute(text(f"SET search_path TO {SCHEMA}"))
        conn.commit()
        context.configure(
            connection=conn,
            version_table_schema=SCHEMA,
            transaction_per_migration=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    raise SystemExit("offline mode is not supported")
run_migrations_online()
