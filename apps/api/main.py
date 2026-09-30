"""ShrutiLipi backend — v1 captions-only."""

import logging
import os
import time

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from services.providers import TranscriptError, build_provider
from services.ratelimit import build_limiter, client_key
from services.youtube import extract_video_id

logger = logging.getLogger("shrutilipi")
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="ShrutiLipi", version="1.0.0")

# --- CORS: allow Vercel frontend + local dev ---
_frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
_allowed = {
    _frontend_url,
    "http://localhost:3000",
    "http://127.0.0.1:3000",
}
# Support comma-separated FRONTEND_URL="https://a.vercel.app,https://b.vercel.app"
for part in _frontend_url.split(","):
    part = part.strip()
    if part:
        _allowed.add(part)

app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(_allowed),
    allow_credentials=False,
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["*"],
)

provider = build_provider()

# Token bucket guarding upstream quota. None when RATE_LIMIT_ENABLED is off.
limiter = build_limiter()

# --- Minimal TTL cache (24h) to avoid re-hitting YouTube ---
_CACHE: dict[str, tuple[float, dict]] = {}
CACHE_TTL = 60 * 60 * 24


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/api/transcript")
def get_transcript(
    request: Request,
    url: str = Query(..., description="YouTube URL or 11-char video id"),
    lang: str = Query("en", description="Preferred caption language"),
):
    video_id = extract_video_id(url)
    if not video_id:
        raise HTTPException(status_code=400, detail="invalid_url")

    cache_key = f"{video_id}:{lang}"
    hit = _CACHE.get(cache_key)
    if hit and (time.time() - hit[0]) < CACHE_TTL:
        return hit[1]

    # Misses only: cached hits cost no upstream quota, so they cost no
    # tokens either. The limiter therefore guards the free-tier budget
    # directly, not raw traffic.
    if limiter is not None:
        key = client_key(
            request.headers.get("x-forwarded-for"),
            request.client.host if request.client else None,
        )
        retry_after = limiter.consume(key)
        if retry_after is not None:
            raise HTTPException(
                status_code=429,
                detail="rate_limited",
                headers={"Retry-After": str(max(1, int(retry_after) + 1))},
            )

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
