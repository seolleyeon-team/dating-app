from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


REQUIRED_MIN_USERS = 3
UID_PHOTO_INPUT_BLOCKERS = {
    "confirm_uid_photo_consent_required",
    "uid_photo_pair_consent_missing",
}
CONSENT_MISMATCH_BLOCKER = "uid_photo_consent_map_mismatch"
GENERAL_CONSENT_EXACT_MISMATCH_BLOCKER = "general_consent_exact_uid_photo_mismatch"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _status_name(statuses: Mapping[str, bool]) -> str:
    if all(value for key, value in statuses.items() if key != "blockedByInputs"):
        return "PASS_INTERNAL_CANARY_3USER"
    if statuses.get("blockedByInputs"):
        return "BLOCKED_BY_INPUTS"
    return "PASS_PARTIAL"


def _canary_summary(report: Mapping[str, Any]) -> dict[str, Any]:
    jobs = report.get("jobs")
    if not isinstance(jobs, list):
        jobs = []
    preview_ready_count = sum(1 for job in jobs if _job_preview_ready(job))
    approved_count = sum(1 for job in jobs if _job_approved(job))
    lock_pass_count = sum(1 for job in jobs if _job_lock_passed(job))
    return {
        "jobCount": int(report.get("jobCount") or len(jobs)),
        "previewReadyCount": preview_ready_count,
        "approvedCount": approved_count,
        "lockRetestPassedCount": lock_pass_count,
    }


def _job_preview_ready(job: Any) -> bool:
    if not isinstance(job, Mapping):
        return False
    nested_job = job.get("job") if isinstance(job.get("job"), Mapping) else {}
    status = str(job.get("status") or nested_job.get("status") or "")
    candidate_stats = job.get("candidateStats")
    preview_count = 0
    if isinstance(candidate_stats, Mapping):
        preview_count = int(candidate_stats.get("previewCount") or 0)
    return status in {"preview_ready", "approved"} and preview_count > 0


def _job_approved(job: Any) -> bool:
    if not isinstance(job, Mapping):
        return False
    approval = job.get("approval") if isinstance(job.get("approval"), Mapping) else {}
    return (
        bool(job.get("approvedAvatarUrlPresent"))
        or bool(approval.get("approvedAvatarUrlPresent"))
        or str(job.get("status") or "") == "approved"
        or str(approval.get("avatarStatus") or "") == "approved"
    )


def _job_lock_passed(job: Any) -> bool:
    if not isinstance(job, Mapping):
        return False
    value = str(job.get("lockRetestStatus") or "").lower()
    if value in {"passed", "pass", "avatar_already_approved"}:
        return True
    lock_retest = job.get("lockRetest") if isinstance(job.get("lockRetest"), Mapping) else {}
    value = str(lock_retest.get("status") or lock_retest.get("errorMessage") or "").lower()
    return value in {"passed", "pass", "avatar_already_approved"}


def _trait_summary(report: Mapping[str, Any]) -> dict[str, Any]:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    return {
        "jobCount": int(report.get("jobCount") or 0),
        "averageCoveragePercentage": summary.get("averageCoveragePercentage"),
        "allExpandedFieldsUnclearCount": int(summary.get("allExpandedFieldsUnclearCount") or 0),
    }


def _inventory_summary(report: Mapping[str, Any]) -> dict[str, Any]:
    if not report:
        return {
            "present": False,
            "passFixtureCount": None,
            "eligibleAuthUserCount": None,
            "eligiblePairUpperBound": None,
            "neededForThreeUserRerun": None,
            "unmappedPassFixtures": [],
        }
    return {
        "present": True,
        "passFixtureCount": int(report.get("passFixtureCount") or 0),
        "eligibleAuthUserCount": int(report.get("eligibleAuthUserCount") or 0),
        "eligiblePairUpperBound": int(report.get("eligiblePairUpperBound") or 0),
        "neededForThreeUserRerun": int(report.get("neededForThreeUserRerun") or 0),
        "unmappedPassFixtures": list(report.get("unmappedPassFixtures") or []),
    }


def _activation_summary(report: Mapping[str, Any]) -> dict[str, Any]:
    if not report:
        return {
            "present": False,
            "status": None,
            "consentPairCount": 0,
            "matchedConsentPairCount": 0,
            "unexpectedConsentPairCount": 0,
            "activeRowCount": None,
            "blockedRowCount": None,
            "blockerCounts": {},
            "requiredConsentMapRows": [],
            "uidPhotoConsentMap": {},
        }
    blocker_counts: dict[str, int] = {}
    for row in report.get("rows", []):
        if not isinstance(row, Mapping) or row.get("active"):
            continue
        for blocker in row.get("blockers", []):
            key = str(blocker or "").strip()
            if key:
                blocker_counts[key] = blocker_counts.get(key, 0) + 1
    return {
        "present": True,
        "status": report.get("status"),
        "consentPairCount": int(report.get("consentPairCount") or 0),
        "matchedConsentPairCount": int(report.get("matchedConsentPairCount") or 0),
        "unexpectedConsentPairCount": int(report.get("unexpectedConsentPairCount") or 0),
        "activeRowCount": int(report.get("activeRowCount") or 0),
        "blockedRowCount": int(report.get("blockedRowCount") or 0),
        "blockerCounts": dict(sorted(blocker_counts.items())),
        "requiredConsentMapRows": list(report.get("requiredConsentMapRows") or []),
        "uidPhotoConsentMap": report.get("uidPhotoConsentMap", {}),
    }


def _general_consent_summary(report: Mapping[str, Any]) -> dict[str, Any]:
    evidence = report.get("generalConsentEvidence")
    if not isinstance(evidence, Mapping):
        return {
            "present": False,
            "valid": None,
            "scope": None,
            "consentFile": None,
            "consentFileSelection": None,
            "exactUidPhotoConsent": {},
            "blockers": [],
        }
    return {
        "present": bool(evidence.get("present")),
        "valid": evidence.get("valid"),
        "scope": evidence.get("scope"),
        "consentFile": evidence.get("consentFile"),
        "consentFileSelection": evidence.get("consentFileSelection"),
        "exactUidPhotoConsent": evidence.get("exactUidPhotoConsent", {}),
        "blockers": list(evidence.get("blockers") or []),
    }


def _general_consent_exact_mismatch(summary: Mapping[str, Any]) -> bool:
    if not summary.get("present") or summary.get("valid") is not True:
        return False
    exact = summary.get("exactUidPhotoConsent")
    if not isinstance(exact, Mapping) or exact.get("satisfiedByThisFile") is True:
        return False
    parsed_count = int(exact.get("parsedRowCount") or 0)
    required_count = int(exact.get("requiredRowCount") or 0)
    matched_count = int(exact.get("matchedRowCount") or 0)
    unexpected_count = int(exact.get("unexpectedRowCount") or 0)
    return unexpected_count > 0 or (
        parsed_count > 0
        and required_count > 0
        and matched_count < required_count
    )


def _post_consent_gate_fresh(post_consent: Mapping[str, Any] | None) -> bool:
    if not isinstance(post_consent, Mapping) or not post_consent:
        return True
    gate = post_consent.get("gate")
    if not isinstance(gate, Mapping):
        return True
    return gate.get("executed") is not False


def build_audit(
    *,
    gate: Mapping[str, Any],
    canary: Mapping[str, Any],
    trait: Mapping[str, Any],
    privacy: Mapping[str, Any],
    inventory: Mapping[str, Any] | None = None,
    activation: Mapping[str, Any] | None = None,
    post_consent: Mapping[str, Any] | None = None,
    min_users: int = REQUIRED_MIN_USERS,
) -> dict[str, Any]:
    gate_fresh_for_post_consent = _post_consent_gate_fresh(post_consent)
    raw_eligible_rows = int(gate.get("validation", {}).get("eligibleUploadRows") or 0)
    raw_safe_to_apply = bool(gate.get("safeToApply"))
    eligible_rows = raw_eligible_rows if gate_fresh_for_post_consent else 0
    safe_to_apply = raw_safe_to_apply if gate_fresh_for_post_consent else False
    canary_summary = _canary_summary(canary)
    trait_summary = _trait_summary(trait)
    inventory_summary = _inventory_summary(inventory or {})
    activation_summary = _activation_summary(activation or {})
    general_consent_summary = _general_consent_summary(post_consent or {})
    privacy_pass = str(privacy.get("status") or "").lower() == "pass"
    consent_evidence = gate.get("validation", {}).get("consentEvidence")
    consent_valid = not isinstance(consent_evidence, Mapping) or bool(consent_evidence.get("valid"))
    inventory_ready_or_absent = (
        not inventory_summary["present"]
        or int(inventory_summary["eligiblePairUpperBound"] or 0) >= min_users
        or canary_summary["jobCount"] >= min_users
    )
    active_uid_photo_rows = int(activation_summary["activeRowCount"] or 0)
    activation_blocker_counts = activation_summary["blockerCounts"]
    consent_map = activation_summary["uidPhotoConsentMap"]
    unexpected_consent_pairs = int(activation_summary["unexpectedConsentPairCount"] or 0)
    if isinstance(consent_map, Mapping):
        unexpected_consent_pairs = max(
            unexpected_consent_pairs,
            int(consent_map.get("unexpectedPairCount") or 0),
        )
    blocked_by_uid_photo_mismatch = (
        activation_summary["present"]
        and canary_summary["jobCount"] < min_users
        and (
            str(activation_summary["status"] or "") == "BLOCKED_CONSENT_MISMATCH"
            or unexpected_consent_pairs > 0
        )
    )
    uid_photo_activation_ready_or_absent = (
        not activation_summary["present"]
        or (
            not blocked_by_uid_photo_mismatch
            and (
                active_uid_photo_rows >= min_users
                or eligible_rows >= min_users
                or canary_summary["jobCount"] >= min_users
            )
        )
    )
    blocked_by_fixture_or_auth = (
        eligible_rows < min_users
        and canary_summary["jobCount"] < min_users
        and inventory_summary["present"]
        and int(inventory_summary["eligiblePairUpperBound"] or 0) < min_users
    )
    blocked_by_consent_evidence = not consent_valid and canary_summary["jobCount"] < min_users
    blocked_by_uid_photo_input = (
        activation_summary["present"]
        and active_uid_photo_rows < min_users
        and canary_summary["jobCount"] < min_users
        and any(
            int(activation_blocker_counts.get(blocker) or 0) > 0
            for blocker in UID_PHOTO_INPUT_BLOCKERS
        )
    )
    blocked_by_general_consent_exact_mismatch = (
        canary_summary["jobCount"] < min_users
        and _general_consent_exact_mismatch(general_consent_summary)
    )
    input_blockers: list[str] = []
    if blocked_by_consent_evidence:
        input_blockers.append("canary_consent_evidence_invalid")
    if blocked_by_general_consent_exact_mismatch:
        input_blockers.append(GENERAL_CONSENT_EXACT_MISMATCH_BLOCKER)
    if blocked_by_fixture_or_auth:
        input_blockers.append("fixture_or_staging_auth_insufficient")
    if blocked_by_uid_photo_input:
        for blocker in sorted(UID_PHOTO_INPUT_BLOCKERS):
            if int(activation_blocker_counts.get(blocker) or 0) > 0:
                input_blockers.append(blocker)
    if blocked_by_uid_photo_mismatch:
        input_blockers.append(CONSENT_MISMATCH_BLOCKER)
    statuses = {
        "projectGuardEvidencePresent": bool(gate.get("generatedAt")),
        "normalizationAndPreflightRan": bool(gate.get("preflight", {}).get("provider")),
        "consentEvidenceValid": consent_valid or canary_summary["jobCount"] >= min_users,
        "inventoryReadyOrCanaryAlreadyRan": inventory_ready_or_absent,
        "uidPhotoActivationReadyOrCanaryAlreadyRan": uid_photo_activation_ready_or_absent,
        "mappingHasThreeEligibleRows": eligible_rows >= min_users,
        "gateSafeToApplyOrAlreadyRan": safe_to_apply or canary_summary["jobCount"] >= min_users,
        "threeJobsObserved": canary_summary["jobCount"] >= min_users,
        "threePreviewReadyObserved": canary_summary["previewReadyCount"] >= min_users,
        "threeApprovalsObserved": canary_summary["approvedCount"] >= min_users,
        "threeLockRetestsObserved": canary_summary["lockRetestPassedCount"] >= min_users,
        "traitCoverageReported": trait_summary["jobCount"] >= 1,
        "privacyQaPassed": privacy_pass,
        "blockedByInputs": bool(input_blockers),
    }
    remaining: list[str] = []
    if not consent_valid and canary_summary["jobCount"] < min_users:
        remaining.append("provide_valid_canary_consent_evidence")
    if blocked_by_general_consent_exact_mismatch:
        remaining.append("fix_general_consent_exact_uid_photo_mismatch")
    if (
        inventory_summary["present"]
        and canary_summary["jobCount"] < min_users
        and int(inventory_summary["passFixtureCount"] or 0) < min_users
    ):
        remaining.append(
            f"provide_{min_users - int(inventory_summary['passFixtureCount'] or 0)}_more_mediapipe_pass_fixtures"
        )
    if (
        inventory_summary["present"]
        and canary_summary["jobCount"] < min_users
        and int(inventory_summary["eligibleAuthUserCount"] or 0) < min_users
    ):
        remaining.append(
            f"provide_{min_users - int(inventory_summary['eligibleAuthUserCount'] or 0)}_unlocked_staging_auth_users"
        )
    needs_uid_photo_activation = (
        activation_summary["present"]
        and canary_summary["jobCount"] < min_users
        and active_uid_photo_rows < min_users
    )
    if needs_uid_photo_activation:
        remaining.append(
            f"activate_{min_users - active_uid_photo_rows}_uid_photo_consent_rows"
        )
    elif blocked_by_uid_photo_mismatch:
        remaining.append("fix_uid_photo_consent_map_mismatch")
    elif (
        activation_summary["present"]
        and active_uid_photo_rows >= min_users
        and not statuses["mappingHasThreeEligibleRows"]
        and canary_summary["jobCount"] < min_users
    ):
        remaining.append("rerun_pr84_gate_with_activated_mapping")
    elif not statuses["mappingHasThreeEligibleRows"] and canary_summary["jobCount"] < min_users:
        remaining.append(f"provide_{max(0, min_users - eligible_rows)}_more_eligible_uid_photo_rows")
    if canary_summary["jobCount"] < min_users:
        remaining.append("run_staging_canary_for_three_valid_users")
    if canary_summary["previewReadyCount"] < min_users:
        remaining.append("observe_preview_ready_for_three_users")
    if canary_summary["approvedCount"] < min_users:
        remaining.append("approve_one_candidate_for_each_preview_ready_user")
    if canary_summary["lockRetestPassedCount"] < min_users:
        remaining.append("retest_approved_avatar_lock_for_three_users")
    if not statuses["traitCoverageReported"]:
        remaining.append("generate_trait_coverage_report")
    if not privacy_pass:
        remaining.append("run_passing_privacy_qa")
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "status": _status_name(statuses),
        "minUsers": min_users,
        "complete": all(value for key, value in statuses.items() if key != "blockedByInputs"),
        "gate": {
            "eligibleUploadRows": eligible_rows,
            "rawEligibleUploadRows": raw_eligible_rows,
            "neededEligibleRows": int(gate.get("neededEligibleRows") or max(0, min_users - eligible_rows)),
            "nextAction": gate.get("nextAction"),
            "safeToApply": safe_to_apply,
            "rawSafeToApply": raw_safe_to_apply,
            "freshForPostConsent": gate_fresh_for_post_consent,
            "consentEvidence": consent_evidence if isinstance(consent_evidence, Mapping) else {},
            "blockerCounts": gate.get("validation", {}).get("blockerCounts", {}),
            "unmappedPassFixtures": gate.get("preflight", {}).get("unmappedPassFixtures", []),
        },
        "canary": canary_summary,
        "inventory": inventory_summary,
        "activation": activation_summary,
        "generalConsentEvidence": general_consent_summary,
        "traitCoverage": trait_summary,
        "privacyQa": {
            "status": privacy.get("status"),
            "publicLeakageCount": privacy.get("public_leakage_count"),
            "clientCodeLeakageCount": privacy.get("client_code_leakage_count"),
        },
        "inputBlockers": input_blockers,
        "requirements": statuses,
        "remaining": list(dict.fromkeys(remaining)),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit PR8.4 canary completion evidence.")
    parser.add_argument("--gate_json", default="out/pr84_canary_gate_summary.json")
    parser.add_argument("--canary_json", default="out/avatar_internal_canary_report_pr84.json")
    parser.add_argument("--trait_json", default="out/avatar_trait_coverage_report.json")
    parser.add_argument("--privacy_json", default="out/qa_media_privacy_report.json")
    parser.add_argument("--inventory_json", default="out/pr84_eligibility_inventory.json")
    parser.add_argument("--activation_json", default="out/pr84_canary_uid_photo_map_activation.json")
    parser.add_argument("--post_consent_json", default="out/pr84_post_consent_canary_report.json")
    parser.add_argument("--output_json", default="out/pr84_completion_audit.json")
    parser.add_argument("--min_users", type=int, default=REQUIRED_MIN_USERS)
    args = parser.parse_args(argv)

    report = build_audit(
        gate=_load_json(Path(args.gate_json)),
        canary=_load_json(Path(args.canary_json)),
        trait=_load_json(Path(args.trait_json)),
        privacy=_load_json(Path(args.privacy_json)),
        inventory=_load_json(Path(args.inventory_json)),
        activation=_load_json(Path(args.activation_json)),
        post_consent=_load_json(Path(args.post_consent_json)),
        min_users=args.min_users,
    )
    output_path = Path(args.output_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(output_path.resolve()),
                "status": report["status"],
                "complete": report["complete"],
                "remaining": report["remaining"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
