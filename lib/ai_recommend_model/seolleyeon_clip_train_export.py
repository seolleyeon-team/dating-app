#!/usr/bin/env python3
"""
Seolleyeon CLIP-based Recommender - Train & Export

목표:
- 프로필 사진 CLIP 임베딩 + 사용자 like/nope 기반 preference vector로
  TopN 후보를 산출한 뒤 Firestore modelRecs/{uid}/daily/{dateKey}/sources/clip 에 저장.

입력:
- Firestore users: onboarding.photoUrls
- Firestore recEvents: like/nope 이벤트 (preference vector 계산용)
- SVD/KNN 결과가 없으면 content-based(전체 유저 유사도)로 fallback

Firestore 저장:
- modelRecs/{uid}/daily/{dateKey}/sources/clip
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from tqdm import tqdm

from google.cloud import firestore

# 스크립트 디렉터리를 path에 추가 (프로젝트 루트에서 실행 시)
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)
from seolleyeon_clip_embedder import SeolleyeonCLIPEmbedder


def parse_datekey(date_key: str) -> str:
    """YYYYMMDD 검증"""
    if len(date_key) != 8:
        raise ValueError("dateKey must be YYYYMMDD")
    return date_key


def load_users_with_photos(
    project_id: str,
    *,
    users_collection: str = "users",
    database: Optional[str] = None,
) -> Dict[str, List[str]]:
    """users/{uid} 에서 onboarding.photoUrls 로드. uid -> [image_urls]"""
    db = firestore.Client(project=project_id, database=database)
    result: Dict[str, List[str]] = {}

    for doc in db.collection(users_collection).stream():
        uid = doc.id
        d = doc.to_dict() or {}
        onboarding = d.get("onboarding")
        if not isinstance(onboarding, dict):
            continue
        photos = onboarding.get("photoUrls")
        if not isinstance(photos, list) or len(photos) == 0:
            continue
        urls = [str(p) for p in photos if p and str(p).startswith("http")]
        if urls:
            result[uid] = urls

    return result


def load_like_nope_from_firestore(
    project_id: str,
    *,
    collection: str = "recEvents",
    start_time_utc: Optional[datetime] = None,
    end_time_utc: Optional[datetime] = None,
    database: Optional[str] = None,
) -> Tuple[Dict[str, List[str]], Dict[str, List[str]]]:
    """recEvents/{userId}/events 에서 like/nope 로드. userId -> [targetUserId, ...]"""
    db = firestore.Client(project=project_id, database=database)
    likes: Dict[str, List[str]] = {}
    nopes: Dict[str, List[str]] = {}

    for user_doc_ref in db.collection(collection).list_documents():
        user_id = user_doc_ref.id
        q = user_doc_ref.collection("events")
        if start_time_utc is not None:
            q = q.where("createdAt", ">=", start_time_utc)
        if end_time_utc is not None:
            q = q.where("createdAt", "<", end_time_utc)

        for doc in q.stream():
            d = doc.to_dict() or {}
            target = d.get("targetUserId") or d.get("targetId") or d.get("candidateUserId")
            event = d.get("eventType") or d.get("type")
            if not target or not event:
                continue
            target = str(target)
            event = str(event).lower()

            if event == "like":
                likes.setdefault(user_id, []).append(target)
            elif event == "nope":
                nopes.setdefault(user_id, []).append(target)

    return likes, nopes


def rrf_merge(
    ranked_lists: List[List[Tuple[str, float]]],
    k: int = 60,
) -> List[Tuple[str, float]]:
    """RRF: score = sum(1/(k+rank)). 여러 리스트를 하나로 합침."""
    scores: Dict[str, float] = {}
    for lst in ranked_lists:
        for rank, (uid, _) in enumerate(lst, start=1):
            scores[uid] = scores.get(uid, 0.0) + 1.0 / (k + rank)

    sorted_items = sorted(scores.items(), key=lambda x: -x[1])
    return sorted_items


def main():
    p = argparse.ArgumentParser(
        description="Seolleyeon CLIP-based recommendation + Firestore export"
    )
    p.add_argument("--firestore_project", type=str, required=True, help="GCP project id")
    p.add_argument("--firestore_database", type=str, default=None)
    p.add_argument("--date_key", type=str, required=True, help="YYYYMMDD (KST)")
    p.add_argument("--lookback_days", type=int, default=120)
    p.add_argument("--topn", type=int, default=400)
    p.add_argument("--device", type=str, default="auto")
    p.add_argument("--export_firestore", action="store_true", default=True)
    p.add_argument("--users_collection", type=str, default="users")
    p.add_argument("--events_collection", type=str, default="recEvents")
    p.add_argument("--skip_clip_if_no_torch", action="store_true", help="torch 미설치 시 CLIP 스킵")

    args = p.parse_args()
    date_key = parse_datekey(args.date_key)

    # 1) users + photoUrls 로드
    print("[1] Loading users with photos...")
    uid_to_urls = load_users_with_photos(
        args.firestore_project,
        users_collection=args.users_collection,
        database=args.firestore_database,
    )
    print(f"    Loaded {len(uid_to_urls)} users with photos")

    if len(uid_to_urls) < 2:
        print("[!] Not enough users with photos. Skipping CLIP export.")
        return 0

    # 2) like/nope 로드
    kst = timezone(timedelta(hours=9))
    yyyy, mm, dd = int(date_key[:4]), int(date_key[4:6]), int(date_key[6:8])
    end_kst = datetime(yyyy, mm, dd, 23, 59, 59, tzinfo=kst)
    start_utc = (end_kst - timedelta(days=args.lookback_days)).astimezone(timezone.utc)
    end_utc = end_kst.astimezone(timezone.utc)

    likes, nopes = load_like_nope_from_firestore(
        args.firestore_project,
        collection=args.events_collection,
        start_time_utc=start_utc,
        end_time_utc=end_utc,
        database=args.firestore_database,
    )
    print(f"    Users with likes: {len(likes)}, with nopes: {len(nopes)}")

    # 3) CLIP 임베딩 (uid -> vector)
    try:
        embedder = SeolleyeonCLIPEmbedder(device=args.device)
    except Exception as e:
        if args.skip_clip_if_no_torch:
            print(f"[!] CLIP init failed ({e}). Skipping.")
            return 0
        raise

    print("[2] Computing profile embeddings...")
    uid_to_vec: Dict[str, List[float]] = {}
    for uid, urls in tqdm(uid_to_urls.items(), desc="embed"):
        try:
            vec, _ = embedder.embed_profile_mean(urls[:3], normalize=True)  # 최대 3장
            uid_to_vec[uid] = vec
        except Exception as ex:
            print(f"    Skip {uid}: {ex}")

    if len(uid_to_vec) < 2:
        print("[!] Not enough embeddings. Skipping.")
        return 0

    uids = list(uid_to_vec.keys())
    emb_matrix = np.array([uid_to_vec[u] for u in uids], dtype=np.float32)
    uid_to_idx = {u: i for i, u in enumerate(uids)}

    # 4) 사용자별 TopN 생성
    print("[3] Generating recommendations...")
    recs_to_export: Dict[str, List[Dict[str, Any]]] = {}
    topn = args.topn

    for user_id in tqdm(uid_to_vec.keys(), desc="recs"):
        if user_id not in uid_to_idx:
            continue
        user_idx = uid_to_idx[user_id]

        # preference vector: mean(like) - mean(nope)
        like_targets = likes.get(user_id, [])
        nope_targets = nopes.get(user_id, [])

        if like_targets or nope_targets:
            like_vecs = [
                uid_to_vec[t] for t in like_targets
                if t in uid_to_vec and t != user_id
            ]
            nope_vecs = [
                uid_to_vec[t] for t in nope_targets
                if t in uid_to_vec and t != user_id
            ]
            if like_vecs or nope_vecs:
                pref = np.zeros(emb_matrix.shape[1], dtype=np.float32)
                if like_vecs:
                    pref += np.mean(like_vecs, axis=0)
                if nope_vecs:
                    pref -= np.mean(nope_vecs, axis=0)
                norm = np.linalg.norm(pref)
                if norm > 1e-9:
                    pref = pref / norm
            else:
                pref = emb_matrix[user_idx]  # 자기 프로필 유사도 (content-based)
        else:
            pref = emb_matrix[user_idx]  # cold start: 자기 프로필과 유사한 사람

        scores = emb_matrix @ pref

        exclude = {user_idx}
        for t in like_targets + nope_targets:
            if t in uid_to_idx:
                exclude.add(uid_to_idx[t])
        scores[list(exclude)] = -np.inf

        top_indices = np.argsort(-scores)[: topn * 2]
        items_out: List[Dict[str, Any]] = []
        for rank, ii in enumerate(top_indices, start=1):
            if scores[ii] <= -np.inf:
                continue
            cand_uid = uids[ii]
            items_out.append({
                "uid": cand_uid,
                "rank": len(items_out) + 1,
                "score": float(scores[ii]),
            })
            if len(items_out) >= topn:
                break

        if items_out:
            recs_to_export[user_id] = items_out

    print(f"[export] prepared recs for {len(recs_to_export)} users")

    # 5) Firestore 저장
    if args.export_firestore and recs_to_export:
        db = firestore.Client(project=args.firestore_project, database=args.firestore_database)
        bw = db.bulk_writer()
        trained_at = datetime.now(tz=timezone.utc).isoformat()
        algo_version = f"clip_{date_key}"

        for uid, items in recs_to_export.items():
            doc_ref = db.document(f"modelRecs/{uid}/daily/{date_key}/sources/clip")
            bw.set(doc_ref, {
                "status": "ready",
                "algorithmVersion": algo_version,
                "model": {"type": "clip", "trainedAt": trained_at},
                "generatedAt": firestore.SERVER_TIMESTAMP,
                "topN": len(items),
                "items": items,
            }, merge=True)

        bw.close()
        print("[export] CLIP done")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
