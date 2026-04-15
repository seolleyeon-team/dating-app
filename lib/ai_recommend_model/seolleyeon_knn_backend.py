from __future__ import annotations

import os

import numpy as np
from scipy import sparse


def should_use_implicit_backend() -> bool:
    """Use native implicit backend only when explicitly opted in."""
    raw = os.getenv("SEOLLEYEON_KNN_BACKEND", "scipy").strip().lower()
    return raw == "implicit"


def build_weighted_user_item(
    user_item: sparse.csr_matrix,
    *,
    knn_type: str,
    bm25_k1: float,
    bm25_b: float,
) -> sparse.csr_matrix:
    """Prepare a stable scipy-friendly user-item matrix for KNN training."""
    base = sparse.coo_matrix(user_item, dtype=np.float32)
    if base.nnz == 0:
        return base.tocsr()

    if knn_type == "cosine":
        return base.tocsr()
    if knn_type == "tfidf":
        return _tfidf_weight(base).tocsr()
    if knn_type == "bm25":
        return _bm25_weight(base, bm25_k1, bm25_b).tocsr()
    raise ValueError("knn_type must be one of: bm25, cosine, tfidf")


def _tfidf_weight(mat: sparse.coo_matrix) -> sparse.coo_matrix:
    weighted = mat.copy()
    num_rows = float(weighted.shape[0])
    idf = np.log(num_rows) - np.log1p(np.bincount(weighted.col, minlength=weighted.shape[1]))
    weighted.data = np.sqrt(weighted.data) * idf[weighted.col]
    return weighted


def _bm25_weight(mat: sparse.coo_matrix, k1: float, b: float) -> sparse.coo_matrix:
    weighted = mat.copy()
    num_rows = float(weighted.shape[0])
    idf = np.log(num_rows) - np.log1p(np.bincount(weighted.col, minlength=weighted.shape[1]))

    row_sums = np.ravel(weighted.sum(axis=1))
    average_length = float(row_sums.mean()) if row_sums.size else 0.0
    if average_length <= 0:
        return weighted

    length_norm = (1.0 - b) + b * row_sums / average_length
    weighted.data = (
        weighted.data
        * (k1 + 1.0)
        / (k1 * length_norm[weighted.row] + weighted.data)
        * idf[weighted.col]
    )
    return weighted
