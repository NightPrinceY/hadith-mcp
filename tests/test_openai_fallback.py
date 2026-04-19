"""OpenAI → keyword fallback heuristics."""

from __future__ import annotations

import httpx
from openai import APIStatusError, RateLimitError

from hadith_mcp.openai_fallback import should_fallback_to_keyword


def _resp(code: int = 429) -> httpx.Response:
    return httpx.Response(code, request=httpx.Request("POST", "https://api.openai.com/x"))


def test_rate_limit_error() -> None:
    assert should_fallback_to_keyword(RateLimitError(message="slow down", response=_resp(), body=None))


def test_api_status_quota_like() -> None:
    req = httpx.Request("POST", "https://api.openai.com/v1/embeddings")
    resp = httpx.Response(429, request=req)
    exc = APIStatusError("too many", response=resp, body=None)
    assert should_fallback_to_keyword(exc)


def test_message_insufficient_quota() -> None:
    assert should_fallback_to_keyword(RuntimeError('{"error":{"code":"insufficient_quota"}}'))


def test_no_fallback_on_random() -> None:
    assert not should_fallback_to_keyword(ValueError("not an api issue"))
