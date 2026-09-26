"""Video ID extraction + caption fetching (v1: captions-only)."""

import os
import random
import re
from typing import Optional
from urllib.parse import quote

import httpx

# Supports: watch?v=, youtu.be/, /shorts/, /embed/, /live/, /v/
_VIDEO_PATTERNS = [
    r"(?:youtube\.com/watch\?.*v=)([A-Za-z0-9_-]{11})",
    r"(?:youtu\.be/)([A-Za-z0-9_-]{11})",
    r"(?:youtube\.com/(?:shorts|embed|live|v)/)([A-Za-z0-9_-]{11})",
    r"^([A-Za-z0-9_-]{11})$",  # raw video id
]


def env_truthy(raw: Optional[str], default: bool = True) -> bool:
    """Parse env truthiness: 0/false/no/off -> False; empty/None -> default."""
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() not in ("0", "false", "no", "off")


def extract_video_id(url_or_id: str) -> Optional[str]:
    """Return 11-char video id or None if unparseable."""
    if not url_or_id:
        return None
    s = url_or_id.strip()
    for pattern in _VIDEO_PATTERNS:
        m = re.search(pattern, s)
        if m:
            return m.group(1)
    return None


def get_title(video_id: str, timeout: float = 5.0) -> Optional[str]:
    """Best-effort title via YouTube oEmbed (no API key). Returns None on failure."""
    try:
        resp = httpx.get(
            "https://www.youtube.com/oembed",
            params={"url": f"https://www.youtube.com/watch?v={video_id}", "format": "json"},
            timeout=timeout,
        )
        if resp.status_code == 200:
            return resp.json().get("title")
    except Exception:
        pass
    return None


def _hosted_levels_active() -> bool:
    """True when a hosted level can serve — skip the known-dead free-proxy hop."""
    if os.getenv("SUPADATA_API_KEY", "").strip() and env_truthy(os.getenv("SUPADATA_ENABLED"), True):
        return True
    if os.getenv("SERPAPI_API_KEY", "").strip() and env_truthy(os.getenv("SERPAPI_ENABLED"), False):
        return True
    return False


def _get_proxy_config():
    """Build GenericProxyConfig from env for Webshare free-tier rotation.

    Priority:
    1. WEBSHARE_PROXY_LIST = comma-separated full URLs (scheme://user:pass@host:port)
    2. WEBSHARE_PROXY_USERNAME + WEBSHARE_PROXY_PASSWORD + WEBSHARE_PROXY_HOSTS
       where HOSTS = comma-separated host:port — user/pass applied to random host
    3. No env -> None (direct, local dev / no proxy)
    Skipped entirely when a hosted level is active (free proxies are YouTube-blocked;
    the hosted level will serve — saves 10-20s of dead-proxy retry latency).
    """
    if _hosted_levels_active():
        return None

    from youtube_transcript_api.proxies import GenericProxyConfig

    full_list = os.getenv("WEBSHARE_PROXY_LIST", "").strip()
    if full_list:
        urls = [u.strip() for u in full_list.split(",") if u.strip()]
        if urls:
            pick = random.choice(urls)
            return GenericProxyConfig(http_url=pick, https_url=pick)

    user = os.getenv("WEBSHARE_PROXY_USERNAME", "").strip()
    password = os.getenv("WEBSHARE_PROXY_PASSWORD", "").strip()
    hosts = os.getenv("WEBSHARE_PROXY_HOSTS", "").strip()

    if user and password and hosts:
        host_list = [h.strip() for h in hosts.split(",") if h.strip()]
        if host_list:
            host = random.choice(host_list)
            safe_user = quote(user, safe="")
            safe_pass = quote(password, safe="")
            url = f"http://{safe_user}:{safe_pass}@{host}"
            return GenericProxyConfig(http_url=url, https_url=url)

    return None


def fetch_caption_transcript(video_id: str, lang: str = "en"):
    """
    Returns (segments, resolved_language) using youtube-transcript-api 1.x.
    Single list() call reused — no extra round-trips.
    Raises youtube-transcript-api errors for caller to map to HTTP codes.
    """
    from youtube_transcript_api import YouTubeTranscriptApi

    langs = [lang, "en"] if lang != "en" else ["en"]
    # New instance per request: requests.Session is not thread-safe.
    # proxy_config=None -> direct (local dev); rotation spreads ban risk across 10 IPs.
    api = YouTubeTranscriptApi(proxy_config=_get_proxy_config())

    # 1) Fast path: direct fetch with preferred languages
    try:
        fetched = api.fetch(video_id, languages=langs)
        return _normalize(fetched.to_raw_data()), fetched.language_code
    except Exception as first_exc:
        first_name = type(first_exc).__name__
        # Only fall through for "not found in requested langs".
        # Blocking / unavailable errors should propagate immediately.
        if first_name not in ("NoTranscriptFound", "TranslationLanguageNotAvailable"):
            raise

    # 2) Fallback: list once, then pick best available
    transcript_list = api.list(video_id)
    try:
        t = transcript_list.find_transcript(langs)
    except Exception:
        try:
            t = transcript_list.find_generated_transcript(langs)
        except Exception:
            try:
                # Any manual transcript, else whatever exists
                all_codes = [tr.language_code for tr in transcript_list]
                t = transcript_list.find_manually_created_transcript(all_codes)
            except Exception:
                t = next(iter(transcript_list))
    fetched = t.fetch()
    return _normalize(fetched.to_raw_data()), fetched.language_code


def _normalize(raw: list) -> list:
    segments = []
    for entry in raw:
        text = (entry.get("text") or "").replace("\n", " ").strip()
        if not text:
            continue
        segments.append(
            {
                "start": float(entry.get("start", 0.0)),
                "duration": float(entry.get("duration", 0.0)),
                "text": text,
            }
        )
    return segments
