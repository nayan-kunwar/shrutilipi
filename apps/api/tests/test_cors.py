"""CORS contract: explicit origins for prod, a localhost-port regex for dev.

No network: TestClient hits the in-process app. Run from apps/api with:
    python -m pytest -q
"""

from fastapi.testclient import TestClient

import main

client = TestClient(main.app)


def test_any_local_port_allowed():
    # Next dev drifts ports when 3000 is taken (3001, 3002, ...); the regex
    # keeps local dev working no matter which one it lands on.
    for origin in ("http://localhost:3002", "http://localhost:3999", "http://127.0.0.1:3001"):
        r = client.get("/api/wake", headers={"Origin": origin})
        assert r.status_code == 200
        assert r.headers.get("access-control-allow-origin") == origin


def test_explicit_origin_still_allowed():
    r = client.get("/api/wake", headers={"Origin": "http://localhost:3000"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_foreign_origin_gets_no_acao_header():
    r = client.get("/api/wake", headers={"Origin": "https://evil.example"})
    assert r.status_code == 200
    assert "access-control-allow-origin" not in r.headers


def test_preflight_allows_get_from_localhost():
    r = client.options(
        "/api/wake",
        headers={"Origin": "http://localhost:3002", "Access-Control-Request-Method": "GET"},
    )
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3002"
