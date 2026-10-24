"""On-demand transcript summarization.

One adapter for any OpenAI-compatible chat-completions endpoint, selected by
environment so the vendor can be swapped without touching the route or the
frontend:

    SUMMARY_BASE_URL   e.g. https://generativelanguage.googleapis.com/v1beta/openai
                            https://api.groq.com/openai/v1
                            https://openrouter.ai/api/v1
    SUMMARY_API_KEY    the provider key (never logged, never sent to clients)
    SUMMARY_MODEL      e.g. gemini-2.5-flash, llama-3.3-70b-versatile

When any of the three is missing, build_summarizer() returns None and the API
answers 503 summary_disabled. The transcript product keeps working — summary
is an optional capability, not a boot dependency.

The transcript text is capped deterministically before the request (see
truncate_for_prompt). Prompt/transcript content and raw upstream bodies are
never logged: only the video id is logged by the route, and this module logs
nothing beyond configuration state.
"""

from __future__ import annotations

import logging
import os
from typing import Optional, Protocol

import httpx

logger = logging.getLogger("shrutilipi")

# Bump when the prompt or generation behavior changes; it is part of the
# summary cache key so old cached summaries are never served under a new prompt.
# v2: 1024-token output cap (Gemini counts thinking tokens against
#     max_tokens) + same-language summaries.
# v3: disable Gemini thinking via reasoning_effort=none; reject any
#     case-variant of a length/max_tokens stop.
PROMPT_VERSION = "v3"

DEFAULT_MAX_CHARS = 15_000
DEFAULT_TIMEOUT_SECONDS = 30
# Kept as a safety ceiling even though thinking is off on Gemini: a runaway
# answer must never be billed without bound.
DEFAULT_MAX_OUTPUT_TOKENS = 1024
TRUNCATION_MARKER = "\n[... transcript truncated for summarization ...]"

# Google's OpenAI-compatible endpoint accepts `reasoning_effort: "none"` for
# Gemini 2.5, which stops thinking tokens from consuming the output budget.
GEMINI_HOST = "generativelanguage.googleapis.com"

SYSTEM_PROMPT = (
    "You summarize YouTube video transcripts for a quick read. "
    "Reply in plain text with no markdown headings: first a line starting "
    '"TL;DR: " with exactly one complete sentence, then a blank line, then '
    'exactly 3-5 bullet points starting with "• ". Keep the whole answer under '
    "120 words. Write the summary in the same language as the transcript. "
    "Never stop mid-sentence."
)


class SummaryError(Exception):
    """Upstream summarization failure. `detail` is a stable API code."""

    def __init__(self, detail: str = "summary_failed", message: str = ""):
        super().__init__(message or detail)
        self.detail = detail


class Summarizer(Protocol):
    model: str

    def summarize(self, plain_text: str) -> str: ...


def truncate_for_prompt(text: str, limit: int = DEFAULT_MAX_CHARS) -> str:
    """Deterministic head truncation, documented in docs/operations.md.

    Cuts at `limit` characters, backing up to the last whitespace so a word is
    not split. The tail of long transcripts is not sent — the marker makes
    that visible to the model and to anyone debugging a summary.
    """
    if len(text) <= limit:
        return text
    head = text[:limit]
    boundary = head.rfind(" ")
    if boundary > 0:
        head = head[:boundary]
    return head.rstrip() + TRUNCATION_MARKER


def _env_int(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def default_reasoning_effort(base_url: str) -> Optional[str]:
    """Thinking is off by default on Gemini; other vendors keep their default.

    Gemini 2.5 counts thinking tokens toward max_tokens, so on a short summary
    task it can spend the whole budget before writing the visible answer.
    """
    return "none" if GEMINI_HOST in base_url else None


def _env_reasoning_effort(base_url: str) -> Optional[str]:
    """SUMMARY_REASONING_EFFORT wins; unset means the per-vendor default.

    An explicitly empty value (e.g. `SUMMARY_REASONING_EFFORT=`) opts out and
    sends no field at all, which matters for providers that reject unknown
    parameters.
    """
    raw = os.getenv("SUMMARY_REASONING_EFFORT")
    if raw is None:
        return default_reasoning_effort(base_url)
    return raw.strip() or None


class OpenAICompatibleSummarizer:
    """POST {base}/chat/completions — works with any OpenAI-compatible server."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        max_chars: int = DEFAULT_MAX_CHARS,
        max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
        reasoning_effort: Optional[str] = None,
        transport: Optional[httpx.BaseTransport] = None,
    ):
        self._endpoint = base_url.rstrip("/") + "/chat/completions"
        self._api_key = api_key
        self.model = model
        self._timeout = timeout_seconds
        self._max_chars = max_chars
        self._max_output_tokens = max_output_tokens
        self._reasoning_effort = reasoning_effort
        self._transport = transport

    def summarize(self, plain_text: str) -> str:
        text = truncate_for_prompt(plain_text, self._max_chars)
        if not text.strip():
            raise SummaryError("summary_failed", "empty transcript")

        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Transcript:\n\n{text}"},
            ],
            "temperature": 0.2,
            "max_tokens": self._max_output_tokens,
        }
        if self._reasoning_effort:
            body["reasoning_effort"] = self._reasoning_effort
        try:
            with httpx.Client(timeout=self._timeout, transport=self._transport) as client:
                response = client.post(
                    self._endpoint,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                )
        except httpx.TimeoutException as exc:
            raise SummaryError("summary_failed", "upstream timeout") from exc
        except httpx.HTTPError as exc:
            raise SummaryError("summary_failed", "upstream transport error") from exc

        if response.status_code >= 400:
            # Status only: the body can echo request content or reveal details
            # that must not reach logs or clients.
            raise SummaryError("summary_failed", f"upstream status {response.status_code}")

        try:
            choice = response.json()["choices"][0]
            content = choice["message"]["content"]
            finish_reason = choice.get("finish_reason")
        except (ValueError, KeyError, IndexError, TypeError, AttributeError) as exc:
            raise SummaryError("summary_failed", "malformed upstream response") from exc

        # Some providers (notably Gemini Flash) count reasoning tokens toward
        # max_tokens, so a length stop can truncate the visible answer
        # mid-sentence. Never cache that: fail so the retry can succeed.
        # Normalize case: OpenAI says "length", Gemini may say "MAX_TOKENS".
        reason = str(finish_reason).lower() if finish_reason is not None else ""
        if reason in ("length", "max_tokens"):
            raise SummaryError("summary_failed", "upstream output truncated")

        if not isinstance(content, str) or not content.strip():
            raise SummaryError("summary_failed", "empty upstream response")
        return content.strip()


def build_summarizer() -> Optional[OpenAICompatibleSummarizer]:
    """Env factory. None means the capability is off (503 summary_disabled)."""
    base_url = os.getenv("SUMMARY_BASE_URL", "").strip()
    api_key = os.getenv("SUMMARY_API_KEY", "").strip()
    model = os.getenv("SUMMARY_MODEL", "").strip()
    if not (base_url and api_key and model):
        logger.info(
            "summary generation disabled: set SUMMARY_BASE_URL, SUMMARY_API_KEY "
            "and SUMMARY_MODEL to enable it"
        )
        return None

    summarizer = OpenAICompatibleSummarizer(
        base_url=base_url,
        api_key=api_key,
        model=model,
        timeout_seconds=_env_int("SUMMARY_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS),
        max_chars=_env_int("SUMMARY_MAX_CHARS", DEFAULT_MAX_CHARS),
        max_output_tokens=_env_int("SUMMARY_MAX_OUTPUT_TOKENS", DEFAULT_MAX_OUTPUT_TOKENS),
        reasoning_effort=_env_reasoning_effort(base_url),
    )
    logger.info(
        "summary generation enabled: model=%s max_chars=%d timeout=%ds reasoning_effort=%s",
        summarizer.model,
        summarizer._max_chars,
        summarizer._timeout,
        summarizer._reasoning_effort or "provider-default",
    )
    return summarizer
