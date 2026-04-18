#!/usr/bin/env python3
"""Run cross-reference matching and provenance tagging on an existing hadith.db (embeddings must exist)."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from hadith_mcp.pipeline.crossref import find_cross_references
from hadith_mcp.pipeline.provenance import assign_provenance


def main() -> int:
    p = argparse.ArgumentParser(description="Compute cross_references + provenance (CPU-only)")
    p.add_argument("--db-path", type=Path, default=ROOT / "data" / "hadith.db")
    args = p.parse_args()
    if not args.db_path.is_file():
        print(f"ERROR: {args.db_path} not found", file=sys.stderr)
        return 1
    conn = sqlite3.connect(args.db_path)
    try:
        n = find_cross_references(conn)
        print(f"cross_reference_edges={n}")
        assign_provenance(conn)
        print("provenance assigned.")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
