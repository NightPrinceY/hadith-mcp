"""Cross-reference hadiths via cosine similarity + narrator boost."""

from __future__ import annotations

import pickle
import sqlite3

import numpy as np

from hadith_mcp.pipeline.narrator_match import narrators_match

BUKHARI = 1
MUSLIM = 2
SIM_MIN = 0.80
SCORE_MIN = 0.88
NARRATOR_BOOST = 0.10
TOPK_BM = 8
TOPK_OTHER = 5


def _unpickle_blob(blob: bytes) -> np.ndarray:
    arr = pickle.loads(blob)  # noqa: S301 - trusted local DB
    return np.asarray(arr, dtype=np.float32)


def _load_matrix(
    conn: sqlite3.Connection,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[str]]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, collection_id, narrator, embedding
        FROM hadiths
        WHERE embedding IS NOT NULL
        ORDER BY id
        """
    )
    rows = cur.fetchall()
    if not rows:
        raise RuntimeError("No embeddings loaded; run embed step first.")
    ids = np.array([int(r[0]) for r in rows], dtype=np.int64)
    colls = np.array([int(r[1]) for r in rows], dtype=np.int32)
    narrators = [str(r[2] or "") for r in rows]
    mats = [_unpickle_blob(r[3]) for r in rows]
    emb = np.stack(mats, axis=0)
    return ids, colls, emb, narrators


def _score(sim: float, na: str, nb: str) -> tuple[float, bool]:
    nm = narrators_match(na, nb)
    boosted = sim + (NARRATOR_BOOST if nm else 0.0)
    return boosted, nm


def _add_edge(
    edges: set[tuple[int, int, float, bool]],
    id_a: int,
    id_b: int,
    sim: float,
    narrator_match: bool,
) -> None:
    if id_a == id_b:
        return
    lo, hi = (id_a, id_b) if id_a < id_b else (id_b, id_a)
    edges.add((lo, hi, float(sim), narrator_match))


def _topk_indices(row: np.ndarray, k: int) -> np.ndarray:
    k = min(k, row.size)
    if k <= 0:
        return np.array([], dtype=np.int64)
    idx = np.argpartition(-row, k - 1)[:k]
    return idx[np.argsort(-row[idx])]


def find_cross_references(conn: sqlite3.Connection) -> int:
    """
    Populate cross_references from embedding similarity.
    Returns number of edges inserted.
    """
    ids, colls, emb, narrators = _load_matrix(conn)
    edges: set[tuple[int, int, float, bool]] = set()

    idx_b = np.where(colls == BUKHARI)[0]
    idx_m = np.where(colls == MUSLIM)[0]
    if idx_b.size and idx_m.size:
        s_bm = emb[idx_b] @ emb[idx_m].T
        for ri in range(s_bm.shape[0]):
            row = s_bm[ri]
            for mj in _topk_indices(row, TOPK_BM):
                sim = float(row[mj])
                if sim < SIM_MIN:
                    continue
                i_b = int(idx_b[ri])
                i_m = int(idx_m[mj])
                sc, nm = _score(sim, narrators[i_b], narrators[i_m])
                if sc < SCORE_MIN:
                    continue
                _add_edge(edges, int(ids[i_b]), int(ids[i_m]), sim, nm)

        s_mb = s_bm.T
        for rj in range(s_mb.shape[0]):
            row = s_mb[rj]
            for bi in _topk_indices(row, TOPK_BM):
                sim = float(row[bi])
                if sim < SIM_MIN:
                    continue
                i_m = int(idx_m[rj])
                i_b = int(idx_b[bi])
                sc, nm = _score(sim, narrators[i_m], narrators[i_b])
                if sc < SCORE_MIN:
                    continue
                _add_edge(edges, int(ids[i_m]), int(ids[i_b]), sim, nm)

    idx_bm = np.sort(np.concatenate([idx_b, idx_m]))
    idx_non = np.where((colls != BUKHARI) & (colls != MUSLIM))[0]
    if idx_non.size and idx_bm.size:
        s_nb = emb[idx_non] @ emb[idx_bm].T
        for ri in range(s_nb.shape[0]):
            row = s_nb[ri]
            for tj in _topk_indices(row, TOPK_OTHER):
                sim = float(row[tj])
                if sim < SIM_MIN:
                    continue
                i_n = int(idx_non[ri])
                i_k = int(idx_bm[tj])
                sc, nm = _score(sim, narrators[i_n], narrators[i_k])
                if sc < SCORE_MIN:
                    continue
                _add_edge(edges, int(ids[i_n]), int(ids[i_k]), sim, nm)

    non_ids = sorted({int(c) for c in colls.tolist() if c not in (BUKHARI, MUSLIM)})
    for a in range(len(non_ids)):
        for b in range(a + 1, len(non_ids)):
            c1, c2 = non_ids[a], non_ids[b]
            idx_1 = np.where(colls == c1)[0]
            idx_2 = np.where(colls == c2)[0]
            if idx_1.size == 0 or idx_2.size == 0:
                continue
            block = emb[idx_1] @ emb[idx_2].T
            for ri in range(block.shape[0]):
                row = block[ri]
                for tj in _topk_indices(row, TOPK_OTHER):
                    sim = float(row[tj])
                    if sim < SIM_MIN:
                        continue
                    i1 = int(idx_1[ri])
                    i2 = int(idx_2[tj])
                    sc, nm = _score(sim, narrators[i1], narrators[i2])
                    if sc < SCORE_MIN:
                        continue
                    _add_edge(edges, int(ids[i1]), int(ids[i2]), sim, nm)

    cur = conn.cursor()
    cur.execute("DELETE FROM cross_references")
    cur.executemany(
        """
        INSERT OR REPLACE INTO cross_references
        (hadith_id, matched_hadith_id, similarity, narrator_match)
        VALUES (?, ?, ?, ?)
        """,
        [(e[0], e[1], e[2], 1 if e[3] else 0) for e in sorted(edges)],
    )
    conn.commit()
    return len(edges)
