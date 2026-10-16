from fastapi.testclient import TestClient

from app.main import create_app


def test_health_reports_db_ok() -> None:
    r = TestClient(create_app()).get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "database": "ok"}


def test_security_headers_present() -> None:
    r = TestClient(create_app()).get("/api/health")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["Referrer-Policy"] == "no-referrer"
    assert "default-src 'none'" in r.headers["Content-Security-Policy"]
    assert r.headers["Cache-Control"] == "no-store"
    # HSTS only in production (HTTPS).
    assert "Strict-Transport-Security" not in r.headers


def test_cors_allows_only_web_origin() -> None:
    client = TestClient(create_app())
    ok = client.options(
        "/api/health",
        headers={"Origin": "http://localhost:8080", "Access-Control-Request-Method": "GET"},
    )
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:8080"
    bad = client.options(
        "/api/health",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"},
    )
    assert "access-control-allow-origin" not in bad.headers


def test_unknown_route_is_generic_404() -> None:
    r = TestClient(create_app()).get("/api/nope")
    assert r.status_code == 404
    assert r.json() == {"detail": "Not Found"}
