"""Drive the import wizard through the API, like the browser does."""

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.config import REPO_ROOT
from tests.conftest import LoggedIn

SAMPLES = REPO_ROOT / "samples"
AMAZON = SAMPLES / "Client prices AmzMx.xlsx"
NOBBY = SAMPLES / "NOBBY_PLS_GEN_Pl-0-2025-Englisch-With-Details_2026-09-12_v01.xlsx"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def h(me: LoggedIn) -> dict[str, str]:
    return {"X-CSRF-Token": me.csrf}


def partner(
    client: TestClient, me: LoggedIn, kind: str, code: str, currency: str
) -> dict[str, Any]:
    r = client.post(
        f"/api/{kind}s",
        json={
            "code": code,
            "legal_name": f"{code} legal",
            "country_code": "MX",
            "default_currency": currency,
        },
        headers=h(me),
    )
    assert r.status_code == 201, r.text
    return dict(r.json())


def upload(
    client: TestClient, me: LoggedIn, party_id: str, name: str, content: bytes, mime: str = XLSX
) -> Any:
    return client.post(
        f"/api/parties/{party_id}/imports", files={"file": (name, content, mime)}, headers=h(me)
    )


def upload_file(client: TestClient, me: LoggedIn, party_id: str, path: Path) -> dict[str, Any]:
    r = upload(client, me, party_id, path.name, path.read_bytes())
    assert r.status_code == 201, r.text
    return dict(r.json())


def confirmed_mapping(preview: dict[str, Any], fixed_currency: str | None = None) -> dict[str, Any]:
    """The suggested mapping as the user would confirm it (choosing a currency where the
    header didn't reveal one)."""
    sug = preview["suggested_mapping"]
    prices = []
    for p in sug["prices"]:
        cur = {k: v for k, v in p["currency"].items() if k != "suggested"}
        if cur["mode"] == "fixed" and not cur.get("value"):
            assert fixed_currency, f"no currency for {p['header']!r}"
            cur["value"] = fixed_currency
        prices.append({**{k: p[k] for k in ("col", "header", "price_type")}, "currency": cur})
    return {
        "sheet": preview["sheet"],
        "header_row": preview["header_row"],
        "data_start_row": preview["data_start_row"],
        "fields": sug["fields"],
        "dimensions": sug["dimensions"],
        "prices": prices,
    }


def validate(
    client: TestClient,
    me: LoggedIn,
    job_id: str,
    mapping: dict[str, Any],
    template_id: str | None = None,
) -> Any:
    body: dict[str, Any] = {"mapping": mapping}
    if template_id:
        body["template_id"] = template_id
    return client.post(f"/api/imports/{job_id}/validate", json=body, headers=h(me))


def commit(client: TestClient, me: LoggedIn, job_id: str, **over: Any) -> Any:
    body = {"name": "Price list", "currency": "EUR", "valid_from": "2026-01-01", **over}
    return client.post(f"/api/imports/{job_id}/commit", json=body, headers=h(me))


def csv_bytes(rows: list[list[Any]]) -> bytes:
    return "\n".join(",".join("" if v is None else str(v) for v in r) for r in rows).encode()
