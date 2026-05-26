from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .codex_imagegen import pending_path, read_pending
from .completion import completion_check
from .config import ensure_base_dirs, now_utc, pipeline_paths, to_portable_path
from .distribution_audit import audit_distribution
from .pending_state import pending_is_unresolved


MANUAL_REVIEW_CLEAR_SCHEMA_VERSION = "seolleyeon_manual_review_clear_v3"
TRANSIENT_CODEX_QA_FAILURE_REASON = "asset_qa_codex_subprocess_failed"
TRANSIENT_CODEX_QA_CLEAR_REASON = "transient_codex_active_visual_qa_subprocess_failed_ready_for_retry"
EXPECTED_PRE_CLEAR_FAILURES = {"manual_review_required", "distribution_mismatch"}
EXPECTED_POST_CLEAR_FAILURES = {"distribution_mismatch"}
TRANSIENT_CODEX_QA_EXPECTED_PRE_CLEAR_FAILURES = {
    "manual_review_required",
    "active_visual_qa_incomplete",
    "distribution_audit_incomplete",
    "distribution_mismatch",
}
TRANSIENT_CODEX_QA_EXPECTED_POST_CLEAR_FAILURES = {
    "active_visual_qa_incomplete",
    "distribution_audit_incomplete",
    "distribution_mismatch",
}


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _read_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def _latest_reset_report(root: Path | str | None) -> Path | None:
    reports_root = pipeline_paths(root).reports / "chunks"
    if not reports_root.exists():
        return None
    candidates = [path for path in reports_root.glob("*/reset_report.json") if path.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _reset_report_ok(path: Path | None) -> tuple[bool, dict[str, Any], list[str]]:
    if path is None or not path.exists():
        return False, {}, ["reset_report_missing"]
    try:
        report = _read_json_object(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return False, {}, [f"reset_report_unreadable:{exc}"]
    required = {
        "generatedFilesPreserved": True,
        "approvedCountChanged": False,
        "distributionCountChanged": False,
        "manualFlagCleared": False,
        "extraAssetsAction": "left_in_place",
    }
    reasons: list[str] = []
    for key, expected in required.items():
        if report.get(key) != expected:
            reasons.append(f"reset_report_{key}_not_{expected}")
    return not reasons, report, reasons


def _archive_manual_flag(flag_path: Path, root: Path | str | None) -> Path:
    archive_dir = pipeline_paths(root).manifests / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    destination = archive_dir / f"manual_review_required_{_stamp()}.flag"
    if destination.exists():
        destination = archive_dir / f"manual_review_required_{_stamp()}_{flag_path.stat().st_mtime_ns}.flag"
    shutil.copy2(flag_path, destination)
    return destination


def _write_reports(root: Path | str | None, report: Mapping[str, Any]) -> None:
    report_dir = pipeline_paths(root).reports / "pipeline_audit"
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / "manual_review_clear_latest.json"
    md_path = report_dir / "manual_review_clear_latest.md"
    json_path.write_text(json.dumps(dict(report), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Manual Review Clear",
        "",
        f"- result: {report.get('result')}",
        f"- cleared: {report.get('cleared')}",
        f"- reason: {report.get('reason')}",
        f"- archivePath: {report.get('archivePath') or ''}",
        f"- readinessPassed: {report.get('readiness', {}).get('passed') if isinstance(report.get('readiness'), Mapping) else ''}",
        f"- postClearFailureReasons: {', '.join(report.get('postClearCompletion', {}).get('failureReasons', [])) if isinstance(report.get('postClearCompletion'), Mapping) else ''}",
    ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _active_finalized_chunk_clearance(paths) -> tuple[bool, dict[str, Any], list[str]]:
    plan_path = paths.manifests / "current_chunk_plan.json"
    state_path = paths.manifests / "current_chunk_state.json"
    result: dict[str, Any] = {
        "planExists": plan_path.exists(),
        "stateExists": state_path.exists(),
        "allowed": False,
        "chunkId": "",
        "planStatus": "",
        "stateStatus": "",
    }
    reasons: list[str] = []
    if not plan_path.exists() and not state_path.exists():
        result["allowed"] = True
        return True, result, reasons
    if not plan_path.exists():
        reasons.append("active_current_chunk_state_exists")
        return False, result, reasons
    if not state_path.exists():
        reasons.append("active_current_chunk_plan_exists")
        return False, result, reasons
    try:
        plan = _read_json_object(plan_path)
        state = _read_json_object(state_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        reasons.append(f"active_current_chunk_unreadable:{exc}")
        return False, result, reasons
    plan_chunk = str(plan.get("chunkId") or "")
    state_chunk = str(state.get("chunkId") or "")
    plan_status = str(plan.get("status") or "")
    state_status = str(state.get("status") or "")
    result.update(
        {
            "chunkId": plan_chunk or state_chunk,
            "planStatus": plan_status,
            "stateStatus": state_status,
            "activeVisualQaComplete": bool(state.get("activeVisualQaComplete")),
            "distributionAuditComplete": bool(state.get("distributionAuditComplete")),
        }
    )
    if plan_chunk and state_chunk and plan_chunk != state_chunk:
        reasons.append("active_current_chunk_plan_state_mismatch")
    if plan_status != "finalized" or state_status != "finalized":
        reasons.append("active_current_chunk_not_finalized")
    if not state.get("activeVisualQaComplete"):
        reasons.append("active_current_chunk_visual_qa_incomplete")
    if not state.get("distributionAuditComplete"):
        reasons.append("active_current_chunk_distribution_audit_incomplete")
    result["allowed"] = not reasons
    return not reasons, result, reasons


def _manual_flag_payload(flag_path: Path) -> dict[str, Any]:
    if not flag_path.exists():
        return {}
    try:
        return _read_json_object(flag_path)
    except (OSError, ValueError, json.JSONDecodeError):
        return {}


def _active_pipeline_processes() -> list[dict[str, Any]]:
    """Best-effort live-process gate for generation/active visual QA children.

    Deliberately excludes this clear-manual-review process and generic status commands;
    the gate is intended to block competing imagegen/one-asset/active QA workers.
    """
    patterns = [
        "hermes-one-asset-loop",
        "active-visual-qa-all",
        "active-visual-asset-qa",
        "active-visual-identity-qa",
        "active-visual-distribution-qa",
        "bounded-chunk-run",
        "bounded-chunk-resume",
        "supervisor-720",
        "codex.exe exec",
        "$imagegen",
        "imagegen",
    ]
    current_pid = os.getpid()
    try:
        if os.name == "nt":
            query: str | list[str] = "wmic process get ProcessId,ParentProcessId,CommandLine /format:csv"
            raw = subprocess.check_output(query, shell=True, stderr=subprocess.DEVNULL, timeout=10)
        else:
            query = ["ps", "-eo", "pid=,ppid=,args="]
            raw = subprocess.check_output(query, stderr=subprocess.DEVNULL, timeout=10)
    except Exception:
        return []
    if isinstance(raw, bytes):
        output = raw.decode("utf-8", errors="replace")
    else:
        output = str(raw or "")
    rows: list[dict[str, Any]] = []
    for line in output.splitlines():
        lowered = line.lower()
        if not any(pattern.lower() in lowered for pattern in patterns):
            continue
        if "clear-manual-review" in lowered:
            continue
        if "wmic process" in lowered or "ps -eo" in lowered:
            continue
        pid = None
        if os.name == "nt":
            parts = line.rsplit(",", 2)
            if len(parts) == 3:
                try:
                    pid = int(parts[-1].strip())
                except ValueError:
                    pid = None
        else:
            fields = line.strip().split(None, 2)
            if fields:
                try:
                    pid = int(fields[0])
                except ValueError:
                    pid = None
        if pid == current_pid:
            continue
        rows.append({"pid": pid, "commandLine": line[:1000]})
    return rows


def _asset_ids_from_whitelist(payload: Mapping[str, Any]) -> set[str]:
    asset_ids = payload.get("assetIds")
    if isinstance(asset_ids, list):
        return {str(item) for item in asset_ids if str(item)}
    found: set[str] = set()
    profiles = payload.get("profiles")
    if isinstance(profiles, list):
        for profile in profiles:
            if not isinstance(profile, Mapping):
                continue
            assets = profile.get("assets")
            if isinstance(assets, Mapping):
                values = assets.values()
            elif isinstance(assets, list):
                values = assets
            else:
                values = []
            for asset in values:
                if isinstance(asset, Mapping) and asset.get("assetId"):
                    found.add(str(asset["assetId"]))
    return found


def _validate_transient_codex_qa_scope(paths, chunk_id: str, selected_assets: set[str]) -> tuple[bool, dict[str, Any], list[str]]:
    chunk_dir = paths.reports / "chunks" / chunk_id
    whitelist_path = chunk_dir / "file_complete_identity_whitelist.json"
    contact_sheet_index_path = chunk_dir / "contact_sheets" / "file_complete_contact_sheet_index.json"
    result: dict[str, Any] = {
        "chunkId": chunk_id,
        "whitelistPath": to_portable_path(whitelist_path),
        "contactSheetIndexPath": to_portable_path(contact_sheet_index_path),
        "whitelistExists": whitelist_path.exists(),
        "contactSheetIndexExists": contact_sheet_index_path.exists(),
        "assetCount": 0,
        "sheetCount": 0,
        "outOfScopeRows": 0,
    }
    reasons: list[str] = []
    if not whitelist_path.exists():
        reasons.append("transient_codex_qa_whitelist_missing")
    if not contact_sheet_index_path.exists():
        reasons.append("transient_codex_qa_contact_sheet_index_missing")
    if reasons:
        return False, result, reasons
    try:
        whitelist = _read_json_object(whitelist_path)
        index = _read_json_object(contact_sheet_index_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return False, result, [f"transient_codex_qa_scope_unreadable:{exc}"]
    whitelist_chunk = str(whitelist.get("chunkId") or "")
    index_chunk = str(index.get("chunkId") or "")
    if whitelist_chunk != chunk_id:
        reasons.append("transient_codex_qa_whitelist_chunk_mismatch")
    if index_chunk != chunk_id:
        reasons.append("transient_codex_qa_contact_sheet_chunk_mismatch")
    whitelist_asset_ids = _asset_ids_from_whitelist(whitelist)
    result["assetCount"] = len(whitelist_asset_ids)
    if not whitelist_asset_ids:
        reasons.append("transient_codex_qa_whitelist_empty")
    if selected_assets and whitelist_asset_ids != selected_assets:
        reasons.append("transient_codex_qa_whitelist_asset_mismatch")
    sheets = index.get("sheets")
    if not isinstance(sheets, list) or not sheets:
        reasons.append("transient_codex_qa_contact_sheet_index_empty")
        sheets = []
    sheet_asset_ids: set[str] = set()
    out_of_scope_rows = 0
    for sheet in sheets:
        if not isinstance(sheet, Mapping):
            continue
        for asset_id in sheet.get("assetIds") or []:
            if str(asset_id):
                sheet_asset_ids.add(str(asset_id))
        out_of_scope = sheet.get("outOfScopeAssetIds") or []
        if isinstance(out_of_scope, list):
            out_of_scope_rows += len(out_of_scope)
    result["sheetCount"] = len(sheets)
    result["outOfScopeRows"] = out_of_scope_rows
    if out_of_scope_rows:
        reasons.append("transient_codex_qa_contact_sheet_out_of_scope_rows")
    if selected_assets and not sheet_asset_ids.issubset(selected_assets):
        reasons.append("transient_codex_qa_contact_sheet_asset_mismatch")
    if whitelist_asset_ids and not sheet_asset_ids:
        reasons.append("transient_codex_qa_contact_sheet_assets_empty")
    return not reasons, result, reasons


def _transient_codex_qa_clearance(
    paths,
    *,
    reason: str,
    flag_payload: Mapping[str, Any],
    pre_completion: Mapping[str, Any],
) -> tuple[bool, dict[str, Any], list[str]]:
    result: dict[str, Any] = {"allowed": False, "clearReason": TRANSIENT_CODEX_QA_CLEAR_REASON}
    reasons: list[str] = []
    if reason != TRANSIENT_CODEX_QA_FAILURE_REASON:
        reasons.append("transient_codex_qa_reason_not_requested")
    if str(flag_payload.get("reason") or "") != TRANSIENT_CODEX_QA_FAILURE_REASON:
        reasons.append(f"transient_codex_qa_flag_reason_mismatch:{flag_payload.get('reason') or ''}")
    pending_payload = read_pending(pending_path(paths.root))
    if pending_payload and pending_is_unresolved(pending_payload):
        reasons.append("unresolved_pending_imagegen")
    active_processes = _active_pipeline_processes()
    result["activeProcesses"] = active_processes
    if active_processes:
        reasons.append("active_generation_or_visual_qa_process")
    plan_path = paths.manifests / "current_chunk_plan.json"
    state_path = paths.manifests / "current_chunk_state.json"
    if not plan_path.exists() or not state_path.exists():
        reasons.append("transient_codex_qa_current_chunk_missing")
        result["allowed"] = False
        return False, result, reasons
    try:
        plan = _read_json_object(plan_path)
        state = _read_json_object(state_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        reasons.append(f"transient_codex_qa_current_chunk_unreadable:{exc}")
        result["allowed"] = False
        return False, result, reasons
    chunk_id = str(plan.get("chunkId") or state.get("chunkId") or "")
    selected_assets: set[str] = set()
    for identity in plan.get("identities") or []:
        if not isinstance(identity, Mapping):
            continue
        for asset in identity.get("assets") or []:
            if isinstance(asset, Mapping) and asset.get("assetId"):
                selected_assets.add(str(asset["assetId"]))
    if not selected_assets:
        selected_assets = {str(key) for key in (state.get("assetStates") or {}).keys() if str(key)}
    asset_states = state.get("assetStates") if isinstance(state.get("assetStates"), Mapping) else {}
    file_qa_passed = sum(1 for asset_id in selected_assets if asset_states.get(asset_id) == "file_qa_passed")
    file_qa_failed = sum(1 for asset_id in selected_assets if "failed" in str(asset_states.get(asset_id) or ""))
    existing_final_files = 0
    final_paths: dict[str, str] = {}
    for identity in plan.get("identities") or []:
        if not isinstance(identity, Mapping):
            continue
        for asset in identity.get("assets") or []:
            if isinstance(asset, Mapping) and asset.get("assetId") in selected_assets:
                final = Path(str(asset.get("finalPath") or ""))
                if final.exists():
                    existing_final_files += 1
                final_paths[str(asset.get("assetId"))] = str(final)
    selected_count = len(selected_assets)
    result.update(
        {
            "chunkId": chunk_id,
            "selectedAssetCount": selected_count,
            "fileQaPassedAssets": file_qa_passed,
            "fileQaFailedAssets": file_qa_failed,
            "existingFinalFiles": existing_final_files,
            "activeVisualQaComplete": bool(state.get("activeVisualQaComplete")),
            "distributionAuditComplete": bool(state.get("distributionAuditComplete")),
        }
    )
    if selected_count <= 0:
        reasons.append("transient_codex_qa_selected_asset_count_zero")
    if file_qa_passed != selected_count:
        reasons.append("transient_codex_qa_file_qa_incomplete")
    if file_qa_failed:
        reasons.append("transient_codex_qa_file_qa_failed")
    if existing_final_files != selected_count:
        reasons.append("transient_codex_qa_missing_final_files")
    scope_ok, scope, scope_reasons = _validate_transient_codex_qa_scope(paths, chunk_id, selected_assets)
    result["scope"] = scope
    if not scope_ok:
        reasons.extend(scope_reasons)
    pre_failures = set(str(item) for item in pre_completion.get("failureReasons", []))
    unexpected_pre = sorted(pre_failures - TRANSIENT_CODEX_QA_EXPECTED_PRE_CLEAR_FAILURES)
    if unexpected_pre:
        reasons.extend(f"unexpected_transient_pre_clear_completion_failure:{item}" for item in unexpected_pre)
    result["allowed"] = not reasons
    return not reasons, result, reasons


def clear_manual_review(*, root: Path | str | None = None, reason: str = "") -> dict[str, Any]:
    paths = pipeline_paths(root)
    ensure_base_dirs(paths)
    flag_path = paths.manifests / "manual_review_required.flag"
    flag_payload = _manual_flag_payload(flag_path)
    is_transient_codex_qa_clear = reason == TRANSIENT_CODEX_QA_FAILURE_REASON
    reasons_if_unsafe: list[str] = []
    if not reason:
        reasons_if_unsafe.append("reason_required")
    if not flag_path.exists():
        reasons_if_unsafe.append("manual_review_flag_missing")
    active_chunk_ok, active_chunk, active_chunk_reasons = _active_finalized_chunk_clearance(paths)
    if not active_chunk_ok and not is_transient_codex_qa_clear:
        reasons_if_unsafe.extend(active_chunk_reasons)
    pending_payload = read_pending(pending_path(root))
    if pending_payload and pending_is_unresolved(pending_payload):
        reasons_if_unsafe.append("unresolved_pending_imagegen")

    reset_path = _latest_reset_report(root)
    reset_ok, reset_report, reset_reasons = _reset_report_ok(reset_path)
    if not reset_ok and not active_chunk_ok and not is_transient_codex_qa_clear:
        reasons_if_unsafe.extend(reset_reasons)

    audit = audit_distribution(root=root, write_outputs=False)
    if str(audit.get("finalDecision") or "") != "needs_more_generation":
        reasons_if_unsafe.append("distribution_audit_not_needs_more_generation")

    pre_completion = completion_check(root=root)
    if int(audit.get("approvedCompleteIdentityCount") or 0) != int(pre_completion.get("approvedCompleteIdentities") or 0):
        reasons_if_unsafe.append("approved_identity_count_mismatch")
    if int(audit.get("approvedImageCount") or 0) != int(pre_completion.get("approvedImages") or 0):
        reasons_if_unsafe.append("approved_image_count_mismatch")
    pre_failures = set(str(item) for item in pre_completion.get("failureReasons", []))
    if is_transient_codex_qa_clear:
        unexpected_pre = sorted(pre_failures - TRANSIENT_CODEX_QA_EXPECTED_PRE_CLEAR_FAILURES)
    else:
        unexpected_pre = sorted(pre_failures - EXPECTED_PRE_CLEAR_FAILURES)
    if unexpected_pre:
        reasons_if_unsafe.extend(f"unexpected_pre_clear_completion_failure:{item}" for item in unexpected_pre)
    if pre_completion.get("passed"):
        reasons_if_unsafe.append("completion_unexpectedly_passed_before_clear")

    transient_clearance: dict[str, Any] = {}
    if is_transient_codex_qa_clear and not any(
        reason_item in {"reason_required", "manual_review_flag_missing"} for reason_item in reasons_if_unsafe
    ):
        transient_ok, transient_clearance, transient_reasons = _transient_codex_qa_clearance(
            paths,
            reason=reason,
            flag_payload=flag_payload,
            pre_completion=pre_completion,
        )
        if not transient_ok:
            reasons_if_unsafe.extend(transient_reasons)

    report: dict[str, Any] = {
        "schemaVersion": MANUAL_REVIEW_CLEAR_SCHEMA_VERSION,
        "result": "not_cleared",
        "cleared": False,
        "reason": reason,
        "createdAt": now_utc(),
        "archivePath": None,
        "manualFlagPath": to_portable_path(flag_path),
        "manualFlag": flag_payload,
        "resetReportPath": to_portable_path(reset_path) if reset_path else "",
        "readiness": {
            "passed": not reasons_if_unsafe,
            "reasonsIfUnsafe": reasons_if_unsafe,
            "resetReport": reset_report,
            "activeChunk": active_chunk,
            "transientCodexQaClearance": transient_clearance,
        },
        "preClearCompletion": {
            "passed": bool(pre_completion.get("passed")),
            "failureReasons": list(pre_completion.get("failureReasons") or []),
            "approvedCompleteIdentities": int(pre_completion.get("approvedCompleteIdentities") or 0),
            "approvedImages": int(pre_completion.get("approvedImages") or 0),
        },
        "postClearCompletion": {},
        "distributionAudit": {
            "passed": bool(audit.get("passed")),
            "finalDecision": audit.get("finalDecision"),
            "approvedCompleteIdentityCount": int(audit.get("approvedCompleteIdentityCount") or 0),
            "approvedImageCount": int(audit.get("approvedImageCount") or 0),
        },
    }
    if reasons_if_unsafe:
        _write_reports(root, report)
        return report

    archive_path = _archive_manual_flag(flag_path, root)
    original = flag_path.read_text(encoding="utf-8", errors="replace")
    flag_path.unlink()
    post_completion = completion_check(root=root)
    post_failures = set(str(item) for item in post_completion.get("failureReasons", []))
    if is_transient_codex_qa_clear:
        unexpected_post = sorted(post_failures - TRANSIENT_CODEX_QA_EXPECTED_POST_CLEAR_FAILURES)
    else:
        unexpected_post = sorted(post_failures - EXPECTED_POST_CLEAR_FAILURES)
    pre_approved_identities = int(pre_completion.get("approvedCompleteIdentities") or 0)
    pre_approved_images = int(pre_completion.get("approvedImages") or 0)
    post_approved_identities = int(post_completion.get("approvedCompleteIdentities") or 0)
    post_approved_images = int(post_completion.get("approvedImages") or 0)
    if post_approved_identities < pre_approved_identities:
        unexpected_post.append("approved_identity_count_regressed")
    if post_approved_images < pre_approved_images:
        unexpected_post.append("approved_image_count_regressed")
    if post_completion.get("passed") or unexpected_post:
        flag_path.write_text(original, encoding="utf-8")
        report.update(
            {
                "result": "restored_after_post_clear_check_failed",
                "archivePath": to_portable_path(archive_path),
                "postClearCompletion": {
                    "passed": bool(post_completion.get("passed")),
                    "failureReasons": list(post_completion.get("failureReasons") or []),
                    "unexpectedFailures": unexpected_post,
                    "approvedCompleteIdentities": post_approved_identities,
                    "approvedImages": post_approved_images,
                },
            }
        )
        _write_reports(root, report)
        return report
    sidecar_path = archive_path.with_suffix(archive_path.suffix + ".clearance.json")
    sidecar = {
        "schemaVersion": "seolleyeon_manual_review_clearance_sidecar_v3",
        "createdAt": now_utc(),
        "originalReason": flag_payload.get("reason"),
        "chunkId": transient_clearance.get("chunkId") or active_chunk.get("chunkId") or "",
        "clearReason": TRANSIENT_CODEX_QA_CLEAR_REASON if is_transient_codex_qa_clear else reason,
        "pendingStatus": "resolved" if not (pending_payload and pending_is_unresolved(pending_payload)) else "unresolved",
        "fileQaPassedAssets": transient_clearance.get("fileQaPassedAssets"),
        "selectedAssetCount": transient_clearance.get("selectedAssetCount"),
        "whitelistPath": (transient_clearance.get("scope") or {}).get("whitelistPath") if isinstance(transient_clearance.get("scope"), Mapping) else None,
        "contactSheetIndexPath": (transient_clearance.get("scope") or {}).get("contactSheetIndexPath") if isinstance(transient_clearance.get("scope"), Mapping) else None,
        "approvedCountsBefore": {
            "approvedCompleteIdentities": pre_approved_identities,
            "approvedImages": pre_approved_images,
        },
        "approvedCountsAfter": {
            "approvedCompleteIdentities": post_approved_identities,
            "approvedImages": post_approved_images,
        },
    }
    sidecar_path.write_text(json.dumps(sidecar, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report.update(
        {
            "result": "cleared",
            "cleared": True,
            "archivePath": to_portable_path(archive_path),
            "archiveSidecarPath": to_portable_path(sidecar_path),
            "clearReason": sidecar["clearReason"],
            "postClearCompletion": {
                "passed": bool(post_completion.get("passed")),
                "failureReasons": list(post_completion.get("failureReasons") or []),
                "approvedCompleteIdentities": post_approved_identities,
                "approvedImages": post_approved_images,
            },
        }
    )
    _write_reports(root, report)
    return report
