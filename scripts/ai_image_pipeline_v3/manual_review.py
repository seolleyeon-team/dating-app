from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .codex_imagegen import pending_path, read_pending
from .completion import completion_check
from .config import ensure_base_dirs, now_utc, pipeline_paths, to_portable_path
from .distribution_audit import audit_distribution
from .pending_state import pending_is_unresolved


MANUAL_REVIEW_CLEAR_SCHEMA_VERSION = "seolleyeon_manual_review_clear_v3"
EXPECTED_PRE_CLEAR_FAILURES = {"manual_review_required", "distribution_mismatch"}
EXPECTED_POST_CLEAR_FAILURES = {"distribution_mismatch"}


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


def clear_manual_review(*, root: Path | str | None = None, reason: str = "") -> dict[str, Any]:
    paths = pipeline_paths(root)
    ensure_base_dirs(paths)
    flag_path = paths.manifests / "manual_review_required.flag"
    reasons_if_unsafe: list[str] = []
    if not reason:
        reasons_if_unsafe.append("reason_required")
    if not flag_path.exists():
        reasons_if_unsafe.append("manual_review_flag_missing")
    active_chunk_ok, active_chunk, active_chunk_reasons = _active_finalized_chunk_clearance(paths)
    if not active_chunk_ok:
        reasons_if_unsafe.extend(active_chunk_reasons)
    pending_payload = read_pending(pending_path(root))
    if pending_payload and pending_is_unresolved(pending_payload):
        reasons_if_unsafe.append("unresolved_pending_imagegen")

    reset_path = _latest_reset_report(root)
    reset_ok, reset_report, reset_reasons = _reset_report_ok(reset_path)
    if not reset_ok and not active_chunk_ok:
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
    unexpected_pre = sorted(pre_failures - EXPECTED_PRE_CLEAR_FAILURES)
    if unexpected_pre:
        reasons_if_unsafe.extend(f"unexpected_pre_clear_completion_failure:{item}" for item in unexpected_pre)
    if pre_completion.get("passed"):
        reasons_if_unsafe.append("completion_unexpectedly_passed_before_clear")

    report: dict[str, Any] = {
        "schemaVersion": MANUAL_REVIEW_CLEAR_SCHEMA_VERSION,
        "result": "not_cleared",
        "cleared": False,
        "reason": reason,
        "createdAt": now_utc(),
        "archivePath": None,
        "manualFlagPath": to_portable_path(flag_path),
        "resetReportPath": to_portable_path(reset_path) if reset_path else "",
        "readiness": {
            "passed": not reasons_if_unsafe,
            "reasonsIfUnsafe": reasons_if_unsafe,
            "resetReport": reset_report,
            "activeChunk": active_chunk,
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
    unexpected_post = sorted(post_failures - EXPECTED_POST_CLEAR_FAILURES)
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
                },
            }
        )
        _write_reports(root, report)
        return report
    report.update(
        {
            "result": "cleared",
            "cleared": True,
            "archivePath": to_portable_path(archive_path),
            "postClearCompletion": {
                "passed": bool(post_completion.get("passed")),
                "failureReasons": list(post_completion.get("failureReasons") or []),
                "approvedCompleteIdentities": int(post_completion.get("approvedCompleteIdentities") or 0),
                "approvedImages": int(post_completion.get("approvedImages") or 0),
            },
        }
    )
    _write_reports(root, report)
    return report
