"""Logs never contain tokens, authorization codes, login state or cookies (§7)."""

import logging
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from app.core.logsafety import AccessLogQueryFilter, install
from tests.conftest import add_user
from tests.fake_idp import FakeIdP

SESSION = "__Host-mdm_session"
CSRF = "__Host-mdm_csrf"


def test_full_login_and_rejections_log_no_secrets(
    client: TestClient, idp: FakeIdP, admin_engine: Engine, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)  # everything any library logs, not only our warnings
    add_user(admin_engine, "ana@buenavidatrading.com", "editor")
    secrets: list[str] = []

    def attempt(email: str, **claims: Any) -> None:
        start = client.get("/auth/login", follow_redirects=False)
        code, state = idp.approve(start.headers["location"], email=email, **claims)
        secrets.extend([code, state])
        client.get("/auth/callback", params={"code": code, "state": state}, follow_redirects=False)

    attempt("ana@buenavidatrading.com")  # success
    secrets += [client.cookies.get(SESSION) or "", client.cookies.get(CSRF) or ""]
    attempt("stranger@buenavidatrading.com")  # not on the allow-list (logged)
    attempt("ana@buenavidatrading.com", aud="someone-else")  # bad token (logged)
    client.get("/auth/callback", params={"code": "c0de-zzz-123", "state": "st4te-zzz-456"})
    secrets += ["c0de-zzz-123", "st4te-zzz-456"]

    secrets += idp.issued_tokens
    assert len([s for s in secrets if s]) >= 10
    assert any("login rejected" in r.getMessage() for r in caplog.records)  # logging does happen
    # The test client's own request log ("HTTP Request: GET https://localhost/auth/callback?…")
    # is this test acting as the browser, not the API: leave it out.
    server = [r for r in caplog.records if "https://localhost/" not in r.getMessage()]
    text = "\n".join(f"{r.getMessage()} {r.exc_text or ''} {r.args!r}" for r in server)
    for secret in filter(None, secrets):
        assert secret not in text


def test_access_log_lines_drop_the_query_string() -> None:
    install()
    install()  # idempotent
    access = logging.getLogger("uvicorn.access")
    assert sum(isinstance(f, AccessLogQueryFilter) for f in access.filters) == 1
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        1,
        '%s - "%s %s HTTP/%s" %d',
        ("10.0.0.1:5000", "GET", "/auth/callback?code=SECRET&state=STATE", "1.1", 303),
        None,
    )
    assert AccessLogQueryFilter().filter(record)
    line = record.getMessage()
    assert line == '10.0.0.1:5000 - "GET /auth/callback HTTP/1.1" 303'
    assert "SECRET" not in line


def test_nginx_access_log_has_no_query_string_or_cookies() -> None:
    from app.config import REPO_ROOT

    conf = (REPO_ROOT / "web" / "nginx.conf").read_text(encoding="utf-8")
    fmt = conf.split("log_format mdm_safe", 1)[1].split(";", 1)[0]
    assert "$uri" in fmt
    for leaky in (
        "$request ",
        '$request"',
        "$request_uri",
        "$args",
        "$query_string",
        "$http_cookie",
    ):
        assert leaky not in fmt
    assert "access_log /var/log/nginx/access.log mdm_safe;" in conf


def test_nginx_overwrites_x_forwarded_for() -> None:
    """uvicorn trusts the proxy and takes the first X-Forwarded-For entry as the client IP
    (rate limits, audit log), so nginx must replace a client-sent header, not append to it."""
    from app.config import REPO_ROOT

    conf = (REPO_ROOT / "web" / "nginx.conf").read_text(encoding="utf-8")
    assert "proxy_set_header X-Forwarded-For $remote_addr;" in conf
    assert "$proxy_add_x_forwarded_for" not in conf
