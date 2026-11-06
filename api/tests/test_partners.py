"""Customers and vendors: same patterns as Company, plus business status, trading terms,
Amazon vendor codes (customers), lead time / MOQ / contact roles (vendors). No Tax ID."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from tests.conftest import LoggedIn

Login = Callable[..., LoggedIn]
KINDS = ("customers", "vendors")


@pytest.fixture
def editor(client: TestClient, login: Login) -> LoggedIn:
    return login("editor@buenavidatrading.com", role="editor")


def _h(me: LoggedIn) -> dict[str, str]:
    return {"X-CSRF-Token": me.csrf}


def _body(kind: str, **over: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "code": "AMZ-MX" if kind == "customers" else "NOBBY",
        "legal_name": "Servicios Comerciales Amazon México"
        if kind == "customers"
        else "Nobby Pet Shop GmbH",
        "country_code": "MX" if kind == "customers" else "DE",
        "default_currency": "MXN" if kind == "customers" else "EUR",
    }
    return {**body, **over}


def _create(client: TestClient, me: LoggedIn, kind: str, **over: Any) -> dict[str, Any]:
    r = client.post(f"/api/{kind}", json=_body(kind, **over), headers=_h(me))
    assert r.status_code == 201, r.text
    return dict(r.json())


# --- Identity, status, terms ------------------------------------------------------------


@pytest.mark.parametrize("kind", KINDS)
def test_add_and_view_minimal(client: TestClient, editor: LoggedIn, kind: str) -> None:
    c = _create(client, editor, kind)
    assert c["status"] == "active"
    assert "tax_id" not in c  # removed from the spec
    assert c["default_currency"] == ("MXN" if kind == "customers" else "EUR")  # kept
    assert c["payment_term_code"] is None
    assert c["addresses"] == []
    assert c["contacts"] == []
    got = client.get(f"/api/{kind}/{c['id']}").json()
    assert got["code"] == c["code"]


def test_customer_full_record(client: TestClient, editor: LoggedIn) -> None:
    c = _create(
        client,
        editor,
        "customers",
        trade_name="Amazon MX",
        status="on_hold",
        payment_term_code="net60",
        incoterm_code="ddp",
    )
    assert c["payment_term_code"] == "NET60"
    assert c["incoterm_code"] == "DDP"
    assert c["status"] == "on_hold"
    assert c["vendor_codes"] == []
    assert "eori" not in c  # customers have no EORI field


def test_vendor_full_record(client: TestClient, editor: LoggedIn) -> None:
    v = _create(
        client,
        editor,
        "vendors",
        eori="de123456789000",
        payment_term_code="NET30",
        incoterm_code="EXW",
        lead_time_days=45,
        moq=100,
    )
    assert v["eori"] == "DE123456789000"
    assert v["lead_time_days"] == 45
    assert v["moq"] == 100
    assert "vendor_codes" not in v


@pytest.mark.parametrize(
    ("kind", "over", "field"),
    [
        ("customers", {"status": "deleted"}, "status"),
        ("customers", {"payment_term_code": "net 30!"}, "payment_term_code"),
        ("customers", {"eori": "ES123"}, "eori"),  # not a customer field
        ("vendors", {"lead_time_days": -1}, "lead_time_days"),
        ("vendors", {"lead_time_days": 731}, "lead_time_days"),
        ("vendors", {"moq": 0}, "moq"),
        ("vendors", {"tax_id": "DE123"}, "tax_id"),  # no Tax ID any more
        ("customers", {"tax_id": "ANE140618P37"}, "tax_id"),
    ],
)
def test_invalid_fields_are_rejected(
    client: TestClient, editor: LoggedIn, kind: str, over: dict[str, Any], field: str
) -> None:
    r = client.post(f"/api/{kind}", json=_body(kind, **over), headers=_h(editor))
    assert r.status_code == 422
    assert any(e["loc"][-1] == field or e["loc"][1] == field for e in r.json()["errors"])


@pytest.mark.parametrize(
    ("over", "message"),
    [
        ({"payment_term_code": "NET999"}, "Unknown payment term NET999"),
        ({"incoterm_code": "XYZ"}, "Unknown Incoterm XYZ"),
        ({"country_code": "ZZ"}, "Unknown country code ZZ"),
    ],
)
def test_unknown_lookup_codes(
    client: TestClient, editor: LoggedIn, over: dict[str, Any], message: str
) -> None:
    r = client.post("/api/customers", json=_body("customers", **over), headers=_h(editor))
    assert r.status_code == 422
    assert r.json()["detail"] == message


# --- Codes ----------------------------------------------------------------------------------


def test_codes_are_unique_across_all_parties(client: TestClient, editor: LoggedIn) -> None:
    _create(client, editor, "customers", code="SAME")
    r = client.post("/api/vendors", json=_body("vendors", code="SAME"), headers=_h(editor))
    assert r.status_code == 409


# --- List -----------------------------------------------------------------------------------


def test_list_search_filter_sort(client: TestClient, editor: LoggedIn) -> None:
    _create(client, editor, "customers", code="AMZ-MX", legal_name="Amazon Mexico", status="active")
    _create(client, editor, "customers", code="AMZ-US", legal_name="Amazon US", status="on_hold")
    _create(client, editor, "customers", code="WMT", legal_name="Walmart", status="blocked")
    base = "/api/customers"
    assert client.get(base).json()["total"] == 3
    assert client.get(base, params={"status": "blocked"}).json()["items"][0]["code"] == "WMT"
    assert client.get(base, params={"q": "amazon"}).json()["total"] == 2
    desc = client.get(base, params={"sort": "status", "order": "desc"}).json()["items"]
    assert [c["status"] for c in desc] == ["on_hold", "blocked", "active"]
    assert client.get(base, params={"status": "nope"}).status_code == 422


# --- Edit / status / remove / permanent ----------------------------------------------------


@pytest.mark.parametrize("kind", KINDS)
def test_edit_status_and_terms_with_locking(
    client: TestClient, editor: LoggedIn, admin_engine: Engine, kind: str
) -> None:
    c = _create(client, editor, kind)
    r = client.patch(
        f"/api/{kind}/{c['id']}",
        json={"version": 1, "status": "blocked", "incoterm_code": "FOB"},
        headers=_h(editor),
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "blocked"
    assert r.json()["version"] == 2  # a status-only change still bumps the record version
    stale = client.patch(
        f"/api/{kind}/{c['id']}", json={"version": 1, "status": "active"}, headers=_h(editor)
    )
    assert stale.status_code == 409
    # Clearing an optional term is allowed; clearing a required field is not.
    cleared = client.patch(
        f"/api/{kind}/{c['id']}", json={"version": 2, "incoterm_code": None}, headers=_h(editor)
    )
    assert cleared.json()["incoterm_code"] is None
    bad = client.patch(
        f"/api/{kind}/{c['id']}", json={"version": 3, "status": None}, headers=_h(editor)
    )
    assert bad.status_code == 422
    with admin_engine.connect() as conn:
        actions = (
            conn.execute(
                text("SELECT action FROM mdm.audit_log WHERE entity = :e ORDER BY id"),
                {"e": kind[:-1]},
            )
            .scalars()
            .all()
        )
    assert actions == ["create", "update", "update"]


@pytest.mark.parametrize("kind", KINDS)
def test_remove_reactivate_and_permanent_delete(
    client: TestClient, login: Login, admin_engine: Engine, kind: str
) -> None:
    admin = login("admin@buenavidatrading.com", role="admin")
    c = _create(client, admin, kind)
    url = f"/api/{kind}/{c['id']}"
    assert (
        client.delete(
            f"{url}/permanent", params={"confirm": c["code"]}, headers=_h(admin)
        ).status_code
        == 409
    )
    assert client.delete(url, params={"version": 1}, headers=_h(admin)).json()["is_active"] is False
    assert client.get(f"/api/{kind}").json()["total"] == 0
    assert client.get(f"/api/{kind}", params={"active": False}).json()["total"] == 1
    back = client.patch(url, json={"version": 2, "is_active": True}, headers=_h(admin))
    assert back.json()["is_active"] is True
    client.delete(url, params={"version": 3}, headers=_h(admin))
    assert (
        client.delete(
            f"{url}/permanent", params={"confirm": "WRONG"}, headers=_h(admin)
        ).status_code
        == 422
    )
    assert (
        client.delete(
            f"{url}/permanent", params={"confirm": c["code"]}, headers=_h(admin)
        ).status_code
        == 204
    )
    assert client.get(url).status_code == 404
    with admin_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM mdm.party")).scalar_one() == 0


@pytest.mark.parametrize("kind", KINDS)
def test_editor_cannot_delete_permanently_viewer_cannot_write(
    client: TestClient, login: Login, kind: str
) -> None:
    editor = login("ed@buenavidatrading.com", role="editor")
    c = _create(client, editor, kind)
    client.delete(f"/api/{kind}/{c['id']}", params={"version": 1}, headers=_h(editor))
    assert (
        client.delete(
            f"/api/{kind}/{c['id']}/permanent", params={"confirm": c["code"]}, headers=_h(editor)
        ).status_code
        == 403
    )
    viewer = login("vi@buenavidatrading.com", role="viewer")
    assert client.get(f"/api/{kind}/{c['id']}").status_code == 200
    assert (
        client.post(f"/api/{kind}", json=_body(kind, code="X1"), headers=_h(viewer)).status_code
        == 403
    )


# --- Addresses and contacts per kind ------------------------------------------------------


@pytest.mark.parametrize(
    ("kind", "allowed", "refused"),
    [
        ("customers", ["billing", "shipping", "shipping"], ["factory", "registered"]),
        ("vendors", ["billing", "pickup", "factory"], ["shipping", "warehouse"]),
    ],
)
def test_address_types_per_kind(
    client: TestClient, editor: LoggedIn, kind: str, allowed: list[str], refused: list[str]
) -> None:
    c = _create(client, editor, kind)
    url = f"/api/parties/{c['id']}/addresses"
    addr = {"line1": "Av. Insurgentes 1", "city": "CDMX", "country_code": "MX"}
    for t in allowed:  # several of the same type are fine (e.g. two ship-to addresses)
        assert (
            client.post(url, json={**addr, "address_type": t}, headers=_h(editor)).status_code
            == 201
        )
    for t in refused:
        assert (
            client.post(url, json={**addr, "address_type": t}, headers=_h(editor)).status_code
            == 422
        )
    assert len(client.get(f"/api/{kind}/{c['id']}").json()["addresses"]) == len(allowed)


def test_vendor_contact_roles(client: TestClient, editor: LoggedIn) -> None:
    v = _create(client, editor, "vendors")
    url = f"/api/parties/{v['id']}/contacts"
    for role in ("sales", "logistics", "quality", "other"):
        r = client.post(url, json={"name": f"P {role}", "contact_role": role}, headers=_h(editor))
        assert r.status_code == 201
        assert r.json()["contact_role"] == role
    assert (
        client.post(url, json={"name": "X", "contact_role": "ceo"}, headers=_h(editor)).status_code
        == 422
    )
    c = _create(client, editor, "customers")
    r = client.post(
        f"/api/parties/{c['id']}/contacts",
        json={"name": "Y", "contact_role": "sales"},
        headers=_h(editor),
    )
    assert r.status_code == 422  # roles are a vendor thing
    ok = client.post(f"/api/parties/{c['id']}/contacts", json={"name": "Y"}, headers=_h(editor))
    assert ok.json()["contact_role"] is None


# --- Amazon vendor codes ----------------------------------------------------------------------


def test_vendor_codes_add_edit_remove(
    client: TestClient, editor: LoggedIn, admin_engine: Engine
) -> None:
    c = _create(client, editor, "customers")
    url = f"/api/customers/{c['id']}/vendor-codes"
    a = client.post(
        url,
        json={
            "parent_code": "bvt0a",
            "child_code": " bvt0b ",
            "destination_country": "mx",
        },
        headers=_h(editor),
    )
    assert a.status_code == 201, a.text
    assert a.json()["parent_code"] == "BVT0A"
    assert a.json()["child_code"] == "BVT0B"
    assert a.json()["destination_country"] == "MX"
    b = client.post(
        url, json={"parent_code": "BVT0A", "child_code": "BVT0C"}, headers=_h(editor)
    ).json()
    assert len(client.get(f"/api/customers/{c['id']}").json()["vendor_codes"]) == 2

    r = client.patch(
        f"/api/vendor-codes/{b['id']}",
        json={
            "version": 1,
            "parent_code": "BVT0A",
            "child_code": "BVT0D",
            "destination_country": "US",
        },
        headers=_h(editor),
    )
    assert r.json()["child_code"] == "BVT0D"
    assert (
        client.patch(
            f"/api/vendor-codes/{b['id']}",
            json={"version": 1, "parent_code": "BVT0A", "child_code": "BVT0E"},
            headers=_h(editor),
        ).status_code
        == 409
    )

    assert (
        client.delete(
            f"/api/vendor-codes/{a.json()['id']}", params={"version": 1}, headers=_h(editor)
        ).status_code
        == 204
    )
    codes = client.get(f"/api/customers/{c['id']}").json()["vendor_codes"]
    assert [x["child_code"] for x in codes] == ["BVT0D"]
    with admin_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM mdm.customer_vendor_code")).scalar_one() == 2


def test_vendor_code_pair_belongs_to_one_customer(client: TestClient, editor: LoggedIn) -> None:
    one = _create(client, editor, "customers", code="C1")
    two = _create(client, editor, "customers", code="C2")
    pair = {"parent_code": "P1", "child_code": "C1"}
    first = client.post(f"/api/customers/{one['id']}/vendor-codes", json=pair, headers=_h(editor))
    assert first.status_code == 201
    dup = client.post(f"/api/customers/{two['id']}/vendor-codes", json=pair, headers=_h(editor))
    assert dup.status_code == 409
    assert dup.json()["detail"] == "This parent/child vendor code pair is already assigned"
    # Once removed, the pair can be reused.
    client.delete(
        f"/api/vendor-codes/{first.json()['id']}", params={"version": 1}, headers=_h(editor)
    )
    assert (
        client.post(
            f"/api/customers/{two['id']}/vendor-codes", json=pair, headers=_h(editor)
        ).status_code
        == 201
    )


@pytest.mark.parametrize(
    "body",
    [
        {"parent_code": "A", "child_code": "BB"},  # too short
        {"parent_code": "AA!", "child_code": "BB"},
        {"parent_code": "AA", "child_code": "BB", "destination_country": "ZZ"},
        {"parent_code": "AA", "child_code": "BB", "description": "x"},  # field removed
        {"parent_code": "AA"},
    ],
)
def test_invalid_vendor_codes(client: TestClient, editor: LoggedIn, body: dict[str, Any]) -> None:
    c = _create(client, editor, "customers")
    assert (
        client.post(
            f"/api/customers/{c['id']}/vendor-codes", json=body, headers=_h(editor)
        ).status_code
        == 422
    )


def test_vendor_codes_need_an_active_customer(client: TestClient, editor: LoggedIn) -> None:
    c = _create(client, editor, "customers")
    client.delete(f"/api/customers/{c['id']}", params={"version": 1}, headers=_h(editor))
    r = client.post(
        f"/api/customers/{c['id']}/vendor-codes",
        json={"parent_code": "AA", "child_code": "BB"},
        headers=_h(editor),
    )
    assert r.status_code == 409


@pytest.mark.parametrize("kind", KINDS)
def test_tax_registration_number_is_company_only(
    client: TestClient, editor: LoggedIn, kind: str
) -> None:
    body = _body(kind, tax_registration_number="TRN 1")
    r = client.post(f"/api/{kind}", json=body, headers=_h(editor))
    assert r.status_code == 422
    assert r.json()["errors"][0]["type"] == "extra_forbidden"
