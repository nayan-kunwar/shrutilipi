"""Provider chain — direct captions + hosted fallbacks (Supadata, SerpApi).

Env-driven (no secrets in code):
  CHAIN_ORDER       comma list, default "direct,supadata,serpapi"; unknown names dropped
  DIRECT_ENABLED    default "true" (render.yaml sets "false" while YouTube blocks Render)
  SUPADATA_API_KEY  required for the supadata level
  SUPADATA_ENABLED  default "true"
  SERPAPI_API_KEY   required for the serpapi level
  SERPAPI_ENABLED   default "false" (emergency-only on free tier)
  SERPAPI_TIME_UNIT auto|seconds|ms — SerpApi docs omit units; auto = ms iff max start > 50000
Missing keys / disabled levels are skipped. Local keyless dev = direct only.
"""

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import httpx

from .youtube import env_truthy, fetch_caption_transcript, get_title

logger = logging.getLogger("shrutilipi")


@dataclass
class TranscriptResult:
    video_id: str
    language: str
    segments: list = field(default_factory=list)
    title: str | None = None

    @property
    def plain_text(self) -> str:
        return " ".join(s["text"] for s in self.segments)


class TranscriptError(Exception):
    """Typed provider failure; detail maps to HTTP in main.py."""

    detail = "transcript_fetch_failed"


class TranscriptsNotFound(TranscriptError):
    detail = "no_captions"


class ProviderQuotaError(TranscriptError):
    detail = "provider_unavailable"


class ProviderAuthError(TranscriptError):
    detail = "provider_unavailable"


class ProviderNetworkError(TranscriptError):
    detail = "provider_unavailable"


class TranscriptProvider(ABC):
    handles_missing: bool = True

    @abstractmethod
    def get_transcript(self, video_id: str, lang: str = "en") -> TranscriptResult:
        raise NotImplementedError


class CaptionProvider(TranscriptProvider):
    """Direct YouTube captions (manual > auto-generated) via youtube-transcript-api."""

    def get_transcript(self, video_id: str, lang: str = "en") -> TranscriptResult:
        segments, resolved_lang = fetch_caption_transcript(video_id, lang=lang)
        title = get_title(video_id)
        return TranscriptResult(
            video_id=video_id,
            language=resolved_lang,
            segments=segments,
            title=title,
        )


def _raise_hosted_error(source: str, msg: str) -> None:
    low = str(msg).lower()
    if any(h in low for h in ("quota", "credit", "exhaust", "rate limit", "too many", "billing", "plan")):
        raise ProviderQuotaError(f"{source}: {msg}")
    if any(h in low for h in ("api key", "api_key", "unauthorized", "forbidden", "invalid key")):
        raise ProviderAuthError(f"{source}: {msg}")
    raise ProviderNetworkError(f"{source}: {msg}")


def _json_or_raise(resp: httpx.Response, source: str) -> dict:
    try:
        data = resp.json()
    except ValueError:
        raise ProviderNetworkError(f"{source}: non-json response ({resp.status_code})")
    if not isinstance(data, dict):
        raise ProviderNetworkError(f"{source}: unexpected payload ({resp.status_code})")
    return data


def _map_hosted_status(resp: httpx.Response, source: str) -> None:
    if resp.status_code in (401, 403):
        raise ProviderAuthError(f"{source}: auth failed ({resp.status_code})")
    if resp.status_code in (402, 429):
        raise ProviderQuotaError(f"{source}: quota/rate limited ({resp.status_code})")
    if resp.status_code == 404:
        raise TranscriptsNotFound(f"{source}: transcript not found")
    if resp.status_code >= 500:
        raise ProviderNetworkError(f"{source}: upstream {resp.status_code}")


class SupadataProvider(TranscriptProvider):
    """Hosted captions with AI fallback — handles caption-less videos too."""

    handles_missing = True

    def __init__(self, api_key: str, timeout: float = 25.0):
        self._api_key = api_key
        self._timeout = timeout

    def get_transcript(self, video_id: str, lang: str = "en") -> TranscriptResult:
        try:
            resp = httpx.get(
                "https://api.supadata.ai/v1/transcript",
                params={"url": f"https://www.youtube.com/watch?v={video_id}", "lang": lang},
                headers={"x-api-key": self._api_key},
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            raise ProviderNetworkError(f"supadata unreachable: {exc}") from exc

        _map_hosted_status(resp, "supadata")
        if resp.status_code != 200:
            raise TranscriptsNotFound(f"supadata: unexpected {resp.status_code}")

        data = _json_or_raise(resp, "supadata")
        if data.get("error"):
            _raise_hosted_error("supadata", data["error"])

        content = data.get("content")
        segments = []
        if isinstance(content, list):
            for entry in content:
                if not isinstance(entry, dict):
                    continue
                text = str(entry.get("text") or "").replace("\n", " ").strip()
                if not text:
                    continue
                segments.append(
                    {
                        "start": float(entry.get("offset") or 0.0) / 1000.0,
                        "duration": float(entry.get("duration") or 0.0) / 1000.0,
                        "text": text,
                    }
                )
        if not segments:
            raise TranscriptsNotFound("supadata: no segments")

        return TranscriptResult(
            video_id=video_id,
            language=str(data.get("lang") or lang),
            segments=segments,
            title=get_title(video_id),
        )


def _normalize_serpapi(entries: list) -> list:
    unit = os.getenv("SERPAPI_TIME_UNIT", "auto").strip().lower()
    starts, durations = [], []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        try:
            starts.append(float(entry.get("start", entry.get("offset", 0)) or 0))
            durations.append(float(entry.get("duration", 0) or 0))
        except (TypeError, ValueError):
            continue
    if unit in ("", "auto"):
        # seconds-based caption segments never reach 100s; ms-based rarely drop below 100ms
        unit = "ms" if (max(starts, default=0) > 50000 or max(durations, default=0) > 100) else "seconds"
    divisor = 1000.0 if unit in ("ms", "milliseconds") else 1.0

    segments = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        text = str(entry.get("text") or "").replace("\n", " ").strip()
        if not text:
            continue
        try:
            start = float(entry.get("start", entry.get("offset", 0)) or 0) / divisor
            duration = float(entry.get("duration", 0) or 0) / divisor
        except (TypeError, ValueError):
            start, duration = 0.0, 0.0
        segments.append({"start": start, "duration": duration, "text": text})
    return segments


class SerpApiProvider(TranscriptProvider):
    """Last-resort hosted captions — no AI fallback, skipped on upstream not-found."""

    handles_missing = False

    def __init__(self, api_key: str, timeout: float = 15.0):
        self._api_key = api_key
        self._timeout = timeout

    def get_transcript(self, video_id: str, lang: str = "en") -> TranscriptResult:
        try:
            resp = httpx.get(
                "https://serpapi.com/search",
                params={
                    "api_key": self._api_key,
                    "engine": "youtube_video_transcript",
                    "v": video_id,
                    "language_code": lang,
                },
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            raise ProviderNetworkError(f"serpapi unreachable: {exc}") from exc

        _map_hosted_status(resp, "serpapi")
        if resp.status_code != 200:
            raise TranscriptsNotFound(f"serpapi: unexpected {resp.status_code}")

        data = _json_or_raise(resp, "serpapi")
        if data.get("error"):
            _raise_hosted_error("serpapi", data["error"])

        entries = data.get("transcripts")
        if not isinstance(entries, list) or not entries:
            plain = data.get("text") or data.get("transcript")
            if isinstance(plain, str) and plain.strip():
                entries = [{"text": plain, "start": 0, "duration": 0}]
        segments = _normalize_serpapi(entries if isinstance(entries, list) else [])
        if not segments:
            raise TranscriptsNotFound("serpapi: no transcripts")

        first = entries[0] if entries and isinstance(entries[0], dict) else {}
        language = str(data.get("language_code") or first.get("lang") or lang)
        return TranscriptResult(
            video_id=video_id,
            language=language,
            segments=segments,
            title=get_title(video_id),
        )


_BLOCK_NAMES = {
    "IpBlocked",
    "RequestBlocked",
    "FailedToCreateConsentCookie",
    "PoTokenRequired",
    "YouTubeRequestFailed",
    "YouTubeDataUnparsable",
    "TooManyRequests",
}
_MISSING_NAMES = {
    "TranscriptsDisabled",
    "NoTranscriptFound",
    "NotTranslatable",
    "TranslationLanguageNotAvailable",
}
_TERMINAL_NAMES = {"VideoUnavailable", "VideoUnplayable", "AgeRestricted"}


def _looks_missing(exc: Exception) -> bool:
    if isinstance(exc, TranscriptError):
        return exc.detail == "no_captions"
    name = type(exc).__name__
    msg = str(exc).lower()
    if name in _BLOCK_NAMES or "blocking requests" in msg or ("ip" in msg and "block" in msg):
        return False
    if name in _MISSING_NAMES or "transcripts disabled" in msg or "no transcript" in msg or "could not retrieve" in msg:
        return True
    return False


def _is_terminal(exc: Exception) -> bool:
    if isinstance(exc, TranscriptError):
        return False
    name = type(exc).__name__
    return name in _TERMINAL_NAMES or "video unavailable" in str(exc).lower()


class FallbackProvider(TranscriptProvider):
    """Walks chain levels in order; not-found narrows remaining to handles_missing."""

    def __init__(self, levels: list):
        self._levels = list(levels)

    def get_transcript(self, video_id: str, lang: str = "en") -> TranscriptResult:
        pending = list(self._levels)
        last_error: Exception | None = None

        while pending:
            level = pending.pop(0)
            name = type(level).__name__
            try:
                result = level.get_transcript(video_id, lang=lang)
                if result.segments:
                    logger.info(
                        "transcript served by %s video_id=%s segments=%d",
                        name,
                        video_id,
                        len(result.segments),
                    )
                    return result
                last_error = TranscriptsNotFound(f"{name} returned no segments")
            except Exception as exc:
                last_error = exc

            logger.warning(
                "level %s failed video_id=%s: %s: %s",
                name,
                video_id,
                type(last_error).__name__,
                last_error,
            )
            if _is_terminal(last_error):
                raise last_error
            if _looks_missing(last_error):
                pending = [p for p in pending if p.handles_missing]

        if last_error is None:
            raise TranscriptError("chain exhausted without an error")
        raise last_error


_CHAIN_DEFAULT = "direct,supadata,serpapi"
_KNOWN_LEVELS = ("direct", "supadata", "serpapi")


def _parse_chain_order() -> list:
    raw = os.getenv("CHAIN_ORDER", _CHAIN_DEFAULT)
    seen, order = set(), []
    for part in raw.split(","):
        name = part.strip().lower()
        if name in _KNOWN_LEVELS and name not in seen:
            seen.add(name)
            order.append(name)
    return order


def build_provider() -> TranscriptProvider:
    levels: list[TranscriptProvider] = []
    for name in _parse_chain_order():
        if name == "direct":
            if env_truthy(os.getenv("DIRECT_ENABLED"), True):
                levels.append(CaptionProvider())
        elif name == "supadata":
            key = os.getenv("SUPADATA_API_KEY", "").strip()
            if key and env_truthy(os.getenv("SUPADATA_ENABLED"), True):
                levels.append(SupadataProvider(key))
        elif name == "serpapi":
            key = os.getenv("SERPAPI_API_KEY", "").strip()
            if key and env_truthy(os.getenv("SERPAPI_ENABLED"), False):
                levels.append(SerpApiProvider(key))

    if not levels:
        logger.warning(
            "chain empty (CHAIN_ORDER=%s) — falling back to direct captions only",
            ",".join(_parse_chain_order()),
        )
        return CaptionProvider()
    if len(levels) == 1:
        return levels[0]
    return FallbackProvider(levels)
