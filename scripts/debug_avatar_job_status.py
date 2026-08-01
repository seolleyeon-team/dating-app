#!/usr/bin/env python3
"""Inspect avatar generation job state without exposing private media refs."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence


PRIVATE_MARKERS = (
    "seolleyeon-private-source-photos",
    "seolleyeon-final-private-source-photos",
    "seolleyeon-avatar-temp",
    "seolleyeon-final-avatar-temp",
)
SIGNED_MARKER_RE = re.compile(
    r"(?i)(X-Goog-[^=&\s]+|GoogleAccessId|Signature|Expires|X-Amz-[^=&\s]+)=([^&\s]+)"
)
GCS_RE = re.compile(r"g(?:s|cs)://[^\s\"']+")


def redact_text(value: Any) -> str:
    text = str(value or "")
    text = GCS_RE.sub("<private-ref-redacted>", text)
    text = SIGNED_MARKER_RE.sub(r"\1=<redacted>", text)
    for marker in PRIVATE_MARKERS:
        text = re.sub(re.escape(marker), "<private-bucket-redacted>", text, flags=re.IGNORECASE)
    return text[:240]


def redact_identifier(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) <= 6:
        return "<redacted>"
    return f"{text[:3]}***{text[-2:]}"


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _status(value: Any) -> str:
    return str(value or "unknown").strip().lower() or "unknown"


def _timestamp_text(value: Any) -> str:
    parsed = parse_timestamp(value)
    return parsed.isoformat() if parsed else ""


def parse_timestamp(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    if isinstance(value, Mapping):
        seconds = value.get("seconds") or value.get("_seconds")
        nanos = value.get("nanos") or value.get("_nanoseconds") or 0
        if seconds is None:
            return None
        return datetime.fromtimestamp(float(seconds) + float(nanos) / 1_000_000_000, tz=timezone.utc)
    if hasattr(value, "timestamp"):
        try:
            return datetime.fromtimestamp(float(value.timestamp()), tz=timezone.utc)
        except Exception:
            return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _candidate_status_counts(candidates: Mapping[str, Any], *, job_id: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for candidate in candidates.values():
        data = _as_mapping(candidate)
        if str(data.get("jobId") or "") != job_id:
            continue
        status = _status(data.get("status"))
        counts[status] = counts.get(status, 0) + 1
    return dict(sorted(counts.items()))


def _candidate_qa_summary(candidates: Mapping[str, Any], *, job_id: str) -> dict[str, Any]:
    reject_reasons: dict[str, int] = {}
    preview_allowed = 0
    expired = 0
    now = datetime.now(timezone.utc)
    total = 0
    for candidate in candidates.values():
        data = _as_mapping(candidate)
        if str(data.get("jobId") or "") != job_id:
            continue
        total += 1
        qa = _as_mapping(data.get("qa"))
        if qa.get("previewAllowed") is True:
            preview_allowed += 1
        expires_at = parse_timestamp(data.get("expiresAt"))
        if expires_at is not None and expires_at <= now:
            expired += 1
        for reason in _as_list(qa.get("rejectReasons")):
            key = str(reason or "").strip() or "unknown"
            reject_reasons[key] = reject_reasons.get(key, 0) + 1
    return {
        "candidateCount": total,
        "previewAllowedCount": preview_allowed,
        "expiredCandidateCount": expired,
        "rejectReasons": dict(sorted(reject_reasons.items())),
    }


def summarize_job(job_id: str, job: Mapping[str, Any], candidates: Mapping[str, Any]) -> dict[str, Any]:
    processing = _as_mapping(job.get("processing"))
    return {
        "jobId": job_id,
        "uid": redact_identifier(job.get("uid")),
        "status": _status(job.get("status")),
        "queueMode": str(job.get("queueMode") or ""),
        "queueStatus": str(job.get("queueStatus") or ""),
        "candidateCount": int(job.get("candidateCount") or 0),
        "errorCode": redact_text(job.get("errorCode")),
        "errorMessage": redact_text(job.get("errorMessage")),
        "createdAt": _timestamp_text(job.get("createdAt")),
        "updatedAt": _timestamp_text(job.get("updatedAt")),
        "queuedAt": _timestamp_text(job.get("queuedAt")),
        "sourcePhotoIdsCount": len(_as_list(job.get("sourcePhotoIds"))),
        "sourcePhotoRefsCount": len(_as_list(job.get("sourcePhotoRefs"))),
        "processing": {
            "attempt": int(processing.get("attempt") or 0),
            "leaseOwner": redact_text(processing.get("leaseOwner")),
            "leaseExpiresAt": _timestamp_text(processing.get("leaseExpiresAt")),
            "lastErrorCode": redact_text(processing.get("lastErrorCode")),
            "lastErrorMessage": redact_text(processing.get("lastErrorMessage")),
        },
        "candidatesByStatus": _candidate_status_counts(candidates, job_id=job_id),
        "candidateQa": _candidate_qa_summary(candidates, job_id=job_id),
    }


def summarize_private_media(private_doc: Mapping[str, Any]) -> dict[str, Any]:
    clip = _as_mapping(private_doc.get("clip"))
    photo_consent = _as_mapping(private_doc.get("photoConsent"))
    chat_real_photo = _as_mapping(private_doc.get("chatRealPhoto"))
    return {
        "exists": bool(private_doc),
        "sourcePhotosCount": len(_as_list(private_doc.get("sourcePhotos"))),
        "activeSourcePhotoCount": sum(
            1
            for item in _as_list(private_doc.get("sourcePhotos"))
            if _as_mapping(item).get("status") not in {"deleted", "inactive"}
        ),
        "clipEmbeddingStatus": str(clip.get("embeddingStatus") or ""),
        "chatPartnerRealPhotoDisclosure": bool(
            photo_consent.get("chatPartnerRealPhotoDisclosure")
        ),
        "chatRealPhotoEnabled": bool(chat_real_photo.get("enabled")),
    }


def summarize_user_doc(user_doc: Mapping[str, Any]) -> dict[str, Any]:
    avatar = _as_mapping(user_doc.get("avatar"))
    onboarding = _as_mapping(user_doc.get("onboarding"))
    return {
        "exists": bool(user_doc),
        "avatarStatus": _status(avatar.get("status")) if avatar else "",
        "avatarIdPresent": bool(str(avatar.get("avatarId") or "").strip()),
        "approvedAvatarUrlPresent": bool(
            str(avatar.get("approvedAvatarUrl") or "").strip()
        ),
        "selectedCandidateId": redact_identifier(avatar.get("selectedCandidateId")),
        "sourceJobId": str(avatar.get("sourceJobId") or ""),
        "onboardingAvatarUrlsCount": len(_as_list(onboarding.get("avatarUrls"))),
        "onboardingPhotoUrlsCount": len(_as_list(onboarding.get("photoUrls"))),
    }


def _filter_recent_jobs(
    jobs: Mapping[str, Any],
    *,
    uid: str,
    job_id: Optional[str],
    recent_minutes: int,
) -> dict[str, Mapping[str, Any]]:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=recent_minutes) if recent_minutes > 0 else None
    selected: dict[str, Mapping[str, Any]] = {}
    for key, raw in jobs.items():
        data = _as_mapping(raw)
        if job_id and key != job_id:
            continue
        if uid and str(data.get("uid") or "") != uid:
            continue
        if cutoff is not None:
            stamp = parse_timestamp(data.get("createdAt")) or parse_timestamp(data.get("updatedAt"))
            if stamp is not None and stamp < cutoff:
                continue
        selected[str(key)] = data
    return selected


def build_diagnostic_report(
    fixture: Mapping[str, Any],
    *,
    uid: str,
    job_id: Optional[str] = None,
    recent_minutes: int = 60,
) -> dict[str, Any]:
    jobs = _as_mapping(fixture.get("avatarJobs"))
    candidates = _as_mapping(fixture.get("avatarCandidates"))
    private_media = _as_mapping(fixture.get("userPrivateMedia"))
    users = _as_mapping(fixture.get("users"))
    selected_jobs = _filter_recent_jobs(
        jobs,
        uid=uid,
        job_id=job_id,
        recent_minutes=recent_minutes,
    )
    return {
        "uid": redact_identifier(uid),
        "jobId": job_id or "",
        "recentMinutes": recent_minutes,
        "jobCount": len(selected_jobs),
        "jobs": [
            summarize_job(key, selected_jobs[key], candidates)
            for key in sorted(selected_jobs)
        ],
        "userPrivateMedia": summarize_private_media(
            _as_mapping(private_media.get(uid))
        ),
        "userDocument": summarize_user_doc(_as_mapping(users.get(uid))),
        "privacy": {
            "privateRefsEmitted": False,
            "signedUrlsEmitted": False,
        },
    }


def _snapshot_to_dict(snapshot: Any) -> tuple[str, Mapping[str, Any]]:
    data = snapshot.to_dict() if hasattr(snapshot, "to_dict") else {}
    if not isinstance(data, Mapping):
        data = {}
    return str(getattr(snapshot, "id", "")), data


def _firestore_fixture(project: str, database: str, uid: str, job_id: Optional[str], limit: int) -> dict[str, Any]:
    try:
        from google.cloud import firestore
        from google.cloud.firestore_v1.base_query import FieldFilter
    except Exception as exc:  # pragma: no cover - depends on local install
        raise RuntimeError("google-cloud-firestore is required for live diagnostics.") from exc

    kwargs: dict[str, Any] = {"project": project}
    if database:
        kwargs["database"] = database
    client = firestore.Client(**kwargs)

    jobs: dict[str, Any] = {}
    if job_id:
        snapshot = client.collection("avatarJobs").document(job_id).get()
        if snapshot.exists:
            key, data = _snapshot_to_dict(snapshot)
            jobs[key] = data
    else:
        query = client.collection("avatarJobs").where(
            filter=FieldFilter("uid", "==", uid)
        ).limit(limit)
        for snapshot in query.stream():
            key, data = _snapshot_to_dict(snapshot)
            jobs[key] = data

    candidates: dict[str, Any] = {}
    for key in list(jobs):
        query = client.collection("avatarCandidates").where(
            filter=FieldFilter("jobId", "==", key)
        ).limit(50)
        for snapshot in query.stream():
            candidate_id, data = _snapshot_to_dict(snapshot)
            candidates[candidate_id] = data

    private_doc = client.collection("userPrivateMedia").document(uid).get()
    private_media = {}
    if private_doc.exists:
        _, data = _snapshot_to_dict(private_doc)
        private_media[uid] = data

    user_doc = client.collection("users").document(uid).get()
    users = {}
    if user_doc.exists:
        _, data = _snapshot_to_dict(user_doc)
        users[uid] = data

    return {
        "avatarJobs": jobs,
        "avatarCandidates": candidates,
        "userPrivateMedia": private_media,
        "users": users,
    }


def _load_fixture(path: str) -> Mapping[str, Any]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError("fixture JSON must contain an object.")
    return raw


def _write_report(report: Mapping[str, Any], path: Optional[str]) -> None:
    encoded = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if path:
        Path(path).write_text(encoded + "\n", encoding="utf-8")
    print(encoded)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Debug avatarJobs/avatarCandidates state without exposing private refs."
    )
    parser.add_argument("--project", default="seolleyeon-final")
    parser.add_argument("--database", default="(default)")
    parser.add_argument("--uid", required=True)
    parser.add_argument("--job_id")
    parser.add_argument("--recent_minutes", type=int, default=60)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--redact", action="store_true", help="Accepted for clarity; output is always redacted.")
    parser.add_argument("--fixture_json")
    parser.add_argument("--output_report_json")
    args = parser.parse_args(argv)

    fixture = (
        _load_fixture(args.fixture_json)
        if args.fixture_json
        else _firestore_fixture(args.project, args.database, args.uid, args.job_id, args.limit)
    )
    report = build_diagnostic_report(
        fixture,
        uid=args.uid,
        job_id=args.job_id,
        recent_minutes=args.recent_minutes,
    )
    _write_report(report, args.output_report_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
