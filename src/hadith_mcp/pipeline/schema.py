"""SQLite schema for hadith.db."""

from __future__ import annotations

SCHEMA_SQL = """
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS collections (
    id INTEGER PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    name_english TEXT NOT NULL,
    name_arabic TEXT NOT NULL,
    author_english TEXT,
    author_arabic TEXT,
    hadith_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS chapters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    collection_id INTEGER NOT NULL REFERENCES collections(id),
    source_chapter_id INTEGER NOT NULL,
    name_english TEXT,
    name_arabic TEXT,
    UNIQUE(collection_id, source_chapter_id)
);

CREATE TABLE IF NOT EXISTS hadiths (
    id INTEGER PRIMARY KEY,
    id_in_book INTEGER NOT NULL,
    collection_id INTEGER NOT NULL REFERENCES collections(id),
    chapter_id INTEGER REFERENCES chapters(id),
    arabic TEXT NOT NULL,
    narrator TEXT,
    english TEXT NOT NULL,
    provenance TEXT,
    embedding BLOB,
    UNIQUE(collection_id, id_in_book)
);

CREATE TABLE IF NOT EXISTS cross_references (
    hadith_id INTEGER NOT NULL REFERENCES hadiths(id),
    matched_hadith_id INTEGER NOT NULL REFERENCES hadiths(id),
    similarity REAL NOT NULL,
    narrator_match INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (hadith_id, matched_hadith_id)
);

CREATE INDEX IF NOT EXISTS idx_hadiths_collection ON hadiths(collection_id);
CREATE INDEX IF NOT EXISTS idx_hadiths_provenance ON hadiths(provenance);
CREATE INDEX IF NOT EXISTS idx_hadiths_chapter ON hadiths(chapter_id);
CREATE INDEX IF NOT EXISTS idx_crossref_hadith ON cross_references(hadith_id);
CREATE INDEX IF NOT EXISTS idx_crossref_matched ON cross_references(matched_hadith_id);
"""


def apply_schema(conn) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.commit()
