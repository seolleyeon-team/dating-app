#!/usr/bin/env python3
"""
Firestore users 컬렉션에 더미 사용자 100명 생성

- ID: 1로 시작하는 10자리 난수
- 템플릿: users/4705818223
- photoUrls: Firebase Storage ai_profiles/female 또는 ai_profiles/male (gender에 따라)
"""

from __future__ import annotations

import argparse
import random
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List
from urllib.parse import quote

from google.cloud import firestore, storage


TEMPLATE_USER_ID = "4705818223"
BUCKET_NAME = "seolleyeon.firebasestorage.app"
AI_PROFILES_PREFIX = "ai_profiles/"


def generate_dummy_id(existing_ids: set) -> str:
    """1로 시작하는 10자리 고유 ID 생성"""
    while True:
        uid = "1" + "".join(str(random.randint(0, 9)) for _ in range(9))
        if uid not in existing_ids:
            existing_ids.add(uid)
            return uid


def list_storage_urls(
    bucket_name: str,
    prefix: str,
    *,
    use_signed_url: bool = True,
    expiration_minutes: int = 60 * 24 * 365 * 10,  # 10년
) -> List[str]:
    """Storage prefix 하위 파일들의 download URL 목록 반환"""
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blobs = list(bucket.list_blobs(prefix=prefix))
    urls: List[str] = []

    for blob in blobs:
        if blob.name.endswith("/"):
            continue
        try:
            if use_signed_url:
                url = blob.generate_signed_url(
                    expiration=timedelta(minutes=expiration_minutes),
                    method="GET",
                )
            else:
                encoded = quote(blob.name, safe="")
                url = f"https://firebasestorage.googleapis.com/v0/b/{bucket_name}/o/{encoded}?alt=media"
            urls.append(url)
        except Exception as e:
            print(f"    [warn] Skip {blob.name}: {e}")

    return urls


def load_template_user(
    project_id: str,
    user_id: str,
    database: str | None = None,
) -> Dict[str, Any] | None:
    """Firestore에서 템플릿 사용자 로드"""
    db = firestore.Client(project=project_id, database=database)
    doc = db.collection("users").document(user_id).get()
    if not doc.exists:
        return None
    return doc.to_dict()


def _deep_copy_serializable(obj: Any) -> Any:
    """Firestore 호환 가능한 deep copy (Timestamp 등 유지)"""
    if isinstance(obj, dict):
        return {k: _deep_copy_serializable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_deep_copy_serializable(v) for v in obj]
    return obj


def create_dummy_user(
    template: Dict[str, Any],
    user_id: str,
    female_urls: List[str],
    male_urls: List[str],
    index: int,
) -> Dict[str, Any]:
    """템플릿 기반 더미 사용자 1명 생성"""
    data = _deep_copy_serializable(template)

    # ID 관련 필드 제거 (문서 ID로 사용)
    for key in ("kakaoUserId", "id"):
        data.pop(key, None)

    # gender 랜덤 할당 (50:50)
    gender = random.choice(["female", "male"])
    photo_pool = female_urls if gender == "female" else male_urls

    # photoUrls: gender에 맞는 폴더에서 2~6장 랜덤 선택 (해당 폴더 비어있으면 반대 성별 fallback)
    if not photo_pool:
        photo_pool = male_urls if gender == "female" else female_urls
    if photo_pool:
        photo_urls = [random.choice(photo_pool)]
    else:
        photo_urls = []

    # onboarding 업데이트
    onboarding = data.get("onboarding") or {}
    if isinstance(onboarding, dict):
        onboarding = dict(onboarding)
    else:
        onboarding = {}

    onboarding["gender"] = gender
    onboarding["photoUrls"] = photo_urls
    onboarding["nickname"] = f"더미{index + 1}"
    onboarding["age"] = onboarding.get("age") or random.randint(22, 28)
    onboarding["height"] = onboarding.get("height") or random.randint(160, 185)
    onboarding["birthYear"] = datetime.now().year - (onboarding["age"] or 25)

    data["onboarding"] = onboarding
    data["initialSetupComplete"] = True
    data["isStudentVerified"] = True
    data["createdAt"] = firestore.SERVER_TIMESTAMP
    data["lastLoginAt"] = firestore.SERVER_TIMESTAMP

    return data


def main():
    p = argparse.ArgumentParser(description="Create dummy users in Firestore")
    p.add_argument("--firestore_project", type=str, default="seolleyeon")
    p.add_argument("--firestore_database", type=str, default=None)
    p.add_argument("--count", type=int, default=100)
    p.add_argument("--template_user", type=str, default=TEMPLATE_USER_ID)
    p.add_argument("--dry_run", action="store_true", help="실제 쓰기 없이 출력만")
    p.add_argument("--offline_dry_run", action="store_true", help="인증 없이 로직만 검증 (가짜 템플릿 사용)")
    args = p.parse_args()

    if args.offline_dry_run:
        print("[OFFLINE DRY RUN] Using fake template (no Firestore/Storage)...")
        template = {"onboarding": {"age": 25, "height": 170}}
        female_urls = ["https://example.com/female1.jpg"]
        male_urls = ["https://example.com/male1.jpg"]
        existing = set()
    else:
        print("[1] Loading template user...")
        template = load_template_user(
            args.firestore_project,
            args.template_user,
            args.firestore_database,
        )
        if not template:
            print(f"[ERROR] Template user {args.template_user} not found.")
            return 1

        print(f"    Template loaded: {list(template.keys())[:10]}...")

        print("[2] Loading Storage images...")
        female_urls = list_storage_urls(BUCKET_NAME, f"{AI_PROFILES_PREFIX}female/")
        male_urls = list_storage_urls(BUCKET_NAME, f"{AI_PROFILES_PREFIX}male/")
        print(f"    female: {len(female_urls)} images")
        print(f"    male: {len(male_urls)} images")

        if not female_urls and not male_urls:
            print("[WARN] No images in ai_profiles. photoUrls will be empty.")
            print("       Upload images to gs://{}/ai_profiles/female/ and .../male/".format(BUCKET_NAME))

        print("[3] Generating dummy users...")
        db = firestore.Client(project=args.firestore_project, database=args.firestore_database)
        existing = {doc.id for doc in db.collection("users").stream()}
    dummy_users: List[tuple[str, Dict[str, Any]]] = []

    for i in range(args.count):
        uid = generate_dummy_id(existing)
        user_data = create_dummy_user(
            template, uid, female_urls, male_urls, i
        )
        dummy_users.append((uid, user_data))

    if args.dry_run or args.offline_dry_run:
        print(f"[DRY RUN] Would create {len(dummy_users)} users.")
        for uid, data in dummy_users[:5]:
            photos = data.get("onboarding", {}).get("photoUrls", [])
            print(f"  - {uid}: {data.get('onboarding', {}).get('nickname')} ({data.get('onboarding', {}).get('gender')}) photoUrls: {len(photos)}")
        return 0

    print("[4] Writing to Firestore...")
    bw = db.bulk_writer()
    for uid, user_data in dummy_users:
        doc_ref = db.collection("users").document(uid)
        bw.set(doc_ref, user_data, merge=True)

    bw.close()
    print(f"[DONE] Created {len(dummy_users)} dummy users.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
