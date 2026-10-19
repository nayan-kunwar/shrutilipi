"""The wake probe contract: /api/wake (frontend) and its /health alias.

No network: TestClient hits the in-process app. Run from apps/api with:
    python -m pytest -q
"""

from fastapi.testclient import TestClient

import main

client = TestClient(main.app)


def test_wake_probe_ok():
    r = client.get("/api/wake")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_health_alias_still_ok():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"ok": True}
