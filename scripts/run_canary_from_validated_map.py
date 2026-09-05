from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import quote

try:
    from avatar_auth_secrets import load_auth_secret_users
except ModuleNotFoundError:  # pragma: no cover - importlib test path support
    import importlib.util

    _AUTH_SECRET_SPEC = importlib.util.spec_from_file_location(
        "avatar_auth_secrets",
        Path(__file__).with_name("avatar_auth_secrets.py"),
    )
    if _AUTH_SECRET_SPEC is None or _AUTH_SECRET_SPEC.loader is None:
        raise
    _AUTH_SECRET_MODULE = importlib.util.module_from_spec(_AUTH_SECRET_SPEC)
    _AUTH_SECRET_SPEC.loader.exec_module(_AUTH_SECRET_MODULE)
    load_auth_secret_users = _AUTH_SECRET_MODULE.load_auth_secret_users

try:
    from avatar_exact_replay_auth import (
        initialize_exact_replay_admin,
        mint_exact_replay_id_token,
        validate_exact_replay_preupload,
    )
except ModuleNotFoundError:  # pragma: no cover - importlib test path support
    _EXACT_REPLAY_AUTH_SPEC = importlib.util.spec_from_file_location(
        "avatar_exact_replay_auth",
        Path(__file__).with_name("avatar_exact_replay_auth.py"),
    )
    if _EXACT_REPLAY_AUTH_SPEC is None or _EXACT_REPLAY_AUTH_SPEC.loader is None:
        raise
    _EXACT_REPLAY_AUTH_MODULE = importlib.util.module_from_spec(_EXACT_REPLAY_AUTH_SPEC)
    _EXACT_REPLAY_AUTH_SPEC.loader.exec_module(_EXACT_REPLAY_AUTH_MODULE)
    initialize_exact_replay_admin = _EXACT_REPLAY_AUTH_MODULE.initialize_exact_replay_admin
    mint_exact_replay_id_token = _EXACT_REPLAY_AUTH_MODULE.mint_exact_replay_id_token
    validate_exact_replay_preupload = _EXACT_REPLAY_AUTH_MODULE.validate_exact_replay_preupload

FORBIDDEN_RESPONSE_MARKERS = (
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
)
DEFAULT_AUTH_SECRET_PATHS = (
    Path(".local_secrets/staging_test_users.json"),
    Path(".local_secrets/staging_test_users_de.json"),
    Path(".local_secrets/staging_pr84_canary_users.json"),
)


def _hash_text(value: Any, *, length: int = 12) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:length]


def _safe_client_request_id(uid: str, file_name: str) -> str:
    lineage = json.dumps(
        {"fileName": str(file_name or ""), "uid": str(uid or "")},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    digest = hashlib.sha256(lineage.encode("utf-8")).hexdigest()[:24]
    return f"calibration_{digest}"


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _prior_uid_hash(uid: str) -> str:
    return f"uid:{_hash_text(uid)}"


def _operator_replay_client_request_id(
    uid: str,
    file_name: str,
    *,
    mapping_sha256: str,
    replay_id: str,
) -> str:
    lineage = json.dumps(
        {
            "fileName": str(file_name or ""),
            "mappingSha256": str(mapping_sha256 or ""),
            "replayId": str(replay_id or ""),
            "uid": str(uid or ""),
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    digest = hashlib.sha256(lineage.encode("utf-8")).hexdigest()[:24]
    return f"operator_replay_{digest}"


def _assignment_pairs(path: Path) -> list[tuple[str, Path]]:
    pairs: list[tuple[str, Path]] = []
    for raw in path.read_text(encoding="utf-8-sig", errors="strict").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        uid, photo_path = line.split("=", 1)
        normalized_uid = uid.strip().strip("<>")
        normalized_path = Path(photo_path.strip())
        if normalized_uid and str(normalized_path):
            pairs.append((normalized_uid, normalized_path))
    return pairs


def _pair_key(pair: tuple[str, Path]) -> tuple[str, str]:
    uid, photo_path = pair
    return uid, str(photo_path.resolve()).casefold()


def _operator_exact_replay_rows(
    *,
    mapping_file: Path,
    consent_file: Path,
    validation_json: Path,
    prior_report_json: Path,
    expected_mapping_sha256: str,
    row_start: int,
    row_limit: int,
) -> tuple[list[dict[str, Any]], int]:
    if not expected_mapping_sha256 or _sha256_file(mapping_file) != expected_mapping_sha256:
        raise ValueError("operator_exact_replay_mapping_digest_mismatch")
    mapping_pairs = _assignment_pairs(mapping_file)
    consent_pairs = _assignment_pairs(consent_file)
    if len(mapping_pairs) != 10 or {_pair_key(pair) for pair in mapping_pairs} != {
        _pair_key(pair) for pair in consent_pairs
    }:
        raise ValueError("operator_exact_replay_consent_mismatch")
    eligible, _ = _eligible_rows(
        mapping_file=mapping_file,
        validation_json=validation_json,
    )
    if len(eligible) != 7:
        raise ValueError("operator_exact_replay_eligible_count_mismatch")
    prior_jobs = _load_json(prior_report_json).get("jobs")
    if not isinstance(prior_jobs, list) or len(prior_jobs) != 7:
        raise ValueError("operator_exact_replay_prior_count_mismatch")
    for index, row in enumerate(eligible, start=1):
        uid = str(row.get("uid") or "")
        photo_path = Path(str(row.get("photoPath") or ""))
        photo_file = str(row.get("photoFile") or "")
        prior = next(
            (
                item
                for item in prior_jobs
                if isinstance(item, Mapping)
                and str(item.get("uidHash") or "") == _prior_uid_hash(uid)
                and str(item.get("photoFile") or "") == photo_file
            ),
            None,
        )
        if prior is None or not photo_path.is_file():
            raise ValueError("operator_exact_replay_prior_pair_mismatch")
        expected_prefix = str(prior.get("imageSha256Prefix") or "")
        exact_digest = _sha256_file(photo_path)
        if not expected_prefix or not exact_digest.startswith(expected_prefix):
            raise ValueError("operator_exact_replay_photo_digest_mismatch")
        validation_rows = _load_json(validation_json).get("rows") or []
        validation_row = next(
            (
                item
                for item in validation_rows
                if isinstance(item, Mapping)
                and str(item.get("photoFile") or "") == photo_file
            ),
            {},
        )
        source_quality_pass = (
            validation_row.get("eligibleForUpload") is True
            and not list(validation_row.get("blockers") or [])
            and str(validation_row.get("preflightRecommendation") or "") == "PASS"
        )
        if not source_quality_pass:
            raise ValueError("operator_exact_replay_source_quality_not_passed")
        row["rowIndex"] = index
        row["expectedPhotoSha256"] = exact_digest
        row["sourceQualityPass"] = True
    if row_start < 0 or row_limit < 1 or row_start + row_limit > len(eligible):
        raise ValueError("operator_exact_replay_row_window_invalid")
    return eligible[row_start : row_start + row_limit], len(eligible)

def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_app_check_token(path: Path) -> str:
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8-sig", errors="replace").strip()
    if not text:
        return ""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return text
    if not isinstance(payload, Mapping):
        return ""
    return str(payload.get("appCheckToken") or payload.get("token") or "").strip()


def _exchange_app_check_debug_token(
    *,
    project_number: str,
    app_id: str,
    api_key: str,
    debug_token: str,
) -> tuple[int, str]:
    if not all((project_number, app_id, api_key, debug_token)):
        return 0, ""
    encoded_app_id = quote(app_id, safe=":")
    url = (
        "https://firebaseappcheck.googleapis.com/v1/projects/"
        f"{project_number}/apps/{encoded_app_id}:exchangeDebugToken?key={api_key}"
    )
    status, payload, _ = _post_json(
        url,
        {"debugToken": debug_token, "limitedUse": False},
        timeout_seconds=60,
    )
    return status, str(payload.get("token") or "") if status == 200 else ""


def _api_key_from_google_services(path: Path) -> str:
    if not path.is_file():
        return ""
    payload = _load_json(path)
    clients = payload.get("client")
    if not isinstance(clients, list):
        return ""
    for client in clients:
        if not isinstance(client, Mapping):
            continue
        api_keys = client.get("api_key")
        if not isinstance(api_keys, list):
            continue
        for api_key in api_keys:
            if isinstance(api_key, Mapping) and api_key.get("current_key"):
                return str(api_key["current_key"])
    return ""


def _load_mapping(path: Path) -> dict[str, tuple[str, Path]]:
    rows: dict[str, tuple[str, Path]] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        uid, photo_path = line.split("=", 1)
        path_obj = Path(photo_path.strip())
        rows[path_obj.name] = (uid.strip().strip("<>"), path_obj)
    return rows


def _eligible_rows(
    *,
    mapping_file: Path,
    validation_json: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    mapping = _load_mapping(mapping_file)
    validation = _load_json(validation_json)
    eligible: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    for row_index, row in enumerate(validation.get("rows", []), start=1):
        if not isinstance(row, Mapping):
            continue
        photo_file = str(row.get("photoFile") or "")
        uid, photo_path = mapping.get(photo_file, ("", Path("")))
        record = {
            "rowIndex": row_index,
            "uid": uid,
            "rowLineage": _safe_client_request_id(uid, photo_file),
            "photoPath": str(photo_path),
            "photoFile": photo_file,
            "eligibleForUpload": row.get("eligibleForUpload") is True,
            "blockers": list(row.get("blockers") or []),
        }
        if record["eligibleForUpload"]:
            eligible.append(record)
        else:
            blocked.append(
                {
                    "rowIndex": row_index,
                    "rowLineage": record["rowLineage"],
                    "blockers": record["blockers"],
                }
            )
    return eligible, blocked


def _load_auth_secrets(paths: list[Path]) -> list[Mapping[str, Any]]:
    return load_auth_secret_users(paths, load_json=_load_json)

def _post_json(
    url: str,
    payload: Mapping[str, Any],
    *,
    token: str = "",
    app_check_token: str = "",
    timeout_seconds: int = 120,
) -> tuple[int, Mapping[str, Any], str]:
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if app_check_token:
        headers["X-Firebase-AppCheck"] = app_check_token
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


def _auth_tokens_by_uid(api_key: str, secret_paths: list[Path]) -> dict[str, str]:
    tokens: dict[str, str] = {}
    if not api_key:
        return tokens
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={api_key}"
    for item in _load_auth_secrets(secret_paths):
        email = str(item.get("email") or "")
        password = str(item.get("password") or "")
        if not email or not password:
            continue
        status, parsed, _ = _post_json(
            url,
            {"email": email, "password": password, "returnSecureToken": True},
            timeout_seconds=60,
        )
        if status == 200 and parsed.get("localId") and parsed.get("idToken"):
            tokens[str(parsed["localId"])] = str(parsed["idToken"])
    return tokens


def _safe_response(value: Mapping[str, Any]) -> bool:
    text = json.dumps(value, ensure_ascii=False, default=str)
    return not any(marker in text for marker in FORBIDDEN_RESPONSE_MARKERS)


def _payload_level(size_bytes: int | None) -> str:
    if size_bytes is None:
        return "unknown"
    if size_bytes > 20 * 1024 * 1024:
        return "critical"
    if size_bytes > 8 * 1024 * 1024:
        return "warning"
    return "ok"


def _firestore_client(project: str):
    try:
        from google.cloud import firestore
    except Exception as exc:  # pragma: no cover - environment dependent
        raise RuntimeError("google-cloud-firestore is required") from exc
    return firestore.Client(project=project)


def _private_source_count(db: Any, uid: str) -> int:
    data = db.collection("userPrivateMedia").document(uid).get().to_dict() or {}
    photos = data.get("sourcePhotos")
    return len(photos) if isinstance(photos, list) else 0


def _job_count(db: Any, uid: str) -> int:
    return sum(1 for _ in db.collection("avatarJobs").where("uid", "==", uid).stream())


def _candidate_counts(db: Any, job_id: str) -> dict[str, int]:
    counts = {
        "candidateCount": 0,
        "previewCount": 0,
        "hardPassCount": 0,
        "softPassCount": 0,
        "needsReviewCount": 0,
        "hardRejectCount": 0,
        "tooIdentifiableCount": 0,
        "childlikeRiskCount": 0,
        "beautificationRiskCount": 0,
        "modelUnavailableCount": 0,
        "childlikeRiskValues": _empty_risk_value_counts(),
        "beautificationRiskValues": _empty_risk_value_counts(),
    }
    for snapshot in db.collection("avatarCandidates").where("jobId", "==", job_id).stream():
        candidate = snapshot.to_dict() or {}
        qa = candidate.get("qa") if isinstance(candidate.get("qa"), Mapping) else {}
        rerank = candidate.get("rerank") if isinstance(candidate.get("rerank"), Mapping) else {}
        tier = (
            rerank.get("selectionTier")
            or qa.get("selectionTier")
            or candidate.get("selectionTier")
            or candidate.get("status")
        )
        counts["candidateCount"] += 1
        if (
            rerank.get("selectedForPreview") is True
            or qa.get("previewAllowed") is True
            or candidate.get("status") in {"preview_ready", "preview"}
        ):
            counts["previewCount"] += 1
        if tier == "hard_pass":
            counts["hardPassCount"] += 1
        elif tier == "soft_pass":
            counts["softPassCount"] += 1
        elif tier == "needs_review":
            counts["needsReviewCount"] += 1
        elif tier in {"hard_reject", "rejected"}:
            counts["hardRejectCount"] += 1
        reason_text = json.dumps({"qa": qa, "rerank": rerank}, ensure_ascii=False)
        if "too_identifiable" in reason_text:
            counts["tooIdentifiableCount"] += 1
        _add_risk_value(counts["childlikeRiskValues"], qa, "childlikeRisk")
        _add_risk_value(counts["beautificationRiskValues"], qa, "beautificationRisk")
        if _risk_value_is_high(qa.get("childlikeRisk") if "childlikeRisk" in qa else None, "childlikeRisk" in qa):
            counts["childlikeRiskCount"] += 1
        if _risk_value_is_high(qa.get("beautificationRisk") if "beautificationRisk" in qa else None, "beautificationRisk" in qa):
            counts["beautificationRiskCount"] += 1
        if _qa_model_unavailable(qa):
            counts["modelUnavailableCount"] += 1
    return counts


def _empty_risk_value_counts() -> dict[str, int]:
    return {
        "trueCount": 0,
        "falseCount": 0,
        "nullCount": 0,
        "missingCount": 0,
        "stringLowCount": 0,
        "stringMediumCount": 0,
        "stringHighCount": 0,
        "stringUnknownCount": 0,
        "stringUnavailableCount": 0,
        "stringOtherCount": 0,
    }


def _add_risk_value(counts: dict[str, int], qa: Mapping[str, Any], key: str) -> None:
    present = key in qa
    bucket = _risk_value_bucket(qa.get(key) if present else None, present=present)
    counts[bucket] = int(counts.get(bucket) or 0) + 1


def _risk_value_bucket(value: Any, *, present: bool) -> str:
    if not present:
        return "missingCount"
    if value is None:
        return "nullCount"
    if value is True:
        return "trueCount"
    if value is False:
        return "falseCount"
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"high", "critical", "fail", "failed", "reject", "rejected"}:
            return "stringHighCount"
        if normalized in {"medium", "review", "needs_review", "uncertain"}:
            return "stringMediumCount"
        if normalized in {"low", "none", "pass", "passed", "ok", "clear"}:
            return "stringLowCount"
        if normalized in {"unknown", ""}:
            return "stringUnknownCount"
        if normalized in {"unavailable", "critical_unavailable", "uncalibrated"}:
            return "stringUnavailableCount"
        return "stringOtherCount"
    return "stringOtherCount"


def _risk_value_is_high(value: Any, present: bool) -> bool:
    return _risk_value_bucket(value, present=present) in {"trueCount", "stringHighCount"}


def _qa_model_unavailable(qa: Mapping[str, Any]) -> bool:
    qa_version = str(qa.get("qaVersion") or "").strip().lower()
    if "model_unavailable" in qa_version:
        return True
    for reason in qa.get("reviewReasons") or ():
        lowered = str(reason or "").strip().lower()
        if lowered == "model_unavailable" or lowered.endswith("_unavailable"):
            return True
    debug = qa.get("debug")
    if not isinstance(debug, Mapping):
        return False
    model_availability = debug.get("modelAvailability")
    if not isinstance(model_availability, Mapping):
        return False
    unavailable = {"unavailable", "critical_unavailable", "uncalibrated"}
    return any(str(value or "").strip().lower() in unavailable for value in model_availability.values())


def _callable_url(project: str, region: str, name: str) -> str:
    return f"https://{region}-{project}.cloudfunctions.net/{name}"


def _callable(
    *,
    project: str,
    region: str,
    name: str,
    data: Mapping[str, Any],
    token: str,
    app_check_token: str,
) -> tuple[int, Mapping[str, Any], str]:
    return _post_json(
        _callable_url(project, region, name),
        {"data": data},
        token=token,
        app_check_token=app_check_token,
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_one(
    *,
    db: Any,
    project: str,
    region: str,
    row: Mapping[str, Any],
    token: str,
    app_check_token: str,
    approve: bool,
    lock_retest: bool,
    poll_timeout_seconds: int,
) -> dict[str, Any]:
    # This historical runner cannot satisfy the canonical 2–6-photo source-set
    # admission contract. Keep apply mode side-effect free until it is replaced.
    del db, project, region, token, app_check_token, approve, lock_retest
    del poll_timeout_seconds
    uid = str(row["uid"])
    photo_path = Path(str(row["photoPath"]))
    return {
        "startedAt": _now(),
        "completedAt": _now(),
        "rowIndex": int(row.get("rowIndex") or 0),
        "rowLineage": _safe_client_request_id(uid, photo_path.name),
        "error": "legacy_single_photo_canary_retired",
    }

    uid = str(row["uid"])
    photo_path = Path(str(row["photoPath"]))
    image_bytes = photo_path.read_bytes()
    payload = {
        "imageBase64": base64.b64encode(image_bytes).decode("ascii"),
        "contentType": "image/jpeg",
        "fileName": "avatar-source.jpg",
        "uid": uid,
        "clientRequestId": str(row.get("clientRequestId") or _safe_client_request_id(uid, photo_path.name)),
        "consentVersion": "photo_consent_v4",
        "consentPurposes": {
            "avatarGeneration": True,
            "clipRecommendation": False,
            "sourcePhotoRetention": False,
        },
        "chatPartnerRealPhotoDisclosure": False,
    }
    result: dict[str, Any] = {
        "startedAt": _now(),
        "rowIndex": int(row.get("rowIndex") or 0),
        "rowLineage": _safe_client_request_id(uid, photo_path.name),
        "initialSourceCount": _private_source_count(db, uid),
        "initialJobCount": _job_count(db, uid),
    }
    status, parsed, _ = _callable(
        project=project,
        region=region,
        name="beginAvatarGenerationFromOnboardingPhotos",
        data=payload,
        token=token,
        app_check_token=app_check_token,
    )
    response = parsed.get("result") or parsed.get("data") or parsed
    job_id = str(response.get("jobId") or "")
    result["upload"] = {
        "httpStatus": status,
        "safeResponse": _safe_response(parsed),
        "avatarStatus": response.get("avatarStatus"),
        "message": response.get("message"),
    }
    if status != 200 or not job_id:
        result["completedAt"] = _now()
        result["error"] = "upload_failed"
        return result

    terminal = {"preview_ready", "no_previewable_candidates", "needs_review", "failed", "approved"}
    deadline = time.time() + max(60, poll_timeout_seconds)
    status_history: list[dict[str, Any]] = []
    final_job: Mapping[str, Any] = {}
    while time.time() < deadline:
        job = db.collection("avatarJobs").document(job_id).get().to_dict() or {}
        job_status = str(job.get("status") or "")
        status_history.append(
            {"at": _now(), "status": job_status, "errorCode": job.get("errorCode")}
        )
        final_job = job
        if job_status in terminal:
            if job_status == "failed" and job.get("errorCode") == "avatar_worker_deadline_exceeded":
                time.sleep(30)
                continue
            break
        time.sleep(15)

    result["job"] = {
        "status": final_job.get("status"),
        "errorCode": final_job.get("errorCode"),
        "generationPlan": final_job.get("generationPlan") or {},
        "cost": final_job.get("cost") or {},
    }
    result["statusHistory"] = status_history[-30:]
    result["candidateStats"] = _candidate_counts(db, job_id)

    if final_job.get("status") == "preview_ready":
        preview_status, preview_parsed, preview_text = _callable(
            project=project,
            region=region,
            name="getAvatarJobCandidates",
            data={"jobId": job_id},
            token=token,
            app_check_token=app_check_token,
        )
        preview_data = preview_parsed.get("result") or preview_parsed.get("data") or preview_parsed
        candidates = preview_data.get("candidates") if isinstance(preview_data, Mapping) else []
        if not isinstance(candidates, list):
            candidates = []
        response_bytes = len(preview_text.encode("utf-8"))
        result["previewApi"] = {
            "httpStatus": preview_status,
            "safeResponse": _safe_response(preview_parsed),
            "responseBytesApprox": response_bytes,
            "payloadLevel": _payload_level(response_bytes),
            "candidateCount": len(candidates),
            "perCandidateBase64Length": [
                len(str(candidate.get("previewImageBase64") or ""))
                for candidate in candidates
                if isinstance(candidate, Mapping)
            ],
        }
        if approve and preview_status == 200 and candidates:
            candidate_id = str(candidates[0].get("candidateId") or "")
            approve_status, approve_parsed, _ = _callable(
                project=project,
                region=region,
                name="approveAvatarCandidate",
                data={"candidateId": candidate_id},
                token=token,
                app_check_token=app_check_token,
            )
            user = db.collection("users").document(uid).get().to_dict() or {}
            avatar = user.get("avatar") if isinstance(user.get("avatar"), Mapping) else {}
            onboarding = user.get("onboarding") if isinstance(user.get("onboarding"), Mapping) else {}
            result["approval"] = {
                "httpStatus": approve_status,
                "safeResponse": _safe_response(approve_parsed),
                "avatarStatus": avatar.get("status"),
                "approvedAvatarUrlPresent": bool(avatar.get("approvedAvatarUrl")),
                "onboardingAvatarUrlsCount": len(onboarding.get("avatarUrls") or []),
            }
            if lock_retest and approve_status == 200:
                before_sources = _private_source_count(db, uid)
                before_jobs = _job_count(db, uid)
                lock_status, lock_parsed, _ = _callable(
                    project=project,
                    region=region,
                    name="beginAvatarGenerationFromOnboardingPhotos",
                    data=payload,
                    token=token,
                    app_check_token=app_check_token,
                )
                result["lockRetest"] = {
                    "httpStatus": lock_status,
                    "safeResponse": _safe_response(lock_parsed),
                    "rejected": lock_status >= 400,
                    "sourceCountBefore": before_sources,
                    "sourceCountAfter": _private_source_count(db, uid),
                    "jobCountBefore": before_jobs,
                    "jobCountAfter": _job_count(db, uid),
                    "errorMessage": (
                        (lock_parsed.get("error") or {}).get("message")
                        if isinstance(lock_parsed, Mapping)
                        else ""
                    ),
                }
    result["completedAt"] = _now()
    return result


def build_dry_run_report(
    *,
    eligible: list[dict[str, Any]],
    blocked: list[dict[str, Any]],
    min_users: int,
) -> dict[str, Any]:
    status = "READY"
    if len(eligible) < min_users:
        status = "BLOCKED_MIN_ELIGIBLE"
    return {
        "generatedAt": _now(),
        "dryRun": True,
        "status": status,
        "eligibleCount": len(eligible),
        "requiredMinUsers": min_users,
        "eligible": [
            {"rowIndex": int(row.get("rowIndex") or 0), "rowLineage": row["rowLineage"]}
            for row in eligible
        ],
        "blocked": _sanitized_blocked_rows(blocked),
    }


def _sanitized_blocked_rows(rows: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "rowIndex": int(row.get("rowIndex") or 0),
            "rowLineage": str(row.get("rowLineage") or ""),
            "blockers": list(row.get("blockers") or []),
        }
        for row in rows
    ]


def _sanitized_report_job(job: Mapping[str, Any]) -> dict[str, Any]:
    sanitized = dict(job)
    for key in ("photoFile", "photoPath", "fileName"):
        sanitized.pop(key, None)
    return sanitized


def _sanitize_operator_report(
    report: dict[str, Any],
    *,
    full_eligible_count: int,
) -> dict[str, Any]:
    report["operatorAuthorizedExactReplay"] = True
    report["fullEligibleCount"] = full_eligible_count
    report["approvalSkipped"] = True
    for key in ("eligible", "blocked", "jobs"):
        rows = report.get(key)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if isinstance(row, dict):
                row.pop("rowLineage", None)
                row.pop("photoFile", None)
                row.pop("photoPath", None)
                row.pop("uidHash", None)
                row.pop("imageSha256Prefix", None)
                row.pop("expectedPhotoSha256", None)
    return report

def _job_error_count(jobs: list[Mapping[str, Any]]) -> int:
    return sum(1 for job in jobs if isinstance(job, Mapping) and job.get("error"))


def _has_unsafe_response(value: Any) -> bool:
    if isinstance(value, Mapping):
        if value.get("safeResponse") is False:
            return True
        return any(_has_unsafe_response(item) for item in value.values())
    if isinstance(value, list):
        return any(_has_unsafe_response(item) for item in value)
    return False


def _mark_unsafe_response_errors(jobs: list[dict[str, Any]]) -> int:
    violation_count = 0
    for job in jobs:
        if not isinstance(job, dict) or not _has_unsafe_response(job):
            continue
        violation_count += 1
        job.setdefault("error", "unsafe_callable_response")
    return violation_count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run avatar canary for rows already validated as eligible."
    )
    parser.add_argument("--project", default="seolleyeon-final")
    parser.add_argument("--region", default="asia-northeast3")
    parser.add_argument("--mapping_file", required=True)
    parser.add_argument("--validation_json", required=True)
    parser.add_argument("--output_json", required=True)
    parser.add_argument("--operator_authorized_exact_replay", action="store_true")
    parser.add_argument("--operator_admin_custom_tokens", action="store_true")
    parser.add_argument("--expected_mapping_sha256", default="")
    parser.add_argument("--consent_file", default="")
    parser.add_argument("--prior_report_json", default="")
    parser.add_argument("--operator_replay_id", default="")
    parser.add_argument("--row_start", type=int, default=0)
    parser.add_argument("--row_limit", type=int, default=7)
    parser.add_argument("--api_key", default="")
    parser.add_argument("--google_services_json", default="")
    parser.add_argument("--auth_secret_json", action="append", default=[])
    parser.add_argument("--app_check_token_file", default="")
    parser.add_argument("--app_check_debug_token_file", default="")
    parser.add_argument("--app_check_project_number", default="")
    parser.add_argument("--app_check_app_id", default="")
    parser.add_argument("--min_users", type=int, default=3)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--allow_partial", action="store_true")
    parser.add_argument("--skip_approval", action="store_true")
    parser.add_argument("--skip_lock_retest", action="store_true")
    parser.add_argument("--poll_timeout_seconds", type=int, default=1500)
    args = parser.parse_args(argv)

    output_path = Path(args.output_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    full_eligible_count = 0
    if args.operator_authorized_exact_replay:
        try:
            if args.project != "seolleyeon-final":
                raise ValueError("operator_exact_replay_project_mismatch")
            if not args.skip_approval:
                raise ValueError("operator_exact_replay_requires_skip_approval")
            if not args.operator_replay_id:
                raise ValueError("operator_exact_replay_id_required")
            if not args.consent_file or not args.prior_report_json:
                raise ValueError("operator_exact_replay_evidence_required")
            eligible, full_eligible_count = _operator_exact_replay_rows(
                mapping_file=Path(args.mapping_file),
                consent_file=Path(args.consent_file),
                validation_json=Path(args.validation_json),
                prior_report_json=Path(args.prior_report_json),
                expected_mapping_sha256=args.expected_mapping_sha256,
                row_start=args.row_start,
                row_limit=args.row_limit,
            )
            _, blocked = _eligible_rows(
                mapping_file=Path(args.mapping_file),
                validation_json=Path(args.validation_json),
            )
            for row in eligible:
                row["clientRequestId"] = _operator_replay_client_request_id(
                    str(row["uid"]),
                    str(row["photoFile"]),
                    mapping_sha256=args.expected_mapping_sha256,
                    replay_id=args.operator_replay_id,
                )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            blocker = str(exc) if isinstance(exc, ValueError) else "operator_exact_replay_evidence_unreadable"
            report = _sanitize_operator_report(
                {
                    "generatedAt": _now(),
                    "dryRun": not args.apply,
                    "status": "BLOCKED_OPERATOR_EXACT_REPLAY_NO_UPLOAD",
                    "eligibleCount": 0,
                    "requiredMinUsers": args.min_users,
                    "blockers": [blocker],
                },
                full_eligible_count=0,
            )
            output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps({"status": report["status"], "eligibleCount": 0}))
            return 1
    else:
        eligible, blocked = _eligible_rows(
            mapping_file=Path(args.mapping_file),
            validation_json=Path(args.validation_json),
        )
        full_eligible_count = len(eligible)
    if not args.apply:
        report = build_dry_run_report(
            eligible=eligible,
            blocked=blocked,
            min_users=args.min_users,
        )
        if args.operator_authorized_exact_replay:
            report = _sanitize_operator_report(
                report,
                full_eligible_count=full_eligible_count,
            )
        output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(
            json.dumps(
                {
                    "output": str(output_path.resolve()),
                    "status": report["status"],
                    "eligibleCount": report["eligibleCount"],
                },
                ensure_ascii=False,
            )
        )
        return 0

    if len(eligible) < args.min_users and not args.allow_partial:
        report = build_dry_run_report(
            eligible=eligible,
            blocked=blocked,
            min_users=args.min_users,
        )
        report["dryRun"] = False
        report["status"] = "BLOCKED_MIN_ELIGIBLE_NO_UPLOAD"
        if args.operator_authorized_exact_replay:
            report = _sanitize_operator_report(
                report,
                full_eligible_count=full_eligible_count,
            )
        output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(
            json.dumps(
                {
                    "output": str(output_path.resolve()),
                    "status": report["status"],
                    "eligibleCount": len(eligible),
                },
                ensure_ascii=False,
            )
        )
        return 0

    api_key = args.api_key or _api_key_from_google_services(Path(args.google_services_json))
    app_check_token = (
        _load_app_check_token(Path(args.app_check_token_file))
        if args.app_check_token_file
        else ""
    )
    app_check_exchange_status = 0
    debug_token = (
        _load_app_check_token(Path(args.app_check_debug_token_file))
        if args.app_check_debug_token_file
        else ""
    )
    if not app_check_token and debug_token:
        app_check_exchange_status, app_check_token = _exchange_app_check_debug_token(
            project_number=args.app_check_project_number,
            app_id=args.app_check_app_id,
            api_key=api_key,
            debug_token=debug_token,
        )
    if not app_check_token:
        report = build_dry_run_report(
            eligible=eligible,
            blocked=blocked,
            min_users=args.min_users,
        )
        report["dryRun"] = False
        report["status"] = (
            "BLOCKED_APPCHECK_TOKEN_EXCHANGE_FAILED_NO_UPLOAD"
            if debug_token
            else "BLOCKED_MISSING_APPCHECK_TOKEN_NO_UPLOAD"
        )
        report["appCheckTokenConfigured"] = False
        report["appCheckExchangeHttpStatus"] = app_check_exchange_status
        if args.operator_authorized_exact_replay:
            report = _sanitize_operator_report(
                report,
                full_eligible_count=full_eligible_count,
            )
        output_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(
            json.dumps(
                {
                    "output": str(output_path.resolve()),
                    "status": report["status"],
                    "eligibleCount": len(eligible),
                },
                ensure_ascii=False,
            )
        )
        return 1

    db = _firestore_client(args.project)
    tokens: dict[str, str] = {}
    auth_mod = None
    admin_app = None
    if args.operator_admin_custom_tokens:
        if not args.operator_authorized_exact_replay or args.project != "seolleyeon-final":
            report = {
                "generatedAt": _now(),
                "dryRun": False,
                "status": "BLOCKED_OPERATOR_CUSTOM_TOKEN_NO_UPLOAD",
                "eligibleCount": 0,
                "requiredMinUsers": args.min_users,
                "blockers": ["operator_custom_token_scope_mismatch"],
            }
            output_path.write_text(
                json.dumps(report, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return 1
        try:
            auth_mod, admin_app = initialize_exact_replay_admin(args.project)
        except (RuntimeError, ValueError):
            report = _sanitize_operator_report(
                {
                    "generatedAt": _now(),
                    "dryRun": False,
                    "status": "BLOCKED_OPERATOR_CUSTOM_TOKEN_NO_UPLOAD",
                    "eligibleCount": len(eligible),
                    "requiredMinUsers": args.min_users,
                    "blockers": ["operator_custom_token_admin_unavailable"],
                },
                full_eligible_count=full_eligible_count,
            )
            output_path.write_text(
                json.dumps(report, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return 1
    else:
        auth_secret_paths = [Path(path) for path in args.auth_secret_json] or list(DEFAULT_AUTH_SECRET_PATHS)
        tokens = _auth_tokens_by_uid(api_key, auth_secret_paths)

    jobs = []
    for row in eligible:
        uid = str(row["uid"])
        token = ""
        preupload_gate: dict[str, Any] | None = None
        if args.operator_admin_custom_tokens:
            try:
                preupload_gate = validate_exact_replay_preupload(
                    project=args.project,
                    db=db,
                    auth_mod=auth_mod,
                    admin_app=admin_app,
                    row=row,
                )
                token = mint_exact_replay_id_token(
                    project=args.project,
                    uid=uid,
                    api_key=api_key,
                    auth_mod=auth_mod,
                    admin_app=admin_app,
                    post_json=_post_json,
                )
                preupload_gate["customTokenCreated"] = True
                preupload_gate["idTokenExchange"] = True
                preupload_gate["decodedUidMatched"] = True
            except ValueError as exc:
                error_code = str(exc)
                if not error_code.startswith("operator_custom_token_"):
                    error_code = "operator_custom_token_preupload_failed"
                jobs.append(
                    {
                        "rowIndex": int(row.get("rowIndex") or 0),
                        "rowLineage": row["rowLineage"],
                        "error": error_code,
                    }
                )
                continue
        else:
            token = tokens.get(uid, "")
            if not token:
                jobs.append(
                    {
                        "rowIndex": int(row.get("rowIndex") or 0),
                        "rowLineage": row["rowLineage"],
                        "error": "missing_auth_token",
                    }
                )
                continue
        try:
            job = _sanitized_report_job(
                _run_one(
                    db=db,
                    project=args.project,
                    region=args.region,
                    row=row,
                    token=token,
                    app_check_token=app_check_token,
                    approve=not args.skip_approval,
                    lock_retest=not args.skip_lock_retest,
                    poll_timeout_seconds=args.poll_timeout_seconds,
                )
            )
            if preupload_gate is not None:
                job["preUploadGate"] = preupload_gate
            jobs.append(job)
        finally:
            token = ""
    tokens.clear()

    response_safety_violation_count = _mark_unsafe_response_errors(jobs)
    job_error_count = _job_error_count(jobs)
    report = {
        "generatedAt": _now(),
        "dryRun": False,
        "status": "COMPLETE_WITH_ERRORS" if job_error_count else "COMPLETE",
        "eligibleCount": len(eligible),
        "requiredMinUsers": args.min_users,
        "jobErrorCount": job_error_count,
        "responseSafetyViolationCount": response_safety_violation_count,
        "appCheckTokenConfigured": True,
        "appCheckExchangeHttpStatus": app_check_exchange_status,
        "blocked": _sanitized_blocked_rows(blocked),
        "jobs": jobs,
    }
    if args.operator_authorized_exact_replay:
        report = _sanitize_operator_report(
            report,
            full_eligible_count=full_eligible_count,
        )
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(output_path.resolve()),
                "status": report["status"],
                "jobCount": len(jobs),
            },
            ensure_ascii=False,
        )
    )
    return 1 if job_error_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
