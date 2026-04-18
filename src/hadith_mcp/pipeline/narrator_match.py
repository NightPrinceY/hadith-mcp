"""Fuzzy narrator matching for cross-reference boosting."""

from __future__ import annotations

import re
import unicodedata


def _normalize_narrator(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = s.lower()
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def narrators_match(a: str, b: str, *, min_ratio: float = 0.82) -> bool:
    """Return True if English narrator lines are likely the same speaker."""
    na, nb = _normalize_narrator(a), _normalize_narrator(b)
    if len(na) < 8 or len(nb) < 8:
        return False
    if na == nb:
        return True
    # Token-set style: require substantial overlap of prefix / substring
    if na in nb or nb in na:
        return True
    # Simple character overlap ratio (cheap Jaccard on chars)
    sa, sb = set(na), set(nb)
    inter = len(sa & sb)
    union = len(sa | sb) or 1
    return (inter / union) >= min_ratio
