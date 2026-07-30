#!/usr/bin/env python3
"""Export CLIP embeddings for festivalProfiles into festivalProfileEmbeddings."""

from __future__ import annotations

import argparse
import os
import sys

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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--database", default=None)
    args = parser.parse_args()

    require_firestore()
    db = firestore.Client(project=args.project, database=args.database)
    embedder = SeolleyeonCLIPEmbedder(device="auto")

    profiles = db.collection("festivalProfiles").stream()
    bw = db.bulk_writer()
    count = 0
    for snap in profiles:
        data = snap.to_dict() or {}
        photo_url = str(data.get("photoUrl") or "").strip()
        if not photo_url:
            continue
        try:
            vec, _ = embedder.embed_profile_mean([photo_url], normalize=True)
        except Exception as exc:
            print(f"[skip] {snap.id}: {exc}")
            continue
        bw.set(
            db.collection("festivalProfileEmbeddings").document(snap.id),
            {
                "ticketId": snap.id,
                "vector": vec,
                "dims": len(vec),
                "modelId": "clip-vit-base-patch32",
                "photoUrl": photo_url,
                "updatedAt": firestore.SERVER_TIMESTAMP,
            },
            merge=True,
        )
        count += 1
        print(f"[ok] {snap.id}")
    bw.close()
    print(f"[done] exported {count} profile embeddings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
