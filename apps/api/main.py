"""ShrutiLipi backend — v1 captions-only, plus optional on-demand summaries."""

import logging
import os
import threading
import time
from contextlib import contextmanager

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from services.providers import TranscriptError, build_provider
from services.ratelimit import build_limiter, client_key
from services.summarize import PROMPT_VERSION, SummaryError, build_summarizer
from services.youtube import extract_video_id

logger = logging.getLogger("shrutilipi")
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="ShrutiLipi", version="1.0.0")

# --- CORS: allow the production frontends + local dev ---
# The production origins live here, not only in Render's env, because a domain
# change (a custom domain added to the Vercel project) once broke every API
# call until someone remembered to edit the dashboard. FRONTEND_URL can still
# *add* origins, but it can no longer take the site down.
#
# Production origins stay explicit — no wildcard for preview deployments.
PROD_ORIGINS = (
    "https://shrutilipi.nayankunwar.com",
    "https://www.shrutilipi.nayankunwar.com",
    "https://shrutilipi-rho.vercel.app",
)

# Local dev. The ports are covered by the regex below as well, but naming the
# common ones keeps the middleware config readable.
LOCAL_ORIGINS = (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
)


def _allowed_origins() -> set[str]:
    """The origins this API answers CORS requests for.

    FRONTEND_URL may be a comma-separated list ("https://a.app,https://b.app").
    It is split *before* being added to the set: adding the raw string first
    would put the whole "a,b" string into the allowlist as one bogus origin.
    """
    origins = set(PROD_ORIGINS) | set(LOCAL_ORIGINS)
    for part in os.getenv("FRONTEND_URL", "").split(","):
        part = part.strip()
        if part:
            origins.add(part)
    return origins


_allowed = _allowed_origins()

app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(_allowed),
    # Local dev: Next picks whatever port is free (3000 is often taken), so
    # allow any localhost port by regex instead of chasing them in _allowed.
    allow_origin_regex=r"^http://(localhost|127\.0\.0\.1):\d+$",
    allow_credentials=False,
    # POST is required by /api/summary; the JSON body triggers a preflight.
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

provider = build_provider()

# Token bucket guarding upstream quota. None when RATE_LIMIT_ENABLED is off.
limiter = build_limiter()

# Summary is optional and independently limited: it spends LLM money, not
# upstream caption quota. None when SUMMARY_RATE_LIMIT_ENABLED is off.
summary_limiter = build_limiter(
    "SUMMARY_RATE_LIMIT", default_requests=5, default_window=600
)
# None when SUMMARY_BASE_URL / SUMMARY_API_KEY / SUMMARY_MODEL are not set.
summarizer = build_summarizer()

# --- Minimal TTL cache (24h) to avoid re-hitting YouTube ---
_CACHE: dict[str, tuple[float, dict]] = {}
CACHE_TTL = 60 * 60 * 24

# Summaries live in their own cache: the key includes model + prompt version,
# so changing either starts a cold (but still correct) cache.
_SUMMARY_CACHE: dict[str, tuple[float, dict]] = {}
SUMMARY_CACHE_TTL = 60 * 60 * 24
# How long a request may wait for another request generating the same video.
_SUMMARY_LOCK_TIMEOUT = 30


@app.get("/api/wake")
@app.get("/health")
def wake():
    """Wake/keep-warm probe — no provider call, no rate-limit tokens.

    The frontend pings /api/wake on load: its arrival starts a boot if the
    free instance is asleep. /health stays as the ops alias (curl, dashboards).
    The probe deliberately does not use the word "health" as the frontend
    path — some adblock filter lists block health-style URLs client-side
    (net::ERR_BLOCKED_BY_CLIENT), which would masquerade as a dead server.
    """
    return {"ok": True}


def _request_key(request: Request) -> str:
    return client_key(
        request.headers.get("x-forwarded-for"),
        request.client.host if request.client else None,
    )


def _consume_or_429(limiter_obj, request: Request, detail: str) -> None:
    """Consume one token, or raise the API's standard 429 shape."""
    if limiter_obj is None:
        return
    retry_after = limiter_obj.consume(_request_key(request))
    if retry_after is not None:
        raise HTTPException(
            status_code=429,
            detail=detail,
            headers={"Retry-After": str(max(1, int(retry_after) + 1))},
        )


def _fetch_transcript_payload(video_id: str, lang: str, request: Request) -> dict:
    """Shared transcript path: cache -> limiter (misses only) -> provider -> cache.

    Both /api/transcript and /api/summary call this. A summary for a video
    that was already fetched therefore never re-spends provider quota or
    transcript rate-limit tokens.
    """
    cache_key = f"{video_id}:{lang}"
    hit = _CACHE.get(cache_key)
    if hit and (time.time() - hit[0]) < CACHE_TTL:
        return hit[1]

    # Misses only: cached hits cost no upstream quota, so they cost no
    # tokens either. The limiter therefore guards the free-tier budget
    # directly, not raw traffic.
    _consume_or_429(limiter, request, "rate_limited")

    try:
        result = provider.get_transcript(video_id, lang=lang)
    except Exception as exc:
        logger.exception("transcript fetch failed video_id=%s lang=%s: %s", video_id, lang, exc)
        raise _map_error(exc) from exc

    if not result.segments:
        raise HTTPException(status_code=404, detail="no_captions")

    payload = {
        "videoId": result.video_id,
        "title": result.title,
        "language": result.language,
        "plainText": result.plain_text,
        "segments": result.segments,
    }
    _CACHE[cache_key] = (time.time(), payload)
    return payload


@app.get("/api/transcript")
def get_transcript(
    request: Request,
    url: str = Query(..., description="YouTube URL or 11-char video id"),
    lang: str = Query("en", description="Preferred caption language"),
):
    video_id = extract_video_id(url)
    if not video_id:
        raise HTTPException(status_code=400, detail="invalid_url")
    return _fetch_transcript_payload(video_id, lang, request)


# --- On-demand summary -----------------------------------------------------
# Nothing here runs unless the user clicks "Generate summary": the transcript
# endpoint has no summary cost or latency. The client sends a video id, never
# text, so the API cannot be used as an open LLM proxy.


class _SummaryLockEntry:
    __slots__ = ("lock", "waiters")

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.waiters = 0


_SUMMARY_LOCKS: dict[str, _SummaryLockEntry] = {}
_SUMMARY_LOCKS_GUARD = threading.Lock()


@contextmanager
def _summary_lock(key: str):
    """Serializes generation for one video, not all videos.

    The refcount removes idle entries so the lock table cannot grow forever.
    The wait is bounded: a stuck generation must not hold request threads
    indefinitely — waiting requests get 503 summary_busy instead.
    """
    with _SUMMARY_LOCKS_GUARD:
        entry = _SUMMARY_LOCKS.get(key)
        if entry is None:
            entry = _SummaryLockEntry()
            _SUMMARY_LOCKS[key] = entry
        entry.waiters += 1

    acquired = entry.lock.acquire(timeout=_SUMMARY_LOCK_TIMEOUT)
    try:
        if not acquired:
            raise HTTPException(status_code=503, detail="summary_busy")
        yield
    finally:
        if acquired:
            entry.lock.release()
        with _SUMMARY_LOCKS_GUARD:
            entry.waiters -= 1
            if entry.waiters == 0:
                _SUMMARY_LOCKS.pop(key, None)


def _summary_cache_key(video_id: str, lang: str, model: str) -> str:
    return f"{video_id}:{lang}:{model}:{PROMPT_VERSION}"


def _prune_summary_cache() -> None:
    now = time.time()
    for key, (stored_at, _) in list(_SUMMARY_CACHE.items()):
        if now - stored_at >= SUMMARY_CACHE_TTL:
            _SUMMARY_CACHE.pop(key, None)


class SummaryRequest(BaseModel):
    videoId: str
    lang: str = "en"


@app.post("/api/summary")
def get_summary(request: Request, body: SummaryRequest):
    video_id = extract_video_id(body.videoId)
    if not video_id:
        raise HTTPException(status_code=400, detail="invalid_url")

    lang = (body.lang or "en").strip() or "en"

    if summarizer is None:
        raise HTTPException(status_code=503, detail="summary_disabled")

    cache_key = _summary_cache_key(video_id, lang, summarizer.model)
    hit = _SUMMARY_CACHE.get(cache_key)
    if hit and (time.time() - hit[0]) < SUMMARY_CACHE_TTL:
        return {**hit[1], "cached": True}

    # Enforce the LLM budget before any expensive work. Tokens are consumed
    # per attempt that reaches this point, not per successful summary — the
    # cheaper-to-reason-about policy; see docs/operations.md §9.
    _consume_or_429(summary_limiter, request, "summary_rate_limited")

    with _summary_lock(cache_key):
        # Another request may have filled the cache while we waited.
        hit = _SUMMARY_CACHE.get(cache_key)
        if hit and (time.time() - hit[0]) < SUMMARY_CACHE_TTL:
            return {**hit[1], "cached": True}

        transcript = _fetch_transcript_payload(video_id, lang, request)
        try:
            text = summarizer.summarize(transcript["plainText"])
        except SummaryError as exc:
            logger.warning(
                "summary failed video_id=%s model=%s detail=%s",
                video_id,
                summarizer.model,
                exc.detail,
            )
            raise HTTPException(status_code=502, detail="summary_failed") from exc
        except Exception as exc:  # defensive: never leak internals to clients
            logger.exception(
                "summary failed unexpectedly video_id=%s type=%s",
                video_id,
                type(exc).__name__,
            )
            raise HTTPException(status_code=502, detail="summary_failed") from exc

        result = {"summary": text, "model": summarizer.model}
        _SUMMARY_CACHE[cache_key] = (time.time(), result)
        _prune_summary_cache()
        return {**result, "cached": False}


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, TranscriptError):
        return HTTPException(
            status_code=404 if exc.detail == "no_captions" else 502,
            detail=exc.detail,
        )

    name = type(exc).__name__
    msg = str(exc).lower()

    if name in ("InvalidVideoId",) or ("invalid" in msg and "video" in msg):
        return HTTPException(status_code=400, detail="invalid_url")
    if name in ("VideoUnavailable", "VideoUnplayable", "AgeRestricted") or "video unavailable" in msg:
        return HTTPException(status_code=404, detail="video_unavailable")
    if name in (
        "TranscriptsDisabled",
        "NoTranscriptFound",
        "NotTranslatable",
        "TranslationLanguageNotAvailable",
    ) or "no transcript" in msg or "transcripts disabled" in msg or "could not retrieve" in msg:
        # CouldNotRetrieveTranscript wraps many causes; distinguish blocking by message
        if "blocking requests from your ip" in msg or "ip" in msg and "block" in msg:
            return HTTPException(status_code=502, detail="youtube_blocked")
        return HTTPException(status_code=404, detail="no_captions")
    if name in (
        "IpBlocked",
        "RequestBlocked",
        "FailedToCreateConsentCookie",
        "PoTokenRequired",
        "YouTubeRequestFailed",
        "YouTubeDataUnparsable",
        "TooManyRequests",
    ) or ("ip" in msg and "block" in msg):
        return HTTPException(status_code=502, detail="youtube_blocked")
    return HTTPException(status_code=502, detail="transcript_fetch_failed")
