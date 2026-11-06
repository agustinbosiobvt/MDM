"""User administration: list/search/filter/sort/paginate, view, add, edit, remove (soft)."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from tests.conftest import BOOTSTRAP_ADMIN, LoggedIn

Login = Callable[..., LoggedIn]


@pytest.fixture
def admin(client: TestClient, login: Login) -> LoggedIn:
    return login("admin@buenavidatrading.com", role="admin")


def _h(me: LoggedIn) -> dict[str, str]:
    return {"X-CSRF-Token": me.csrf}


def _create(client: TestClient, me: LoggedIn, email: str, role: str = "viewer") -> dict[str, Any]:
    r = client.post("/api/users", json={"email": email, "role": role}, headers=_h(me))
    assert r.status_code == 201, r.text
    return dict(r.json())


def test_add_view_and_list(client: TestClient, admin: LoggedIn) -> None:
    created = _create(client, admin, "  New.Person@BuenaVidaTrading.com ", "editor")
    assert created["email"] == "new.person@buenavidatrading.com"  # trimmed + lowercased
    assert created["is_active"] is True
    assert created["version"] == 1

    one = client.get(f"/api/users/{created['id']}").json()
    assert one["role"] == "editor"

    page = client.get("/api/users").json()
    assert page["total"] == 3  # + the bootstrap admin seeded at startup
    assert {u["email"] for u in page["items"]} == {
        BOOTSTRAP_ADMIN,
        "admin@buenavidatrading.com",
        "new.person@buenavidatrading.com",
    }


def test_search_filter_sort_paginate(client: TestClient, admin: LoggedIn) -> None:
    for i in range(5):
        _create(client, admin, f"user{i}@buenavidatrading.com", "editor" if i % 2 else "viewer")

    assert client.get("/api/users", params={"q": "user3"}).json()["total"] == 1
    assert client.get("/api/users", params={"role": "editor"}).json()["total"] == 2
    desc = client.get("/api/users", params={"sort": "email", "order": "desc"}).json()
    assert desc["items"][0]["email"] == "user4@buenavidatrading.com"
    p2 = client.get("/api/users", params={"page": 2, "page_size": 4}).json()
    assert p2["total"] == 7  # 5 + admin + bootstrap admin
    assert len(p2["items"]) == 3
    assert client.get("/api/users", params={"sort": "nope"}).status_code == 422
    assert client.get("/api/users", params={"page_size": 1000}).status_code == 422


def test_duplicate_email_is_rejected(client: TestClient, admin: LoggedIn) -> None:
    _create(client, admin, "dup@buenavidatrading.com")
    r = client.post(
        "/api/users",
        json={"email": "DUP@buenavidatrading.com", "role": "viewer"},
        headers=_h(admin),
    )
    assert r.status_code == 409


@pytest.mark.parametrize(
    "body",
    [
        {"email": "someone@gmail.com", "role": "viewer"},  # outside the Workspace domain
        {"email": "not-an-email", "role": "viewer"},
        {"email": "x@buenavidatrading.com", "role": "finance"},  # role no longer exists
        {"email": "x@buenavidatrading.com", "role": "viewer", "is_admin": True},  # extra field
        {"email": "a" * 250 + "@buenavidatrading.com", "role": "viewer"},  # too long
        {"email": "x@buenavidatrading.com", "role": "viewer", "display_name": "x" * 201},
    ],
)
def test_invalid_input_is_rejected(
    client: TestClient, admin: LoggedIn, body: dict[str, Any]
) -> None:
    assert client.post("/api/users", json=body, headers=_h(admin)).status_code == 422


def test_edit_with_optimistic_locking(
    client: TestClient, admin: LoggedIn, admin_engine: Engine
) -> None:
    u = _create(client, admin, "edit@buenavidatrading.com")
    r = client.patch(
        f"/api/users/{u['id']}",
        json={"version": 1, "role": "editor", "display_name": "Edit Me"},
        headers=_h(admin),
    )
    assert r.status_code == 200
    assert r.json()["role"] == "editor"
    assert r.json()["version"] == 2

    # Someone else's stale copy (version 1) is refused with 409.
    stale = client.patch(
        f"/api/users/{u['id']}", json={"version": 1, "role": "viewer"}, headers=_h(admin)
    )
    assert stale.status_code == 409
    assert "someone else changed" in stale.json()["detail"].lower()
    assert client.get(f"/api/users/{u['id']}").json()["role"] == "editor"

    with admin_engine.connect() as conn:
        entry = conn.execute(
            text(
                "SELECT user_email, old_values, new_values FROM mdm.audit_log "
                "WHERE entity = 'app_user' AND action = 'update'"
            )
        ).one()
    assert entry.user_email == "admin@buenavidatrading.com"
    assert entry.old_values["role"] == "viewer"
    assert entry.new_values["role"] == "editor"


def test_remove_is_a_soft_delete_that_ends_sessions(
    client: TestClient, admin: LoggedIn, admin_engine: Engine
) -> None:
    u = _create(client, admin, "leaver@buenavidatrading.com")
    with admin_engine.begin() as conn:  # the leaver has a live session
        conn.execute(
            text(
                "INSERT INTO mdm.user_session (token_hash, csrf_hash, user_id, expires_at) "
                "VALUES (sha256('t'), sha256('c'), :id, now() + interval '1 h')"
            ),
            {"id": u["id"]},
        )
    r = client.delete(f"/api/users/{u['id']}", params={"version": 1}, headers=_h(admin))
    assert r.status_code == 200
    assert r.json()["is_active"] is False

    with admin_engine.connect() as conn:
        assert (
            conn.execute(
                text("SELECT count(*) FROM mdm.app_user WHERE id = :id"), {"id": u["id"]}
            ).scalar_one()
            == 1
        )
        assert (
            conn.execute(
                text("SELECT count(*) FROM mdm.user_session WHERE user_id = :id"), {"id": u["id"]}
            ).scalar_one()
            == 0
        )
    assert client.get("/api/users", params={"active": False}).json()["total"] == 1

    # Reactivate.
    back = client.patch(
        f"/api/users/{u['id']}", json={"version": 2, "is_active": True}, headers=_h(admin)
    )
    assert back.json()["is_active"] is True


def test_admin_cannot_lock_themselves_out(client: TestClient, admin: LoggedIn) -> None:
    me = client.get("/api/me").json()
    version = client.get(f"/api/users/{me['id']}").json()["version"]
    assert (
        client.patch(
            f"/api/users/{me['id']}", json={"version": version, "role": "viewer"}, headers=_h(admin)
        ).status_code
        == 409
    )
    assert (
        client.delete(
            f"/api/users/{me['id']}", params={"version": version}, headers=_h(admin)
        ).status_code
        == 409
    )
    assert client.get("/api/me").json()["role"] == "admin"


def test_role_change_applies_on_next_request(
    client: TestClient, login: Login, admin_engine: Engine
) -> None:
    login("ed@buenavidatrading.com", role="admin")
    assert client.get("/api/users").status_code == 200
    with admin_engine.begin() as conn:
        conn.execute(text("UPDATE mdm.app_user SET role = 'viewer'"))
    assert client.get("/api/users").status_code == 403


def test_unknown_user_is_404(client: TestClient, admin: LoggedIn) -> None:
    missing = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"/api/users/{missing}").status_code == 404
    assert client.get("/api/users/not-a-uuid").status_code == 422
