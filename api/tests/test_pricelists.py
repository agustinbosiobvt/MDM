"""Price lists inside customers/vendors: D4 duplicates, activation/expiry, versions,
line filters (category, brand, search), editing category/brand, immutable prices."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from tests.conftest import LoggedIn
from tests.import_helpers import commit, csv_bytes, h, partner, upload, validate

Login = Callable[..., LoggedIn]

HEADER = [
    "EAN",
    "ASIN",
    "Description",
    "Brand",
    "Destination country",
    "Shipping Port",
    "Cost (USD)",
    "RRP",
    "RRP Currency",
]
ROWS = [
    ["4033766024122", "B003QQ37HI", "Poly bag", "Nobby", "MX", "NLRTM", "10.50", "199", "MXN"],
    ["4033766024146", " ", "Cat toy mouse", "Nobby", "MX", "NLRTM", "2.25", "49.9", "MXN"],
    [
        "4033766024122",
        "B003QQ37HI",
        "Poly bag (again)",
        "Nobby",
        "MX",
        "NLRTM",
        "10.60",
        "199",
        "MXN",
    ],  # dup of row 2
    [
        "4033766024122",
        "B003QQ37HI",
        "Poly bag",
        "Nobby",
        "US",
        "NLRTM",
        "11.00",
        "15",
        "USD",
    ],  # other dimension: OK
    [
        "0012345678905",
        "",
        "Dog bed",
        "Trixie",
        "MX",
        "NLRTM",
        "30",
        "",
        "",
    ],  # leading zeros; no RRP
    ["", "#N/A", "No key at all", "Trixie", "MX", "NLRTM", "1", "1", "MXN"],  # rejected
    ["4033766024123", "", "Bad check digit", "", "MX", "NLRTM", "5", "9", "XXX"],  # 2 warnings
]
MAPPING: dict[str, Any] = {
    "sheet": "CSV",
    "header_row": 1,
    "data_start_row": 2,
    "fields": {
        "ean": {"col": 0},
        "asin": {"col": 1},
        "description": {"col": 2},
        "brand": {"col": 3},
    },
    "dimensions": [{"col": 4}, {"col": 5}],
    "prices": [
        {"col": 6, "price_type": "import_cost", "currency": {"mode": "fixed", "value": "USD"}},
        {"col": 7, "price_type": "rrp", "currency": {"mode": "column", "col": 8}},
    ],
}


@pytest.fixture
def editor(client: TestClient, login: Login) -> LoggedIn:
    return login("editor@buenavidatrading.com", role="editor")


def _import(
    client: TestClient, me: LoggedIn, party_id: str, rows: list[list[Any]] | None = None, **kw: Any
) -> dict[str, Any]:
    job = upload(
        client, me, party_id, "list.csv", csv_bytes([HEADER, *(rows or ROWS)]), "text/csv"
    ).json()
    report = validate(client, me, job["id"], MAPPING)
    assert report.status_code == 200, report.text
    done = commit(client, me, job["id"], **{"currency": "USD", **kw})
    assert done.status_code == 200, done.text
    return {**done.json(), "report": report.json()}


def _lines(client: TestClient, pl_id: str, **params: Any) -> dict[str, Any]:
    r = client.get(f"/api/price-lists/{pl_id}/lines", params=params)
    assert r.status_code == 200, r.text
    return dict(r.json())


def test_validation_report(client: TestClient, editor: LoggedIn) -> None:
    c = partner(client, editor, "customer", "AMZ", "MXN")
    job = upload(client, editor, c["id"], "list.csv", csv_bytes([HEADER, *ROWS]), "text/csv").json()
    report = validate(client, editor, job["id"], MAPPING).json()
    s = report["summary"]
    assert s["rows_read"] == 7
    assert s["rows_rejected"] == 1
    assert s["lines"] == 6
    assert s["duplicate_groups"] == 1
    assert s["issue_counts"] == {
        "duplicate_key": 2,
        "invalid_currency": 1,
        "invalid_ean": 1,
        "no_product_key": 1,
    }
    assert s["lines_with_warnings"] == 3
    assert {(p["price_type"], p["currency"]): p["count"] for p in s["prices"]} == {
        ("import_cost", "USD"): 6,
        ("rrp", "MXN"): 3,
        ("rrp", "USD"): 1,
    }
    assert report["issues"][0]["severity"] == "error"  # errors listed first
    assert report["issues"][0]["source_row"] == 7
    page = client.get(f"/api/imports/{job['id']}/issues", params={"severity": "warning"}).json()
    assert page["total"] == 4


def test_lines_keep_ean_as_text_and_blank_asin_empty(client: TestClient, editor: LoggedIn) -> None:
    c = partner(client, editor, "customer", "AMZ", "MXN")
    pl = _import(client, editor, c["id"])
    items = _lines(client, pl["price_list_id"], page_size=50)["items"]
    by_row = {i["source_row"]: i for i in items}
    assert by_row[6]["ean"] == "0012345678905"  # leading zeros kept
    assert by_row[3]["asin"] is None  # ' ' → empty
    assert by_row[2]["prices"] == [
        {"price_type": "import_cost", "currency": "USD", "amount": "10.5000"},
        {"price_type": "rrp", "currency": "MXN", "amount": "199.0000"},
    ]
    assert by_row[8]["issues"] == ["invalid_ean", "invalid_currency"]
    assert [p["price_type"] for p in by_row[8]["prices"]] == [
        "import_cost"
    ]  # RRP skipped: bad currency


def test_filters_category_brand_search(client: TestClient, editor: LoggedIn) -> None:
    c = partner(client, editor, "customer", "AMZ", "MXN")
    pl_id = _import(client, editor, c["id"])["price_list_id"]
    detail = client.get(f"/api/price-lists/{pl_id}").json()
    assert {f["value"]: f["count"] for f in detail["brands"]} == {"Nobby": 4, "Trixie": 1, None: 1}
    assert detail["categories"] == [{"value": None, "count": 6}]  # no category column in the file
    assert _lines(client, pl_id, brand="Trixie")["total"] == 1
    assert _lines(client, pl_id, brand="__none__")["total"] == 1
    assert _lines(client, pl_id, q="b003qq37hi")["total"] == 3  # ASIN, case-insensitive
    assert _lines(client, pl_id, q="4033766024146")["total"] == 1  # EAN
    assert _lines(client, pl_id, q="dog")["total"] == 1  # description
    assert _lines(client, pl_id, only="duplicates")["total"] == 2
    assert _lines(client, pl_id, only="warnings")["total"] == 3
    assert (
        _lines(client, pl_id, sort="description", order="desc")["items"][0]["description"]
        == "Poly bag (again)"
    )


def test_edit_category_and_brand(
    client: TestClient, editor: LoggedIn, admin_engine: Engine
) -> None:
    c = partner(client, editor, "customer", "AMZ", "MXN")
    pl_id = _import(client, editor, c["id"])["price_list_id"]
    line = _lines(client, pl_id, q="dog")["items"][0]
    r = client.patch(
        f"/api/price-list-lines/{line['id']}",
        json={"version": 1, "category": " Dog beds ", "brand": "Trixie Pet"},
        headers=h(editor),
    )
    assert r.status_code == 200, r.text
    assert r.json()["category"] == "Dog beds"
    assert r.json()["brand"] == "Trixie Pet"
    assert _lines(client, pl_id, category="Dog beds")["total"] == 1
    assert (
        client.patch(
            f"/api/price-list-lines/{line['id']}",
            json={"version": 1, "category": "x"},
            headers=h(editor),
        ).status_code
        == 409
    )
    cleared = client.patch(
        f"/api/price-list-lines/{line['id']}",
        json={"version": 2, "category": ""},
        headers=h(editor),
    )
    assert cleared.json()["category"] is None
    # Prices can't be sent, and the list shows who changed it last.
    bad = client.patch(
        f"/api/price-list-lines/{line['id']}", json={"version": 3, "prices": []}, headers=h(editor)
    )
    assert bad.status_code == 422
    detail = client.get(f"/api/price-lists/{pl_id}").json()
    assert detail["updated_by_email"] == "editor@buenavidatrading.com"
    with admin_engine.connect() as conn:
        audit = conn.execute(
            text(
                "SELECT old_values, new_values FROM mdm.audit_log WHERE entity = 'price_list_line' ORDER BY id LIMIT 1"
            )
        ).one()
    assert audit.old_values == {"category": None, "brand": "Trixie"}
    assert audit.new_values == {"category": "Dog beds", "brand": "Trixie Pet"}


def test_d4_activation_needs_duplicates_resolved(client: TestClient, editor: LoggedIn) -> None:
    c = partner(client, editor, "customer", "AMZ", "MXN")
    pl = _import(client, editor, c["id"])
    pl_id = pl["price_list_id"]
    detail = client.get(f"/api/price-lists/{pl_id}").json()
    assert detail["status"] == "draft"
    assert detail["duplicate_groups"] == 1
    r = client.post(
        f"/api/price-lists/{pl_id}/activate", json={"version": detail["version"]}, headers=h(editor)
    )
    assert r.status_code == 409
    assert "1 duplicate group" in r.json()["detail"]

    dup = next(
        i
        for i in _lines(client, pl_id, only="duplicates")["items"]
        if i["description"] == "Poly bag (again)"
    )
    assert dup["duplicate"] is True
    ex = client.patch(
        f"/api/price-list-lines/{dup['id']}",
        json={"version": 1, "is_active": False},
        headers=h(editor),
    )
    assert ex.status_code == 200
    assert client.get(f"/api/price-lists/{pl_id}").json()["duplicate_groups"] == 0
    assert _lines(client, pl_id, only="excluded")["total"] == 1
    assert _lines(client, pl_id)["total"] == 5  # excluded lines are hidden by default

    detail = client.get(f"/api/price-lists/{pl_id}").json()
    ok = client.post(
        f"/api/price-lists/{pl_id}/activate", json={"version": detail["version"]}, headers=h(editor)
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "active"
    # Once active, lines can no longer be excluded or included (category/brand still editable).
    back = client.patch(
        f"/api/price-list-lines/{dup['id']}",
        json={"version": 2, "is_active": True},
        headers=h(editor),
    )
    assert back.status_code == 409


def test_activation_expires_the_previous_list(
    client: TestClient, editor: LoggedIn, admin_engine: Engine
) -> None:
    v = partner(client, editor, "vendor", "NOBBY", "USD")
    rows = [r for r in ROWS if r[2] != "Poly bag (again)"]  # no duplicates
    first = _import(client, editor, v["id"], rows, valid_from="2026-01-01")
    second = _import(client, editor, v["id"], rows, valid_from="2026-06-01")
    other_ccy = _import(client, editor, v["id"], rows, valid_from="2026-03-01", currency="EUR")
    for pl in (first, second, other_ccy):
        version = client.get(f"/api/price-lists/{pl['price_list_id']}").json()["version"]
        r = client.post(
            f"/api/price-lists/{pl['price_list_id']}/activate",
            json={"version": version},
            headers=h(editor),
        )
        assert r.status_code == 200, r.text
    versions = {v["revision"]: v for v in client.get(f"/api/parties/{v['id']}/price-lists").json()}
    assert [*versions] == [3, 2, 1]
    assert versions[1]["status"] == "expired"
    assert versions[1]["valid_to"] == "2026-05-31"  # ends the day before the new one starts
    assert versions[2]["status"] == "active"
    assert versions[3]["status"] == "active"  # EUR list: a different currency
    assert versions[2]["imported_by_email"] == "editor@buenavidatrading.com"
    # Prices of the expired version are still there (history).
    assert _lines(client, first["price_list_id"])["total"] == 5
    # The database itself refuses two active lists for the same owner/currency/period.
    with admin_engine.begin() as conn, pytest.raises(DBAPIError, match="ex_price_list_one_active"):
        conn.execute(
            text("UPDATE mdm.price_list SET status = 'active', valid_to = NULL WHERE revision = 1")
        )


def test_active_list_past_its_end_shows_as_expired(client: TestClient, editor: LoggedIn) -> None:
    v = partner(client, editor, "vendor", "OLD", "USD")
    rows = [r for r in ROWS if r[2] != "Poly bag (again)"]
    pl = _import(client, editor, v["id"], rows, valid_from="2020-01-01", valid_to="2020-12-31")
    version = client.get(f"/api/price-lists/{pl['price_list_id']}").json()["version"]
    client.post(
        f"/api/price-lists/{pl['price_list_id']}/activate",
        json={"version": version},
        headers=h(editor),
    )
    out = client.get(f"/api/price-lists/{pl['price_list_id']}").json()
    assert out["status"] == "active"
    assert out["effective_status"] == "expired"


def test_prices_cannot_be_deleted_or_rewritten_by_the_app(app_engine: Engine) -> None:
    for table in ("price_list", "price_list_line", "price_list_line_price"):
        with app_engine.connect() as conn, pytest.raises(DBAPIError, match="permission denied"):
            conn.execute(text(f"DELETE FROM mdm.{table}"))  # noqa: S608 (fixed names)


def test_partner_with_price_lists_cannot_be_deleted_permanently(
    client: TestClient, login: Login
) -> None:
    admin = login("admin@buenavidatrading.com", role="admin")
    v = partner(client, admin, "vendor", "KEEP", "USD")
    _import(client, admin, v["id"])
    client.delete(f"/api/vendors/{v['id']}", params={"version": 1}, headers=h(admin))
    r = client.delete(
        f"/api/vendors/{v['id']}/permanent", params={"confirm": "KEEP"}, headers=h(admin)
    )
    assert r.status_code == 409
    assert "price lists" in r.json()["detail"]


def test_viewer_reads_but_cannot_import_or_edit(client: TestClient, login: Login) -> None:
    ed = login("ed@buenavidatrading.com", role="editor")
    c = partner(client, ed, "customer", "AMZ", "MXN")
    pl_id = _import(client, ed, c["id"])["price_list_id"]
    viewer = login("vi@buenavidatrading.com", role="viewer")
    assert client.get(f"/api/parties/{c['id']}/price-lists").status_code == 200
    assert _lines(client, pl_id)["total"] == 6  # nothing excluded in this list
    line = _lines(client, pl_id)["items"][0]
    assert (
        client.patch(
            f"/api/price-list-lines/{line['id']}",
            json={"version": 1, "category": "x"},
            headers=h(viewer),
        ).status_code
        == 403
    )
    assert upload(client, viewer, c["id"], "x.csv", b"EAN\n1", "text/csv").status_code == 403


def _version(client: TestClient, pl_id: str) -> int:
    return int(client.get(f"/api/price-lists/{pl_id}").json()["version"])


def test_draft_can_be_deleted_and_is_audited(
    client: TestClient, editor: LoggedIn, admin_engine: Engine
) -> None:
    v = partner(client, editor, "vendor", "DRAFTY", "USD")
    keep = _import(client, editor, v["id"])["price_list_id"]
    gone = _import(client, editor, v["id"])["price_list_id"]
    stale = client.delete(f"/api/price-lists/{gone}", params={"version": 99}, headers=h(editor))
    assert stale.status_code == 409
    r = client.delete(
        f"/api/price-lists/{gone}", params={"version": _version(client, gone)}, headers=h(editor)
    )
    assert r.status_code == 204, r.text
    # Hidden everywhere, and nothing more can be done with it.
    assert [x["id"] for x in client.get(f"/api/parties/{v['id']}/price-lists").json()] == [keep]
    assert client.get(f"/api/price-lists/{gone}").status_code == 404
    assert client.get(f"/api/price-lists/{gone}/lines").status_code == 404
    assert (
        client.post(
            f"/api/price-lists/{gone}/activate", json={"version": 2}, headers=h(editor)
        ).status_code
        == 404
    )
    assert (
        client.delete(
            f"/api/price-lists/{gone}", params={"version": 2}, headers=h(editor)
        ).status_code
        == 404
    )
    # Soft delete: the rows stay (the app can't delete price list rows), and it's audited.
    with admin_engine.connect() as conn:
        assert (
            conn.execute(
                text("SELECT is_active FROM mdm.price_list WHERE id = :i"), {"i": gone}
            ).scalar_one()
            is False
        )
        audit = conn.execute(
            text(
                "SELECT user_email, old_values, new_values FROM mdm.audit_log "
                "WHERE entity = 'price_list' AND entity_id = :i AND action = 'delete'"
            ),
            {"i": gone},
        ).one()
    assert audit.user_email == "editor@buenavidatrading.com"
    assert audit.old_values["status"] == "draft"
    assert audit.new_values == {"is_active": False}
    # A deleted draft no longer counts as "already imported"; the next revision still moves on.
    again = upload(
        client, editor, v["id"], "list.csv", csv_bytes([HEADER, *ROWS]), "text/csv"
    ).json()
    assert again["already_imported_as"] == [1]
    assert _import(client, editor, v["id"])["revision"] == 3


def test_only_a_draft_can_be_deleted(client: TestClient, login: Login) -> None:
    admin = login("admin@buenavidatrading.com", role="admin")
    v = partner(client, admin, "vendor", "ACTIVE", "USD")
    rows = [r for r in ROWS if r[2] != "Poly bag (again)"]
    first = _import(client, admin, v["id"], rows, valid_from="2026-01-01")["price_list_id"]
    second = _import(client, admin, v["id"], rows, valid_from="2026-06-01")["price_list_id"]
    for pl in (first, second):
        client.post(
            f"/api/price-lists/{pl}/activate",
            json={"version": _version(client, pl)},
            headers=h(admin),
        )
    statuses = {pl: client.get(f"/api/price-lists/{pl}").json()["status"] for pl in (first, second)}
    assert statuses == {first: "expired", second: "active"}
    for pl in (first, second):  # not even an Admin
        r = client.delete(
            f"/api/price-lists/{pl}", params={"version": _version(client, pl)}, headers=h(admin)
        )
        assert r.status_code == 409
        assert "draft" in r.json()["detail"]


def test_viewer_cannot_delete_a_draft(client: TestClient, login: Login) -> None:
    ed = login("ed@buenavidatrading.com", role="editor")
    c = partner(client, ed, "customer", "AMZD", "MXN")
    pl_id = _import(client, ed, c["id"])["price_list_id"]
    viewer = login("vi@buenavidatrading.com", role="viewer")
    r = client.delete(f"/api/price-lists/{pl_id}", params={"version": 1}, headers=h(viewer))
    assert r.status_code == 403
    assert client.get(f"/api/price-lists/{pl_id}").status_code == 200
