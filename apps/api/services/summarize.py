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

# Bump when the prompt changes; it is part of the summary cache key so old
# cached summaries are never served under a new prompt.
PROMPT_VERSION = "v1"

DEFAULT_MAX_CHARS = 15_000
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_MAX_OUTPUT_TOKENS = 350
TRUNCATION_MARKER = "\n[... transcript truncated for summarization ...]"

SYSTEM_PROMPT = (
    "You summarize YouTube video transcripts for a quick read. "
    "Reply in plain text with no markdown headings: first a line starting "
    '"TL;DR: " with one sentence, then a blank line, then 3-5 bullet points '
    'starting with "• ". Keep the whole answer under 120 words.'
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
        transport: Optional[httpx.BaseTransport] = None,
    ):
        self._endpoint = base_url.rstrip("/") + "/chat/completions"
        self._api_key = api_key
        self.model = model
        self._timeout = timeout_seconds
        self._max_chars = max_chars
        self._max_output_tokens = max_output_tokens
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
            content = response.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise SummaryError("summary_failed", "malformed upstream response") from exc

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
    )
    logger.info(
        "summary generation enabled: model=%s max_chars=%d timeout=%ds",
        summarizer.model,
        summarizer._max_chars,
        summarizer._timeout,
    )
    return summarizer
