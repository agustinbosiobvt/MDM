"""Application settings, read from the environment (and ../.env when run on the host)."""

from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, PostgresDsn, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]

LOCAL_DB_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "db"})

GOOGLE_ISSUER = "https://accounts.google.com"
GOOGLE_AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
# A public URL, not a secret.
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"  # noqa: S105  # nosec B105
GOOGLE_JWKS_URI = "https://www.googleapis.com/oauth2/v3/certs"


def require_ssl_unless_local(url: str) -> str:
    """Refuse non-local Postgres URLs that don't enforce TLS."""
    dsn = PostgresDsn(url)
    hosts = {h["host"] for h in dsn.hosts() if h["host"]}
    if hosts - LOCAL_DB_HOSTS and "sslmode=require" not in url and "sslmode=verify" not in url:
        raise ValueError("non-local database URLs must set sslmode=require (or verify-*)")
    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_env: Literal["local", "e2e", "production"] = "local"
    log_level: str = "INFO"
    web_origin: str = "http://localhost:8080"

    database_url: str = Field(min_length=1)

    # --- Google OIDC (server-side Authorization Code + PKCE) ------------------
    google_client_id: str = ""
    google_client_secret: SecretStr = SecretStr("")
    oidc_redirect_uri: str = "http://localhost:8080/auth/callback"
    allowed_hosted_domain: str = "buenavidatrading.com"
    bootstrap_admin_email: str = ""
    # Provider endpoints. Overridable only outside production (e2e uses a mock IdP).
    oidc_issuer: str = GOOGLE_ISSUER
    oidc_authorization_endpoint: str = GOOGLE_AUTHORIZATION_ENDPOINT
    oidc_token_endpoint: str = GOOGLE_TOKEN_ENDPOINT
    oidc_jwks_uri: str = GOOGLE_JWKS_URI

    # --- Sessions ---------------------------------------------------------------
    session_idle_minutes: int = Field(default=30, ge=1, le=24 * 60)
    session_absolute_hours: int = Field(default=8, ge=1, le=72)
    login_state_minutes: int = Field(default=10, ge=1, le=30)

    # --- Rate limits (slowapi syntax) --------------------------------------------
    auth_rate_limit: str = "20/minute"
    import_rate_limit: str = "30/minute"

    # --- Imports ------------------------------------------------------------------
    upload_dir: Path = REPO_ROOT / "api" / "var" / "uploads"  # outside any web root
    upload_max_bytes: int = Field(default=20 * 1024 * 1024, ge=1024, le=100 * 1024 * 1024)
    import_job_hours: int = Field(default=4, ge=1, le=72)

    @field_validator("upload_dir")
    @classmethod
    def _absolute_upload_dir(cls, v: Path) -> Path:
        return v if v.is_absolute() else (REPO_ROOT / v).resolve()

    @field_validator("database_url")
    @classmethod
    def _db_ssl(cls, v: str) -> str:
        return require_ssl_unless_local(v)

    @field_validator("allowed_hosted_domain", "bootstrap_admin_email")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.strip().lower()

    @model_validator(mode="after")
    def _only_google_outside_e2e(self) -> Self:
        """A non-Google identity provider (the e2e mock) is accepted only with APP_ENV=e2e.

        Settings are built when the app is created, so this stops the API from starting.
        """
        overridden = [
            name
            for name, value, google in (
                ("OIDC_ISSUER", self.oidc_issuer, GOOGLE_ISSUER),
                (
                    "OIDC_AUTHORIZATION_ENDPOINT",
                    self.oidc_authorization_endpoint,
                    GOOGLE_AUTHORIZATION_ENDPOINT,
                ),
                ("OIDC_TOKEN_ENDPOINT", self.oidc_token_endpoint, GOOGLE_TOKEN_ENDPOINT),
                ("OIDC_JWKS_URI", self.oidc_jwks_uri, GOOGLE_JWKS_URI),
            )
            if value != google
        ]
        if overridden and self.app_env != "e2e":
            raise ValueError(
                f"refusing to start: {', '.join(overridden)} must be Google's unless APP_ENV=e2e "
                f"(APP_ENV={self.app_env})"
            )
        return self

    @model_validator(mode="after")
    def _e2e_only_on_throwaway_db(self) -> Self:
        """In e2e mode (mock Google, test data) the API may only use a *_e2e / *_test DB."""
        if self.app_env == "e2e":
            name = PostgresDsn(self.database_url).path or ""
            if not name.lstrip("/").endswith(("_e2e", "_test")):
                raise ValueError(
                    "refusing to start: APP_ENV=e2e needs a database ending in _e2e or _test"
                )
        return self

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def accepted_issuers(self) -> frozenset[str]:
        # Google issues both forms.
        if self.oidc_issuer == GOOGLE_ISSUER:
            return frozenset({GOOGLE_ISSUER, "accounts.google.com"})
        return frozenset({self.oidc_issuer})


@lru_cache
def get_settings() -> Settings:
    return Settings()
