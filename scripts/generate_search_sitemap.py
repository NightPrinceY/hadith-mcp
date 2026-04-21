#!/usr/bin/env python3
"""Generate search.hadith-mcp.org sitemap index + per-collection urlsets from hadith.db.

Run once after DB changes, from repo root:
  python3 scripts/generate_search_sitemap.py

Output:
  search/sitemap.xml              — sitemap index
  search/sitemaps/sitemap-pages.xml — homepage only
  search/sitemaps/sitemap-{slug}.xml — one file per collection (~50k URLs total)
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "hadith.db"
DEFAULT_OUT_DIR = ROOT / "search" / "sitemaps"
DEFAULT_INDEX = ROOT / "search" / "sitemap.xml"
BASE = "https://search.hadith-mcp.org"
URLSET_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
SITEMAPINDEX_NS = URLSET_NS

HIGH_PRIORITY_COLLECTIONS = frozenset({"bukhari", "muslim"})


def url_entry(loc: str, changefreq: str, priority: str) -> str:
    return (
        f"  <url>\n"
        f"    <loc>{escape(loc)}</loc>\n"
        f"    <changefreq>{changefreq}</changefreq>\n"
        f"    <priority>{priority}</priority>\n"
        f"  </url>\n"
    )


def write_urlset(path: Path, urls: list[tuple[str, str, str]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write(f'<urlset xmlns="{URLSET_NS}">\n')
        for loc, changefreq, priority in urls:
            f.write(url_entry(loc, changefreq, priority))
        f.write("</urlset>\n")
    return len(urls)


def write_sitemap_index(path: Path, locs: list[str]) -> None:
    with path.open("w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write(f'<sitemapindex xmlns="{SITEMAPINDEX_NS}">\n')
        for loc in locs:
            f.write("  <sitemap>\n")
            f.write(f"    <loc>{escape(loc)}</loc>\n")
            f.write("  </sitemap>\n")
        f.write("</sitemapindex>\n")


def main() -> int:
    p = argparse.ArgumentParser(description="Generate search frontend sitemaps from hadith.db")
    p.add_argument("--db-path", type=Path, default=DEFAULT_DB, help="Path to hadith.db")
    p.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help="Directory for sitemap-*.xml urlsets (default: search/sitemaps/)",
    )
    p.add_argument(
        "--index-path",
        type=Path,
        default=DEFAULT_INDEX,
        help="Path for sitemap index (default: search/sitemap.xml)",
    )
    p.add_argument(
        "--base-url",
        default=BASE,
        help="Canonical origin for search URLs (default: https://search.hadith-mcp.org)",
    )
    args = p.parse_args()
    base = args.base_url.rstrip("/")

    if not args.db_path.is_file():
        print(f"error: database not found: {args.db_path}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(args.db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.execute(
        """
        SELECT h.id AS hadith_id, c.slug AS collection_slug
        FROM hadiths h
        JOIN collections c ON c.id = h.collection_id
        ORDER BY c.slug, h.id
        """
    )
    by_slug: dict[str, list[int]] = defaultdict(list)
    for row in cur:
        by_slug[row["collection_slug"]].append(int(row["hadith_id"]))
    conn.close()

    args.out_dir.mkdir(parents=True, exist_ok=True)

    # Homepage
    pages_path = args.out_dir / "sitemap-pages.xml"
    n_pages = write_urlset(
        pages_path,
        [(f"{base}/", "weekly", "1.0")],
    )

    sub_sitemap_locs: list[str] = [f"{base}/sitemaps/sitemap-pages.xml"]
    total_urls = n_pages

    for slug in sorted(by_slug.keys()):
        ids = by_slug[slug]
        priority = "0.7" if slug in HIGH_PRIORITY_COLLECTIONS else "0.6"
        urls = [(f"{base}/?id={hid}", "monthly", priority) for hid in ids]
        out_path = args.out_dir / f"sitemap-{slug}.xml"
        n = write_urlset(out_path, urls)
        total_urls += n
        sub_sitemap_locs.append(f"{base}/sitemaps/sitemap-{slug}.xml")
        print(f"  wrote {out_path.relative_to(ROOT)}  ({n} urls)")

    write_sitemap_index(args.index_path, sub_sitemap_locs)

    print()
    print(f"  wrote {pages_path.relative_to(ROOT)}  ({n_pages} urls)")
    print(f"  wrote {args.index_path.relative_to(ROOT)}  (index with {len(sub_sitemap_locs)} sitemaps)")
    print()
    print(f"total url entries across all files: {total_urls}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
