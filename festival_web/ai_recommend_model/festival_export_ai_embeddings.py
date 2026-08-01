#!/usr/bin/env python3
"""Export CLIP embeddings for festival AI taste cards into festivalAiEmbeddings."""

from __future__ import annotations

import argparse
import os
import sys
from urllib.parse import quote

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_SCRIPT_DIR, "..", ".."))
_MAIN_AI_DIR = os.path.join(_REPO_ROOT, "lib", "ai_recommend_model")
for path in (_SCRIPT_DIR, _MAIN_AI_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

from festival_rec_common import require_firestore  # noqa: E402
from seolleyeon_clip_embedder import SeolleyeonCLIPEmbedder  # noqa: E402

try:
    from google.cloud import firestore
except Exception:  # pragma: no cover
    firestore = None


def ai_url(code: str, *, bucket: str) -> str:
    gender = "female" if code.startswith("f") else "male"
    path = f"ai_profiles/{gender}/{code}.png"
    encoded = quote(path, safe="")
    return f"https://firebasestorage.googleapis.com/v0/b/{bucket}/o/{encoded}?alt=media"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--database", default=None)
    parser.add_argument(
        "--bucket",
        default=os.environ.get(
            "FIREBASE_STORAGE_BUCKET", "seolleyeon-festival.firebasestorage.app"
        ),
    )
    args = parser.parse_args()

    require_firestore()
    db = firestore.Client(project=args.project, database=args.database)
    embedder = SeolleyeonCLIPEmbedder(device="auto")

    codes: list[str] = []
    for i in range(1, 21):
        codes.append(f"f{i}")
        codes.append(f"m{i}")

    bw = db.bulk_writer()
    for code in codes:
        url = ai_url(code, bucket=args.bucket)
        vec, _ = embedder.embed_profile_mean([url], normalize=True)
        bw.set(
            db.collection("festivalAiEmbeddings").document(code),
            {
                "code": code,
                "vector": vec,
                "dims": len(vec),
                "modelId": "clip-vit-base-patch32",
                "imageUrl": url,
                "updatedAt": firestore.SERVER_TIMESTAMP,
            },
            merge=True,
        )
        print(f"[ok] {code}")
    bw.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
