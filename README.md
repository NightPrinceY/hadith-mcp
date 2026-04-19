# hadith-mcp

**Model Context Protocol (MCP) server and data pipeline** for serving **canonical hadith text** (Arabic and English) to assistants in a **citation-safe** way—similar in spirit to [quran-mcp](https://github.com/quran/quran-mcp): fetch from a real corpus instead of quoting from model memory.

This repository currently focuses on **building `data/hadith.db`**: normalized SQLite, **OpenAI embeddings** (`text-embedding-3-large`), **cross-collection references** (cosine similarity + narrator-aware scoring), and **provenance-style tags** (e.g. muttafaq-style links between Sahih al-Bukhari and Sahih Muslim). The FastMCP HTTP surface is planned to sit on top of that database.

## Data sources and credits

- **Hadith text** comes from the community **[hadith-json](https://github.com/AhmedBaset/hadith-json)** dataset (scraped from [Sunnah.com](https://sunnah.com/)), which aligns with the broader **[sunnah-com](https://github.com/sunnah-com/api)** / Quran Foundation ecosystem—the same family of sources behind [quran-mcp](https://github.com/quran/quran-mcp).
- **Architecture and patterns** are inspired by **[quran-mcp](https://github.com/quran/quran-mcp)** (FastMCP, grounding mindset, tooling layout).

If you ship a product or paper, keep upstream attribution visible (dataset authors, Sunnah.com, and the scholarly collections themselves).

## Repository layout

| Path | Purpose |
|------|---------|
| `scripts/build_db.py` | Load `hadith-json` `db/by_book` JSON → SQLite schema, optional embed, cross-ref, provenance |
| `scripts/embed_hadith.py` | **Resume-only** embedding for rows with `embedding IS NULL` (slow, checkpoint-friendly) |
| `scripts/merge_embedding_checkpoints.py` | Replay JSONL embedding checkpoints into `hadith.db` after crashes or restores |
| `scripts/compute_crossref.py` | Recompute `cross_references` + `provenance` only (does **not** re-import JSON; safe after embed) |
| `src/hadith_mcp/pipeline/` | Loaders, schema, embed, cross-reference, provenance logic |

Large reference trees **`hadith-json-main/`** and **`quran-mcp-master/`** are listed in `.gitignore`. Clone or unpack **[hadith-json](https://github.com/AhmedBaset/hadith-json)** locally (for example as `hadith-json-main/`) or pass **`--data-dir`** to `build_db.py`.

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # set OPENAI_API_KEY for embedding steps
```

### 1) Build the database (without calling OpenAI)

Point `--data-dir` at your local `hadith-json` **`db/by_book`** directory.

```bash
python scripts/build_db.py --fresh --skip-embed --skip-cross --skip-provenance \
  --data-dir ./hadith-json-main/db/by_book
```

### 2) Embeddings (long run; use a separate machine if you prefer)

Assim-style defaults: **batch size 1**, **commit every 10 rows**, **sleep between calls**, optional **JSONL checkpoint** for safety.

```bash
python scripts/embed_hadith.py \
  --db-path ./data/hadith.db \
  --checkpoint ./data/embeddings_checkpoint.jsonl \
  --batch-size 1 \
  --commit-every 10 \
  --sleep-between-batches 0.15
```

Replay checkpoints into the DB when needed:

```bash
python scripts/merge_embedding_checkpoints.py --db-path ./data/hadith.db \
  ./data/embeddings_checkpoint.jsonl --only-missing
```

### 3) Cross-references and provenance (local CPU)

Do **not** re-run `build_db.py` without `--fresh` after embedding unless you intend to re-import JSON (that path can **overwrite** rows and clear `embedding`). Instead:

```bash
python scripts/compute_crossref.py --db-path ./data/hadith.db
```

For a **single-machine** full build (import + embed + cross + provenance), run `build_db.py` once **without** `--skip-embed` / `--skip-cross` / `--skip-provenance`, and pass embedding pacing flags as needed (`python scripts/build_db.py --help`).

## Configuration

- **Secrets:** `.env` is gitignored; see `.env.example` for `OPENAI_API_KEY`.
- **Artifacts:** `data/*.db` and embedding checkpoint glob patterns are gitignored by default.
- **Embeddings:** Rows with empty English narrator and text still embed using **Arabic** text when present. Long inputs are clipped with **tiktoken** (`cl100k_base`) to stay under the **8192-token** API limit, with a further shrink ladder if a row still hits length errors.
- **Count rows without the `sqlite3` CLI:**  
  `python -c "import sqlite3; c=sqlite3.connect('data/hadith.db'); print(c.execute('SELECT COUNT(*) FROM hadiths WHERE embedding IS NULL').fetchone()[0])"`

## License

- **This repository (code, scripts, docs we wrote):** [GNU General Public License v3.0 only](LICENSE) (GPL-3.0-only). That is a strong copyleft FOSS license: people who distribute derivatives of your code (or a combined work that links GPL code in certain ways) generally need to release their changes under GPL-compatible terms as well. GPLv3 adds a few clauses compared to GPLv2 (for example around patents and tivoization). If you specifically need GPLv2-only compatibility with another GPLv2-only project, we can switch the license text—ask before there are many external contributors.
- **Hadith text and other upstream content** are **not** relicensed by our GPL: they stay under **[hadith-json](https://github.com/AhmedBaset/hadith-json)** / [Sunnah.com](https://sunnah.com/) terms. Ship attribution and comply with those terms when you redistribute databases or excerpts.

### Releases and data integrity (when `hadith.db` is ready)

Cryptographic **signing** proves **who published** an artifact and that the **bytes did not change** after signing. It does **not** prove religious “accuracy” of every narration or that every automated cross-reference is perfect—that still depends on sources, methodology, and human review.

Practical stack many projects use:

1. **Checksums** — Publish `SHA256SUMS` (or `sha256sum hadith.db`) next to each release asset so anyone can verify the download is bit-for-bit what you built.
2. **Detached signatures** — Sign those checksums (or sign the database file directly) with **GPG** or **[Sigstore](https://www.sigstore.dev/)** so users can verify it came from your release key.
3. **Reproducibility** — Document exact inputs: pinned **hadith-json** tag/commit, pipeline **git tag**, embedding **model id**, and script versions so others can audit or rebuild.

Signing is worthwhile if you distribute `hadith.db` as a **release binary**; for a purely local build, checksums alone are often enough.

## Contributing

Issues and PRs welcome. Please keep diffs focused and match existing style (`ruff` / `pytest` when present).
