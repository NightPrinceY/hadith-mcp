#!/usr/bin/env python3
"""Resume-only OpenAI embedding for an existing hadith.db (no full rebuild)."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from openai import OpenAI

from hadith_mcp.pipeline.embed import EMBEDDING_MODEL, EmbedRunConfig, embed_all_hadiths
from hadith_mcp.pipeline.embed_db_io import load_pending_embed_texts


def main() -> int:
    p = argparse.ArgumentParser(
        description="Embed hadiths with NULL embedding in hadith.db (resumable, slow by default)."
    )
    p.add_argument("--db-path", type=Path, default=ROOT / "data" / "hadith.db")
    p.add_argument(
        "--checkpoint",
        type=Path,
        default=None,
        help="Append-only JSONL path for each successful embedding (merge separately if needed)",
    )
    p.add_argument("--batch-size", type=int, default=1, help="OpenAI inputs per request (1 = safest)")
    p.add_argument(
        "--commit-every",
        type=int,
        default=10,
        help="SQLite COMMIT after this many successful writes (assim default: 10)",
    )
    p.add_argument(
        "--sleep-between-batches",
        type=float,
        default=0.12,
        help="Seconds to sleep after each API call / batch (assim used ~0.1)",
    )
    p.add_argument("--sleep-on-error", type=float, default=0.5)
    p.add_argument("--rate-limit-base-sleep", type=float, default=30.0)
    p.add_argument("--rate-limit-max-sleep", type=float, default=300.0)
    p.add_argument("--max-retries", type=int, default=6)
    args = p.parse_args()

    if not args.db_path.is_file():
        print(f"ERROR: {args.db_path} not found. Run scripts/build_db.py --skip-embed first.", file=sys.stderr)
        return 1

    conn = sqlite3.connect(args.db_path)
    try:
        texts = load_pending_embed_texts(conn)
    finally:
        conn.close()

    if not texts:
        print("Nothing to embed (no rows with embedding IS NULL).")
        return 0

    print(f"Pending hadiths: {len(texts)} model={EMBEDDING_MODEL}")
    cfg = EmbedRunConfig(
        batch_size=args.batch_size,
        commit_every=args.commit_every,
        sleep_between_batches=args.sleep_between_batches,
        sleep_on_item_error=args.sleep_on_error,
        sleep_on_rate_limit_base=args.rate_limit_base_sleep,
        sleep_on_rate_limit_max=args.rate_limit_max_sleep,
        max_retries_per_request=args.max_retries,
        checkpoint_path=args.checkpoint,
    )

    conn = sqlite3.connect(args.db_path)
    try:
        client = OpenAI()
        ok, bad = embed_all_hadiths(conn, client, texts_by_id=texts, config=cfg)
        print(f"Finished. embedded_ok={ok} skipped_or_failed={bad}")
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
