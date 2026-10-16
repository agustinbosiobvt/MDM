"""Application settings, read from the environment (and ../.env when run on the host)."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, PostgresDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]

LOCAL_DB_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "db"})


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

    app_env: Literal["local", "test", "production"] = "local"
    log_level: str = "INFO"
    web_origin: str = "http://localhost:8080"

    database_url: str = Field(min_length=1)

    @field_validator("database_url")
    @classmethod
    def _db_ssl(cls, v: str) -> str:
        return require_ssl_unless_local(v)

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
