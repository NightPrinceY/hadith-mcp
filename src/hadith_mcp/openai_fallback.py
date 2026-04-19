"""Decide when semantic search should fall back to keyword (quota, billing, errors)."""

from __future__ import annotations

from openai import APIConnectionError, APIStatusError, AuthenticationError, RateLimitError


def should_fallback_to_keyword(exc: BaseException) -> bool:
    """True when OpenAI is unavailable or the account cannot bill — try keyword search instead."""
    if isinstance(exc, (APIConnectionError, RateLimitError, AuthenticationError)):
        return True
    if isinstance(exc, APIStatusError):
        if exc.status_code in (401, 402, 403, 429, 500, 502, 503, 504):
            return True
    msg = str(exc).lower()
    needles = (
        "insufficient_quota",
        "billing",
        "exceeded your current quota",
        "you exceeded your current quota",
        "credit balance is too low",
        "payment required",
        "invalid_api_key",
        "incorrect api key",
    )
    return any(n in msg for n in needles)
