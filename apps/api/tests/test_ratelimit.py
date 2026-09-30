"""Tests for services/ratelimit.py and its wiring in main.py.

No network, no sleeping: the limiter takes an injectable clock, and the HTTP
test stubs the transcript provider. Run from apps/api with:
    python -m pytest -q
"""

import main
from services.providers import TranscriptResult
from services.ratelimit import (
    RateLimiter,
    build_limiter,
    client_key,
)


def make_clock(start=1000.0):
    """A manual clock: [now] + advance()."""
    state = [start]

    def now():
        return state[0]

    def advance(seconds):
        state[0] += seconds

    return now, advance


# --- bucket behavior ---


def test_allow_up_to_capacity_then_deny():
    now, _ = make_clock()
    lim = RateLimiter(capacity=3, window_seconds=600, clock=now)
    assert lim.consume("a") is None
    assert lim.consume("a") is None
    assert lim.consume("a") is None
    retry = lim.consume("a")
    assert isinstance(retry, float) and retry > 0


def test_refill_after_full_window():
    now, advance = make_clock()
    lim = RateLimiter(capacity=2, window_seconds=100, clock=now)
    lim.consume("a")
    lim.consume("a")
    assert lim.consume("a") is not None  # empty
    advance(100)  # a full window refills the bucket completely
    assert lim.consume("a") is None


def test_partial_refill_is_proportional():
    now, advance = make_clock()
    lim = RateLimiter(capacity=2, window_seconds=100, clock=now)
    lim.consume("a")
    lim.consume("a")
    advance(50)  # half a window -> exactly one of two tokens back
    assert lim.consume("a") is None
    assert lim.consume("a") is not None


def test_keys_do_not_share_buckets():
    now, _ = make_clock()
    lim = RateLimiter(capacity=1, window_seconds=600, clock=now)
    assert lim.consume("a") is None
    assert lim.consume("b") is None  # different key, fresh bucket
    assert lim.consume("a") is not None


def test_stale_buckets_are_pruned():
    now, advance = make_clock()
    lim = RateLimiter(capacity=1, window_seconds=60, clock=now)
    lim.consume("a")
    lim.consume("b")
    assert len(lim._buckets) == 2
    advance(61)  # both idle past the window
    lim.consume("c")
    assert set(lim._buckets) == {"c"}


def test_retry_after_matches_refill_math():
    now, _ = make_clock()
    lim = RateLimiter(capacity=20, window_seconds=600, clock=now)
    for _ in range(20):
        lim.consume("a")
    retry = lim.consume("a")
    # One token refills every window/capacity = 30s here.
    assert retry == 600 / 20


# --- client identity ---


def test_client_key_prefers_leftmost_xff():
    assert client_key("203.0.113.7, 70.41.3.18", "10.0.0.1") == "203.0.113.7"


def test_client_key_strips_xff_whitespace():
    assert client_key("  203.0.113.7  ", None) == "203.0.113.7"


def test_client_key_falls_back_to_peer():
    assert client_key(None, "127.0.0.1") == "127.0.0.1"
    assert client_key("", "127.0.0.1") == "127.0.0.1"
    assert client_key(" , ", "127.0.0.1") == "127.0.0.1"


def test_client_key_never_empty():
    assert client_key(None, None) == "unknown"


# --- env factory ---


def test_build_limiter_defaults(monkeypatch):
    for var in ("RATE_LIMIT_ENABLED", "RATE_LIMIT_REQUESTS", "RATE_LIMIT_WINDOW_SECONDS"):
        monkeypatch.delenv(var, raising=False)
    lim = build_limiter()
    assert lim is not None
    assert (lim.capacity, lim.window_seconds) == (20, 600)


def test_build_limiter_disabled(monkeypatch):
    for raw in ("0", "false", "no", "off"):
        monkeypatch.setenv("RATE_LIMIT_ENABLED", raw)
        assert build_limiter() is None


def test_build_limiter_custom_values(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("RATE_LIMIT_REQUESTS", "5")
    monkeypatch.setenv("RATE_LIMIT_WINDOW_SECONDS", "60")
    lim = build_limiter()
    assert (lim.capacity, lim.window_seconds) == (5, 60)


def test_build_limiter_garbage_falls_back(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "yes")  # truthy, not in the false-list
    monkeypatch.setenv("RATE_LIMIT_REQUESTS", "lots")
    monkeypatch.setenv("RATE_LIMIT_WINDOW_SECONDS", "-30")
    lim = build_limiter()
    assert (lim.capacity, lim.window_seconds) == (20, 600)


# --- HTTP wiring: 429 shape + miss-only consumption ---


class _StubProvider:
    """Stands in for the real chain: instant canned transcript, no network."""

    def get_transcript(self, video_id, lang="en"):
        return TranscriptResult(
            video_id=video_id,
            language=lang,
            segments=[{"start": 0.0, "duration": 1.0, "text": "hello"}],
            title="stub",
        )


def _vid(tag, i):
    """Distinct valid 11-char IDs per test (avoids the shared _CACHE)."""
    return f"{tag}{i:02d}"  # e.g. "rlimhttp00" — caller picks a 9-char tag


def test_http_429_shape_and_headers(monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setattr(main, "provider", _StubProvider())
    monkeypatch.setattr(main, "limiter", RateLimiter(capacity=3, window_seconds=600))
    client = TestClient(main.app)

    for i in range(3):
        r = client.get("/api/transcript", params={"url": _vid("rlimhttp0", i)})
        assert r.status_code == 200, r.text

    limited = client.get("/api/transcript", params={"url": _vid("rlimhttp0", 3)})
    assert limited.status_code == 429
    assert limited.json() == {"detail": "rate_limited"}
    retry_after = int(limited.headers["retry-after"])
    assert retry_after >= 1


def test_cache_hits_do_not_consume_tokens(monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setattr(main, "provider", _StubProvider())
    monkeypatch.setattr(main, "limiter", RateLimiter(capacity=3, window_seconds=600))
    client = TestClient(main.app)

    first = _vid("rlimcache", 0)
    assert client.get("/api/transcript", params={"url": first}).status_code == 200
    # Same ID twice more: served from _CACHE, must not touch the bucket.
    assert client.get("/api/transcript", params={"url": first}).status_code == 200
    assert client.get("/api/transcript", params={"url": first}).status_code == 200
    # Only one token spent so far: two more misses fit, the third is limited.
    assert client.get("/api/transcript", params={"url": _vid("rlimcache", 1)}).status_code == 200
    assert client.get("/api/transcript", params={"url": _vid("rlimcache", 2)}).status_code == 200
    assert client.get("/api/transcript", params={"url": _vid("rlimcache", 3)}).status_code == 429
