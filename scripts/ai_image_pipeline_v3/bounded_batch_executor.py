from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .active_visual_verdict_runner import run_active_visual_qa_all, write_manual_review_flag
from .codex_imagegen import build_pending_payload, pending_path, read_pending, recover_pending_imagegen, write_pending
from .config import MAX_ATTEMPTS, SHOT_ORDER, ensure_base_dirs, now_utc, pipeline_paths, prompt_hash, read_jsonl, to_portable_path, write_jsonl
from .contact_sheet import generate_chunk_contact_sheets, generate_grouped_contact_sheets, generate_identity_contact_sheets, generate_strict_chunk_contact_sheets
from .distribution_audit import audit_distribution
from .distribution_selection import select_distribution_buckets
from .distribution_targets import target_face_type, target_looks_level_band
from .manifest import load_generation_manifest, manifest_path, public_final_path, write_generation_outputs
from .one_asset_transaction import (
    OneAssetTransactionError,
    backup_forbidden_files,
    build_one_asset_worker_prompt,
    build_receipt_from_existing_file,
    detect_forbidden_mutations,
    restore_forbidden_files,
    snapshot_forbidden_files,
    transaction_receipt_path,
    verify_one_asset_transaction,
    write_receipt,
)
from .pending_state import pending_is_resolved, pending_is_unresolved, pending_requires_recovery, resolved_pending_payload
from .qa import inspect_image_detail
from .retry_plan import APPROVED_STATUSES, attempt_count, face_card_exhaustion
from .prompt_source import load_prompt_module


PLAN_SCHEMA_VERSION = "seolleyeon_bounded_chunk_plan_v3"
STATE_SCHEMA_VERSION = "seolleyeon_bounded_chunk_state_v3"
REPORT_SCHEMA_VERSION = "seolleyeon_bounded_chunk_report_v3"
ABANDONED_CHUNK_SCHEMA_VERSION = "seolleyeon_abandoned_chunk_manifest_v3"
ASSET_QA_MANIFEST_SCHEMA_VERSION = "seolleyeon_asset_qa_manifest_v3"
RESET_SCHEMA_VERSION = "seolleyeon_bounded_chunk_reset_v3"
MAX_CHUNK_IDENTITIES = 24
MAX_CHUNK_ASSETS = 72
IMAGEGEN_RECOVERY_WAIT_SECONDS = 45.0
IMAGEGEN_RECOVERY_POLL_SECONDS = 1.5

CHUNK_TERMINAL_STATUSES = {"finalized", "failed", "needs_manual_review"}
EXECUTABLE_CHUNK_STATUSES = {"planned", "running", "generation_in_progress", "generation_paused"}
ABANDONABLE_CHUNK_STATUSES = {"running", "generation_in_progress", "generation_paused", "failed"}
RESETTABLE_CHUNK_STATUSES = {"needs_manual_review", "failed", "abandoned", "reset_required", "reset_recommended"}
ASSET_TERMINAL_STATUSES = {
    "file_qa_passed",
    "visual_qa_approved",
    "visual_qa_needs_review",
    "visual_qa_rejected",
    "approved",
    "needs_review",
    "rejected",
    "failed",
    "skipped",
}
GENERATION_COMPLETE_ASSET_STATUSES = {"file_qa_passed", "failed", "skipped"}
IDENTITY_TERMINAL_STATUSES = {"approved", "needs_review", "rejected", "failed"}
DEPENDENT_SHOTS = {"silhouette_card", "vibe_card"}
RECOVERABLE_MANUAL_REVIEW_REASONS = {
    "child_forbidden_mutation",
    "one_asset_receipt_missing_or_invalid_requires_reconcile",
    "bounded_recovery_failed",
    "unresolved_pending_imagegen",
}
RESET_MANIFEST_SNAPSHOT_FILES = (
    "generation_manifest.jsonl",
    "file_qa_manifest.jsonl",
    "asset_qa_manifest.jsonl",
    "identity_qa_manifest.jsonl",
    "approved_identity_manifest.jsonl",
    "rejected_identity_manifest.jsonl",
    "needs_review_identity_manifest.jsonl",
    "imagegen_queue.jsonl",
    "asset_manifest.jsonl",
    "identity_manifest.jsonl",
    "ai_profile_assets_v3.jsonl",
    "ai_profile_specs_v3.jsonl",
)
RESET_VISUAL_VERDICT_FILES = (
    "asset_qa_latest.json",
    "identity_qa_latest.json",
    "distribution_audit_latest.json",
    "asset_qa_apply_history.jsonl",
    "identity_qa_apply_history.jsonl",
    "distribution_audit_apply.json",
)
PLAN_TYPE_FULL_IDENTITY_GENERATION = "full_identity_generation"
PLAN_TYPE_TARGETED_RETRY = "targeted_retry"
PLAN_TYPE_PARTIAL_SALVAGE = "partial_salvage"
PARTIAL_PLAN_TYPES = {PLAN_TYPE_TARGETED_RETRY, PLAN_TYPE_PARTIAL_SALVAGE}
DEFAULT_REUSE_POLICY = {
    "allowAssetReuse": False,
    "allowSilhouetteReuseWithoutApprovedFaceAnchor": False,
    "allowReuseFromRejectedIdentity": False,
}


class BoundedBatchExecutorError(RuntimeError):
    pass


class PlanValidationError(BoundedBatchExecutorError):
    def __init__(self, reason_code: str, message: str | None = None, details: Mapping[str, Any] | None = None) -> None:
        self.reason_code = reason_code
        self.details = dict(details or {})
        super().__init__(message or reason_code)


@dataclass(frozen=True)
class BoundedExecutorConfig:
    agent_cmd: str
    agent_mode: str
    imagegen_surface: str
    timeout_sec: int
    max_asset_attempts: int
    allow_reserve_activation: bool
    max_identities: int
    max_assets: int
    reference_mode: str
    active_visual_qa: bool
    image_arg_mode: str = "auto"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "BoundedExecutorConfig":
        values = env or os.environ
        agent_mode = str(values.get("BOUNDED_EXECUTOR_AGENT_MODE") or "exec").strip()
        if agent_mode != "exec":
            raise ValueError(f"Unsupported BOUNDED_EXECUTOR_AGENT_MODE: {agent_mode}")
        imagegen_surface = str(values.get("BOUNDED_EXECUTOR_IMAGEGEN_SURFACE") or "parent").strip()
        if imagegen_surface not in {"parent", "child"}:
            raise ValueError(f"Unsupported BOUNDED_EXECUTOR_IMAGEGEN_SURFACE: {imagegen_surface}")
        reference_mode = str(values.get("BOUNDED_EXECUTOR_REFERENCE_MODE") or "path").strip()
        if reference_mode not in {"path", "image", "disabled"}:
            raise ValueError(f"Unsupported BOUNDED_EXECUTOR_REFERENCE_MODE: {reference_mode}")
        image_arg_mode = str(values.get("BOUNDED_EXECUTOR_IMAGE_ARG_MODE") or values.get("CODEX_IMAGE_ARG_MODE") or "auto").strip()
        if image_arg_mode not in {"auto", "image", "short_i"}:
            raise ValueError(f"Unsupported BOUNDED_EXECUTOR_IMAGE_ARG_MODE: {image_arg_mode}")
        default_agent_cmd = str(values.get("CODEX_BIN") or "omx").strip() or "omx"
        requested_timeout_sec = int(values.get("BOUNDED_EXECUTOR_TIMEOUT_SEC") or "300")
        safe_timeout_sec = max(30, min(requested_timeout_sec, 300))
        return cls(
            agent_cmd=str(values.get("BOUNDED_EXECUTOR_AGENT_CMD") or default_agent_cmd).strip() or default_agent_cmd,
            agent_mode=agent_mode,
            imagegen_surface=imagegen_surface,
            timeout_sec=safe_timeout_sec,
            max_asset_attempts=int(values.get("BOUNDED_EXECUTOR_MAX_ASSET_ATTEMPTS") or str(MAX_ATTEMPTS)),
            allow_reserve_activation=str(values.get("BOUNDED_EXECUTOR_ALLOW_RESERVE_ACTIVATION") or "0") == "1",
            max_identities=min(MAX_CHUNK_IDENTITIES, int(values.get("BOUNDED_EXECUTOR_MAX_IDENTITIES") or str(MAX_CHUNK_IDENTITIES))),
            max_assets=min(MAX_CHUNK_ASSETS, int(values.get("BOUNDED_EXECUTOR_MAX_ASSETS") or str(MAX_CHUNK_ASSETS))),
            reference_mode=reference_mode,
            active_visual_qa=str(values.get("ACTIVE_VISUAL_QA") or "1") != "0",
            image_arg_mode=image_arg_mode,
        )


def _chunk_id() -> str:
    return "chunk_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _replacement_chunk_id(root: Path | str | None = None) -> str:
    candidate = _chunk_id()
    try:
        current = str(read_current_plan(root).get("chunkId") or "")
    except Exception:
        current = ""
    if candidate != current:
        return candidate
    return "chunk_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def current_plan_path(root: Path | str | None = None) -> Path:
    return pipeline_paths(root).manifests / "current_chunk_plan.json"


def current_state_path(root: Path | str | None = None) -> Path:
    return pipeline_paths(root).manifests / "current_chunk_state.json"


def target_config_path(root: Path | str | None = None) -> Path:
    return pipeline_paths(root).ai_image / "config" / "AI_IMAGE_DISTRIBUTION_TARGETS_V3.json"


def latest_distribution_audit_path(root: Path | str | None = None) -> Path:
    return pipeline_paths(root).reports / "latest_distribution_audit.json"


def queue_jsonl_path(root: Path | str | None = None) -> Path:
    return pipeline_paths(root).manifests / "imagegen_queue.jsonl"


def asset_manifest_jsonl_path(root: Path | str | None = None) -> Path:
    return pipeline_paths(root).manifests / "ai_profile_assets_v3.jsonl"


def abandoned_chunk_manifest_path(root: Path | str | None = None) -> Path:
    return pipeline_paths(root).manifests / "abandoned_chunk_manifest.jsonl"


def chunk_report_dir(root: Path | str | None, chunk_id: str) -> Path:
    return pipeline_paths(root).reports / "chunks" / chunk_id


def chunk_report_path(root: Path | str | None, chunk_id: str) -> Path:
    return chunk_report_dir(root, chunk_id) / "chunk_report.json"


def events_path(root: Path | str | None, chunk_id: str) -> Path:
    return chunk_report_dir(root, chunk_id) / "events.jsonl"


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        f.write(json.dumps(dict(payload), ensure_ascii=False, indent=2))
        f.write("\n")
        f.flush()
        try:
            os.fsync(f.fileno())
        except OSError:
            pass
    last_error: OSError | None = None
    # Windows can briefly deny os.replace() when another process, AV scanner, or
    # file indexer has just opened the destination after a read.  Retrying in a
    # tight loop usually hits the same transient lock repeatedly, so use a short
    # backoff before surfacing the real permission problem.
    for attempt in range(8):
        try:
            tmp.replace(path)
            return
        except PermissionError as exc:
            last_error = exc
            if attempt < 7:
                time.sleep(0.1 * (attempt + 1))
    if last_error is not None:
        raise last_error


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def read_current_plan(root: Path | str | None = None) -> dict[str, Any]:
    return _read_json(current_plan_path(root))


def read_current_state(root: Path | str | None = None) -> dict[str, Any]:
    return _read_json(current_state_path(root))


def _sha256_file(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _input_hashes(root: Path | str | None = None) -> dict[str, str | None]:
    return {
        "targetsJsonSha256": _sha256_file(target_config_path(root)),
        "distributionAuditJsonSha256": _sha256_file(latest_distribution_audit_path(root)),
        "queueJsonSha256": _sha256_file(queue_jsonl_path(root)),
        "assetManifestJsonSha256": _sha256_file(asset_manifest_jsonl_path(root)),
    }


def _mtime_value(path: Path) -> float | None:
    return path.stat().st_mtime if path.exists() else None


def _input_mtimes(root: Path | str | None = None) -> dict[str, float | None]:
    return {
        "targetsJsonMtime": _mtime_value(target_config_path(root)),
        "distributionAuditJsonMtime": _mtime_value(latest_distribution_audit_path(root)),
        "queueJsonMtime": _mtime_value(queue_jsonl_path(root)),
        "assetManifestJsonMtime": _mtime_value(asset_manifest_jsonl_path(root)),
    }


def _plan_hash(plan: Mapping[str, Any]) -> str:
    payload = copy.deepcopy(dict(plan))
    for key in ("createdAt", "updatedAt", "planHash", "archivedPreviousPlan", "abandonedPreviousChunk", "resumeInputRefreshHistory"):
        payload.pop(key, None)
    payload["status"] = "planned"
    for identity in payload.get("identities", []) or []:
        if isinstance(identity, dict):
            identity["status"] = "planned"
            for asset in identity.get("assets", []) or []:
                if isinstance(asset, dict):
                    asset["status"] = "planned"
                    asset["attempt"] = 0
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _archive_file(path: Path, history_dir: Path, prefix: str, timestamp: str) -> str:
    history_dir.mkdir(parents=True, exist_ok=True)
    destination = history_dir / f"{prefix}_{timestamp}{path.suffix}"
    shutil.copy2(path, destination)
    return to_portable_path(destination)


def _archive_current_plan_state(root: Path | str | None = None) -> dict[str, str]:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    history_dir = pipeline_paths(root).reports / "chunks" / "plan_history"
    archived: dict[str, str] = {}
    plan_path = current_plan_path(root)
    state_path = current_state_path(root)
    if plan_path.exists():
        archived["plan"] = _archive_file(plan_path, history_dir, "current_chunk_plan", timestamp)
    if state_path.exists():
        archived["state"] = _archive_file(state_path, history_dir, "current_chunk_state", timestamp)
    return archived


def _current_plan_profile_ids(root: Path | str | None = None) -> set[str]:
    try:
        plan = read_current_plan(root)
    except Exception:
        return set()
    return {
        str(identity.get("profileId") or "")
        for identity in plan.get("identities", []) or []
        if isinstance(identity, Mapping) and identity.get("profileId")
    }


def _abandoned_chunk_rows(root: Path | str | None = None) -> list[dict[str, Any]]:
    return read_jsonl(abandoned_chunk_manifest_path(root))


def _abandoned_chunk_summary(root: Path | str | None = None) -> dict[str, Any]:
    rows = _abandoned_chunk_rows(root)
    chunk_ids: list[str] = []
    for row in rows:
        chunk_id = str(row.get("abandonedChunkId") or row.get("chunkId") or "")
        if chunk_id and chunk_id not in chunk_ids:
            chunk_ids.append(chunk_id)
    last_row = rows[-1] if rows else {}
    return {
        "abandonedChunkCount": len(chunk_ids),
        "lastAbandonedChunkId": str(last_row.get("abandonedChunkId") or last_row.get("chunkId") or "") if last_row else "",
        "abandonedChunkManifest": to_portable_path(abandoned_chunk_manifest_path(root)),
    }


def _current_chunk_abandonable(root: Path | str | None = None) -> bool:
    if not current_plan_path(root).exists() or not current_state_path(root).exists():
        return False
    try:
        plan = read_current_plan(root)
        state = read_current_state(root)
    except Exception:
        return False
    if str(plan.get("planMode") or "") != "production":
        return False
    if pipeline_paths(root).manifests.joinpath("manual_review_required.flag").exists():
        return False
    if pending_is_unresolved(read_pending(pending_path(root))):
        return False
    return str(state.get("status") or plan.get("status") or "") in ABANDONABLE_CHUNK_STATUSES


def _manual_review_reason(root: Path | str | None = None) -> str:
    flag = pipeline_paths(root).manifests / "manual_review_required.flag"
    if not flag.exists():
        return ""
    text = flag.read_text(encoding="utf-8", errors="replace").strip()
    if not text:
        return "manual_review_required"
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        first_line = text.splitlines()[0].strip()
        return first_line.split("=", 1)[0].strip() or "manual_review_required"
    if isinstance(payload, Mapping):
        return str(payload.get("reason") or payload.get("reasonCode") or "manual_review_required")
    return "manual_review_required"


def _append_event(
    root: Path | str | None,
    chunk_id: str,
    *,
    event_type: str,
    profile_id: str = "",
    asset_id: str = "",
    shot_type: str = "",
    from_status: str = "",
    to_status: str = "",
    reason: str = "",
    command: Sequence[str] | None = None,
    return_code: int | None = None,
    output_path: str = "",
) -> None:
    path = events_path(root, chunk_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "timestamp": now_utc(),
        "chunkId": chunk_id,
        "eventType": event_type,
        "profileId": profile_id,
        "assetId": asset_id,
        "shotType": shot_type,
        "fromStatus": from_status,
        "toStatus": to_status,
        "reason": reason,
        "command": list(command or []),
        "returnCode": return_code,
        "outputPath": output_path,
    }
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _profile_number(profile_id: str) -> str:
    parts = profile_id.split("_", 1)
    if len(parts) != 2 or not parts[1]:
        raise BoundedBatchExecutorError(f"Invalid profileId in bounded chunk plan: {profile_id}")
    return parts[1]


def _target_face(row: Mapping[str, Any]) -> str:
    return target_face_type(row) or "unknown"


def _target_looks(row: Mapping[str, Any]) -> str:
    return target_looks_level_band(row) or "unknown"


def _normalize_has_eyewear_filter(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if not text:
        return None
    if text in {"1", "true", "yes", "y", "with", "with_eyewear", "glasses"}:
        return True
    if text in {"0", "false", "no", "n", "none", "without", "without_eyewear", "no_eyewear"}:
        return False
    raise ValueError(f"Unsupported has_eyewear filter: {value!r}")


def _row_has_eyewear(row: Mapping[str, Any]) -> bool:
    explicit = _normalize_has_eyewear_filter(row.get("hasEyewear"))
    if explicit is not None:
        return explicit
    for key in ("eyewearGroup", "targetEyewearGroup", "shotEyewearExpected", "canonicalEyewear", "eyewear"):
        text = str(row.get(key) or "").strip().lower()
        if text and text not in {"none", "no_eyewear", "without_eyewear", "bare_face"}:
            return True
    return False


def _row_eyewear_group(row: Mapping[str, Any]) -> str:
    value = str(row.get("eyewearGroup") or row.get("targetEyewearGroup") or "").strip()
    if value:
        return value
    return "glasses" if _row_has_eyewear(row) else "none"


def _row_final_path(paths: Any, row: Mapping[str, Any]) -> Path:
    value = str(row.get("finalPath") or row.get("expectedFinalPath") or "")
    return Path(value).resolve() if value else public_final_path(paths, row)


def _path_exists(value: Any) -> bool:
    if not value:
        return False
    path = Path(str(value))
    return path.exists() and path.stat().st_size > 0


def _asset_already_approved(row: Mapping[str, Any]) -> bool:
    return str(row.get("status") or "") in APPROVED_STATUSES and _path_exists(row.get("finalPath"))


def _asset_needs_generation(row: Mapping[str, Any]) -> bool:
    if _asset_already_approved(row):
        return False
    status = str(row.get("status") or "")
    if status in {"vision_approved", "identity_approved"} and _path_exists(row.get("finalPath")):
        return False
    return True


def _prompt_targeting_version(row: Mapping[str, Any]) -> str:
    value = str(row.get("promptTargetingVersion") or "").strip()
    if value:
        return value
    metadata = row.get("metadata")
    if isinstance(metadata, Mapping):
        return str(metadata.get("promptTargetingVersion") or "").strip()
    return ""


def _active_prompt_targeting_version() -> str:
    module = load_prompt_module()
    return str(getattr(module, "PROMPT_TARGETING_VERSION", "") or "").strip()


def _prompt_evidence_matches_active_asset(active_row: Mapping[str, Any], evidence_row: Mapping[str, Any]) -> bool:
    active_version = _prompt_targeting_version(active_row)
    evidence_version = _prompt_targeting_version(evidence_row)
    if active_version and evidence_version != active_version:
        return False
    active_hash = str(active_row.get("promptHash") or "")
    evidence_hash = str(evidence_row.get("promptHash") or "")
    if active_hash and evidence_hash != active_hash:
        return False
    return True


def _active_asset_rows_by_id(root: Path | str | None = None) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("assetId") or ""): dict(row)
        for row in read_jsonl(asset_manifest_jsonl_path(root))
        if row.get("assetId")
    }


def _active_generation_rows(root: Path | str | None = None) -> list[dict[str, Any]]:
    active_assets = _active_asset_rows_by_id(root)
    rows = load_generation_manifest(pipeline_paths(root))
    if not active_assets:
        return rows
    return [
        dict(row)
        for row in rows
        if str(row.get("assetId") or "") in active_assets
        and _prompt_evidence_matches_active_asset(active_assets[str(row.get("assetId") or "")], row)
    ]


def _env_flag(name: str, default: str = "0") -> bool:
    return str(os.environ.get(name) or default).strip() == "1"


def _allow_partial_salvage_plan() -> bool:
    return _env_flag("ALLOW_PARTIAL_SALVAGE_PLAN", "0")


def _allow_reuse_from_rejected_identity() -> bool:
    # This flag exists for explicit schema/config visibility, but the production
    # safety policy is fail-closed: rejected identities are never reusable.
    return False and _env_flag("ALLOW_REUSE_FROM_REJECTED_IDENTITY", "0")


def _allow_silhouette_reuse_without_face_anchor() -> bool:
    # This flag exists for explicit schema/config visibility, but the production
    # safety policy is fail-closed: dependent shots always need an approved face.
    return False and _env_flag("ALLOW_SILHOUETTE_REUSE_WITHOUT_FACE_ANCHOR", "0")


def _normalize_decision(value: Any) -> str:
    text = str(value or "").strip().lower()
    aliases = {
        "asset_approved": "approved",
        "visual_approved": "approved",
        "vision_approved": "approved",
        "identity_approved": "approved",
        "file_qa_passed": "file_qa_passed",
        "file_passed": "file_qa_passed",
        "passed": "file_qa_passed",
        "asset_needs_review": "needs_review",
        "visual_needs_review": "needs_review",
        "vision_needs_review": "needs_review",
        "identity_needs_review": "needs_review",
        "asset_rejected": "rejected",
        "visual_rejected": "rejected",
        "vision_rejected": "rejected",
        "identity_rejected": "rejected",
    }
    return aliases.get(text, text)


def _latest_by_key(rows: Sequence[Mapping[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        value = str(row.get(key) or "")
        if value:
            latest[value] = dict(row)
    return latest


def _asset_visual_decision(row: Mapping[str, Any]) -> str:
    for key in ("finalDecision", "decision", "status", "visualDecision", "assetDecision"):
        decision = _normalize_decision(row.get(key))
        if decision:
            return decision
    return ""


def _identity_qa_decision(row: Mapping[str, Any]) -> str:
    for key in ("finalCompleteIdentityDecision", "completeIdentityDecision", "decision", "status"):
        decision = _normalize_decision(row.get(key))
        if decision:
            return decision
    return ""


def _file_qa_passed(row: Mapping[str, Any]) -> bool:
    for key in ("fileQaStatus", "fileQAStatus", "decision", "status", "qaStatus"):
        if _normalize_decision(row.get(key)) == "file_qa_passed":
            return True
    return False


def _generation_file_qa_passed(row: Mapping[str, Any]) -> bool:
    if _file_qa_passed(row):
        return True
    status = str(row.get("status") or "").strip().lower()
    visual_status = str(row.get("visualQaStatus") or row.get("visualQAStatus") or "").strip().lower()
    return status == "file_needs_review" and visual_status in {"", "visual_qa_pending"}


def _reuse_context(root: Path | str | None = None) -> dict[str, Any]:
    paths = pipeline_paths(root)
    asset_manifest_rows = read_jsonl(paths.manifests / "ai_profile_assets_v3.jsonl") + read_jsonl(paths.manifests / "asset_manifest.jsonl")
    generation_rows = _active_generation_rows(root)
    return {
        "assetManifestByAssetId": _latest_by_key(asset_manifest_rows, "assetId"),
        "generationByAssetId": _latest_by_key(generation_rows, "assetId"),
        "fileQaByAssetId": _latest_by_key(read_jsonl(paths.manifests / "file_qa_manifest.jsonl"), "assetId"),
        "assetQaByAssetId": _latest_by_key(read_jsonl(paths.manifests / "asset_qa_manifest.jsonl"), "assetId"),
        "identityQaByProfileId": _latest_by_key(read_jsonl(paths.manifests / "identity_qa_manifest.jsonl"), "profileId"),
        "abandonedProfileIds": {str(row.get("profileId") or "") for row in _abandoned_chunk_rows(root) if row.get("profileId")},
    }


def _reuse_context_mapping(context: Mapping[str, Any] | Path | str | None) -> Mapping[str, Any]:
    if isinstance(context, Mapping):
        return context
    return _reuse_context(context)


def _row_for_asset(context: Mapping[str, Any], asset_id: str) -> Mapping[str, Any]:
    for key in ("assetManifestByAssetId", "generationByAssetId", "assetQaByAssetId"):
        mapping = context.get(key)
        if isinstance(mapping, Mapping) and isinstance(mapping.get(asset_id), Mapping):
            return mapping[asset_id]
    return {}


def _asset_final_file_ok(row: Mapping[str, Any]) -> bool:
    final_path = str(row.get("finalPath") or row.get("expectedFinalPath") or "")
    if not final_path:
        return False
    detail = inspect_image_detail(Path(final_path))
    return bool(detail.get("ok"))


def is_asset_reusable_for_new_plan(asset_id: str, profile_id: str, shot_type: str, context: Mapping[str, Any] | Path | str | None) -> bool:
    """Return whether a prior asset can be skipped in a new bounded production plan.

    This is intentionally stricter than asset-level visual approval.  A rejected
    identity poisons all of its assets for fresh production planning, and
    dependent shots require a valid approved face-card anchor.
    """
    ctx = _reuse_context_mapping(context)
    asset_manifest = ctx.get("assetManifestByAssetId") if isinstance(ctx.get("assetManifestByAssetId"), Mapping) else {}
    if asset_id not in asset_manifest:
        return False
    active_asset = asset_manifest[asset_id]
    generation_row = (ctx.get("generationByAssetId") or {}).get(asset_id, {}) if isinstance(ctx.get("generationByAssetId"), Mapping) else {}
    if not generation_row or not _prompt_evidence_matches_active_asset(active_asset, generation_row):
        return False
    row = _row_for_asset(ctx, asset_id)
    if str(row.get("profileId") or "") != profile_id or str(row.get("shotType") or "") != shot_type:
        return False
    if str(row.get("looksLevelBand") or target_looks_level_band(row) or "") == "4.4-5.0":
        return False
    if not _asset_final_file_ok(row):
        return False
    file_qa = (ctx.get("fileQaByAssetId") or {}).get(asset_id, {}) if isinstance(ctx.get("fileQaByAssetId"), Mapping) else {}
    if file_qa and not _prompt_evidence_matches_active_asset(active_asset, file_qa):
        return False
    if not _file_qa_passed(file_qa):
        return False
    asset_qa = (ctx.get("assetQaByAssetId") or {}).get(asset_id, {}) if isinstance(ctx.get("assetQaByAssetId"), Mapping) else {}
    if asset_qa and not _prompt_evidence_matches_active_asset(active_asset, asset_qa):
        return False
    if _asset_visual_decision(asset_qa) != "approved":
        return False
    if bool(asset_qa.get("metadataMismatch")):
        return False
    identity_qa = (ctx.get("identityQaByProfileId") or {}).get(profile_id, {}) if isinstance(ctx.get("identityQaByProfileId"), Mapping) else {}
    identity_decision = _identity_qa_decision(identity_qa)
    if identity_decision == "rejected":
        return False
    if identity_decision == "needs_review":
        return False
    if profile_id in set(ctx.get("abandonedProfileIds") or set()):
        return False
    if shot_type in DEPENDENT_SHOTS:
        face_asset_id = f"{profile_id}__face_card__v001"
        face_active_asset = asset_manifest.get(face_asset_id, {}) if isinstance(asset_manifest, Mapping) else {}
        face_generation_row = (ctx.get("generationByAssetId") or {}).get(face_asset_id, {}) if isinstance(ctx.get("generationByAssetId"), Mapping) else {}
        if not face_active_asset or not face_generation_row or not _prompt_evidence_matches_active_asset(face_active_asset, face_generation_row):
            return False
        face_row = _row_for_asset(ctx, face_asset_id)
        face_file_qa = (ctx.get("fileQaByAssetId") or {}).get(face_asset_id, {}) if isinstance(ctx.get("fileQaByAssetId"), Mapping) else {}
        face_asset_qa = (ctx.get("assetQaByAssetId") or {}).get(face_asset_id, {}) if isinstance(ctx.get("assetQaByAssetId"), Mapping) else {}
        if face_file_qa and not _prompt_evidence_matches_active_asset(face_active_asset, face_file_qa):
            return False
        if face_asset_qa and not _prompt_evidence_matches_active_asset(face_active_asset, face_asset_qa):
            return False
        if not _asset_final_file_ok(face_row):
            return False
        if not _file_qa_passed(face_file_qa):
            return False
        if _asset_visual_decision(face_asset_qa) != "approved":
            return False
    return True


def _group_by_profile(rows: Sequence[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row.get("profileId") or ""), []).append(dict(row))
    return grouped


def _load_latest_audit(root: Path | str | None = None) -> dict[str, Any]:
    path = pipeline_paths(root).reports / "latest_distribution_audit.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return audit_distribution(root=root)


def _identity_capacity(audit: Mapping[str, Any], gender: str) -> int:
    checks = audit.get("countChecks") if isinstance(audit.get("countChecks"), Mapping) else {}
    key = f"{gender}ApprovedIdentities"
    if isinstance(checks.get(key), Mapping):
        return max(0, int(checks[key].get("deficit") or 0))
    target_key = f"{gender}ApprovedIdentityCount"
    target = 120
    current = int(audit.get(target_key) or 0)
    return max(0, target - current)


def _capacity_from_audit(audit: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "gender": {
            "female": _identity_capacity(audit, "female"),
            "male": _identity_capacity(audit, "male"),
        },
        "globalFaceType": dict(audit.get("globalFaceTypeDeficits") or {}),
        "genderFaceType": {gender: dict((audit.get("genderFaceTypeDeficits") or {}).get(gender, {})) for gender in ("female", "male")},
        "globalLooksLevelBand": dict(audit.get("globalLooksLevelBandDeficits") or {}),
        "genderLooksLevelBand": {gender: dict((audit.get("genderLooksLevelBandDeficits") or {}).get(gender, {})) for gender in ("female", "male")},
    }


def _remaining_deficits(audit: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "femaleApprovedIdentities": int(((audit.get("countChecks") or {}).get("femaleApprovedIdentities") or {}).get("deficit") or 0)
        if isinstance(audit.get("countChecks"), Mapping)
        else max(0, 120 - int(audit.get("femaleApprovedIdentityCount") or 0)),
        "maleApprovedIdentities": int(((audit.get("countChecks") or {}).get("maleApprovedIdentities") or {}).get("deficit") or 0)
        if isinstance(audit.get("countChecks"), Mapping)
        else max(0, 120 - int(audit.get("maleApprovedIdentityCount") or 0)),
        "globalFaceTypeDeficits": dict(audit.get("globalFaceTypeDeficits") or {}),
        "genderFaceTypeDeficits": dict(audit.get("genderFaceTypeDeficits") or {}),
        "globalLooksLevelBandDeficits": dict(audit.get("globalLooksLevelBandDeficits") or {}),
        "genderLooksLevelBandDeficits": dict(audit.get("genderLooksLevelBandDeficits") or {}),
    }


def _audit_has_surplus(audit: Mapping[str, Any]) -> bool:
    surplus_keys = (
        "globalFaceTypeSurpluses",
        "genderFaceTypeSurpluses",
        "globalLooksLevelBandSurpluses",
        "genderLooksLevelBandSurpluses",
    )
    for key in surplus_keys:
        value = audit.get(key)
        if not isinstance(value, Mapping):
            continue
        if _mapping_has_positive_int(value):
            return True
    return False


def _mapping_has_positive_int(value: Mapping[str, Any]) -> bool:
    for item in value.values():
        if isinstance(item, Mapping):
            if _mapping_has_positive_int(item):
                return True
        else:
            try:
                if int(item or 0) > 0:
                    return True
            except (TypeError, ValueError):
                continue
    return False


def _completion_passed(root: Path | str | None = None) -> bool:
    path = latest_distribution_audit_path(root)
    if not path.exists():
        return False
    try:
        audit = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    return bool(audit.get("passed")) or str(audit.get("finalDecision") or "") == "approved"


def _precheck_production_plan_inputs(root: Path | str | None = None, *, force_replan: bool = False, abandon_current: bool = False) -> None:
    paths = pipeline_paths(root)
    manual_flag = paths.manifests / "manual_review_required.flag"
    if manual_flag.exists():
        raise PlanValidationError("manual_review_required", "Cannot create a production chunk plan while manual review is required.", {"manualReviewFlag": to_portable_path(manual_flag)})
    pending_payload = read_pending(pending_path(root))
    if pending_is_unresolved(pending_payload):
        raise PlanValidationError("unresolved_pending_imagegen", "Cannot create a production chunk plan while pending-imagegen.json is unresolved.", {"pendingPath": to_portable_path(pending_path(root))})
    if _completion_passed(root):
        raise PlanValidationError("completion_already_passed", "Final completion already passed; no production chunk plan should be created.")
    queue_path = queue_jsonl_path(root)
    if not queue_path.exists():
        raise PlanValidationError("queue_missing", "Production chunk planning requires ai_image/manifests/imagegen_queue.jsonl.", {"queueJson": to_portable_path(queue_path)})
    if not read_jsonl(queue_path):
        raise PlanValidationError("queue_empty", "Production chunk planning requires a non-empty imagegen queue.", {"queueJson": to_portable_path(queue_path)})
    audit = _load_latest_audit(root)
    if _audit_has_surplus(audit):
        raise PlanValidationError("surplus_bucket_in_plan", "Cannot create a production chunk plan while distribution audit reports surplus buckets.")
    if current_state_path(root).exists() and current_plan_path(root).exists() and not force_replan:
        try:
            existing = read_current_plan(root)
            state = read_current_state(root)
            if str(state.get("chunkId") or "") == str(existing.get("chunkId") or "") and str(state.get("status") or "") in {"running", "generation_in_progress", "generation_paused"}:
                raise PlanValidationError("current_plan_not_executable", "Refusing to replace an in-progress chunk plan without --force-replan.")
        except PlanValidationError:
            raise
        except Exception:
            pass
    if current_state_path(root).exists() and current_plan_path(root).exists() and force_replan and not abandon_current:
        try:
            existing = read_current_plan(root)
            state = read_current_state(root)
            if str(state.get("chunkId") or "") == str(existing.get("chunkId") or "") and str(state.get("status") or "") in ABANDONABLE_CHUNK_STATUSES:
                raise PlanValidationError("in_progress_plan_requires_abandon_current", "Refusing to replace a partial bounded chunk without --abandon-current.")
        except PlanValidationError:
            raise
        except Exception:
            pass


def _has_capacity(capacity: Mapping[str, Any], gender: str, face_type: str, looks_band: str) -> bool:
    if looks_band == "4.4-5.0":
        return False
    return (
        int(capacity["gender"].get(gender, 0)) > 0
        and int(capacity["globalFaceType"].get(face_type, 0)) > 0
        and int(capacity["genderFaceType"].get(gender, {}).get(face_type, 0)) > 0
        and int(capacity["globalLooksLevelBand"].get(looks_band, 0)) > 0
        and int(capacity["genderLooksLevelBand"].get(gender, {}).get(looks_band, 0)) > 0
    )


def _consume_capacity(capacity: dict[str, Any], gender: str, face_type: str, looks_band: str) -> None:
    capacity["gender"][gender] = int(capacity["gender"].get(gender, 0)) - 1
    capacity["globalFaceType"][face_type] = int(capacity["globalFaceType"].get(face_type, 0)) - 1
    capacity["genderFaceType"][gender][face_type] = int(capacity["genderFaceType"].get(gender, {}).get(face_type, 0)) - 1
    capacity["globalLooksLevelBand"][looks_band] = int(capacity["globalLooksLevelBand"].get(looks_band, 0)) - 1
    capacity["genderLooksLevelBand"][gender][looks_band] = int(capacity["genderLooksLevelBand"].get(gender, {}).get(looks_band, 0)) - 1


def _materialize_asset(paths: Any, row: Mapping[str, Any], *, order: int, max_attempts: int) -> dict[str, Any]:
    profile_id = str(row.get("profileId") or "")
    shot_type = str(row.get("shotType") or "")
    asset_id = str(row.get("assetId") or "")
    if shot_type not in SHOT_ORDER:
        raise BoundedBatchExecutorError(f"Unsupported shotType in bounded chunk plan: {shot_type}")
    if not asset_id or not profile_id:
        raise BoundedBatchExecutorError("Every bounded chunk asset requires assetId and profileId.")
    prompt = str(row.get("prompt") or "")
    if not prompt:
        raise BoundedBatchExecutorError(f"Asset lacks prompt and cannot be generated deterministically: {asset_id}")
    attempt = int(row.get("attemptCount") or row.get("attempt") or 0)
    face_asset_id = f"{profile_id}__face_card__v001"
    final_path = _row_final_path(paths, row)
    has_eyewear = _row_has_eyewear(row)
    eyewear_group = _row_eyewear_group(row)
    canonical_eyewear = str(row.get("canonicalEyewear") or row.get("eyewear") or ("none" if not has_eyewear else "")).strip()
    shot_eyewear_expected = str(row.get("shotEyewearExpected") or canonical_eyewear or ("none" if not has_eyewear else "")).strip()
    return {
        "assetId": asset_id,
        "shotType": shot_type,
        "order": int(order),
        "status": "planned",
        "attempt": attempt,
        "maxAttempts": int(max_attempts),
        "prompt": prompt,
        "promptHash": str(row.get("promptHash") or ""),
        "promptBuilderVersion": str(row.get("promptBuilderVersion") or ""),
        "promptTargetingVersion": str(row.get("promptTargetingVersion") or ""),
        "hasEyewear": has_eyewear,
        "eyewearGroup": eyewear_group,
        "eyewear": str(row.get("eyewear") or canonical_eyewear).strip(),
        "canonicalEyewear": canonical_eyewear,
        "eyewearConsistencyPolicy": str(row.get("eyewearConsistencyPolicy") or "").strip(),
        "shotEyewearExpected": shot_eyewear_expected,
        "temporaryEyewearAllowed": bool(row.get("temporaryEyewearAllowed")),
        "temporaryEyewearApplied": bool(row.get("temporaryEyewearApplied")),
        "finalPath": to_portable_path(final_path),
        "rawPathPattern": to_portable_path(paths.raw / f"{asset_id}__attemptXX.png"),
        "legacyStoragePath": str(row.get("legacyStoragePath") or ""),
        "storagePath": str(row.get("storagePath") or ""),
        "requiresReferenceAssetId": None if shot_type == "face_card" else face_asset_id,
    }


def _reuse_justification_map(plan: Mapping[str, Any]) -> dict[tuple[str, str], Mapping[str, Any]]:
    values: list[Any] = list(plan.get("reuseJustifications") or [])
    for identity in plan.get("identities", []) or []:
        if isinstance(identity, Mapping):
            values.extend(identity.get("reuseJustifications") or [])
    result: dict[tuple[str, str], Mapping[str, Any]] = {}
    for row in values:
        if not isinstance(row, Mapping):
            continue
        profile_id = str(row.get("profileId") or "")
        shot_type = str(row.get("shotType") or "")
        if profile_id and shot_type:
            result[(profile_id, shot_type)] = row
    return result


def _plan_missing_shots(plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    missing: list[dict[str, Any]] = []
    for identity in plan.get("identities", []) or []:
        if not isinstance(identity, Mapping):
            continue
        profile_id = str(identity.get("profileId") or "")
        present = {str(asset.get("shotType") or "") for asset in identity.get("assets", []) or [] if isinstance(asset, Mapping)}
        for shot_type in SHOT_ORDER:
            if shot_type not in present:
                missing.append({"profileId": profile_id, "shotType": shot_type, "assetId": f"{profile_id}__{shot_type}__v001"})
    return missing


def _validate_partial_plan_policy(
    plan: Mapping[str, Any],
    *,
    root: Path | str | None = None,
    selected_assets: int,
) -> None:
    identities = [identity for identity in plan.get("identities", []) or [] if isinstance(identity, Mapping)]
    expected_assets = len(identities) * len(SHOT_ORDER)
    declared_assets = int(plan.get("selectedAssetCount") or selected_assets)
    if declared_assets != selected_assets:
        raise PlanValidationError(
            "selected_asset_count_mismatch",
            "selectedAssetCount does not match the number of materialized plan assets.",
            {"selectedAssetCount": declared_assets, "actualAssetCount": selected_assets},
        )
    missing = _plan_missing_shots(plan)
    if not missing and selected_assets >= expected_assets:
        return
    reasons: list[str] = ["unsafe_partial_plan"]
    if bool(plan.get("partialPlanAllowed")) is not True:
        reasons.append("partial_plan_not_allowed")
    if str(plan.get("planType") or "") not in PARTIAL_PLAN_TYPES:
        reasons.append("partial_plan_not_allowed")
    reuse_policy = plan.get("reusePolicy") if isinstance(plan.get("reusePolicy"), Mapping) else {}
    if bool(reuse_policy.get("allowReuseFromRejectedIdentity")):
        reasons.append("reuse_from_rejected_identity")
    if bool(reuse_policy.get("allowSilhouetteReuseWithoutApprovedFaceAnchor")):
        reasons.append("silhouette_reuse_without_approved_face_anchor")
    justifications = _reuse_justification_map(plan)
    context = _reuse_context(root) if root is not None else {}
    partial_details: list[dict[str, Any]] = []
    for item in missing:
        profile_id = str(item["profileId"])
        shot_type = str(item["shotType"])
        justification = justifications.get((profile_id, shot_type), {})
        detail = dict(item)
        if not justification:
            reasons.append("omitted_asset_without_reuse_justification")
            if shot_type in DEPENDENT_SHOTS:
                reasons.append("silhouette_reuse_without_approved_face_anchor")
        else:
            detail["reuseJustification"] = dict(justification)
            if justification.get("allowed") is not True:
                reasons.append("omitted_asset_without_reuse_justification")
            if str(justification.get("identityQaStatus") or "") == "rejected":
                reasons.append("reuse_from_rejected_identity")
            if shot_type in DEPENDENT_SHOTS and justification.get("faceAnchorApproved") is not True:
                reasons.append("silhouette_reuse_without_approved_face_anchor")
            if str(justification.get("sourceChunkStatus") or "") in {"archived", "reset", "needs_manual_review"} and str(justification.get("reason") or "") != "operator_approved_reuse":
                reasons.append("archived_chunk_asset_reuse_not_allowed")
        if context:
            identity_qa = (context.get("identityQaByProfileId") or {}).get(profile_id, {}) if isinstance(context.get("identityQaByProfileId"), Mapping) else {}
            identity_decision = _identity_qa_decision(identity_qa)
            detail["identityQaStatus"] = identity_decision or "none"
            if identity_decision == "rejected":
                reasons.append("reuse_from_rejected_identity")
            if shot_type in DEPENDENT_SHOTS:
                face_asset_id = f"{profile_id}__face_card__v001"
                face_asset_qa = (context.get("assetQaByAssetId") or {}).get(face_asset_id, {}) if isinstance(context.get("assetQaByAssetId"), Mapping) else {}
                face_file_qa = (context.get("fileQaByAssetId") or {}).get(face_asset_id, {}) if isinstance(context.get("fileQaByAssetId"), Mapping) else {}
                face_anchor_approved = _asset_visual_decision(face_asset_qa) == "approved" and _file_qa_passed(face_file_qa)
                detail["faceAnchorAssetId"] = face_asset_id
                detail["faceAnchorApproved"] = face_anchor_approved
                if not face_anchor_approved:
                    reasons.append("silhouette_reuse_without_approved_face_anchor")
        partial_details.append(detail)
    unique_reasons = list(dict.fromkeys(reasons))
    priority = [
        "reuse_from_rejected_identity",
        "silhouette_reuse_without_approved_face_anchor",
        "omitted_asset_without_reuse_justification",
        "partial_plan_not_allowed",
        "archived_chunk_asset_reuse_not_allowed",
        "selected_asset_count_mismatch",
        "unsafe_partial_plan",
    ]
    reason_code = next((reason for reason in priority if reason in unique_reasons), unique_reasons[0])
    raise PlanValidationError(
        reason_code,
        "Unsafe partial bounded chunk plan.",
        {
            "reasons": unique_reasons,
            "partialIdentities": partial_details,
            "selectedAssetCount": selected_assets,
            "expectedAssetCount": expected_assets,
        },
    )


def validate_chunk_plan(plan: Mapping[str, Any], *, root: Path | str | None = None) -> None:
    if plan.get("schemaVersion") != PLAN_SCHEMA_VERSION:
        raise PlanValidationError("current_plan_not_executable", f"Unexpected bounded chunk plan schema: {plan.get('schemaVersion')}")
    identities = plan.get("identities")
    if not isinstance(identities, list):
        raise PlanValidationError("current_plan_not_executable", "Bounded chunk plan requires identities[].")
    if int(plan.get("selectedIdentityCount") or len(identities)) > int(plan.get("maxIdentities") or MAX_CHUNK_IDENTITIES):
        raise PlanValidationError("plan_identity_limit_exceeded", "Bounded chunk plan exceeds maxIdentities.")
    asset_ids: set[str] = set()
    final_paths: set[str] = set()
    selected_assets = 0
    active_prompt_targeting_version = _active_prompt_targeting_version()
    for identity in identities:
        if not isinstance(identity, Mapping):
            raise PlanValidationError("current_plan_not_executable", "Bounded chunk plan identities[] must contain objects.")
        if identity.get("targetLooksLevelBand") == "4.4-5.0":
            raise PlanValidationError("over_level_bucket_in_plan", "Bounded chunk plan includes forbidden looksLevelBand 4.4-5.0.")
        assets = identity.get("assets")
        if not isinstance(assets, list):
            raise PlanValidationError("current_plan_not_executable", "Bounded chunk plan identity requires assets[].")
        face_asset = next((asset for asset in assets if isinstance(asset, Mapping) and str(asset.get("shotType") or "") == "face_card"), {})
        exhausted_face = face_card_exhaustion([face_asset], max_attempts=int(face_asset.get("maxAttempts") or plan.get("maxAttempts") or MAX_ATTEMPTS))
        if exhausted_face:
            raise PlanValidationError(
                "face_card_max_attempts_exhausted",
                f"Bounded chunk plan includes exhausted face_card asset: {exhausted_face['assetId']}",
                {"reasons": ["face_card_max_attempts_exhausted"], "candidate": exhausted_face},
            )
        sorted_assets = sorted(assets, key=lambda item: int(item.get("order") or 99))
        shot_order = [str(asset.get("shotType") or "") for asset in sorted_assets]
        if shot_order != sorted(shot_order, key=lambda shot: SHOT_ORDER.index(shot) if shot in SHOT_ORDER else 99):
            raise PlanValidationError("current_plan_not_executable", "Bounded chunk assets are not ordered by required shot order.")
        face_id = str(next((asset.get("assetId") for asset in assets if asset.get("shotType") == "face_card"), "") or "")
        for asset in sorted_assets:
            selected_assets += 1
            asset_id = str(asset.get("assetId") or "")
            final_path = str(asset.get("finalPath") or "")
            if not asset_id:
                raise PlanValidationError("current_plan_not_executable", "Bounded chunk plan contains blank assetId.")
            if asset_id in asset_ids:
                raise PlanValidationError("duplicate_asset_id", f"Duplicate assetId in bounded chunk plan: {asset_id}", {"assetId": asset_id})
            asset_ids.add(asset_id)
            if final_path in final_paths:
                raise PlanValidationError("duplicate_final_path", f"Duplicate finalPath in bounded chunk plan: {final_path}", {"finalPath": final_path})
            final_paths.add(final_path)
            shot_type = str(asset.get("shotType") or "")
            if shot_type in DEPENDENT_SHOTS and str(asset.get("requiresReferenceAssetId") or "") != face_id:
                raise PlanValidationError("missing_reference_asset", f"{shot_type} must reference the same identity face_card asset.", {"assetId": asset_id})
            if not final_path:
                raise PlanValidationError("current_plan_not_executable", f"Missing finalPath for bounded chunk asset: {asset_id}")
            if not asset.get("prompt"):
                raise PlanValidationError("current_plan_not_executable", f"Missing prompt for bounded chunk asset: {asset_id}")
            if not asset.get("promptHash"):
                raise PlanValidationError("current_plan_not_executable", f"Missing promptHash for bounded chunk asset: {asset_id}")
            if active_prompt_targeting_version and str(asset.get("promptTargetingVersion") or "") != active_prompt_targeting_version:
                raise PlanValidationError(
                    "stale_prompt_targeting_version",
                    f"Bounded chunk asset promptTargetingVersion does not match active prompt builder: {asset_id}",
                    {
                        "assetId": asset_id,
                        "assetPromptTargetingVersion": str(asset.get("promptTargetingVersion") or ""),
                        "activePromptTargetingVersion": active_prompt_targeting_version,
                    },
                )
            if str(asset.get("promptHash") or "") != prompt_hash(str(asset.get("prompt") or "")):
                raise PlanValidationError("stale_prompt_hash", f"promptHash does not match prompt for bounded chunk asset: {asset_id}", {"assetId": asset_id})
    if selected_assets > int(plan.get("maxAssets") or MAX_CHUNK_ASSETS):
        raise PlanValidationError("plan_asset_limit_exceeded", "Bounded chunk plan exceeds maxAssets.")
    _validate_partial_plan_policy(plan, root=root, selected_assets=selected_assets)


def _write_plan_and_state(root: Path | str | None, plan: Mapping[str, Any], *, archive_existing: bool = False) -> dict[str, Any]:
    archived = _archive_current_plan_state(root) if archive_existing else {}
    created_at = str(plan.get("createdAt") or now_utc())
    plan_hash = str(plan.get("planHash") or _plan_hash(plan))
    state = {
        "schemaVersion": STATE_SCHEMA_VERSION,
        "chunkId": plan["chunkId"],
        "planHash": plan_hash,
        "status": "dry_run" if str(plan.get("planMode") or "") == "dry_run" else "planned",
        "currentAssetId": None,
        "completedAssetIds": [],
        "failedAssetIds": [],
        "assetStates": {
            str(asset["assetId"]): str(asset.get("status") or "planned")
            for identity in plan.get("identities", [])
            for asset in identity.get("assets", [])
        },
        "identityStates": {
            str(identity["profileId"]): str(identity.get("status") or "planned")
            for identity in plan.get("identities", [])
        },
        "activeVisualQaComplete": False,
        "distributionAuditComplete": False,
        "startedAt": "",
        "createdAt": created_at,
        "updatedAt": now_utc(),
    }
    plan_to_write = dict(plan)
    plan_to_write["planHash"] = plan_hash
    plan_to_write["updatedAt"] = now_utc()
    if archived:
        plan_to_write["archivedPreviousPlan"] = archived
    _write_json(current_plan_path(root), plan_to_write)
    _write_json(current_state_path(root), state)
    if str(plan_to_write.get("planMode") or "") == "dry_run":
        dry_run_dir = pipeline_paths(root).reports / "chunks" / "dry_run_plans"
        dry_run_dir.mkdir(parents=True, exist_ok=True)
        _write_json(dry_run_dir / f"{plan_to_write['chunkId']}.json", plan_to_write)
    report = _base_report(root, plan_to_write, state)
    _write_json(chunk_report_path(root, str(plan["chunkId"])), report)
    _append_event(root, str(plan["chunkId"]), event_type="plan_created", to_status="planned", output_path=to_portable_path(current_plan_path(root)))
    return state


def create_chunk_plan(
    *,
    root: Path | str | None = None,
    max_identities: int = MAX_CHUNK_IDENTITIES,
    max_assets: int = MAX_CHUNK_ASSETS,
    refresh_audit: bool = False,
    dry_run: bool = False,
    production: bool = False,
    force_replan: bool = False,
    abandon_current: bool = False,
    abandon_reason: str = "fresh_production_replan_after_distribution_audit",
    max_attempts: int = MAX_ATTEMPTS,
    face_type: str | None = None,
    looks_level_band: str | None = None,
    gender: str | None = None,
    has_eyewear: Any = None,
    eyewear_group: str | None = None,
    require_eyewear_mix: bool = False,
    require_focused_match: bool = False,
) -> dict[str, Any]:
    paths = pipeline_paths(root)
    ensure_base_dirs(paths)
    max_identities = min(MAX_CHUNK_IDENTITIES, int(max_identities))
    max_assets = min(MAX_CHUNK_ASSETS, int(max_assets))
    plan_mode = "dry_run" if dry_run and not production else "production"
    dry_run = plan_mode == "dry_run"
    if plan_mode == "production":
        _precheck_production_plan_inputs(root, force_replan=force_replan, abandon_current=abandon_current)
    replacement_chunk_id = _replacement_chunk_id(root)
    should_abandon_current = plan_mode == "production" and abandon_current and _current_chunk_abandonable(root)
    excluded_profiles = _current_plan_profile_ids(root) if should_abandon_current else set()
    focus_face_type = str(face_type or "").strip()
    focus_looks_level_band = str(looks_level_band or "").strip()
    focus_gender = str(gender or "").strip()
    try:
        focus_has_eyewear = _normalize_has_eyewear_filter(has_eyewear)
    except ValueError as exc:
        raise PlanValidationError("invalid_focused_filter", str(exc), {"hasEyewear": has_eyewear}) from exc
    focus_eyewear_group = str(eyewear_group or "").strip()
    selection = select_distribution_buckets(
        root=root,
        refresh_audit=refresh_audit,
        max_identities=max_identities,
        max_attempts=max_attempts,
        exclude_profile_ids=excluded_profiles,
        face_type=face_type,
        looks_level_band=looks_level_band,
        gender=gender,
        has_eyewear=focus_has_eyewear,
        eyewear_group=eyewear_group,
        require_eyewear_mix=require_eyewear_mix,
    )
    allow_partial_salvage = plan_mode == "production" and _allow_partial_salvage_plan()
    reuse_context = _reuse_context(root) if allow_partial_salvage else {}
    audit = _load_latest_audit(root)
    capacity = _capacity_from_audit(audit)
    all_rows = _active_generation_rows(root)
    rows_by_profile = _group_by_profile(all_rows)
    selected: list[dict[str, Any]] = []
    selected_asset_count = 0
    reuse_justifications: list[dict[str, Any]] = []

    for selected_identity in selection.get("selectedIdentities", []):
        profile_id = str(selected_identity.get("profileId") or "")
        profile_rows = rows_by_profile.get(profile_id, [])
        if not profile_rows:
            continue
        anchor = profile_rows[0]
        gender = str(anchor.get("gender") or "")
        face_type = _target_face(anchor)
        looks_band = _target_looks(anchor)
        identity_has_eyewear = _row_has_eyewear(anchor)
        identity_eyewear_group = _row_eyewear_group(anchor)
        if gender not in {"female", "male"} or not _has_capacity(capacity, gender, face_type, looks_band):
            continue
        by_shot = {str(row.get("shotType") or ""): row for row in profile_rows}
        materialized_assets: list[dict[str, Any]] = []
        identity_reuse_justifications: list[dict[str, Any]] = []
        for index, shot_type in enumerate(SHOT_ORDER, start=1):
            row = by_shot.get(shot_type)
            if not row:
                raise BoundedBatchExecutorError(f"Selected identity lacks required shot {shot_type}: {profile_id}")
            should_generate = True
            if plan_mode == "dry_run":
                should_generate = _asset_needs_generation(row)
            elif allow_partial_salvage and is_asset_reusable_for_new_plan(str(row.get("assetId") or ""), profile_id, shot_type, reuse_context):
                should_generate = False
                asset_id = str(row.get("assetId") or "")
                identity_qa = (reuse_context.get("identityQaByProfileId") or {}).get(profile_id, {}) if isinstance(reuse_context.get("identityQaByProfileId"), Mapping) else {}
                face_asset_id = f"{profile_id}__face_card__v001" if shot_type in DEPENDENT_SHOTS else None
                face_asset_qa = (reuse_context.get("assetQaByAssetId") or {}).get(face_asset_id or "", {}) if isinstance(reuse_context.get("assetQaByAssetId"), Mapping) else {}
                justification = {
                    "assetId": asset_id,
                    "profileId": profile_id,
                    "shotType": shot_type,
                    "reason": "valid_face_anchor_salvage" if shot_type in DEPENDENT_SHOTS else "operator_approved_reuse",
                    "fileQaPassed": True,
                    "assetVisualQaApproved": True,
                    "identityQaStatus": _identity_qa_decision(identity_qa) or "none",
                    "faceAnchorAssetId": face_asset_id,
                    "faceAnchorApproved": _asset_visual_decision(face_asset_qa) == "approved" if face_asset_id else True,
                    "sourceChunkId": str(row.get("chunkId") or ""),
                    "sourceChunkStatus": str(row.get("chunkStatus") or ""),
                    "allowed": True,
                }
                reuse_justifications.append(justification)
                identity_reuse_justifications.append(justification)
            if should_generate:
                materialized_assets.append(_materialize_asset(paths, row, order=index, max_attempts=max_attempts))
        if not materialized_assets:
            continue
        if selected_asset_count + len(materialized_assets) > max_assets:
            break
        _consume_capacity(capacity, gender, face_type, looks_band)
        selected_asset_count += len(materialized_assets)
        source = "reserve" if bool(anchor.get("isReserve")) or str(anchor.get("identityScope") or "") == "reserve" else "primary"
        selected.append(
            {
                "profileId": profile_id,
                "gender": gender,
                "numericId": str(anchor.get("numericId") or _profile_number(profile_id)),
                "targetFaceType": face_type,
                "targetLooksLevelBand": looks_band,
                "hasEyewear": identity_has_eyewear,
                "eyewearGroup": identity_eyewear_group,
                "eyewear": str(anchor.get("eyewear") or "").strip(),
                "canonicalEyewear": str(anchor.get("canonicalEyewear") or "").strip(),
                "source": source,
                "status": "planned",
                "assets": materialized_assets,
                "reuseJustifications": identity_reuse_justifications,
            }
        )
        if len(selected) >= max_identities:
            break

    focused_enabled = bool(
        focus_face_type
        or focus_looks_level_band
        or focus_gender
        or focus_has_eyewear is not None
        or focus_eyewear_group
        or require_eyewear_mix
    )
    if require_focused_match and focused_enabled:
        focused_failures: list[dict[str, Any]] = []
        for identity in selected:
            if focus_face_type and str(identity.get("targetFaceType") or "") != focus_face_type:
                focused_failures.append({"profileId": identity.get("profileId"), "reason": "face_type_mismatch"})
            if focus_looks_level_band and str(identity.get("targetLooksLevelBand") or "") != focus_looks_level_band:
                focused_failures.append({"profileId": identity.get("profileId"), "reason": "looks_level_band_mismatch"})
            if focus_gender and str(identity.get("gender") or "") != focus_gender:
                focused_failures.append({"profileId": identity.get("profileId"), "reason": "gender_mismatch"})
            if focus_has_eyewear is not None and bool(identity.get("hasEyewear")) != focus_has_eyewear:
                focused_failures.append({"profileId": identity.get("profileId"), "reason": "has_eyewear_mismatch"})
            if focus_eyewear_group and str(identity.get("eyewearGroup") or "") != focus_eyewear_group:
                focused_failures.append({"profileId": identity.get("profileId"), "reason": "eyewear_group_mismatch"})
        if require_eyewear_mix and not (
            any(bool(identity.get("hasEyewear")) for identity in selected)
            and any(not bool(identity.get("hasEyewear")) for identity in selected)
        ):
            focused_failures.append({"reason": "eyewear_mix_missing"})
        expected_assets = len(selected) * len(SHOT_ORDER)
        if focused_failures or len(selected) < max_identities or selected_asset_count != expected_assets:
            raise PlanValidationError(
                "focused_selection_insufficient_candidates",
                "Focused bounded chunk selection could not produce a complete strict-match plan.",
                {
                    "focusedFilters": {
                        "faceType": focus_face_type,
                        "looksLevelBand": focus_looks_level_band,
                        "gender": focus_gender,
                        "hasEyewear": focus_has_eyewear,
                        "eyewearGroup": focus_eyewear_group,
                        "requireEyewearMix": bool(require_eyewear_mix),
                    },
                    "selectedIdentityCount": len(selected),
                    "requestedIdentityCount": max_identities,
                    "selectedAssetCount": selected_asset_count,
                    "expectedAssetCount": expected_assets,
                    "focusedFailures": focused_failures,
                },
            )

    chunk_id = replacement_chunk_id
    plan = {
        "schemaVersion": PLAN_SCHEMA_VERSION,
        "chunkId": chunk_id,
        "createdAt": now_utc(),
        "updatedAt": now_utc(),
        "dryRun": bool(dry_run),
        "planMode": plan_mode,
        "planType": PLAN_TYPE_PARTIAL_SALVAGE if reuse_justifications else PLAN_TYPE_FULL_IDENTITY_GENERATION,
        "partialPlanAllowed": bool(reuse_justifications),
        "reusePolicy": {
            **DEFAULT_REUSE_POLICY,
            "allowAssetReuse": bool(reuse_justifications),
            "allowSilhouetteReuseWithoutApprovedFaceAnchor": _allow_silhouette_reuse_without_face_anchor(),
            "allowReuseFromRejectedIdentity": _allow_reuse_from_rejected_identity(),
        },
        "reuseJustifications": reuse_justifications,
        "executable": not dry_run,
        "status": "dry_run" if dry_run else "planned",
        "maxIdentities": max_identities,
        "maxAssets": max_assets,
        "selectedIdentityCount": len(selected),
        "selectedAssetCount": selected_asset_count,
        "selectionSource": "latest_distribution_audit",
        "focusedSelection": {
            "enabled": focused_enabled,
            "faceType": focus_face_type,
            "looksLevelBand": focus_looks_level_band,
            "gender": focus_gender,
            "hasEyewear": focus_has_eyewear,
            "eyewearGroup": focus_eyewear_group,
            "requireEyewearMix": bool(require_eyewear_mix),
            "containsEyewearIdentity": any(bool(identity.get("hasEyewear")) for identity in selected),
            "containsNoEyewearIdentity": any(not bool(identity.get("hasEyewear")) for identity in selected),
            "strictFocusedMatch": bool(require_focused_match),
        },
        "root": to_portable_path(paths.root),
        "targetsJson": to_portable_path(target_config_path(root)),
        "distributionAuditJson": to_portable_path(latest_distribution_audit_path(root)),
        "queueJson": to_portable_path(queue_jsonl_path(root)),
        "assetManifestJson": to_portable_path(asset_manifest_jsonl_path(root)),
        "inputHashes": _input_hashes(root),
        "inputMtimes": _input_mtimes(root),
        "allowedBuckets": selection.get("allowedBuckets", []),
        "forbiddenBuckets": selection.get("forbiddenBuckets", []),
        "skippedExhaustedCandidates": selection.get("skippedExhaustedCandidates", []),
        "remainingDeficitsAtPlanTime": _remaining_deficits(audit),
        "identities": selected,
        "initialProgress": _progress_snapshot(root),
    }
    plan["planHash"] = _plan_hash(plan)
    validate_chunk_plan(plan, root=root)
    if plan_mode == "production" and not selected and not _completion_passed(root):
        flag = write_manual_review_flag(root, "no_deficit_assets_available", {"chunkId": chunk_id})
        raise PlanValidationError("no_deficit_assets_available", "Distribution deficits remain, but no eligible bounded chunk assets are available.", {"manualReviewFlag": to_portable_path(flag)})
    abandoned: dict[str, Any] = {}
    if should_abandon_current:
        abandoned = _abandon_current_chunk(root, replacement_chunk_id=chunk_id, reason=abandon_reason)
        if abandoned:
            plan["abandonedPreviousChunk"] = abandoned
    _write_plan_and_state(root, plan, archive_existing=plan_mode == "production" or current_plan_path(root).exists())
    return plan


def _parse_iso_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _file_mtime_newer_than(path: Path, timestamp: datetime | None) -> bool:
    if not path.exists() or timestamp is None:
        return False
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc) > timestamp


def _selected_profile_ids(plan: Mapping[str, Any]) -> set[str]:
    return {str(identity.get("profileId") or "") for identity in plan.get("identities", []) if isinstance(identity, Mapping)}


def _approved_profile_ids(root: Path | str | None = None) -> set[str]:
    rows = read_jsonl(pipeline_paths(root).manifests / "approved_identity_manifest.jsonl")
    return {str(row.get("profileId") or "") for row in rows if row.get("profileId")}


def _surplus_bucket_match(audit: Mapping[str, Any], gender: str, face_type: str, looks_band: str) -> bool:
    global_face = audit.get("globalFaceTypeSurpluses") if isinstance(audit.get("globalFaceTypeSurpluses"), Mapping) else {}
    global_looks = audit.get("globalLooksLevelBandSurpluses") if isinstance(audit.get("globalLooksLevelBandSurpluses"), Mapping) else {}
    gender_face_all = audit.get("genderFaceTypeSurpluses") if isinstance(audit.get("genderFaceTypeSurpluses"), Mapping) else {}
    gender_looks_all = audit.get("genderLooksLevelBandSurpluses") if isinstance(audit.get("genderLooksLevelBandSurpluses"), Mapping) else {}
    gender_face = gender_face_all.get(gender, {}) if isinstance(gender_face_all.get(gender, {}), Mapping) else {}
    gender_looks = gender_looks_all.get(gender, {}) if isinstance(gender_looks_all.get(gender, {}), Mapping) else {}
    return (
        int(global_face.get(face_type) or 0) > 0
        or int(global_looks.get(looks_band) or 0) > 0
        or int(gender_face.get(face_type) or 0) > 0
        or int(gender_looks.get(looks_band) or 0) > 0
    )


def _state_matches_plan(root: Path | str | None, plan: Mapping[str, Any], reasons: list[str]) -> dict[str, Any]:
    if not current_state_path(root).exists():
        reasons.append("state_plan_mismatch")
        return {}
    try:
        state = read_current_state(root)
    except Exception:
        reasons.append("state_plan_mismatch")
        return {}
    if str(state.get("chunkId") or "") != str(plan.get("chunkId") or ""):
        reasons.append("state_plan_mismatch")
    if str(state.get("planHash") or "") != str(plan.get("planHash") or ""):
        reasons.append("state_plan_mismatch")
    return state


def _append_stale_reasons(root: Path | str | None, plan: Mapping[str, Any], reasons: list[str]) -> None:
    current_hashes = _input_hashes(root)
    planned_hashes = plan.get("inputHashes") if isinstance(plan.get("inputHashes"), Mapping) else {}
    for key, current_hash in current_hashes.items():
        if planned_hashes.get(key) != current_hash:
            reasons.append(f"input_hash_changed:{key}")
    created_at = _parse_iso_timestamp(plan.get("createdAt"))
    planned_mtimes = plan.get("inputMtimes") if isinstance(plan.get("inputMtimes"), Mapping) else {}
    for label, path in (
        ("distributionAuditJson", latest_distribution_audit_path(root)),
        ("queueJson", queue_jsonl_path(root)),
        ("assetManifestJson", asset_manifest_jsonl_path(root)),
    ):
        planned_mtime = planned_mtimes.get(f"{label}Mtime")
        current_mtime = _mtime_value(path)
        if planned_mtime is not None and current_mtime is not None:
            if float(current_mtime) > float(planned_mtime) + 0.001:
                reasons.append(f"input_mtime_newer:{label}")
        elif _file_mtime_newer_than(path, created_at):
            reasons.append(f"input_mtime_newer:{label}")
    manual_flag = pipeline_paths(root).manifests / "manual_review_required.flag"
    if _file_mtime_newer_than(manual_flag, created_at):
        reasons.append("manual_review_required_newer_than_plan")
    approved_profiles = _approved_profile_ids(root)
    selected_approved = sorted(_selected_profile_ids(plan) & approved_profiles)
    if selected_approved:
        reasons.append("selected_identity_already_approved")


def _append_bucket_validation_reasons(root: Path | str | None, plan: Mapping[str, Any], reasons: list[str]) -> None:
    audit = _load_latest_audit(root)
    capacity = _capacity_from_audit(audit)
    for identity in plan.get("identities", []) or []:
        if not isinstance(identity, Mapping):
            continue
        gender = str(identity.get("gender") or "")
        face_type = str(identity.get("targetFaceType") or "")
        looks_band = str(identity.get("targetLooksLevelBand") or "")
        if looks_band == "4.4-5.0":
            reasons.append("over_level_bucket_in_plan")
            continue
        if _surplus_bucket_match(audit, gender, face_type, looks_band):
            reasons.append("surplus_bucket_in_plan")
            continue
        if not _has_capacity(capacity, gender, face_type, looks_band):
            reasons.append("quota_full_bucket_in_plan")
            continue
        _consume_capacity(capacity, gender, face_type, looks_band)


def _validation_failure_payload(reason_code: str, reasons: list[str], extra: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return {
        "schemaVersion": "seolleyeon_bounded_chunk_plan_validation_v3",
        "valid": False,
        "canRun": False,
        "reasonCode": reason_code,
        "reasons": reasons,
        **dict(extra or {}),
    }


def validate_current_chunk_plan(*, root: Path | str | None = None, strict: bool = True) -> dict[str, Any]:
    reasons: list[str] = []
    plan_path = current_plan_path(root)
    if not plan_path.exists():
        payload = _validation_failure_payload("current_plan_missing", ["current_plan_missing"], {"planPath": to_portable_path(plan_path)})
        if strict:
            raise PlanValidationError("current_plan_missing", "current_chunk_plan.json does not exist.", payload)
        return payload
    plan = read_current_plan(root)
    state = _state_matches_plan(root, plan, reasons)
    reason_code = ""
    if plan.get("dryRun") is True or str(plan.get("planMode") or "") == "dry_run":
        reasons.append("dry_run_plan_not_executable")
        reason_code = reason_code or "dry_run_plan_not_executable"
    if plan.get("executable") is not True:
        reasons.append("current_plan_not_executable")
        reason_code = reason_code or "current_plan_not_executable"
    if str(plan.get("planMode") or "") != "production":
        reasons.append("current_plan_not_executable")
        reason_code = reason_code or "current_plan_not_executable"
    if str(plan.get("status") or state.get("status") or "") not in EXECUTABLE_CHUNK_STATUSES:
        reasons.append("current_plan_not_executable")
        reason_code = reason_code or "current_plan_not_executable"
    try:
        validate_chunk_plan(plan, root=root)
    except PlanValidationError as exc:
        detail_reasons = exc.details.get("reasons") if isinstance(exc.details, Mapping) else None
        if isinstance(detail_reasons, Sequence) and not isinstance(detail_reasons, (str, bytes)):
            reasons.extend(str(reason) for reason in detail_reasons)
        else:
            reasons.append(exc.reason_code)
        reason_code = reason_code or exc.reason_code
    manual_flag = pipeline_paths(root).manifests / "manual_review_required.flag"
    if manual_flag.exists():
        reasons.append("manual_review_required")
        reason_code = reason_code or "manual_review_required"
    pending_payload = read_pending(pending_path(root))
    if pending_is_unresolved(pending_payload):
        reasons.append("unresolved_pending_imagegen")
        reason_code = reason_code or "unresolved_pending_imagegen"
    _append_stale_reasons(root, plan, reasons)
    _append_bucket_validation_reasons(root, plan, reasons)
    if any(reason.startswith("input_hash_changed:") or reason.startswith("input_mtime_newer:") for reason in reasons):
        reason_code = reason_code or "stale_plan"
    if "state_plan_mismatch" in reasons:
        reason_code = reason_code or "state_plan_mismatch"
    if "surplus_bucket_in_plan" in reasons:
        reason_code = reason_code or "surplus_bucket_in_plan"
    if "quota_full_bucket_in_plan" in reasons:
        reason_code = reason_code or "quota_full_bucket_in_plan"
    if "over_level_bucket_in_plan" in reasons:
        reason_code = reason_code or "over_level_bucket_in_plan"
    if "selected_identity_already_approved" in reasons or "manual_review_required_newer_than_plan" in reasons:
        reason_code = reason_code or "stale_plan"
    if int(plan.get("selectedIdentityCount") or 0) <= 0:
        reasons.append("no_selected_identities")
        reason_code = reason_code or "current_plan_not_executable"
    if int(plan.get("selectedAssetCount") or 0) <= 0:
        reasons.append("no_selected_assets")
        reason_code = reason_code or "current_plan_not_executable"
    unique_reasons = list(dict.fromkeys(reasons))
    if unique_reasons:
        payload = _validation_failure_payload(reason_code or "current_plan_not_executable", unique_reasons, {"chunkId": plan.get("chunkId"), "planPath": to_portable_path(plan_path)})
        if strict:
            raise PlanValidationError(payload["reasonCode"], "Current bounded chunk plan is not executable.", payload)
        return payload
    return {
        "schemaVersion": "seolleyeon_bounded_chunk_plan_validation_v3",
        "valid": True,
        "canRun": True,
        "reasonCode": "",
        "reasons": [],
        "chunkId": plan.get("chunkId"),
        "planPath": to_portable_path(plan_path),
        "statePath": to_portable_path(current_state_path(root)),
    }


def _replace_plan_asset(plan: dict[str, Any], asset_id: str, updates: Mapping[str, Any]) -> None:
    for identity in plan.get("identities", []):
        for asset in identity.get("assets", []):
            if str(asset.get("assetId") or "") == asset_id:
                asset.update(dict(updates))


def _replace_plan_identity(plan: dict[str, Any], profile_id: str, updates: Mapping[str, Any]) -> None:
    for identity in plan.get("identities", []):
        if str(identity.get("profileId") or "") == profile_id:
            identity.update(dict(updates))


def _save_plan_state(root: Path | str | None, plan: Mapping[str, Any], state: Mapping[str, Any]) -> None:
    _write_json(current_plan_path(root), plan)
    _write_json(current_state_path(root), state)
    _write_json(chunk_report_path(root, str(plan["chunkId"])), _base_report(root, plan, state))


def _transition_chunk(root: Path | str | None, plan: dict[str, Any], state: dict[str, Any], to_status: str, *, reason: str = "") -> None:
    old = str(state.get("status") or "")
    state["status"] = to_status
    state["updatedAt"] = now_utc()
    if not state.get("startedAt") and to_status == "running":
        state["startedAt"] = now_utc()
    plan["status"] = to_status
    _append_event(root, str(plan["chunkId"]), event_type="chunk_status", from_status=old, to_status=to_status, reason=reason)
    _save_plan_state(root, plan, state)


def _transition_asset(
    root: Path | str | None,
    plan: dict[str, Any],
    state: dict[str, Any],
    asset_id: str,
    to_status: str,
    *,
    profile_id: str = "",
    shot_type: str = "",
    reason: str = "",
    command: Sequence[str] | None = None,
    return_code: int | None = None,
    output_path: str = "",
) -> None:
    old = str(state.setdefault("assetStates", {}).get(asset_id) or "")
    state["assetStates"][asset_id] = to_status
    state["currentAssetId"] = asset_id if to_status not in ASSET_TERMINAL_STATUSES else ""
    state["updatedAt"] = now_utc()
    _replace_plan_asset(plan, asset_id, {"status": to_status})
    _append_event(
        root,
        str(plan["chunkId"]),
        event_type="asset_status",
        profile_id=profile_id,
        asset_id=asset_id,
        shot_type=shot_type,
        from_status=old,
        to_status=to_status,
        reason=reason,
        command=command,
        return_code=return_code,
        output_path=output_path,
    )
    _save_plan_state(root, plan, state)


def _transition_identity(root: Path | str | None, plan: dict[str, Any], state: dict[str, Any], profile_id: str, to_status: str, *, reason: str = "") -> None:
    old = str(state.setdefault("identityStates", {}).get(profile_id) or "")
    state["identityStates"][profile_id] = to_status
    state["updatedAt"] = now_utc()
    _replace_plan_identity(plan, profile_id, {"status": to_status})
    _append_event(root, str(plan["chunkId"]), event_type="identity_status", profile_id=profile_id, from_status=old, to_status=to_status, reason=reason)
    _save_plan_state(root, plan, state)


def _base_report(root: Path | str | None, plan: Mapping[str, Any], state: Mapping[str, Any]) -> dict[str, Any]:
    snapshot = _progress_snapshot(root)
    initial = plan.get("initialProgress") if isinstance(plan.get("initialProgress"), Mapping) else {}
    return {
        "schemaVersion": REPORT_SCHEMA_VERSION,
        "chunkId": plan.get("chunkId", ""),
        "status": state.get("status", plan.get("status", "")),
        "chunk_unattended_verification": "PASS" if state.get("status") in {"generation_complete", "file_qa_complete", "active_visual_qa_complete", "distribution_audit_complete", "finalized"} else "PENDING",
        "chunk_qa_complete": bool(state.get("activeVisualQaComplete")),
        "chunk_distribution_updated": bool(state.get("distributionAuditComplete")),
        "chunk_new_generated_assets": int(state.get("generatedAssets", 0)),
        "chunk_new_recovered_assets": int(state.get("recoveredAssets", 0)),
        "chunk_new_file_qa_passed_assets": sum(1 for value in (state.get("assetStates") or {}).values() if value == "file_qa_passed"),
        "chunk_new_visual_approved_assets": max(0, int(snapshot.get("approvedAssetCount", 0)) - int(initial.get("approvedAssetCount", 0))),
        "chunk_new_approved_identities": max(0, int(snapshot.get("approvedIdentityCount", 0)) - int(initial.get("approvedIdentityCount", 0))),
        "chunk_new_needs_review_identities": int(snapshot.get("needsReviewIdentityCount", 0)),
        "chunk_new_rejected_identities": max(0, int(snapshot.get("rejectedIdentityCount", 0)) - int(initial.get("rejectedIdentityCount", 0))),
        "selectedIdentityCount": plan.get("selectedIdentityCount", 0),
        "selectedAssetCount": plan.get("selectedAssetCount", 0),
        "remainingDeficits": snapshot.get("remainingDeficits", {}),
        "surplusBuckets": snapshot.get("surplusBuckets", []),
        "updatedAt": now_utc(),
    }


def _abandon_current_chunk(
    root: Path | str | None,
    *,
    replacement_chunk_id: str,
    reason: str,
) -> dict[str, Any]:
    if not current_plan_path(root).exists() or not current_state_path(root).exists():
        return {}
    plan = read_current_plan(root)
    state = read_current_state(root)
    old_chunk_id = str(plan.get("chunkId") or state.get("chunkId") or "")
    if not old_chunk_id or old_chunk_id == replacement_chunk_id:
        return {}
    abandoned_at = now_utc()
    old_report_dir = chunk_report_dir(root, old_chunk_id)
    old_report_dir.mkdir(parents=True, exist_ok=True)
    _write_json(old_report_dir / "abandoned_current_chunk_plan.json", plan)
    _write_json(old_report_dir / "abandoned_current_chunk_state.json", state)
    old_status = str(state.get("status") or plan.get("status") or "")

    rows = _abandoned_chunk_rows(root)
    manifest_rows: list[dict[str, Any]] = []
    asset_states = state.get("assetStates") if isinstance(state.get("assetStates"), Mapping) else {}
    identity_states = state.get("identityStates") if isinstance(state.get("identityStates"), Mapping) else {}
    for identity in plan.get("identities", []) or []:
        if not isinstance(identity, Mapping):
            continue
        profile_id = str(identity.get("profileId") or "")
        for asset in identity.get("assets", []) or []:
            if not isinstance(asset, Mapping):
                continue
            asset_id = str(asset.get("assetId") or "")
            final_path = str(asset.get("finalPath") or "")
            manifest_rows.append(
                {
                    "schemaVersion": ABANDONED_CHUNK_SCHEMA_VERSION,
                    "abandonedChunkId": old_chunk_id,
                    "replacementChunkId": replacement_chunk_id,
                    "abandonedAt": abandoned_at,
                    "abandonReason": reason,
                    "profileId": profile_id,
                    "identityStatus": str(identity_states.get(profile_id) or identity.get("status") or ""),
                    "assetId": asset_id,
                    "shotType": str(asset.get("shotType") or ""),
                    "assetStatus": str(asset_states.get(asset_id) or asset.get("status") or ""),
                    "finalPath": final_path,
                    "finalPathExists": bool(final_path and Path(final_path).exists()),
                    "rawPathPattern": str(asset.get("rawPathPattern") or ""),
                }
            )
    write_jsonl(abandoned_chunk_manifest_path(root), rows + manifest_rows)

    plan.update(
        {
            "status": "abandoned",
            "executable": False,
            "abandonedAt": abandoned_at,
            "abandonReason": reason,
            "replacementChunkId": replacement_chunk_id,
        }
    )
    state.update(
        {
            "status": "abandoned",
            "currentAssetId": None,
            "updatedAt": abandoned_at,
            "abandonedAt": abandoned_at,
            "abandonReason": reason,
            "replacementChunkId": replacement_chunk_id,
        }
    )
    _append_event(root, old_chunk_id, event_type="chunk_abandoned", from_status=old_status, to_status="abandoned", reason=reason, output_path=to_portable_path(abandoned_chunk_manifest_path(root)))
    _write_json(current_plan_path(root), plan)
    _write_json(current_state_path(root), state)
    report = _base_report(root, plan, state)
    report.update(
        {
            "abandonedAt": abandoned_at,
            "abandonReason": reason,
            "replacementChunkId": replacement_chunk_id,
            "abandonedAssetCount": len(manifest_rows),
            "abandonedChunkManifest": to_portable_path(abandoned_chunk_manifest_path(root)),
        }
    )
    _write_json(chunk_report_path(root, old_chunk_id), report)
    return {
        "abandonedChunkId": old_chunk_id,
        "abandonedAt": abandoned_at,
        "abandonReason": reason,
        "replacementChunkId": replacement_chunk_id,
        "abandonedAssetCount": len(manifest_rows),
        "abandonedProfileCount": len({row["profileId"] for row in manifest_rows if row.get("profileId")}),
        "abandonedChunkManifest": to_portable_path(abandoned_chunk_manifest_path(root)),
        "abandonedReportPath": to_portable_path(chunk_report_path(root, old_chunk_id)),
    }


def _progress_snapshot(root: Path | str | None = None) -> dict[str, Any]:
    paths = pipeline_paths(root)
    audit_path = paths.reports / "latest_distribution_audit.json"
    audit: dict[str, Any] = {}
    if audit_path.exists():
        try:
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            audit = {}
    return {
        "approvedIdentityCount": int(audit.get("approvedCompleteIdentityCount") or audit.get("approvedCompleteIdentities") or 0),
        "approvedAssetCount": int(audit.get("approvedImageCount") or audit.get("approvedImages") or 0),
        "assetQaCount": len(read_jsonl(paths.manifests / "asset_qa_manifest.jsonl")),
        "identityQaCount": len(read_jsonl(paths.manifests / "identity_qa_manifest.jsonl")),
        "resolvedPendingCount": len(read_jsonl(paths.manifests / "completed_pending_imagegen.jsonl")),
        "rejectedIdentityCount": len(read_jsonl(paths.manifests / "rejected_identity_manifest.jsonl")),
        "needsReviewIdentityCount": len(read_jsonl(paths.manifests / "needs_review_identity_manifest.jsonl")),
        "remainingDeficits": audit.get("countChecks", {}),
        "surplusBuckets": [
            row for row in audit.get("bucketChecks", []) if isinstance(row, Mapping) and int(row.get("surplus") or 0) > 0
        ],
    }


def _native_codex_exe_from_cmd_shim(resolved: str) -> str:
    """Return the native Codex executable for the Windows codex.cmd shim when possible.

    On Windows, subprocess timeouts can kill the .cmd wrapper while leaving the
    native codex.exe child alive with inherited pipe handles.  The parent Python
    process then remains stuck in communicate() and the bounded chunk keeps an
    unresolved pending-imagegen checkpoint.  Running codex.exe directly avoids
    that wrapper/orphan failure mode.
    """
    path = Path(resolved)
    if path.suffix.lower() != ".cmd" or path.name.lower() != "codex.cmd":
        return resolved
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        native = Path(local_app_data) / "OpenAI" / "Codex" / "bin" / "codex.exe"
        if native.exists():
            return str(native)
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return resolved
    marker = "%LOCALAPPDATA%\\OpenAI\\Codex\\bin\\codex.exe"
    if marker in text and local_app_data:
        native = Path(local_app_data) / "OpenAI" / "Codex" / "bin" / "codex.exe"
        if native.exists():
            return str(native)
    return resolved


def _resolve_agent_binary(
    config: BoundedExecutorConfig,
    *,
    root: Path | str | None = None,
    which_func: Callable[[str], str | None] = shutil.which,
) -> str:
    candidates = [config.agent_cmd]
    if config.agent_cmd == "omx":
        candidates.append("codex")
    elif config.agent_cmd == "codex":
        candidates.append("omx")
    for candidate in candidates:
        resolved = which_func(candidate)
        if resolved:
            return _native_codex_exe_from_cmd_shim(resolved)
    write_manual_review_flag(root, "agent_command_unavailable", {"candidates": candidates})
    raise BoundedBatchExecutorError(f"No bounded executor agent command is available: {', '.join(candidates)}")


def _run_agent_help(
    agent_bin: str,
    *,
    run_func: Callable[..., subprocess.CompletedProcess[str]],
) -> tuple[int, str]:
    try:
        result = run_func(
            [agent_bin, "exec", "--help"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, str(exc)
    return int(result.returncode), f"{result.stdout or ''}\n{result.stderr or ''}"


def discover_reference_image_arg_modes(
    *,
    agent_bin: str,
    config: BoundedExecutorConfig,
    run_func: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> list[str]:
    if config.image_arg_mode != "auto":
        return [config.image_arg_mode]
    rc, help_text = _run_agent_help(agent_bin, run_func=run_func)
    if rc != 0:
        return []
    modes: list[str] = []
    if "--image" in help_text:
        modes.append("image")
    if "-i" in help_text:
        modes.append("short_i")
    return modes


def _resolve_reference_image_arg_mode(
    root: Path | str | None,
    *,
    agent_bin: str,
    config: BoundedExecutorConfig,
    run_func: Callable[..., subprocess.CompletedProcess[str]],
    asset_id: str,
    reference_path: Path,
) -> str:
    modes = discover_reference_image_arg_modes(agent_bin=agent_bin, config=config, run_func=run_func)
    if modes:
        return modes[0]
    write_manual_review_flag(
        root,
        "reference_image_input_unavailable",
        {"assetId": asset_id, "referencePath": to_portable_path(reference_path), "agent": agent_bin},
    )
    raise BoundedBatchExecutorError("reference_image_input_unavailable")


def _command_has_reference_arg(command: Sequence[str], reference_path: Path, image_arg_mode: str) -> bool:
    image_arg = "--image" if image_arg_mode == "image" else "-i"
    normalized_reference = str(reference_path.resolve())
    for index, item in enumerate(command):
        if item != image_arg:
            continue
        if index + 1 >= len(command):
            return False
        attached_paths = [str(Path(part).resolve()) for part in str(command[index + 1]).split(",") if part]
        return normalized_reference in attached_paths
    return False


def _handle_child_forbidden_mutation(
    root: Path | str | None,
    plan: dict[str, Any],
    state: dict[str, Any],
    *,
    asset_id: str,
    profile_id: str,
    shot_type: str,
    violations: Sequence[Mapping[str, Any]],
    backup: Mapping[str, Any],
) -> None:
    restore_report = restore_forbidden_files(root, backup, violations)
    flag = write_manual_review_flag(
        root,
        "child_forbidden_mutation",
        {"assetId": asset_id, "violations": list(violations), "restore": restore_report},
    )
    _transition_asset(root, plan, state, asset_id, "failed", profile_id=profile_id, shot_type=shot_type, reason="child_forbidden_mutation")
    _append_event(root, str(plan["chunkId"]), event_type="manual_review_flag_written", asset_id=asset_id, profile_id=profile_id, shot_type=shot_type, reason="child_forbidden_mutation", output_path=to_portable_path(flag))
    _transition_chunk(root, plan, state, "needs_manual_review", reason="child_forbidden_mutation")
    raise BoundedBatchExecutorError("child_forbidden_mutation")


def child_workspace_path(root: Path | str | None, chunk_id: str, asset_id: str, attempt: int) -> Path:
    path = chunk_report_dir(root, chunk_id) / "child_workspaces" / f"{asset_id}_attempt{attempt}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _kill_process_tree(proc: subprocess.Popen[Any]) -> None:
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                capture_output=True,
                text=True,
                timeout=10,
                shell=False,
            )
            return
        except Exception:
            pass
    try:
        proc.kill()
    except Exception:
        pass


def run_child_command_with_tree_timeout(
    args: Sequence[str],
    *,
    cwd: str | None = None,
    capture_output: bool = True,
    text: bool = True,
    encoding: str | None = "utf-8",
    errors: str | None = "replace",
    timeout: int | float | None = None,
    shell: bool = False,
    env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    if shell:
        raise ValueError("child commands must run with shell=False")
    stdout_pipe = subprocess.PIPE if capture_output else None
    stderr_pipe = subprocess.PIPE if capture_output else None
    proc = subprocess.Popen(
        list(args),
        cwd=cwd,
        stdout=stdout_pipe,
        stderr=stderr_pipe,
        text=text,
        encoding=encoding,
        errors=errors,
        shell=False,
        env=dict(env) if env is not None else None,
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        _kill_process_tree(proc)
        try:
            stdout, stderr = proc.communicate(timeout=5)
        except Exception:
            stdout = getattr(exc, "output", None)
            stderr = getattr(exc, "stderr", None)
        raise subprocess.TimeoutExpired(list(args), timeout, output=stdout, stderr=stderr) from exc
    return subprocess.CompletedProcess(list(args), int(proc.returncode or 0), stdout, stderr)


def build_agent_args(
    prompt: str,
    *,
    root: Path | str | None = None,
    config: BoundedExecutorConfig | None = None,
    agent_bin: str | None = None,
    image_paths: Sequence[Path | str] | None = None,
    image_arg_mode: str = "image",
    child_workspace: Path | str | None = None,
) -> list[str]:
    config = config or BoundedExecutorConfig.from_env()
    binary = agent_bin or config.agent_cmd
    workspace = Path(child_workspace) if child_workspace is not None else pipeline_paths(root).root
    workspace.mkdir(parents=True, exist_ok=True)
    args = [
        binary,
        "exec",
        "--ephemeral",
        "--ignore-rules",
        "--skip-git-repo-check",
        "-s",
        "read-only",
    ]
    if image_paths:
        image_arg = "--image" if image_arg_mode == "image" else "-i"
        args.extend([image_arg, ",".join(str(Path(path).resolve()) for path in image_paths)])
    args.extend(["-C", str(workspace), prompt])
    return args


def child_agent_env(env: Mapping[str, str] | None = None) -> dict[str, str]:
    values = dict(env or os.environ)
    for key in (
        "CODEX_SANDBOX_NETWORK_DISABLED",
        "CODEX_DISABLE_TOOLS",
        "CODEX_TOOLS_DISABLED",
        "CODEX_IMAGEGEN_DISABLED",
    ):
        values.pop(key, None)
    return values


def build_one_asset_child_prompt(
    asset: Mapping[str, Any],
    *,
    generation_prompt: str,
    reference_path: str | None = None,
) -> str:
    reference_rule = "- Use attached face_card as same-person reference.\n- The attached face_card image is the authoritative identity anchor.\n" if reference_path else ""
    return (
        "Invoke the built-in $imagegen tool exactly once to create one image using Codex internal Image Gen.\n\n"
        "Asset:\n"
        f"- assetId: {asset.get('assetId')}\n"
        f"- profileId: {asset.get('profileId')}\n"
        f"- shotType: {asset.get('shotType')}\n"
        f"- attempt: {asset.get('attempt')}\n\n"
        "Rules:\n"
        f"{reference_rule}"
        "- Use $imagegen explicitly; do not answer with text-only planning.\n"
        "- Generate one image only.\n"
        "- Canvas geometry is mandatory: portrait 2:3 aspect ratio, ideally 1024x1536.\n"
        "- The image width must be roughly 55% to 85% of its height; avoid ultra-tall 9:19/phone-screenshot framing.\n"
        "- Keep the subject framed as a realistic profile photo, not a long full-body crop with excessive empty vertical space.\n"
        "- Do not write files.\n"
        "- Do not run shell commands.\n"
        "- Do not inspect or modify project files.\n"
        "- Do not recover, copy, move, or rename images.\n"
        "- After image generation, respond with exactly: IMAGEGEN_DONE\n\n"
        "Generation prompt:\n"
        "Mandatory output geometry reminder: portrait 2:3, ideally 1024x1536; width/height must be between 0.55 and 0.85 for file QA.\n\n"
        f"{generation_prompt}\n"
    )


def _write_parent_imagegen_handoff(
    root: Path | str | None,
    plan: Mapping[str, Any],
    pending_payload: Mapping[str, Any],
    prompt: str,
    *,
    reference_path: Path | None = None,
) -> dict[str, str]:
    asset_id = str(pending_payload.get("assetId") or "")
    attempt = int(pending_payload.get("attempt") or 0)
    handoff_dir = chunk_report_dir(root, str(plan["chunkId"])) / "parent_imagegen_handoffs"
    handoff_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = handoff_dir / f"{asset_id}_attempt{attempt}.prompt.txt"
    report_path = handoff_dir / f"{asset_id}_attempt{attempt}.json"
    parent_prompt = (
        "Use the Codex built-in image_gen tool exactly once for this pending Seolleyeon asset.\n"
        "Do not use OpenAI Image API, Batch API, or OPENAI_API_KEY.\n"
        "After the image is generated, recover it according to pending-imagegen.json before continuing.\n\n"
        f"pendingPath: {to_portable_path(pending_path(root))}\n"
        f"assetId: {pending_payload.get('assetId')}\n"
        f"profileId: {pending_payload.get('profileId')}\n"
        f"shotType: {pending_payload.get('shotType')}\n"
        f"attempt: {pending_payload.get('attempt')}\n"
        f"expectedRawPath: {pending_payload.get('expectedRawPath')}\n"
        f"expectedFinalPath: {pending_payload.get('expectedFinalPath')}\n"
        f"referenceImagePath: {to_portable_path(reference_path) if reference_path else ''}\n\n"
        "Image generation instruction for the parent surface:\n\n"
        f"{prompt}\n"
    )
    prompt_path.write_text(parent_prompt, encoding="utf-8")
    report = {
        "schemaVersion": "seolleyeon_parent_imagegen_handoff_v1",
        "chunkId": str(plan["chunkId"]),
        "assetId": asset_id,
        "profileId": str(pending_payload.get("profileId") or ""),
        "shotType": str(pending_payload.get("shotType") or ""),
        "attempt": attempt,
        "pendingPath": to_portable_path(pending_path(root)),
        "promptPath": to_portable_path(prompt_path),
        "expectedRawPath": str(pending_payload.get("expectedRawPath") or ""),
        "expectedFinalPath": str(pending_payload.get("expectedFinalPath") or ""),
        "referenceImagePath": to_portable_path(reference_path) if reference_path else "",
        "nextCommands": [
            "Use the parent Codex/Hermes imagegen surface with the promptPath.",
            "python scripts/run_ai_image_pipeline_v3.py pending-status --root .",
            "python scripts/recover_pending_imagegen_v3.py --root .",
            "python scripts/run_ai_image_pipeline_v3.py bounded-chunk-resume --root .",
        ],
        "createdAt": now_utc(),
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"promptPath": to_portable_path(prompt_path), "reportPath": to_portable_path(report_path)}


def build_one_asset_prompt(asset_row: Mapping[str, Any], pending_payload: Mapping[str, Any]) -> str:
    reference_path = str(pending_payload.get("referenceImagePath") or "")
    reference_block = ""
    if str(asset_row.get("shotType") or "") in DEPENDENT_SHOTS:
        reference_block = (
            "\nReference requirement:\n"
            f"- referenceAssetId: {pending_payload.get('referenceAssetId')}\n"
            f"- referenceImagePath: {reference_path}\n"
            "- Use this face_card as the same-person identity anchor.\n"
            "- If this Codex/Image Gen surface cannot use that reference image, stop and report reference_image_input_unavailable; do not generate an independent dependent shot.\n"
        )
    return (
        "Use Codex internal Image Gen only for exactly one Seolleyeon AI profile asset.\n"
        "Do not use OpenAI Image API. Do not use Batch API. Do not require OPENAI_API_KEY.\n"
        "Do not modify CLIP/SVD/KNN/RRF recommender files or any recommender pipeline code.\n"
        "Generate exactly one image, then stop. Do not continue to the next asset. Do not run QA.\n"
        "Do not recover, copy, move, rename, or import generated files; the parent bounded executor owns recovery and file QA after this call.\n\n"
        "Output geometry requirement:\n"
        "- Generate a portrait image close to 2:3 aspect ratio, ideally 1024x1536.\n"
        "- Do not create an ultra-tall, panoramic, square, or heavily cropped image.\n"
        "- The recovered file must satisfy vertical profile file QA aspect ratio checks.\n\n"
        "Single asset to generate:\n"
        f"assetId: {pending_payload.get('assetId')}\n"
        f"profileId: {pending_payload.get('profileId')}\n"
        f"gender: {pending_payload.get('gender')}\n"
        f"numericId: {pending_payload.get('numericId')}\n"
        f"shotType: {pending_payload.get('shotType')}\n"
        f"targetFaceType: {asset_row.get('targetFaceType')}\n"
        f"targetLooksLevelBand: {asset_row.get('targetLooksLevelBand')}\n"
        f"attempt: {pending_payload.get('attempt')}\n"
        f"promptHash: {pending_payload.get('promptHash')}\n"
        f"expectedRawPath: {pending_payload.get('expectedRawPath')}\n"
        f"expectedFinalPath: {pending_payload.get('expectedFinalPath')}\n"
        f"{reference_block}\n"
        "Generation prompt:\n"
        f"{pending_payload.get('prompt')}\n"
    )


def _log_command_output(root: Path | str | None, chunk_id: str, asset_id: str, attempt: int, stdout: str, stderr: str, command: Sequence[str]) -> tuple[Path, Path]:
    log_dir = chunk_report_dir(root, chunk_id) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = log_dir / f"{asset_id}_attempt{attempt}.stdout.txt"
    stderr_path = log_dir / f"{asset_id}_attempt{attempt}.stderr.txt"
    command_path = log_dir / f"{asset_id}_attempt{attempt}.command.json"
    stdout_path.write_text(stdout, encoding="utf-8")
    stderr_path.write_text(stderr, encoding="utf-8")
    command_path.write_text(json.dumps({"args": list(command)}, ensure_ascii=False, indent=2), encoding="utf-8")
    return stdout_path, stderr_path


def _clear_pending_after_failed_call(root: Path | str | None, reason: str) -> None:
    pending_file = pending_path(root)
    payload = read_pending(pending_file)
    if not payload:
        return
    write_pending(
        pending_file,
        resolved_pending_payload(payload, status="cleared", recoveryStatus="not_recovered", reason=reason, clearedAt=now_utc()),
    )


def _mark_pending_imagegen_status(root: Path | str | None, status: str, **extra: Any) -> None:
    pending_file = pending_path(root)
    payload = read_pending(pending_file)
    if not payload or pending_is_resolved(payload):
        return
    updated = dict(payload)
    updated.update(extra)
    updated["status"] = status
    updated["updatedAt"] = now_utc()
    write_pending(pending_file, updated)


def _recover_pending_with_board_wait(recover_func: Callable[..., Any], *, root: Path | str | None, pending_file: Path, run_qa: bool) -> Any:
    try:
        return recover_func(
            root=root,
            pending=pending_file,
            run_qa=run_qa,
            wait_seconds=IMAGEGEN_RECOVERY_WAIT_SECONDS,
            poll_interval=IMAGEGEN_RECOVERY_POLL_SECONDS,
        )
    except TypeError:
        # Tests and older injected recovery functions may not accept the wait
        # knobs; preserve compatibility while the real Codex recovery path polls.
        return recover_func(root=root, pending=pending_file, run_qa=run_qa)


def _update_generation_row_pending(root: Path | str | None, pending_payload: Mapping[str, Any]) -> None:
    paths = pipeline_paths(root)
    rows = load_generation_manifest(paths)
    updated: list[dict[str, Any]] = []
    for row in rows:
        out = dict(row)
        if str(out.get("assetId") or "") == str(pending_payload.get("assetId") or ""):
            out.update(
                {
                    "status": "pending_imagegen",
                    "attempt": int(pending_payload.get("attempt") or 0),
                    "attemptCount": int(pending_payload.get("attempt") or 0),
                    "pendingPath": to_portable_path(pending_path(root)),
                    "expectedRawPath": pending_payload["expectedRawPath"],
                    "expectedFinalPath": pending_payload["expectedFinalPath"],
                    "expectedApprovedPath": pending_payload["expectedApprovedPath"],
                    "expectedRejectedPath": pending_payload["expectedRejectedPath"],
                    "finalPath": pending_payload["expectedFinalPath"],
                    "approvedPath": pending_payload["expectedApprovedPath"],
                    "rejectedPath": pending_payload["expectedRejectedPath"],
                    "resolvedReferencePath": pending_payload.get("referenceImagePath", ""),
                    "updatedAt": now_utc(),
                    "error": "",
                }
            )
        updated.append(out)
    write_generation_outputs(paths, updated)


def _restore_generation_row_after_infrastructure_failure(
    root: Path | str | None,
    *,
    asset_id: str,
    previous_attempt: int,
    failed_attempt: int,
    reason: str,
    stdout_path: Path | None = None,
    stderr_path: Path | None = None,
) -> None:
    paths = pipeline_paths(root)
    rows = load_generation_manifest(paths)
    updated: list[dict[str, Any]] = []
    for row in rows:
        out = dict(row)
        if str(out.get("assetId") or "") == asset_id:
            out.update(
                {
                    "status": "imagegen_infrastructure_blocked",
                    "attempt": int(previous_attempt),
                    "attemptCount": int(previous_attempt),
                    "lastInfrastructureFailureAttempt": int(failed_attempt),
                    "lastInfrastructureFailureReason": reason,
                    "error": reason,
                    "updatedAt": now_utc(),
                }
            )
            if stdout_path is not None:
                out["lastInfrastructureFailureStdoutLog"] = to_portable_path(stdout_path)
            if stderr_path is not None:
                out["lastInfrastructureFailureStderrLog"] = to_portable_path(stderr_path)
        updated.append(out)
    write_generation_outputs(paths, updated)


def _block_for_imagegen_infrastructure_failure(
    root: Path | str | None,
    plan: dict[str, Any],
    state: dict[str, Any],
    *,
    asset_id: str,
    profile_id: str,
    shot_type: str,
    previous_attempt: int,
    failed_attempt: int,
    reason: str,
    command: Sequence[str],
    return_code: int,
    stdout_path: Path | None = None,
    stderr_path: Path | None = None,
) -> None:
    _replace_plan_asset(plan, asset_id, {"attempt": int(previous_attempt), "attemptCount": int(previous_attempt)})
    _restore_generation_row_after_infrastructure_failure(
        root,
        asset_id=asset_id,
        previous_attempt=previous_attempt,
        failed_attempt=failed_attempt,
        reason=reason,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
    )
    _clear_pending_after_failed_call(root, reason)
    flag = write_manual_review_flag(
        root,
        "imagegen_infrastructure_failure",
        {
            "assetId": asset_id,
            "profileId": profile_id,
            "shotType": shot_type,
            "failedAttempt": int(failed_attempt),
            "preservedAttemptCount": int(previous_attempt),
            "reason": reason,
            "returnCode": int(return_code),
            "stdoutLog": to_portable_path(stdout_path) if stdout_path is not None else "",
            "stderrLog": to_portable_path(stderr_path) if stderr_path is not None else "",
        },
    )
    _transition_asset(
        root,
        plan,
        state,
        asset_id,
        "imagegen_infrastructure_blocked",
        profile_id=profile_id,
        shot_type=shot_type,
        reason=reason,
        command=command,
        return_code=return_code,
        output_path=to_portable_path(flag),
    )
    _append_event(
        root,
        str(plan["chunkId"]),
        event_type="manual_review_flag_written",
        profile_id=profile_id,
        asset_id=asset_id,
        shot_type=shot_type,
        reason="imagegen_infrastructure_failure",
        output_path=to_portable_path(flag),
    )
    _transition_chunk(root, plan, state, "needs_manual_review", reason="imagegen_infrastructure_failure")
    raise BoundedBatchExecutorError("imagegen_infrastructure_failure")


def _latest_generation_asset(root: Path | str | None, asset_id: str) -> dict[str, Any]:
    for row in load_generation_manifest(pipeline_paths(root)):
        if str(row.get("assetId") or "") == asset_id:
            return dict(row)
    return {}


def _expected_transaction_payload(plan: Mapping[str, Any], row: Mapping[str, Any], pending_payload: Mapping[str, Any]) -> dict[str, Any]:
    reference_path = str(pending_payload.get("referenceImagePath") or row.get("resolvedReferencePath") or "")
    reference_digest = _sha256_file(Path(reference_path)) if reference_path else None
    return {
        "chunkId": str(plan.get("chunkId") or pending_payload.get("chunkId") or ""),
        "assetId": str(pending_payload.get("assetId") or row.get("assetId") or ""),
        "profileId": str(pending_payload.get("profileId") or row.get("profileId") or ""),
        "gender": str(pending_payload.get("gender") or row.get("gender") or ""),
        "numericId": str(pending_payload.get("numericId") or row.get("numericId") or ""),
        "shotType": str(pending_payload.get("shotType") or row.get("shotType") or ""),
        "attempt": int(pending_payload.get("attempt") or row.get("attempt") or 0),
        "expectedRawPath": str(pending_payload.get("expectedRawPath") or row.get("expectedRawPath") or row.get("localPath") or ""),
        "expectedFinalPath": str(pending_payload.get("expectedFinalPath") or row.get("expectedFinalPath") or row.get("finalPath") or ""),
        "expectedReceiptPath": str(pending_payload.get("expectedReceiptPath") or ""),
        "referencePath": reference_path,
        "referencePathSha256": reference_digest,
    }


def _update_generation_row_from_transaction(
    root: Path | str | None,
    *,
    asset_id: str,
    pending_payload: Mapping[str, Any],
    receipt: Mapping[str, Any],
    status: str = "recovered_pending_qa",
) -> None:
    paths = pipeline_paths(root)
    rows = load_generation_manifest(paths)
    updated: list[dict[str, Any]] = []
    for row in rows:
        out = dict(row)
        if str(out.get("assetId") or "") == asset_id:
            out.update(
                {
                    "status": status,
                    "attempt": int(pending_payload.get("attempt") or receipt.get("attempt") or out.get("attempt") or 0),
                    "attemptCount": int(pending_payload.get("attempt") or receipt.get("attempt") or out.get("attemptCount") or 0),
                    "pendingPath": to_portable_path(pending_path(root)),
                    "localPath": to_portable_path(Path(str(receipt.get("rawPath") or pending_payload.get("expectedRawPath") or out.get("localPath") or ""))),
                    "rawPath": to_portable_path(Path(str(receipt.get("rawPath") or pending_payload.get("expectedRawPath") or ""))),
                    "finalPath": to_portable_path(Path(str(receipt.get("finalPath") or pending_payload.get("expectedFinalPath") or out.get("finalPath") or ""))),
                    "expectedRawPath": str(pending_payload.get("expectedRawPath") or out.get("expectedRawPath") or ""),
                    "expectedFinalPath": str(pending_payload.get("expectedFinalPath") or out.get("expectedFinalPath") or ""),
                    "transactionReceiptPath": str(pending_payload.get("expectedReceiptPath") or ""),
                    "updatedAt": now_utc(),
                    "error": "",
                }
            )
        updated.append(out)
    write_generation_outputs(paths, updated)


def _commit_verified_transaction(
    root: Path | str | None,
    plan: dict[str, Any],
    state: dict[str, Any],
    *,
    asset_id: str,
    profile_id: str,
    shot_type: str,
    pending_payload: Mapping[str, Any],
    receipt_result: Mapping[str, Any],
    file_qa_func: Callable[..., Mapping[str, int]],
    reason: str,
) -> bool:
    receipt = receipt_result.get("receipt") if isinstance(receipt_result.get("receipt"), Mapping) else {}
    _update_generation_row_from_transaction(root, asset_id=asset_id, pending_payload=pending_payload, receipt=receipt, status="recovered_pending_qa")
    if str((state.get("assetStates") or {}).get(asset_id) or "") != "recovered":
        state["recoveredAssets"] = int(state.get("recoveredAssets", 0)) + 1
        _transition_asset(
            root,
            plan,
            state,
            asset_id,
            "recovered",
            profile_id=profile_id,
            shot_type=shot_type,
            reason=reason,
            output_path=str(receipt.get("finalPath") or pending_payload.get("expectedFinalPath") or ""),
        )
    committed = _file_qa_recovered_asset(
        root,
        plan,
        state,
        asset_id=asset_id,
        profile_id=profile_id,
        shot_type=shot_type,
        file_qa_func=file_qa_func,
        reason="one_asset_transaction_verified",
    )
    if committed:
        _append_event(
            root,
            str(plan["chunkId"]),
            event_type="one_asset_transaction_committed",
            profile_id=profile_id,
            asset_id=asset_id,
            shot_type=shot_type,
            from_status="recovered",
            to_status="file_qa_passed",
            reason=reason,
            output_path=str(pending_payload.get("expectedReceiptPath") or ""),
        )
    return committed


def file_qa_single_asset(
    *,
    root: Path | str | None = None,
    chunk_id: str = "",
    asset_id: str,
    shot_type: str = "",
    force: bool = False,
) -> dict[str, int]:
    del force
    paths = pipeline_paths(root)
    rows = load_generation_manifest(paths)
    updated: list[dict[str, Any]] = []
    counts = {"checked": 0, "approved": 0, "needs_manual_review": 0, "rejected": 0, "missing": 0}
    report_rows: list[dict[str, Any]] = []
    for row in rows:
        out = dict(row)
        if str(out.get("assetId") or "") == asset_id:
            counts["checked"] += 1
            final_path = Path(str(out.get("finalPath") or out.get("expectedFinalPath") or ""))
            local_path = Path(str(out.get("localPath") or ""))
            candidate = final_path if str(final_path) not in {"", "."} and final_path.exists() else local_path
            detail = inspect_image_detail(candidate)
            reasons = list(detail.get("reasons", []))
            candidate_hash = _sha256_file(candidate) if str(candidate) not in {"", "."} and candidate.exists() else None
            if candidate_hash:
                for other in rows:
                    other_asset_id = str(other.get("assetId") or "")
                    if not other_asset_id or other_asset_id == asset_id:
                        continue
                    for path_key in ("finalPath", "approvedPath", "localPath", "rawPath"):
                        other_value = str(other.get(path_key) or "")
                        if not other_value:
                            continue
                        other_path = Path(other_value)
                        if other_path.exists() and _sha256_file(other_path) == candidate_hash:
                            reasons.append("duplicate_image_hash")
                            break
                    if "duplicate_image_hash" in reasons:
                        break
            expected_final = public_final_path(paths, out)
            try:
                if final_path and final_path.resolve() != expected_final.resolve():
                    reasons.append("final_path_mismatch")
            except OSError:
                reasons.append("final_path_invalid")
            if shot_type and str(out.get("shotType") or "") != shot_type:
                reasons.append("shot_type_mismatch")
            if detail.get("ok") and not reasons:
                out["status"] = "file_needs_review"
                out["error"] = "Integrity passed; active visual QA still required."
                counts["needs_manual_review"] += 1
            elif "missing_image" in reasons:
                out["status"] = "missing"
                out["error"] = "; ".join(str(reason) for reason in reasons)
                counts["missing"] += 1
            else:
                out["status"] = "file_rejected"
                out["error"] = "; ".join(str(reason) for reason in reasons)
                counts["rejected"] += 1
            out["updatedAt"] = now_utc()
            report_rows.append(
                {
                    "assetId": asset_id,
                    "profileId": out.get("profileId", ""),
                    "shotType": out.get("shotType", ""),
                    "qaStatus": out["status"],
                    "imagePath": to_portable_path(candidate) if str(candidate) not in {"", "."} else "",
                    "width": detail.get("width", 0),
                    "height": detail.get("height", 0),
                    "fileBytes": detail.get("fileBytes", 0),
                    "reasonCodes": reasons,
                    "updatedAt": now_utc(),
                }
            )
        updated.append(out)
    if counts["checked"] == 0:
        raise BoundedBatchExecutorError(f"File QA could not find planned asset: {asset_id}")
    write_generation_outputs(paths, updated)
    if chunk_id:
        report_path = chunk_report_dir(root, chunk_id) / "file_qa.jsonl"
        existing = read_jsonl(report_path)
        existing.extend(report_rows)
        write_jsonl(report_path, existing)
    return counts


def _pending_guard(root: Path | str | None, *, recover_func: Callable[..., Any] = recover_pending_imagegen) -> None:
    pending_file = pending_path(root)
    payload = read_pending(pending_file)
    if not payload or pending_is_resolved(payload):
        return
    if pending_requires_recovery(payload):
        recover_func(root=root, pending=pending_file, run_qa=False)
        return
    if pending_is_unresolved(payload):
        write_manual_review_flag(root, "unresolved_pending_imagegen", {"assetId": payload.get("assetId"), "status": payload.get("status")})
        raise BoundedBatchExecutorError("Unresolved pending-imagegen.json blocks bounded executor.")


def _face_asset_state(plan: Mapping[str, Any], state: Mapping[str, Any], profile_id: str) -> tuple[str, str]:
    for identity in plan.get("identities", []):
        if str(identity.get("profileId") or "") != profile_id:
            continue
        for asset in identity.get("assets", []):
            if asset.get("shotType") == "face_card":
                asset_id = str(asset.get("assetId") or "")
                return asset_id, str((state.get("assetStates") or {}).get(asset_id) or asset.get("status") or "")
    return "", ""


def _reference_ready(root: Path | str | None, plan: Mapping[str, Any], state: Mapping[str, Any], profile_id: str) -> bool:
    face_asset_id, face_state = _face_asset_state(plan, state, profile_id)
    if not face_asset_id:
        return False
    row = _latest_generation_asset(root, face_asset_id)
    return face_state == "file_qa_passed" and _path_exists(row.get("finalPath"))


def _reference_final_path(root: Path | str | None, plan: Mapping[str, Any], state: Mapping[str, Any], profile_id: str) -> Path | None:
    if not _reference_ready(root, plan, state, profile_id):
        return None
    face_asset_id, _face_state = _face_asset_state(plan, state, profile_id)
    row = _latest_generation_asset(root, face_asset_id)
    final_path = Path(str(row.get("finalPath") or ""))
    if final_path.exists():
        return final_path
    return None


def _write_identity_context(
    root: Path | str | None,
    plan: Mapping[str, Any],
    state: Mapping[str, Any],
    identity: Mapping[str, Any],
    *,
    reference_path: Path | None = None,
) -> Path:
    profile_id = str(identity.get("profileId") or "")
    chunk_id = str(plan.get("chunkId") or "")
    face_asset_id, face_state = _face_asset_state(plan, state, profile_id)
    rows_by_asset = {
        str(row.get("assetId") or ""): row
        for row in load_generation_manifest(pipeline_paths(root))
        if str(row.get("profileId") or "") == profile_id
    }
    assets: list[dict[str, Any]] = []
    for asset in identity.get("assets", []):
        asset_id = str(asset.get("assetId") or "")
        row = rows_by_asset.get(asset_id, {})
        assets.append(
            {
                "assetId": asset_id,
                "shotType": str(asset.get("shotType") or row.get("shotType") or ""),
                "state": str((state.get("assetStates") or {}).get(asset_id) or asset.get("status") or row.get("status") or ""),
                "finalPath": str(row.get("finalPath") or asset.get("finalPath") or ""),
                "requiresReferenceAssetId": asset.get("requiresReferenceAssetId"),
            }
        )
    face_row = rows_by_asset.get(face_asset_id, {})
    metadata = face_row.get("metadata") if isinstance(face_row.get("metadata"), Mapping) else {}
    payload = {
        "schemaVersion": "seolleyeon_identity_context_v3",
        "chunkId": chunk_id,
        "profileId": profile_id,
        "gender": str(identity.get("gender") or face_row.get("gender") or ""),
        "numericId": str(identity.get("numericId") or face_row.get("numericId") or ""),
        "targetFaceType": str(identity.get("targetFaceType") or face_row.get("targetFaceType") or target_face_type(face_row) or ""),
        "targetLooksLevelBand": str(identity.get("targetLooksLevelBand") or face_row.get("targetLooksLevelBand") or target_looks_level_band(face_row) or ""),
        "faceAssetId": face_asset_id,
        "faceState": face_state,
        "faceFinalPath": to_portable_path(reference_path) if reference_path else str(face_row.get("finalPath") or ""),
        "faceFinalSha256": _sha256_file(reference_path) if reference_path else None,
        "hair": metadata.get("hair", {}) if isinstance(metadata, Mapping) else {},
        "body": metadata.get("body", {}) if isinstance(metadata, Mapping) else {},
        "styling": metadata.get("styling", {}) if isinstance(metadata, Mapping) else {},
        "assets": assets,
        "updatedAt": now_utc(),
    }
    path = chunk_report_dir(root, chunk_id) / "identity_context" / profile_id / "identity_context.json"
    _write_json(path, payload)
    return path


def _identity_context_prompt(context_path: Path, reference_path: Path) -> str:
    return (
        "Identity context for same-person generation:\n"
        f"- identityContextPath: {to_portable_path(context_path)}\n"
        f"- attachedFaceCardPath: {to_portable_path(reference_path)}\n"
        "- The attached face_card image is the authoritative identity anchor.\n"
        "- Text metadata is secondary and must not override the attached person's face, age impression, hairstyle family, or overall identity.\n"
        "- If you cannot use the attached face_card as an image reference, write a failed receipt with error=reference_image_input_unavailable and stop.\n"
    )


def _file_qa_recovered_asset(
    root: Path | str | None,
    plan: dict[str, Any],
    state: dict[str, Any],
    *,
    asset_id: str,
    profile_id: str,
    shot_type: str,
    file_qa_func: Callable[..., Mapping[str, int]],
    reason: str,
) -> bool:
    latest_row = _latest_generation_asset(root, asset_id)
    final_path = str(latest_row.get("finalPath") or "")
    if not _path_exists(final_path):
        return False
    if str((state.get("assetStates") or {}).get(asset_id) or "") != "recovered":
        state["recoveredAssets"] = max(int(state.get("recoveredAssets", 0)), 1)
        _transition_asset(root, plan, state, asset_id, "recovered", profile_id=profile_id, shot_type=shot_type, reason=reason, output_path=final_path)
    qa_counts = file_qa_func(root=root, chunk_id=str(plan["chunkId"]), asset_id=asset_id, shot_type=shot_type, force=True)
    latest_row = _latest_generation_asset(root, asset_id)
    status = str(latest_row.get("status") or "")
    if int(qa_counts.get("rejected", 0)) > 0 and status == "file_rejected":
        _transition_asset(root, plan, state, asset_id, "file_qa_failed", profile_id=profile_id, shot_type=shot_type, reason="file_qa_rejected")
        return False
    if status in {"file_rejected", "missing"}:
        _transition_asset(root, plan, state, asset_id, "file_qa_failed", profile_id=profile_id, shot_type=shot_type, reason=status)
        return False
    _transition_asset(root, plan, state, asset_id, "file_qa_passed", profile_id=profile_id, shot_type=shot_type, reason="file_integrity_passed_visual_qa_pending")
    return True


def _sync_file_qa_passed_asset_from_manifest(
    root: Path | str | None,
    plan: dict[str, Any],
    state: dict[str, Any],
    *,
    asset_id: str,
    profile_id: str,
    shot_type: str,
    reason: str,
) -> bool:
    latest_row = _latest_generation_asset(root, asset_id)
    final_path = str(latest_row.get("finalPath") or latest_row.get("expectedFinalPath") or "")
    if not latest_row or not _generation_file_qa_passed(latest_row) or not _path_exists(final_path):
        return False
    attempt_count = int(latest_row.get("attemptCount") or latest_row.get("attempt") or 0)
    updates: dict[str, Any] = {"status": "file_qa_passed"}
    if attempt_count:
        updates.update({"attempt": attempt_count, "attemptCount": attempt_count})
    _replace_plan_asset(plan, asset_id, updates)
    if str((state.get("assetStates") or {}).get(asset_id) or "") != "file_qa_passed":
        _transition_asset(
            root,
            plan,
            state,
            asset_id,
            "file_qa_passed",
            profile_id=profile_id,
            shot_type=shot_type,
            reason=reason,
            output_path=final_path,
        )
    else:
        _save_plan_state(root, plan, state)
    return True


def _process_asset(
    root: Path | str | None,
    plan: dict[str, Any],
    state: dict[str, Any],
    identity: Mapping[str, Any],
    asset: Mapping[str, Any],
    *,
    config: BoundedExecutorConfig,
    run_func: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    recover_func: Callable[..., Any] = recover_pending_imagegen,
    file_qa_func: Callable[..., Mapping[str, int]] = file_qa_single_asset,
    which_func: Callable[[str], str | None] = shutil.which,
) -> bool:
    paths = pipeline_paths(root)
    asset_id = str(asset["assetId"])
    profile_id = str(identity["profileId"])
    shot_type = str(asset["shotType"])
    reference_path: Path | None = None
    reference_image_arg_mode = ""
    if str((state.get("assetStates") or {}).get(asset_id) or "") in ASSET_TERMINAL_STATUSES:
        return True
    if shot_type in DEPENDENT_SHOTS:
        if config.reference_mode == "disabled":
            write_manual_review_flag(root, "reference_image_input_unavailable", {"assetId": asset_id, "shotType": shot_type})
            _transition_asset(root, plan, state, asset_id, "failed", profile_id=profile_id, shot_type=shot_type, reason="reference_image_input_unavailable")
            return False
        reference_path = _reference_final_path(root, plan, state, profile_id)
        if reference_path is None:
            _transition_asset(root, plan, state, asset_id, "failed", profile_id=profile_id, shot_type=shot_type, reason="face_card_reference_missing_or_not_file_qa_passed")
            _transition_identity(root, plan, state, profile_id, "failed", reason="dependent_reference_unavailable")
            return False

    generation_row = _latest_generation_asset(root, asset_id)
    if not generation_row:
        raise BoundedBatchExecutorError(f"Planned asset not found in generation manifest: {asset_id}")
    if _sync_file_qa_passed_asset_from_manifest(
        root,
        plan,
        state,
        asset_id=asset_id,
        profile_id=profile_id,
        shot_type=shot_type,
        reason="manifest_file_qa_passed_resume",
    ):
        return True
    existing_state = str((state.get("assetStates") or {}).get(asset_id) or "")
    if existing_state in {"imagegen_called", "recovered", "file_qa_failed"} and pending_is_resolved(read_pending(pending_path(root))):
        if _file_qa_recovered_asset(
            root,
            plan,
            state,
            asset_id=asset_id,
            profile_id=profile_id,
            shot_type=shot_type,
            file_qa_func=file_qa_func,
            reason="resume_from_resolved_pending",
        ):
            return True
    agent_bin = ""
    if config.imagegen_surface == "child":
        agent_bin = _resolve_agent_binary(config, root=root, which_func=which_func)
    if reference_path is not None and config.imagegen_surface == "child":
        try:
            reference_image_arg_mode = _resolve_reference_image_arg_mode(
                root,
                agent_bin=agent_bin,
                config=config,
                run_func=run_func,
                asset_id=asset_id,
                reference_path=reference_path,
            )
        except BoundedBatchExecutorError:
            _transition_asset(root, plan, state, asset_id, "failed", profile_id=profile_id, shot_type=shot_type, reason="reference_image_input_unavailable")
            _transition_identity(root, plan, state, profile_id, "failed", reason="dependent_reference_unavailable")
            return False
    max_attempts = int(asset.get("maxAttempts") or config.max_asset_attempts)
    current_attempt = int(asset.get("attempt") or generation_row.get("attemptCount") or generation_row.get("attempt") or 0)

    while current_attempt < max_attempts:
        _pending_guard(root, recover_func=recover_func)
        previous_attempt = current_attempt
        current_attempt += 1
        _replace_plan_asset(plan, asset_id, {"attempt": current_attempt})
        pending_file = pending_path(root)
        pending_payload = build_pending_payload(
            paths_root=root,
            row=generation_row,
            attempt=current_attempt,
            queue_file=paths.manifests / "imagegen_queue.jsonl",
            manifest_file=manifest_path(paths),
            out_pending=pending_file,
        )
        receipt_path = transaction_receipt_path(root, str(plan["chunkId"]), asset_id, current_attempt)
        pending_payload.update(
            {
                "schemaVersion": "seolleyeon_pending_imagegen_v3",
                "chunkId": plan["chunkId"],
                "boundedExecutor": True,
                "expectedReceiptPath": to_portable_path(receipt_path),
                "resolvedAt": None,
                "resolvedBy": None,
            }
        )
        write_pending(pending_file, pending_payload)
        _update_generation_row_pending(root, pending_payload)
        _transition_asset(root, plan, state, asset_id, "pending_imagegen", profile_id=profile_id, shot_type=shot_type, reason="pending_written")

        generation_prompt = str(pending_payload.get("prompt") or "")
        prompt = build_one_asset_child_prompt(
            {
                "assetId": asset_id,
                "profileId": profile_id,
                "shotType": shot_type,
                "attempt": current_attempt,
            },
            generation_prompt=generation_prompt,
            reference_path=str(pending_payload.get("referenceImagePath") or "") or None,
        )
        if config.imagegen_surface == "parent":
            handoff = _write_parent_imagegen_handoff(root, plan, pending_payload, prompt, reference_path=reference_path)
            _append_event(
                root,
                str(plan["chunkId"]),
                event_type="parent_imagegen_handoff_written",
                profile_id=profile_id,
                asset_id=asset_id,
                shot_type=shot_type,
                reason="parent_managed_imagegen_required",
                output_path=handoff["promptPath"],
            )
            _transition_chunk(root, plan, state, "generation_paused", reason="parent_managed_imagegen_required")
            raise BoundedBatchExecutorError("parent_managed_imagegen_required")

        child_guard = snapshot_forbidden_files(root)
        child_backup = backup_forbidden_files(root, child_guard, chunk_id=str(plan["chunkId"]), asset_id=asset_id, attempt=current_attempt)
        workspace = child_workspace_path(root, str(plan["chunkId"]), asset_id, current_attempt)
        command = build_agent_args(
            prompt,
            root=root,
            config=config,
            agent_bin=agent_bin,
            image_paths=[reference_path] if reference_path is not None else None,
            image_arg_mode=reference_image_arg_mode or "image",
            child_workspace=workspace,
        )
        if reference_path is not None and not _command_has_reference_arg(command, reference_path, reference_image_arg_mode):
            write_manual_review_flag(root, "reference_image_input_unavailable", {"assetId": asset_id, "referencePath": to_portable_path(reference_path)})
            _transition_asset(root, plan, state, asset_id, "failed", profile_id=profile_id, shot_type=shot_type, reason="reference_image_arg_missing")
            _transition_identity(root, plan, state, profile_id, "failed", reason="dependent_reference_unavailable")
            return False
        try:
            command_runner = run_child_command_with_tree_timeout if run_func is subprocess.run else run_func
            _mark_pending_imagegen_status(root, "imagegen_started", startedAt=now_utc())
            _append_event(root, str(plan["chunkId"]), event_type="imagegen_child_started", profile_id=profile_id, asset_id=asset_id, shot_type=shot_type, reason="pending_written")
            result = command_runner(
                command,
                cwd=str(paths.root),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=config.timeout_sec,
                shell=False,
                env=child_agent_env(),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            _mark_pending_imagegen_status(root, "imagegen_process_returned", processReturnedAt=now_utc(), processException=str(exc))
            _append_event(root, str(plan["chunkId"]), event_type="imagegen_child_returned", profile_id=profile_id, asset_id=asset_id, shot_type=shot_type, reason="agent_exception", return_code=127)
            stdout_path, stderr_path = _log_command_output(root, str(plan["chunkId"]), asset_id, current_attempt, "", str(exc), command)
            violations = detect_forbidden_mutations(root, child_guard)
            if violations:
                _handle_child_forbidden_mutation(root, plan, state, asset_id=asset_id, profile_id=profile_id, shot_type=shot_type, violations=violations, backup=child_backup)
            try:
                receipt_result = verify_one_asset_transaction(
                    root=root,
                    receipt_path=receipt_path,
                    expected=_expected_transaction_payload(plan, generation_row, pending_payload),
                    pending_payload=read_pending(pending_file),
                )
                if _commit_verified_transaction(
                    root,
                    plan,
                    state,
                    asset_id=asset_id,
                    profile_id=profile_id,
                    shot_type=shot_type,
                    pending_payload=pending_payload,
                    receipt_result=receipt_result,
                    file_qa_func=file_qa_func,
                    reason="timeout_with_valid_receipt",
                ):
                    return True
            except OneAssetTransactionError:
                pass
            try:
                recovered = _recover_pending_with_board_wait(recover_func, root=root, pending_file=pending_file, run_qa=False)
                state["recoveredAssets"] = int(state.get("recoveredAssets", 0)) + 1
                _transition_asset(root, plan, state, asset_id, "recovered", profile_id=profile_id, shot_type=shot_type, reason="timeout_parent_recovery", output_path=str(getattr(recovered, "final_path", "")))
                fallback_receipt = build_receipt_from_existing_file(
                    root=root,
                    expected=_expected_transaction_payload(plan, generation_row, pending_payload),
                    source="parent_recovery_after_child_timeout",
                )
                write_receipt(receipt_path, fallback_receipt)
                if _file_qa_recovered_asset(
                    root,
                    plan,
                    state,
                    asset_id=asset_id,
                    profile_id=profile_id,
                    shot_type=shot_type,
                    file_qa_func=file_qa_func,
                    reason="timeout_parent_recovery",
                ):
                    return True
            except Exception:
                pass
            _block_for_imagegen_infrastructure_failure(
                root,
                plan,
                state,
                asset_id=asset_id,
                profile_id=profile_id,
                shot_type=shot_type,
                previous_attempt=previous_attempt,
                failed_attempt=current_attempt,
                reason="imagegen_child_timeout_or_agent_exception_no_image",
                command=command,
                return_code=127,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
            )

        stdout_path, _stderr_path = _log_command_output(root, str(plan["chunkId"]), asset_id, current_attempt, result.stdout or "", result.stderr or "", command)
        _mark_pending_imagegen_status(root, "imagegen_process_returned", processReturnedAt=now_utc(), returnCode=int(result.returncode), stdoutLog=to_portable_path(stdout_path))
        _append_event(root, str(plan["chunkId"]), event_type="imagegen_child_returned", profile_id=profile_id, asset_id=asset_id, shot_type=shot_type, reason="agent_returned", return_code=int(result.returncode), output_path=to_portable_path(stdout_path))
        violations = detect_forbidden_mutations(root, child_guard)
        if violations:
            _handle_child_forbidden_mutation(root, plan, state, asset_id=asset_id, profile_id=profile_id, shot_type=shot_type, violations=violations, backup=child_backup)
        state["generatedAssets"] = int(state.get("generatedAssets", 0)) + (1 if int(result.returncode) == 0 else 0)
        _transition_asset(
            root,
            plan,
            state,
            asset_id,
            "imagegen_called",
            profile_id=profile_id,
            shot_type=shot_type,
            reason="agent_returned",
            command=command,
            return_code=int(result.returncode),
            output_path=to_portable_path(stdout_path),
        )
        if int(result.returncode) != 0:
            _clear_pending_after_failed_call(root, f"agent_returncode_{result.returncode}")
            continue

        try:
            receipt_result = verify_one_asset_transaction(
                root=root,
                receipt_path=receipt_path,
                expected=_expected_transaction_payload(plan, generation_row, pending_payload),
                pending_payload=read_pending(pending_file),
            )
            if _commit_verified_transaction(
                root,
                plan,
                state,
                asset_id=asset_id,
                profile_id=profile_id,
                shot_type=shot_type,
                pending_payload=pending_payload,
                receipt_result=receipt_result,
                file_qa_func=file_qa_func,
                reason="child_receipt_verified",
            ):
                return True
        except OneAssetTransactionError as receipt_exc:
            current_pending = read_pending(pending_file)
            if pending_is_resolved(current_pending):
                existing_final = Path(str(pending_payload.get("expectedFinalPath") or ""))
                if existing_final.exists():
                    flag = write_manual_review_flag(
                        root,
                        "one_asset_receipt_missing_or_invalid_requires_reconcile",
                        {"assetId": asset_id, "error": str(receipt_exc), "receiptPath": to_portable_path(receipt_path)},
                    )
                    _transition_asset(root, plan, state, asset_id, "failed", profile_id=profile_id, shot_type=shot_type, reason=f"receipt_invalid:{receipt_exc}")
                    return False

        try:
            recovered = _recover_pending_with_board_wait(recover_func, root=root, pending_file=pending_file, run_qa=False)
        except Exception as exc:  # noqa: BLE001 - recovery failure blocks further generation.
            if pending_is_resolved(read_pending(pending_file)):
                try:
                    receipt_result = verify_one_asset_transaction(
                        root=root,
                        receipt_path=receipt_path,
                        expected=_expected_transaction_payload(plan, generation_row, pending_payload),
                        pending_payload=read_pending(pending_file),
                    )
                    if _commit_verified_transaction(
                        root,
                        plan,
                        state,
                        asset_id=asset_id,
                        profile_id=profile_id,
                        shot_type=shot_type,
                        pending_payload=pending_payload,
                        receipt_result=receipt_result,
                        file_qa_func=file_qa_func,
                        reason="resolved_pending_receipt_reconciled",
                    ):
                        return True
                except OneAssetTransactionError:
                    pass
            write_manual_review_flag(root, "bounded_recovery_failed", {"assetId": asset_id, "error": str(exc)})
            _transition_asset(root, plan, state, asset_id, "failed", profile_id=profile_id, shot_type=shot_type, reason=f"recovery_failed:{exc}")
            return False
        state["recoveredAssets"] = int(state.get("recoveredAssets", 0)) + 1
        _transition_asset(root, plan, state, asset_id, "recovered", profile_id=profile_id, shot_type=shot_type, output_path=str(getattr(recovered, "final_path", "")))
        fallback_receipt = build_receipt_from_existing_file(
            root=root,
            expected=_expected_transaction_payload(plan, generation_row, pending_payload),
            source="parent_recovery_after_child_imagegen",
        )
        write_receipt(receipt_path, fallback_receipt)

        if not _file_qa_recovered_asset(
            root,
            plan,
            state,
            asset_id=asset_id,
            profile_id=profile_id,
            shot_type=shot_type,
            file_qa_func=file_qa_func,
            reason="recovery_complete",
        ):
            continue
        return True

    _transition_asset(root, plan, state, asset_id, "failed", profile_id=profile_id, shot_type=shot_type, reason="max_attempts_exhausted")
    return False


def _generation_complete(plan: Mapping[str, Any], state: Mapping[str, Any]) -> bool:
    asset_states = state.get("assetStates") if isinstance(state.get("assetStates"), Mapping) else {}
    for identity in plan.get("identities", []):
        for asset in identity.get("assets", []):
            if str(asset_states.get(str(asset.get("assetId") or "")) or "") not in GENERATION_COMPLETE_ASSET_STATUSES:
                return False
    return True


def _auto_reconcile_after_child_forbidden_mutation(
    root: Path | str | None,
    *,
    chunk_id: str,
    asset_id: str,
    profile_id: str,
    shot_type: str,
    file_qa_func: Callable[..., Mapping[str, int]],
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "attempted": True,
        "resumed": False,
        "reconcile": {},
        "status": {},
        "assetStatus": "",
        "reason": "",
    }
    try:
        reconcile = reconcile_bounded_chunk(
            root=root,
            dry_run=False,
            apply=True,
            clear_manual_flag_if_safe=True,
            file_qa_func=file_qa_func,
        )
    except Exception as exc:  # noqa: BLE001 - unsafe reconcile leaves manual review in place.
        result["reason"] = f"auto_reconcile_failed:{exc}"
        _append_event(
            root,
            chunk_id,
            event_type="child_forbidden_mutation_auto_reconcile_failed",
            profile_id=profile_id,
            asset_id=asset_id,
            shot_type=shot_type,
            reason=str(exc),
        )
        return result
    result["reconcile"] = dict(reconcile)
    status = bounded_chunk_status(root=root)
    result["status"] = dict(status)
    try:
        state = read_current_state(root)
        result["assetStatus"] = str((state.get("assetStates") or {}).get(asset_id) or "")
    except Exception:
        result["assetStatus"] = ""
    safe_to_resume = (
        bool(reconcile.get("manualFlagCanClear"))
        and bool(reconcile.get("manualFlagCleared"))
        and not bool(status.get("manualReviewRequired"))
        and bool(status.get("canRun"))
    )
    if safe_to_resume:
        result["resumed"] = True
        _append_event(
            root,
            chunk_id,
            event_type="child_forbidden_mutation_auto_reconciled",
            profile_id=profile_id,
            asset_id=asset_id,
            shot_type=shot_type,
            from_status="needs_manual_review",
            to_status=str(status.get("status") or ""),
            reason=f"assetStatus={result['assetStatus']}",
            output_path=str(reconcile.get("reportPath") or ""),
        )
    else:
        result["reason"] = "auto_reconcile_not_safe_to_resume"
        _append_event(
            root,
            chunk_id,
            event_type="child_forbidden_mutation_auto_reconcile_blocked",
            profile_id=profile_id,
            asset_id=asset_id,
            shot_type=shot_type,
            reason=json.dumps(
                {
                    "manualFlagCanClear": reconcile.get("manualFlagCanClear"),
                    "manualFlagCleared": reconcile.get("manualFlagCleared"),
                    "canRun": status.get("canRun"),
                    "manualReviewRequired": status.get("manualReviewRequired"),
                    "assetStatus": result["assetStatus"],
                },
                ensure_ascii=False,
            ),
            output_path=str(reconcile.get("reportPath") or ""),
        )
    return result


def _auto_reconcile_existing_manual_flag(
    root: Path | str | None,
    *,
    file_qa_func: Callable[..., Mapping[str, int]],
) -> dict[str, Any]:
    paths = pipeline_paths(root)
    manual_flag = paths.manifests / "manual_review_required.flag"
    reason = _manual_review_reason(root)
    result: dict[str, Any] = {
        "attempted": False,
        "resumed": False,
        "reason": reason,
        "reconcile": {},
        "status": {},
    }
    if not manual_flag.exists():
        return result
    if reason not in RECOVERABLE_MANUAL_REVIEW_REASONS:
        result["reason"] = f"manual_flag_reason_not_recoverable:{reason}"
        return result
    result["attempted"] = True
    try:
        reconcile = reconcile_bounded_chunk(
            root=root,
            dry_run=False,
            apply=True,
            clear_manual_flag_if_safe=True,
            file_qa_func=file_qa_func,
        )
    except Exception as exc:  # noqa: BLE001 - unsafe reconcile leaves manual review in place.
        result["reason"] = f"pre_run_auto_reconcile_failed:{exc}"
        return result
    result["reconcile"] = dict(reconcile)
    status = bounded_chunk_status(root=root)
    result["status"] = dict(status)
    safe_to_resume = (
        bool(reconcile.get("manualFlagCanClear"))
        and bool(reconcile.get("manualFlagCleared"))
        and not bool(status.get("manualReviewRequired"))
        and bool(status.get("canRun"))
    )
    if safe_to_resume:
        result["resumed"] = True
        _append_event(
            root,
            str(status.get("chunkId") or reconcile.get("chunkId") or ""),
            event_type="pre_run_manual_flag_auto_reconciled",
            from_status="needs_manual_review",
            to_status=str(status.get("status") or ""),
            reason=reason,
            output_path=str(reconcile.get("reportPath") or ""),
        )
    else:
        result["reason"] = "pre_run_auto_reconcile_not_safe_to_resume"
        chunk_id = str(status.get("chunkId") or reconcile.get("chunkId") or "")
        if chunk_id:
            _append_event(
                root,
                chunk_id,
                event_type="pre_run_manual_flag_auto_reconcile_blocked",
                reason=json.dumps(
                    {
                        "manualFlagCanClear": reconcile.get("manualFlagCanClear"),
                        "manualFlagCleared": reconcile.get("manualFlagCleared"),
                        "canRun": status.get("canRun"),
                        "manualReviewRequired": status.get("manualReviewRequired"),
                    },
                    ensure_ascii=False,
                ),
                output_path=str(reconcile.get("reportPath") or ""),
            )
    return result


def run_bounded_chunk(
    *,
    root: Path | str | None = None,
    resume: bool = False,
    config: BoundedExecutorConfig | None = None,
    run_func: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    recover_func: Callable[..., Any] = recover_pending_imagegen,
    file_qa_func: Callable[..., Mapping[str, int]] = file_qa_single_asset,
    active_visual_func: Callable[..., Mapping[str, Any]] = run_active_visual_qa_all,
    audit_func: Callable[..., Mapping[str, Any]] = audit_distribution,
    which_func: Callable[[str], str | None] = shutil.which,
) -> dict[str, Any]:
    config = config or BoundedExecutorConfig.from_env()
    paths = pipeline_paths(root)
    ensure_base_dirs(paths)
    manual_flag = paths.manifests / "manual_review_required.flag"
    if manual_flag.exists():
        return {
            "status": "needs_manual_review",
            "reasonCode": "manual_review_required",
            "manualReviewFlag": to_portable_path(manual_flag),
            "canRun": False,
            "recommendedAction": "Run bounded-chunk-status and bounded-chunk-reconcile --dry-run; do not resume generation until manual review is resolved.",
        }
    if not config.active_visual_qa:
        flag = write_manual_review_flag(root, "active_visual_qa_disabled_for_bounded_chunk", {"stage": "bounded_chunk_run_precheck"})
        return {"status": "needs_manual_review", "reasonCode": "current_plan_not_executable", "manualReviewFlag": to_portable_path(flag)}
    try:
        validate_current_chunk_plan(root=root, strict=True)
        plan = read_current_plan(root)
        state = read_current_state(root)
    except PlanValidationError as exc:
        return {
            "status": "failed",
            "reasonCode": exc.reason_code,
            "error": str(exc),
            **dict(exc.details),
        }
    if not plan.get("identities"):
        return {"status": "no_eligible_assets", "planPath": to_portable_path(current_plan_path(root))}
    if str(state.get("status") or "") in CHUNK_TERMINAL_STATUSES:
        return {"status": state["status"], "planPath": to_portable_path(current_plan_path(root)), "statePath": to_portable_path(current_state_path(root))}

    if str(state.get("status") or "") == "planned":
        _transition_chunk(root, plan, state, "running")
    for identity in plan.get("identities", []):
        if str(state.get("status") or "") == "needs_manual_review":
            return bounded_chunk_status(root=root)
        profile_id = str(identity["profileId"])
        identity_status = str((state.get("identityStates") or {}).get(profile_id) or "")
        if identity_status in IDENTITY_TERMINAL_STATUSES or identity_status == "assets_complete":
            continue
        _transition_identity(root, plan, state, profile_id, "running")
        identity_ok = True
        for asset in sorted(identity.get("assets", []), key=lambda item: int(item.get("order") or 99)):
            if str(state.get("status") or "") == "needs_manual_review":
                return bounded_chunk_status(root=root)
            asset_id = str(asset["assetId"])
            asset_status = str((state.get("assetStates") or {}).get(asset_id) or asset.get("status") or "")
            if asset_status in GENERATION_COMPLETE_ASSET_STATUSES:
                continue
            try:
                ok = _process_asset(
                    root,
                    plan,
                    state,
                    identity,
                    asset,
                    config=config,
                    run_func=run_func,
                    recover_func=recover_func,
                    file_qa_func=file_qa_func,
                    which_func=which_func,
                )
            except BoundedBatchExecutorError as exc:
                if str(exc) == "child_forbidden_mutation":
                    auto_reconcile = _auto_reconcile_after_child_forbidden_mutation(
                        root,
                        chunk_id=str(plan["chunkId"]),
                        asset_id=asset_id,
                        profile_id=profile_id,
                        shot_type=str(asset.get("shotType") or ""),
                        file_qa_func=file_qa_func,
                    )
                    if auto_reconcile.get("resumed"):
                        plan = read_current_plan(root)
                        state = read_current_state(root)
                        asset_status = str((state.get("assetStates") or {}).get(asset_id) or "")
                        if asset_status == "file_qa_passed":
                            continue
                        if asset_status in {"file_qa_failed", "failed", "skipped"}:
                            identity_ok = False
                            break
                        continue
                status = bounded_chunk_status(root=root)
                status["reasonCode"] = str(exc)
                if str(exc) == "parent_managed_imagegen_required":
                    pending_payload = read_pending(pending_path(root))
                    handoff_dir = chunk_report_dir(root, str(status.get("chunkId") or "")) / "parent_imagegen_handoffs"
                    asset_attempt = f"{pending_payload.get('assetId')}_attempt{int(pending_payload.get('attempt') or 0)}"
                    status.update(
                        {
                            "status": "awaiting_parent_imagegen",
                            "canRun": False,
                            "pendingPath": to_portable_path(pending_path(root)),
                            "handoffPromptPath": to_portable_path(handoff_dir / f"{asset_attempt}.prompt.txt"),
                            "handoffReportPath": to_portable_path(handoff_dir / f"{asset_attempt}.json"),
                            "recommendedAction": "Use the parent Codex/Hermes imagegen surface with the handoff prompt, recover pending-imagegen, then resume the bounded chunk.",
                        }
                    )
                if str(exc) == "child_forbidden_mutation":
                    status["autoReconcile"] = auto_reconcile
                return status
            if not ok:
                identity_ok = False
                break
        if identity_ok:
            _transition_identity(root, plan, state, profile_id, "assets_complete")
        elif str(state.get("status") or "") == "needs_manual_review":
            return bounded_chunk_status(root=root)
        elif str((state.get("identityStates") or {}).get(profile_id) or "") not in IDENTITY_TERMINAL_STATUSES:
            _transition_identity(root, plan, state, profile_id, "failed", reason="asset_failed")

    if not _generation_complete(plan, state):
        _transition_chunk(root, plan, state, "failed", reason="generation_incomplete")
        return bounded_chunk_status(root=root)

    _transition_chunk(root, plan, state, "generation_complete")
    _transition_chunk(root, plan, state, "file_qa_complete")
    qa_result = run_bounded_chunk_qa(root=root, active_visual_func=active_visual_func, config=config)
    if qa_result.get("status") != "active_visual_qa_complete":
        return bounded_chunk_status(root=root)
    finalize_result = finalize_bounded_chunk(root=root, audit_func=audit_func)
    return finalize_result


def resume_bounded_chunk(**kwargs: Any) -> dict[str, Any]:
    kwargs["resume"] = True
    return run_bounded_chunk(**kwargs)


def _planned_asset_entries(plan: Mapping[str, Any]) -> list[tuple[Mapping[str, Any], Mapping[str, Any]]]:
    entries: list[tuple[Mapping[str, Any], Mapping[str, Any]]] = []
    for identity in plan.get("identities", []) or []:
        for asset in identity.get("assets", []) or []:
            entries.append((identity, asset))
    return entries


def _reconcile_file_qa_complete_from_manifest(root: Path | str | None, plan: dict[str, Any], state: dict[str, Any]) -> bool:
    entries = _planned_asset_entries(plan)
    if not entries:
        return False
    for identity, asset in entries:
        if not _sync_file_qa_passed_asset_from_manifest(
            root,
            plan,
            state,
            asset_id=str(asset.get("assetId") or ""),
            profile_id=str(identity.get("profileId") or ""),
            shot_type=str(asset.get("shotType") or ""),
            reason="manifest_file_qa_passed_qa_reconcile",
        ):
            return False
    for identity in plan.get("identities", []) or []:
        profile_id = str(identity.get("profileId") or "")
        if profile_id:
            _transition_identity(root, plan, state, profile_id, "assets_complete", reason="manifest_file_qa_passed_qa_reconcile")
    _transition_chunk(root, plan, state, "generation_complete", reason="manifest_file_qa_passed_qa_reconcile")
    _transition_chunk(root, plan, state, "file_qa_complete", reason="manifest_file_qa_passed_qa_reconcile")
    return True


def _refresh_distribution_stale_plan_after_reconcile(root: Path | str | None, plan: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "applied": False,
        "allowed": False,
        "reasonsBefore": [],
        "blockingReasons": [],
        "previousPlanHash": str(plan.get("planHash") or ""),
        "newPlanHash": "",
    }
    validation = validate_current_chunk_plan(root=root, strict=False)
    reasons = list(validation.get("reasons") or [])
    result["reasonsBefore"] = reasons
    if not reasons:
        result["allowed"] = True
        return result
    allowed_reasons = {"input_hash_changed:distributionAuditJsonSha256", "input_mtime_newer:distributionAuditJson"}
    blocking = [reason for reason in reasons if reason not in allowed_reasons]
    result["blockingReasons"] = blocking
    if blocking:
        return result
    result["allowed"] = True
    history = list(plan.get("resumeInputRefreshHistory") or [])
    history.append(
        {
            "refreshedAt": now_utc(),
            "reason": "reconcile_resume_distribution_audit_snapshot_refresh",
            "previousPlanHash": result["previousPlanHash"],
            "reasonsBefore": reasons,
        }
    )
    plan["resumeInputRefreshHistory"] = history
    plan["inputHashes"] = _input_hashes(root)
    plan["inputMtimes"] = _input_mtimes(root)
    plan["updatedAt"] = now_utc()
    plan["planHash"] = _plan_hash(plan)
    state["planHash"] = plan["planHash"]
    state["updatedAt"] = now_utc()
    _save_plan_state(root, plan, state)
    result["newPlanHash"] = str(plan.get("planHash") or "")
    result["applied"] = True
    return result


def _sanitize_asset_qa_manifest_for_reconcile(
    root: Path | str | None,
    *,
    chunk_id: str,
    apply: bool,
) -> dict[str, Any]:
    manifest = pipeline_paths(root).manifests / "asset_qa_manifest.jsonl"
    result: dict[str, Any] = {
        "manifestPath": to_portable_path(manifest),
        "exists": manifest.exists(),
        "rowsTotal": 0,
        "rowsKept": 0,
        "rowsQuarantined": 0,
        "backupPath": "",
        "quarantinePath": "",
        "applied": False,
    }
    if not manifest.exists():
        return result
    rows = read_jsonl(manifest)
    kept: list[Mapping[str, Any]] = []
    quarantined: list[Mapping[str, Any]] = []
    for row in rows:
        if isinstance(row, Mapping) and row.get("schemaVersion") == ASSET_QA_MANIFEST_SCHEMA_VERSION:
            kept.append(row)
        else:
            quarantined.append(row)
    result.update({"rowsTotal": len(rows), "rowsKept": len(kept), "rowsQuarantined": len(quarantined)})
    if not apply or not quarantined:
        return result
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    quarantine_dir = chunk_report_dir(root, chunk_id) / "quarantine"
    quarantine_dir.mkdir(parents=True, exist_ok=True)
    backup_path = quarantine_dir / f"asset_qa_manifest_before_sanitize_{stamp}.jsonl"
    quarantine_path = quarantine_dir / f"asset_qa_manifest_non_visual_rows_{stamp}.jsonl"
    shutil.copy2(manifest, backup_path)
    write_jsonl(quarantine_path, quarantined)
    write_jsonl(manifest, kept)
    result.update(
        {
            "backupPath": to_portable_path(backup_path),
            "quarantinePath": to_portable_path(quarantine_path),
            "applied": True,
        }
    )
    return result


def _extra_generation_assets_not_in_manifest(root: Path | str | None) -> list[dict[str, Any]]:
    paths = pipeline_paths(root)
    asset_ids: set[str] = set()
    for name in ("ai_profile_assets_v3.jsonl", "asset_manifest.jsonl"):
        for row in read_jsonl(paths.manifests / name):
            asset_id = str(row.get("assetId") or "")
            if asset_id:
                asset_ids.add(asset_id)
    extras: list[dict[str, Any]] = []
    for row in load_generation_manifest(paths):
        asset_id = str(row.get("assetId") or "")
        if asset_id and asset_id not in asset_ids:
            extras.append(
                {
                    "assetId": asset_id,
                    "profileId": row.get("profileId", ""),
                    "shotType": row.get("shotType", ""),
                    "localPath": row.get("localPath", ""),
                    "finalPath": row.get("finalPath", ""),
                    "status": row.get("status", ""),
                    "classification": "extra_generation_asset_not_in_asset_manifest",
                    "countsTowardApproval": False,
                }
            )
    return extras


def _quarantine_extra_generation_assets(root: Path | str | None, extras: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    paths = pipeline_paths(root)
    quarantined: list[dict[str, Any]] = []
    for row in extras:
        asset_id = str(row.get("assetId") or "")
        for key in ("localPath", "finalPath"):
            source = Path(str(row.get(key) or ""))
            if not source.exists() or not source.is_file():
                continue
            target = paths.ai_image / "quarantine" / f"{asset_id}__{source.name}"
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                quarantined.append({"assetId": asset_id, "source": to_portable_path(source), "target": to_portable_path(target), "status": "already_quarantined"})
                continue
            shutil.move(str(source), str(target))
            quarantined.append({"assetId": asset_id, "source": to_portable_path(source), "target": to_portable_path(target), "status": "quarantined"})
    return quarantined


def _reset_archive_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _unique_directory(path: Path) -> Path:
    if not path.exists():
        return path
    for index in range(2, 1000):
        candidate = path.with_name(f"{path.name}_{index}")
        if not candidate.exists():
            return candidate
    raise BoundedBatchExecutorError(f"Could not allocate unique archive directory for {path}")


def _copy_file_if_exists(source: Path, destination: Path) -> dict[str, Any]:
    row = {
        "source": to_portable_path(source),
        "destination": to_portable_path(destination),
        "exists": source.exists() and source.is_file(),
        "copied": False,
    }
    if row["exists"]:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        row["copied"] = True
    return row


def _copy_tree_if_exists(source: Path, destination: Path) -> dict[str, Any]:
    row = {
        "source": to_portable_path(source),
        "destination": to_portable_path(destination),
        "exists": source.exists() and source.is_dir(),
        "copied": False,
    }
    if row["exists"]:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, destination, dirs_exist_ok=True)
        row["copied"] = True
    return row


def _manual_flag_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {"reason": text.splitlines()[0].strip() if text.strip() else "manual_review_required", "rawText": text}
    return dict(payload) if isinstance(payload, Mapping) else {"reason": "manual_review_required", "rawValue": payload}


def _append_reset_manual_flag_reason(root: Path | str | None, *, chunk_id: str, reset_report_path: Path) -> bool:
    flag = pipeline_paths(root).manifests / "manual_review_required.flag"
    if not flag.exists():
        return False
    payload = _manual_flag_payload(flag)
    previous_reason = str(payload.get("reason") or payload.get("reasonCode") or "manual_review_required")
    reasons: list[str] = []
    for value in payload.get("reasons", []) if isinstance(payload.get("reasons"), Sequence) and not isinstance(payload.get("reasons"), (str, bytes)) else []:
        reason = str(value or "").strip()
        if reason and reason not in reasons:
            reasons.append(reason)
    for reason in (previous_reason, "current_chunk_archived_reset_pending_new_plan"):
        if reason and reason not in reasons:
            reasons.append(reason)
    details = dict(payload.get("details") or {}) if isinstance(payload.get("details"), Mapping) else {}
    details.update(
        {
            "archivedChunkId": chunk_id,
            "resetStatus": "current_chunk_archived_reset_pending_new_plan",
            "resetReportPath": to_portable_path(reset_report_path),
        }
    )
    updated = {
        "schemaVersion": "seolleyeon_active_visual_manual_review_v3",
        "reason": previous_reason,
        "reasons": reasons,
        "details": details,
        "updatedAt": now_utc(),
    }
    flag.write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


def _clear_manual_flag_after_reset_if_safe(root: Path | str | None) -> dict[str, Any]:
    flag = pipeline_paths(root).manifests / "manual_review_required.flag"
    result = {
        "requested": True,
        "cleared": False,
        "safe": False,
        "reasonsIfNotCleared": [],
        "completionFailureReasonsAfterClear": [],
    }
    if pending_is_unresolved(read_pending(pending_path(root))):
        result["reasonsIfNotCleared"].append("pending_unresolved")
        return result
    if current_plan_path(root).exists() or current_state_path(root).exists():
        result["reasonsIfNotCleared"].append("active_current_chunk_still_present")
        return result
    if not flag.exists():
        result["safe"] = True
        return result
    original = flag.read_text(encoding="utf-8", errors="replace")
    flag.unlink()
    try:
        from .completion import completion_check

        completion = completion_check(root=root)
    except Exception as exc:  # noqa: BLE001 - restore the flag on any uncertainty.
        flag.write_text(original, encoding="utf-8")
        result["reasonsIfNotCleared"].append(f"completion_check_failed:{exc}")
        return result
    failures = set(str(reason) for reason in completion.get("failureReasons", []))
    result["completionFailureReasonsAfterClear"] = sorted(failures)
    allowed_failures = {"distribution_mismatch"}
    if (
        not current_plan_path(root).exists()
        and not current_state_path(root).exists()
        and int(completion.get("approvedCompleteIdentities") or 0) == 0
        and int(completion.get("approvedImages") or 0) == 0
    ):
        allowed_failures.add("missing_visual_verdict")
    if completion.get("passed") or not failures or (failures - allowed_failures):
        flag.write_text(original, encoding="utf-8")
        result["reasonsIfNotCleared"].append("completion_not_limited_to_distribution_mismatch")
        return result
    result["safe"] = True
    result["cleared"] = True
    return result


def _copy_extra_generation_assets_to_quarantine(root: Path | str | None, extras: Sequence[Mapping[str, Any]], *, chunk_id: str, stamp: str) -> list[dict[str, Any]]:
    paths = pipeline_paths(root)
    quarantine_dir = paths.ai_image / "quarantine" / f"{chunk_id}_extras_{stamp}"
    copied: list[dict[str, Any]] = []
    for row in extras:
        asset_id = str(row.get("assetId") or "")
        for key in ("localPath", "finalPath"):
            source = Path(str(row.get(key) or ""))
            if not source.exists() or not source.is_file():
                continue
            destination = quarantine_dir / asset_id / source.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            if not destination.exists():
                shutil.copy2(source, destination)
                status = "copied_to_quarantine_original_preserved"
            else:
                status = "already_copied_original_preserved"
            copied.append({"assetId": asset_id, "source": to_portable_path(source), "target": to_portable_path(destination), "status": status})
    return copied


def _planned_reset_archive_items(
    root: Path | str | None,
    *,
    chunk_id: str,
    reports_archive_dir: Path,
    manifest_archive_dir: Path,
) -> dict[str, list[dict[str, Any]]]:
    paths = pipeline_paths(root)
    files_to_archive = [
        {
            "source": to_portable_path(current_plan_path(root)),
            "destination": to_portable_path(reports_archive_dir / "active_pointers" / "current_chunk_plan.json"),
            "exists": current_plan_path(root).exists(),
            "kind": "active_pointer",
        },
        {
            "source": to_portable_path(current_state_path(root)),
            "destination": to_portable_path(reports_archive_dir / "active_pointers" / "current_chunk_state.json"),
            "exists": current_state_path(root).exists(),
            "kind": "active_pointer",
        },
        {
            "source": to_portable_path(pending_path(root)),
            "destination": to_portable_path(reports_archive_dir / "active_pointers" / "pending-imagegen.json"),
            "exists": pending_path(root).exists(),
            "kind": "active_pointer",
        },
        {
            "source": to_portable_path(chunk_report_dir(root, chunk_id)),
            "destination": to_portable_path(reports_archive_dir / "chunk_reports"),
            "exists": chunk_report_dir(root, chunk_id).exists(),
            "kind": "chunk_report_tree",
        },
    ]
    visual_dir = paths.reports / "visual_verdict"
    for filename in RESET_VISUAL_VERDICT_FILES:
        source = visual_dir / filename
        files_to_archive.append(
            {
                "source": to_portable_path(source),
                "destination": to_portable_path(reports_archive_dir / "visual_verdict" / filename),
                "exists": source.exists(),
                "kind": "visual_verdict",
            }
        )
    parts_dir = visual_dir / "parts"
    files_to_archive.append(
        {
            "source": to_portable_path(parts_dir),
            "destination": to_portable_path(reports_archive_dir / "visual_verdict" / "parts"),
            "exists": parts_dir.exists(),
            "kind": "visual_verdict_parts",
        }
    )
    for log_path in sorted(paths.logs.rglob(f"*{chunk_id}*")) if paths.logs.exists() else []:
        if log_path.is_file():
            files_to_archive.append(
                {
                    "source": to_portable_path(log_path),
                    "destination": to_portable_path(reports_archive_dir / "logs" / log_path.name),
                    "exists": True,
                    "kind": "chunk_log",
                }
            )
    manifest_snapshots = [
        {
            "source": to_portable_path(paths.manifests / filename),
            "destination": to_portable_path(manifest_archive_dir / filename),
            "exists": (paths.manifests / filename).exists(),
            "kind": "manifest_snapshot",
        }
        for filename in RESET_MANIFEST_SNAPSHOT_FILES
    ]
    return {"filesToArchive": files_to_archive, "manifestSnapshotsToArchive": manifest_snapshots}


def bounded_chunk_reset(
    *,
    root: Path | str | None = None,
    archive_current: bool = False,
    dry_run: bool = False,
    clear_manual_flag_if_safe: bool = False,
    quarantine_extra: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    paths = pipeline_paths(root)
    ensure_base_dirs(paths)
    stamp = _reset_archive_stamp()
    plan_path = current_plan_path(root)
    state_path = current_state_path(root)
    plan: dict[str, Any] = {}
    state: dict[str, Any] = {}
    reasons_if_unsafe: list[str] = []
    if not archive_current:
        reasons_if_unsafe.append("archive_current_required")
    if not plan_path.exists():
        reasons_if_unsafe.append("current_chunk_plan_missing")
    else:
        try:
            plan = read_current_plan(root)
        except Exception as exc:  # noqa: BLE001 - malformed active pointers are unsafe to reset silently.
            reasons_if_unsafe.append(f"current_chunk_plan_unreadable:{exc}")
    if not state_path.exists():
        reasons_if_unsafe.append("current_chunk_state_missing")
    else:
        try:
            state = read_current_state(root)
        except Exception as exc:  # noqa: BLE001
            reasons_if_unsafe.append(f"current_chunk_state_unreadable:{exc}")
    chunk_id = str(plan.get("chunkId") or state.get("chunkId") or "unknown_chunk")
    status_before = str(state.get("status") or plan.get("status") or "")
    reports_archive_dir = _unique_directory(paths.reports / "chunks" / "archive" / f"{chunk_id}_{stamp}")
    manifest_archive_dir = _unique_directory(paths.manifests / "archive" / f"{chunk_id}_reset_{stamp}")
    pending_payload = read_pending(pending_path(root))
    pending_status = str(pending_payload.get("status") or "absent") if pending_payload else "absent"
    if pending_payload and pending_is_unresolved(pending_payload):
        reasons_if_unsafe.append("pending_unresolved")
    if plan and state:
        plan_chunk_id = str(plan.get("chunkId") or "")
        state_chunk_id = str(state.get("chunkId") or "")
        if plan_chunk_id and state_chunk_id and plan_chunk_id != state_chunk_id:
            reasons_if_unsafe.append("current_chunk_plan_state_mismatch")
        status = status_before
        if not force and status not in RESETTABLE_CHUNK_STATUSES:
            if bool(plan.get("executable")) and status in EXECUTABLE_CHUNK_STATUSES:
                reasons_if_unsafe.append("active_executable_chunk_not_resettable")
            else:
                reasons_if_unsafe.append(f"chunk_status_not_resettable:{status or 'missing'}")
    planned_items = _planned_reset_archive_items(root, chunk_id=chunk_id, reports_archive_dir=reports_archive_dir, manifest_archive_dir=manifest_archive_dir)
    before_snapshot = _progress_snapshot(root)
    extras = _extra_generation_assets_not_in_manifest(root)
    safe_to_apply = not reasons_if_unsafe
    report_path = chunk_report_dir(root, chunk_id) / ("reset_dry_run_report.json" if dry_run else "reset_report.json")
    current_pointers_to_reset = [
        row for row in planned_items["filesToArchive"] if row.get("kind") == "active_pointer" and row.get("exists")
    ]
    report: dict[str, Any] = {
        "schemaVersion": RESET_SCHEMA_VERSION,
        "chunkId": chunk_id,
        "dryRun": bool(dry_run),
        "archiveCurrent": bool(archive_current),
        "statusBefore": status_before,
        "resetDecision": "archive_preserving_reset",
        "createdAt": now_utc(),
        "safeToApply": safe_to_apply,
        "reasonsIfUnsafe": reasons_if_unsafe,
        "filesToArchive": planned_items["filesToArchive"],
        "manifestSnapshotsToArchive": planned_items["manifestSnapshotsToArchive"],
        "currentPointersToReset": current_pointers_to_reset,
        "pendingStatus": pending_status,
        "manualFlagAction": "left_present" if (paths.manifests / "manual_review_required.flag").exists() else "absent",
        "extraAssetsAction": "copy_to_quarantine_original_preserved" if quarantine_extra else "left_in_place",
        "extraGenerationAssets": extras,
        "approvalCountWouldChange": False,
        "distributionCountWouldChange": False,
        "approvalCountBefore": int(before_snapshot.get("approvedIdentityCount") or 0),
        "distributionCountBefore": int(before_snapshot.get("approvedAssetCount") or 0),
        "generatedFilesPreserved": True,
        "approvedCountChanged": False,
        "distributionCountChanged": False,
        "manualFlagCleared": False,
        "reportPath": to_portable_path(report_path),
        "archivedReportsDir": to_portable_path(reports_archive_dir),
        "archivedManifestSnapshotDir": to_portable_path(manifest_archive_dir),
        "nextRecommendedCommand": "python scripts/run_ai_image_pipeline_v3.py bounded-chunk-reset --root . --archive-current" if dry_run and safe_to_apply else "",
    }
    if dry_run:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        _write_json(report_path, report)
        return report
    if not safe_to_apply:
        report.update({"status": "failed"})
        report_path.parent.mkdir(parents=True, exist_ok=True)
        _write_json(report_path, report)
        return report

    reports_archive_dir.mkdir(parents=True, exist_ok=True)
    manifest_archive_dir.mkdir(parents=True, exist_ok=True)
    archived_files: list[dict[str, Any]] = []
    active_pointer_dir = reports_archive_dir / "active_pointers"
    for pointer in current_pointers_to_reset:
        source = Path(str(pointer["source"]))
        destination = Path(str(pointer["destination"]))
        if source.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(destination))
            archived_files.append({**pointer, "archived": True})
    chunk_dir = chunk_report_dir(root, chunk_id)
    archived_files.append(_copy_tree_if_exists(chunk_dir, reports_archive_dir / "chunk_reports"))
    visual_dir = paths.reports / "visual_verdict"
    for filename in RESET_VISUAL_VERDICT_FILES:
        archived_files.append(_copy_file_if_exists(visual_dir / filename, reports_archive_dir / "visual_verdict" / filename))
    archived_files.append(_copy_tree_if_exists(visual_dir / "parts", reports_archive_dir / "visual_verdict" / "parts"))
    for log_path in sorted(paths.logs.rglob(f"*{chunk_id}*")) if paths.logs.exists() else []:
        if log_path.is_file():
            archived_files.append(_copy_file_if_exists(log_path, reports_archive_dir / "logs" / log_path.name))
    manifest_archives: list[dict[str, Any]] = []
    for filename in RESET_MANIFEST_SNAPSHOT_FILES:
        manifest_archives.append(_copy_file_if_exists(paths.manifests / filename, manifest_archive_dir / filename))
    quarantined_files: list[dict[str, Any]] = []
    if quarantine_extra and extras:
        quarantined_files = _copy_extra_generation_assets_to_quarantine(root, extras, chunk_id=chunk_id, stamp=stamp)
    reset_report_path = chunk_report_dir(root, chunk_id) / "reset_report.json"
    manual_flag_appended = _append_reset_manual_flag_reason(root, chunk_id=chunk_id, reset_report_path=reset_report_path)
    clear_result = {"requested": bool(clear_manual_flag_if_safe), "cleared": False, "safe": False, "reasonsIfNotCleared": []}
    if clear_manual_flag_if_safe:
        clear_result = _clear_manual_flag_after_reset_if_safe(root)
    after_snapshot = _progress_snapshot(root)
    approved_count_changed = int(before_snapshot.get("approvedIdentityCount") or 0) != int(after_snapshot.get("approvedIdentityCount") or 0)
    distribution_count_changed = int(before_snapshot.get("approvedAssetCount") or 0) != int(after_snapshot.get("approvedAssetCount") or 0)
    archived_plan_path = active_pointer_dir / "current_chunk_plan.json"
    archived_state_path = active_pointer_dir / "current_chunk_state.json"
    report.update(
        {
            "status": "reset",
            "archivedPlanPath": to_portable_path(archived_plan_path) if archived_plan_path.exists() else "",
            "archivedStatePath": to_portable_path(archived_state_path) if archived_state_path.exists() else "",
            "archivedPendingPath": to_portable_path(active_pointer_dir / "pending-imagegen.json") if (active_pointer_dir / "pending-imagegen.json").exists() else "",
            "archivedFiles": archived_files,
            "manifestSnapshotsArchived": manifest_archives,
            "quarantinedFiles": quarantined_files,
            "manualFlagReasonAppended": manual_flag_appended,
            "manualFlagClearResult": clear_result,
            "manualFlagCleared": bool(clear_result.get("cleared")),
            "approvedCountChanged": approved_count_changed,
            "distributionCountChanged": distribution_count_changed,
            "approvalCountAfter": int(after_snapshot.get("approvedIdentityCount") or 0),
            "distributionCountAfter": int(after_snapshot.get("approvedAssetCount") or 0),
            "nextRecommendedAction": "create_fresh_production_plan_after_manual_flag_resolution",
        }
    )
    _append_event(root, chunk_id, event_type="chunk_reset", from_status=status_before, to_status="reset", reason="archive_preserving_reset", output_path=to_portable_path(reset_report_path))
    _write_json(reset_report_path, report)
    return report


def reconcile_bounded_chunk(
    *,
    root: Path | str | None = None,
    dry_run: bool = True,
    apply: bool = False,
    clear_manual_flag_if_safe: bool = False,
    quarantine_extra: bool = False,
    file_qa_func: Callable[..., Mapping[str, int]] = file_qa_single_asset,
) -> dict[str, Any]:
    paths = pipeline_paths(root)
    plan = read_current_plan(root)
    state = read_current_state(root)
    chunk_id = str(plan.get("chunkId") or "")
    pending_payload = read_pending(pending_path(root))
    planned_entries = _planned_asset_entries(plan)
    planned_by_asset = {str(asset.get("assetId") or ""): (identity, asset) for identity, asset in planned_entries}
    report: dict[str, Any] = {
        "schemaVersion": "seolleyeon_bounded_chunk_reconcile_v3",
        "chunkId": chunk_id,
        "dryRun": bool(dry_run),
        "apply": bool(apply),
        "manualReviewReason": _manual_review_reason(root),
        "manualFlagRecoverable": False,
        "existingFinalFiles": 0,
        "plannedExistingFiles": 0,
        "reconciledAssets": [],
        "reconstructedReceipts": [],
        "fileQaPassedAssets": 0,
        "fileQaFailedAssets": 0,
        "quarantinedFiles": [],
        "unknownFiles": [],
        "extraGenerationAssetsNotInManifest": [],
        "extraGenerationAssetCount": 0,
        "quarantineExtraRequested": bool(quarantine_extra),
        "pendingStatus": "",
        "resolvedPendingReconciled": False,
        "resolvedPendingMismatch": [],
        "finalizedFailedPendingAssetId": "",
        "finalizedFailedPendingSkipped": False,
        "manualFlagCanClear": False,
        "reasonsIfCannotClear": [],
        "stateChanged": False,
        "chunkStatusRestored": False,
        "planInputRefresh": {"applied": False},
        "reportPath": to_portable_path(chunk_report_dir(root, chunk_id) / "reconcile_report.json"),
    }
    extras = _extra_generation_assets_not_in_manifest(root)
    report["extraGenerationAssetsNotInManifest"] = extras
    report["extraGenerationAssetCount"] = len(extras)
    if extras:
        report["reasonsIfCannotClear"].append("extra_generation_assets_not_in_asset_manifest")
    report["assetQaManifestSanitization"] = _sanitize_asset_qa_manifest_for_reconcile(root, chunk_id=chunk_id, apply=bool(apply and not dry_run))
    if pending_payload:
        report["pendingStatus"] = str(pending_payload.get("status") or "")
        if pending_is_resolved(pending_payload) and (
            str(pending_payload.get("status") or "") == "failed"
            or str(pending_payload.get("recoveryStatus") or "") in {"not_recoverable", "failed"}
            or str(pending_payload.get("resolutionMode") or "") == "finalize_failed"
        ):
            report["finalizedFailedPendingAssetId"] = str(pending_payload.get("assetId") or "")
    if pending_payload and pending_is_unresolved(pending_payload):
        report["reasonsIfCannotClear"].append("pending_unresolved")
    elif pending_payload and pending_is_resolved(pending_payload):
        pending_mismatches: list[str] = []
        pending_asset_id = str(pending_payload.get("assetId") or "")
        pending_chunk_id = str(pending_payload.get("chunkId") or "")
        if pending_asset_id not in planned_by_asset:
            pending_mismatches.append("asset_not_in_current_plan")
        if pending_chunk_id and chunk_id and pending_chunk_id != chunk_id:
            pending_mismatches.append("chunk_mismatch")
        if pending_asset_id in planned_by_asset:
            _identity, planned_asset = planned_by_asset[pending_asset_id]
            planned_final = Path(str(planned_asset.get("finalPath") or ""))
            pending_final_value = str(pending_payload.get("expectedFinalPath") or pending_payload.get("finalPath") or "")
            pending_final = Path(pending_final_value) if pending_final_value else Path()
            if pending_final_value and planned_final:
                try:
                    if pending_final.resolve() != planned_final.resolve():
                        pending_mismatches.append("final_path_mismatch")
                except OSError:
                    pending_mismatches.append("final_path_invalid")
        if pending_mismatches:
            report["resolvedPendingMismatch"] = sorted(set(pending_mismatches))
            report["reasonsIfCannotClear"].append("resolved_pending_mismatch")
        else:
            report["resolvedPendingReconciled"] = True
    manual_flag = paths.manifests / "manual_review_required.flag"
    if manual_flag.exists():
        reason = str(report["manualReviewReason"] or "")
        if reason in RECOVERABLE_MANUAL_REVIEW_REASONS:
            report["manualFlagRecoverable"] = True
        else:
            report["reasonsIfCannotClear"].append(f"manual_flag_reason_not_recoverable:{reason}")

    for identity, asset in planned_entries:
        asset_id = str(asset.get("assetId") or "")
        if asset_id and asset_id == str(report.get("finalizedFailedPendingAssetId") or ""):
            report["finalizedFailedPendingSkipped"] = True
            continue
        profile_id = str(identity.get("profileId") or "")
        shot_type = str(asset.get("shotType") or "")
        row = _latest_generation_asset(root, asset_id)
        final_path = Path(str(asset.get("finalPath") or row.get("finalPath") or ""))
        if final_path.exists():
            report["existingFinalFiles"] += 1
            report["plannedExistingFiles"] += 1
        else:
            continue
        detail = inspect_image_detail(final_path)
        ok = bool(detail.get("ok"))
        if ok:
            report["fileQaPassedAssets"] += 1
        else:
            report["fileQaFailedAssets"] += 1
        report["reconciledAssets"].append({"assetId": asset_id, "fileQaPassed": ok, "finalPath": to_portable_path(final_path)})

        asset_status = str((state.get("assetStates") or {}).get(asset_id) or asset.get("status") or "")
        if ok and asset_status == "file_qa_passed" and _generation_file_qa_passed(row):
            continue

        attempt = int(row.get("attemptCount") or row.get("attempt") or asset.get("attempt") or 1)
        raw_path = Path(str(row.get("expectedRawPath") or row.get("localPath") or asset.get("rawPathPattern") or ""))
        if "attemptXX" in str(raw_path):
            raw_path = paths.raw / f"{asset_id}__attempt{attempt:02d}.png"
        expected = {
            "chunkId": chunk_id,
            "assetId": asset_id,
            "profileId": profile_id,
            "gender": str(identity.get("gender") or row.get("gender") or ""),
            "numericId": str(identity.get("numericId") or row.get("numericId") or ""),
            "shotType": shot_type,
            "attempt": attempt,
            "expectedRawPath": to_portable_path(raw_path if raw_path.exists() else final_path),
            "expectedFinalPath": to_portable_path(final_path),
            "referencePath": str(asset.get("referenceImagePath") or row.get("resolvedReferencePath") or ""),
        }
        receipt_path = transaction_receipt_path(root, chunk_id, asset_id, attempt)
        receipt = build_receipt_from_existing_file(root=root, expected=expected)
        if not receipt_path.exists():
            report["reconstructedReceipts"].append(to_portable_path(receipt_path))
        if apply and not dry_run:
            if not receipt_path.exists():
                write_receipt(receipt_path, receipt)
            pending_for_commit = {
                **expected,
                "expectedReceiptPath": to_portable_path(receipt_path),
                "expectedRawPath": expected["expectedRawPath"],
                "expectedFinalPath": expected["expectedFinalPath"],
            }
            if ok:
                try:
                    receipt_result = verify_one_asset_transaction(
                        root=root,
                        receipt_path=receipt_path,
                        expected=pending_for_commit,
                        pending_payload={**pending_for_commit, "status": "resolved", "resolved": True},
                    )
                except OneAssetTransactionError:
                    receipt_result = {"receipt": receipt, "valid": True}
                _commit_verified_transaction(
                    root,
                    plan,
                    state,
                    asset_id=asset_id,
                    profile_id=profile_id,
                    shot_type=shot_type,
                    pending_payload=pending_for_commit,
                    receipt_result=receipt_result,
                    file_qa_func=file_qa_func,
                    reason="parent_reconcile_existing_file",
                )
            else:
                _transition_asset(root, plan, state, asset_id, "file_qa_failed", profile_id=profile_id, shot_type=shot_type, reason="reconcile_file_qa_failed")
            report["stateChanged"] = True

    if apply and not dry_run and not manual_flag.exists() and not pending_is_unresolved(pending_payload):
        asset_states = state.get("assetStates") if isinstance(state.get("assetStates"), Mapping) else {}
        has_remaining_planned = any(str(value) == "planned" for value in asset_states.values())
        has_active_blocker = any(str(value) in {"pending_imagegen", "imagegen_called", "recovered", "file_qa_failed"} for value in asset_states.values())
        if has_remaining_planned and not has_active_blocker and str(state.get("status") or "") in {"needs_manual_review", "failed"}:
            _transition_chunk(root, plan, state, "running", reason="terminal_failed_asset_continue_after_reconcile")
            report["chunkStatusRestored"] = True
            report["stateChanged"] = True

    if manual_flag.exists() and report["manualReviewReason"] in {"bounded_recovery_failed", "one_asset_receipt_missing_or_invalid_requires_reconcile"} and int(report["plannedExistingFiles"]) <= 0:
        report["reasonsIfCannotClear"].append("no_reconcilable_final_files")

    if not report["reasonsIfCannotClear"]:
        report["manualFlagCanClear"] = True
    if apply and not dry_run and clear_manual_flag_if_safe and report["manualFlagCanClear"]:
        if manual_flag.exists():
            manual_flag.unlink()
            report["manualFlagCleared"] = True
        else:
            report["manualFlagCleared"] = False
        if str(state.get("status") or "") == "needs_manual_review":
            _transition_chunk(root, plan, state, "running", reason="manual_review_cleared_after_reconcile")
            report["chunkStatusRestored"] = True
            report["stateChanged"] = True
        report["planInputRefresh"] = _refresh_distribution_stale_plan_after_reconcile(root, plan, state)
        if report["planInputRefresh"].get("applied"):
            report["stateChanged"] = True
    elif manual_flag.exists():
        report["manualFlagCleared"] = False
    if apply and not dry_run and quarantine_extra and extras:
        report["quarantinedFiles"].extend(_quarantine_extra_generation_assets(root, extras))
    report_path = chunk_report_dir(root, chunk_id) / "reconcile_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def _call_active_visual(
    active_visual_func: Callable[..., Mapping[str, Any]],
    *,
    root: Path | str | None,
    chunk_id: str,
    strict_chunk_scope: bool = False,
    asset_whitelist: Path | str | None = None,
    contact_sheet_index: Path | str | None = None,
) -> Mapping[str, Any]:
    try:
        return active_visual_func(
            root=root,
            chunk_id=chunk_id,
            strict_chunk_scope=strict_chunk_scope,
            asset_whitelist=asset_whitelist,
            contact_sheet_index=contact_sheet_index,
        )
    except TypeError:
        try:
            return active_visual_func(root=root, chunk_id=chunk_id)
        except TypeError:
            return active_visual_func(root=root)


def run_bounded_chunk_qa(
    *,
    root: Path | str | None = None,
    active_visual_func: Callable[..., Mapping[str, Any]] = run_active_visual_qa_all,
    config: BoundedExecutorConfig | None = None,
) -> dict[str, Any]:
    config = config or BoundedExecutorConfig.from_env()
    plan = read_current_plan(root)
    state = read_current_state(root)
    if str(state.get("status") or "") not in {"file_qa_complete", "generation_complete", "active_visual_qa_running"}:
        if not _reconcile_file_qa_complete_from_manifest(root, plan, state):
            raise BoundedBatchExecutorError("Bounded chunk cannot run active visual QA before file QA completes.")
        state = read_current_state(root)
    if not config.active_visual_qa:
        flag = write_manual_review_flag(root, "active_visual_qa_disabled_for_bounded_chunk", {"chunkId": plan["chunkId"]})
        _transition_chunk(root, plan, state, "needs_manual_review", reason="active_visual_qa_disabled")
        return {"status": "needs_manual_review", "manualReviewFlag": to_portable_path(flag)}
    strict_sheets = generate_strict_chunk_contact_sheets(root=root, chunk_id=str(plan["chunkId"]))
    _transition_chunk(root, plan, state, "active_visual_qa_running")
    try:
        result = _call_active_visual(
            active_visual_func,
            root=root,
            chunk_id=str(plan["chunkId"]),
            strict_chunk_scope=True,
            asset_whitelist=strict_sheets.get("assetWhitelistPath"),
            contact_sheet_index=strict_sheets.get("contactSheetIndexPath"),
        )
    except Exception as exc:  # noqa: BLE001 - strict visual QA failure forces manual review.
        flag = write_manual_review_flag(root, "bounded_active_visual_qa_failed", {"chunkId": plan["chunkId"], "error": str(exc)})
        _transition_chunk(root, plan, state, "needs_manual_review", reason=f"active_visual_qa_failed:{exc}")
        return {"status": "needs_manual_review", "manualReviewFlag": to_portable_path(flag)}
    state = read_current_state(root)
    state["activeVisualQaComplete"] = True
    _transition_chunk(root, plan, state, "active_visual_qa_complete")
    return {"status": "active_visual_qa_complete", "activeVisualQa": dict(result), "reportPath": to_portable_path(chunk_report_path(root, str(plan["chunkId"])))}


def finalize_bounded_chunk(
    *,
    root: Path | str | None = None,
    audit_func: Callable[..., Mapping[str, Any]] = audit_distribution,
) -> dict[str, Any]:
    plan = read_current_plan(root)
    state = read_current_state(root)
    if not state.get("activeVisualQaComplete"):
        raise BoundedBatchExecutorError("Bounded chunk cannot finalize without active visual QA.")
    audit = audit_func(root=root)
    state["distributionAuditComplete"] = True
    _transition_chunk(root, plan, state, "distribution_audit_complete")
    state = read_current_state(root)
    _transition_chunk(root, plan, state, "finalized")
    report = _base_report(root, read_current_plan(root), read_current_state(root))
    report["distributionAuditSummary"] = {
        "passed": bool(audit.get("passed")),
        "finalDecision": audit.get("finalDecision"),
        "approvedCompleteIdentityCount": audit.get("approvedCompleteIdentityCount"),
        "approvedImageCount": audit.get("approvedImageCount"),
    }
    _write_json(chunk_report_path(root, str(plan["chunkId"])), report)
    return {"status": "finalized", "chunkId": plan["chunkId"], "reportPath": to_portable_path(chunk_report_path(root, str(plan["chunkId"]))), "distributionAudit": report["distributionAuditSummary"]}


def bounded_chunk_status(*, root: Path | str | None = None) -> dict[str, Any]:
    paths = pipeline_paths(root)
    plan_exists = current_plan_path(root).exists()
    state_exists = current_state_path(root).exists()
    validation = validate_current_chunk_plan(root=root, strict=False)
    result = {
        "schemaVersion": "seolleyeon_bounded_chunk_status_v3",
        "isPlanPresent": plan_exists,
        "planExists": plan_exists,
        "stateExists": state_exists,
        "planPath": to_portable_path(current_plan_path(root)),
        "statePath": to_portable_path(current_state_path(root)),
        "manualReviewRequired": (paths.manifests / "manual_review_required.flag").exists(),
        "manualReviewReason": _manual_review_reason(root),
        "isDryRun": False,
        "isExecutable": False,
        "isStale": False,
        "staleReasons": [],
        "abandonable": _current_chunk_abandonable(root),
        **_abandoned_chunk_summary(root),
        "canRun": bool(validation.get("canRun")),
        "reasonCode": validation.get("reasonCode", ""),
        "reasons": list(validation.get("reasons") or []),
        "validation": validation,
        "updatedAt": now_utc(),
    }
    if plan_exists:
        plan = read_current_plan(root)
        stale_reasons = [reason for reason in validation.get("reasons", []) if reason.startswith("input_") or reason in {"selected_identity_already_approved", "manual_review_required_newer_than_plan"}]
        result.update(
            {
                "chunkId": plan.get("chunkId"),
                "planMode": plan.get("planMode"),
                "isDryRun": bool(plan.get("dryRun")) or str(plan.get("planMode") or "") == "dry_run",
                "isExecutable": bool(plan.get("executable")),
                "isStale": bool(stale_reasons),
                "staleReasons": stale_reasons,
                "selectedIdentityCount": plan.get("selectedIdentityCount"),
                "selectedAssetCount": plan.get("selectedAssetCount"),
            }
        )
    if state_exists:
        state = read_current_state(root)
        result.update(
            {
                "status": state.get("status"),
                "currentAssetId": state.get("currentAssetId", ""),
                "activeVisualQaComplete": bool(state.get("activeVisualQaComplete")),
                "distributionAuditComplete": bool(state.get("distributionAuditComplete")),
                "assetStates": state.get("assetStates", {}),
                "identityStates": state.get("identityStates", {}),
            }
        )
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Deterministic bounded Seolleyeon Codex internal Image Gen chunk executor.")
    parser.add_argument("command", choices=["plan", "run", "resume", "status", "validate-plan", "reconcile", "reset", "qa", "finalize"])
    parser.add_argument("--root", default=None)
    parser.add_argument("--max_identities", type=int, default=MAX_CHUNK_IDENTITIES)
    parser.add_argument("--max_assets", type=int, default=MAX_CHUNK_ASSETS)
    parser.add_argument("--refresh_audit", action="store_true")
    parser.add_argument("--dry-run", "--dry_run", dest="dry_run", action="store_true")
    parser.add_argument("--production", "--no-dry-run", "--execute", dest="production", action="store_true")
    parser.add_argument("--force-replan", "--force_replan", dest="force_replan", action="store_true")
    parser.add_argument("--abandon-current", "--abandon_current", dest="abandon_current", action="store_true")
    parser.add_argument("--face_type", "--face-type", dest="face_type", default="")
    parser.add_argument("--looks_level_band", "--looks-level-band", dest="looks_level_band", default="")
    parser.add_argument("--gender", dest="gender", default="")
    parser.add_argument("--has_eyewear", "--has-eyewear", dest="has_eyewear", default="")
    parser.add_argument("--eyewear_group", "--eyewear-group", dest="eyewear_group", default="")
    parser.add_argument("--require-eyewear-mix", "--require_eyewear_mix", dest="require_eyewear_mix", action="store_true", default=False)
    parser.add_argument("--require-focused-match", "--require_focused_match", "--strict-focus", dest="require_focused_match", action="store_true")
    parser.add_argument("--reason", default="fresh_production_replan_after_distribution_audit")
    parser.add_argument("--apply", dest="apply", action="store_true")
    parser.add_argument("--quarantine-extra", "--quarantine_extra", dest="quarantine_extra", action="store_true")
    parser.add_argument("--clear-manual-flag-if-safe", "--clear_manual_flag_if_safe", dest="clear_manual_flag_if_safe", action="store_true")
    parser.add_argument("--archive-current", "--archive_current", dest="archive_current", action="store_true")
    parser.add_argument("--force", dest="force", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "plan":
            result = create_chunk_plan(
                root=args.root,
                max_identities=args.max_identities,
                max_assets=args.max_assets,
                refresh_audit=args.refresh_audit,
                dry_run=args.dry_run,
                production=args.production,
                force_replan=args.force_replan,
                abandon_current=args.abandon_current,
                abandon_reason=args.reason,
                face_type=args.face_type,
                looks_level_band=args.looks_level_band,
                gender=args.gender,
                has_eyewear=args.has_eyewear,
                eyewear_group=args.eyewear_group,
                require_eyewear_mix=args.require_eyewear_mix,
                require_focused_match=args.require_focused_match,
            )
        elif args.command == "run":
            result = run_bounded_chunk(root=args.root)
        elif args.command == "resume":
            result = resume_bounded_chunk(root=args.root)
        elif args.command == "status":
            result = bounded_chunk_status(root=args.root)
        elif args.command == "validate-plan":
            result = validate_current_chunk_plan(root=args.root, strict=False)
        elif args.command == "reconcile":
            result = reconcile_bounded_chunk(
                root=args.root,
                dry_run=args.dry_run or not args.apply,
                apply=args.apply,
                clear_manual_flag_if_safe=args.clear_manual_flag_if_safe,
                quarantine_extra=getattr(args, "quarantine_extra", False),
            )
        elif args.command == "reset":
            result = bounded_chunk_reset(
                root=args.root,
                archive_current=args.archive_current,
                dry_run=args.dry_run,
                clear_manual_flag_if_safe=args.clear_manual_flag_if_safe,
                quarantine_extra=getattr(args, "quarantine_extra", False),
                force=args.force,
            )
        elif args.command == "qa":
            result = run_bounded_chunk_qa(root=args.root)
        else:
            result = finalize_bounded_chunk(root=args.root)
    except PlanValidationError as exc:
        result = {"status": "failed", "reasonCode": exc.reason_code, "error": str(exc), **dict(exc.details)}
    except BoundedBatchExecutorError as exc:
        result = {"status": "failed", "reasonCode": "bounded_executor_error", "error": str(exc)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("valid") is False:
        return 2
    return 0 if str(result.get("status") or "") not in {"failed", "needs_manual_review"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
