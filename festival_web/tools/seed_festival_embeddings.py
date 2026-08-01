#!/usr/bin/env python3
"""
Seed festivalAiEmbeddings + festivalProfileEmbeddings via CLIP + Firestore REST.

Uses firebase login access token (no gcloud ADC required).

Usage:
  python3 tools/seed_festival_embeddings.py
  python3 tools/seed_festival_embeddings.py --profiles-only
  python3 tools/seed_festival_embeddings.py --ai-only
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

ROOT = Path(__file__).resolve().parents[2]
AI_DIR = ROOT / "festival_web" / "ai_recommend_model"
MAIN_AI = ROOT / "lib" / "ai_recommend_model"
for p in (AI_DIR, MAIN_AI):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from seolleyeon_clip_embedder import SeolleyeonCLIPEmbedder  # noqa: E402

PROJECT_ID = "seolleyeon-festival"
DATABASE = "(default)"
BUCKET = os.environ.get(
    "FIREBASE_STORAGE_BUCKET", "seolleyeon-festival.firebasestorage.app"
)
BASE = f"https://firestore.googleapis.com/v1/projects/{PROJECT_ID}/databases/{DATABASE}/documents"
CONFIG_PATH = Path.home() / ".config/configstore/firebase-tools.json"


def get_access_token() -> str:
    if not CONFIG_PATH.exists():
        raise SystemExit("firebase login이 필요합니다.")
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    token = data.get("tokens", {}).get("access_token")
    if not token:
        raise SystemExit("firebase access token을 찾지 못했습니다.")
    return token


def vector_to_firestore(values: list[float]) -> dict[str, Any]:
    return {
        "arrayValue": {
            "values": [{"doubleValue": float(v)} for v in values],
        }
    }


def firestore_set(
    collection: str,
    doc_id: str,
    fields: dict[str, Any],
    token: str,
) -> None:
    path = f"{collection}/{doc_id}"
    url = f"{BASE}/{path}"
    body = {"fields": fields}
    resp = requests.patch(
        url,
        params={"updateMask.fieldPaths": ",".join(fields.keys())},
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json=body,
        timeout=120,
    )
    if resp.status_code == 404:
        resp = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=120,
        )
    if not resp.ok:
        raise RuntimeError(f"Firestore write failed {path}: {resp.status_code} {resp.text}")


def list_profiles(token: str) -> list[tuple[str, str]]:
    url = f"{BASE}:runQuery"
    profiles: list[tuple[str, str]] = []
    for gender in ("남성", "여성"):
        query = {
            "structuredQuery": {
                "from": [{"collectionId": "festivalProfiles"}],
                "where": {
                    "fieldFilter": {
                        "field": {"fieldPath": "gender"},
                        "op": "EQUAL",
                        "value": {"stringValue": gender},
                    }
                },
            }
        }
        resp = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=query,
            timeout=60,
        )
        resp.raise_for_status()
        for row in resp.json():
            doc = row.get("document")
            if not doc:
                continue
            doc_id = doc["name"].split("/")[-1]
            fields = doc.get("fields", {})
            photo = fields.get("photoUrl", {}).get("stringValue", "").strip()
            if photo:
                profiles.append((doc_id, photo))
    return profiles


def ai_image_url(code: str) -> str:
    gender = "female" if code.startswith("f") else "male"
    path = f"ai_profiles/{gender}/{code}.png"
    encoded = quote(path, safe="")
    return f"https://firebasestorage.googleapis.com/v0/b/{BUCKET}/o/{encoded}?alt=media"


def seed_ai(embedder: SeolleyeonCLIPEmbedder, token: str) -> int:
    codes: list[str] = []
    for i in range(1, 21):
        codes.append(f"f{i}")
        codes.append(f"m{i}")

    count = 0
    for code in codes:
        url = ai_image_url(code)
        print(f"[ai] {code} …", flush=True)
        vec, _ = embedder.embed_profile_mean([url], normalize=True)
        firestore_set(
            "festivalAiEmbeddings",
            code,
            {
                "code": {"stringValue": code},
                "vector": vector_to_firestore(vec),
                "dims": {"integerValue": str(len(vec))},
                "modelId": {"stringValue": "clip-vit-large-patch14"},
                "imageUrl": {"stringValue": url},
                "updatedAt": {"timestampValue": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())},
            },
            token,
        )
        count += 1
    return count


def seed_profiles(embedder: SeolleyeonCLIPEmbedder, token: str) -> int:
    profiles = list_profiles(token)
    print(f"[profiles] found {len(profiles)} with photoUrl")
    count = 0
    for ticket_id, photo_url in profiles:
        print(f"[profile] {ticket_id} …", flush=True)
        try:
            vec, _ = embedder.embed_profile_mean([photo_url], normalize=True)
        except Exception as exc:
            print(f"  skip: {exc}")
            continue
        firestore_set(
            "festivalProfileEmbeddings",
            ticket_id,
            {
                "ticketId": {"stringValue": ticket_id},
                "vector": vector_to_firestore(vec),
                "dims": {"integerValue": str(len(vec))},
                "modelId": {"stringValue": "clip-vit-large-patch14"},
                "photoUrl": {"stringValue": photo_url},
                "updatedAt": {"timestampValue": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())},
            },
            token,
        )
        count += 1
    return count


def verify(token: str) -> None:
    for coll in ("festivalAiEmbeddings", "festivalProfileEmbeddings"):
        resp = requests.get(
            f"{BASE}/{coll}",
            params={"pageSize": 3},
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        resp.raise_for_status()
        docs = resp.json().get("documents", [])
        print(f"[verify] {coll}: {len(docs)}+ docs (sample: {[d['name'].split('/')[-1] for d in docs]})")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ai-only", action="store_true")
    parser.add_argument("--profiles-only", action="store_true")
    parser.add_argument("--device", default="auto")
    args = parser.parse_args()

    run_ai = not args.profiles_only
    run_profiles = not args.ai_only

    token = get_access_token()
    print("Loading CLIP model (first run may download weights)…", flush=True)
    embedder = SeolleyeonCLIPEmbedder(device=args.device)

    if run_ai:
        n = seed_ai(embedder, token)
        print(f"[done] AI embeddings: {n}")

    if run_profiles:
        n = seed_profiles(embedder, token)
        print(f"[done] Profile embeddings: {n}")

    verify(token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
