from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping

from .config import MAX_ATTEMPTS, SHOT_ORDER, ensure_base_dirs, pipeline_paths, read_jsonl
from .distribution_audit import audit_distribution, group_by_profile
from .distribution_targets import FACE_TYPES, LOOKS_LEVEL_BANDS, target_face_type, target_looks_level_band
from .manifest import load_generation_manifest
from .retry_plan import APPROVED_STATUSES, attempt_count, face_card_exhaustion


def _latest_audit(root: Path | str | None = None, *, refresh: bool = False) -> dict[str, Any]:
    paths = pipeline_paths(root)
    latest = paths.reports / "latest_distribution_audit.json"
    if refresh or not latest.exists():
        return audit_distribution(root=root)
    return json.loads(latest.read_text(encoding="utf-8"))


def deficit_sets(audit: Mapping[str, Any]) -> dict[str, dict[str, set[str]]]:
    result: dict[str, dict[str, set[str]]] = {
        "global": {"faceType": set(), "looksLevelBand": set()},
        "female": {"faceType": set(), "looksLevelBand": set()},
        "male": {"faceType": set(), "looksLevelBand": set()},
    }
    for row in audit.get("bucketChecks", []):
        if not isinstance(row, Mapping):
            continue
        if int(row.get("deficit") or 0) <= 0:
            continue
        scope = str(row.get("scope") or "")
        dimension = str(row.get("dimension") or "")
        bucket = str(row.get("bucket") or "")
        if scope in result and dimension in result[scope]:
            result[scope][dimension].add(bucket)
    return result


def is_bucket_allowed(gender: str, face_type: str, looks_band: str, deficits: Mapping[str, Mapping[str, set[str]]]) -> bool:
    return (
        face_type in deficits.get("global", {}).get("faceType", set())
        and face_type in deficits.get(gender, {}).get("faceType", set())
        and looks_band in deficits.get("global", {}).get("looksLevelBand", set())
        and looks_band in deficits.get(gender, {}).get("looksLevelBand", set())
        and looks_band != "4.4-5.0"
    )


def _normalize_identity_decision(row: Mapping[str, Any]) -> str:
    for key in ("finalCompleteIdentityDecision", "completeIdentityDecision", "decision", "status"):
        value = str(row.get(key) or "").strip().lower()
        if value in {"approved", "identity_approved"}:
            return "approved"
        if value in {"needs_review", "identity_needs_review"}:
            return "needs_review"
        if value in {"rejected", "identity_rejected"}:
            return "rejected"
    return ""


def _latest_identity_qa_by_profile(root: Path | str | None = None) -> dict[str, Mapping[str, Any]]:
    rows = read_jsonl(pipeline_paths(root).manifests / "identity_qa_manifest.jsonl")
    latest: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        profile_id = str(row.get("profileId") or "")
        if profile_id:
            latest[profile_id] = row
    return latest


def _rejected_profile_ids(root: Path | str | None = None) -> set[str]:
    """Profiles with a durable rejected-identity verdict must not be replanned.

    The bounded chunk planner's reuse policy disallows reuse from rejected
    identities. A rejected identity can have some approved assets (for example
    an approved face/silhouette and a rejected vibe card). Replanning that same
    profile as a fresh full identity is unsafe because existing per-asset
    attempt counters and QA verdicts still belong to the rejected identity and
    can immediately trip max-attempt exhaustion. Treat the rejected identity
    manifest as the durable exclusion source, not just identity_qa_manifest.
    """
    rows = read_jsonl(pipeline_paths(root).manifests / "rejected_identity_manifest.jsonl")
    rejected: set[str] = set()
    for row in rows:
        profile_id = str(row.get("profileId") or "")
        if not profile_id:
            continue
        decision = _normalize_identity_decision(row)
        if decision == "rejected" or bool(row.get("rejected")) or bool(row.get("completeApproved") is False):
            rejected.add(profile_id)
    return rejected


def _prompt_targeting_version(row: Mapping[str, Any]) -> str:
    value = str(row.get("promptTargetingVersion") or "").strip()
    if value:
        return value
    metadata = row.get("metadata")
    if isinstance(metadata, Mapping):
        return str(metadata.get("promptTargetingVersion") or "").strip()
    return ""


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


def _active_generation_rows(root: Path | str | None = None) -> list[dict[str, Any]]:
    paths = pipeline_paths(root)
    active_assets = {
        str(row.get("assetId") or ""): row
        for row in read_jsonl(paths.manifests / "ai_profile_assets_v3.jsonl")
        if row.get("assetId")
    }
    rows = load_generation_manifest(paths)
    if not active_assets:
        return rows
    return [
        dict(row)
        for row in rows
        if str(row.get("assetId") or "") in active_assets
        and _prompt_evidence_matches_active_asset(active_assets[str(row.get("assetId") or "")], row)
    ]


def _identity_complete(profile_rows: list[Mapping[str, Any]], identity_qa: Mapping[str, Any] | None = None) -> bool:
    decision = _normalize_identity_decision(identity_qa or {})
    if decision == "rejected":
        return False
    if decision == "approved":
        return True
    by_shot = {str(row.get("shotType") or ""): row for row in profile_rows}
    return all(str(by_shot.get(shot, {}).get("status") or "") in APPROVED_STATUSES for shot in SHOT_ORDER) and decision == "approved"


def _abandoned_profile_ids(root: Path | str | None = None) -> set[str]:
    rows = read_jsonl(pipeline_paths(root).manifests / "abandoned_chunk_manifest.jsonl")
    return {str(row.get("profileId") or "") for row in rows if row.get("profileId")}


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


def _identity_has_eyewear(row: Mapping[str, Any]) -> bool:
    explicit = _normalize_has_eyewear_filter(row.get("hasEyewear"))
    if explicit is not None:
        return explicit
    for key in ("eyewearGroup", "targetEyewearGroup", "shotEyewearExpected", "canonicalEyewear", "eyewear"):
        text = str(row.get(key) or "").strip().lower()
        if text and text not in {"none", "no_eyewear", "without_eyewear", "bare_face"}:
            return True
    return False


def _identity_eyewear_group(row: Mapping[str, Any]) -> str:
    value = str(row.get("eyewearGroup") or row.get("targetEyewearGroup") or "").strip()
    if value:
        return value
    return "glasses" if _identity_has_eyewear(row) else "none"


def select_distribution_buckets(
    *,
    root: Path | str | None = None,
    refresh_audit: bool = False,
    max_identities: int = 24,
    max_attempts: int = MAX_ATTEMPTS,
    exclude_abandoned: bool = True,
    exclude_profile_ids: set[str] | None = None,
    face_type: str | None = None,
    looks_level_band: str | None = None,
    gender: str | None = None,
    has_eyewear: Any = None,
    eyewear_group: str | None = None,
    require_eyewear_mix: bool = False,
) -> dict[str, Any]:
    paths = pipeline_paths(root)
    ensure_base_dirs(paths)
    audit = _latest_audit(root, refresh=refresh_audit)
    deficits = deficit_sets(audit)
    rows = _active_generation_rows(root)
    grouped = group_by_profile(rows)
    allowed_identities: list[dict[str, Any]] = []
    forbidden_buckets: list[dict[str, Any]] = []
    skipped_exhausted_candidates: list[dict[str, Any]] = []
    seen_forbidden: set[tuple[str, str, str]] = set()
    excluded_profiles = set(exclude_profile_ids or set())
    identity_qa_by_profile = _latest_identity_qa_by_profile(root)
    if exclude_abandoned:
        excluded_profiles.update(_abandoned_profile_ids(root))
    excluded_profiles.update(_rejected_profile_ids(root))
    excluded_profiles.update(
        profile_id
        for profile_id, row in identity_qa_by_profile.items()
        if _normalize_identity_decision(row) == "rejected"
    )
    focus_face_type = str(face_type or "").strip()
    focus_looks_level_band = str(looks_level_band or "").strip()
    focus_gender = str(gender or "").strip()
    focus_has_eyewear = _normalize_has_eyewear_filter(has_eyewear)
    focus_eyewear_group = str(eyewear_group or "").strip()

    for profile_id, profile_rows in sorted(grouped.items()):
        if profile_id in excluded_profiles:
            continue
        anchor = profile_rows[0]
        gender = str(anchor.get("gender") or "")
        if gender not in {"female", "male"}:
            continue
        if focus_gender and gender != focus_gender:
            continue
        if not bool(anchor.get("activeForTarget", True)):
            continue
        if _identity_complete(profile_rows, identity_qa_by_profile.get(profile_id)):
            continue
        face_type = target_face_type(anchor)
        looks_band = target_looks_level_band(anchor)
        identity_has_eyewear = _identity_has_eyewear(anchor)
        identity_eyewear_group = _identity_eyewear_group(anchor)
        if focus_face_type and face_type != focus_face_type:
            continue
        if focus_looks_level_band and looks_band != focus_looks_level_band:
            continue
        if focus_has_eyewear is not None and identity_has_eyewear != focus_has_eyewear:
            continue
        if focus_eyewear_group and identity_eyewear_group != focus_eyewear_group:
            continue
        key = (gender, face_type, looks_band)
        if not is_bucket_allowed(gender, face_type, looks_band, deficits):
            if key not in seen_forbidden:
                seen_forbidden.add(key)
                forbidden_buckets.append({"gender": gender, "targetFaceType": face_type, "targetLooksLevelBand": looks_band})
            continue
        exhausted_face = face_card_exhaustion(profile_rows, max_attempts=max_attempts)
        if exhausted_face:
            skipped_exhausted_candidates.append(
                {
                    **exhausted_face,
                    "gender": gender,
                    "targetFaceType": face_type,
                    "targetLooksLevelBand": looks_band,
                }
            )
            continue
        if all(attempt_count(row) >= max_attempts and str(row.get("status") or "") not in APPROVED_STATUSES for row in profile_rows):
            continue
        allowed_identities.append(
            {
                "profileId": profile_id,
                "gender": gender,
                "targetFaceType": face_type,
                "targetLooksLevelBand": looks_band,
                "hasEyewear": identity_has_eyewear,
                "eyewearGroup": identity_eyewear_group,
                "eyewear": str(anchor.get("eyewear") or "").strip(),
                "canonicalEyewear": str(anchor.get("canonicalEyewear") or "").strip(),
                "shotStatuses": {str(row.get("shotType") or ""): str(row.get("status") or "") for row in profile_rows},
            }
        )
        if len(allowed_identities) >= max_identities and not require_eyewear_mix:
            break

    if require_eyewear_mix:
        mixed_selection: list[dict[str, Any]] = []
        selected_profile_ids: set[str] = set()
        for needed in (True, False):
            candidate = next((identity for identity in allowed_identities if bool(identity.get("hasEyewear")) is needed), None)
            if candidate and str(candidate.get("profileId") or "") not in selected_profile_ids:
                mixed_selection.append(candidate)
                selected_profile_ids.add(str(candidate.get("profileId") or ""))
        if max_identities >= 3 and len({str(identity.get("gender") or "") for identity in mixed_selection}) < 2:
            gender_diversity_candidate = next(
                (
                    identity
                    for identity in allowed_identities
                    if str(identity.get("profileId") or "") not in selected_profile_ids
                    and str(identity.get("gender") or "") not in {str(selected.get("gender") or "") for selected in mixed_selection}
                ),
                None,
            )
            if gender_diversity_candidate:
                mixed_selection.append(gender_diversity_candidate)
                selected_profile_ids.add(str(gender_diversity_candidate.get("profileId") or ""))
        for candidate in allowed_identities:
            profile_id = str(candidate.get("profileId") or "")
            if profile_id in selected_profile_ids:
                continue
            mixed_selection.append(candidate)
            selected_profile_ids.add(profile_id)
            if len(mixed_selection) >= max_identities:
                break
        allowed_identities = mixed_selection[:max_identities]
    else:
        allowed_identities = allowed_identities[:max_identities]

    allowed_bucket_keys = sorted(
        {
            (identity["gender"], identity["targetFaceType"], identity["targetLooksLevelBand"])
            for identity in allowed_identities
        }
    )
    return {
        "schemaVersion": "seolleyeon_next_distribution_buckets_v3",
        "maxIdentities": int(max_identities),
        "allowedBuckets": [
            {"gender": gender, "targetFaceType": face_type, "targetLooksLevelBand": looks_band}
            for gender, face_type, looks_band in allowed_bucket_keys
        ],
        "forbiddenBuckets": forbidden_buckets,
        "skippedExhaustedCandidates": skipped_exhausted_candidates,
        "selectedIdentities": allowed_identities,
        "focusedFilters": {
            "faceType": focus_face_type,
            "looksLevelBand": focus_looks_level_band,
            "gender": focus_gender,
            "hasEyewear": focus_has_eyewear,
            "eyewearGroup": focus_eyewear_group,
            "requireEyewearMix": bool(require_eyewear_mix),
        },
        "deficitSets": {
            scope: {dimension: sorted(values) for dimension, values in dimensions.items()}
            for scope, dimensions in deficits.items()
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Select deficit-only distribution buckets for the next Seolleyeon imagegen chunk.")
    parser.add_argument("--root", default=None)
    parser.add_argument("--refresh_audit", action="store_true")
    parser.add_argument("--max_identities", type=int, default=24)
    parser.add_argument("--chunk_identities", dest="max_identities", type=int, default=argparse.SUPPRESS)
    parser.add_argument("--max_attempts", type=int, default=MAX_ATTEMPTS)
    parser.add_argument("--targets_json", default=None, help="Compatibility option; targets are loaded from ai_image/config.")
    parser.add_argument("--audit_json", default=None, help="Compatibility option; latest audit path remains standardized.")
    parser.add_argument("--queue", default=None, help="Compatibility option; imagegen queue path remains standardized.")
    parser.add_argument("--has_eyewear", "--has-eyewear", dest="has_eyewear", default="")
    parser.add_argument("--eyewear_group", "--eyewear-group", dest="eyewear_group", default="")
    parser.add_argument("--require-eyewear-mix", "--require_eyewear_mix", dest="require_eyewear_mix", action="store_true", default=False)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = select_distribution_buckets(
        root=args.root,
        refresh_audit=args.refresh_audit,
        max_identities=args.max_identities,
        max_attempts=args.max_attempts,
        has_eyewear=args.has_eyewear,
        eyewear_group=args.eyewear_group,
        require_eyewear_mix=args.require_eyewear_mix,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
