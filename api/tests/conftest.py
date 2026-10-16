"""Test setup: a fresh `mdm` schema in the mdm_test database, migrated from scratch.

URLs are derived from .env (or the environment) by swapping the database name,
so tests can never touch the real `mdm` database.
"""

import os
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from dotenv import dotenv_values
from sqlalchemy import Engine, create_engine, make_url, text

from app.config import REPO_ROOT

API_ROOT = REPO_ROOT / "api"
_DOTENV = dotenv_values(REPO_ROOT / ".env")


def _env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name) or _DOTENV.get(name) or default
    if not value:
        raise RuntimeError(f"{name} must be set (see .env.example)")
    return value


TEST_DB = _env("TEST_DATABASE_NAME", "mdm_test")
if TEST_DB == "mdm":
    raise RuntimeError("tests must not run against the main database")

APP_URL = make_url(_env("DATABASE_URL")).set(database=TEST_DB)
MIGRATOR_URL = make_url(_env("MIGRATION_DATABASE_URL")).set(database=TEST_DB)
READONLY_URL = APP_URL.set(username="mdm_readonly", password=_env("MDM_READONLY_PASSWORD"))

# The app under test reads its settings from the environment.
os.environ["DATABASE_URL"] = APP_URL.render_as_string(hide_password=False)
os.environ["APP_ENV"] = "test"


@pytest.fixture(scope="session", autouse=True)
def migrated_db() -> None:
    engine = create_engine(MIGRATOR_URL)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS mdm CASCADE"))
    engine.dispose()

    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    cfg.attributes["skip_logging"] = True
    cfg.attributes["db_url"] = MIGRATOR_URL.render_as_string(hide_password=False)
    command.upgrade(cfg, "head")


@pytest.fixture(scope="session")
def app_engine() -> Iterator[Engine]:
    engine = create_engine(APP_URL)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def readonly_engine() -> Iterator[Engine]:
    engine = create_engine(READONLY_URL)
    yield engine
    engine.dispose()
