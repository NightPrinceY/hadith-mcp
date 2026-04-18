#!/usr/bin/env python3
"""Build data/hadith.db from hadith-json by_book corpus (embed + cross-ref + provenance)."""

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

import numpy as np

from openai import OpenAI

from hadith_mcp.pipeline.crossref import find_cross_references
from hadith_mcp.pipeline.db_loader import init_db, insert_chapters, insert_collections, insert_hadiths
from hadith_mcp.pipeline.embed import EMBEDDING_MODEL, EmbedRunConfig, embed_all_hadiths, to_blob
from hadith_mcp.pipeline.load_books import embedding_input, load_all
from hadith_mcp.pipeline.provenance import assign_provenance


def main() -> int:
    p = argparse.ArgumentParser(description="Build hadith SQLite database")
    p.add_argument(
        "--data-dir",
        type=Path,
        default=ROOT / "hadith-json-main" / "db" / "by_book",
        help="Path to hadith-json db/by_book directory",
    )
    p.add_argument(
        "--db-path",
        type=Path,
        default=ROOT / "data" / "hadith.db",
        help="Output SQLite path",
    )
    p.add_argument("--fresh", action="store_true", help="Delete existing DB before build")
    p.add_argument("--skip-embed", action="store_true", help="Skip OpenAI embedding step")
    p.add_argument(
        "--fake-embed",
        action="store_true",
        help="Fill random L2-normalized vectors (3072 dims) for pipeline testing without API",
    )
    p.add_argument("--skip-cross", action="store_true", help="Skip cross-reference computation")
    p.add_argument("--skip-provenance", action="store_true", help="Skip provenance tagging")
    # OpenAI embedding pacing (see also scripts/embed_hadith.py for long resume-only runs)
    p.add_argument(
        "--embed-checkpoint",
        type=Path,
        default=None,
        help="Append-only JSONL: each successful embedding (merge with merge_embedding_checkpoints.py)",
    )
    p.add_argument("--embed-batch-size", type=int, default=1, help="Inputs per API call (1 = slowest/safest)")
    p.add_argument(
        "--embed-commit-every",
        type=int,
        default=10,
        help="SQLite COMMIT after this many successes (assim-style)",
    )
    p.add_argument(
        "--embed-sleep",
        type=float,
        default=0.12,
        help="Sleep seconds after each batch (assim used ~0.1)",
    )
    p.add_argument("--embed-sleep-on-error", type=float, default=0.5)
    p.add_argument("--embed-rate-limit-base", type=float, default=30.0)
    p.add_argument("--embed-rate-limit-max", type=float, default=300.0)
    p.add_argument("--embed-max-retries", type=int, default=6)
    args = p.parse_args()

    by_book = args.data_dir
    if not by_book.is_dir():
        print(f"ERROR: data directory not found: {by_book}", file=sys.stderr)
        return 1

    db_path = args.db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if args.fresh and db_path.is_file():
        db_path.unlink()
        print(f"Removed existing {db_path}")

    print("Loading JSON books...")
    collections, chapters, hadiths = load_all(by_book)
    print(f"  collections={len(collections)} hadiths={len(hadiths)}")

    conn = sqlite3.connect(db_path)
    try:
        print("Applying schema + inserting rows...")
        init_db(conn)
        insert_collections(conn, collections)
        ch_map = insert_chapters(conn, chapters)
        insert_hadiths(conn, hadiths, ch_map)

        texts_by_id = {h.id: embedding_input(h.narrator, h.english) for h in hadiths}

        if args.fake_embed:
            print("Filling fake embeddings (3072-d, normalized)...")
            rng = np.random.default_rng(0)
            cur = conn.cursor()
            # text-embedding-3-large dimension
            dim = 3072
            for h in hadiths:
                v = rng.standard_normal(dim, dtype=np.float32)
                v /= np.linalg.norm(v) + 1e-12
                cur.execute(
                    "UPDATE hadiths SET embedding = ? WHERE id = ?",
                    (to_blob(v.tolist()), h.id),
                )
            conn.commit()
            print(f"  fake_embed_model={EMBEDDING_MODEL} dim={dim} count={len(hadiths)}")
        elif not args.skip_embed:
            print("Embedding (OpenAI text-embedding-3-large)...")
            client = OpenAI()
            ecfg = EmbedRunConfig(
                batch_size=args.embed_batch_size,
                commit_every=args.embed_commit_every,
                sleep_between_batches=args.embed_sleep,
                sleep_on_item_error=args.embed_sleep_on_error,
                sleep_on_rate_limit_base=args.embed_rate_limit_base,
                sleep_on_rate_limit_max=args.embed_rate_limit_max,
                max_retries_per_request=args.embed_max_retries,
                checkpoint_path=args.embed_checkpoint,
            )
            ok, bad = embed_all_hadiths(conn, client, texts_by_id=texts_by_id, config=ecfg)
            print(f"  embedded_ok={ok} failures={bad}")
        else:
            print("Skipping embed step.")

        if not args.skip_cross:
            print("Computing cross-references...")
            n = find_cross_references(conn)
            print(f"  cross_reference_edges={n}")
        else:
            print("Skipping cross-reference step.")

        if not args.skip_provenance:
            print("Assigning provenance...")
            assign_provenance(conn)
            print("  done.")
        else:
            print("Skipping provenance step.")

    finally:
        conn.close()

    print(f"Database ready: {db_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
