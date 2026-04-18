"""Append-only JSONL checkpoints for embedding runs (crash-safe sidecar)."""

from __future__ import annotations

import base64
import json
from pathlib import Path


SCHEMA_KEY = "_checkpoint_schema"
CHECKPOINT_VERSION = "hadith-embedding-blob-v1"


def append_embedding_checkpoint(path: Path | None, hadith_id: int, blob: bytes) -> None:
    """Append one successful embedding as JSONL; flush so a crash loses at most one in-flight write."""
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        SCHEMA_KEY: CHECKPOINT_VERSION,
        "id": hadith_id,
        "blob_b64": base64.standard_b64encode(blob).decode("ascii"),
    }
    line = json.dumps(payload, separators=(",", ":")) + "\n"
    with path.open("a", encoding="utf-8") as f:
        f.write(line)
        f.flush()


def init_checkpoint_file(path: Path | None) -> None:
    """Write a header line once so empty tail merges cleanly."""
    if path is None or path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps({SCHEMA_KEY: CHECKPOINT_VERSION, "note": "hadith embedding checkpoint"}, separators=(",", ":")) + "\n"
    path.write_text(line, encoding="utf-8")


def iter_checkpoint_embeddings(path: Path) -> tuple[int, bytes]:
    """Yield (hadith_id, blob) from a checkpoint JSONL file."""
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict):
                continue
            if "id" not in obj or "blob_b64" not in obj:
                continue
            hid = int(obj["id"])
            raw = base64.standard_b64decode(str(obj["blob_b64"]))
            yield hid, raw
