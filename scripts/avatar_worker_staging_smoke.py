from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence
from urllib.error import HTTPError

REPO_ROOT = Path(__file__).resolve().parents[1]
AI_MODEL_DIR = REPO_ROOT / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

from avatar_generation import FLUX2_KLEIN_MODEL_ID
from avatar_generation.worker import (
    AvatarGenerationError,
    parse_gcs_uri,
    process_avatar_generation_payload,
    redact_gcs_ref,
)

from avatar_worker_smoke_test import _fake_firestore, _fake_storage, _smoke_qa


def _payload(args: argparse.Namespace) -> Dict[str, Any]:
    return {
        "jobId": args.job_id,
        "uid": args.uid,
        "sourcePhotoIds": ["smoke_source_001"],
        "sourcePhotoRefs": [args.source_gcs_uri],
        "candidateCount": args.candidate_count,
        "modelId": FLUX2_KLEIN_MODEL_ID,
        "jobType": "avatar_generation",
        "schemaVersion": "avatar_job_v1",
        "idempotencyKey": f"{args.uid}:smoke_source_001:avatar_generation_v1",
    }


def _gcloud_id_token(audience: Optional[str]) -> str:
    gcloud = shutil.which("gcloud") or shutil.which("gcloud.cmd")
    if not gcloud:
        raise AvatarGenerationError("gcloud was not found in PATH.")
    command = [gcloud, "auth", "print-identity-token"]
    if audience:
        command.append(f"--audiences={audience}")
    completed = subprocess.run(
        command,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise AvatarGenerationError(completed.stderr.strip() or "gcloud identity token request failed.")
    return completed.stdout.strip()


def _post_json(
    url: str,
    payload: Mapping[str, Any],
    headers: Mapping[str, str],
    *,
    timeout_seconds: int = 120,
) -> Dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", **dict(headers)},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            data = response.read().decode("utf-8")
    except HTTPError as exc:
        data = exc.read(4096).decode("utf-8", errors="replace")
        raise AvatarGenerationError(f"Worker returned HTTP {exc.code}: {data[:500]}") from exc
    decoded = json.loads(data)
    if not isinstance(decoded, dict):
        raise AvatarGenerationError("Worker response was not a JSON object.")
    return decoded


def _get_json(url: str, headers: Mapping[str, str]) -> Dict[str, Any]:
    request = urllib.request.Request(url, headers=dict(headers), method="GET")
    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read().decode("utf-8")
    decoded = json.loads(data)
    if not isinstance(decoded, dict):
        raise AvatarGenerationError("Worker response was not a JSON object.")
    return decoded


def _redacted_report(args: argparse.Namespace, payload: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "status": "started",
        "mode": "real_gpu" if args.real_gpu else "dry_run",
        "workerUrl": args.worker_url or "",
        "jobId": _redacted_identifier("job", payload.get("jobId")),
        "uid": _redacted_identifier("uid", payload.get("uid")),
        "sourceRef": redact_gcs_ref(str(payload.get("sourcePhotoRefs", [""])[0])),
        "candidateCount": int(payload.get("candidateCount") or 0),
    }


def _redacted_identifier(label: str, value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text.startswith(f"{label}:"):
        return text
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
    return f"{label}:{digest}"


def _redact_report_value(key: str, value: Any) -> Any:
    normalized_key = key.lower()
    if normalized_key in {"uid", "userid"}:
        return _redacted_identifier("uid", value)
    if normalized_key == "jobid":
        return _redacted_identifier("job", value)
    if normalized_key in {"candidateid", "selectedcandidateid", "avatarid"}:
        return _redacted_identifier("candidate", value)
    if normalized_key == "candidateids" and isinstance(value, Sequence) and not isinstance(value, str):
        return [_redacted_identifier("candidate", item) for item in value]
    if isinstance(value, Mapping):
        return {
            str(child_key): _redact_report_value(str(child_key), child_value)
            for child_key, child_value in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, str):
        return [_redact_report_value("", item) for item in value]
    return value


def _write_report(report: Mapping[str, Any], path: Optional[str]) -> None:
    safe_report = _redact_report_value("", report)
    encoded = json.dumps(safe_report, ensure_ascii=False, indent=2)
    if path:
        Path(path).write_text(encoded + "\n", encoding="utf-8")
    print(encoded)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Staging smoke test for the Seolleyeon avatar GPU worker.")
    parser.add_argument("--dry_run", action="store_true")
    parser.add_argument("--real_gpu", action="store_true")
    parser.add_argument("--worker_url", default="")
    parser.add_argument("--audience", default="")
    parser.add_argument("--id_token_from_gcloud", action="store_true")
    parser.add_argument(
        "--gcloud_token_without_audience",
        action="store_true",
        help="Use gcloud auth print-identity-token without --audiences for user-account smoke checks.",
    )
    parser.add_argument(
        "--post_task_payload",
        action="store_true",
        help=(
            "Post the synthetic task payload to /tasks/avatar-generation. "
            "For live GPU readiness, the default is /warmup because task payloads "
            "require real Firestore job/private media state."
        ),
    )
    parser.add_argument("--warmup_timeout_seconds", type=int, default=900)
    parser.add_argument("--task_timeout_seconds", type=int, default=900)
    parser.add_argument("--output_report_json")
    parser.add_argument("--job_id", default="avatar_staging_smoke_job")
    parser.add_argument("--uid", default="avatar_staging_smoke_user")
    parser.add_argument(
        "--source_gcs_uri",
        default="gs://seolleyeon-final-private-source-photos/users/avatar_staging_smoke_user/source/smoke_source_001.jpg",
    )
    parser.add_argument("--candidate_count", type=int, default=4)
    parser.add_argument("--skip_trait_extraction", action="store_true")
    parser.add_argument("--force_mock_trait", action="store_true")
    args = parser.parse_args(argv)

    if args.dry_run == args.real_gpu:
        parser.error("Choose exactly one of --dry_run or --real_gpu.")

    payload = _payload(args)
    source_ref = parse_gcs_uri(str(payload["sourcePhotoRefs"][0]))
    os.environ.setdefault("SOURCE_PHOTO_BUCKET", source_ref.bucket)
    if args.skip_trait_extraction:
        os.environ["AVATAR_TRAIT_EXTRACTION_ENABLED"] = "false"
    if args.force_mock_trait:
        os.environ["AVATAR_TRAIT_EXTRACTION_ENABLED"] = "true"
        os.environ["AVATAR_TRAIT_DRY_RUN"] = "true"
    report = _redacted_report(args, payload)
    headers: Dict[str, str] = {}
    try:
        if args.id_token_from_gcloud:
            audience = None if args.gcloud_token_without_audience else args.audience or args.worker_url
            if not audience and not args.gcloud_token_without_audience:
                raise AvatarGenerationError("--audience or --worker_url is required with --id_token_from_gcloud.")
            headers["Authorization"] = f"Bearer {_gcloud_id_token(audience)}"

        if args.worker_url:
            base_url = args.worker_url.rstrip("/")
            report["readyz"] = _get_json(f"{base_url}/readyz", headers)
            if args.real_gpu and not args.post_task_payload:
                report["warmup"] = _post_json(
                    f"{base_url}/warmup",
                    {},
                    headers,
                    timeout_seconds=args.warmup_timeout_seconds,
                )
                report["result"] = {
                    "status": "warmup_completed",
                    "taskPayloadPosted": False,
                }
            else:
                endpoint = f"{base_url}/tasks/avatar-generation"
                report["result"] = _post_json(
                    endpoint,
                    payload,
                    headers,
                    timeout_seconds=args.task_timeout_seconds,
                )
        else:
            mode = "flux" if args.real_gpu else "dry_run"
            with tempfile.TemporaryDirectory(prefix="avatar-staging-smoke-") as temp_dir:
                fake_storage = _fake_storage(payload)

                def qa_runner(source_ref: str, candidate_ref: str, metadata: Dict[str, Any]):
                    qa_metadata = dict(metadata)
                    qa_metadata["_storage_client"] = fake_storage
                    return _smoke_qa(source_ref, candidate_ref, qa_metadata)

                result = process_avatar_generation_payload(
                    payload,
                    firestore_client=_fake_firestore(payload),
                    storage_client=fake_storage,
                    qa_runner=qa_runner,
                    mode=mode,
                    fixture_output_dir=Path(temp_dir) if args.dry_run else None,
                )
            report["result"] = result.to_dict()
        report["status"] = "ok"
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = str(exc)[:240]
        _write_report(report, args.output_report_json)
        return 1

    _write_report(report, args.output_report_json)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
