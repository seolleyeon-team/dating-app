from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .config import SHOT_ORDER, pipeline_paths, read_jsonl
from .codex_imagegen import read_pending
from .distribution_audit import audit_distribution
from .approval_evidence import evaluate_approved_identity_evidence
from .pending_state import pending_is_resolved, pending_unresolved_reason


COMPLETION_FAILURE_REASON_ORDER = (
    "manual_review_required",
    "unresolved_pending_imagegen",
    "stale_current_chunk_plan",
    "non_executable_current_chunk",
    "active_visual_qa_incomplete",
    "distribution_audit_incomplete",
    "missing_asset_qa_manifest",
    "missing_identity_qa_manifest",
    "missing_visual_verdict",
    "missing_approved_identity_manifest",
    "approved_identity_missing_final_file",
    "approved_asset_missing_file_qa",
    "approved_asset_missing_visual_qa",
    "approved_identity_missing_identity_qa",
    "approved_asset_not_in_asset_manifest",
    "approved_asset_not_in_generation_manifest",
    "metadata_mismatch",
    "needs_review_counted",
    "rejected_counted",
    "invalid_counted_identity",
    "over_level_approved",
    "over_level_4_4_to_5_0_counted",
    "distribution_mismatch",
    "surplus_detected",
)


def _as_bool(value: Any, *, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "y", "approved"}


def _failure_list(reasons: set[str]) -> list[str]:
    ordered = [reason for reason in COMPLETION_FAILURE_REASON_ORDER if reason in reasons]
    ordered.extend(sorted(reason for reason in reasons if reason not in set(ordered)))
    return ordered


def _pending_unresolved(pending_path: Path) -> tuple[bool, str]:
    if not pending_path.exists():
        return False, ""
    payload = read_pending(pending_path)
    if not isinstance(payload, dict):
        return True, "pending_json_not_object"
    if pending_is_resolved(payload):
        return False, ""
    return True, pending_unresolved_reason(payload)


def _count_jsonl_rows(path: Path) -> int:
    if not path.exists():
        return 0
    count = 0
    with path.open("rb") as f:
        for line in f:
            if line not in (b"", b"\n", b"\r\n"):
                count += 1
    return count


def _visual_manifest_state(root: Path | str | None) -> dict[str, Any]:
    paths = pipeline_paths(root)
    asset_path = paths.manifests / "asset_qa_manifest.jsonl"
    identity_path = paths.manifests / "identity_qa_manifest.jsonl"
    generation_path = paths.manifests / "generation_manifest.jsonl"
    approved_path = paths.manifests / "approved_identity_manifest.jsonl"
    asset_rows = read_jsonl(paths.manifests / "asset_qa_manifest.jsonl")
    identity_rows = read_jsonl(paths.manifests / "identity_qa_manifest.jsonl")
    generation_rows_count = _count_jsonl_rows(generation_path)
    asset_shots_by_profile: dict[str, set[str]] = {}
    for row in asset_rows:
        profile_id = str(row.get("profileId") or "")
        shot = str(row.get("shotType") or "")
        if profile_id and shot:
            asset_shots_by_profile.setdefault(profile_id, set()).add(shot)
    return {
        "assetRows": asset_rows,
        "identityRows": identity_rows,
        "identityProfiles": {str(row.get("profileId") or "") for row in identity_rows if row.get("profileId")},
        "assetShotsByProfile": asset_shots_by_profile,
        "assetQaRows": len(asset_rows),
        "identityQaRows": len(identity_rows),
        "generationRowsCount": generation_rows_count,
        "assetManifestExists": asset_path.exists(),
        "identityManifestExists": identity_path.exists(),
        "approvedManifestExists": approved_path.exists(),
        "visualMissing": not asset_rows or not identity_rows,
    }


def _latest_reset_report(root: Path | str | None) -> Path | None:
    reports_root = pipeline_paths(root).reports / "chunks"
    if not reports_root.exists():
        return None
    candidates = [path for path in reports_root.glob("*/reset_report.json") if path.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _read_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def _reset_completed_without_count_changes(root: Path | str | None) -> tuple[bool, str]:
    reset_path = _latest_reset_report(root)
    if reset_path is None:
        return False, ""
    try:
        report = _read_json_object(reset_path)
    except (OSError, ValueError, json.JSONDecodeError):
        return False, str(reset_path)
    safe = (
        str(report.get("status") or "") == "reset"
        and bool(report.get("generatedFilesPreserved")) is True
        and bool(report.get("approvedCountChanged")) is False
        and bool(report.get("distributionCountChanged")) is False
    )
    return safe, str(reset_path)


def _chunk_blockers(root: Path | str | None) -> dict[str, Any]:
    paths = pipeline_paths(root)
    plan_path = paths.manifests / "current_chunk_plan.json"
    state_path = paths.manifests / "current_chunk_state.json"
    reasons: set[str] = set()
    plan: dict[str, Any] = {}
    state: dict[str, Any] = {}
    if plan_path.exists():
        try:
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            reasons.add("stale_current_chunk_plan")
        if isinstance(plan, dict):
            status = str(plan.get("status") or "")
            if plan.get("executable") is not True and status not in {"finalized", "complete", "completed", "distribution_audit_complete"}:
                reasons.add("non_executable_current_chunk")
            if plan.get("dryRun") is True or str(plan.get("planMode") or "") == "dry_run":
                reasons.add("stale_current_chunk_plan")
            if status in {"running", "needs_manual_review", "failed", "conflicted", "stale"}:
                reasons.add("stale_current_chunk_plan")
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            reasons.add("stale_current_chunk_plan")
        if isinstance(state, dict):
            status = str(state.get("status") or "")
            if status in {"running", "needs_manual_review", "failed", "conflicted", "stale"}:
                reasons.add("stale_current_chunk_plan")
            generated_or_completed = bool(state.get("generatedAssets") or state.get("recoveredAssets") or state.get("completedAssetIds") or state.get("assetStates"))
            if generated_or_completed and state.get("activeVisualQaComplete") is False:
                reasons.add("active_visual_qa_incomplete")
            if generated_or_completed and state.get("distributionAuditComplete") is False:
                reasons.add("distribution_audit_incomplete")
    return {
        "planPath": str(plan_path),
        "statePath": str(state_path),
        "planExists": plan_path.exists(),
        "stateExists": state_path.exists(),
        "planStatus": plan.get("status", "") if isinstance(plan, dict) else "",
        "stateStatus": state.get("status", "") if isinstance(state, dict) else "",
        "activeVisualQaComplete": state.get("activeVisualQaComplete") if isinstance(state, dict) else None,
        "distributionAuditComplete": state.get("distributionAuditComplete") if isinstance(state, dict) else None,
        "reasons": sorted(reasons),
    }


def _invalid_counted_identities(audit: dict[str, Any]) -> list[dict[str, Any]]:
    invalid: list[dict[str, Any]] = []
    required_shots = set(SHOT_ORDER)
    candidates: list[dict[str, Any]] = []
    for identity in audit.get("approvedIdentities", []):
        if isinstance(identity, dict):
            candidates.append(identity)
    for identity in audit.get("evaluatedIdentities", []):
        if not isinstance(identity, dict):
            continue
        if _as_bool(identity.get("countsTowardDistribution")) and _as_bool(identity.get("completeApproved")):
            candidates.append(identity)
    seen_profiles: set[str] = set()
    for identity in candidates:
        if not isinstance(identity, dict):
            continue
        profile_key = str(identity.get("profileId") or "")
        if profile_key in seen_profiles:
            continue
        seen_profiles.add(profile_key)
        reasons: list[str] = []
        asset_decisions = identity.get("assetDecisions") if isinstance(identity.get("assetDecisions"), dict) else {}
        missing_shots = set(identity.get("missingShotTypes") or [])
        if str(identity.get("completeIdentityDecision") or "") != "approved":
            reasons.append("completeIdentityDecision_not_approved")
        if not _as_bool(identity.get("countsTowardDistribution")):
            reasons.append("countsTowardDistribution_false")
        if _as_bool(identity.get("metadataMismatch")):
            reasons.append("metadataMismatch_true")
        if str(identity.get("observedLooksLevelBand") or "") == "4.4-5.0":
            reasons.append("observedLooksLevelBand_4.4-5.0")
        if _as_bool(identity.get("sameIdentity"), default=True) is False:
            reasons.append("sameIdentity_false")
        if int(identity.get("approvedShotCount") or 0) != len(SHOT_ORDER):
            reasons.append("less_than_3_approved_shots")
        for shot in SHOT_ORDER:
            if str(asset_decisions.get(shot) or "") != "approved":
                reasons.append(f"{shot}_not_approved")
            if shot in missing_shots:
                reasons.append(f"{shot}_missing")
        if required_shots - set(asset_decisions):
            for shot in sorted(required_shots - set(asset_decisions)):
                reasons.append(f"{shot}_missing")
        if _as_bool(identity.get("needsReview")):
            reasons.append("needs_review")
        if _as_bool(identity.get("rejected")):
            reasons.append("rejected")
        for reason in identity.get("reasons") or []:
            if str(reason) in {"metadata_mismatch", "over_level_4.4-5.0", "sameIdentity_false"}:
                reasons.append(str(reason))
        if reasons:
            invalid.append(
                {
                    "profileId": identity.get("profileId", ""),
                    "reasons": sorted(set(reasons)),
                }
            )
    return invalid


def completion_check(*, root: Path | str | None = None) -> dict[str, Any]:
    paths = pipeline_paths(root)
    audit = audit_distribution(root=root, write_outputs=False)
    evidence = evaluate_approved_identity_evidence(root)
    count_checks = audit["countChecks"]
    failures: set[str] = set()
    manual_flag = paths.manifests / "manual_review_required.flag"
    if manual_flag.exists():
        failures.add("manual_review_required")

    pending_unresolved, pending_reason = _pending_unresolved(paths.manifests / "pending-imagegen.json")
    if pending_unresolved:
        failures.add("unresolved_pending_imagegen")

    chunk_state = _chunk_blockers(root)
    failures.update(str(reason) for reason in chunk_state["reasons"])

    visual_state = _visual_manifest_state(root)
    if not visual_state["assetManifestExists"]:
        failures.add("missing_asset_qa_manifest")
    if not visual_state["identityManifestExists"]:
        failures.add("missing_identity_qa_manifest")
    if visual_state["visualMissing"]:
        reset_ok, reset_path = _reset_completed_without_count_changes(root)
        reset_has_no_active_chunk = reset_ok and not chunk_state["planExists"] and not chunk_state["stateExists"]
        no_approved_distribution = int(audit.get("approvedCompleteIdentityCount") or 0) == 0 and int(audit.get("approvedImageCount") or 0) == 0
        if not (reset_has_no_active_chunk and no_approved_distribution):
            failures.add("missing_visual_verdict")
    if not visual_state["approvedManifestExists"]:
        failures.add("missing_approved_identity_manifest")
    missing_visual_rows: list[dict[str, Any]] = []
    for identity in audit.get("approvedIdentities", []):
        if not isinstance(identity, dict):
            continue
        profile_id = str(identity.get("profileId") or "")
        missing: list[str] = []
        if profile_id not in visual_state["identityProfiles"]:
            missing.append("identity_qa")
        asset_shots = visual_state["assetShotsByProfile"].get(profile_id, set())
        for shot in SHOT_ORDER:
            if shot not in asset_shots:
                missing.append(f"asset_qa:{shot}")
        if missing:
            missing_visual_rows.append({"profileId": profile_id, "missing": missing})
    if missing_visual_rows:
        failures.add("approved_asset_missing_visual_qa")

    for invalid in evidence["invalidApprovedIdentities"]:
        failures.update(str(reason) for reason in invalid.get("reasons", []))
    if evidence["invalidApprovedIdentities"]:
        failures.add("invalid_counted_identity")
    for invalid in evidence["invalidApprovedAssets"]:
        failures.update(str(reason) for reason in invalid.get("reasons", []))

    invalid_counted = _invalid_counted_identities(audit)
    if invalid_counted or audit.get("countedWithoutThreeApprovedShots"):
        failures.add("approved_identity_missing_identity_qa")
        failures.add("invalid_counted_identity")
    if audit.get("overLevelApprovedIdentities") or "over_level_4_4_to_5_0_counted" in failures:
        failures.add("over_level_4_4_to_5_0_counted")
        failures.add("over_level_approved")
    if any(int(row.get("surplus") or 0) > 0 for row in audit.get("bucketChecks", [])):
        failures.add("surplus_detected")
    if not audit.get("exactFinalCountMatch") or not audit.get("exactDistributionMatch") or audit.get("failConditions"):
        failures.add("distribution_mismatch")

    passed = bool(audit["passed"]) and not failures
    result = {
        "schemaVersion": "seolleyeon_ai_image_completion_check_v3",
        "passed": passed,
        "failureReasons": _failure_list(failures),
        "manualReviewRequired": manual_flag.exists(),
        "manualReviewFlag": str(manual_flag) if manual_flag.exists() else "",
        "unresolvedPendingImagegen": pending_unresolved,
        "pendingReason": pending_reason,
        "chunkState": chunk_state,
        "visualVerdictState": {
            "assetQaRows": visual_state["assetQaRows"],
            "identityQaRows": visual_state["identityQaRows"],
            "generationRows": visual_state["generationRowsCount"],
            "assetManifestExists": visual_state["assetManifestExists"],
            "identityManifestExists": visual_state["identityManifestExists"],
            "approvedManifestExists": visual_state["approvedManifestExists"],
            "missingVisualVerdictSuppressedAfterReset": bool(
                visual_state["visualMissing"]
                and "missing_visual_verdict" not in failures
                and not chunk_state["planExists"]
                and not chunk_state["stateExists"]
            ),
        },
        "missingVisualVerdict": bool(
            "missing_visual_verdict" in failures
            or "missing_asset_qa_manifest" in failures
            or "missing_identity_qa_manifest" in failures
            or "approved_asset_missing_visual_qa" in failures
        ),
        "invalidApprovedIdentities": evidence["invalidApprovedIdentities"],
        "invalidApprovedAssets": evidence["invalidApprovedAssets"],
        "invalidCountedIdentities": invalid_counted,
        "missingVisualVerdictRows": missing_visual_rows,
        "approvedCompleteIdentities": audit["approvedCompleteIdentities"],
        "approvedImages": audit["approvedImages"],
        "femaleApprovedCompleteIdentities": audit["femaleApprovedCompleteIdentities"],
        "maleApprovedCompleteIdentities": audit["maleApprovedCompleteIdentities"],
        "exactFinalCountMatch": audit["exactFinalCountMatch"],
        "exactDistributionMatch": audit["exactDistributionMatch"],
        "countChecks": count_checks,
        "overLevelApprovedIdentities": audit["overLevelApprovedIdentities"],
    }
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Pass only when Seolleyeon v3 AI image final targets are exactly complete.")
    parser.add_argument("--root", default=None)
    parser.add_argument("--targets_json", default=None, help="Compatibility option; targets are loaded from ai_image/config.")
    parser.add_argument("--audit_json", default=None, help="Compatibility option; completion recomputes the numeric audit.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = completion_check(root=args.root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1
