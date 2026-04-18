"""Assign provenance tags from cross-reference graph."""

from __future__ import annotations

import sqlite3
from collections import defaultdict

BUKHARI = 1
MUSLIM = 2


def _build_graph(conn: sqlite3.Connection) -> dict[int, set[int]]:
    cur = conn.cursor()
    cur.execute("SELECT hadith_id, matched_hadith_id FROM cross_references")
    g: dict[int, set[int]] = defaultdict(set)
    for lo, hi in cur.fetchall():
        lo, hi = int(lo), int(hi)
        g[lo].add(hi)
        g[hi].add(lo)
    return g


def assign_provenance(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.execute("SELECT id, collection_id FROM hadiths")
    hadith_coll = {int(r[0]): int(r[1]) for r in cur.fetchall()}
    graph = _build_graph(conn)

    def partner_collections(hid: int) -> set[int]:
        return {hadith_coll[p] for p in graph.get(hid, ()) if p in hadith_coll}

    updates: list[tuple[str | None, int]] = []
    for hid, coll in hadith_coll.items():
        pc = partner_collections(hid)
        tag: str | None = None
        if coll == BUKHARI and MUSLIM in pc:
            tag = "muttafaq_alayh"
        elif coll == MUSLIM and BUKHARI in pc:
            tag = "muttafaq_alayh"
        elif coll == BUKHARI:
            tag = "bukhari"
        elif coll == MUSLIM:
            tag = "muslim"
        elif coll not in (BUKHARI, MUSLIM) and (BUKHARI in pc or MUSLIM in pc):
            tag = "corroborated"
        elif coll not in (BUKHARI, MUSLIM) and pc and not (pc & {BUKHARI, MUSLIM}):
            tag = "cross_referenced"
        updates.append((tag, hid))

    cur.executemany("UPDATE hadiths SET provenance = ? WHERE id = ?", updates)
    conn.commit()
