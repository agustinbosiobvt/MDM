"""Company module: list / view / add / edit / remove, the default company, addresses, contacts."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from tests.conftest import LoggedIn

Login = Callable[..., LoggedIn]


@pytest.fixture
def editor(client: TestClient, login: Login) -> LoggedIn:
    return login("editor@buenavidatrading.com", role="editor")


def _h(me: LoggedIn) -> dict[str, str]:
    return {"X-CSRF-Token": me.csrf}


def _company(**over: Any) -> dict[str, Any]:
    body = {
        "code": "BVT",
        "legal_name": "Buena Vida Trading S.L.",
        "trade_name": "Buena Vida",
        "eori": "ESB12345678",
        "country_code": "ES",
    }
    return {**body, **over}


def _create(client: TestClient, me: LoggedIn, **over: Any) -> dict[str, Any]:
    r = client.post("/api/companies", json=_company(**over), headers=_h(me))
    assert r.status_code == 201, r.text
    return dict(r.json())


def _audit(engine: Engine, entity: str) -> list[Any]:
    with engine.connect() as conn:
        return list(
            conn.execute(
                text(
                    "SELECT action, user_email, old_values, new_values FROM mdm.audit_log "
                    "WHERE entity = :e ORDER BY id"
                ),
                {"e": entity},
            )
        )


# --- Identity ----------------------------------------------------------------------


def test_add_and_view(client: TestClient, editor: LoggedIn, admin_engine: Engine) -> None:
    c = _create(client, editor, code=" bvt-es ", eori="es b123 45678")
    assert c["code"] == "BVT-ES"  # upper-cased, spaces removed
    assert c["eori"] == "ESB12345678"
    assert "base_currency" not in c  # Company has no currency
    assert "tax_id" not in c  # ...and no Tax ID
    assert c["is_default"] is True  # the first company becomes the default
    assert c["addresses"] == []
    assert c["contacts"] == []
    got = client.get(f"/api/companies/{c['id']}").json()
    assert got["legal_name"] == "Buena Vida Trading S.L."
    created = _audit(admin_engine, "company")[0]
    assert created.action == "create"
    assert created.user_email == "editor@buenavidatrading.com"
    assert created.new_values["eori"] == "ESB12345678"


def test_list_search_filter_sort_paginate(client: TestClient, editor: LoggedIn) -> None:
    for i, name in enumerate(["Alpha GmbH", "Beta S.A.", "Gamma Ltd"]):
        _create(client, editor, code=f"C{i}", legal_name=name)
    page = client.get("/api/companies").json()
    assert page["total"] == 3
    assert [c["legal_name"] for c in page["items"]] == ["Alpha GmbH", "Beta S.A.", "Gamma Ltd"]
    assert client.get("/api/companies", params={"q": "beta"}).json()["total"] == 1
    assert client.get("/api/companies", params={"q": "c2"}).json()["total"] == 1  # by code
    desc = client.get("/api/companies", params={"sort": "code", "order": "desc"}).json()
    assert desc["items"][0]["code"] == "C2"
    p2 = client.get("/api/companies", params={"page": 2, "page_size": 2}).json()
    assert len(p2["items"]) == 1
    assert client.get("/api/companies", params={"sort": "nope"}).status_code == 422


@pytest.mark.parametrize(
    ("over", "field"),
    [
        ({"code": "x"}, "code"),  # too short
        ({"code": "BAD CODE!"}, "code"),
        ({"legal_name": "  "}, "legal_name"),
        ({"legal_name": "x" * 201}, "legal_name"),
        ({"eori": "12345"}, "eori"),  # must start with 2 letters
        ({"eori": "ES" + "1" * 16}, "eori"),  # too long
        ({"country_code": "Spain"}, "country_code"),
    ],
)
def test_invalid_identity_is_rejected(
    client: TestClient, editor: LoggedIn, over: dict[str, Any], field: str
) -> None:
    r = client.post("/api/companies", json=_company(**over), headers=_h(editor))
    assert r.status_code == 422
    assert any(e["loc"][-1] == field for e in r.json()["errors"])


def test_unknown_iso_codes_are_rejected(client: TestClient, editor: LoggedIn) -> None:
    r = client.post("/api/companies", json=_company(country_code="ZZ"), headers=_h(editor))
    assert r.status_code == 422
    assert r.json()["detail"] == "Unknown country code ZZ"


def test_duplicate_code_is_blocked(client: TestClient, editor: LoggedIn) -> None:
    _create(client, editor)
    dup_code = client.post("/api/companies", json=_company(legal_name="Other"), headers=_h(editor))
    assert dup_code.status_code == 409
    assert dup_code.json()["detail"] == "Another record already uses this code"


@pytest.mark.parametrize("field", ["tax_id", "base_currency", "default_currency"])
def test_removed_fields_are_rejected(client: TestClient, editor: LoggedIn, field: str) -> None:
    """Company has no Tax ID and no currency (spec correction 2026-10-16)."""
    r = client.post("/api/companies", json=_company(**{field: "X1"}), headers=_h(editor))
    assert r.status_code == 422
    assert r.json()["errors"][0]["type"] == "extra_forbidden"


def test_edit_with_optimistic_locking(
    client: TestClient, editor: LoggedIn, admin_engine: Engine
) -> None:
    c = _create(client, editor)
    r = client.patch(
        f"/api/companies/{c['id']}",
        json={"version": 1, "trade_name": "BVT", "country_code": "pt", "eori": None},
        headers=_h(editor),
    )
    assert r.status_code == 200, r.text
    assert r.json()["trade_name"] == "BVT"
    assert r.json()["country_code"] == "PT"
    assert r.json()["eori"] is None
    assert r.json()["version"] == 2
    stale = client.patch(
        f"/api/companies/{c['id']}", json={"version": 1, "legal_name": "Old"}, headers=_h(editor)
    )
    assert stale.status_code == 409
    update = _audit(admin_engine, "company")[-1]
    assert update.action == "update"
    assert update.old_values["country_code"] == "ES"
    assert update.new_values["country_code"] == "PT"


def test_required_fields_cannot_be_cleared(client: TestClient, editor: LoggedIn) -> None:
    c = _create(client, editor)
    r = client.patch(
        f"/api/companies/{c['id']}", json={"version": 1, "legal_name": None}, headers=_h(editor)
    )
    assert r.status_code == 422


# --- Default company ---------------------------------------------------------------


def test_exactly_one_default(client: TestClient, editor: LoggedIn) -> None:
    a = _create(client, editor, code="A1")
    b = _create(client, editor, code="B1")
    assert a["is_default"] is True
    assert b["is_default"] is False
    r = client.post(f"/api/companies/{b['id']}/default", headers=_h(editor))
    assert r.json()["is_default"] is True
    assert client.get(f"/api/companies/{a['id']}").json()["is_default"] is False
    # Creating with is_default=true moves it as well.
    c = _create(client, editor, code="C1", is_default=True)
    defaults = [x for x in client.get("/api/companies").json()["items"] if x["is_default"]]
    assert [d["id"] for d in defaults] == [c["id"]]


def test_default_company_cannot_be_removed(client: TestClient, editor: LoggedIn) -> None:
    a = _create(client, editor)
    r = client.delete(f"/api/companies/{a['id']}", params={"version": 1}, headers=_h(editor))
    assert r.status_code == 409
    assert "default" in r.json()["detail"]
    r = client.patch(
        f"/api/companies/{a['id']}", json={"version": 1, "is_active": False}, headers=_h(editor)
    )
    assert r.status_code == 409


# --- Remove / reactivate / permanent delete ---------------------------------------------


def test_remove_is_soft_and_reversible(
    client: TestClient, editor: LoggedIn, admin_engine: Engine
) -> None:
    _create(client, editor, code="MAIN")
    b = _create(client, editor, code="OLD")
    r = client.delete(f"/api/companies/{b['id']}", params={"version": 1}, headers=_h(editor))
    assert r.status_code == 200
    assert r.json()["is_active"] is False
    assert client.get("/api/companies").json()["total"] == 1
    assert client.get("/api/companies", params={"active": False}).json()["total"] == 1
    with admin_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM mdm.party")).scalar_one() == 2
    # A removed company can't be edited in place, can't be default; it can be reactivated.
    assert (
        client.post(
            f"/api/parties/{b['id']}/contacts", json={"name": "X"}, headers=_h(editor)
        ).status_code
        == 409
    )
    assert client.post(f"/api/companies/{b['id']}/default", headers=_h(editor)).status_code == 409
    back = client.patch(
        f"/api/companies/{b['id']}", json={"version": 2, "is_active": True}, headers=_h(editor)
    )
    assert back.json()["is_active"] is True


def test_permanent_delete(client: TestClient, login: Login, admin_engine: Engine) -> None:
    admin = login("admin@buenavidatrading.com", role="admin")
    _create(client, admin, code="MAIN")
    b = _create(client, admin, code="GONE")
    client.post(
        f"/api/parties/{b['id']}/addresses",
        json={"address_type": "billing", "line1": "x", "city": "y", "country_code": "ES"},
        headers=_h(admin),
    )
    url = f"/api/companies/{b['id']}/permanent"
    # Must be removed first.
    assert client.delete(url, params={"confirm": "GONE"}, headers=_h(admin)).status_code == 409
    client.delete(f"/api/companies/{b['id']}", params={"version": 1}, headers=_h(admin))
    # Must type the code.
    assert client.delete(url, params={"confirm": "NOPE"}, headers=_h(admin)).status_code == 422
    assert client.delete(url, params={"confirm": "gone"}, headers=_h(admin)).status_code == 204
    assert client.get(f"/api/companies/{b['id']}").status_code == 404
    with admin_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM mdm.address")).scalar_one() == 0
    deleted = _audit(admin_engine, "company")[-1]
    assert deleted.action == "delete_permanently"
    assert deleted.old_values["code"] == "GONE"
    assert deleted.old_values["addresses"][0]["address_type"] == "billing"


def test_editor_cannot_delete_permanently(client: TestClient, editor: LoggedIn) -> None:
    c = _create(client, editor)
    r = client.delete(
        f"/api/companies/{c['id']}/permanent", params={"confirm": "BVT"}, headers=_h(editor)
    )
    assert r.status_code == 403


def test_viewer_can_read_but_not_write(
    client: TestClient, login: Login, admin_engine: Engine
) -> None:
    editor = login("ed@buenavidatrading.com", role="editor")
    c = _create(client, editor)
    viewer = login("vi@buenavidatrading.com", role="viewer")
    assert client.get("/api/companies").status_code == 200
    assert client.get(f"/api/companies/{c['id']}").status_code == 200
    assert (
        client.post("/api/companies", json=_company(code="V1"), headers=_h(viewer)).status_code
        == 403
    )
    assert (
        client.patch(
            f"/api/companies/{c['id']}", json={"version": 1, "trade_name": "x"}, headers=_h(viewer)
        ).status_code
        == 403
    )


# --- Addresses -----------------------------------------------------------------------


def _address(**over: Any) -> dict[str, Any]:
    body = {
        "address_type": "registered",
        "line1": "Calle Mayor 1",
        "line2": "",
        "postal_code": "28001",
        "city": "Madrid",
        "region": "Madrid",
        "country_code": "es",
    }
    return {**body, **over}


def test_addresses_add_edit_remove(
    client: TestClient, editor: LoggedIn, admin_engine: Engine
) -> None:
    c = _create(client, editor)
    base = f"/api/parties/{c['id']}/addresses"
    ids = []
    for kind in ("registered", "billing", "warehouse"):
        r = client.post(base, json=_address(address_type=kind), headers=_h(editor))
        assert r.status_code == 201, r.text
        ids.append(r.json()["id"])
    first = client.get(f"/api/companies/{c['id']}").json()["addresses"][0]
    assert first["country_code"] == "ES"
    assert first["line2"] is None  # blank → null

    r = client.patch(
        f"/api/addresses/{ids[1]}",
        json={**_address(address_type="billing", city="Barcelona"), "version": 1},
        headers=_h(editor),
    )
    assert r.json()["city"] == "Barcelona"
    stale = client.patch(
        f"/api/addresses/{ids[1]}", json={**_address(), "version": 1}, headers=_h(editor)
    )
    assert stale.status_code == 409

    assert (
        client.delete(
            f"/api/addresses/{ids[2]}", params={"version": 1}, headers=_h(editor)
        ).status_code
        == 204
    )
    detail = client.get(f"/api/companies/{c['id']}").json()
    assert sorted(a["address_type"] for a in detail["addresses"]) == ["billing", "registered"]
    with admin_engine.connect() as conn:  # soft delete: the row is kept
        assert conn.execute(text("SELECT count(*) FROM mdm.address")).scalar_one() == 3
    assert [a.action for a in _audit(admin_engine, "address")] == ["create"] * 3 + [
        "update",
        "remove",
    ]


@pytest.mark.parametrize(
    "over",
    [
        {"address_type": "shipping"},  # not a company address type
        {"address_type": "home"},
        {"line1": ""},
        {"city": " "},
        {"country_code": "ZZ"},
        {"postal_code": "1" * 21},
        {"extra": "field"},
    ],
)
def test_invalid_address_is_rejected(
    client: TestClient, editor: LoggedIn, over: dict[str, Any]
) -> None:
    c = _create(client, editor)
    r = client.post(f"/api/parties/{c['id']}/addresses", json=_address(**over), headers=_h(editor))
    assert r.status_code == 422


# --- Contacts ------------------------------------------------------------------------


def test_contacts_and_single_primary(client: TestClient, editor: LoggedIn) -> None:
    c = _create(client, editor)
    base = f"/api/parties/{c['id']}/contacts"
    ana = client.post(
        base,
        json={
            "name": "Ana",
            "role_title": "CEO",
            "email": "Ana@BVT.example",
            "phone": "+34 600 000 001",
        },
        headers=_h(editor),
    ).json()
    assert ana["is_primary"] is True  # first contact
    assert ana["email"] == "ana@bvt.example"
    bob = client.post(base, json={"name": "Bob"}, headers=_h(editor)).json()
    assert bob["is_primary"] is False

    # Making Bob primary demotes Ana (and bumps her version).
    r = client.patch(
        f"/api/contacts/{bob['id']}",
        json={"version": 1, "name": "Bob", "is_primary": True},
        headers=_h(editor),
    )
    assert r.json()["is_primary"] is True
    contacts = {x["name"]: x for x in client.get(f"/api/companies/{c['id']}").json()["contacts"]}
    assert contacts["Ana"]["is_primary"] is False
    assert contacts["Ana"]["version"] == 2

    # A new contact flagged primary also takes over.
    cy = client.post(base, json={"name": "Cy", "is_primary": True}, headers=_h(editor)).json()
    primaries = [
        x for x in client.get(f"/api/companies/{c['id']}").json()["contacts"] if x["is_primary"]
    ]
    assert [p["id"] for p in primaries] == [cy["id"]]

    assert (
        client.delete(
            f"/api/contacts/{cy['id']}", params={"version": 1}, headers=_h(editor)
        ).status_code
        == 204
    )
    names = [x["name"] for x in client.get(f"/api/companies/{c['id']}").json()["contacts"]]
    assert names == ["Ana", "Bob"]


@pytest.mark.parametrize(
    "body",
    [
        {"name": ""},
        {"name": "x", "email": "not-an-email"},
        {"name": "x", "phone": "call me"},
        {"name": "x", "role_title": "x" * 101},
    ],
)
def test_invalid_contact_is_rejected(
    client: TestClient, editor: LoggedIn, body: dict[str, Any]
) -> None:
    c = _create(client, editor)
    assert (
        client.post(f"/api/parties/{c['id']}/contacts", json=body, headers=_h(editor)).status_code
        == 422
    )


def test_lookups(client: TestClient, login: Login) -> None:
    login("vi@buenavidatrading.com", role="viewer")
    countries = client.get("/api/lookups/countries").json()
    assert {"code": "ES", "name": "Spain"} in countries
    currencies = client.get("/api/lookups/currencies").json()
    assert {"code": "MXN", "name": "Mexican Peso"} in currencies


# --- Tax registration number (Company only) ------------------------------------------------


def test_tax_registration_number(
    client: TestClient, editor: LoggedIn, admin_engine: Engine
) -> None:
    c = _create(client, editor, tax_registration_number="  TRN 104965266000001 ")
    assert c["tax_registration_number"] == "TRN 104965266000001"  # free text, trimmed
    # Editing only this field still bumps the record version (optimistic locking).
    r = client.patch(
        f"/api/companies/{c['id']}",
        json={"version": 1, "tax_registration_number": "TRN-0001/A"},
        headers=_h(editor),
    )
    assert r.json()["tax_registration_number"] == "TRN-0001/A"
    assert r.json()["version"] == 2
    stale = client.patch(
        f"/api/companies/{c['id']}",
        json={"version": 1, "tax_registration_number": "x"},
        headers=_h(editor),
    )
    assert stale.status_code == 409
    cleared = client.patch(
        f"/api/companies/{c['id']}",
        json={"version": 2, "tax_registration_number": ""},
        headers=_h(editor),
    )
    assert cleared.json()["tax_registration_number"] is None  # optional
    with admin_engine.connect() as conn:
        last = conn.execute(
            text(
                "SELECT old_values, new_values FROM mdm.audit_log "
                "WHERE entity = 'company' ORDER BY id DESC LIMIT 1"
            )
        ).one()
    assert last.old_values["tax_registration_number"] == "TRN-0001/A"
    assert last.new_values["tax_registration_number"] is None


def test_tax_registration_number_length(client: TestClient, editor: LoggedIn) -> None:
    r = client.post(
        "/api/companies", json=_company(tax_registration_number="x" * 51), headers=_h(editor)
    )
    assert r.status_code == 422
