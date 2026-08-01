#!/usr/bin/env python3
"""Generate festivalModelRecs clip recommendations for all completed tickets."""

from __future__ import annotations

import argparse
from typing import Any, Dict, List

import numpy as np

from festival_rec_common import (
    build_preference_vector,
    kst_date_key,
    load_ai_embeddings,
    load_profile_embeddings,
    load_taste_swipes,
    require_firestore,
)

try:
    from google.cloud import firestore
except Exception:  # pragma: no cover
    firestore = None


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na <= 1e-12 or nb <= 1e-12:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--database", default=None)
    parser.add_argument("--date_key", default=None)
    parser.add_argument("--topn", type=int, default=12)
    args = parser.parse_args()

    require_firestore()
    db = firestore.Client(project=args.project, database=args.database)
    date_key = args.date_key or kst_date_key()

    ai_embeddings = load_ai_embeddings(args.project, database=args.database)
    profile_embeddings = load_profile_embeddings(args.project, database=args.database)
    profiles = {snap.id: snap.to_dict() or {} for snap in db.collection("festivalProfiles").stream()}

    tickets = db.collection("festivalTickets").where("tasteCompleted", "==", True).stream()
    bw = db.bulk_writer()
    generated = 0

    for ticket_snap in tickets:
        ticket_id = ticket_snap.id
        viewer = profiles.get(ticket_id) or {}
        gender = str(viewer.get("gender") or "")
        if not gender:
            continue
        target_gender = "여성" if gender == "남성" else "남성"

        swipes = load_taste_swipes(db, ticket_id)
        pref_list, affinities = build_preference_vector(swipes, ai_embeddings)
        if pref_list is None:
            pref_list = profile_embeddings.get(ticket_id)
        if pref_list is None:
            continue
        pref = np.asarray(pref_list, dtype=np.float32)

        self_vec = profile_embeddings.get(ticket_id)
        if self_vec is not None:
            self_np = np.asarray(self_vec, dtype=np.float32)
            confidence = min(1.0, len([s for s in swipes if s.get("liked") is True]) / 6.0)
            pref = (confidence * pref) + ((1.0 - confidence) * self_np)
            norm = float(np.linalg.norm(pref))
            if norm > 1e-12:
                pref = pref / norm

        scored: List[Dict[str, Any]] = []
        for cand_id, cand_profile in profiles.items():
            if cand_id == ticket_id:
                continue
            if str(cand_profile.get("gender") or "") != target_gender:
                continue
            emb = profile_embeddings.get(cand_id)
            if emb is None:
                continue
            score = cosine(pref, np.asarray(emb, dtype=np.float32))
            scored.append({"ticketId": cand_id, "uid": cand_id, "score": score})

        scored.sort(key=lambda row: row["score"], reverse=True)
        items = []
        for idx, row in enumerate(scored[: args.topn]):
            items.append({**row, "rank": idx + 1})
        if not items:
            continue

        bw.set(
            db.document(f"festivalModelRecs/{ticket_id}/daily/{date_key}/sources/clip"),
            {
                "status": "ready",
                "algorithmVersion": "festival_clip_batch_py_v1",
                "model": {"type": "clip", "source": "festival_clip_recommend.py"},
                "generatedAt": firestore.SERVER_TIMESTAMP,
                "topN": len(items),
                "items": items,
                "signal": {"affinities": affinities},
            },
            merge=True,
        )
        bw.set(
            db.collection("festivalTickets").document(ticket_id),
            {
                "aiProfileAffinities": affinities,
                "preferenceVector": {
                    "vector": pref.tolist(),
                    "dims": int(pref.shape[0]),
                    "modelId": "festival-clip-v1",
                    "source": "festival_clip_recommend.py",
                },
            },
            merge=True,
        )
        generated += 1
        print(f"[ok] {ticket_id} -> {len(items)} items")

    bw.close()
    print(f"[done] generated for {generated} tickets ({date_key})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
