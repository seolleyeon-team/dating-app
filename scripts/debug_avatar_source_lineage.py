from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping


def _hash_text(value: Any, *, length: int = 12) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:length]


def _timestamp(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "to_datetime"):
        try:
            return value.to_datetime().isoformat()
        except Exception:
            return str(value)
    return str(value)


def _safe_source_photo(entry: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "photoIdHash": _hash_text(entry.get("photoId")),
        "sha256Prefix": str(entry.get("sha256") or "")[:12],
        "storagePathHash": _hash_text(entry.get("storagePath")),
        "gcsUriHash": _hash_text(entry.get("gcsUri")),
        "status": str(entry.get("status") or ""),
        "updatedAt": _timestamp(entry.get("updatedAt")),
    }


def _safe_job(doc_id: str, data: Mapping[str, Any]) -> dict[str, Any]:
    refs = data.get("sourcePhotoRefs")
    ids = data.get("sourcePhotoIds")
    return {
        "jobIdHash": _hash_text(data.get("jobId") or doc_id),
        "status": str(data.get("status") or ""),
        "uidHash": _hash_text(data.get("uid")),
        "sourcePhotoIdHashes": [_hash_text(value) for value in ids] if isinstance(ids, list) else [],
        "sourceRefHashes": [_hash_text(value) for value in refs] if isinstance(refs, list) else [],
        "queueStatus": str(data.get("queueStatus") or ""),
        "queueMode": str(data.get("queueMode") or ""),
        "createdAt": _timestamp(data.get("createdAt")),
        "updatedAt": _timestamp(data.get("updatedAt")),
        "errorCode": str(data.get("errorCode") or ""),
    }


def _client(project: str):
    try:
        from google.cloud import firestore
    except Exception as exc:  # pragma: no cover - environment dependent
        raise RuntimeError("google-cloud-firestore is required") from exc
    return firestore.Client(project=project)


def build_report(
    *,
    project: str,
    uid: str,
    job_id: str | None,
    recent_minutes: int,
) -> dict[str, Any]:
    db = _client(project)
    private_doc = db.collection("userPrivateMedia").document(uid).get()
    private_data = private_doc.to_dict() or {}
    source_photos = private_data.get("sourcePhotos")
    safe_sources = [
        _safe_source_photo(entry)
        for entry in source_photos
        if isinstance(entry, Mapping)
    ] if isinstance(source_photos, list) else []

    jobs: list[dict[str, Any]] = []
    if job_id:
        snap = db.collection("avatarJobs").document(job_id).get()
        if snap.exists:
            jobs.append(_safe_job(snap.id, snap.to_dict() or {}))
    else:
        cutoff = datetime.now(tz=timezone.utc) - timedelta(minutes=max(1, recent_minutes))
        query = (
            db.collection("avatarJobs")
            .where("uid", "==", uid)
            .where("createdAt", ">=", cutoff)
            .limit(20)
        )
        for snap in query.stream():
            jobs.append(_safe_job(snap.id, snap.to_dict() or {}))

    shared_ref_hashes: dict[str, int] = {}
    for job in jobs:
        for ref_hash in job.get("sourceRefHashes", []):
            if ref_hash:
                shared_ref_hashes[ref_hash] = shared_ref_hashes.get(ref_hash, 0) + 1

    return {
        "project": project,
        "uidHash": _hash_text(uid),
        "jobIdHash": _hash_text(job_id or ""),
        "recentMinutes": recent_minutes,
        "sourcePhotoCount": len(safe_sources),
        "sourcePhotos": safe_sources,
        "avatarJobs": jobs,
        "sourceRefHashCountsInReport": shared_ref_hashes,
        "redacted": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only, redacted avatar source lineage diagnostic."
    )
    parser.add_argument("--project", default="seolleyeon-final")
    parser.add_argument("--uid", required=True)
    parser.add_argument("--job_id")
    parser.add_argument("--recent_minutes", type=int, default=120)
    parser.add_argument("--redact", action="store_true", default=True)
    args = parser.parse_args(argv)

    report = build_report(
        project=args.project,
        uid=args.uid,
        job_id=args.job_id,
        recent_minutes=args.recent_minutes,
    )
    json.dump(report, sys.stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
