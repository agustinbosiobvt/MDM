"""Observations survive import and support audited edits with existing role checks."""

from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.imports.detect import suggest_mapping
from tests.conftest import LoggedIn
from tests.import_helpers import commit, csv_bytes, h, partner, upload, validate


def test_observations_import_edit_limits_and_audit(
    client: TestClient, login: Callable[..., LoggedIn], admin_engine: Engine
) -> None:
    editor = login("editor@buenavidatrading.com", role="editor")
    vendor = partner(client, editor, "vendor", "OBS", "EUR")
    note = "MOQ originales: 3 y 30 piezas. Se conserva el menor: 3."
    content = csv_bytes(
        [
            ["EAN", "Price EUR", "Observations"],
            ["5415245053400", "1.2345", note],
            ["4033766024122", "2.50", None],
        ]
    )
    job = upload(client, editor, vendor["id"], "observations.csv", content, "text/csv").json()
    mapping = {
        "sheet": "CSV",
        "header_row": 1,
        "data_start_row": 2,
        "fields": {"ean": {"col": 0}, "observations": {"col": 2}},
        "prices": [
            {"col": 1, "price_type": "purchase", "currency": {"mode": "fixed", "value": "EUR"}}
        ],
    }
    report = validate(client, editor, job["id"], mapping)
    assert report.status_code == 200, report.text
    done = commit(client, editor, job["id"])
    assert done.status_code == 200, done.text
    pl_id = done.json()["price_list_id"]
    lines = client.get(f"/api/price-lists/{pl_id}/lines").json()["items"]
    line = next(x for x in lines if x["ean"] == "5415245053400")
    assert line["observations"] == note
    assert next(x for x in lines if x["ean"] == "4033766024122")["observations"] is None
    assert line["prices"][0]["amount"] == "1.2345"
    url = f"/api/price-list-lines/{line['id']}"
    too_long = client.patch(
        url, json={"version": line["version"], "observations": "x" * 2001}, headers=h(editor)
    )
    assert too_long.status_code == 422
    saved = client.patch(
        url, json={"version": line["version"], "observations": "  Revisado  "}, headers=h(editor)
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["observations"] == "Revisado"
    with admin_engine.connect() as conn:
        audit = conn.execute(
            text(
                "SELECT old_values, new_values FROM mdm.audit_log "
                "WHERE entity = 'price_list_line' ORDER BY id DESC LIMIT 1"
            )
        ).one()
    assert audit.old_values == {"observations": note}
    assert audit.new_values == {"observations": "Revisado"}
    cleared = client.patch(
        url, json={"version": saved.json()["version"], "observations": "  "}, headers=h(editor)
    )
    assert cleared.status_code == 200
    assert cleared.json()["observations"] is None
    viewer = login("viewer@buenavidatrading.com", role="viewer")
    denied = client.patch(
        url, json={"version": cleared.json()["version"], "observations": "No"}, headers=h(viewer)
    )
    assert denied.status_code == 403


def test_observations_column_suggestions() -> None:
    for header in ("Observations", "Observaciones", "Notes"):
        assert suggest_mapping(("EAN", header))["fields"]["observations"]["col"] == 1
