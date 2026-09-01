"""Recover G004 QA evidence from an already-generated private review bundle."""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import re
import sys
from typing import Any, Mapping
from urllib.parse import urlsplit

import httpx


REPO_ROOT = Path(__file__).resolve().parents[1]
AI_MODEL_DIR = REPO_ROOT / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

from avatar_generation.calibration_operator import (  # noqa: E402
    CalibrationOperatorError,
    GcloudStorageGateway,
    assert_redacted_calibration_report,
    delete_staged_recovery_candidates,
    enrich_manifest_source_generations,
    stage_local_review_bundle_for_recovery,
)
from avatar_generation.calibration_recovery import (  # noqa: E402
    CALIBRATION_RECOVERY_REQUEST_SCHEMA,
    CALIBRATION_RECOVERY_EVALUATION_SUFFIX,
)
from avatar_generation.analysis.watermark import WATERMARK_POLICY_VERSION  # noqa: E402
from avatar_generation.calibration_evaluator import CALIBRATION_EVALUATION_VERSION  # noqa: E402
from avatar_generation.qa import QA_CONTRACT_VERSION  # noqa: E402


EXPECTED_RUN_ID = "G004-AZURE-CAL-20260824-001"
DEFAULT_PROJECT = "seolleyeon-final"
DEFAULT_TEMP_BUCKET = "seolleyeon-final-avatar-temp"
DEFAULT_SERVICE = "seolleyeon-avatar-worker"
DEFAULT_REGION = "asia-southeast1"
DEFAULT_TAG = "g4-rec-0824"
EXPECTED_PARTICIPANTS = 5
EXPECTED_CANDIDATES_PER_PARTICIPANT = 4
EXPECTED_CANDIDATES = 20
OPERATOR_RECOVERY_EVALUATION_SUFFIX = "QA-RECOVERY-3"
_IMAGE_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_ACCEPTED_VERSION_BUNDLES = {
    # Current recovery output.
    (QA_CONTRACT_VERSION, WATERMARK_POLICY_VERSION, CALIBRATION_EVALUATION_VERSION),
    # Historical v9 evidence remains readable and immutable after the policy bump.
    (
        "avatar_qa_v3_watermark_evidence_v1",
        "watermark_policy_v2_source_consistency_v1",
        "g004_calibration_evaluation_v2_watermark_evidence",
    ),
}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--review-root", type=Path, required=True)
    parser.add_argument("--original-server-duration-seconds", type=float, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=1800.0)
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--temp-bucket", default=DEFAULT_TEMP_BUCKET)
    parser.add_argument("--service", default=DEFAULT_SERVICE)
    parser.add_argument("--region", default=DEFAULT_REGION)
    parser.add_argument("--tag", default=DEFAULT_TAG)
    parser.add_argument("--parent-recovery-id")
    parser.add_argument("--worker-image-digest", required=True)
    return parser


def _service_url(gateway: GcloudStorageGateway, args: argparse.Namespace) -> str:
    value = os.environ.get("AVATAR_CALIBRATION_SERVICE_URL", "").strip().rstrip("/")
    if not value:
        return gateway.cloud_run_tag_url(
            service=args.service,
            region=args.region,
            project=args.project,
            tag=args.tag,
        )
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or not parsed.hostname.endswith(".run.app")
        or parsed.username
        or parsed.password
        or parsed.port
        or parsed.query
        or parsed.fragment
    ):
        raise CalibrationOperatorError("operator_service_url_invalid")
    return value


def _read_manifest(path: Path, *, expected_project: str) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise CalibrationOperatorError("operator_manifest_invalid") from exc
    if not isinstance(value, Mapping) or str(value.get("projectId") or "") != expected_project:
        raise CalibrationOperatorError("operator_manifest_project_invalid")
    return value


def _private_values(manifest: Mapping[str, Any]) -> tuple[str, ...]:
    values: list[str] = []
    participants = manifest.get("participants")
    if isinstance(participants, list):
        for participant in participants:
            if not isinstance(participant, Mapping):
                continue
            values.extend(
                str(participant.get(key) or "").strip()
                for key in ("uid", "sourcePhotoRef")
            )
    return tuple(value for value in values if value)


def _post_once(
    *,
    service_url: str,
    token: str,
    request_body: Mapping[str, Any],
    timeout_seconds: float,
) -> Mapping[str, Any]:
    try:
        response = httpx.post(
            f"{service_url}/internal/g004-calibration-recovery",
            headers={"Authorization": f"Bearer {token}"},
            json=request_body,
            timeout=httpx.Timeout(max(1.0, float(timeout_seconds))),
            follow_redirects=False,
        )
    except Exception as exc:
        # No generation occurs on this route. Preserve staged candidates so a
        # QA-only retry remains possible after an unknown HTTP outcome.
        raise CalibrationOperatorError("operator_recovery_http_unknown_outcome") from exc
    try:
        payload = response.json()
    except Exception as exc:
        raise CalibrationOperatorError("operator_recovery_http_response_invalid") from exc
    if not isinstance(payload, Mapping):
        raise CalibrationOperatorError("operator_recovery_http_response_invalid")
    if response.status_code != 200:
        code = str(payload.get("errorCode") or "operator_recovery_remote_rejected").strip()
        if not code or not code.replace("_", "").isalnum():
            code = "operator_recovery_remote_rejected"
        raise CalibrationOperatorError(code)
    return payload


def _validate_recovery_report(report: Mapping[str, Any]) -> None:
    recovery = report.get("recovery")
    recovery_value = recovery if isinstance(recovery, Mapping) else {}
    review = report.get("reviewArtifacts")
    review_value = review if isinstance(review, Mapping) else {}
    rows_value = report.get("qaEvaluation")
    rows_container = rows_value if isinstance(rows_value, Mapping) else {}
    rows = rows_container.get("rows")
    row_list = rows if isinstance(rows, list) else []
    valid = bool(
        report.get("status") == "completed"
        and report.get("nextState") == "HUMAN_REVIEW_REQUIRED"
        and report.get("evaluationId")
        == f"{EXPECTED_RUN_ID}-{CALIBRATION_RECOVERY_EVALUATION_SUFFIX}"
        and report.get("participantCount") == EXPECTED_PARTICIPANTS
        and report.get("participantOrdinals")
        == [f"P{index:02d}" for index in range(1, EXPECTED_PARTICIPANTS + 1)]
        and report.get("candidateCount") == EXPECTED_CANDIDATES
        and report.get("azureCallCount") == EXPECTED_CANDIDATES
        and report.get("retryCount") == 0
        and report.get("generationCallsPerformedByRecovery") == 0
            and (
                report.get("qaEvaluationVersion"),
                report.get("watermarkPolicyVersion"),
                report.get("calibrationEvaluationVersion"),
            )
            in _ACCEPTED_VERSION_BUNDLES
        and isinstance(report.get("thresholdSnapshot"), Mapping)
        and isinstance(report.get("calibrationArtifactIntegrity"), str)
        and isinstance(report.get("gitRevision"), str)
        and report.get("previewSideEffects") == 0
        and report.get("approvalSideEffects") == 0
        and report.get("publicProjectionSideEffects") == 0
        and report.get("rawImagePersistence") == 0
        and report.get("rawBiometricPersistence") == 0
        and recovery_value.get("candidatePreflightCount") == EXPECTED_CANDIDATES
        and recovery_value.get("qaEvaluationCount") == EXPECTED_CANDIDATES
        and recovery_value.get("readOnly") is True
        and review_value.get("count") == EXPECTED_CANDIDATES
        and review_value.get("referencesExposed") is False
        and len(row_list) == EXPECTED_PARTICIPANTS
    )
    candidate_total = 0
    if valid:
        for participant_index, row in enumerate(row_list, start=1):
            if not isinstance(row, Mapping):
                valid = False
                break
            candidates = row.get("candidates")
            candidate_list = candidates if isinstance(candidates, list) else []
            if (
                row.get("participantOrdinal") != f"P{participant_index:02d}"
                or len(candidate_list) != EXPECTED_CANDIDATES_PER_PARTICIPANT
            ):
                valid = False
                break
            for candidate_index, candidate in enumerate(candidate_list, start=1):
                if not isinstance(candidate, Mapping):
                    valid = False
                    break
                qa = candidate.get("qa")
                if (
                    candidate.get("candidateOrdinal") != candidate_index
                    or candidate.get("previewExposed") is not False
                    or candidate.get("approvalPerformed") is not False
                    or candidate.get("publicProjection") is not False
                    or not isinstance(qa, Mapping)
                    or not str(qa.get("qaVersion") or "").strip()
                ):
                    valid = False
                    break
                candidate_total += 1
            if not valid:
                break
    if not valid or candidate_total != EXPECTED_CANDIDATES:
        raise CalibrationOperatorError("operator_recovery_report_invalid")


def _recover_report_and_cleanup(
    *,
    gateway: GcloudStorageGateway,
    staged_bundle: Any,
    service_url: str,
    request_body: Mapping[str, Any],
    timeout_seconds: float,
    private_values: tuple[str, ...],
) -> tuple[dict[str, Any], dict[str, int]]:
    """Fetch/validate evidence and clean staged objects on known outcomes."""

    try:
        token = gateway.identity_token()
        report = dict(
            _post_once(
                service_url=service_url,
                token=token,
                request_body=request_body,
                timeout_seconds=timeout_seconds,
            )
        )
        assert_redacted_calibration_report(report, private_values=private_values)
        _validate_recovery_report(report)
    except CalibrationOperatorError as exc:
        if str(exc) == "operator_recovery_http_unknown_outcome":
            raise
        try:
            delete_staged_recovery_candidates(gateway, staged_bundle)
        except CalibrationOperatorError as cleanup_exc:
            raise CalibrationOperatorError(
                "operator_recovery_failure_cleanup_incomplete"
            ) from cleanup_exc
        raise
    except Exception as exc:
        try:
            delete_staged_recovery_candidates(gateway, staged_bundle)
        except CalibrationOperatorError as cleanup_exc:
            raise CalibrationOperatorError(
                "operator_recovery_failure_cleanup_incomplete"
            ) from cleanup_exc
        raise CalibrationOperatorError("operator_recovery_validation_failed") from exc

    cleanup = delete_staged_recovery_candidates(gateway, staged_bundle)
    return report, cleanup


def _write_report(path: Path, report: Mapping[str, Any]) -> None:
    target = path.resolve()
    if target.exists():
        raise CalibrationOperatorError("operator_report_exists")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    if temporary.exists():
        raise CalibrationOperatorError("operator_report_temp_exists")
    temporary.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(target)


def _attach_recovery_audit_metadata(
    report: Mapping[str, Any],
    *,
    run_id: str,
    parent_recovery_id: str,
    worker_image_digest: str,
) -> dict[str, Any]:
    """Attach safe operator lineage without changing candidate evidence."""

    digest = str(worker_image_digest or "").strip().lower()
    parent = str(parent_recovery_id or "").strip()
    normalized_run_id = str(run_id or "").strip().upper()
    if not _IMAGE_DIGEST_PATTERN.fullmatch(digest):
        raise CalibrationOperatorError("operator_worker_image_digest_invalid")
    if not parent:
        raise CalibrationOperatorError("operator_parent_recovery_id_invalid")
    enriched = dict(report)
    enriched.update(
        {
            "evaluationId": (
                f"{normalized_run_id}-{OPERATOR_RECOVERY_EVALUATION_SUFFIX}"
            ),
            "evaluationVersion": OPERATOR_RECOVERY_EVALUATION_SUFFIX,
            "parentRunId": normalized_run_id,
            "parentRecoveryId": parent,
            "qaVersion": str(enriched.get("qaEvaluationVersion") or ""),
            # The value is an immutable image digest; the neutral field name
            # keeps the report redaction contract from treating it as a hash
            # of participant or image content.
            "workerImage": digest,
        }
    )
    return enriched


def main() -> int:
    args = _parser().parse_args()
    run_id = str(args.run_id or "").strip().upper()
    if args.project != DEFAULT_PROJECT:
        raise CalibrationOperatorError("operator_staging_project_required")
    if run_id != EXPECTED_RUN_ID:
        raise CalibrationOperatorError("operator_recovery_run_id_invalid")
    if not math.isfinite(args.original_server_duration_seconds):
        raise CalibrationOperatorError("operator_original_duration_invalid")
    if args.report.resolve().exists():
        raise CalibrationOperatorError("operator_report_exists")

    manifest = _read_manifest(args.manifest, expected_project=DEFAULT_PROJECT)
    private_values = _private_values(manifest)
    gateway = GcloudStorageGateway()
    service_url = _service_url(gateway, args)
    enriched_manifest = enrich_manifest_source_generations(manifest, gateway)

    staged_bundle = stage_local_review_bundle_for_recovery(
        gateway,
        run_id=run_id,
        participant_count=EXPECTED_PARTICIPANTS,
        candidates_per_participant=EXPECTED_CANDIDATES_PER_PARTICIPANT,
        review_root=args.review_root,
        temp_bucket=args.temp_bucket,
    )
    request_body = {
        "schemaVersion": CALIBRATION_RECOVERY_REQUEST_SCHEMA,
        "runId": run_id,
        "manifest": enriched_manifest,
        "originalRunEvidence": {
            "serverRequestCount": 1,
            "serverHttpStatus": 200,
            "serverDurationSeconds": args.original_server_duration_seconds,
            "candidateCount": EXPECTED_CANDIDATES,
            "retryCount": 0,
            "providerRequestBudget": {
                "limit": EXPECTED_CANDIDATES,
                "consumed": EXPECTED_CANDIDATES,
                "remaining": 0,
            },
        },
    }
    report, cleanup = _recover_report_and_cleanup(
        gateway=gateway,
        staged_bundle=staged_bundle,
        service_url=service_url,
        request_body=request_body,
        timeout_seconds=args.timeout_seconds,
        private_values=private_values,
    )
    report = _attach_recovery_audit_metadata(
        report,
        run_id=run_id,
        parent_recovery_id=(
            args.parent_recovery_id
            or f"{run_id}-{CALIBRATION_RECOVERY_EVALUATION_SUFFIX}"
        ),
        worker_image_digest=args.worker_image_digest,
    )
    report["operatorReviewRecovery"] = {
        "localArtifactCount": EXPECTED_CANDIDATES,
        **cleanup,
        "generationMatchDelete": True,
    }
    report["automaticEvidenceValidated"] = True
    assert_redacted_calibration_report(report, private_values=private_values)
    _write_report(args.report, report)
    print(
        json.dumps(
            {
                "status": "completed",
                "nextState": "HUMAN_REVIEW_REQUIRED",
                "participantCount": EXPECTED_PARTICIPANTS,
                "candidateCount": EXPECTED_CANDIDATES,
                "generationCallsPerformedByRecovery": 0,
                "localArtifactCount": EXPECTED_CANDIDATES,
                "remoteRemainingCount": cleanup["remoteRemainingCount"],
                "redacted": True,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CalibrationOperatorError as exc:
        print(json.dumps({"status": "error", "errorCode": str(exc)}))
        raise SystemExit(1)
