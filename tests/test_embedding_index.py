"""Unit tests for ``EmbeddingIndex`` (no database required)."""

from __future__ import annotations

import numpy as np

from hadith_mcp.embeddings_index import EmbeddingIndex


def test_topk_cosine_order_and_collection_mask() -> None:
    ids = np.array([10, 20, 30], dtype=np.int64)
    coll_ids = np.array([1, 2, 1], dtype=np.int32)
    mat = np.array(
        [
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float32,
    )
    ix = EmbeddingIndex(ids, coll_ids, mat)
    q = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    top = ix.topk(q, k=2, collection_id=1)
    assert [t[0] for t in top] == [10, 30]
    assert top[0][1] > top[1][1] - 1e-6
