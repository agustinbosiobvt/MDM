"""Tests and scripts can never write to the real `mdm` database.

- pytest refuses to start unless TEST_DATABASE_NAME ends in _test or _e2e (tests/safety.py,
  checked in conftest before anything connects);
- scripts/reset_schema.py refuses any other database;
- the API refuses to start in e2e mode (mock Google) on a non-throwaway database.
"""

import os
import subprocess
import sys

import pytest
from pydantic import ValidationError

from app.config import REPO_ROOT, Settings
from tests.safety import UnsafeDatabaseError, require_throwaway_database

API_ROOT = REPO_ROOT / "api"
# Port 1 on loopback: nothing listens there, so any attempt to connect would fail with a
# connection error, not with the refusal message these tests expect.
UNREACHABLE = "postgresql+psycopg://u:p@127.0.0.1:1/{db}?connect_timeout=2"


@pytest.mark.parametrize(
    "name", ["mdm", "mdm_prod", "test_mdm", "mdm_testing", "mdm_e2e_x", "", None]
)
def test_guard_refuses_real_or_ambiguous_databases(name: str | None) -> None:
    with pytest.raises(UnsafeDatabaseError, match="refusing to run"):
        require_throwaway_database(name)


@pytest.mark.parametrize("name", ["mdm_test", "mdm_e2e", "other_test"])
def test_guard_accepts_throwaway_databases(name: str) -> None:
    assert require_throwaway_database(name) == name


def _run(args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 (fixed argv, test only)
        [sys.executable, *args],
        cwd=API_ROOT,
        env={**os.environ, **env},
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def test_pytest_refuses_to_start_on_the_real_database() -> None:
    result = _run(
        ["-m", "pytest", "tests/test_config.py", "-q", "-p", "no:cacheprovider"],
        {"TEST_DATABASE_NAME": "mdm"},
    )
    assert result.returncode != 0
    assert "refusing to run against database 'mdm'" in result.stdout + result.stderr
    assert "passed" not in result.stdout


def test_reset_script_refuses_the_real_database() -> None:
    result = _run(
        ["scripts/reset_schema.py"],
        {"MIGRATION_DATABASE_URL": UNREACHABLE.format(db="mdm")},
    )
    assert result.returncode == 1
    assert "refusing to reset database 'mdm'" in result.stderr


@pytest.mark.parametrize("db", ["mdm", "mdm_prod"])
def test_api_refuses_e2e_mode_on_a_real_database(db: str) -> None:
    with pytest.raises(
        ValidationError, match="APP_ENV=e2e needs a database ending in _e2e or _test"
    ):
        Settings(_env_file=None, app_env="e2e", database_url=UNREACHABLE.format(db=db))
    result = _run(
        ["-c", "import app.main"],
        {"APP_ENV": "e2e", "DATABASE_URL": UNREACHABLE.format(db=db)},
    )
    assert result.returncode != 0
    assert "APP_ENV=e2e needs a database ending in _e2e or _test" in result.stderr


def test_e2e_mode_accepts_throwaway_databases() -> None:
    for db in ("mdm_e2e", "mdm_test"):
        s = Settings(_env_file=None, app_env="e2e", database_url=UNREACHABLE.format(db=db))
        assert s.app_env == "e2e"
