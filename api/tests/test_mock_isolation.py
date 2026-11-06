"""The mock Google used by the e2e suite can never be active outside e2e.

1. The API refuses to start with a non-Google OIDC issuer/endpoint unless APP_ENV=e2e.
2. The mock and its configuration exist only in docker-compose.e2e.yml: not in the
   normal compose file, not in the API image's build inputs, not in the web image.
   (`make audit` additionally inspects the built images: scripts/check_images.sh.)
"""

import os
import re
import subprocess
import sys
from typing import Any

import pytest
from pydantic import ValidationError

from app.config import (
    GOOGLE_AUTHORIZATION_ENDPOINT,
    GOOGLE_ISSUER,
    GOOGLE_JWKS_URI,
    GOOGLE_TOKEN_ENDPOINT,
    REPO_ROOT,
    Settings,
)

API_ROOT = REPO_ROOT / "api"
DB_URL = "postgresql+psycopg://u:p@127.0.0.1:5432/mdm_e2e"  # e2e mode requires *_e2e/*_test
GOOGLE = {
    "oidc_issuer": GOOGLE_ISSUER,
    "oidc_authorization_endpoint": GOOGLE_AUTHORIZATION_ENDPOINT,
    "oidc_token_endpoint": GOOGLE_TOKEN_ENDPOINT,
    "oidc_jwks_uri": GOOGLE_JWKS_URI,
}
MOCK = {
    "oidc_issuer": "https://mock-oidc.e2e",
    "oidc_authorization_endpoint": "http://localhost:8090/authorize",
    "oidc_token_endpoint": "http://mock-oidc:8090/token",
    "oidc_jwks_uri": "http://mock-oidc:8090/jwks",
}


def _settings(**kwargs: Any) -> Settings:
    return Settings(_env_file=None, database_url=DB_URL, **kwargs)


# --- 1. Settings / start-up refusal ------------------------------------------------


@pytest.mark.parametrize("app_env", ["local", "production"])
@pytest.mark.parametrize("field", sorted(MOCK))
def test_any_non_google_oidc_setting_is_refused_outside_e2e(app_env: str, field: str) -> None:
    with pytest.raises(ValidationError, match="unless APP_ENV=e2e"):
        _settings(app_env=app_env, **{**GOOGLE, field: MOCK[field]})


@pytest.mark.parametrize("app_env", ["local", "production"])
def test_google_is_accepted_everywhere(app_env: str) -> None:
    assert _settings(app_env=app_env, **GOOGLE).oidc_issuer == GOOGLE_ISSUER


def test_mock_is_accepted_only_with_app_env_e2e() -> None:
    assert _settings(app_env="e2e", **MOCK).oidc_issuer == "https://mock-oidc.e2e"


def test_unknown_app_env_is_refused() -> None:
    with pytest.raises(ValidationError):
        _settings(app_env="test", **GOOGLE)


def _start_api(app_env: str, issuer: str) -> subprocess.CompletedProcess[str]:
    """Import app.main in a fresh interpreter: exactly what uvicorn does at start-up."""
    env = {
        **os.environ,
        "APP_ENV": app_env,
        "DATABASE_URL": DB_URL,
        "OIDC_ISSUER": issuer,
        "OIDC_AUTHORIZATION_ENDPOINT": GOOGLE_AUTHORIZATION_ENDPOINT,
        "OIDC_TOKEN_ENDPOINT": GOOGLE_TOKEN_ENDPOINT,
        "OIDC_JWKS_URI": GOOGLE_JWKS_URI,
    }
    return subprocess.run(
        [sys.executable, "-c", "import app.main"],
        cwd=API_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


@pytest.mark.parametrize("app_env", ["local", "production"])
def test_api_process_refuses_to_start_with_mock_issuer(app_env: str) -> None:
    result = _start_api(app_env, "https://mock-oidc.e2e")
    assert result.returncode != 0
    assert "refusing to start: OIDC_ISSUER must be Google's unless APP_ENV=e2e" in result.stderr


def test_api_process_starts_with_google_issuer() -> None:
    result = _start_api("local", GOOGLE_ISSUER)
    assert result.returncode == 0, result.stderr


# --- 2. Where the mock lives ---------------------------------------------------------

OIDC_OVERRIDE_KEYS = (
    "OIDC_ISSUER",
    "OIDC_AUTHORIZATION_ENDPOINT",
    "OIDC_TOKEN_ENDPOINT",
    "OIDC_JWKS_URI",
)


def test_normal_compose_has_no_mock_and_no_oidc_overrides() -> None:
    text = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert not re.search(r"mock|e2e", text, re.IGNORECASE)
    for key in OIDC_OVERRIDE_KEYS:
        assert key not in text  # the api service gets an explicit env list without these


def test_mock_and_its_config_live_only_in_the_e2e_overlay() -> None:
    overlay = (REPO_ROOT / "docker-compose.e2e.yml").read_text(encoding="utf-8")
    assert "mock-oidc:" in overlay
    assert "APP_ENV: e2e" in overlay
    for key in OIDC_OVERRIDE_KEYS:
        assert key in overlay


def test_make_up_does_not_use_the_e2e_overlay() -> None:
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    up_recipe = re.search(r"^up:.*?\n((?:\t.*\n)+)", makefile, re.MULTILINE)
    assert up_recipe is not None
    assert "e2e" not in up_recipe.group(1)


def test_api_image_build_inputs_exclude_the_mock() -> None:
    dockerfile = (API_ROOT / "Dockerfile").read_text(encoding="utf-8")
    sources = {
        src
        for line in dockerfile.splitlines()
        if line.startswith("COPY") and "--from=" not in line
        for src in line.split()[1:-1]
    }
    assert sources == {
        "pyproject.toml",
        "uv.lock",
        ".python-version",
        "app",
        "alembic",
        "alembic.ini",
        "scripts",
    }
    for folder in ("app", "alembic", "scripts"):
        for path in (API_ROOT / folder).rglob("*.py"):
            assert "mock_oidc" not in path.read_text(encoding="utf-8"), path


def test_web_image_context_has_no_mock() -> None:
    # The web image is built from ./web only.
    assert not list((REPO_ROOT / "web").glob("**/mock_oidc*"))
    assert (REPO_ROOT / "e2e" / "mock_oidc" / "mock_oidc.py").is_file()
