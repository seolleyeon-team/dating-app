#!/usr/bin/env python3
"""Festival web recommendation shared helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

try:
    from google.cloud import firestore
except Exception:  # pragma: no cover
    firestore = None


LIKE_WEIGHT = 1.0
DISLIKE_WEIGHT = 0.65


def require_firestore() -> None:
    if firestore is None:
        raise RuntimeError("google-cloud-firestore is required")


def kst_date_key(now: Optional[datetime] = None) -> str:
    kst = (now or datetime.now(tz=timezone.utc)) + timedelta(hours=9)
    return f"{kst.year:04d}{kst.month:02d}{kst.day:02d}"


def load_ai_embeddings(
    project_id: str,
    *,
    database: Optional[str] = None,
) -> Dict[str, List[float]]:
    require_firestore()
    db = firestore.Client(project=project_id, database=database)
    out: Dict[str, List[float]] = {}
    for snap in db.collection("festivalAiEmbeddings").stream():
        raw = snap.to_dict() or {}
        vector = raw.get("vector")
        if isinstance(vector, list) and vector:
            out[snap.id] = [float(v) for v in vector]
    return out


def load_profile_embeddings(
    project_id: str,
    *,
    database: Optional[str] = None,
) -> Dict[str, List[float]]:
    require_firestore()
    db = firestore.Client(project=project_id, database=database)
    out: Dict[str, List[float]] = {}
    for snap in db.collection("festivalProfileEmbeddings").stream():
        raw = snap.to_dict() or {}
        vector = raw.get("vector")
        if isinstance(vector, list) and vector:
            out[snap.id] = [float(v) for v in vector]
    return out


def load_taste_swipes(
    db: firestore.Client,
    ticket_id: str,
) -> List[Dict[str, Any]]:
    snaps = (
        db.collection("festivalTickets")
        .document(ticket_id)
        .collection("tasteSwipes")
        .stream()
    )
    return [snap.to_dict() or {} for snap in snaps]


def build_preference_vector(
    swipes: List[Dict[str, Any]],
    ai_embeddings: Dict[str, List[float]],
) -> Tuple[Optional[List[float]], Dict[str, float]]:
    import numpy as np

    affinities: Dict[str, float] = {}
    pos: List[Tuple[np.ndarray, float]] = []
    neg: List[Tuple[np.ndarray, float]] = []

    for swipe in swipes:
        code = str(swipe.get("aiProfileCode") or "").strip()
        if not code:
            continue
        liked = swipe.get("liked") is True
        affinities[code] = 1.0 if liked else 0.0
        emb = ai_embeddings.get(code)
        if emb is None:
            continue
        vec = np.asarray(emb, dtype=np.float32)
        if liked:
            pos.append((vec, LIKE_WEIGHT))
        else:
            neg.append((vec, DISLIKE_WEIGHT))

    def weighted_mean(samples: List[Tuple[np.ndarray, float]]) -> Optional[np.ndarray]:
        if not samples:
            return None
        weights = np.asarray([w for _, w in samples], dtype=np.float32)
        if float(weights.sum()) <= 1e-12:
            return None
        mat = np.stack([v for v, _ in samples], axis=0)
        mean = np.average(mat, axis=0, weights=weights)
        norm = float(np.linalg.norm(mean))
        if norm <= 1e-12:
            return None
        return (mean / norm).astype(np.float32)

    pos_mean = weighted_mean(pos)
    neg_mean = weighted_mean(neg)
    if pos_mean is not None and neg_mean is not None:
        pref = pos_mean - DISLIKE_WEIGHT * neg_mean
        norm = float(np.linalg.norm(pref))
        if norm > 1e-12:
            return (pref / norm).tolist(), affinities
    if pos_mean is not None:
        return pos_mean.tolist(), affinities
    return None, affinities
