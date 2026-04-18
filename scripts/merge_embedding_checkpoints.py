#!/usr/bin/env python3
"""Merge JSONL embedding checkpoints into hadith.db (idempotent, safe after crashes)."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from hadith_mcp.pipeline.checkpoint import iter_checkpoint_embeddings


def main() -> int:
    p = argparse.ArgumentParser(
        description="Apply embedding blobs from JSONL checkpoint(s) into SQLite hadiths.embedding"
    )
    p.add_argument(
        "--db-path",
        type=Path,
        default=ROOT / "data" / "hadith.db",
        help="SQLite database built by build_db.py",
    )
    p.add_argument(
        "checkpoints",
        nargs="+",
        type=Path,
        help="One or more .jsonl files written during embedding (append-only)",
    )
    p.add_argument(
        "--only-missing",
        action="store_true",
        help="UPDATE only rows where embedding IS NULL (default: overwrite all matched ids)",
    )
    args = p.parse_args()

    if not args.db_path.is_file():
        print(f"ERROR: database not found: {args.db_path}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(args.db_path)
    try:
        cur = conn.cursor()
        n = 0
        for ck in args.checkpoints:
            if not ck.is_file():
                print(f"WARN: skip missing file {ck}", file=sys.stderr)
                continue
            n_ck = 0
            for hid, blob in iter_checkpoint_embeddings(ck):
                if args.only_missing:
                    cur.execute("SELECT embedding FROM hadiths WHERE id = ?", (hid,))
                    row = cur.fetchone()
                    if row and row[0] is not None:
                        continue
                cur.execute("UPDATE hadiths SET embedding = ? WHERE id = ?", (blob, hid))
                if cur.rowcount:
                    n_ck += 1
            conn.commit()
            n += n_ck
            print(f"Merged from {ck} rows_updated={n_ck} (cumulative={n})")
    finally:
        conn.close()

    print(f"Done. Rows updated this run: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
