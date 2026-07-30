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
import re
import sys
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import numpy as np
from tqdm import tqdm

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

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


def is_ai_profile(target_id: str) -> bool:
    """ai_preference 타겟: female_123, male_456"""
    return bool(target_id and re.match(r"^(female|male)_\d+$", str(target_id)))


def ai_profile_to_storage_url(
    ai_profile_id: str,
    *,
    bucket: str = "seolleyeon.firebasestorage.app",
) -> str:
    """female_385 -> Firebase Storage download URL"""
    m = re.match(r"^(female|male)_(\d+)$", str(ai_profile_id))
    if not m:
        raise ValueError(f"Invalid ai_profile_id: {ai_profile_id}")
    folder, pid = m.group(1), m.group(2)
    path = f"ai_profiles/{folder}/{pid}.png"
    encoded = quote(path, safe="")
    return f"https://firebasestorage.googleapis.com/v0/b/{bucket}/o/{encoded}?alt=media"


def add_ai_profiles_to_uid_urls(
    uid_to_urls: Dict[str, List[str]],
    likes: Dict[str, List[str]],
    nopes: Dict[str, List[str]],
    *,
    bucket: str = "seolleyeon.firebasestorage.app",
) -> None:
    """likes/nopes에 있는 ai_profile 타겟을 uid_to_urls에 추가 (in-place)"""
    seen: set[str] = set()
    for targets in list(likes.values()) + list(nopes.values()):
        for t in targets:
            if is_ai_profile(t) and t not in seen:
                seen.add(t)
                try:
                    url = ai_profile_to_storage_url(t, bucket=bucket)
                    uid_to_urls[t] = [url]
                except Exception:
                    pass


def load_user_genders_from_firestore(
    project_id: str,
    *,
    users_collection: str = "users",
    database: Optional[str] = None,
) -> Dict[str, str]:
    """users/{uid} onboarding.gender 로드. uid -> gender (female|male 등)"""
    db = firestore.Client(project=project_id, database=database)
    result: Dict[str, str] = {}
    for doc in db.collection(users_collection).stream():
        d = doc.to_dict() or {}
        onboarding = d.get("onboarding")
        if isinstance(onboarding, dict):
            g = onboarding.get("gender")
            if g is not None:
                result[doc.id] = str(g).strip().lower()
    return result


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


def _rec_events_created_at_query_bounds(
    start_time_utc: Optional[datetime], end_time_utc: Optional[datetime]
) -> Tuple[Optional[str], Optional[str]]:
    """Flutter rec_event_service는 createdAt을 UTC ISO 문자열로 저장함. datetime으로 쿼리하면 0건."""
    def to_iso(dt: datetime) -> str:
        u = dt.astimezone(timezone.utc)
        return u.strftime("%Y-%m-%dT%H:%M:%S.000Z")

    return (
        to_iso(start_time_utc) if start_time_utc is not None else None,
        to_iso(end_time_utc) if end_time_utc is not None else None,
    )


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
        start_str, end_str = _rec_events_created_at_query_bounds(start_time_utc, end_time_utc)
        if start_str is not None:
            q = q.where(filter=FieldFilter("createdAt", ">=", start_str))
        if end_str is not None:
            q = q.where(filter=FieldFilter("createdAt", "<", end_str))

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

    # ai_preference like/nope 타겟(ai_profiles)을 uid_to_urls에 추가
    bucket = os.environ.get("FIREBASE_STORAGE_BUCKET", "seolleyeon.firebasestorage.app")
    add_ai_profiles_to_uid_urls(uid_to_urls, likes, nopes, bucket=bucket)

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

    # users/onboarding gender (동성 제외용)
    gender_by_uid = load_user_genders_from_firestore(
        args.firestore_project,
        users_collection=args.users_collection,
        database=args.firestore_database,
    )
    print(f"[gender] loaded from users/onboarding: {len(gender_by_uid)} users")

    uids = list(uid_to_vec.keys())
    emb_matrix = np.array([uid_to_vec[u] for u in uids], dtype=np.float32)
    uid_to_idx = {u: i for i, u in enumerate(uids)}

    # 4) 사용자별 TopN 생성
    print("[3] Generating recommendations...")
    recs_to_export: Dict[str, List[Dict[str, Any]]] = {}
    topn = args.topn

    for user_id in tqdm(uid_to_vec.keys(), desc="recs"):
        # AI 취향 카드 ID(male_*, female_*)는 임베딩·학습용으로만 쓰고 modelRecs 문서는 만들지 않음
        if is_ai_profile(user_id):
            continue
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
            # ai_preference 타겟은 추천 출력에서 제외
            if is_ai_profile(cand_uid):
                continue
            # 동성 제외: users/onboarding.gender 기준
            u_g = gender_by_uid.get(user_id)
            v_g = gender_by_uid.get(cand_uid)
            if u_g and v_g and u_g == v_g:
                continue
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
