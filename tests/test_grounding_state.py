"""Grounding nonce / repeat suppression."""

from __future__ import annotations

from hadith_mcp.grounding_state import GroundingState


def test_grounding_nonce_flow() -> None:
    g = GroundingState()
    a = g.fetch("sess-a", nonce=None, force_full=False, full_text="FULL RULES")
    assert a["rules"] == "FULL RULES"
    assert a["repeat_suppressed"] is False
    assert a["nonce"]

    b = g.fetch("sess-a", nonce=None, force_full=False, full_text="FULL RULES")
    assert b["rules"] is None
    assert b["repeat_suppressed"] is True
    assert b["nonce"] == a["nonce"]

    c = g.fetch("sess-a", nonce="wrong", force_full=False, full_text="FULL RULES")
    assert c.get("error") == "unknown_nonce"

    d = g.fetch("sess-a", nonce=None, force_full=True, full_text="FULL RULES")
    assert d["rules"] == "FULL RULES"
    assert d["repeat_suppressed"] is False
