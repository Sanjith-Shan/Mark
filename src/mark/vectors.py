"""Small vector utilities shared by the novelty guard and RAG-of-winners."""

from __future__ import annotations

import numpy as np


def normalize(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v)
    return v / n if n else v


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def cosine_to_matrix(query: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """Cosine similarity of a single vector against each row of ``matrix``."""
    if matrix.size == 0:
        return np.zeros((0,), dtype=np.float32)
    q = normalize(query.astype(np.float32))
    norms = np.linalg.norm(matrix, axis=1)
    norms[norms == 0] = 1.0
    normed = matrix / norms[:, None]
    return normed @ q


def top_k(query: np.ndarray, matrix: np.ndarray, k: int) -> list[tuple[int, float]]:
    """Return ``[(row_index, similarity), ...]`` for the top-k most similar rows."""
    sims = cosine_to_matrix(query, matrix)
    if sims.size == 0:
        return []
    k = min(k, sims.shape[0])
    idx = np.argsort(-sims)[:k]
    return [(int(i), float(sims[i])) for i in idx]


def to_blob(v: np.ndarray) -> bytes:
    return np.asarray(v, dtype=np.float32).tobytes()


def from_blob(b: bytes) -> np.ndarray:
    return np.frombuffer(b, dtype=np.float32)
