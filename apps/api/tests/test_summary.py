"""HTTP contract for the on-demand summary endpoint.

No network: the transcript provider and the summarizer are stubs. Run from
apps/api with: python -m pytest -q
"""

import threading

from fastapi.testclient import TestClient

import main
from services.providers import TranscriptResult
from services.ratelimit import RateLimiter
from services.summarize import SummaryError


def _vid(tag, i):
    """Distinct valid 11-char IDs per test (avoids the shared caches)."""
    return f"{tag}{i:02d}"


class _StubProvider:
    def __init__(self):
        self.calls = 0

    def get_transcript(self, video_id, lang="en"):
        self.calls += 1
        return TranscriptResult(
            video_id=video_id,
            language=lang,
            segments=[{"start": 0.0, "duration": 1.0, "text": "hello world"}],
            title="stub",
        )


class _StubSummarizer:
    model = "stub-model"

    def __init__(self, text="TL;DR: ok\n\n• one", error=None):
        self.calls = 0
        self.text = text
        self.error = error

    def summarize(self, plain_text):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.text


def _client():
    return TestClient(main.app)


# --- disabled / validation ---------------------------------------------------


def test_summary_disabled_without_provider_config(monkeypatch):
    monkeypatch.setattr(main, "summarizer", None)
    r = _client().post("/api/summary", json={"videoId": _vid("summdisab", 0)})
    assert r.status_code == 503
    assert r.json() == {"detail": "summary_disabled"}


def test_invalid_video_id_is_400(monkeypatch):
    monkeypatch.setattr(main, "summarizer", _StubSummarizer())
    r = _client().post("/api/summary", json={"videoId": "not a video"})
    assert r.status_code == 400
    assert r.json() == {"detail": "invalid_url"}


# --- happy path / caching ----------------------------------------------------


def test_happy_path_then_cache_hit(monkeypatch):
    provider = _StubProvider()
    summarizer = _StubSummarizer()
    monkeypatch.setattr(main, "provider", provider)
    monkeypatch.setattr(main, "summarizer", summarizer)
    monkeypatch.setattr(main, "summary_limiter", RateLimiter(5, 600))

    vid = _vid("summhappy", 0)
    client = _client()

    first = client.post("/api/summary", json={"videoId": vid, "lang": "en"})
    assert first.status_code == 200, first.text
    assert first.json() == {
        "summary": "TL;DR: ok\n\n• one",
        "model": "stub-model",
        "cached": False,
    }

    second = client.post("/api/summary", json={"videoId": vid, "lang": "en"})
    assert second.status_code == 200
    assert second.json()["cached"] is True
    assert summarizer.calls == 1  # cached summaries never re-bill the LLM
    assert provider.calls == 1  # the transcript was fetched once, then reused


def test_summary_reuses_transcript_cache_without_spending_transcript_tokens(monkeypatch):
    provider = _StubProvider()
    summarizer = _StubSummarizer()
    monkeypatch.setattr(main, "provider", provider)
    monkeypatch.setattr(main, "summarizer", summarizer)
    # One transcript token only: the summary must not need a second one.
    monkeypatch.setattr(main, "limiter", RateLimiter(1, 600))
    monkeypatch.setattr(main, "summary_limiter", RateLimiter(5, 600))

    vid = _vid("summcache", 0)
    client = _client()

    assert client.get("/api/transcript", params={"url": vid}).status_code == 200
    r = client.post("/api/summary", json={"videoId": vid})
    assert r.status_code == 200, r.text
    assert provider.calls == 1


def test_summary_cache_hit_does_not_consume_summary_tokens(monkeypatch):
    monkeypatch.setattr(main, "provider", _StubProvider())
    summarizer = _StubSummarizer()
    monkeypatch.setattr(main, "summarizer", summarizer)
    monkeypatch.setattr(main, "summary_limiter", RateLimiter(1, 600))
    monkeypatch.setattr(main, "limiter", RateLimiter(5, 600))

    vid = _vid("summhit00", 0)
    client = _client()
    assert client.post("/api/summary", json={"videoId": vid}).status_code == 200
    again = client.post("/api/summary", json={"videoId": vid})
    assert again.status_code == 200
    assert again.json()["cached"] is True
    assert summarizer.calls == 1


# --- limiter placement -------------------------------------------------------


def test_summary_limiter_is_enforced_before_transcript_work(monkeypatch):
    provider = _StubProvider()
    monkeypatch.setattr(main, "provider", provider)
    monkeypatch.setattr(main, "summarizer", _StubSummarizer())
    monkeypatch.setattr(main, "summary_limiter", RateLimiter(1, 600))
    monkeypatch.setattr(main, "limiter", RateLimiter(5, 600))

    client = _client()
    assert client.post("/api/summary", json={"videoId": _vid("summrate0", 0)}).status_code == 200
    blocked = client.post("/api/summary", json={"videoId": _vid("summrate0", 1)})
    assert blocked.status_code == 429
    assert blocked.json() == {"detail": "summary_rate_limited"}
    assert int(blocked.headers["retry-after"]) >= 1
    assert provider.calls == 1  # the second video never reached the provider


def test_transcript_limiter_applies_when_summary_needs_a_fetch(monkeypatch):
    provider = _StubProvider()
    monkeypatch.setattr(main, "provider", provider)
    monkeypatch.setattr(main, "summarizer", _StubSummarizer())
    monkeypatch.setattr(main, "limiter", RateLimiter(1, 600))
    monkeypatch.setattr(main, "summary_limiter", RateLimiter(1, 600))

    client = _client()
    assert client.get("/api/transcript", params={"url": _vid("summtrans", 0)}).status_code == 200

    # New video: the summary token is spent, then the transcript limiter
    # rejects the fetch. Documented attempt-level accounting trade-off.
    first = client.post("/api/summary", json={"videoId": _vid("summtrans", 1)})
    assert first.status_code == 429
    assert first.json() == {"detail": "rate_limited"}
    assert provider.calls == 1

    # The summary token was consumed by that attempt: a retry is now limited
    # in the summary bucket rather than reaching upstream again.
    second = client.post("/api/summary", json={"videoId": _vid("summtrans", 1)})
    assert second.status_code == 429
    assert second.json() == {"detail": "summary_rate_limited"}
    assert provider.calls == 1


# --- failures ----------------------------------------------------------------


def test_llm_failure_is_502_and_transcript_still_works(monkeypatch):
    provider = _StubProvider()
    monkeypatch.setattr(main, "provider", provider)
    monkeypatch.setattr(main, "summarizer", _StubSummarizer(error=SummaryError()))
    monkeypatch.setattr(main, "summary_limiter", RateLimiter(5, 600))
    monkeypatch.setattr(main, "limiter", RateLimiter(5, 600))

    vid = _vid("summfail0", 0)
    client = _client()
    r = client.post("/api/summary", json={"videoId": vid})
    assert r.status_code == 502
    assert r.json() == {"detail": "summary_failed"}

    # The transcript was cached before the LLM call; the failure is isolated.
    t = client.get("/api/transcript", params={"url": vid})
    assert t.status_code == 200
    assert t.json()["plainText"] == "hello world"
    assert provider.calls == 1


def test_unexpected_llm_exception_does_not_leak(monkeypatch):
    monkeypatch.setattr(main, "provider", _StubProvider())
    monkeypatch.setattr(main, "summarizer", _StubSummarizer(error=RuntimeError("secret stack")))
    monkeypatch.setattr(main, "summary_limiter", RateLimiter(5, 600))
    monkeypatch.setattr(main, "limiter", RateLimiter(5, 600))

    r = _client().post("/api/summary", json={"videoId": _vid("summboom0", 0)})
    assert r.status_code == 502
    assert r.json() == {"detail": "summary_failed"}
    assert "secret stack" not in r.text


def test_same_video_concurrency_is_bounded_by_the_lock(monkeypatch):
    monkeypatch.setattr(main, "provider", _StubProvider())
    monkeypatch.setattr(main, "summarizer", _StubSummarizer())
    monkeypatch.setattr(main, "summary_limiter", RateLimiter(5, 600))
    monkeypatch.setattr(main, "limiter", RateLimiter(5, 600))
    monkeypatch.setattr(main, "_SUMMARY_LOCK_TIMEOUT", 0.05)

    vid = _vid("summbusy0", 0)
    key = main._summary_cache_key(vid, "en", "stub-model")

    started = threading.Event()
    release = threading.Event()

    def hold_lock():
        with main._summary_lock(key):
            started.set()
            release.wait(5)

    t = threading.Thread(target=hold_lock, daemon=True)
    t.start()
    assert started.wait(2)
    try:
        r = _client().post("/api/summary", json={"videoId": vid})
        assert r.status_code == 503
        assert r.json() == {"detail": "summary_busy"}
    finally:
        release.set()
        t.join()


# --- cache key dimensions ----------------------------------------------------


def test_language_is_part_of_the_cache_key(monkeypatch):
    provider = _StubProvider()
    summarizer = _StubSummarizer()
    monkeypatch.setattr(main, "provider", provider)
    monkeypatch.setattr(main, "summarizer", summarizer)
    monkeypatch.setattr(main, "summary_limiter", RateLimiter(5, 600))
    monkeypatch.setattr(main, "limiter", RateLimiter(5, 600))

    vid = _vid("summlang0", 0)
    client = _client()
    assert client.post("/api/summary", json={"videoId": vid, "lang": "en"}).status_code == 200
    assert client.post("/api/summary", json={"videoId": vid, "lang": "hi"}).status_code == 200
    assert provider.calls == 2
    assert summarizer.calls == 2
