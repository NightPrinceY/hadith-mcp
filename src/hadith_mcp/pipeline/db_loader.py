"""Insert normalized rows into SQLite."""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

from hadith_mcp.pipeline.load_books import LoadedChapter, LoadedCollection, LoadedHadith
from hadith_mcp.pipeline.schema import apply_schema

if TYPE_CHECKING:
    pass


def init_db(conn: sqlite3.Connection) -> None:
    apply_schema(conn)


def insert_collections(conn: sqlite3.Connection, collections: list[LoadedCollection]) -> None:
    cur = conn.cursor()
    cur.executemany(
        """
        INSERT OR REPLACE INTO collections
        (id, slug, name_english, name_arabic, author_english, author_arabic, hadith_count)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                c.id,
                c.slug,
                c.name_english,
                c.name_arabic,
                c.author_english,
                c.author_arabic,
                c.hadith_count,
            )
            for c in collections
        ],
    )
    conn.commit()


def insert_chapters(
    conn: sqlite3.Connection, chapters: list[LoadedChapter]
) -> dict[tuple[int, int], int]:
    """Return map (collection_id, source_chapter_id) -> chapters.id row."""
    cur = conn.cursor()
    for ch in chapters:
        cur.execute(
            """
            INSERT INTO chapters (collection_id, source_chapter_id, name_english, name_arabic)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(collection_id, source_chapter_id) DO UPDATE SET
                name_english = excluded.name_english,
                name_arabic = excluded.name_arabic
            """,
            (ch.collection_id, ch.source_chapter_id, ch.name_english, ch.name_arabic),
        )
    conn.commit()
    key_to_row: dict[tuple[int, int], int] = {}
    cur.execute("SELECT id, collection_id, source_chapter_id FROM chapters")
    for row_id, coll_id, src in cur.fetchall():
        key_to_row[(int(coll_id), int(src))] = int(row_id)
    return key_to_row


def insert_hadiths(
    conn: sqlite3.Connection,
    hadiths: list[LoadedHadith],
    chapter_key_to_row: dict[tuple[int, int], int],
) -> None:
    cur = conn.cursor()
    rows = []
    for h in hadiths:
        ch_row = chapter_key_to_row.get((h.collection_id, h.chapter_source_id))
        rows.append(
            (
                h.id,
                h.id_in_book,
                h.collection_id,
                ch_row,
                h.arabic,
                h.narrator,
                h.english,
                None,
                None,
            )
        )
    cur.executemany(
        """
        INSERT OR REPLACE INTO hadiths
        (id, id_in_book, collection_id, chapter_id, arabic, narrator, english, provenance, embedding)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
