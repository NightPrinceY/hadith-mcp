"""OpenAI text-embedding-3-large — assim-style incremental saves, slow pacing, checkpoints."""

from __future__ import annotations

import pickle
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np
import tiktoken
from openai import APIStatusError, OpenAI

from hadith_mcp.pipeline.checkpoint import append_embedding_checkpoint, init_checkpoint_file

EMBEDDING_MODEL = "text-embedding-3-large"
EMBEDDING_DIMENSION = 3072
# OpenAI embedding models accept at most 8192 tokens; Arabic can be >1 token/char vs char cuts.
MAX_EMBED_TOKENS = 8000
_TIKTOKEN_ENC: tiktoken.Encoding | None = None


def _tiktoken_enc() -> tiktoken.Encoding:
    global _TIKTOKEN_ENC
    if _TIKTOKEN_ENC is None:
        # Same family as GPT-4 / text-embedding-ada-002; valid for counting OpenAI embed inputs.
        _TIKTOKEN_ENC = tiktoken.get_encoding("cl100k_base")
    return _TIKTOKEN_ENC


def truncate_embed_input(text: str, *, max_tokens: int = MAX_EMBED_TOKENS) -> str:
    """Clip text to a safe token budget (API hard limit 8192 tokens)."""
    t = text.strip()
    if not t:
        return ""
    enc = _tiktoken_enc()
    ids = enc.encode(t)
    if len(ids) <= max_tokens:
        return t
    clipped = enc.decode(ids[:max_tokens])
    return clipped + "\n[...truncated-for-embed...]"


def to_blob(vec: list[float] | np.ndarray) -> bytes:
    arr = np.asarray(vec, dtype=np.float32)
    norm = np.linalg.norm(arr)
    if norm > 0:
        arr = arr / norm
    return pickle.dumps(arr, protocol=4)


def _is_rate_limited(exc: BaseException) -> bool:
    if isinstance(exc, APIStatusError) and getattr(exc, "status_code", None) == 429:
        return True
    msg = str(exc).lower()
    return "429" in msg or "rate limit" in msg or "too many requests" in msg


def embed_one(client: OpenAI, text: str) -> list[float]:
    resp = client.embeddings.create(model=EMBEDDING_MODEL, input=text)
    return resp.data[0].embedding


def embed_batch(client: OpenAI, texts: Sequence[str]) -> list[list[float]]:
    resp = client.embeddings.create(model=EMBEDDING_MODEL, input=list(texts))
    data = sorted(resp.data, key=lambda x: x.index)
    return [d.embedding for d in data]


def _is_context_length_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return "maximum context length" in msg or "8192" in msg


def embed_one_safe(client: OpenAI, text: str) -> list[float]:
    """Embed one string; shrink by token count if the API still rejects length (tokenizer edge cases)."""
    last: BaseException | None = None
    for lim in (MAX_EMBED_TOKENS, 6000, 4000, 2000, 1000, 512):
        payload = truncate_embed_input(text, max_tokens=lim)
        try:
            return embed_one(client, payload)
        except BaseException as exc:  # noqa: BLE001
            if _is_context_length_error(exc):
                last = exc
                continue
            raise
    assert last is not None
    raise last


def embed_batch_safe(client: OpenAI, texts: list[str]) -> list[list[float]]:
    trimmed = [truncate_embed_input(t) for t in texts]
    try:
        return embed_batch(client, trimmed)
    except BaseException as exc:  # noqa: BLE001
        if not _is_context_length_error(exc):
            raise
        return [embed_one_safe(client, t) for t in texts]


@dataclass
class EmbedRunConfig:
    """Defaults tuned for long runs and OpenAI rate limits (assim-inspired).

    ``batch_size=1`` + ``sleep_between_batches=0.12`` approximates assim one-call + 0.1s pacing.
    """

    batch_size: int = 1
    commit_every: int = 10
    sleep_between_batches: float = 0.12
    sleep_on_item_error: float = 0.5
    sleep_on_rate_limit_base: float = 30.0
    sleep_on_rate_limit_max: float = 300.0
    max_retries_per_request: int = 6
    checkpoint_path: Path | None = None


def _backoff_sleep(attempt: int, cfg: EmbedRunConfig) -> None:
    base = cfg.sleep_on_rate_limit_base * (2**attempt)
    cap = cfg.sleep_on_rate_limit_max
    jitter = random.uniform(0, base * 0.1)
    time.sleep(min(base + jitter, cap))


def _call_with_retries(
    client: OpenAI,
    *,
    texts: list[str],
    cfg: EmbedRunConfig,
) -> list[list[float]]:
    """Call embeddings API (batch); retry on rate limit / transient errors."""
    last: BaseException | None = None
    for attempt in range(cfg.max_retries_per_request + 1):
        try:
            if len(texts) == 1:
                return [embed_one_safe(client, texts[0])]
            return embed_batch_safe(client, texts)
        except BaseException as exc:  # noqa: BLE001
            last = exc
            if attempt >= cfg.max_retries_per_request:
                raise last
            if _is_rate_limited(exc):
                print(f"  rate limited (attempt {attempt + 1}/{cfg.max_retries_per_request}), backing off...")
                _backoff_sleep(attempt, cfg)
            else:
                print(f"  API error (attempt {attempt + 1}): {exc}")
                time.sleep(cfg.sleep_on_item_error)
    raise RuntimeError("unreachable") from last


def embed_all_hadiths(
    conn,
    client: OpenAI,
    *,
    texts_by_id: dict[int, str],
    config: EmbedRunConfig | None = None,
) -> tuple[int, int]:
    """
    Embed rows where ``embedding IS NULL``, resumable across restarts.

    - Commits every ``commit_every`` successful writes (assim-style periodic commit).
    - Optional JSONL ``checkpoint_path``: append each blob after DB write (parts on disk).
    - On batch failure (when batch_size > 1): retry each item with ``batch_size`` 1 semantics.
    - Empty input text: skip (leave NULL), counted in ``bad``.

    Returns ``(success_count, failure_or_skip_count)``.
    """
    cfg = config or EmbedRunConfig()
    init_checkpoint_file(cfg.checkpoint_path)

    cur = conn.cursor()
    cur.execute("SELECT id FROM hadiths WHERE embedding IS NULL ORDER BY id")
    missing = [int(row[0]) for row in cur.fetchall()]
    ok, bad = 0, 0
    since_commit = 0

    def commit_if_needed(force: bool = False) -> None:
        nonlocal since_commit
        if force or since_commit >= cfg.commit_every:
            conn.commit()
            since_commit = 0

    def write_one(hid: int, vec: list[float]) -> None:
        nonlocal ok, since_commit
        blob = to_blob(vec)
        cur.execute("UPDATE hadiths SET embedding = ? WHERE id = ?", (blob, hid))
        append_embedding_checkpoint(cfg.checkpoint_path, hid, blob)
        ok += 1
        since_commit += 1
        commit_if_needed()

    total = len(missing)
    idx = 0
    bs = max(1, cfg.batch_size)

    while idx < total:
        batch_ids: list[int] = []
        batch_texts: list[str] = []
        while idx < total and len(batch_ids) < bs:
            hid = missing[idx]
            idx += 1
            raw = texts_by_id.get(hid, "").strip()
            if not raw:
                bad += 1
                continue
            batch_ids.append(hid)
            batch_texts.append(raw)

        if not batch_ids:
            continue

        try:
            vectors = _call_with_retries(client, texts=batch_texts, cfg=cfg)
        except BaseException as exc:  # noqa: BLE001
            print(f"  batch failed after retries (start id={batch_ids[0]}): {exc}")
            if len(batch_ids) > 1:
                for hid, txt in zip(batch_ids, batch_texts, strict=True):
                    try:
                        v = _call_with_retries(client, texts=[txt], cfg=cfg)
                        write_one(hid, v[0])
                    except BaseException as e2:  # noqa: BLE001
                        print(f"  skip id={hid}: {e2}")
                        bad += 1
                        time.sleep(cfg.sleep_on_item_error)
            else:
                bad += 1
                time.sleep(cfg.sleep_on_item_error)
            commit_if_needed(force=True)
            time.sleep(cfg.sleep_between_batches)
            continue

        if len(vectors) != len(batch_ids):
            print(f"  API length mismatch; per-item fallback from id={batch_ids[0]}")
            for hid, txt in zip(batch_ids, batch_texts, strict=True):
                try:
                    v = _call_with_retries(client, texts=[txt], cfg=cfg)
                    write_one(hid, v[0])
                except BaseException as e2:  # noqa: BLE001
                    print(f"  skip id={hid}: {e2}")
                    bad += 1
                    time.sleep(cfg.sleep_on_item_error)
        else:
            for hid, vec in zip(batch_ids, vectors, strict=True):
                write_one(hid, vec)

        commit_if_needed(force=True)
        time.sleep(cfg.sleep_between_batches)

        if ok and ok % max(cfg.commit_every * 20, 200) == 0:
            print(f"  embedded ok={ok} pending~{max(0, total - idx)}...")

    commit_if_needed(force=True)
    return ok, bad
