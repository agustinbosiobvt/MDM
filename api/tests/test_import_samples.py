"""Both real sample files, end to end through the API and *saved mapping templates*:
row counts, EAN normalisation, blank ASINs, the currency of every price, no floats in money.

The samples are customer data and not committed (samples/ is git-ignored); without them
these tests are skipped with a clear reason.
"""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from tests.conftest import LoggedIn
from tests.import_helpers import (
    AMAZON,
    NOBBY,
    commit,
    confirmed_mapping,
    h,
    partner,
    upload_file,
    validate,
)

pytestmark = pytest.mark.skipif(
    not (AMAZON.exists() and NOBBY.exists()), reason="sample files not present in ./samples"
)
Login = Callable[..., LoggedIn]
ROWS = 7515


@pytest.fixture
def editor(client: TestClient, login: Login) -> LoggedIn:
    return login("editor@buenavidatrading.com", role="editor")


def _prices(engine: Engine, pl_id: str) -> dict[tuple[str, str], int]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT p.price_type, p.currency, count(*) FROM mdm.price_list_line_price p "
                "JOIN mdm.price_list_line l ON l.id = p.line_id WHERE l.price_list_id = :id "
                "GROUP BY 1, 2"
            ),
            {"id": pl_id},
        ).all()
    return {(t, c): n for t, c, n in rows}


def _import(
    client: TestClient, me: LoggedIn, party_id: str, path: Any, fixed: str | None, **commit_kw: Any
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    job = upload_file(client, me, party_id, path)
    prev = client.get(
        f"/api/imports/{job['id']}/preview", params={"sheet": job["suggested_sheet"]}
    ).json()
    mapping = confirmed_mapping(prev, fixed)
    report = validate(client, me, job["id"], mapping)
    assert report.status_code == 200, report.text
    done = commit(client, me, job["id"], **commit_kw)
    assert done.status_code == 200, done.text
    return prev, report.json(), done.json()


def test_amazon_sample(client: TestClient, editor: LoggedIn, admin_engine: Engine) -> None:
    amz = partner(client, editor, "customer", "AMZ-MX", "MXN")
    prev, report, done = _import(
        client, editor, amz["id"], AMAZON, None,
        name="Amazon MX quote", currency="MXN", save_template={"name": "Amazon quote sheet"},
    )  # fmt: skip

    # Sheet, header row and data start detected (title, flags, column numbers, instructions skipped).
    assert prev["sheet"] == "ALL"
    assert prev["header_row"] == 4
    assert prev["data_start_row"] == 7
    sug = prev["suggested_mapping"]
    assert sug["fields"]["brand"]["header"] == "Brand Name"
    assert "category" not in sug["fields"]  # the file has no category column
    assert [d["header"] for d in sug["dimensions"]] == ["Destination country", "Shipping Port"]
    rrp = next(p for p in sug["prices"] if p["price_type"] == "rrp")
    assert rrp["currency"]["mode"] == "column"  # currency lives in another column (W)
    assert rrp["currency"]["header"] == "Recommended Retail Price  Currency"

    s = report["summary"]
    assert s["rows_read"] == ROWS
    assert s["lines"] == ROWS
    assert s["rows_rejected"] == 0
    assert s["lines_with_warnings"] == 1
    assert s["issue_counts"] == {"invalid_ean": 1}  # 43917996264 (11 digits)
    assert s["duplicate_groups"] == 0
    assert done["lines"] == ROWS
    assert done["prices"] == 2 * ROWS

    assert _prices(admin_engine, done["price_list_id"]) == {
        ("import_cost", "USD"): ROWS,
        ("rrp", "MXN"): ROWS,
    }
    with admin_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT count(*) FILTER (WHERE asin IS NULL) AS blank_asin, "
                "count(*) FILTER (WHERE ean LIKE '%.%') AS dotted_ean, "
                "count(*) FILTER (WHERE brand = 'Nobby') AS nobby, "
                "count(*) FILTER (WHERE category IS NOT NULL) AS with_category "
                "FROM mdm.price_list_line WHERE price_list_id = :id"
            ),
            {"id": done["price_list_id"]},
        ).one()
        first = conn.execute(
            text(
                "SELECT l.ean, l.asin, p.price_type, p.amount, p.currency FROM mdm.price_list_line l "
                "JOIN mdm.price_list_line_price p ON p.line_id = l.id "
                "WHERE l.price_list_id = :id AND l.source_row = 7 ORDER BY p.price_type"
            ),
            {"id": done["price_list_id"]},
        ).all()
    assert row.blank_asin == 1970  # ' ' in the file → empty, not an issue
    assert row.dotted_ean == 0
    assert row.nobby == ROWS  # brand mapped from "Brand Name"
    assert row.with_category == 0  # no category column → empty, editable later
    assert [(r.ean, r.asin, r.price_type, str(r.amount), r.currency) for r in first] == [
        ("4033766024122", "B003QQ37HI", "import_cost", "78.1126", "USD"),
        ("4033766024122", "B003QQ37HI", "rrp", "3728.8200", "MXN"),
    ]


def test_nobby_sample(client: TestClient, editor: LoggedIn, admin_engine: Engine) -> None:
    nobby = partner(client, editor, "vendor", "NOBBY", "EUR")
    prev, report, done = _import(
        client, editor, nobby["id"], NOBBY, None,  # all currencies come from the headers
        name="Nobby export 2025", currency="EUR", valid_from="2025-08-15",
        save_template={"name": "Nobby export list"},
    )  # fmt: skip
    assert prev["header_row"] == 7
    assert prev["data_start_row"] == 8
    assert prev["suggested_valid_from"] == "2025-08-15"  # from "valid from 15.08.2025"
    assert ["Nobby Pet Shop GmbH", "Concept", "Amount"] in prev["metadata"]
    # Duplicate header names: mapping by column index, first occurrence suggested.
    assert prev["suggested_mapping"]["fields"]["asin"]["col"] == 2
    assert prev["suggested_mapping"]["fields"]["ean"]["col"] == 1
    # Margin columns are not prices.
    assert all(
        "margin" not in (p["header"] or "").lower() for p in prev["suggested_mapping"]["prices"]
    )

    s = report["summary"]
    assert s["lines"] == ROWS
    assert s["rows_rejected"] == 0
    assert s["issue_counts"] == {"invalid_ean": 1}
    assert done["prices"] == 45061
    assert _prices(admin_engine, done["price_list_id"]) == {
        ("purchase", "EUR"): 7486,  # 29 rows have no purchase price
        ("rrp", "EUR"): ROWS,
        ("rrp_ex_vat", "MXN"): ROWS,
        ("rrp", "MXN"): ROWS,
        ("retailer_cost", "MXN"): ROWS,
        ("retailer_cost", "USD"): ROWS,
    }
    with admin_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT count(*) FILTER (WHERE asin IS NULL) AS blank_asin, "
                "count(*) FILTER (WHERE asin ~ '^[0-9]{10}$') AS numeric_asin, "
                "count(*) FILTER (WHERE vendor_sku LIKE '%.0') AS dotted_sku, "
                "count(*) FILTER (WHERE country_of_origin IS NOT NULL) AS coo "
                "FROM mdm.price_list_line WHERE price_list_id = :id"
            ),
            {"id": done["price_list_id"]},
        ).one()
        meta = conn.execute(
            text("SELECT source_metadata FROM mdm.price_list WHERE id = :id"),
            {"id": done["price_list_id"]},
        ).scalar_one()
        rates = conn.execute(text("SELECT count(*) FROM mdm.exchange_rate")).scalar_one()
    assert row.blank_asin == 1970
    assert row.numeric_asin == 60  # ISBN-style ASINs stored without '.0'
    assert row.dotted_sku == 0
    assert row.coo == ROWS - 33
    assert ["EUR to MX", "21.43"] in [r[1:] for r in meta["rows_above_header"] if len(r) == 3]
    assert rates == 0  # FX rates in the file are kept as metadata, never imported


def test_next_month_uses_the_saved_template(client: TestClient, editor: LoggedIn) -> None:
    amz = partner(client, editor, "customer", "AMZ-MX", "MXN")
    _, _, first = _import(
        client,
        editor,
        amz["id"],
        AMAZON,
        None,
        currency="MXN",
        save_template={"name": "Amazon quote sheet"},
    )
    job = upload_file(client, editor, amz["id"], AMAZON)
    assert job["already_imported_as"] == [first["revision"]]
    [tpl] = job["templates"]
    assert tpl["name"] == "Amazon quote sheet"
    assert tpl["matches"] is True
    assert job["suggested_sheet"] == "ALL"
    report = validate(client, editor, job["id"], tpl["mapping"], template_id=tpl["id"])
    assert report.status_code == 200, report.text
    assert report.json()["summary"]["lines"] == ROWS
    second = commit(client, editor, job["id"], currency="MXN").json()
    assert second["revision"] == first["revision"] + 1  # a new version; history kept
    assert second["template_id"] == tpl["id"]
    versions = client.get(f"/api/parties/{amz['id']}/price-lists").json()
    assert [v["revision"] for v in versions] == [2, 1]


def test_money_columns_are_numeric_18_4(admin_engine: Engine) -> None:
    with admin_engine.connect() as conn:
        cols = conn.execute(
            text(
                "SELECT table_name, column_name, data_type, numeric_precision, numeric_scale "
                "FROM information_schema.columns WHERE table_schema = 'mdm' "
                "AND (column_name IN ('amount') OR data_type IN ('real', 'double precision'))"
            )
        ).all()
    assert [tuple(c) for c in cols] == [("price_list_line_price", "amount", "numeric", 18, 4)]


def test_api_returns_money_as_text(client: TestClient, editor: LoggedIn) -> None:
    amz = partner(client, editor, "customer", "AMZ-MX", "MXN")
    _, _, done = _import(client, editor, amz["id"], AMAZON, None, currency="MXN")
    page = client.get(
        f"/api/price-lists/{done['price_list_id']}/lines", params={"page_size": 5}
    ).json()
    amounts = [p["amount"] for line in page["items"] for p in line["prices"]]
    assert amounts
    assert all(
        isinstance(a, str) and a.count(".") == 1 and len(a.split(".")[1]) == 4 for a in amounts
    )
    assert h(editor)  # (keeps the helper import used)
