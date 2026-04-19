from hadith_mcp.query_cache import SearchResponseCache


def test_query_cache_lru() -> None:
    c = SearchResponseCache(2)
    c.set(("a",), 1)
    c.set(("b",), 2)
    c.get(("a",))
    c.set(("c",), 3)
    assert c.get(("b",)) is None
    assert c.get(("a",)) == 1
    assert c.get(("c",)) == 3


def test_query_cache_zero_disabled() -> None:
    c = SearchResponseCache(0)
    c.set(("x",), 1)
    assert c.get(("x",)) is None
