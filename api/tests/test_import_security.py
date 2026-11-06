"""Upload checks (size, extension, content, MIME), temp-file handling, ownership, layout
drift against a saved template, and rate limiting."""

import io
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from tests.conftest import LoggedIn
from tests.import_helpers import XLSX, commit, csv_bytes, h, partner, upload, validate

Login = Callable[..., LoggedIn]
CSV_OK = csv_bytes([["EAN", "Description", "Price USD"], ["4033766024122", "Bag", "10.5"]])


@pytest.fixture
def editor(client: TestClient, login: Login) -> LoggedIn:
    return login("editor@buenavidatrading.com", role="editor")


@pytest.fixture
def vendor(client: TestClient, editor: LoggedIn) -> str:
    return str(partner(client, editor, "vendor", "V1", "USD")["id"])


def _xlsx_like(extra: dict[str, bytes] | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("xl/workbook.xml", "<workbook/>")
        for name, data in (extra or {}).items():
            z.writestr(name, data)
    return buf.getvalue()


@pytest.mark.parametrize(
    ("name", "content", "mime", "message"),
    [
        ("prices.xlsm", b"x", XLSX, "Macro-enabled workbooks (.xlsm)"),
        ("prices.xls", b"x", "application/vnd.ms-excel", "Old Excel files (.xls)"),
        ("prices.pdf", b"%PDF", "application/pdf", "Only .xlsx and .csv"),
        ("prices.xlsx", b"not a zip at all", XLSX, "not a valid .xlsx"),
        ("prices.xlsx", _xlsx_like({"xl/vbaProject.bin": b"macro"}), XLSX, "Macro-enabled"),
        ("prices.csv", b"EAN,Price\x00\x01", "text/csv", "doesn't look like a text"),
        ("prices.csv", CSV_OK, "application/x-msdownload", "doesn't match a .csv"),
        ("prices.csv", b"", "text/csv", "empty"),
    ],
)
def test_bad_uploads_are_refused(
    client: TestClient,
    editor: LoggedIn,
    vendor: str,
    name: str,
    content: bytes,
    mime: str,
    message: str,
) -> None:
    r = upload(client, editor, vendor, name, content, mime)
    assert r.status_code == 422, r.text
    assert message in r.json()["detail"]
    assert not list(get_settings().upload_dir.glob("*.upload"))  # nothing left behind


def test_size_limit(client: TestClient, editor: LoggedIn, vendor: str) -> None:
    settings = get_settings()
    original = settings.upload_max_bytes
    settings.upload_max_bytes = 1024
    try:
        r = upload(client, editor, vendor, "big.csv", b"EAN,Price\n" + b"1,2\n" * 1000, "text/csv")
    finally:
        settings.upload_max_bytes = original
    assert r.status_code == 413
    assert not list(settings.upload_dir.glob("*.upload"))


def _files() -> list[Path]:
    return list(get_settings().upload_dir.glob("*.upload"))


def test_temp_file_random_name_and_deleted_after_commit(
    client: TestClient, editor: LoggedIn, vendor: str
) -> None:
    job = upload(client, editor, vendor, "../../etc/passwd.csv", CSV_OK, "text/csv").json()
    [stored] = _files()
    assert (
        stored.parent == get_settings().upload_dir
    )  # never under a web root, never the client's name
    assert "passwd" not in stored.name
    assert job["original_name"] == "passwd.csv"  # path parts stripped
    mapping = {
        "sheet": "CSV", "header_row": 1, "data_start_row": 2,
        "fields": {"ean": {"col": 0}, "description": {"col": 1}},
        "prices": [{"col": 2, "price_type": "purchase", "currency": {"mode": "fixed", "value": "USD"}}],
    }  # fmt: skip
    assert validate(client, editor, job["id"], mapping).status_code == 200
    assert commit(client, editor, job["id"], currency="USD").status_code == 200
    assert _files() == []


def test_cancel_deletes_the_file(client: TestClient, editor: LoggedIn, vendor: str) -> None:
    job = upload(client, editor, vendor, "p.csv", CSV_OK, "text/csv").json()
    assert len(_files()) == 1
    assert client.delete(f"/api/imports/{job['id']}", headers=h(editor)).status_code == 204
    assert _files() == []
    assert client.get(f"/api/imports/{job['id']}/preview").status_code == 409


def test_an_import_belongs_to_whoever_started_it(client: TestClient, login: Login) -> None:
    alice = login("alice@buenavidatrading.com", role="editor")
    v = partner(client, alice, "vendor", "V9", "USD")
    job = upload(client, alice, v["id"], "p.csv", CSV_OK, "text/csv").json()
    login("bob@buenavidatrading.com", role="editor")
    assert client.get(f"/api/imports/{job['id']}/preview").status_code == 404
    login("boss@buenavidatrading.com", role="admin")
    assert client.get(f"/api/imports/{job['id']}/preview").status_code == 200


def test_company_cannot_have_price_lists(client: TestClient, editor: LoggedIn) -> None:
    c = client.post(
        "/api/companies",
        json={"code": "BVT", "legal_name": "BVT", "country_code": "ES"},
        headers=h(editor),
    ).json()
    assert upload(client, editor, c["id"], "p.csv", CSV_OK, "text/csv").status_code == 404


def test_layout_change_is_detected(client: TestClient, editor: LoggedIn, vendor: str) -> None:
    job = upload(client, editor, vendor, "p.csv", CSV_OK, "text/csv").json()
    stale_mapping = {
        "sheet": "CSV", "header_row": 1, "data_start_row": 2,
        "fields": {"ean": {"col": 0, "header": "EAN"}, "description": {"col": 1, "header": "Item Name"}},
        "prices": [{"col": 2, "header": "Price USD", "price_type": "purchase", "currency": {"mode": "fixed", "value": "USD"}}],
    }  # fmt: skip
    r = validate(client, editor, job["id"], stale_mapping)
    assert r.status_code == 422
    assert "column B: expected 'Item Name', the file has 'Description'" in r.json()["detail"]


@pytest.mark.parametrize(
    ("mapping_patch", "message"),
    [
        ({"fields": {"description": {"col": 1}}}, "product key"),
        ({"prices": []}, "at least 1"),
        ({"header_row": 3, "data_start_row": 2}, "after the header"),
    ],
)
def test_incomplete_mapping_is_refused(
    client: TestClient,
    editor: LoggedIn,
    vendor: str,
    mapping_patch: dict[str, object],
    message: str,
) -> None:
    job = upload(client, editor, vendor, "p.csv", CSV_OK, "text/csv").json()
    mapping = {
        "sheet": "CSV", "header_row": 1, "data_start_row": 2, "fields": {"ean": {"col": 0}},
        "prices": [{"col": 2, "price_type": "purchase", "currency": {"mode": "fixed", "value": "USD"}}],
        **mapping_patch,
    }  # fmt: skip
    r = validate(client, editor, job["id"], mapping)
    assert r.status_code == 422
    assert message in r.text


def test_currency_must_be_chosen(client: TestClient, editor: LoggedIn, vendor: str) -> None:
    job = upload(client, editor, vendor, "p.csv", CSV_OK, "text/csv").json()
    mapping = {
        "sheet": "CSV", "header_row": 1, "data_start_row": 2, "fields": {"ean": {"col": 0}},
        "prices": [{"col": 2, "price_type": "purchase", "currency": {"mode": "fixed"}}],
    }  # fmt: skip
    r = validate(client, editor, job["id"], mapping)
    assert r.status_code == 422
    assert "choose the currency" in r.text


def test_import_endpoints_are_rate_limited(
    client: TestClient, editor: LoggedIn, vendor: str
) -> None:
    settings = get_settings()
    original = settings.import_rate_limit
    settings.import_rate_limit = "2/minute"
    try:
        codes = [
            upload(client, editor, vendor, "p.csv", CSV_OK, "text/csv").status_code
            for _ in range(3)
        ]
    finally:
        settings.import_rate_limit = original
    assert codes == [201, 201, 429]


def test_import_requires_the_english_description_when_available(
    client: TestClient, editor: LoggedIn, vendor: str
) -> None:
    content = csv_bytes(
        [
            ["EAN", "Description ES", "Description EN", "Price USD"],
            ["5415245053400", "Anillo metalico", "Metal ring", "1.25"],
        ]
    )
    job = upload(client, editor, vendor, "bilingual.csv", content, "text/csv").json()
    preview = client.get(f"/api/imports/{job['id']}/preview").json()
    assert preview["suggested_mapping"]["fields"]["description"]["col"] == 2
    mapping: dict[str, Any] = {
        "sheet": "CSV",
        "header_row": 1,
        "data_start_row": 2,
        "fields": {"ean": {"col": 0}, "description": {"col": 1}},
        "prices": [
            {"col": 3, "price_type": "purchase", "currency": {"mode": "fixed", "value": "USD"}}
        ],
    }
    wrong = validate(client, editor, job["id"], mapping)
    assert wrong.status_code == 422
    assert "English description column" in wrong.json()["detail"]
    mapping["fields"]["description"]["col"] = 2
    assert validate(client, editor, job["id"], mapping).status_code == 200
    done = commit(client, editor, job["id"], currency="USD")
    assert done.status_code == 200, done.text
    pl_id = done.json()["price_list_id"]
    saved = client.get(f"/api/price-lists/{pl_id}/lines").json()["items"]
    assert saved[0]["description"] == "Metal ring"
