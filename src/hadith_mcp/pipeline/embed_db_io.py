"""Load pending texts from SQLite for embedding-only runs."""

from __future__ import annotations

import sqlite3

from hadith_mcp.pipeline.load_books import embedding_input


def load_pending_embed_texts(conn: sqlite3.Connection) -> dict[int, str]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, narrator, english, arabic FROM hadiths
        WHERE embedding IS NULL
        ORDER BY id
        """
    )
    out: dict[int, str] = {}
    for hid, narr, eng, ar in cur.fetchall():
        out[int(hid)] = embedding_input(
            str(narr or ""),
            str(eng or ""),
            arabic=str(ar or ""),
        )
    return out
