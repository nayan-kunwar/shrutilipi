"""Unit tests for services/summarize.py. No network.

Run from apps/api with: python -m pytest -q
"""

import httpx
import pytest

from services.summarize import (
    PROMPT_VERSION,
    OpenAICompatibleSummarizer,
    SummaryError,
    build_summarizer,
    truncate_for_prompt,
)


def _summarizer(handler, **kwargs):
    return OpenAICompatibleSummarizer(
        base_url="https://llm.example/v1",
        api_key="test-key",
        model="test-model",
        transport=httpx.MockTransport(handler),
        **kwargs,
    )


# --- truncation (deterministic policy) -------------------------------------


def test_short_text_is_untouched():
    assert truncate_for_prompt("short text", limit=100) == "short text"


def test_long_text_cuts_at_last_word_boundary():
    out = truncate_for_prompt("alpha beta gamma delta", limit=15)
    assert out.startswith("alpha beta")
    assert not out.startswith("alpha beta gamm")
    assert out.endswith("truncated for summarization ...]")
    assert "delta" not in out  # the tail is deliberately not sent


def test_long_text_without_whitespace_falls_back_to_hard_cut():
    out = truncate_for_prompt("x" * 100, limit=10)
    assert out.startswith("x" * 10)
    assert "truncated" in out


def test_truncation_is_deterministic():
    text = "word " * 5000
    assert truncate_for_prompt(text) == truncate_for_prompt(text)


# --- env factory ------------------------------------------------------------


def test_build_summarizer_disabled_when_any_setting_is_missing(monkeypatch):
    for var in ("SUMMARY_BASE_URL", "SUMMARY_API_KEY", "SUMMARY_MODEL"):
        monkeypatch.delenv(var, raising=False)
    assert build_summarizer() is None

    monkeypatch.setenv("SUMMARY_BASE_URL", "https://llm.example/v1")
    monkeypatch.setenv("SUMMARY_API_KEY", "k")
    assert build_summarizer() is None  # model still missing

    monkeypatch.setenv("SUMMARY_MODEL", "m")
    assert build_summarizer() is not None


def test_build_summarizer_parses_limits(monkeypatch):
    monkeypatch.setenv("SUMMARY_BASE_URL", "https://llm.example/v1")
    monkeypatch.setenv("SUMMARY_API_KEY", "k")
    monkeypatch.setenv("SUMMARY_MODEL", "m")
    monkeypatch.setenv("SUMMARY_MAX_CHARS", "1234")
    monkeypatch.setenv("SUMMARY_MAX_OUTPUT_TOKENS", "99")
    monkeypatch.setenv("SUMMARY_TIMEOUT_SECONDS", "7")
    s = build_summarizer()
    assert s is not None
    assert (s.model, s._max_chars, s._max_output_tokens, s._timeout) == (
        "m",
        1234,
        99,
        7,
    )


def test_build_summarizer_garbage_limits_fall_back(monkeypatch):
    monkeypatch.setenv("SUMMARY_BASE_URL", "https://llm.example/v1")
    monkeypatch.setenv("SUMMARY_API_KEY", "k")
    monkeypatch.setenv("SUMMARY_MODEL", "m")
    monkeypatch.setenv("SUMMARY_MAX_CHARS", "lots")
    monkeypatch.setenv("SUMMARY_TIMEOUT_SECONDS", "-1")
    s = build_summarizer()
    assert s is not None
    assert s._max_chars == 15_000
    assert s._timeout == 30
    assert s._max_output_tokens == 1024


def _configure(monkeypatch, base_url):
    monkeypatch.setenv("SUMMARY_BASE_URL", base_url)
    monkeypatch.setenv("SUMMARY_API_KEY", "k")
    monkeypatch.setenv("SUMMARY_MODEL", "m")
    monkeypatch.delenv("SUMMARY_REASONING_EFFORT", raising=False)


def test_gemini_disables_thinking_by_default(monkeypatch):
    # Gemini counts thinking tokens toward max_tokens; the summary task does
    # not need reasoning, so the adapter opts out explicitly.
    _configure(monkeypatch, "https://generativelanguage.googleapis.com/v1beta/openai")
    s = build_summarizer()
    assert s is not None
    assert s._reasoning_effort == "none"


def test_non_gemini_sends_no_reasoning_field_by_default(monkeypatch):
    # Unknown OpenAI-compatible servers may reject the field; only send it
    # when the vendor is known to support it or the operator asks for it.
    _configure(monkeypatch, "https://llm.example/v1")
    s = build_summarizer()
    assert s is not None
    assert s._reasoning_effort is None


def test_reasoning_effort_env_overrides_the_vendor_default(monkeypatch):
    _configure(monkeypatch, "https://llm.example/v1")
    monkeypatch.setenv("SUMMARY_REASONING_EFFORT", "high")
    s = build_summarizer()
    assert s is not None
    assert s._reasoning_effort == "high"


def test_blank_reasoning_effort_opts_out_even_on_gemini(monkeypatch):
    _configure(monkeypatch, "https://generativelanguage.googleapis.com/v1beta/openai")
    monkeypatch.setenv("SUMMARY_REASONING_EFFORT", "")
    s = build_summarizer()
    assert s is not None
    assert s._reasoning_effort is None


# --- adapter -----------------------------------------------------------------


def test_summarize_parses_content_and_sends_expected_request():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = request.read().decode()
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "  TL;DR: ok\n\n• one  "}}]},
        )

    out = _summarizer(handler).summarize("hello transcript")
    assert out == "TL;DR: ok\n\n• one"
    assert seen["url"] == "https://llm.example/v1/chat/completions"
    assert seen["auth"] == "Bearer test-key"
    assert '"model":"test-model"' in seen["body"].replace(" ", "")
    assert "hello transcript" in seen["body"]
    assert "TL;DR" in seen["body"]  # prompt asks for the agreed format


def test_summarize_sends_reasoning_effort_when_configured():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.read().decode()
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    _summarizer(handler, reasoning_effort="none").summarize("hello")
    assert '"reasoning_effort":"none"' in seen["body"].replace(" ", "")


def test_summarize_omits_reasoning_effort_when_unset():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.read().decode()
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    _summarizer(handler).summarize("hello")
    assert "reasoning_effort" not in seen["body"]


def test_summarize_sends_truncated_transcript():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.read().decode()
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    long_text = "alpha " * 1000 + "UNIQUE_TAIL"
    _summarizer(handler, max_chars=50).summarize(long_text)
    assert "UNIQUE_TAIL" not in seen["body"]
    assert "truncated for summarization" in seen["body"]


def test_summarize_upstream_status_is_summary_failed():
    def handler(request):
        return httpx.Response(500, json={"error": "secret upstream details"})

    with pytest.raises(SummaryError) as info:
        _summarizer(handler).summarize("hello")
    assert info.value.detail == "summary_failed"
    assert "secret upstream details" not in str(info.value)


def test_summarize_malformed_json_is_summary_failed():
    def handler(request):
        return httpx.Response(200, text="not json")

    with pytest.raises(SummaryError):
        _summarizer(handler).summarize("hello")


def test_summarize_missing_choices_is_summary_failed():
    def handler(request):
        return httpx.Response(200, json={"choices": []})

    with pytest.raises(SummaryError):
        _summarizer(handler).summarize("hello")


def test_summarize_empty_content_is_summary_failed():
    def handler(request):
        return httpx.Response(200, json={"choices": [{"message": {"content": "   "}}]})

    with pytest.raises(SummaryError):
        _summarizer(handler).summarize("hello")


def test_summarize_timeout_is_summary_failed():
    def handler(request):
        raise httpx.TimeoutException("too slow")

    with pytest.raises(SummaryError) as info:
        _summarizer(handler, timeout_seconds=1).summarize("hello")
    assert info.value.detail == "summary_failed"


def test_summarize_transport_error_is_summary_failed():
    def handler(request):
        raise httpx.ConnectError("no route")

    with pytest.raises(SummaryError):
        _summarizer(handler).summarize("hello")


@pytest.mark.parametrize("finish_reason", ["length", "max_tokens", "MAX_TOKENS", "Length"])
def test_summarize_truncated_finish_is_summary_failed(finish_reason):
    # Gemini counts thinking tokens toward max_tokens; a length stop means the
    # visible answer was cut off mid-sentence and must not be cached. Providers
    # spell the reason differently and in different cases.
    def handler(request):
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {"content": "TL;DR: cut off mid-sen"},
                        "finish_reason": finish_reason,
                    }
                ]
            },
        )

    with pytest.raises(SummaryError) as info:
        _summarizer(handler).summarize("hello")
    assert info.value.detail == "summary_failed"
    assert "truncated" in str(info.value)


def test_prompt_version_is_part_of_the_contract():
    # The route puts this in the cache key; it must change when the prompt or
    # generation settings do.
    assert PROMPT_VERSION == "v3"
