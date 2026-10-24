"""CORS contract: explicit origins for prod, a localhost-port regex for dev.

No network: TestClient hits the in-process app. Run from apps/api with:
    python -m pytest -q
"""

from fastapi.testclient import TestClient

import main

client = TestClient(main.app)

# The custom domain is the production frontend. It was added to the Vercel
# project without touching the API's allowlist, and the result was a site
# that looked fine but could not call its own API ("Disallowed CORS origin").
CUSTOM_DOMAIN = "https://shrutilipi.nayankunwar.com"
LEGACY_VERCEL = "https://shrutilipi-rho.vercel.app"


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


def test_custom_domain_get_is_allowed():
    # The real browser path: a simple GET with no custom headers, so there is
    # no preflight — the allow-origin header on the response is the whole
    # contract. Without it the browser discards the body.
    r = client.get("/api/wake", headers={"Origin": CUSTOM_DOMAIN})
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == CUSTOM_DOMAIN


def test_preflight_allows_summary_post_from_localhost():
    # The summary endpoint sends JSON, so the browser preflights it. Without
    # POST in allow_methods the feature would fail only in real browsers.
    r = client.options(
        "/api/summary",
        headers={
            "Origin": "http://localhost:3001",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3001"
    assert "POST" in r.headers.get("access-control-allow-methods", "")


def test_custom_domain_preflight_is_allowed():
    r = client.options(
        "/api/transcript",
        headers={"Origin": CUSTOM_DOMAIN, "Access-Control-Request-Method": "GET"},
    )
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == CUSTOM_DOMAIN


def test_legacy_vercel_origin_still_allowed():
    # Regression guard: the old Vercel URL must keep working.
    r = client.get("/api/wake", headers={"Origin": LEGACY_VERCEL})
    assert r.headers.get("access-control-allow-origin") == LEGACY_VERCEL


def test_www_custom_domain_allowed():
    # www has no DNS record yet, but allowing it now means adding it later
    # needs no API deploy. Exact-match only, so it grants nothing extra.
    origin = "https://www.shrutilipi.nayankunwar.com"
    r = client.get("/api/wake", headers={"Origin": origin})
    assert r.headers.get("access-control-allow-origin") == origin


def test_frontend_url_is_split_into_discrete_origins(monkeypatch):
    # Regression guard for a real bug: the raw FRONTEND_URL string used to be
    # added to the allowlist before being split, so "a,b" landed in the set as
    # one bogus origin.
    monkeypatch.setenv("FRONTEND_URL", "https://a.example,https://b.example")
    origins = main._allowed_origins()
    assert "https://a.example" in origins
    assert "https://b.example" in origins
    assert "https://a.example,https://b.example" not in origins


def test_production_origins_survive_an_unrelated_frontend_url(monkeypatch):
    # The whole point of hardcoding them: a stale or wrong env value must not
    # be able to lock the production frontend out of its own API.
    monkeypatch.setenv("FRONTEND_URL", "https://stale.example")
    origins = main._allowed_origins()
    assert CUSTOM_DOMAIN in origins
    assert LEGACY_VERCEL in origins


def test_configured_middleware_allows_production_origins():
    # The allowlist on the live middleware, not just the helper — a refactor
    # could wire the helper up wrongly while the helper itself stays correct.
    allowed = {
        o
        for o in main.PROD_ORIGINS
        if client.get("/api/wake", headers={"Origin": o}).headers.get(
            "access-control-allow-origin"
        )
        == o
    }
    assert allowed == set(main.PROD_ORIGINS)
