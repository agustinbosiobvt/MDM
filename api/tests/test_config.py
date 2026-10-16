import pytest

from app.config import require_ssl_unless_local


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://u:p@127.0.0.1:5432/mdm",
        "postgresql+psycopg://u:p@localhost/mdm",
        "postgresql+psycopg://u:p@db:5432/mdm",
        "postgresql+psycopg://u:p@pg.example.com/mdm?sslmode=require",
        "postgresql+psycopg://u:p@pg.example.com/mdm?sslmode=verify-full",
    ],
)
def test_accepted_db_urls(url: str) -> None:
    assert require_ssl_unless_local(url) == url


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://u:p@pg.example.com/mdm",
        "postgresql+psycopg://u:p@pg.example.com/mdm?sslmode=prefer",
    ],
)
def test_remote_db_without_tls_is_refused(url: str) -> None:
    with pytest.raises(ValueError, match="sslmode"):
        require_ssl_unless_local(url)
