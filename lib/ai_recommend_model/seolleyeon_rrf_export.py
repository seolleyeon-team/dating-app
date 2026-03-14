#!/usr/bin/env python3
"""
Seolleyeon RRF (Reciprocal Rank Fusion) - 통합 추천 Firestore 저장

목표:
- CLIP, SVD, KNN 각 소스의 TopN을 RRF로 합쳐
  modelRecs/{uid}/daily/{dateKey}/sources/rrf 에 저장.

RRF 공식: score(uid) = sum over sources of 1/(k + rank)
기본 k=60 (논문 권장값)

입력:
- modelRecs/{uid}/daily/{dateKey}/sources/clip
- modelRecs/{uid}/daily/{dateKey}/sources/svd
- modelRecs/{uid}/daily/{dateKey}/sources/knn

출력:
- modelRecs/{uid}/daily/{dateKey}/sources/rrf
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from google.cloud import firestore


def parse_datekey(date_key: str) -> str:
    if len(date_key) != 8:
        raise ValueError("dateKey must be YYYYMMDD")
    return date_key


def load_source_items(
    doc_ref,
) -> Optional[List[Dict[str, Any]]]:
    """문서에서 items 배열 로드. 없거나 비어있으면 None."""
    try:
        snap = doc_ref.get()
        if not snap.exists:
            return None
        data = snap.to_dict() or {}
        items = data.get("items")
        if not isinstance(items, list) or len(items) == 0:
            return None
        return items
    except Exception:
        return None


def rrf_merge(
    source_lists: List[List[Dict[str, Any]]],
    k: int = 60,
) -> List[Dict[str, Any]]:
    """
    RRF: score = sum(1/(k+rank))
    각 소스는 [{"uid": "...", "rank": 1, "score": ...}, ...] 형태
    """
    scores: Dict[str, float] = {}
    for lst in source_lists:
        for rank, item in enumerate(lst, start=1):
            uid = item.get("uid")
            if not uid:
                continue
            uid = str(uid)
            scores[uid] = scores.get(uid, 0.0) + 1.0 / (k + rank)

    sorted_items = sorted(scores.items(), key=lambda x: -x[1])
    result: List[Dict[str, Any]] = []
    for rank, (uid, rrf_score) in enumerate(sorted_items, start=1):
        result.append({
            "uid": uid,
            "rank": rank,
            "score": round(rrf_score, 6),
        })
    return result


def main():
    p = argparse.ArgumentParser(
        description="Seolleyeon RRF merge (CLIP+SVD+KNN) + Firestore export"
    )
    p.add_argument("--firestore_project", type=str, required=True)
    p.add_argument("--firestore_database", type=str, default=None)
    p.add_argument("--date_key", type=str, required=True, help="YYYYMMDD (KST)")
    p.add_argument("--rrf_k", type=int, default=60, help="RRF k parameter")
    p.add_argument("--sources", type=str, default="clip,svd,knn",
                   help="Comma-separated source names (e.g. clip,svd,knn)")
    p.add_argument("--topn", type=int, default=400, help="Max items per user in output")

    args = p.parse_args()
    date_key = parse_datekey(args.date_key)
    source_names = [s.strip() for s in args.sources.split(",") if s.strip()]

    db = firestore.Client(project=args.firestore_project, database=args.firestore_database)

    # modelRecs에 문서가 있는 user id 수집
    user_ids = [doc.id for doc in db.collection("modelRecs").list_documents()]
    print(f"[RRF] Checking {len(user_ids)} users in modelRecs")

    recs_to_export: Dict[str, List[Dict[str, Any]]] = {}
    for uid in user_ids:
        source_lists: List[List[Dict[str, Any]]] = []
        for algo in source_names:
            doc_ref = db.document(f"modelRecs/{uid}/daily/{date_key}/sources/{algo}")
            items = load_source_items(doc_ref)
            if items:
                source_lists.append(items)

        if not source_lists:
            continue

        merged = rrf_merge(source_lists, k=args.rrf_k)
        recs_to_export[uid] = merged[: args.topn]

    print(f"[export] RRF merged for {len(recs_to_export)} users")

    # Firestore 저장
    bw = db.bulk_writer()
    gen_at = firestore.SERVER_TIMESTAMP
    algo_version = f"rrf_k{args.rrf_k}_{date_key}"
    model_meta = {
        "type": "rrf",
        "k": args.rrf_k,
        "sources": source_names,
        "generatedAt": datetime.now(tz=timezone.utc).isoformat(),
    }

    for uid, items in recs_to_export.items():
        doc_ref = db.document(f"modelRecs/{uid}/daily/{date_key}/sources/rrf")
        bw.set(doc_ref, {
            "status": "ready",
            "algorithmVersion": algo_version,
            "model": model_meta,
            "generatedAt": gen_at,
            "topN": len(items),
            "items": items,
        }, merge=True)

    bw.close()
    print("[export] RRF done")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
