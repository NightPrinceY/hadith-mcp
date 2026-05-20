# Data directory (not in git)

Generated artifacts live here. Clone the repo, then build locally:

| File | Produced by |
|------|-------------|
| `hadith.db` | `scripts/build_db.py` (import + optional embed/crossref) |
| `SHA256SUMS` | `cd data && sha256sum hadith.db > SHA256SUMS` |
| `stats.db` | Created at runtime by the server (usage analytics) |
| `*checkpoint*.jsonl` | `scripts/embed_hadith.py` (intermediate embedding checkpoints) |

## Quick start

```bash
# Requires hadith-json source data
python scripts/build_db.py /path/to/hadith-json-main/db/by_book

# Resume embeddings (requires OPENAI_API_KEY)
python scripts/embed_hadith.py

# Cross-references + provenance (after embeddings are complete)
python scripts/compute_crossref.py
```

Typical size after a full run: ~730 MB (`hadith.db` with embeddings).

## Pre-built database

A pre-built `hadith.db` is available from [GitHub Releases](https://github.com/ovehbe/hadith-mcp/releases). Download it into this directory to skip the build pipeline.
