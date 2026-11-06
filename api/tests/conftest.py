"""Test setup: a fresh `mdm` schema in the mdm_test database, migrated from scratch.

URLs are derived from .env (or the environment) by swapping the database name,
so tests can never touch the real `mdm` database. Google is replaced by
tests/fake_idp.py, wired into the real OIDC client.
"""

import os
import tempfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from dotenv import dotenv_values
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, make_url, text

from app.config import REPO_ROOT
from tests import fake_idp
from tests.safety import require_throwaway_database

API_ROOT = REPO_ROOT / "api"
_DOTENV = dotenv_values(REPO_ROOT / ".env")

WEB_ORIGIN = "http://localhost:8080"
BOOTSTRAP_ADMIN = "boot-admin@buenavidatrading.com"


def _env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name) or _DOTENV.get(name) or default
    if not value:
        raise RuntimeError(f"{name} must be set (see .env.example)")
    return value


# Refuse before anything connects: only *_test / *_e2e databases (tests/safety.py).
TEST_DB = require_throwaway_database(_env("TEST_DATABASE_NAME", "mdm_test"))

APP_URL = make_url(_env("DATABASE_URL")).set(database=TEST_DB)
MIGRATOR_URL = make_url(_env("MIGRATION_DATABASE_URL")).set(database=TEST_DB)
READONLY_URL = APP_URL.set(username="mdm_readonly", password=_env("MDM_READONLY_PASSWORD"))

# The app under test reads its settings from the environment (before first import).
os.environ.update(
    {
        "DATABASE_URL": APP_URL.render_as_string(hide_password=False),
        "APP_ENV": "e2e",  # pytest also uses a fake IdP (tests/fake_idp.py)
        "WEB_ORIGIN": WEB_ORIGIN,
        "GOOGLE_CLIENT_ID": fake_idp.CLIENT_ID,
        "GOOGLE_CLIENT_SECRET": fake_idp.CLIENT_SECRET,
        "OIDC_REDIRECT_URI": fake_idp.REDIRECT_URI,
        "OIDC_ISSUER": fake_idp.ISSUER,
        "OIDC_AUTHORIZATION_ENDPOINT": fake_idp.ISSUER + "/authorize",
        "OIDC_TOKEN_ENDPOINT": fake_idp.ISSUER + "/token",
        "OIDC_JWKS_URI": fake_idp.ISSUER + "/jwks",
        "ALLOWED_HOSTED_DOMAIN": "buenavidatrading.com",
        "BOOTSTRAP_ADMIN_EMAIL": BOOTSTRAP_ADMIN,
        "AUTH_RATE_LIMIT": "1000/minute",
        "IMPORT_RATE_LIMIT": "1000/minute",
        # Uploads go to a throwaway folder, never the real one.
        "UPLOAD_DIR": tempfile.mkdtemp(prefix="mdm-test-uploads-"),
    }
)


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
def admin_engine() -> Iterator[Engine]:
    """Schema owner: used by tests to arrange/inspect state the app role can't touch."""
    engine = create_engine(MIGRATOR_URL)
    yield engine
    engine.dispose()


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


@pytest.fixture
def clean_db(admin_engine: Engine) -> None:
    with admin_engine.begin() as conn:
        conn.execute(text("DELETE FROM mdm.user_session"))
        conn.execute(text("DELETE FROM mdm.oauth_login_state"))
        conn.execute(text("TRUNCATE mdm.audit_log"))
        conn.execute(text("DELETE FROM mdm.import_job"))  # cascades to import_issue
        conn.execute(text("DELETE FROM mdm.import_template"))
        conn.execute(text("DELETE FROM mdm.price_list"))  # cascades to lines and prices
        conn.execute(text("DELETE FROM mdm.party"))  # cascades to company/address/contact
        conn.execute(text("DELETE FROM mdm.app_user"))


@pytest.fixture
def idp() -> fake_idp.FakeIdP:
    return fake_idp.FakeIdP()


@pytest.fixture
def client(clean_db: None, idp: fake_idp.FakeIdP) -> Iterator[TestClient]:
    from app.auth.deps import get_oidc_client
    from app.auth.oidc import OIDCClient
    from app.config import get_settings
    from app.main import create_app
    from app.security.ratelimit import limiter

    limiter.reset()
    app = create_app()
    app.dependency_overrides[get_oidc_client] = lambda: OIDCClient(
        get_settings(), transport=idp.transport()
    )
    # https base URL so the client stores and returns Secure cookies, like a browser on localhost.
    with TestClient(app, base_url="https://localhost", headers={"Origin": WEB_ORIGIN}) as c:
        yield c


@dataclass
class LoggedIn:
    email: str
    csrf: str


def add_user(engine: Engine, email: str, role: str, *, active: bool = True) -> str:
    with engine.begin() as conn:
        return str(
            conn.execute(
                text(
                    "INSERT INTO mdm.app_user (email, role, is_active) "
                    "VALUES (:e, :r, :a) RETURNING id"
                ),
                {"e": email, "r": role, "a": active},
            ).scalar_one()
        )


@pytest.fixture
def login(
    client: TestClient, idp: fake_idp.FakeIdP, admin_engine: Engine
) -> Callable[..., LoggedIn]:
    """Full browser-style login. Creates the user first unless role=None."""

    def _login(email: str, role: str | None = "viewer", **claims: Any) -> LoggedIn:
        if role is not None:
            add_user(admin_engine, email, role)
        start = client.get("/auth/login", follow_redirects=False)
        assert start.status_code == 303, start.text
        code, state = idp.approve(start.headers["location"], email=email, **claims)
        cb = client.get(
            "/auth/callback", params={"code": code, "state": state}, follow_redirects=False
        )
        assert cb.status_code == 303
        return LoggedIn(email=email, csrf=client.cookies.get("__Host-mdm_csrf") or "")

    return _login
