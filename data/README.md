# Data directory (not in git)

Generated artifacts live here. Clone the repo, then build locally:

| File | Produced by |
|------|-------------|
| `hadith.db` | `scripts/build_db.py` |
| `stats.db` | Created at runtime by the server |
| `*checkpoint*.jsonl` | `scripts/embed_hadith.py` (intermediate checkpoints) |

Typical size after a full run: ~730 MB (`hadith.db` with embeddings).
