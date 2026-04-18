"""Static registry of collections matching hadith-json book ids."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BookPath:
    collection_id: int
    slug: str
    relative_path: str  # under db/by_book/


# Order matches hadith-json / Sunnah.com book ids (1–17).
BOOK_FILES: tuple[BookPath, ...] = (
    BookPath(1, "bukhari", "the_9_books/bukhari.json"),
    BookPath(2, "muslim", "the_9_books/muslim.json"),
    BookPath(3, "nasai", "the_9_books/nasai.json"),
    BookPath(4, "abudawud", "the_9_books/abudawud.json"),
    BookPath(5, "tirmidhi", "the_9_books/tirmidhi.json"),
    BookPath(6, "ibnmajah", "the_9_books/ibnmajah.json"),
    BookPath(7, "malik", "the_9_books/malik.json"),
    BookPath(8, "ahmed", "the_9_books/ahmed.json"),
    BookPath(9, "darimi", "the_9_books/darimi.json"),
    BookPath(10, "nawawi40", "forties/nawawi40.json"),
    BookPath(11, "qudsi40", "forties/qudsi40.json"),
    BookPath(12, "shahwaliullah40", "forties/shahwaliullah40.json"),
    BookPath(13, "riyad_assalihin", "other_books/riyad_assalihin.json"),
    BookPath(14, "mishkat_almasabih", "other_books/mishkat_almasabih.json"),
    BookPath(15, "aladab_almufrad", "other_books/aladab_almufrad.json"),
    BookPath(16, "shamail_muhammadiyah", "other_books/shamail_muhammadiyah.json"),
    BookPath(17, "bulugh_almaram", "other_books/bulugh_almaram.json"),
)


def resolve_book_path(by_book_root: Path, bp: BookPath) -> Path:
    return by_book_root / bp.relative_path
