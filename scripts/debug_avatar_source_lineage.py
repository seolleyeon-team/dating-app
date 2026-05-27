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


def _datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if hasattr(value, "to_datetime"):
        try:
            parsed = value.to_datetime()
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except Exception:
            return None
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(raw)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def _timestamp(value: Any) -> str:
    parsed = _datetime(value)
    if parsed is not None:
        return parsed.isoformat()
    return str(value)


def _safe_source_photo(entry: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "photoIdHash": _hash_text(entry.get("photoId")),
        "sha256Prefix": str(entry.get("sha256") or "")[:12],
        "storagePathHash": _hash_text(entry.get("storagePath")),
        "gcsUriHash": _hash_text(entry.get("gcsUri")),
        "status": str(entry.get("status") or ""),
        "avatarGenerationState": str(entry.get("avatarGenerationState") or ""),
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
        "sourceSelectionVersion": data.get("avatarSourceSelectionVersion"),
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
    current_source_id = str(private_data.get("currentAvatarSourcePhotoId") or "")
    current_job_id = str(private_data.get("currentAvatarJobId") or "")
    current_source_ref_hash = ""
    state_counts: dict[str, int] = {}
    if isinstance(source_photos, list):
        for entry in source_photos:
            if not isinstance(entry, Mapping):
                continue
            state = str(entry.get("avatarGenerationState") or "missing")
            state_counts[state] = state_counts.get(state, 0) + 1
            if str(entry.get("photoId") or "") == current_source_id:
                current_source_ref_hash = _hash_text(entry.get("gcsUri"))

    jobs: list[dict[str, Any]] = []
    if job_id:
        snap = db.collection("avatarJobs").document(job_id).get()
        if snap.exists:
            jobs.append(_safe_job(snap.id, snap.to_dict() or {}))
    else:
        cutoff = datetime.now(tz=timezone.utc) - timedelta(minutes=max(1, recent_minutes))
        query = db.collection("avatarJobs").where("uid", "==", uid).limit(50)
        for snap in query.stream():
            data = snap.to_dict() or {}
            created_at = _datetime(data.get("createdAt"))
            updated_at = _datetime(data.get("updatedAt"))
            if (
                created_at is not None
                and created_at < cutoff
                and (updated_at is None or updated_at < cutoff)
            ):
                continue
            jobs.append(_safe_job(snap.id, data))

    shared_ref_hashes: dict[str, int] = {}
    mismatches: list[dict[str, Any]] = []
    if not current_job_id or not current_source_id:
        mismatches.append({
            "reason": "missing_current_avatar_contract",
            "currentJobPresent": bool(current_job_id),
            "currentSourcePresent": bool(current_source_id),
        })
    for job in jobs:
        for ref_hash in job.get("sourceRefHashes", []):
            if ref_hash:
                shared_ref_hashes[ref_hash] = shared_ref_hashes.get(ref_hash, 0) + 1
        job_is_current = job.get("jobIdHash") == _hash_text(current_job_id)
        job_source_hashes = job.get("sourcePhotoIdHashes", [])
        job_source_is_current = (
            isinstance(job_source_hashes, list)
            and _hash_text(current_source_id) in job_source_hashes
        )
        if job_is_current != job_source_is_current:
            mismatches.append({
                "jobIdHash": job.get("jobIdHash"),
                "jobIsCurrent": job_is_current,
                "jobSourceIsCurrent": job_source_is_current,
            })

    return {
        "project": project,
        "uidHash": _hash_text(uid),
        "jobIdHash": _hash_text(job_id or ""),
        "recentMinutes": recent_minutes,
        "currentAvatarSourcePhotoIdHash": _hash_text(current_source_id),
        "currentAvatarJobIdHash": _hash_text(current_job_id),
        "avatarSourceSelectionVersion": private_data.get("avatarSourceSelectionVersion"),
        "currentSourceRefHash": current_source_ref_hash,
        "sourcePhotoCount": len(safe_sources),
        "sourcePhotosByAvatarGenerationState": dict(sorted(state_counts.items())),
        "sourcePhotos": safe_sources,
        "avatarJobs": jobs,
        "sourceRefHashCountsInReport": shared_ref_hashes,
        "currentContractMismatches": mismatches,
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
