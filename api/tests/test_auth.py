"""Google login end to end (fake IdP): ID-token validation, allow-list, sessions, logout."""

import time
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from joserfc.jwk import RSAKey
from sqlalchemy import Engine, text

from tests.conftest import BOOTSTRAP_ADMIN, WEB_ORIGIN, LoggedIn, add_user
from tests.fake_idp import FakeIdP

Login = Callable[..., LoggedIn]
SESSION = "__Host-mdm_session"
CSRF = "__Host-mdm_csrf"


def _audit(engine: Engine, action: str) -> list[dict[str, Any]]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT user_email, action, new_values FROM mdm.audit_log "
                "WHERE action = :a ORDER BY id"
            ),
            {"a": action},
        ).mappings()
        return [dict(r) for r in rows]


def _start(client: TestClient) -> str:
    r = client.get("/auth/login", follow_redirects=False)
    assert r.status_code == 303
    return r.headers["location"]


def _callback(client: TestClient, code: str, state: str) -> Any:
    return client.get(
        "/auth/callback", params={"code": code, "state": state}, follow_redirects=False
    )


# --- Happy path ----------------------------------------------------------------


def test_login_creates_session_with_hardened_cookies(
    client: TestClient, idp: FakeIdP, admin_engine: Engine
) -> None:
    add_user(admin_engine, "ana@buenavidatrading.com", "editor")
    authorize = _start(client)
    assert authorize.startswith("https://idp.test/authorize?")
    assert "code_challenge=" in authorize
    assert "hd=buenavidatrading.com" in authorize

    code, state = idp.approve(authorize, email="ana@buenavidatrading.com")
    r = _callback(client, code, state)

    assert r.status_code == 303
    assert r.headers["location"] == "/"
    cookies = {c.split("=", 1)[0]: c.lower() for c in r.headers.get_list("set-cookie")}
    session_cookie = cookies[SESSION]
    for attr in ("httponly", "secure", "samesite=lax", "path=/"):
        assert attr in session_cookie
    assert "domain=" not in session_cookie
    assert "httponly" not in cookies[CSRF]  # readable by the SPA (double submit)
    assert "id_token" not in r.text
    assert "eyJ" not in r.headers["location"]

    me = client.get("/api/me")
    assert me.status_code == 200
    assert me.json()["email"] == "ana@buenavidatrading.com"
    assert me.json()["role"] == "editor"
    assert _audit(admin_engine, "login")[0]["user_email"] == "ana@buenavidatrading.com"


def test_login_bookkeeping_does_not_bump_version(
    client: TestClient, login: Login, admin_engine: Engine
) -> None:
    """Signing in is not an edit: an admin holding this user open must not get a 409."""
    add_user(admin_engine, "ana@buenavidatrading.com", "editor")
    login("ana@buenavidatrading.com", role=None, name="Ana Example")
    login("ana@buenavidatrading.com", role=None, name="Other Name")
    with admin_engine.connect() as conn:
        row = conn.execute(
            text("SELECT version, last_login_at, display_name FROM mdm.app_user WHERE email = :e"),
            {"e": "ana@buenavidatrading.com"},
        ).one()
    assert row.version == 1
    assert row.last_login_at is not None
    assert row.display_name == "Ana Example"  # filled once from Google, never overwritten


def test_bootstrap_admin_is_seeded_and_can_log_in(client: TestClient, login: Login) -> None:
    login(BOOTSTRAP_ADMIN, role=None)
    assert client.get("/api/me").json()["role"] == "admin"


def test_session_token_is_stored_hashed(
    client: TestClient, login: Login, admin_engine: Engine
) -> None:
    login("ana@buenavidatrading.com")
    token = client.cookies.get(SESSION)
    assert token
    with admin_engine.connect() as conn:
        stored = conn.execute(text("SELECT token_hash FROM mdm.user_session")).scalar_one()
    assert token.encode() not in bytes(stored)
    assert len(bytes(stored)) == 32


# --- Allow-list and claim checks ------------------------------------------------------


def test_unknown_user_gets_no_access_and_is_logged(
    client: TestClient, idp: FakeIdP, admin_engine: Engine
) -> None:
    code, state = idp.approve(_start(client), email="stranger@buenavidatrading.com")
    r = _callback(client, code, state)
    assert r.headers["location"] == "/no-access?reason=not_allowed"
    assert SESSION not in client.cookies
    denied = _audit(admin_engine, "login_denied")
    assert denied[0]["user_email"] == "stranger@buenavidatrading.com"
    assert denied[0]["new_values"] == {"reason": "not_in_allowlist"}


def test_inactive_user_is_rejected(client: TestClient, idp: FakeIdP, admin_engine: Engine) -> None:
    add_user(admin_engine, "old@buenavidatrading.com", "admin", active=False)
    code, state = idp.approve(_start(client), email="old@buenavidatrading.com")
    assert _callback(client, code, state).headers["location"] == "/no-access?reason=not_allowed"
    assert client.get("/api/me").status_code == 401


@pytest.mark.parametrize(
    ("email", "claims"),
    [
        ("someone@gmail.com", {"hd": None}),  # consumer account
        ("x@buenavidatrading.com", {"hd": "other.com"}),  # other Workspace
        ("x@buenavidatrading.com", {"hd": None}),  # hd missing
        ("x@other.com", {"hd": "buenavidatrading.com"}),  # email outside the domain
        ("x@buenavidatrading.com", {"email_verified": False}),
    ],
)
def test_domain_and_verified_email_are_enforced(
    client: TestClient, idp: FakeIdP, admin_engine: Engine, email: str, claims: dict[str, Any]
) -> None:
    add_user(admin_engine, "x@buenavidatrading.com", "admin")
    code, state = idp.approve(_start(client), email=email, **claims)
    assert _callback(client, code, state).headers["location"] == "/no-access?reason=not_allowed"
    assert client.get("/api/me").status_code == 401


@pytest.mark.parametrize(
    "claims",
    [
        {"nonce": "replayed-nonce"},
        {"aud": "someone-elses-client"},
        {"iss": "https://evil.example"},
        {"exp": int(time.time()) - 3600},
        {"iat": None},
    ],
    ids=["nonce", "aud", "iss", "expired", "no-iat"],
)
def test_invalid_id_token_claims_are_rejected(
    client: TestClient, idp: FakeIdP, admin_engine: Engine, claims: dict[str, Any]
) -> None:
    add_user(admin_engine, "ana@buenavidatrading.com", "admin")
    code, state = idp.approve(_start(client), email="ana@buenavidatrading.com")
    grant = idp.grants[code]
    grant.claims.update(claims)
    if claims.get("iat", 0) is None:
        del grant.claims["iat"]
    assert _callback(client, code, state).headers["location"] == "/no-access?reason=error"
    assert client.get("/api/me").status_code == 401


def test_token_signed_by_unknown_key_is_rejected(
    client: TestClient, idp: FakeIdP, admin_engine: Engine
) -> None:
    add_user(admin_engine, "ana@buenavidatrading.com", "admin")
    code, state = idp.approve(_start(client), email="ana@buenavidatrading.com")
    attacker = RSAKey.generate_key(2048, parameters={"kid": "k1"})  # same kid, wrong key
    grant = idp.grants[code]
    grant.claims["__raw_id_token"] = idp.sign(dict(grant.claims), key=attacker)
    assert _callback(client, code, state).headers["location"] == "/no-access?reason=error"


def test_alg_none_token_is_rejected(client: TestClient, idp: FakeIdP, admin_engine: Engine) -> None:
    add_user(admin_engine, "ana@buenavidatrading.com", "admin")
    code, state = idp.approve(_start(client), email="ana@buenavidatrading.com")
    grant = idp.grants[code]
    _header, payload, _ = idp.sign(dict(grant.claims)).split(".")
    grant.claims["__raw_id_token"] = "eyJhbGciOiJub25lIn0." + payload + "."
    assert _callback(client, code, state).headers["location"] == "/no-access?reason=error"


# --- State, PKCE, browser binding -------------------------------------------------------


def test_pkce_verifier_must_match(client: TestClient, idp: FakeIdP, admin_engine: Engine) -> None:
    add_user(admin_engine, "ana@buenavidatrading.com", "admin")
    code, state = idp.approve(_start(client), email="ana@buenavidatrading.com")
    idp.grants[code].code_challenge = "tampered"
    assert _callback(client, code, state).headers["location"] == "/no-access?reason=error"


def test_state_is_single_use(client: TestClient, idp: FakeIdP, admin_engine: Engine) -> None:
    add_user(admin_engine, "ana@buenavidatrading.com", "admin")
    authorize = _start(client)
    code, state = idp.approve(authorize, email="ana@buenavidatrading.com")
    assert _callback(client, code, state).headers["location"] == "/"
    code2, _ = idp.approve(authorize, email="ana@buenavidatrading.com")
    assert _callback(client, code2, state).headers["location"] == "/no-access?reason=error"


def test_unknown_state_is_rejected_without_calling_idp(client: TestClient, idp: FakeIdP) -> None:
    _start(client)
    assert (
        _callback(client, "code", "forged-state").headers["location"] == "/no-access?reason=error"
    )
    assert idp.token_requests == 0


def test_callback_from_another_browser_is_rejected(
    client: TestClient, idp: FakeIdP, admin_engine: Engine
) -> None:
    """A login link started in one browser can't be completed in another (login CSRF)."""
    add_user(admin_engine, "ana@buenavidatrading.com", "admin")
    code, state = idp.approve(_start(client), email="ana@buenavidatrading.com")
    client.cookies.delete("__Host-mdm_login")
    assert _callback(client, code, state).headers["location"] == "/no-access?reason=error"
    assert idp.token_requests == 0


def test_expired_login_state_is_rejected(
    client: TestClient, idp: FakeIdP, admin_engine: Engine
) -> None:
    add_user(admin_engine, "ana@buenavidatrading.com", "admin")
    code, state = idp.approve(_start(client), email="ana@buenavidatrading.com")
    with admin_engine.begin() as conn:
        conn.execute(text("UPDATE mdm.oauth_login_state SET expires_at = now() - interval '1 s'"))
    assert _callback(client, code, state).headers["location"] == "/no-access?reason=error"


def test_user_cancelling_at_google(client: TestClient) -> None:
    r = client.get("/auth/callback", params={"error": "access_denied"}, follow_redirects=False)
    assert r.headers["location"] == "/no-access?reason=cancelled"


# --- Session lifecycle ----------------------------------------------------------------


def test_session_id_rotates_at_login(
    client: TestClient, login: Login, admin_engine: Engine
) -> None:
    login("ana@buenavidatrading.com")
    first = client.cookies.get(SESSION)
    login("bob@buenavidatrading.com", role="editor")
    second = client.cookies.get(SESSION)
    assert first
    assert second
    assert first != second
    with admin_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM mdm.user_session")).scalar_one() == 1
    client.cookies.clear()
    client.cookies.set(SESSION, first)
    assert client.get("/api/me").status_code == 401


def test_logout_invalidates_session_server_side(
    client: TestClient, login: Login, admin_engine: Engine
) -> None:
    me = login("ana@buenavidatrading.com")
    token = client.cookies.get(SESSION)
    r = client.post("/auth/logout", headers={"X-CSRF-Token": me.csrf})
    assert r.status_code == 204
    with admin_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM mdm.user_session")).scalar_one() == 0
    # Even a copy of the old cookie is now worthless.
    client.cookies.clear()
    client.cookies.set(SESSION, token or "")
    assert client.get("/api/me").status_code == 401
    assert _audit(admin_engine, "logout")[0]["user_email"] == "ana@buenavidatrading.com"


def test_logout_requires_csrf_token(client: TestClient, login: Login) -> None:
    login("ana@buenavidatrading.com")
    assert client.post("/auth/logout").status_code == 403
    assert client.post("/auth/logout", headers={"X-CSRF-Token": "wrong"}).status_code == 403
    assert client.get("/api/me").status_code == 200


def test_cross_origin_post_is_blocked(client: TestClient, login: Login) -> None:
    me = login("ana@buenavidatrading.com")
    for origin in ("https://evil.example", "http://127.0.0.1:8080", "null"):
        r = client.post("/auth/logout", headers={"X-CSRF-Token": me.csrf, "Origin": origin})
        assert r.status_code == 403
    assert client.get("/api/me").status_code == 200


def test_idle_timeout(client: TestClient, login: Login, admin_engine: Engine) -> None:
    login("ana@buenavidatrading.com")
    with admin_engine.begin() as conn:
        conn.execute(text("UPDATE mdm.user_session SET last_seen_at = now() - interval '31 min'"))
    assert client.get("/api/me").status_code == 401


def test_activity_extends_idle_window(
    client: TestClient, login: Login, admin_engine: Engine
) -> None:
    login("ana@buenavidatrading.com")
    with admin_engine.begin() as conn:
        conn.execute(text("UPDATE mdm.user_session SET last_seen_at = now() - interval '29 min'"))
    assert client.get("/api/me").status_code == 200
    with admin_engine.connect() as conn:
        age = conn.execute(
            text("SELECT extract(epoch FROM now() - last_seen_at) FROM mdm.user_session")
        ).scalar_one()
    assert age < 60


def test_absolute_timeout(client: TestClient, login: Login, admin_engine: Engine) -> None:
    login("ana@buenavidatrading.com")
    with admin_engine.connect() as conn:
        hours = conn.execute(
            text("SELECT extract(epoch FROM expires_at - created_at) / 3600 FROM mdm.user_session")
        ).scalar_one()
    assert round(hours) == 8
    with admin_engine.begin() as conn:
        conn.execute(text("UPDATE mdm.user_session SET expires_at = now() - interval '1 s'"))
    assert client.get("/api/me").status_code == 401


def test_deactivated_user_loses_access_immediately(
    client: TestClient, login: Login, admin_engine: Engine
) -> None:
    login("ana@buenavidatrading.com")
    with admin_engine.begin() as conn:
        conn.execute(text("UPDATE mdm.app_user SET is_active = false"))
    assert client.get("/api/me").status_code == 401


def test_login_is_rate_limited(client: TestClient) -> None:
    from app.config import get_settings

    settings = get_settings()
    original = settings.auth_rate_limit
    settings.auth_rate_limit = "3/minute"
    try:
        codes = [client.get("/auth/login", follow_redirects=False).status_code for _ in range(5)]
    finally:
        settings.auth_rate_limit = original
    assert codes[:3] == [303, 303, 303]
    assert codes[3:] == [429, 429]


def test_login_not_configured_explains_itself(client: TestClient) -> None:
    from app.config import get_settings

    settings = get_settings()
    original = settings.google_client_id
    settings.google_client_id = ""
    try:
        r = client.get("/auth/login", follow_redirects=False)
        assert r.headers["location"] == "/no-access?reason=not_configured"
    finally:
        settings.google_client_id = original


def test_me_requires_login(client: TestClient) -> None:
    r = client.get("/api/me")
    assert r.status_code == 401
    assert r.json() == {"detail": "Not authenticated"}


def test_web_origin_constant_matches_settings() -> None:
    from app.config import get_settings

    assert get_settings().web_origin == WEB_ORIGIN
