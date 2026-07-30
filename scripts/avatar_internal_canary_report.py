from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Iterable, Mapping, Sequence


TIMING_FIELDS = (
    "modelLoadSeconds",
    "faceDetectSeconds",
    "traitExtractSeconds",
    "preprocessSeconds",
    "generationSeconds",
    "qaSeconds",
    "rerankSeconds",
    "uploadSeconds",
    "totalWorkerSeconds",
)

TRAIT_COMPLETENESS_PATHS = (
    ("hair", "bangs"),
    ("facialHair", "present"),
    ("facialHair", "broadStyle"),
    ("faceImpression", "facialFeatureBalance"),
    ("faceImpression", "eyeShapeMood"),
    ("faceImpression", "browShape"),
    ("faceImpression", "noseBridgeImpression"),
    ("faceImpression", "mouthFullnessCategory"),
)

TRAIT_COMPLETENESS_FLAT_KEYS = {
    ("hair", "bangs"): "hair_bangs",
    ("facialHair", "present"): "facial_hair_present",
    ("facialHair", "broadStyle"): "facial_hair_style",
    ("faceImpression", "facialFeatureBalance"): "facial_feature_balance",
    ("faceImpression", "eyeShapeMood"): "eye_shape_mood",
    ("faceImpression", "browShape"): "brow_shape",
    ("faceImpression", "noseBridgeImpression"): "nose_bridge_impression",
    ("faceImpression", "mouthFullnessCategory"): "mouth_fullness_category",
}

PRIVATE_OUTPUT_PATTERNS = (
    re.compile(r"gs://", re.IGNORECASE),
    re.compile(r"gcs://", re.IGNORECASE),
    re.compile(r"sourcePhotoRefs?", re.IGNORECASE),
    re.compile(r"sourcePhotoGcsUri", re.IGNORECASE),
    re.compile(r"\bgcsUri\b", re.IGNORECASE),
    re.compile(r"userPrivateMedia", re.IGNORECASE),
    re.compile(r"clipEmbeddings", re.IGNORECASE),
    re.compile(r"X-Goog-Signature", re.IGNORECASE),
    re.compile(r"X-Goog-Credential", re.IGNORECASE),
    re.compile(r"GoogleAccessId", re.IGNORECASE),
    re.compile(r"Signature=", re.IGNORECASE),
    re.compile(r"signedUrl", re.IGNORECASE),
    re.compile(r"seolleyeon(?:-final)?-private-source-photos", re.IGNORECASE),
    re.compile(r"seolleyeon(?:-final)?-avatar-temp", re.IGNORECASE),
)

RAW_ANALYSIS_KEYS = {
    "rawLandmarks",
    "raw_landmarks",
    "faceLandmarks",
    "face_landmarks",
    "landmarks",
    "blendshapes",
    "rawBlendshapes",
    "rawEmbeddings",
    "embeddings",
}


def _hash_text(value: Any, *, length: int = 12) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:length]


def _safe_id(value: Any, prefix: str, *, redact: bool) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if redact:
        return f"{prefix}:{_hash_text(text)}"
    return _redact_sensitive_text(text)


def _redact_sensitive_text(value: Any) -> str:
    text = str(value or "")
    if not text:
        return ""
    text = re.sub(r"g(?:s|cs)://[^\s\"']+", "[redacted-storage-ref]", text, flags=re.I)
    text = re.sub(r"https?://[^\s\"']*(?:X-Goog-|Signature=|GoogleAccessId)[^\s\"']*", "[redacted-signed-url]", text, flags=re.I)
    text = re.sub(r"seolleyeon(?:-final)?-(?:private-source-photos|avatar-temp)[^\s\"']*", "[redacted-private-bucket]", text, flags=re.I)
    return text[:240]


def _as_map(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _get_path(data: Mapping[str, Any], path: Sequence[str], default: Any = None) -> Any:
    current: Any = data
    for key in path:
        if not isinstance(current, Mapping) or key not in current:
            return default
        current = current[key]
    return current


def _timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if hasattr(value, "to_datetime"):
        try:
            dt = value.to_datetime()
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except Exception:
            return None
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(raw)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def _parse_since(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = _timestamp(value)
    if parsed is None:
        raise ValueError(f"Invalid --since ISO timestamp: {value}")
    return parsed


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _contains_reason(candidate: Mapping[str, Any], fragments: Iterable[str]) -> bool:
    haystacks: list[str] = []
    qa = _as_map(candidate.get("qa"))
    rerank = _as_map(candidate.get("rerank"))
    debug = _as_map(qa.get("debug"))
    decision = _as_map(debug.get("decision"))
    for value in (
        qa.get("rejectReasons"),
        qa.get("reviewReasons"),
        qa.get("needsReviewReasons"),
        qa.get("softPassReasons"),
        rerank.get("rejectReasons"),
        rerank.get("reviewReasons"),
        decision.get("hardRejectReasons"),
        decision.get("needsReviewReasons"),
        candidate.get("rejectReasons"),
        candidate.get("reviewReasons"),
    ):
        haystacks.extend(str(item) for item in _as_list(value))
    text = " ".join(haystacks).lower()
    return any(fragment in text for fragment in fragments)


def _selection_tier(candidate: Mapping[str, Any]) -> str:
    qa = _as_map(candidate.get("qa"))
    rerank = _as_map(candidate.get("rerank"))
    debug = _as_map(qa.get("debug"))
    decision = _as_map(debug.get("decision"))
    for value in (
        rerank.get("selectionTier"),
        qa.get("selectionTier"),
        decision.get("selectionTier"),
        candidate.get("selectionTier"),
    ):
        if value:
            return str(value)
    status = str(candidate.get("status") or "")
    if status in {"rejected", "hard_reject"}:
        return "hard_reject"
    if status == "needs_review":
        return "needs_review"
    return ""


def _selected_for_preview(candidate: Mapping[str, Any]) -> bool:
    qa = _as_map(candidate.get("qa"))
    rerank = _as_map(candidate.get("rerank"))
    if rerank.get("selectedForPreview") is True:
        return True
    if qa.get("previewAllowed") is True:
        return True
    return str(candidate.get("status") or "") in {"preview_ready", "preview"}


def _source_entries(private_doc: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    source_photos = private_doc.get("sourcePhotos")
    if isinstance(source_photos, list):
        return [entry for entry in source_photos if isinstance(entry, Mapping)]
    source_map = private_doc.get("sourcePhotoMap")
    if isinstance(source_map, Mapping):
        return [entry for entry in source_map.values() if isinstance(entry, Mapping)]
    return []


def _matching_source_entry(
    private_doc: Mapping[str, Any],
    source_photo_ids: Sequence[Any],
) -> Mapping[str, Any]:
    ids = {str(value) for value in source_photo_ids if str(value).strip()}
    for entry in _source_entries(private_doc):
        if str(entry.get("photoId") or "") in ids:
            return entry
    entries = _source_entries(private_doc)
    return entries[-1] if entries else {}


def _source_ref_hashes(job: Mapping[str, Any], source_entry: Mapping[str, Any]) -> list[str]:
    refs: list[Any] = []
    for key in ("sourceRefHash", "sourceRefHashes"):
        value = job.get(key)
        if isinstance(value, list):
            refs.extend(value)
        elif value:
            refs.append(value)
    for key in ("sourcePhotoRefs", "sourcePhotoRef", "gcsUri", "storagePath"):
        value = job.get(key)
        if isinstance(value, list):
            refs.extend(value)
        elif value:
            refs.append(value)
    for key in ("gcsUri", "storagePath"):
        if source_entry.get(key):
            refs.append(source_entry.get(key))
    return sorted({_hash_text(ref) for ref in refs if str(ref).strip()})


def _source_analysis_summary(job: Mapping[str, Any]) -> dict[str, Any]:
    source = _as_map(job.get("sourceAnalysis"))
    model_availability = _as_map(source.get("modelAvailability"))
    return {
        "modelAvailability": {
            "mediapipe": str(model_availability.get("mediapipe") or ""),
            "faceDetector": str(model_availability.get("faceDetector") or ""),
        },
        "faceVisible": source.get("faceVisible"),
        "singlePerson": source.get("singlePerson"),
        "faceCount": source.get("faceCount"),
        "visibleCrop": str(source.get("visibleCrop") or ""),
        "occlusionLevel": str(source.get("occlusionLevel") or ""),
        "lighting": str(source.get("lighting") or ""),
        "usableForAvatar": source.get("usableForAvatar"),
        "rejectReasons": [
            _redact_sensitive_text(item) for item in _as_list(source.get("rejectReasons"))
        ],
        "broadTraitHintsPresent": bool(source.get("broadTraitHints")),
    }


def _trait_card_summary(job: Mapping[str, Any]) -> dict[str, Any]:
    trait_card = _as_map(job.get("traitCard"))
    if "traitCard" in trait_card and isinstance(trait_card.get("traitCard"), Mapping):
        trait_card = _as_map(trait_card.get("traitCard"))
    present_fields: list[str] = []
    unclear_fields: list[str] = []
    for path in TRAIT_COMPLETENESS_PATHS:
        value = _get_path(trait_card, path)
        if value is None:
            value = trait_card.get(TRAIT_COMPLETENESS_FLAT_KEYS.get(path, ""))
        name = ".".join(path)
        if value in (None, "", "unclear"):
            unclear_fields.append(name)
        else:
            present_fields.append(name)
    return {
        "traitCardPresent": bool(trait_card),
        "privacySafe": job.get("privacySafe")
        if job.get("privacySafe") is not None
        else trait_card.get("privacySafe"),
        "completeCount": len(present_fields),
        "totalFields": len(TRAIT_COMPLETENESS_PATHS),
        "presentFields": present_fields,
        "unclearFields": unclear_fields,
    }


def _timing_summary(job: Mapping[str, Any]) -> dict[str, float | None]:
    cost = _as_map(job.get("cost"))
    seconds_by_stage = _as_map(cost.get("secondsByStage"))
    processing = _as_map(job.get("processing"))
    result: dict[str, float | None] = {}
    aliases = {
        "modelLoadSeconds": ("model_load_seconds", "modelLoadSeconds"),
        "faceDetectSeconds": ("face_detect_seconds", "faceDetectSeconds"),
        "traitExtractSeconds": ("trait_extract_seconds", "traitExtractSeconds"),
        "preprocessSeconds": ("preprocess_seconds", "preprocessSeconds"),
        "generationSeconds": ("generation_seconds", "generationSeconds"),
        "qaSeconds": ("qa_seconds", "qaSeconds"),
        "rerankSeconds": ("rerank_seconds", "rerankSeconds"),
        "uploadSeconds": ("upload_seconds", "uploadSeconds"),
        "totalWorkerSeconds": ("total_worker_seconds", "totalWorkerSeconds"),
    }
    for output_key, candidates in aliases.items():
        value = cost.get(output_key)
        if value is None:
            for key in candidates:
                if seconds_by_stage.get(key) is not None:
                    value = seconds_by_stage.get(key)
                    break
        if value is None:
            for key in candidates:
                if processing.get(key) is not None:
                    value = processing.get(key)
                    break
        result[output_key] = _to_float(value)
    return result


def _estimated_usd(job: Mapping[str, Any]) -> float | None:
    cost = _as_map(job.get("cost"))
    for value in (
        cost.get("estimatedUsd"),
        job.get("costEstimateUsd"),
        job.get("estimatedUsd"),
    ):
        numeric = _to_float(value)
        if numeric is not None:
            return numeric
    return None


def _candidate_counts(candidates: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts = {
        "candidateCount": len(candidates),
        "previewCount": 0,
        "hardPassCount": 0,
        "softPassCount": 0,
        "needsReviewCount": 0,
        "hardRejectCount": 0,
        "tooIdentifiableCount": 0,
        "childlikeRiskCount": 0,
        "beautificationRiskCount": 0,
    }
    for candidate in candidates:
        tier = _selection_tier(candidate)
        if _selected_for_preview(candidate):
            counts["previewCount"] += 1
        if tier == "hard_pass":
            counts["hardPassCount"] += 1
        elif tier == "soft_pass":
            counts["softPassCount"] += 1
        elif tier == "needs_review":
            counts["needsReviewCount"] += 1
        elif tier == "hard_reject":
            counts["hardRejectCount"] += 1
        if _contains_reason(candidate, ("too_identifiable", "over_resemblance")):
            counts["tooIdentifiableCount"] += 1
        if _contains_reason(candidate, ("childlike", "teenager", "babyface", "chibi", "doll")):
            counts["childlikeRiskCount"] += 1
        if _contains_reason(candidate, ("beautification", "beauty", "handsome", "pretty", "attractive")):
            counts["beautificationRiskCount"] += 1
    return counts


def _preview_payload_summary(candidates: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    lengths: list[int] = []
    total: int | None = 0
    for candidate in candidates:
        length = candidate.get("previewImageBase64Length")
        if length is None:
            payload = candidate.get("previewImageBase64")
            length = len(payload) if isinstance(payload, str) else None
        if length is None:
            payload_bytes = candidate.get("previewPayloadBytes")
            length = payload_bytes if isinstance(payload_bytes, int) else None
        if length is None:
            total = None
            continue
        try:
            lengths.append(int(length))
        except (TypeError, ValueError):
            total = None
    if total is not None:
        total = sum(lengths)
    level = "unknown"
    if total is not None:
        if total > 20 * 1024 * 1024:
            level = "critical"
        elif total > 8 * 1024 * 1024:
            level = "warning"
        else:
            level = "ok"
    return {
        "previewPayloadBytes": total,
        "perCandidateBase64Bytes": lengths,
        "warningLevel": level,
    }


def _privacy_findings(*docs: Mapping[str, Any]) -> list[str]:
    findings: set[str] = set()

    def walk(value: Any, path: str = "") -> None:
        if isinstance(value, Mapping):
            for key, child in value.items():
                key_text = str(key)
                next_path = f"{path}.{key_text}" if path else key_text
                if key_text in RAW_ANALYSIS_KEYS:
                    findings.add(f"raw_analysis_key:{next_path}")
                walk(child, next_path)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{path}[{index}]")

    for doc in docs:
        walk(doc)
    return sorted(findings)


def _job_created_after(job: Mapping[str, Any], since: datetime | None) -> bool:
    if since is None:
        return True
    created_at = _timestamp(job.get("createdAt"))
    return created_at is None or created_at >= since


def _normalize_doc_map(value: Any) -> dict[str, Mapping[str, Any]]:
    if isinstance(value, Mapping):
        return {
            str(key): dict(doc)
            for key, doc in value.items()
            if isinstance(doc, Mapping)
        }
    if isinstance(value, list):
        result: dict[str, Mapping[str, Any]] = {}
        for index, doc in enumerate(value):
            if not isinstance(doc, Mapping):
                continue
            doc_id = str(doc.get("id") or doc.get("jobId") or doc.get("candidateId") or index)
            result[doc_id] = dict(doc)
        return result
    return {}


def build_report_from_documents(
    *,
    project: str,
    uids: Sequence[str],
    since: datetime | None,
    users: Mapping[str, Mapping[str, Any]],
    private_media: Mapping[str, Mapping[str, Any]],
    jobs: Mapping[str, Mapping[str, Any]],
    candidates: Mapping[str, Mapping[str, Any]],
    redact: bool = True,
) -> dict[str, Any]:
    uid_set = {str(uid) for uid in uids if str(uid).strip()}
    rows: list[dict[str, Any]] = []

    for uid in sorted(uid_set):
        user_doc = _as_map(users.get(uid))
        private_doc = _as_map(private_media.get(uid))
        user_jobs = [
            (job_id, job)
            for job_id, job in jobs.items()
            if str(job.get("uid") or "") == uid and _job_created_after(job, since)
        ]
        user_jobs.sort(key=lambda item: str(item[1].get("createdAt") or ""))

        if not user_jobs:
            rows.append(_empty_user_row(project, uid, user_doc, private_doc, redact=redact))
            continue

        for job_id, job in user_jobs:
            job_candidates = [
                candidate
                for candidate in candidates.values()
                if str(candidate.get("jobId") or "") == str(job.get("jobId") or job_id)
                or str(candidate.get("jobId") or "") == job_id
            ]
            source_ids = _as_list(job.get("sourcePhotoIds"))
            if not source_ids and job.get("sourcePhotoId"):
                source_ids = [job.get("sourcePhotoId")]
            source_entry = _matching_source_entry(private_doc, source_ids)
            counts = _candidate_counts(job_candidates)
            timing = _timing_summary(job)
            preview_payload = _preview_payload_summary(job_candidates)
            selected_candidate_id = (
                job.get("selectedCandidateId")
                or job.get("approvedCandidateId")
                or _get_path(user_doc, ("avatar", "approvedCandidateId"))
            )
            approved_url = _get_path(user_doc, ("avatar", "approvedAvatarUrl")) or job.get(
                "approvedAvatarUrl"
            )
            row = {
                "project": project,
                "uidHash": _hash_text(uid),
                "jobId": _safe_id(job.get("jobId") or job_id, "job", redact=redact),
                "status": str(job.get("status") or ""),
                "sourcePhotoId": _safe_id(
                    source_ids[0] if source_ids else source_entry.get("photoId"),
                    "photo",
                    redact=redact,
                ),
                "sourceHashPrefix": str(source_entry.get("sha256") or job.get("sourceSha256") or "")[:12],
                "sourceRefHash": _source_ref_hashes(job, source_entry),
                "sourceAnalysis": _source_analysis_summary(job),
                "traitCardCompleteness": _trait_card_summary(job),
                "candidateStats": counts,
                "selectedCandidateId": _safe_id(selected_candidate_id, "candidate", redact=redact),
                "approvalStatus": _approval_status(job, user_doc),
                "approvedAvatarUrlPresent": bool(approved_url),
                "lockRetestStatus": str(job.get("lockRetestStatus") or "not_run"),
                "timing": timing,
                "estimatedUsd": _estimated_usd(job),
                "previewPayload": preview_payload,
                "errors": _safe_errors(job),
                "privacyFindings": _privacy_findings(job, *job_candidates),
            }
            rows.append(row)

    summary = _summary(rows)
    return {
        "project": project,
        "since": since.isoformat() if since else "",
        "redacted": redact,
        "participantCount": len(uid_set),
        "jobCount": sum(1 for row in rows if row.get("jobId")),
        "summary": summary,
        "jobs": rows,
    }


def _empty_user_row(
    project: str,
    uid: str,
    user_doc: Mapping[str, Any],
    private_doc: Mapping[str, Any],
    *,
    redact: bool,
) -> dict[str, Any]:
    approved_url = _get_path(user_doc, ("avatar", "approvedAvatarUrl"))
    source_entry = _matching_source_entry(private_doc, [])
    return {
        "project": project,
        "uidHash": _hash_text(uid),
        "jobId": "",
        "status": "no_job_in_window",
        "sourcePhotoId": _safe_id(source_entry.get("photoId"), "photo", redact=redact),
        "sourceHashPrefix": str(source_entry.get("sha256") or "")[:12],
        "sourceRefHash": _source_ref_hashes({}, source_entry),
        "sourceAnalysis": {},
        "traitCardCompleteness": {},
        "candidateStats": _candidate_counts([]),
        "selectedCandidateId": "",
        "approvalStatus": "approved" if approved_url else "not_approved",
        "approvedAvatarUrlPresent": bool(approved_url),
        "lockRetestStatus": "not_run",
        "timing": {field: None for field in TIMING_FIELDS},
        "estimatedUsd": None,
        "previewPayload": {
            "previewPayloadBytes": None,
            "perCandidateBase64Bytes": [],
            "warningLevel": "unknown",
        },
        "errors": [],
        "privacyFindings": [],
    }


def _approval_status(job: Mapping[str, Any], user_doc: Mapping[str, Any]) -> str:
    if str(job.get("status") or "") == "approved":
        return "approved"
    avatar = _as_map(user_doc.get("avatar"))
    if avatar.get("approvedAvatarUrl") and avatar.get("status") == "approved":
        return "approved"
    if avatar.get("approvedAvatarUrl"):
        return "approved_url_present"
    return "not_approved"


def _safe_errors(job: Mapping[str, Any]) -> list[dict[str, str]]:
    errors = []
    for code_key, message_key in (
        ("errorCode", "errorMessage"),
        ("reasonCode", "reasonMessage"),
    ):
        if job.get(code_key) or job.get(message_key):
            errors.append(
                {
                    "code": _redact_sensitive_text(job.get(code_key)),
                    "message": _redact_sensitive_text(job.get(message_key)),
                }
            )
    processing = _as_map(job.get("processing"))
    if processing.get("lastErrorCode") or processing.get("lastErrorMessage"):
        errors.append(
            {
                "code": _redact_sensitive_text(processing.get("lastErrorCode")),
                "message": _redact_sensitive_text(processing.get("lastErrorMessage")),
            }
        )
    return errors


def _summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    job_rows = [row for row in rows if row.get("jobId")]
    preview_ready = [
        row for row in job_rows if row.get("status") in {"preview_ready", "approved"}
    ]
    approved = [row for row in job_rows if row.get("approvalStatus") == "approved"]
    candidate_totals = {
        key: sum(int(_as_map(row.get("candidateStats")).get(key) or 0) for row in job_rows)
        for key in (
            "candidateCount",
            "previewCount",
            "hardPassCount",
            "softPassCount",
            "needsReviewCount",
            "hardRejectCount",
            "tooIdentifiableCount",
            "childlikeRiskCount",
            "beautificationRiskCount",
        )
    }
    timing = {
        field: _numeric_summary(
            _to_float(_as_map(row.get("timing")).get(field)) for row in job_rows
        )
        for field in TIMING_FIELDS
    }
    estimated_usd_values = [_to_float(row.get("estimatedUsd")) for row in job_rows]
    preview_bytes = [
        _to_float(_as_map(row.get("previewPayload")).get("previewPayloadBytes"))
        for row in job_rows
    ]
    return {
        "previewReadyRate": _ratio(len(preview_ready), len(job_rows)),
        "approvalRate": _ratio(len(approved), len(job_rows)),
        "candidateStats": candidate_totals,
        "timing": timing,
        "estimatedUsd": _numeric_summary(estimated_usd_values),
        "previewPayloadBytes": _numeric_summary(preview_bytes),
        "previewPayloadWarnings": {
            "warning": sum(
                1
                for row in job_rows
                if _as_map(row.get("previewPayload")).get("warningLevel") == "warning"
            ),
            "critical": sum(
                1
                for row in job_rows
                if _as_map(row.get("previewPayload")).get("warningLevel") == "critical"
            ),
        },
        "privacyFindingCount": sum(len(_as_list(row.get("privacyFindings"))) for row in job_rows),
    }


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def _numeric_summary(values: Iterable[float | None]) -> dict[str, float | None]:
    nums = sorted(value for value in values if value is not None)
    if not nums:
        return {"count": 0, "avg": None, "min": None, "max": None}
    return {
        "count": len(nums),
        "avg": round(mean(nums), 4),
        "min": round(nums[0], 4),
        "max": round(nums[-1], 4),
    }


def build_report_from_fixture(
    fixture: Mapping[str, Any],
    *,
    project: str,
    uids: Sequence[str],
    since: datetime | None,
    redact: bool = True,
) -> dict[str, Any]:
    return build_report_from_documents(
        project=project,
        uids=uids,
        since=since,
        users=_normalize_doc_map(fixture.get("users")),
        private_media=_normalize_doc_map(
            fixture.get("privateMedia", fixture.get("userPrivateMedia"))
        ),
        jobs=_normalize_doc_map(fixture.get("jobs", fixture.get("avatarJobs"))),
        candidates=_normalize_doc_map(
            fixture.get("candidates", fixture.get("avatarCandidates"))
        ),
        redact=redact,
    )


def build_report_from_firestore(
    *,
    project: str,
    uids: Sequence[str],
    since: datetime | None,
    redact: bool = True,
) -> dict[str, Any]:
    try:
        from google.cloud import firestore
    except Exception as exc:  # pragma: no cover - environment dependent
        raise RuntimeError("google-cloud-firestore is required for live reports") from exc

    client = firestore.Client(project=project)
    users: dict[str, Mapping[str, Any]] = {}
    private_media: dict[str, Mapping[str, Any]] = {}
    jobs: dict[str, Mapping[str, Any]] = {}
    candidates: dict[str, Mapping[str, Any]] = {}

    for uid in uids:
        uid = str(uid).strip()
        if not uid:
            continue
        users[uid] = client.collection("users").document(uid).get().to_dict() or {}
        private_media[uid] = (
            client.collection("userPrivateMedia").document(uid).get().to_dict() or {}
        )
        for snapshot in client.collection("avatarJobs").where("uid", "==", uid).stream():
            data = snapshot.to_dict() or {}
            if _job_created_after(data, since):
                jobs[snapshot.id] = data

    job_ids = {str(job.get("jobId") or job_id) for job_id, job in jobs.items()}
    for job_id in job_ids:
        for snapshot in client.collection("avatarCandidates").where("jobId", "==", job_id).stream():
            candidates[snapshot.id] = snapshot.to_dict() or {}

    return build_report_from_documents(
        project=project,
        uids=uids,
        since=since,
        users=users,
        private_media=private_media,
        jobs=jobs,
        candidates=candidates,
        redact=redact,
    )


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fieldnames = [
        "uidHash",
        "jobId",
        "status",
        "candidateCount",
        "previewCount",
        "hardPassCount",
        "softPassCount",
        "needsReviewCount",
        "hardRejectCount",
        "tooIdentifiableCount",
        "approvalStatus",
        "approvedAvatarUrlPresent",
        "totalWorkerSeconds",
        "estimatedUsd",
        "previewPayloadBytes",
        "previewPayloadWarning",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            stats = _as_map(row.get("candidateStats"))
            timing = _as_map(row.get("timing"))
            preview = _as_map(row.get("previewPayload"))
            writer.writerow(
                {
                    "uidHash": row.get("uidHash"),
                    "jobId": row.get("jobId"),
                    "status": row.get("status"),
                    "candidateCount": stats.get("candidateCount"),
                    "previewCount": stats.get("previewCount"),
                    "hardPassCount": stats.get("hardPassCount"),
                    "softPassCount": stats.get("softPassCount"),
                    "needsReviewCount": stats.get("needsReviewCount"),
                    "hardRejectCount": stats.get("hardRejectCount"),
                    "tooIdentifiableCount": stats.get("tooIdentifiableCount"),
                    "approvalStatus": row.get("approvalStatus"),
                    "approvedAvatarUrlPresent": row.get("approvedAvatarUrlPresent"),
                    "totalWorkerSeconds": timing.get("totalWorkerSeconds"),
                    "estimatedUsd": row.get("estimatedUsd"),
                    "previewPayloadBytes": preview.get("previewPayloadBytes"),
                    "previewPayloadWarning": preview.get("warningLevel"),
                }
            )


def _assert_safe_output(report: Mapping[str, Any]) -> None:
    text = json.dumps(report, ensure_ascii=False, sort_keys=True)
    for pattern in PRIVATE_OUTPUT_PATTERNS:
        if pattern.search(text):
            raise RuntimeError(f"Report output contains forbidden private marker: {pattern.pattern}")


def _parse_uids(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a redacted internal avatar canary report."
    )
    parser.add_argument("--project", default="seolleyeon-final")
    parser.add_argument("--uids", required=True, help="Comma-separated staging user UIDs.")
    parser.add_argument("--since", help="ISO timestamp lower bound for avatarJobs.createdAt.")
    parser.add_argument("--output_json", "--output-json", dest="output_json")
    parser.add_argument("--output_csv", "--output-csv", dest="output_csv")
    parser.add_argument("--fixture_json", "--fixture-json", dest="fixture_json")
    parser.add_argument("--redact", action="store_true", default=True)
    args = parser.parse_args(argv)

    since = _parse_since(args.since)
    uids = _parse_uids(args.uids)
    if args.fixture_json:
        fixture = json.loads(Path(args.fixture_json).read_text(encoding="utf-8"))
        report = build_report_from_fixture(
            fixture,
            project=args.project,
            uids=uids,
            since=since,
            redact=args.redact,
        )
    else:
        report = build_report_from_firestore(
            project=args.project,
            uids=uids,
            since=since,
            redact=args.redact,
        )

    _assert_safe_output(report)

    if args.output_json:
        Path(args.output_json).write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    if args.output_csv:
        _write_csv(Path(args.output_csv), _as_list(report.get("jobs")))
    if not args.output_json and not args.output_csv:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
