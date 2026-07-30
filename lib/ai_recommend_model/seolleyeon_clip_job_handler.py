#!/usr/bin/env python3
"""Process Seolleyeon CLIP embedding jobs from private GCS source photos.

The handler accepts the upload pipeline's ``clip_job_v1`` payload, reloads the
authoritative source photo refs from backend-only ``userPrivateMedia/{uid}``,
computes a normalized CLIP profile embedding, and writes backend-only
``clipEmbeddings/{uid}``.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

try:
    from google.cloud import firestore
except Exception:  # pragma: no cover - optional in fixture tests
    firestore = None

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from seolleyeon_clip_embedder import DEFAULT_MODEL_ID, SeolleyeonCLIPEmbedder
from seolleyeon_rec_common_v3 import redact_private_image_ref

CLIP_SCHEMA_VERSION = "clip_job_v1"
CLIP_JOB_TYPE = "clip_embedding"
DEFAULT_EMBEDDING_VERSION = "clip-vit-large-patch14_v1"
DEFAULT_PRIVATE_SOURCE_PHOTO_BUCKET = "seolleyeon-private-" "source-photos"


def _as_str(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _as_str_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    out: List[str] = []
    seen = set()
    for item in value:
        text = _as_str(item)
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def _parse_allowed_buckets(value: str | None = None) -> Optional[set[str]]:
    raw = (
        value
        if value is not None
        else os.getenv("ALLOWED_GCS_IMAGE_BUCKETS", DEFAULT_PRIVATE_SOURCE_PHOTO_BUCKET)
    )
    raw = (raw or "").strip()
    if not raw:
        return None
    buckets = {item.strip() for item in raw.split(",") if item.strip()}
    return buckets or None


def _gcs_bucket(source: str) -> str:
    if source.startswith("gs://"):
        rest = source[len("gs://") :]
    elif source.startswith("gcs://"):
        rest = source[len("gcs://") :]
    else:
        return ""
    return rest.split("/", 1)[0].strip()


def _load_json_arg(value: str) -> Dict[str, Any]:
    """Load a JSON string or a path containing JSON."""
    candidate = Path(value)
    if candidate.exists():
        return json.loads(candidate.read_text(encoding="utf-8"))
    return json.loads(value)


def decode_clip_job_payload(value: Mapping[str, Any] | str) -> Dict[str, Any]:
    """Decode direct JSON or Pub/Sub push wrapper into a clip job payload."""
    raw: Mapping[str, Any]
    if isinstance(value, str):
        raw = _load_json_arg(value)
    else:
        raw = value

    if isinstance(raw.get("message"), Mapping):
        message = raw["message"]
        encoded = _as_str(message.get("data"))
        if not encoded:
            raise ValueError("Pub/Sub wrapper is missing message.data")
        decoded = base64.b64decode(encoded).decode("utf-8")
        raw = json.loads(decoded)

    payload = dict(raw)
    if payload.get("schemaVersion") != CLIP_SCHEMA_VERSION:
        raise ValueError(f"Unsupported schemaVersion: {payload.get('schemaVersion')}")
    if payload.get("jobType") != CLIP_JOB_TYPE:
        raise ValueError(f"Unsupported jobType: {payload.get('jobType')}")
    uid = _as_str(payload.get("uid"))
    if not uid:
        raise ValueError("clip job payload requires uid")
    return payload


def select_private_clip_sources(
    private_media_doc: Mapping[str, Any],
    *,
    requested_source_photo_ids: Optional[Iterable[str]] = None,
    allowed_buckets: Optional[set[str]] = None,
) -> Tuple[List[str], List[str]]:
    """Return (sourcePhotoIds, private GCS URIs) eligible for CLIP."""
    consent = private_media_doc.get("photoConsent")
    if not isinstance(consent, Mapping):
        raise ValueError("photoConsent is required")
    if consent.get("clipRecommendation") is not True:
        raise ValueError("clipRecommendation consent is not enabled")
    if consent.get("profileDisplayOriginalPhoto") is not False:
        raise ValueError("profileDisplayOriginalPhoto must be false")

    requested = {
        _as_str(photo_id)
        for photo_id in (requested_source_photo_ids or [])
        if _as_str(photo_id)
    }
    allowed_buckets = _parse_allowed_buckets() if allowed_buckets is None else allowed_buckets

    selected_ids: List[str] = []
    selected_refs: List[str] = []
    source_photos = private_media_doc.get("sourcePhotos")
    if not isinstance(source_photos, list):
        raise ValueError("sourcePhotos must be a list")

    for entry in source_photos:
        if not isinstance(entry, Mapping):
            continue
        if entry.get("status") != "active":
            continue
        purpose = entry.get("purpose")
        if not isinstance(purpose, Mapping) or purpose.get("clipRecommendation") is not True:
            continue
        photo_id = _as_str(entry.get("photoId"))
        if requested and photo_id not in requested:
            continue
        gcs_uri = _as_str(entry.get("gcsUri"))
        if not gcs_uri.startswith(("gs://", "gcs://")):
            continue
        bucket = _gcs_bucket(gcs_uri)
        if allowed_buckets is not None and bucket not in allowed_buckets:
            raise ValueError(f"source photo bucket is not allowed: {bucket}")
        selected_ids.append(photo_id)
        selected_refs.append(gcs_uri)

    if not selected_refs:
        raise ValueError("no active consented private GCS source photos found")
    return selected_ids, selected_refs


def build_clip_embedding_document(
    *,
    vector: Sequence[float],
    dims: int,
    source_photo_ids: Sequence[str],
    embedding_version: str = DEFAULT_EMBEDDING_VERSION,
    model_id: str = DEFAULT_MODEL_ID,
    updated_at: Any = None,
) -> Dict[str, Any]:
    doc = {
        "vector": [float(x) for x in vector],
        "modelId": model_id,
        "embeddingVersion": embedding_version,
        "sourcePhotoIds": list(source_photo_ids),
        "normalized": True,
        "dims": int(dims),
    }
    if updated_at is not None:
        doc["updatedAt"] = updated_at
    return doc


def _require_firestore() -> None:
    if firestore is None:
        raise RuntimeError("google-cloud-firestore is not installed.")


def _load_private_media_doc(
    *,
    db: Any,
    collection: str,
    uid: str,
) -> Dict[str, Any]:
    snap = db.collection(collection).document(uid).get()
    if not snap.exists:
        raise ValueError(f"userPrivateMedia document not found for uid={uid}")
    return snap.to_dict() or {}


def _write_failure_status(
    *,
    db: Any,
    collection: str,
    uid: str,
    embedding_version: str,
) -> None:
    db.collection(collection).document(uid).set(
        {
            "clip": {
                "embeddingStatus": "failed",
                "embeddingVersion": embedding_version,
                "updatedAt": firestore.SERVER_TIMESTAMP,
            }
        },
        merge=True,
    )


def process_clip_job_payload(
    payload: Mapping[str, Any],
    *,
    firestore_project: str,
    firestore_database: Optional[str] = None,
    private_media_collection: str = "userPrivateMedia",
    clip_embeddings_collection: str = "clipEmbeddings",
    device: str = "auto",
    dry_run: bool = False,
    embedder: Optional[Any] = None,
) -> Dict[str, Any]:
    """Process one CLIP job payload and return a redacted summary."""
    _require_firestore()
    job = decode_clip_job_payload(payload)
    uid = _as_str(job["uid"])
    embedding_version = _as_str(job.get("embeddingVersion")) or DEFAULT_EMBEDDING_VERSION
    requested_ids = _as_str_list(job.get("sourcePhotoIds"))

    db = firestore.Client(project=firestore_project, database=firestore_database)
    try:
        private_doc = _load_private_media_doc(
            db=db,
            collection=private_media_collection,
            uid=uid,
        )
        source_photo_ids, source_refs = select_private_clip_sources(
            private_doc,
            requested_source_photo_ids=requested_ids,
        )

        if dry_run:
            return {
                "uid": uid,
                "status": "dry_run",
                "sourcePhotoIds": source_photo_ids,
                "sourcePhotoRefs": [redact_private_image_ref(ref) for ref in source_refs],
            }

        embedder = embedder or SeolleyeonCLIPEmbedder(device=device)
        vector, dims = embedder.embed_profile_mean(source_refs[:3], normalize=True)
        embedding_doc = build_clip_embedding_document(
            vector=vector,
            dims=dims,
            source_photo_ids=source_photo_ids,
            embedding_version=embedding_version,
            model_id=getattr(embedder, "model_id", DEFAULT_MODEL_ID),
            updated_at=firestore.SERVER_TIMESTAMP,
        )

        db.collection(clip_embeddings_collection).document(uid).set(embedding_doc, merge=True)
        db.collection(private_media_collection).document(uid).set(
            {
                "clip": {
                    "embeddingStatus": "ready",
                    "embeddingVersion": embedding_version,
                    "lastEmbeddedAt": firestore.SERVER_TIMESTAMP,
                    "sourcePhotoIds": source_photo_ids,
                    "updatedAt": firestore.SERVER_TIMESTAMP,
                }
            },
            merge=True,
        )
        return {
            "uid": uid,
            "status": "ready",
            "dims": dims,
            "sourcePhotoIds": source_photo_ids,
            "clipEmbeddingsCollection": clip_embeddings_collection,
        }
    except Exception:
        if not dry_run:
            _write_failure_status(
                db=db,
                collection=private_media_collection,
                uid=uid,
                embedding_version=embedding_version,
            )
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Process a Seolleyeon CLIP embedding job.")
    parser.add_argument("--firestore_project", required=True)
    parser.add_argument("--firestore_database", default=None)
    parser.add_argument("--private_media_collection", default="userPrivateMedia")
    parser.add_argument("--clip_embeddings_collection", default="clipEmbeddings")
    parser.add_argument("--payload_json", default=None, help="JSON payload string or JSON file path.")
    parser.add_argument("--uid", default=None, help="Build a local clip_job_v1 payload for this uid.")
    parser.add_argument("--source_photo_id", action="append", default=[])
    parser.add_argument("--embedding_version", default=DEFAULT_EMBEDDING_VERSION)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--dry_run", action="store_true")
    parser.add_argument("--skip_clip_if_no_torch", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.payload_json:
        payload = decode_clip_job_payload(args.payload_json)
    elif args.uid:
        payload = {
            "uid": args.uid,
            "sourcePhotoIds": list(args.source_photo_id),
            "sourcePhotoRefs": [],
            "embeddingVersion": args.embedding_version,
            "jobType": CLIP_JOB_TYPE,
            "schemaVersion": CLIP_SCHEMA_VERSION,
            "idempotencyKey": f"{args.uid}:{','.join(args.source_photo_id)}:clip_embedding_v1",
        }
    else:
        raise SystemExit("--payload_json or --uid is required")

    try:
        result = process_clip_job_payload(
            payload,
            firestore_project=args.firestore_project,
            firestore_database=args.firestore_database,
            private_media_collection=args.private_media_collection,
            clip_embeddings_collection=args.clip_embeddings_collection,
            device=args.device,
            dry_run=args.dry_run,
        )
    except Exception as exc:
        if args.skip_clip_if_no_torch:
            print(json.dumps({"status": "skipped", "error": redact_private_image_ref(str(exc))}))
            return 0
        print(json.dumps({"status": "failed", "error": redact_private_image_ref(str(exc))}))
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
