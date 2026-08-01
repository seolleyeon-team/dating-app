from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]
AVATAR_LIB = REPO_ROOT / "lib" / "ai_recommend_model"
if str(AVATAR_LIB) not in sys.path:
    sys.path.insert(0, str(AVATAR_LIB))

from avatar_generation.analysis.config import SourceSafetyConfig
from avatar_generation.analysis.detectors import StaticFaceDetector
from avatar_generation.analysis.schema import FaceDetection
from avatar_generation.analysis.source_analyzer import analyze_avatar_source_image
from avatar_generation.preprocessing.reference import (
    ReferencePreprocessConfig,
    preprocess_reference_image,
)

PROJECT = "seolleyeon-final"
REGION = "asia-northeast3"
EXPECTED_CASES = (
    "A_SIMPLE_SINGLE_FACE",
    "B_COMPLEX_CLEAR_PRIMARY",
    "C_SMALL_BACKGROUND_FACE",
    "D_TWO_PRIMARY_FACES",
    "E_TEXT_LOGO_RISK",
)
POSITIVE_CASES = {
    "A_SIMPLE_SINGLE_FACE",
    "B_COMPLEX_CLEAR_PRIMARY",
    "C_SMALL_BACKGROUND_FACE",
    "E_TEXT_LOGO_RISK",
}
FORBIDDEN_MARKERS = (
    "sourcePhotoRefs",
    "sourcePhotoGcsUri",
    "gcsUri",
    "userPrivateMedia",
    "clipEmbeddings",
    "gs://",
    "gcs://",
    "X-Goog-Signature",
    "X-Goog-Credential",
    "GoogleAccessId",
    "Signature=",
    "signedUrl",
    "seolleyeon-final-private-source-photos",
    "seolleyeon-final-avatar-temp",
    "raw_landmarks",
    "face_landmarks",
    "blendshapes",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_text(value: Any, *, length: int = 12) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:length]


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _parse_case_rows(path: Path) -> tuple[dict[str, tuple[str, Path]], list[str]]:
    rows: dict[str, tuple[str, Path]] = {}
    invalid: list[str] = []
    if not path.is_file():
        return rows, [f"missing_file:{path}"]
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        parts = line.split("=", 2)
        if len(parts) != 3:
            invalid.append(line)
            continue
        case, uid, photo_path = (part.strip() for part in parts)
        rows[case] = (uid, Path(photo_path))
    return rows, invalid


def _api_key_from_google_services(path: Path) -> str:
    payload = _load_json(path)
    for client in payload.get("client") or []:
        if not isinstance(client, Mapping):
            continue
        for api_key in client.get("api_key") or []:
            if isinstance(api_key, Mapping) and api_key.get("current_key"):
                return str(api_key["current_key"])
    return ""


def _post_json(
    url: str,
    payload: Mapping[str, Any],
    *,
    token: str = "",
    timeout_seconds: int = 120,
) -> tuple[int, Mapping[str, Any], str]:
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            text = response.read().decode("utf-8")
            parsed = json.loads(text) if text else {}
            return int(response.status), parsed if isinstance(parsed, Mapping) else {}, text
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = {"error": {"message": text[:240]}}
        return int(exc.code), parsed if isinstance(parsed, Mapping) else {}, text


def _callable_url(name: str) -> str:
    return f"https://{REGION}-{PROJECT}.cloudfunctions.net/{name}"


def _callable(name: str, data: Mapping[str, Any], token: str) -> tuple[int, Mapping[str, Any], str]:
    return _post_json(_callable_url(name), {"data": data}, token=token, timeout_seconds=180)


def _safe_response(value: Any) -> bool:
    encoded = json.dumps(value, ensure_ascii=False, default=str)
    return not any(marker in encoded for marker in FORBIDDEN_MARKERS)


def _auth_tokens_by_uid(api_key: str, secret_path: Path) -> dict[str, str]:
    tokens: dict[str, str] = {}
    payload = _load_json(secret_path)
    signin_url = (
        "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"
        f"?key={api_key}"
    )
    for entry in (payload.get("users") or {}).values():
        if not isinstance(entry, Mapping):
            continue
        email = str(entry.get("email") or "")
        password = str(entry.get("password") or "")
        uid = str(entry.get("uid") or "")
        if not email or not password or not uid:
            continue
        status, parsed, _ = _post_json(
            signin_url,
            {"email": email, "password": password, "returnSecureToken": True},
            timeout_seconds=60,
        )
        if status == 200 and parsed.get("localId") == uid and parsed.get("idToken"):
            tokens[uid] = str(parsed["idToken"])
    return tokens


def _source_config() -> SourceSafetyConfig:
    return SourceSafetyConfig(
        mediapipe_enabled=False,
        mediapipe_fail_closed_in_production=False,
        primary_face_min_score_margin=0.20,
        primary_face_min_relative_area=0.04,
        allow_small_background_faces_if_removed=True,
        reject_large_secondary_face=True,
    )


def _fixture_faces(fixture: Mapping[str, Any]) -> list[FaceDetection]:
    faces = []
    for face in fixture.get("faces") or []:
        if not isinstance(face, Mapping):
            continue
        bbox = face.get("bbox")
        if isinstance(bbox, list) and len(bbox) == 4:
            faces.append(
                FaceDetection(
                    bbox=tuple(float(value) for value in bbox),  # type: ignore[arg-type]
                    confidence=0.96,
                )
            )
    return faces


def _analyze_fixture(path: Path, fixture: Mapping[str, Any], *, text_logo_risk: bool) -> tuple[dict[str, Any], dict[str, Any]]:
    image = Image.open(path).convert("RGB")
    result = analyze_avatar_source_image(
        image,
        source_ref="local://complex-background-live-redacted.jpg",
        detector=StaticFaceDetector(
            _fixture_faces(fixture),
            provider_name="matrix_manifest_static",
        ),
        config=_source_config(),
    )
    source_doc = result.to_document()
    if text_logo_risk:
        source_doc["backgroundTextLogoRisk"] = True
    preprocess = preprocess_reference_image(
        image,
        source_analysis=source_doc,
        config=ReferencePreprocessConfig(
            primary_crop_enabled=True,
            background_neutralization_enabled=True,
            background_neutral_color="#F7F2EC",
            background_text_logo_blur=True,
        ),
    )
    return source_doc, preprocess.metadata


def _fresh_user_state(db: Any, uid: str) -> dict[str, Any]:
    data = db.collection("users").document(uid).get().to_dict() or {}
    avatar = data.get("avatar") if isinstance(data.get("avatar"), Mapping) else {}
    return {
        "userDocExists": bool(data),
        "isStudentVerified": bool(data.get("isStudentVerified")),
        "studentEmailDomainOk": str(data.get("studentEmail") or "").endswith("@yonsei.ac.kr"),
        "approvedLock": str(avatar.get("status") or "") == "approved"
        and bool(avatar.get("approvedAvatarUrl")),
    }


def _image_format(path: Path) -> str:
    if not path.is_file():
        return ""
    with Image.open(path) as image:
        return str(image.format or "")


def validate_and_dry_run(args: argparse.Namespace) -> dict[str, Any]:
    import firebase_admin
    from firebase_admin import auth, credentials, firestore

    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.ApplicationDefault(), {"projectId": PROJECT})
    db = firestore.client()

    required, required_invalid = _parse_case_rows(Path(args.required_file))
    consent, consent_invalid = _parse_case_rows(Path(args.consent_file))
    fixture_manifest = _load_json(Path(args.fixture_manifest))
    fixtures = {
        str(item.get("case")): item
        for item in fixture_manifest.get("fixtures", [])
        if isinstance(item, Mapping)
    }
    api_key = _api_key_from_google_services(Path(args.google_services_json))
    tokens = _auth_tokens_by_uid(api_key, Path(args.auth_secret_json))

    matched_rows = 0
    missing_rows = 0
    unexpected_rows = 0
    for case, row in required.items():
        if consent.get(case) == row:
            matched_rows += 1
        else:
            missing_rows += 1
    for case, row in consent.items():
        if required.get(case) != row:
            unexpected_rows += 1

    consent_text = Path(args.consent_file).read_text(encoding="utf-8-sig") if Path(args.consent_file).is_file() else ""
    general_consent_valid = (
        Path(args.consent_file).is_file()
        and "seolleyeon-final" in consent_text
        and "staging" in consent_text.lower()
        and ("동의" in consent_text or "consent" in consent_text.lower())
        and "production" in consent_text.lower()
    )
    exact_ok = (
        general_consent_valid
        and not required_invalid
        and not consent_invalid
        and matched_rows == len(EXPECTED_CASES)
        and missing_rows == 0
        and unexpected_rows == 0
        and set(required) == set(EXPECTED_CASES)
    )

    rows: list[dict[str, Any]] = []
    blockers: list[str] = []
    for case in EXPECTED_CASES:
        uid, photo_path = required.get(case, ("", Path("")))
        fixture = fixtures.get(case, {})
        if not uid or not photo_path:
            blockers.append(f"missing_required_row:{case}")
            continue
        try:
            auth.get_user(uid)
            auth_exists = True
        except Exception:
            auth_exists = False
            blockers.append(f"auth_uid_missing:{case}")
        user_state = _fresh_user_state(db, uid)
        image_format = _image_format(photo_path)
        source_doc, preprocess_doc = _analyze_fixture(
            photo_path,
            fixture,
            text_logo_risk=case == "E_TEXT_LOGO_RISK",
        )
        expected_ok = (
            source_doc.get("status") == "accepted"
            if case in POSITIVE_CASES
            else (
                source_doc.get("hardReject") is True
                and "multi_face_primary" in (source_doc.get("rejectReasons") or [])
            )
        )
        case_blockers = []
        if not auth_exists:
            case_blockers.append("auth_uid_missing")
        if user_state["approvedLock"]:
            case_blockers.append("approved_lock")
        if not user_state["userDocExists"]:
            case_blockers.append("user_doc_missing")
        if not user_state["isStudentVerified"]:
            case_blockers.append("student_not_verified")
        if not user_state["studentEmailDomainOk"]:
            case_blockers.append("student_email_not_yonsei")
        if not photo_path.is_file():
            case_blockers.append("photo_missing")
        if image_format.upper() != "JPEG":
            case_blockers.append("not_plain_jpeg")
        if uid not in tokens:
            case_blockers.append("missing_auth_token")
        if not expected_ok:
            case_blockers.append("local_preflight_unexpected")
        blockers.extend(f"{blocker}:{case}" for blocker in case_blockers)
        rows.append(
            {
                "caseName": case,
                "uid": uid,
                "uidHash": f"uid:{_hash_text(uid)}",
                "photoPath": str(photo_path),
                "photoFile": photo_path.name,
                "authExists": auth_exists,
                **user_state,
                "imageFormat": image_format,
                "localPreflightStatus": source_doc.get("status"),
                "localRejectReasons": source_doc.get("rejectReasons", []),
                "localExpectedOk": expected_ok,
                "uploadIntended": True,
                "blockers": case_blockers,
                "sourceAnalysis": _selected_source_fields(source_doc),
                "referencePreprocess": _selected_preprocess_fields(preprocess_doc),
            }
        )

    status = "READY" if exact_ok and not blockers else "BLOCKED"
    if not exact_ok:
        status = "BLOCKED_BY_CONSENT"
    elif blockers:
        status = "BLOCKED_BY_FIXTURE"
    report = {
        "generatedAt": _now(),
        "status": status,
        "project": PROJECT,
        "generalConsentValid": general_consent_valid,
        "exactConsent": {
            "rowMatch": exact_ok,
            "matched": matched_rows,
            "missing": missing_rows,
            "unexpected": unexpected_rows,
            "invalidRequiredRows": len(required_invalid),
            "invalidConsentRows": len(consent_invalid),
        },
        "freshUidCount": len(rows),
        "rows": [_public_dry_row(row) for row in rows],
        "blockers": blockers,
        "safeReport": True,
        "productionReady": False,
    }
    report["safeReport"] = _safe_response(report)
    Path(args.dry_run_json).write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report


def _public_dry_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in row.items()
        if key not in {"uid", "photoPath"}
    }


def _selected_source_fields(source: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "primaryFaceConfidence": source.get("primaryFaceConfidence"),
        "secondaryFaceCount": source.get("secondaryFaceCount"),
        "largeSecondaryFaceCount": source.get("largeSecondaryFaceCount"),
        "backgroundFaceRisk": source.get("backgroundFaceRisk"),
        "hardReject": source.get("hardReject"),
        "rejectReasons": list(source.get("rejectReasons") or []),
    }


def _selected_preprocess_fields(preprocess: Mapping[str, Any]) -> dict[str, Any]:
    bg = preprocess.get("backgroundNeutralization")
    bg_doc = bg if isinstance(bg, Mapping) else {}
    return {
        "primaryCropApplied": preprocess.get("primaryCropApplied"),
        "cropType": preprocess.get("cropType"),
        "cropRisk": preprocess.get("cropRisk"),
        "backgroundNeutralized": preprocess.get("backgroundNeutralized"),
        "secondaryFacesNeutralized": bg_doc.get("secondaryFaceAction")
        == "removed_with_background",
        "textLogoNeutralized": bg_doc.get("textLogoAction") == "neutralized_background",
    }


def _candidate_counts(db: Any, job_id: str) -> tuple[dict[str, int], dict[str, Any]]:
    counts = {
        "candidateCount": 0,
        "previewCount": 0,
        "hardRejectCount": 0,
    }
    qa_rollup = {
        "backgroundLeakageRisk": None,
        "secondaryFaceLeakageRisk": None,
        "textLogoWatermarkRisk": None,
        "cropIsolationQuality": None,
    }
    for snapshot in db.collection("avatarCandidates").where("jobId", "==", job_id).stream():
        data = snapshot.to_dict() or {}
        qa = data.get("qa") if isinstance(data.get("qa"), Mapping) else {}
        rerank = data.get("rerank") if isinstance(data.get("rerank"), Mapping) else {}
        counts["candidateCount"] += 1
        if qa.get("previewAllowed") is True or rerank.get("selectedForPreview") is True:
            counts["previewCount"] += 1
        if qa.get("rejectReasons"):
            counts["hardRejectCount"] += 1
        for key in qa_rollup:
            if qa_rollup[key] is None and key in qa:
                qa_rollup[key] = qa.get(key)
    return counts, qa_rollup


def _extract_result(parsed: Mapping[str, Any]) -> Mapping[str, Any]:
    result = parsed.get("result")
    if isinstance(result, Mapping):
        return result
    data = parsed.get("data")
    if isinstance(data, Mapping):
        return data
    return parsed


def _private_source_count(db: Any, uid: str) -> int:
    data = db.collection("userPrivateMedia").document(uid).get().to_dict() or {}
    source_photos = data.get("sourcePhotos")
    return len(source_photos) if isinstance(source_photos, list) else 0


def _job_count(db: Any, uid: str) -> int:
    return sum(1 for _ in db.collection("avatarJobs").where("uid", "==", uid).stream())


def _run_case(
    *,
    db: Any,
    row: Mapping[str, Any],
    token: str,
    poll_timeout_seconds: int,
) -> dict[str, Any]:
    uid = str(row["uid"])
    photo_path = Path(str(row["photoPath"]))
    case = str(row["caseName"])
    started = time.time()
    payload = {
        "imageBase64": base64.b64encode(photo_path.read_bytes()).decode("ascii"),
        "contentType": "image/jpeg",
        "fileName": photo_path.name,
        "uid": uid,
        "chatPartnerRealPhotoDisclosure": False,
    }
    result: dict[str, Any] = {
        "caseName": case,
        "uidHash": row["uidHash"],
        "preflightStatus": row["localPreflightStatus"],
        "uploadStatus": "not_started",
        "jobId": None,
        "photoIdHash": "",
        "sourceAnalysis": row["sourceAnalysis"],
        "referencePreprocess": row["referencePreprocess"],
        "jobStatus": "not_created",
        "candidateCount": 0,
        "previewCount": 0,
        "approvalStatus": "not_attempted",
        "lockRetestStatus": "not_attempted",
        "qa": {
            "backgroundLeakageRisk": None,
            "secondaryFaceLeakageRisk": None,
            "textLogoWatermarkRisk": None,
            "cropIsolationQuality": None,
        },
        "timingCost": {"elapsedSeconds": None, "cost": None},
    }
    status, parsed, _ = _callable("uploadAvatarSourcePhoto", payload, token)
    response = _extract_result(parsed)
    job_id = str(response.get("jobId") or "")
    result["uploadStatus"] = f"http_{status}"
    result["uploadSafeResponse"] = _safe_response(parsed)
    result["queueStatus"] = response.get("queueStatus") or response.get("avatarStatus")
    result["jobId"] = job_id or None
    result["photoIdHash"] = _hash_text(response.get("photoId"))
    if status != 200 or not job_id:
        result["errorCode"] = _safe_error(parsed)
        result["timingCost"]["elapsedSeconds"] = round(time.time() - started, 2)
        return result

    terminal = {"preview_ready", "no_previewable_candidates", "needs_review", "failed", "approved"}
    status_history: list[dict[str, Any]] = []
    final_job: Mapping[str, Any] = {}
    deadline = time.time() + max(60, poll_timeout_seconds)
    while time.time() < deadline:
        job = db.collection("avatarJobs").document(job_id).get().to_dict() or {}
        job_status = str(job.get("status") or "")
        status_history.append({"at": _now(), "status": job_status, "errorCode": job.get("errorCode")})
        final_job = job
        if job_status in terminal:
            if job_status == "failed" and job.get("errorCode") == "avatar_worker_deadline_exceeded":
                time.sleep(30)
                continue
            break
        time.sleep(15)

    result["statusHistory"] = status_history[-40:]
    result["jobStatus"] = final_job.get("status") or "timeout"
    result["errorCode"] = final_job.get("errorCode")
    if isinstance(final_job.get("sourceAnalysis"), Mapping):
        result["sourceAnalysis"] = _selected_source_fields(final_job["sourceAnalysis"])
    if isinstance(final_job.get("referencePreprocess"), Mapping):
        result["referencePreprocess"] = _selected_preprocess_fields(final_job["referencePreprocess"])
    result["timingCost"]["cost"] = final_job.get("cost") if isinstance(final_job.get("cost"), Mapping) else None

    counts, qa_rollup = _candidate_counts(db, job_id)
    result.update(counts)
    result["qa"] = qa_rollup

    if result["jobStatus"] == "preview_ready":
        preview_status, preview_parsed, preview_text = _callable(
            "getAvatarJobCandidates",
            {"jobId": job_id},
            token,
        )
        preview_data = _extract_result(preview_parsed)
        candidates = preview_data.get("candidates") if isinstance(preview_data, Mapping) else []
        if not isinstance(candidates, list):
            candidates = []
        result["previewApi"] = {
            "httpStatus": preview_status,
            "safeResponse": _safe_response(preview_parsed),
            "candidateCount": len(candidates),
            "responseBytesApprox": len(preview_text.encode("utf-8")),
        }
        result["candidateCount"] = len(candidates)
        result["previewCount"] = len(candidates)
        if candidates:
            candidate_id = str(candidates[0].get("candidateId") or "")
            approve_status, approve_parsed, _ = _callable(
                "approveAvatarCandidate",
                {"candidateId": candidate_id},
                token,
            )
            user = db.collection("users").document(uid).get().to_dict() or {}
            avatar = user.get("avatar") if isinstance(user.get("avatar"), Mapping) else {}
            result["approvalStatus"] = (
                "approved"
                if approve_status == 200
                and avatar.get("status") == "approved"
                and bool(avatar.get("approvedAvatarUrl"))
                else f"http_{approve_status}"
            )
            result["approvalSafeResponse"] = _safe_response(approve_parsed)
            if approve_status == 200:
                before_sources = _private_source_count(db, uid)
                before_jobs = _job_count(db, uid)
                lock_status, lock_parsed, _ = _callable("uploadAvatarSourcePhoto", payload, token)
                result["lockRetestStatus"] = (
                    "rejected"
                    if lock_status >= 400
                    else f"http_{lock_status}"
                )
                result["lockRetestSafeResponse"] = _safe_response(lock_parsed)
                result["lockRetestCounts"] = {
                    "sourceCountBefore": before_sources,
                    "sourceCountAfter": _private_source_count(db, uid),
                    "jobCountBefore": before_jobs,
                    "jobCountAfter": _job_count(db, uid),
                }
    result["timingCost"]["elapsedSeconds"] = round(time.time() - started, 2)
    return result


def _safe_error(parsed: Mapping[str, Any]) -> str:
    error = parsed.get("error") if isinstance(parsed.get("error"), Mapping) else {}
    message = str(error.get("message") or parsed.get("message") or "")[:160]
    return message


def _write_live_reports(report: Mapping[str, Any], json_path: Path, csv_path: Path) -> None:
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    fields = [
        "caseName",
        "uidHash",
        "preflightStatus",
        "uploadStatus",
        "jobId",
        "sourceAnalysis.primaryFaceConfidence",
        "secondaryFaceCount",
        "largeSecondaryFaceCount",
        "backgroundFaceRisk",
        "referencePreprocess.primaryCropApplied",
        "backgroundNeutralized",
        "secondaryFacesNeutralized",
        "textLogoNeutralized",
        "jobStatus",
        "candidateCount",
        "previewCount",
        "approvalStatus",
        "lockRetestStatus",
        "QA.backgroundLeakageRisk",
        "QA.secondaryFaceLeakageRisk",
        "QA.textLogoWatermarkRisk",
        "cropIsolationQuality",
        "timingCost",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in report.get("matrix", []):
            if not isinstance(row, Mapping):
                continue
            source = row.get("sourceAnalysis") if isinstance(row.get("sourceAnalysis"), Mapping) else {}
            preprocess = row.get("referencePreprocess") if isinstance(row.get("referencePreprocess"), Mapping) else {}
            qa = row.get("qa") if isinstance(row.get("qa"), Mapping) else {}
            writer.writerow(
                {
                    "caseName": row.get("caseName"),
                    "uidHash": row.get("uidHash"),
                    "preflightStatus": row.get("preflightStatus"),
                    "uploadStatus": row.get("uploadStatus"),
                    "jobId": row.get("jobId") or "",
                    "sourceAnalysis.primaryFaceConfidence": source.get("primaryFaceConfidence"),
                    "secondaryFaceCount": source.get("secondaryFaceCount"),
                    "largeSecondaryFaceCount": source.get("largeSecondaryFaceCount"),
                    "backgroundFaceRisk": source.get("backgroundFaceRisk"),
                    "referencePreprocess.primaryCropApplied": preprocess.get("primaryCropApplied"),
                    "backgroundNeutralized": preprocess.get("backgroundNeutralized"),
                    "secondaryFacesNeutralized": preprocess.get("secondaryFacesNeutralized"),
                    "textLogoNeutralized": preprocess.get("textLogoNeutralized"),
                    "jobStatus": row.get("jobStatus"),
                    "candidateCount": row.get("candidateCount"),
                    "previewCount": row.get("previewCount"),
                    "approvalStatus": row.get("approvalStatus"),
                    "lockRetestStatus": row.get("lockRetestStatus"),
                    "QA.backgroundLeakageRisk": qa.get("backgroundLeakageRisk"),
                    "QA.secondaryFaceLeakageRisk": qa.get("secondaryFaceLeakageRisk"),
                    "QA.textLogoWatermarkRisk": qa.get("textLogoWatermarkRisk"),
                    "cropIsolationQuality": qa.get("cropIsolationQuality"),
                    "timingCost": json.dumps(row.get("timingCost") or {}, ensure_ascii=False),
                }
            )


def apply_live(args: argparse.Namespace, dry_run: Mapping[str, Any]) -> dict[str, Any]:
    from google.cloud import firestore

    if dry_run.get("status") != "READY":
        raise SystemExit("dry-run status is not READY; refusing live upload")
    db = firestore.Client(project=PROJECT)
    api_key = _api_key_from_google_services(Path(args.google_services_json))
    tokens = _auth_tokens_by_uid(api_key, Path(args.auth_secret_json))
    rows = []
    required, _ = _parse_case_rows(Path(args.required_file))
    dry_rows = {str(row.get("caseName")): row for row in dry_run.get("rows", []) if isinstance(row, Mapping)}
    for case in EXPECTED_CASES:
        uid, photo_path = required[case]
        dry_row = dict(dry_rows[case])
        dry_row["uid"] = uid
        dry_row["photoPath"] = str(photo_path)
        token = tokens.get(uid)
        if not token:
            raise SystemExit(f"missing auth token for {case}")
        rows.append(_run_case(db=db, row=dry_row, token=token, poll_timeout_seconds=args.poll_timeout_seconds))

    positive_rows = [row for row in rows if row["caseName"] in POSITIVE_CASES]
    preview_ready = sum(1 for row in positive_rows if row.get("jobStatus") == "preview_ready")
    approved = sum(1 for row in positive_rows if row.get("approvalStatus") == "approved")
    d_row = next((row for row in rows if row.get("caseName") == "D_TWO_PRIMARY_FACES"), {})
    d_rejected = (
        d_row.get("jobStatus") == "failed"
        and str(d_row.get("errorCode") or "") in {"avatar_source_multi_face", "multi_face_primary"}
    )
    status = "PASS_COMPLEX_BACKGROUND_LIVE_MATRIX"
    if preview_ready < len(positive_rows) or approved < preview_ready or not d_rejected:
        status = "PASS_PARTIAL" if d_rejected and any(row.get("jobStatus") in {"preview_ready", "no_previewable_candidates", "needs_review", "failed"} for row in positive_rows) else "FAILED"
    report = {
        "generatedAt": _now(),
        "status": status,
        "project": PROJECT,
        "workerRevision": "seolleyeon-avatar-worker-00033-8gs",
        "freshUidCount": dry_run.get("freshUidCount"),
        "exactConsent": dry_run.get("exactConsent"),
        "previewReadyRate": f"{preview_ready}/{len(positive_rows)}",
        "approvalRate": f"{approved}/{len(positive_rows)}",
        "matrix": rows,
        "safeReport": True,
        "productionReady": False,
    }
    report["safeReport"] = _safe_response(report)
    _write_live_reports(
        report,
        Path(args.output_json),
        Path(args.output_csv),
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--required_file", default="out/complex_background_live_uid_photo_consent_required.txt")
    parser.add_argument("--consent_file", default="complex_background_live_uid_photo_consent_map.txt")
    parser.add_argument("--fixture_manifest", default="out/complex_background_matrix_fixtures/fixture_manifest.json")
    parser.add_argument("--google_services_json", default="android/app/google-services.json")
    parser.add_argument("--auth_secret_json", default=".local_secrets/staging_complex_background_matrix_users.json")
    parser.add_argument("--dry_run_json", default="out/complex_background_matrix_live_dry_run.json")
    parser.add_argument("--output_json", default="out/complex_background_matrix_live_report.json")
    parser.add_argument("--output_csv", default="out/complex_background_matrix_live_report.csv")
    parser.add_argument("--poll_timeout_seconds", type=int, default=1800)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    dry_run = validate_and_dry_run(args)
    if not args.apply:
        print(json.dumps({"status": dry_run["status"], "dryRunJson": args.dry_run_json}, ensure_ascii=False))
        return 0 if dry_run["status"] == "READY" else 2
    report = apply_live(args, dry_run)
    print(
        json.dumps(
            {
                "status": report["status"],
                "outputJson": args.output_json,
                "outputCsv": args.output_csv,
                "previewReadyRate": report["previewReadyRate"],
                "approvalRate": report["approvalRate"],
            },
            ensure_ascii=False,
        )
    )
    return 0 if report["status"] in {"PASS_COMPLEX_BACKGROUND_LIVE_MATRIX", "PASS_PARTIAL"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
