from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from .codex_imagegen import (
    CODEX_GENERATED_IMAGES_DIR_ENV,
    DEFAULT_CODEX_GENERATED_IMAGES_DIR,
    GENERATED_IMAGE_TIMESTAMP_GRACE_SECONDS,
    completed_pending_path,
    latest_generated_image,
    pending_path,
    read_pending,
    write_pending,
)
from .config import now_utc, pipeline_paths, read_jsonl, to_portable_path, write_jsonl
from .manifest import load_generation_manifest, write_generation_outputs
from .pending_state import (
    pending_is_resolved,
    pending_is_unresolved,
    pending_requires_recovery,
    pending_status,
    pending_unresolved_reason,
)


PENDING_RESOLUTION_FILENAME = "pending_resolution_manifest.jsonl"
CANCELLED_PENDING_PREFIX = "cancelled"
FINALIZE_FAILED_RECOVERY_STATUS = "not_recoverable"


def pending_resolution_path(root: Path | str | None = None) -> Path:
    return pipeline_paths(root).manifests / PENDING_RESOLUTION_FILENAME


def _safe_path(value: Any) -> Path | None:
    if not value:
        return None
    try:
        return Path(str(value)).resolve()
    except OSError:
        return None


def _path_report(value: Any, *, pending_created_at: Any = None) -> dict[str, Any]:
    path = _safe_path(value)
    if path is None:
        return {"path": str(value or ""), "exists": False, "size": 0, "newEnoughForPending": False, "staleForPending": False}
    try:
        exists = path.exists()
        new_enough = _file_new_enough_for_pending(path, pending_created_at) if pending_created_at else False
        return {
            "path": to_portable_path(path),
            "exists": exists,
            "size": path.stat().st_size if exists else 0,
            "newEnoughForPending": bool(new_enough),
            "staleForPending": bool(exists and pending_created_at and not new_enough),
        }
    except OSError:
        return {"path": to_portable_path(path), "exists": False, "size": 0, "newEnoughForPending": False, "staleForPending": False}


def pending_status_report(*, root: Path | str | None = None, pending: Path | str | None = None) -> dict[str, Any]:
    pending_file = Path(pending).resolve() if pending else pending_path(root)
    per_asset_summary: dict[str, Any] = {}
    if pending is None:
        from .identity_parallel import identity_parallel_status

        per_asset_summary = identity_parallel_status(root=root)
    payload = read_pending(pending_file)
    if not payload:
        return {
            "exists": pending_file.exists(),
            "pendingPath": to_portable_path(pending_file),
            "status": "",
            "resolved": True,
            "unresolved": False,
            "requiresRecovery": False,
            "reason": "",
            "assetId": "",
            "expectedRawPath": _path_report(""),
            "expectedFinalPath": _path_report(""),
            "perAssetPending": per_asset_summary,
        }
    return {
        "exists": True,
        "pendingPath": to_portable_path(pending_file),
        "status": pending_status(payload),
        "resolved": pending_is_resolved(payload),
        "unresolved": pending_is_unresolved(payload),
        "requiresRecovery": pending_requires_recovery(payload),
        "reason": pending_unresolved_reason(payload) if pending_is_unresolved(payload) else str(payload.get("reason") or ""),
        "assetId": str(payload.get("assetId") or ""),
        "profileId": str(payload.get("profileId") or ""),
        "shotType": str(payload.get("shotType") or ""),
        "attempt": int(payload.get("attempt") or 0),
        "expectedRawPath": _path_report(payload.get("expectedRawPath"), pending_created_at=payload.get("createdAt")),
        "expectedFinalPath": _path_report(payload.get("expectedFinalPath"), pending_created_at=payload.get("createdAt")),
        "perAssetPending": per_asset_summary,
    }


def _append_resolution(root: Path | str | None, row: Mapping[str, Any]) -> None:
    path = pending_resolution_path(root)
    rows = read_jsonl(path)
    rows.append(dict(row))
    write_jsonl(path, rows)


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def _write_json_object(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(dict(payload), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _append_jsonl(path: Path, row: Mapping[str, Any]) -> None:
    rows = read_jsonl(path)
    rows.append(dict(row))
    write_jsonl(path, rows)


def _parse_timestamp(value: Any) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _file_new_enough_for_pending(path_value: Any, created_at: Any) -> bool:
    path = _safe_path(path_value)
    created_ts = _parse_timestamp(created_at)
    if path is None or created_ts is None or not path.exists():
        return False
    try:
        return path.stat().st_mtime >= created_ts - GENERATED_IMAGE_TIMESTAMP_GRACE_SECONDS
    except OSError:
        return False


def _find_planned_asset(plan: Mapping[str, Any], asset_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    for identity in plan.get("identities", []) or []:
        if not isinstance(identity, dict):
            continue
        for asset in identity.get("assets", []) or []:
            if isinstance(asset, dict) and str(asset.get("assetId") or "") == asset_id:
                return identity, asset
    raise RuntimeError(f"Pending assetId is not in current chunk plan: {asset_id}")


def _validate_pending_against_plan(payload: Mapping[str, Any], plan: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    asset_id = str(payload.get("assetId") or "")
    identity, asset = _find_planned_asset(plan, asset_id)
    checks = {
        "chunkId": str(plan.get("chunkId") or "") == str(payload.get("chunkId") or ""),
        "profileId": str(identity.get("profileId") or "") == str(payload.get("profileId") or ""),
        "shotType": str(asset.get("shotType") or "") == str(payload.get("shotType") or ""),
    }
    final_value = str(payload.get("expectedFinalPath") or payload.get("finalPath") or "")
    planned_final_value = str(asset.get("finalPath") or "")
    if final_value and planned_final_value:
        try:
            checks["expectedFinalPath"] = Path(final_value).resolve() == Path(planned_final_value).resolve()
        except OSError:
            checks["expectedFinalPath"] = False
    if not all(checks.values()):
        failed = ", ".join(key for key, ok in checks.items() if not ok)
        raise RuntimeError(f"Pending checkpoint does not match current chunk plan: {failed}")
    return identity, asset


def _ensure_no_recoverable_source(payload: Mapping[str, Any]) -> dict[str, Any]:
    created_at = payload.get("createdAt")
    generated_dir = Path(
        str(
            payload.get("codexGeneratedImagesDir")
            or os.environ.get(CODEX_GENERATED_IMAGES_DIR_ENV)
            or DEFAULT_CODEX_GENERATED_IMAGES_DIR
        )
    ).resolve()
    expected_raw_new = _file_new_enough_for_pending(payload.get("expectedRawPath"), created_at)
    expected_final_new = _file_new_enough_for_pending(payload.get("expectedFinalPath"), created_at)
    if expected_raw_new or expected_final_new:
        raise RuntimeError("Expected raw/final path has a post-checkpoint file; run recover instead of finalizing failed.")
    try:
        candidate = latest_generated_image(generated_dir, created_at=str(created_at or ""))
    except FileNotFoundError as exc:
        return {
            "generatedImagesDir": to_portable_path(generated_dir),
            "sourceFound": False,
            "sourcePath": None,
            "notRecoverableReason": str(exc),
            "expectedRawPath": _path_report(payload.get("expectedRawPath")),
            "expectedFinalPath": _path_report(payload.get("expectedFinalPath")),
        }
    except RuntimeError as exc:
        raise RuntimeError(f"Generated image recovery candidate is ambiguous: {exc}") from exc
    raise RuntimeError(f"Recoverable generated image exists; run recover first: {candidate}")


def _update_generation_manifest_failed(
    *,
    root: Path | str | None,
    payload: Mapping[str, Any],
    reason: str,
    timestamp: str,
) -> bool:
    paths = pipeline_paths(root)
    rows = load_generation_manifest(paths)
    asset_id = str(payload.get("assetId") or "")
    updated: list[dict[str, Any]] = []
    found = False
    for row in rows:
        out = dict(row)
        if str(out.get("assetId") or "") == asset_id:
            found = True
            out.update(
                {
                    "status": "failed",
                    "attempt": int(payload.get("attempt") or out.get("attempt") or 1),
                    "attemptCount": int(payload.get("attempt") or out.get("attemptCount") or 1),
                    "pendingPath": to_portable_path(pending_path(root)),
                    "recoveryStatus": FINALIZE_FAILED_RECOVERY_STATUS,
                    "pendingFinalizedAt": timestamp,
                    "updatedAt": timestamp,
                    "error": reason,
                }
            )
        updated.append(out)
    if not found:
        raise RuntimeError(f"Pending assetId was not found in generation manifest: {asset_id}")
    write_generation_outputs(paths, updated)
    return True


def _update_current_chunk_failed(
    *,
    root: Path | str | None,
    payload: Mapping[str, Any],
    reason: str,
    timestamp: str,
) -> dict[str, Any]:
    paths = pipeline_paths(root)
    plan_path = paths.manifests / "current_chunk_plan.json"
    state_path = paths.manifests / "current_chunk_state.json"
    plan = _read_json_object(plan_path)
    state = _read_json_object(state_path)
    identity, asset = _validate_pending_against_plan(payload, plan)
    asset_id = str(payload.get("assetId") or "")
    profile_id = str(payload.get("profileId") or "")
    shot_type = str(payload.get("shotType") or "")
    before = {
        "planStatus": str(plan.get("status") or ""),
        "stateStatus": str(state.get("status") or ""),
        "assetStatus": str(asset.get("status") or ""),
        "identityStatus": str(identity.get("status") or ""),
    }
    asset.update({"status": "failed", "attempt": int(payload.get("attempt") or asset.get("attempt") or 1), "error": reason})
    identity["status"] = "failed"
    plan["status"] = "needs_manual_review"
    plan["updatedAt"] = timestamp
    asset_states = state.setdefault("assetStates", {})
    identity_states = state.setdefault("identityStates", {})
    if isinstance(asset_states, dict):
        asset_states[asset_id] = "failed"
    if isinstance(identity_states, dict):
        identity_states[profile_id] = "failed"
    failed_asset_ids = state.setdefault("failedAssetIds", [])
    if isinstance(failed_asset_ids, list) and asset_id not in failed_asset_ids:
        failed_asset_ids.append(asset_id)
    if str(state.get("currentAssetId") or "") == asset_id:
        state["currentAssetId"] = ""
    state["status"] = "needs_manual_review"
    state["updatedAt"] = timestamp
    state["pendingFinalization"] = {
        "assetId": asset_id,
        "profileId": profile_id,
        "shotType": shot_type,
        "status": "failed",
        "reason": reason,
        "finalizedAt": timestamp,
    }
    _write_json_object(plan_path, plan)
    _write_json_object(state_path, state)
    event_path = paths.reports / "chunks" / str(payload.get("chunkId") or "") / "events.jsonl"
    _append_jsonl(
        event_path,
        {
            "timestamp": timestamp,
            "chunkId": str(payload.get("chunkId") or ""),
            "eventType": "pending_finalized_failed",
            "profileId": profile_id,
            "assetId": asset_id,
            "shotType": shot_type,
            "fromStatus": before["assetStatus"],
            "toStatus": "failed",
            "reason": reason,
            "command": ["finalize-pending"],
            "returnCode": 0,
            "outputPath": to_portable_path(pending_path(root)),
        },
    )
    return {
        "before": before,
        "after": {
            "planStatus": "needs_manual_review",
            "stateStatus": "needs_manual_review",
            "assetStatus": "failed",
            "identityStatus": "failed",
        },
        "eventsPath": to_portable_path(event_path),
    }


def _resolve_pending(
    *,
    root: Path | str | None,
    pending: Path | str | None,
    reason: str,
    action: str,
    require_cancelled: bool,
) -> dict[str, Any]:
    pending_file = Path(pending).resolve() if pending else pending_path(root)
    payload = read_pending(pending_file)
    if not payload:
        raise FileNotFoundError(f"No pending-imagegen checkpoint found: {pending_file}")
    if pending_is_resolved(payload):
        report = pending_status_report(root=root, pending=pending_file)
        report["action"] = "already_resolved"
        return report
    if pending_requires_recovery(payload):
        raise RuntimeError(
            "Active pending imagegen checkpoints must be recovered, not manually cleared. "
            f"Run recover first for assetId={payload.get('assetId') or ''}."
        )
    status = pending_status(payload)
    if require_cancelled and not status.startswith(CANCELLED_PENDING_PREFIX):
        raise RuntimeError(f"Refusing to clear non-cancelled pending checkpoint with status={status!r}.")

    before = pending_status_report(root=root, pending=pending_file)
    resolved = dict(payload)
    resolved.update(
        {
            "status": "cleared" if require_cancelled else "resolved",
            "resolved": True,
            "resolvedAt": now_utc(),
            "resolveReason": reason,
            "resolutionMode": action,
        }
    )
    write_pending(pending_file, resolved)
    after = pending_status_report(root=root, pending=pending_file)
    _append_resolution(
        root,
        {
            "assetId": str(payload.get("assetId") or ""),
            "profileId": str(payload.get("profileId") or ""),
            "shotType": str(payload.get("shotType") or ""),
            "attempt": int(payload.get("attempt") or 0),
            "beforeStatus": before["status"],
            "afterStatus": after["status"],
            "reason": reason,
            "action": action,
            "expectedRawExists": bool(before["expectedRawPath"]["exists"]),
            "expectedFinalExists": bool(before["expectedFinalPath"]["exists"]),
            "resolvedAt": resolved["resolvedAt"],
        },
    )
    after["action"] = action
    return after


def resolve_pending(
    *,
    root: Path | str | None = None,
    pending: Path | str | None = None,
    reason: str = "manual_resolution",
) -> dict[str, Any]:
    return _resolve_pending(root=root, pending=pending, reason=reason, action="manual_resolve", require_cancelled=False)


def clear_cancelled_pending(
    *,
    root: Path | str | None = None,
    pending: Path | str | None = None,
    reason: str = "cancelled_pending_clear",
) -> dict[str, Any]:
    return _resolve_pending(root=root, pending=pending, reason=reason, action="clear_cancelled", require_cancelled=True)


def finalize_pending_failed(
    *,
    root: Path | str | None = None,
    pending: Path | str | None = None,
    asset_id: str = "",
    reason: str = "pending_image_not_recoverable",
) -> dict[str, Any]:
    pending_file = Path(pending).resolve() if pending else pending_path(root)
    payload = read_pending(pending_file)
    if not payload:
        raise FileNotFoundError(f"No pending-imagegen checkpoint found: {pending_file}")
    if pending_is_resolved(payload):
        report = pending_status_report(root=root, pending=pending_file)
        report["action"] = "already_resolved"
        return report
    pending_asset_id = str(payload.get("assetId") or "")
    if asset_id and pending_asset_id != asset_id:
        raise RuntimeError(f"Refusing to finalize pending assetId={pending_asset_id}; requested assetId={asset_id}")
    if not pending_requires_recovery(payload):
        raise RuntimeError(f"Refusing to finalize pending checkpoint with non-active status={pending_status(payload)!r}.")

    plan = _read_json_object(pipeline_paths(root).manifests / "current_chunk_plan.json")
    _validate_pending_against_plan(payload, plan)
    before = pending_status_report(root=root, pending=pending_file)
    recovery_probe = _ensure_no_recoverable_source(payload)
    timestamp = now_utc()
    generation_manifest_updated = _update_generation_manifest_failed(root=root, payload=payload, reason=reason, timestamp=timestamp)
    chunk_update = _update_current_chunk_failed(root=root, payload=payload, reason=reason, timestamp=timestamp)
    finalized = dict(payload)
    finalized.update(
        {
            "status": "failed",
            "resolved": True,
            "resolvedAt": timestamp,
            "failedAt": timestamp,
            "resolveReason": reason,
            "resolutionMode": "finalize_failed",
            "recoveryStatus": FINALIZE_FAILED_RECOVERY_STATUS,
            "error": reason,
            "sourcePath": None,
            "rawPath": None,
            "finalPath": None,
        }
    )
    write_pending(pending_file, finalized)
    _append_resolution(
        root,
        {
            "assetId": pending_asset_id,
            "profileId": str(payload.get("profileId") or ""),
            "shotType": str(payload.get("shotType") or ""),
            "attempt": int(payload.get("attempt") or 0),
            "beforeStatus": before["status"],
            "afterStatus": "failed",
            "reason": reason,
            "action": "finalize_failed",
            "recoveryStatus": FINALIZE_FAILED_RECOVERY_STATUS,
            "expectedRawExists": bool(before["expectedRawPath"]["exists"]),
            "expectedFinalExists": bool(before["expectedFinalPath"]["exists"]),
            "resolvedAt": timestamp,
        },
    )
    _append_jsonl(completed_pending_path(root), finalized)
    after = pending_status_report(root=root, pending=pending_file)
    return {
        **after,
        "action": "finalize_failed",
        "recoveryStatus": FINALIZE_FAILED_RECOVERY_STATUS,
        "reason": reason,
        "recoveryProbe": recovery_probe,
        "generationManifestUpdated": generation_manifest_updated,
        "currentChunkStateUpdated": True,
        "currentChunkUpdate": chunk_update,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect or manually resolve safe pending-imagegen checkpoint states.")
    parser.add_argument("command", choices=["status", "resolve", "clear-cancelled", "finalize-failed"])
    parser.add_argument("--root", default=None)
    parser.add_argument("--pending", default=None)
    parser.add_argument("--asset-id", "--asset_id", "--assetId", dest="asset_id", default="")
    parser.add_argument("--failed", action="store_true", default=False)
    parser.add_argument("--reason", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "status":
        result = pending_status_report(root=args.root, pending=args.pending)
    elif args.command == "resolve":
        result = resolve_pending(root=args.root, pending=args.pending, reason=args.reason or "manual_resolution")
    elif args.command == "clear-cancelled":
        result = clear_cancelled_pending(root=args.root, pending=args.pending, reason=args.reason or "cancelled_pending_clear")
    elif args.command == "finalize-failed":
        if not args.failed:
            raise SystemExit("finalize-failed requires --failed")
        result = finalize_pending_failed(root=args.root, pending=args.pending, asset_id=args.asset_id, reason=args.reason or "pending_image_not_recoverable")
    else:
        raise AssertionError(f"Unhandled command: {args.command}")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
