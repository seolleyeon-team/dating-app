"""Privacy-safe operator helpers for one controlled G004 staging run."""

from __future__ import annotations

from dataclasses import dataclass, field
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit

from PIL import Image


_RUN_ID_PATTERN = re.compile(r"^G004-[A-Z0-9][A-Z0-9_-]{6,79}$")
_BUCKET_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{1,61}[a-z0-9]$")
_PRIVATE_MARKERS = (
    "gs://",
    "gcs://",
    "http://",
    "https://",
    "x-goog-signature",
    "x-amz-signature",
    "private-source",
)
_FORBIDDEN_REPORT_KEY_FRAGMENTS = (
    "hash",
    "digest",
    "checksum",
    "etag",
    "md5",
)


class CalibrationOperatorError(RuntimeError):
    """Stable operator failure that never includes a private object reference."""


@dataclass(frozen=True)
class StagedRecoveryBundle:
    """Opaque generation-pinned handles for temporary recovery candidates."""

    count: int
    _objects: tuple[tuple[str, str], ...] = field(repr=False)


class GcloudStorageGateway:
    """Use the authenticated gcloud CLI without exposing captured output."""

    def __init__(self, executable: str | None = None) -> None:
        self.executable = executable or shutil.which("gcloud") or shutil.which("gcloud.cmd") or "gcloud"

    def describe_generation(self, uri: str) -> str:
        completed = self._run(
            ["storage", "objects", "describe", uri, "--format=json"],
            text=True,
        )
        try:
            payload = json.loads(completed.stdout)
            generation = str(payload.get("generation") or "").strip()
        except Exception as exc:
            raise CalibrationOperatorError("operator_object_metadata_invalid") from exc
        return _safe_generation(generation)

    def download(self, uri: str, *, generation: str) -> bytes:
        safe_generation = _safe_generation(generation)
        if "#" in uri:
            raise CalibrationOperatorError("operator_object_ref_invalid")
        return bytes(
            self._run(
                ["storage", "cat", f"{uri}#{safe_generation}"],
                text=False,
            ).stdout
        )

    def upload_create_only(self, path: Path, uri: str) -> str:
        source = Path(path).resolve()
        if not source.is_file() or "#" in uri:
            raise CalibrationOperatorError("operator_recovery_upload_invalid")
        self._run(
            [
                "storage",
                "cp",
                str(source),
                uri,
                "--if-generation-match=0",
                "--content-type=image/png",
            ],
            text=True,
        )
        return self.describe_generation(uri)

    def delete(self, uri: str, *, generation: str) -> None:
        safe_generation = _safe_generation(generation)
        self._run(
            [
                "storage",
                "rm",
                f"--if-generation-match={safe_generation}",
                uri,
            ],
            text=False,
        )

    def identity_token(self) -> str:
        override = os.environ.get("AVATAR_CALIBRATION_IDENTITY_TOKEN", "").strip()
        if override:
            return override
        completed = self._run(
            ["auth", "print-identity-token"],
            text=True,
        )
        token = str(completed.stdout or "").strip()
        if not token:
            raise CalibrationOperatorError("operator_identity_token_missing")
        return token

    def cloud_run_tag_url(
        self,
        *,
        service: str,
        region: str,
        project: str,
        tag: str,
    ) -> str:
        completed = self._run(
            [
                "run",
                "services",
                "describe",
                service,
                f"--region={region}",
                f"--project={project}",
                "--format=json(status.traffic)",
            ],
            text=True,
        )
        try:
            payload = json.loads(completed.stdout)
            traffic = payload.get("status", {}).get("traffic", [])
            value = next(
                str(row.get("url") or "").strip()
                for row in traffic
                if isinstance(row, Mapping) and row.get("tag") == tag
            )
        except Exception as exc:
            raise CalibrationOperatorError("operator_service_tag_missing") from exc
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or not parsed.hostname.endswith(".run.app")
            or parsed.username
            or parsed.password
            or parsed.port
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
        ):
            raise CalibrationOperatorError("operator_service_url_invalid")
        return value.rstrip("/")

    def _run(self, arguments: Sequence[str], *, text: bool) -> subprocess.CompletedProcess[Any]:
        try:
            completed = subprocess.run(
                [self.executable, *[str(value) for value in arguments]],
                check=False,
                capture_output=True,
                text=text,
            )
        except Exception as exc:
            raise CalibrationOperatorError("operator_gcloud_unavailable") from exc
        if completed.returncode != 0:
            raise CalibrationOperatorError("operator_gcloud_command_failed")
        return completed


def enrich_manifest_source_generations(
    manifest: Mapping[str, Any],
    storage_gateway: Any,
) -> dict[str, Any]:
    """Return a deep copied manifest with exact GCS generations in memory."""

    try:
        enriched = json.loads(json.dumps(manifest, ensure_ascii=False))
    except Exception as exc:
        raise CalibrationOperatorError("operator_manifest_invalid") from exc
    if not isinstance(enriched, dict):
        raise CalibrationOperatorError("operator_manifest_invalid")
    participants = enriched.get("participants")
    if not isinstance(participants, list) or not participants:
        raise CalibrationOperatorError("operator_manifest_invalid")
    for participant in participants:
        if not isinstance(participant, dict):
            raise CalibrationOperatorError("operator_manifest_invalid")
        source_ref = str(participant.get("sourcePhotoRef") or "").strip()
        if not source_ref.startswith("gs://"):
            raise CalibrationOperatorError("operator_source_ref_invalid")
        participant["sourceGeneration"] = _safe_generation(
            storage_gateway.describe_generation(source_ref)
        )
    return enriched


def assert_redacted_calibration_report(
    report: Mapping[str, Any],
    *,
    private_values: Sequence[str] = (),
) -> None:
    try:
        serialized = json.dumps(report, ensure_ascii=False, sort_keys=True).lower()
    except Exception as exc:
        raise CalibrationOperatorError("operator_report_invalid") from exc
    if any(marker in serialized for marker in _PRIVATE_MARKERS):
        raise CalibrationOperatorError("operator_report_privacy_failed")
    for value in private_values:
        normalized = str(value or "").strip().lower()
        if len(normalized) >= 6 and normalized in serialized:
            raise CalibrationOperatorError("operator_report_privacy_failed")
    if re.search(r"\buid[-_:][a-z0-9_-]+", serialized):
        raise CalibrationOperatorError("operator_report_privacy_failed")
    if _contains_forbidden_report_key(report):
        raise CalibrationOperatorError("operator_report_privacy_failed")


def _contains_forbidden_report_key(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).replace("_", "").replace("-", "").lower()
            if (
                any(fragment in normalized for fragment in _FORBIDDEN_REPORT_KEY_FRAGMENTS)
                or normalized.startswith("sha")
            ):
                return True
            if _contains_forbidden_report_key(child):
                return True
        return False
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return any(_contains_forbidden_report_key(child) for child in value)
    return False


def persist_review_bundle_and_delete_remote(
    storage_gateway: Any,
    *,
    run_id: str,
    participant_count: int,
    candidates_per_participant: int,
    review_root: Path,
    temp_bucket: str,
) -> dict[str, int]:
    """Download all generated review images, then generation-match delete GCS copies."""

    safe_run_id = _safe_run_id(run_id)
    safe_bucket = str(temp_bucket or "").strip()
    if not _BUCKET_PATTERN.fullmatch(safe_bucket):
        raise CalibrationOperatorError("operator_temp_bucket_invalid")
    participants = int(participant_count)
    candidates = int(candidates_per_participant)
    if not 1 <= participants <= 100 or not 1 <= candidates <= 4:
        raise CalibrationOperatorError("operator_review_shape_invalid")

    targets: list[tuple[str, str, str]] = []
    for participant in range(1, participants + 1):
        for candidate in range(1, candidates + 1):
            ordinal = f"P{participant:02d}"
            candidate_label = f"C{candidate:02d}"
            uri = (
                f"gs://{safe_bucket}/calibration/g004/{safe_run_id}/"
                f"{ordinal}/{candidate_label}.png"
            )
            generation = _safe_generation(storage_gateway.describe_generation(uri))
            targets.append((uri, generation, f"{ordinal}_{candidate_label}.png"))

    root = Path(review_root).resolve()
    final_directory = (root / safe_run_id).resolve()
    partial_directory = (root / f".{safe_run_id}.partial").resolve()
    if final_directory.parent != root or partial_directory.parent != root:
        raise CalibrationOperatorError("operator_review_directory_invalid")
    if final_directory.exists() or partial_directory.exists():
        raise CalibrationOperatorError("operator_review_directory_exists")
    root.mkdir(parents=True, exist_ok=True)
    partial_directory.mkdir()

    try:
        for uri, generation, filename in targets:
            data = bytes(storage_gateway.download(uri, generation=generation))
            _validate_generated_png(data)
            (partial_directory / filename).write_bytes(data)
        partial_directory.replace(final_directory)
    except Exception as exc:
        if isinstance(exc, CalibrationOperatorError):
            raise
        raise CalibrationOperatorError("operator_review_download_failed") from exc

    deleted = 0
    try:
        for uri, generation, _filename in targets:
            storage_gateway.delete(uri, generation=generation)
            deleted += 1
    except Exception as exc:
        raise CalibrationOperatorError("operator_review_remote_cleanup_incomplete") from exc

    return {
        "localArtifactCount": len(targets),
        "remoteDeletedCount": deleted,
        "remoteRemainingCount": max(0, len(targets) - deleted),
    }


def stage_local_review_bundle_for_recovery(
    storage_gateway: Any,
    *,
    run_id: str,
    participant_count: int,
    candidates_per_participant: int,
    review_root: Path,
    temp_bucket: str,
) -> StagedRecoveryBundle:
    """Create-only upload a complete ordinal-only local review bundle."""

    safe_run_id = _safe_run_id(run_id)
    safe_bucket = str(temp_bucket or "").strip()
    if not _BUCKET_PATTERN.fullmatch(safe_bucket):
        raise CalibrationOperatorError("operator_temp_bucket_invalid")
    participants = int(participant_count)
    candidates = int(candidates_per_participant)
    if not 1 <= participants <= 100 or not 1 <= candidates <= 4:
        raise CalibrationOperatorError("operator_review_shape_invalid")

    root = Path(review_root).resolve()
    directory = (root / safe_run_id).resolve()
    if directory.parent != root or not directory.is_dir():
        raise CalibrationOperatorError("operator_review_bundle_invalid")

    expected: list[tuple[Path, str]] = []
    expected_names: set[str] = set()
    for participant in range(1, participants + 1):
        for candidate in range(1, candidates + 1):
            ordinal = f"P{participant:02d}"
            candidate_label = f"C{candidate:02d}"
            filename = f"{ordinal}_{candidate_label}.png"
            expected_names.add(filename)
            path = (directory / filename).resolve()
            if path.parent != directory or not path.is_file():
                raise CalibrationOperatorError("operator_review_bundle_invalid")
            _validate_generated_png(path.read_bytes())
            uri = (
                f"gs://{safe_bucket}/calibration/g004/{safe_run_id}/"
                f"{ordinal}/{candidate_label}.png"
            )
            expected.append((path, uri))

    observed_names = {
        path.name
        for path in directory.iterdir()
        if path.is_file()
    }
    if observed_names != expected_names or any(path.is_dir() for path in directory.iterdir()):
        raise CalibrationOperatorError("operator_review_bundle_invalid")

    staged: list[tuple[str, str]] = []
    try:
        for path, uri in expected:
            generation = _safe_generation(
                storage_gateway.upload_create_only(path, uri)
            )
            staged.append((uri, generation))
    except Exception as exc:
        rollback_complete = True
        for uri, generation in reversed(staged):
            try:
                storage_gateway.delete(uri, generation=generation)
            except Exception:
                rollback_complete = False
        if not rollback_complete:
            raise CalibrationOperatorError(
                "operator_recovery_stage_rollback_incomplete"
            ) from exc
        raise CalibrationOperatorError("operator_recovery_stage_failed") from exc

    return StagedRecoveryBundle(count=len(staged), _objects=tuple(staged))


def delete_staged_recovery_candidates(
    storage_gateway: Any,
    bundle: StagedRecoveryBundle,
) -> dict[str, int]:
    """Generation-match delete only objects created for QA-only recovery."""

    if not isinstance(bundle, StagedRecoveryBundle) or bundle.count != len(bundle._objects):
        raise CalibrationOperatorError("operator_recovery_bundle_invalid")
    deleted = 0
    try:
        for uri, generation in bundle._objects:
            storage_gateway.delete(uri, generation=_safe_generation(generation))
            deleted += 1
    except Exception as exc:
        raise CalibrationOperatorError(
            "operator_recovery_remote_cleanup_incomplete"
        ) from exc
    return {
        "remoteUploadedCount": bundle.count,
        "remoteDeletedCount": deleted,
        "remoteRemainingCount": max(0, bundle.count - deleted),
    }


def _safe_run_id(value: Any) -> str:
    run_id = str(value or "").strip().upper()
    if not _RUN_ID_PATTERN.fullmatch(run_id):
        raise CalibrationOperatorError("operator_run_id_invalid")
    return run_id


def _safe_generation(value: Any) -> str:
    generation = str(value or "").strip()
    if not generation.isdigit():
        raise CalibrationOperatorError("operator_object_generation_invalid")
    return generation


def _validate_generated_png(data: bytes) -> None:
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.verify()
        with Image.open(io.BytesIO(data)) as image:
            if image.format != "PNG" or image.width <= 0 or image.height <= 0:
                raise ValueError("invalid generated PNG")
    except Exception as exc:
        raise CalibrationOperatorError("operator_review_image_invalid") from exc


__all__ = [
    "CalibrationOperatorError",
    "GcloudStorageGateway",
    "StagedRecoveryBundle",
    "assert_redacted_calibration_report",
    "delete_staged_recovery_candidates",
    "enrich_manifest_source_generations",
    "persist_review_bundle_and_delete_remote",
    "stage_local_review_bundle_for_recovery",
]
