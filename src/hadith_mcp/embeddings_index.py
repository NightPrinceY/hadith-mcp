"""In-memory embedding matrix for semantic hadith search (cosine ~ dot product on L2-normalized rows)."""

from __future__ import annotations

import pickle
import sqlite3
from pathlib import Path

import numpy as np


class EmbeddingIndex:
    """Maps hadith row ids to normalized vectors; supports top-k cosine search."""

    __slots__ = ("ids", "coll_ids", "mat")

    def __init__(
        self,
        ids: np.ndarray,
        coll_ids: np.ndarray,
        mat: np.ndarray,
    ) -> None:
        self.ids = np.asarray(ids, dtype=np.int64)
        self.coll_ids = np.asarray(coll_ids, dtype=np.int32)
        self.mat = np.asarray(mat, dtype=np.float32)

    @classmethod
    def load(cls, db_path: Path) -> EmbeddingIndex:
        resolved = db_path.expanduser().resolve()
        conn = sqlite3.connect(str(resolved), check_same_thread=False)
        conn.execute("PRAGMA query_only = ON")
        try:
            cur = conn.execute(
                """
                SELECT h.id, h.collection_id, h.embedding
                FROM hadiths h
                WHERE h.embedding IS NOT NULL
                ORDER BY h.id
                """
            )
            ids_list: list[int] = []
            col_list: list[int] = []
            mats: list[np.ndarray] = []
            for row in cur:
                blob = row[2]
                if not blob:
                    continue
                arr = pickle.loads(blob)  # noqa: S301 - local trusted DB
                arr = np.asarray(arr, dtype=np.float32).ravel()
                ids_list.append(int(row[0]))
                col_list.append(int(row[1]))
                mats.append(arr)
        finally:
            conn.close()
        if not mats:
            raise RuntimeError("No embeddings found in hadiths.embedding")
        mat = np.stack(mats, axis=0)
        if mat.ndim != 2:
            raise RuntimeError(f"Expected 2D embedding matrix, got shape {mat.shape}")
        return cls(np.array(ids_list, dtype=np.int64), np.array(col_list, dtype=np.int32), mat)

    def topk(
        self,
        query_vec: np.ndarray,
        k: int,
        *,
        collection_id: int | None = None,
    ) -> list[tuple[int, float]]:
        """Return up to ``k`` (hadith_id, cosine_similarity) pairs, highest similarity first."""
        q = np.asarray(query_vec, dtype=np.float32).ravel()
        if q.shape[0] != self.mat.shape[1]:
            raise ValueError(
                f"Query dim {q.shape[0]} does not match index dim {self.mat.shape[1]}"
            )
        nq = float(np.linalg.norm(q))
        if nq > 0:
            q = q / nq
        sims = self.mat @ q
        if collection_id is not None:
            mask = self.coll_ids == collection_id
            sims = np.where(mask, sims, -np.inf)
        k = max(1, min(int(k), int(sims.size)))
        idx = np.argpartition(-sims, k - 1)[:k]
        idx = idx[np.argsort(-sims[idx])]
        out: list[tuple[int, float]] = []
        for i in idx:
            sc = float(sims[i])
            if not np.isfinite(sc) or sc <= -1e9:
                continue
            out.append((int(self.ids[i]), sc))
        return out
