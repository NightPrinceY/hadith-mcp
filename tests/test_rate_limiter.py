"""Sliding-window rate limiter."""

from __future__ import annotations

import time

from hadith_mcp.rate_limit import RateLimiter


def test_rate_limiter_allows_then_blocks() -> None:
    rl = RateLimiter(2)
    assert rl.allow("a")
    assert rl.allow("a")
    assert not rl.allow("a")
    assert rl.allow("b")


def test_rate_limiter_disabled() -> None:
    rl = RateLimiter(None)
    for _ in range(5):
        assert rl.allow("x")


def test_rate_limiter_window_refreshes(monkeypatch) -> None:
    rl = RateLimiter(1)
    t = [0.0]

    def fake_monotonic() -> float:
        return t[0]

    monkeypatch.setattr(time, "monotonic", fake_monotonic)
    assert rl.allow("u")
    assert not rl.allow("u")
    t[0] += 61.0
    assert rl.allow("u")
