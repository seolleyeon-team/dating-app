from __future__ import annotations

import argparse
import base64
import hashlib
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


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


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


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
    for row in validation.get("rows", []):
        if not isinstance(row, Mapping):
            continue
        photo_file = str(row.get("photoFile") or "")
        uid, photo_path = mapping.get(photo_file, ("", Path("")))
        record = {
            "uid": uid,
            "uidHash": f"uid:{_hash_text(uid)}",
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
                    "uidHash": record["uidHash"],
                    "photoFile": photo_file,
                    "blockers": record["blockers"],
                }
            )
    return eligible, blocked


def _load_auth_secrets(paths: list[Path]) -> list[Mapping[str, Any]]:
    users: list[Mapping[str, Any]] = []
    for path in paths:
        if not path.is_file():
            continue
        payload = _load_json(path)
        for label, entry in (payload.get("users") or {}).items():
            if isinstance(entry, Mapping):
                item = dict(entry)
                item["label"] = str(label)
                users.append(item)
    return users


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
        if "childlike" in reason_text or "babyface" in reason_text:
            counts["childlikeRiskCount"] += 1
        if "beautification" in reason_text or "beauty" in reason_text:
            counts["beautificationRiskCount"] += 1
    return counts


def _callable_url(project: str, region: str, name: str) -> str:
    return f"https://{region}-{project}.cloudfunctions.net/{name}"


def _callable(
    *,
    project: str,
    region: str,
    name: str,
    data: Mapping[str, Any],
    token: str,
) -> tuple[int, Mapping[str, Any], str]:
    return _post_json(_callable_url(project, region, name), {"data": data}, token=token)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_one(
    *,
    db: Any,
    project: str,
    region: str,
    row: Mapping[str, Any],
    token: str,
    approve: bool,
    lock_retest: bool,
    poll_timeout_seconds: int,
) -> dict[str, Any]:
    uid = str(row["uid"])
    photo_path = Path(str(row["photoPath"]))
    image_bytes = photo_path.read_bytes()
    payload = {
        "imageBase64": base64.b64encode(image_bytes).decode("ascii"),
        "contentType": "image/jpeg",
        "fileName": photo_path.name,
        "uid": uid,
        "chatPartnerRealPhotoDisclosure": False,
    }
    result: dict[str, Any] = {
        "startedAt": _now(),
        "uidHash": f"uid:{_hash_text(uid)}",
        "photoFile": photo_path.name,
        "imageSha256Prefix": hashlib.sha256(image_bytes).hexdigest()[:12],
        "initialSourceCount": _private_source_count(db, uid),
        "initialJobCount": _job_count(db, uid),
    }
    status, parsed, _ = _callable(
        project=project,
        region=region,
        name="uploadAvatarSourcePhoto",
        data=payload,
        token=token,
    )
    response = parsed.get("result") or parsed.get("data") or parsed
    job_id = str(response.get("jobId") or "")
    result["upload"] = {
        "httpStatus": status,
        "safeResponse": _safe_response(parsed),
        "jobIdHash": _hash_text(job_id),
        "photoIdHash": _hash_text(response.get("photoId")),
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
        "jobIdHash": _hash_text(job_id),
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
                    name="uploadAvatarSourcePhoto",
                    data=payload,
                    token=token,
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
            {"uidHash": row["uidHash"], "photoFile": row["photoFile"]}
            for row in eligible
        ],
        "blocked": blocked,
    }


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
    parser.add_argument("--api_key", default="")
    parser.add_argument("--google_services_json", default="")
    parser.add_argument("--auth_secret_json", action="append", default=[])
    parser.add_argument("--min_users", type=int, default=3)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--allow_partial", action="store_true")
    parser.add_argument("--skip_approval", action="store_true")
    parser.add_argument("--skip_lock_retest", action="store_true")
    parser.add_argument("--poll_timeout_seconds", type=int, default=1500)
    args = parser.parse_args(argv)

    output_path = Path(args.output_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    eligible, blocked = _eligible_rows(
        mapping_file=Path(args.mapping_file),
        validation_json=Path(args.validation_json),
    )
    if not args.apply:
        report = build_dry_run_report(
            eligible=eligible,
            blocked=blocked,
            min_users=args.min_users,
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
    auth_secret_paths = [Path(path) for path in args.auth_secret_json] or list(DEFAULT_AUTH_SECRET_PATHS)
    tokens = _auth_tokens_by_uid(api_key, auth_secret_paths)
    db = _firestore_client(args.project)
    jobs = []
    for row in eligible:
        uid = str(row["uid"])
        token = tokens.get(uid)
        if not token:
            jobs.append(
                {
                    "uidHash": row["uidHash"],
                    "photoFile": row["photoFile"],
                    "error": "missing_auth_token",
                }
            )
            continue
        jobs.append(
            _run_one(
                db=db,
                project=args.project,
                region=args.region,
                row=row,
                token=token,
                approve=not args.skip_approval,
                lock_retest=not args.skip_lock_retest,
                poll_timeout_seconds=args.poll_timeout_seconds,
            )
        )

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
        "blocked": blocked,
        "jobs": jobs,
    }
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
