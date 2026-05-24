from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping

from .config import SHOT_ORDER, ensure_base_dirs, now_utc, pipeline_paths, read_jsonl, to_portable_path, write_csv, write_jsonl
from .distribution_targets import (
    EYEWEAR_BUCKETS,
    FACE_TYPES,
    LOOKS_LEVEL_BANDS,
    SEASONS,
    load_distribution_targets,
    normalize_face_type,
    target_face_type,
    target_looks_level,
    target_looks_level_band,
    validate_distribution_targets,
)
from .approval_evidence import evaluate_approved_identity_evidence
from .retry_plan import APPROVED_STATUSES


DISTRIBUTION_REPORT_FIELDS = (
    "scope",
    "dimension",
    "bucket",
    "target",
    "current",
    "deficit",
    "surplus",
    "exactMatch",
    "updatedAt",
)

CONFIDENCE_THRESHOLD = 0.70
COUNTABLE_LOOKS_BANDS = tuple(band for band in LOOKS_LEVEL_BANDS if band != "4.4-5.0")
VISUAL_DISTRIBUTION_AUDIT_CANDIDATES = (
    "visual_verdict/distribution_audit.json",
    "visual_verdict/latest_distribution_audit.json",
)


def _path_exists(value: Any) -> bool:
    if not value:
        return False
    path = Path(str(value))
    return path.exists() and path.stat().st_size > 0


def _asset_approved(row: Mapping[str, Any]) -> bool:
    final_decision = _normalize_decision(row.get("finalDecision"))
    if final_decision:
        return final_decision == "approved"
    status = str(row.get("status") or "")
    decision = str(row.get("decision") or row.get("visualDecision") or "")
    return decision == "approved" or status in APPROVED_STATUSES


def _as_bool(value: Any, *, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "y", "approved"}


def _as_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _json_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if value in (None, ""):
        return []
    return [str(value)]


def _normalize_decision(value: Any) -> str:
    raw = str(value or "").strip()
    if raw in {"identity_approved", "vision_approved", "qa_approved"}:
        return "approved"
    if raw in {"identity_rejected", "vision_rejected", "qa_rejected"}:
        return "rejected"
    return raw


def group_by_profile(rows: list[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        profile_id = str(row.get("profileId") or "")
        if profile_id:
            grouped[profile_id].append(dict(row))
    return dict(grouped)


def _read_json_records(path: Path, *, visual_key: str | None = None) -> tuple[list[dict[str, Any]], list[str]]:
    if not path.exists():
        return [], []
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        return [], [f"{path.name}:read_error:{exc}"]
    if not text:
        return [], []

    errors: list[str] = []
    records: list[dict[str, Any]] = []

    def add_record(value: Any, source: str) -> None:
        if not isinstance(value, Mapping):
            errors.append(f"{path.name}:{source}:not_object")
            return
        if visual_key and isinstance(value.get(visual_key), list):
            for index, item in enumerate(value[visual_key]):
                if isinstance(item, Mapping):
                    records.append(dict(item))
                else:
                    errors.append(f"{path.name}:{source}.{visual_key}[{index}]:not_object")
            return
        records.append(dict(value))

    if text[0] == "[":
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            return [], [f"{path.name}:invalid_json:{exc.msg}:line{exc.lineno}:col{exc.colno}"]
        if not isinstance(parsed, list):
            return [], [f"{path.name}:array_expected"]
        for index, item in enumerate(parsed):
            add_record(item, f"[{index}]")
        return records, errors

    if text[0] == "{":
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            if exc.msg != "Extra data":
                return [], [f"{path.name}:invalid_json:{exc.msg}:line{exc.lineno}:col{exc.colno}"]
        else:
            add_record(parsed, "object")
            return records, errors

    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            add_record(json.loads(line), f"line{line_number}")
        except json.JSONDecodeError as exc:
            errors.append(f"{path.name}:invalid_json:line{line_number}:col{exc.colno}:{exc.msg}")
    return records, errors


def _latest_by_key(rows: list[Mapping[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        row_key = str(row.get(key) or "")
        if row_key:
            latest[row_key] = dict(row)
    return latest


def _asset_id_for(profile_id: str, shot_type: str) -> str:
    return f"{profile_id}__{shot_type}__v001"


def _asset_shot(row: Mapping[str, Any], profile_id: str) -> str:
    shot = str(row.get("shotType") or "")
    if shot:
        return shot
    asset_id = str(row.get("assetId") or "")
    prefix = f"{profile_id}__"
    if asset_id.startswith(prefix):
        remainder = asset_id[len(prefix) :]
        for candidate in SHOT_ORDER:
            if remainder.startswith(candidate):
                return candidate
    return ""


def _explicit_metadata_mismatch(row: Mapping[str, Any]) -> bool:
    if _as_bool(row.get("metadataMismatch")):
        return True
    if _json_list(row.get("mismatchFields")):
        return True
    return str(row.get("status") or "") == "metadata_mismatch"


def _observed_face(row: Mapping[str, Any]) -> str:
    return normalize_face_type(row.get("observedFaceType") or row.get("visualFaceType") or "")


def _observed_looks(row: Mapping[str, Any]) -> str:
    return str(row.get("observedLooksLevelBand") or row.get("visualLooksLevelBand") or "")


def _confidence(row: Mapping[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        value = _as_float(row.get(key))
        if value is not None:
            return value
    return None


def _bucket_from_rows(
    *,
    dimension: str,
    target_bucket: str,
    identity_row: Mapping[str, Any],
    asset_rows: list[Mapping[str, Any]],
    metadata_mismatch: bool,
) -> tuple[str, bool, list[str]]:
    if dimension == "faceType":
        observed_getter = _observed_face
        confidence_keys = ("faceTypeConfidence", "observedFaceTypeConfidence", "visualFaceTypeConfidence")
        allowed = set(FACE_TYPES)
    else:
        observed_getter = _observed_looks
        confidence_keys = ("looksLevelConfidence", "looksLevelBandConfidence", "observedLooksLevelConfidence")
        allowed = set(LOOKS_LEVEL_BANDS)

    review_rows: list[Mapping[str, Any]] = [identity_row, *asset_rows]
    reasons: list[str] = []
    confidence_available = False
    high_confidence_observed = ""

    for row in review_rows:
        observed = observed_getter(row)
        if observed == "unclear":
            return "", True, [f"{dimension}_unclear"]
        if dimension == "looksLevelBand" and observed == "4.4-5.0":
            return observed, False, reasons
        confidence = _confidence(row, confidence_keys)
        if confidence is None:
            continue
        confidence_available = True
        if observed in allowed and confidence >= CONFIDENCE_THRESHOLD:
            high_confidence_observed = observed
            break

    if high_confidence_observed:
        if target_bucket and target_bucket not in {"unknown", high_confidence_observed}:
            reasons.append(f"{dimension}_observed_target_mismatch")
            return "", True, reasons
        return high_confidence_observed, False, reasons

    if confidence_available:
        return "", True, [f"{dimension}_low_confidence"]

    if not metadata_mismatch and target_bucket and target_bucket != "unknown":
        return target_bucket, False, reasons

    return "", True, [f"{dimension}_missing_bucket"]


def _asset_decision(identity_row: Mapping[str, Any], asset_rows_by_shot: Mapping[str, Mapping[str, Any]], shot: str) -> str:
    asset_row = asset_rows_by_shot.get(shot, {})
    if not asset_row:
        return "missing"
    asset_final_decisions = identity_row.get("assetFinalDecisions")
    if isinstance(asset_final_decisions, Mapping):
        final_from_identity = _normalize_decision(asset_final_decisions.get(shot))
        if final_from_identity:
            return final_from_identity
    asset_decisions = identity_row.get("assetDecisions")
    identity_decision = ""
    if isinstance(asset_decisions, Mapping):
        identity_decision = _normalize_decision(asset_decisions.get(shot))
    asset_decision = _normalize_decision(asset_row.get("finalDecision") or asset_row.get("decision") or asset_row.get("visualDecision") or asset_row.get("status"))
    if asset_decision and asset_decision != "approved":
        return asset_decision
    if identity_decision and identity_decision != "approved":
        return identity_decision
    if asset_decision == "approved" or _asset_approved(asset_row):
        return "approved"
    if identity_decision == "approved":
        return "approved"
    return "missing"


def _identity_anchor(profile_id: str, identity_row: Mapping[str, Any], approved_row: Mapping[str, Any], asset_rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    anchor: dict[str, Any] = {"profileId": profile_id}
    for source in (identity_row, approved_row, *(asset_rows or [])):
        for key in ("gender", "numericId", "targetFaceType", "targetLooksLevel", "targetLooksLevelBand", "identityScope", "isReserve", "reserveStatus"):
            if not anchor.get(key) and source.get(key) not in (None, ""):
                anchor[key] = source.get(key)
        if not anchor.get("targetFaceType") and source.get("faceType") not in (None, ""):
            anchor["targetFaceType"] = source.get("faceType")
        if not anchor.get("targetLooksLevelBand") and source.get("looksLevelBand") not in (None, ""):
            anchor["targetLooksLevelBand"] = source.get("looksLevelBand")
    if not anchor.get("gender") and "_" in profile_id:
        anchor["gender"] = profile_id.split("_", 1)[0]
    if not anchor.get("targetFaceType"):
        anchor["targetFaceType"] = target_face_type(anchor)
    if not anchor.get("targetLooksLevel"):
        anchor["targetLooksLevel"] = target_looks_level(anchor) or ""
    if not anchor.get("targetLooksLevelBand"):
        anchor["targetLooksLevelBand"] = target_looks_level_band(anchor)
    return anchor


def evaluate_identity_from_visual_manifests(
    profile_id: str,
    *,
    identity_row: Mapping[str, Any],
    approved_row: Mapping[str, Any],
    asset_rows: list[Mapping[str, Any]],
) -> dict[str, Any]:
    anchor = _identity_anchor(profile_id, identity_row, approved_row, asset_rows)
    asset_rows_by_shot = {_asset_shot(row, profile_id): row for row in asset_rows if _asset_shot(row, profile_id)}
    asset_decisions = {shot: _asset_decision(identity_row, asset_rows_by_shot, shot) for shot in SHOT_ORDER}
    missing_or_failed_shots = [shot for shot, decision in asset_decisions.items() if decision != "approved"]
    identity_decision = _normalize_decision(
        identity_row.get("finalCompleteIdentityDecision")
        or identity_row.get("completeIdentityDecision")
        or identity_row.get("decision")
        or approved_row.get("finalCompleteIdentityDecision")
        or approved_row.get("completeIdentityDecision")
        or approved_row.get("decision")
    )
    same_identity = _as_bool(identity_row.get("sameIdentity"), default=True)
    counts_toward_distribution = _as_bool(identity_row.get("countsTowardDistribution"), default=False)
    metadata_mismatch = any(_explicit_metadata_mismatch(row) for row in [identity_row, approved_row, *asset_rows])
    target_face = normalize_face_type(anchor.get("targetFaceType") or target_face_type(anchor))
    target_looks = str(anchor.get("targetLooksLevelBand") or target_looks_level_band(anchor))
    face_bucket, face_needs_review, face_reasons = _bucket_from_rows(
        dimension="faceType",
        target_bucket=target_face,
        identity_row=identity_row,
        asset_rows=asset_rows,
        metadata_mismatch=metadata_mismatch,
    )
    looks_bucket, looks_needs_review, looks_reasons = _bucket_from_rows(
        dimension="looksLevelBand",
        target_bucket=target_looks,
        identity_row=identity_row,
        asset_rows=asset_rows,
        metadata_mismatch=metadata_mismatch,
    )

    reasons: list[str] = []
    if identity_decision != "approved":
        reasons.append("identity_not_approved")
    if not same_identity:
        reasons.append("sameIdentity_false")
    if not counts_toward_distribution:
        reasons.append("countsTowardDistribution_not_true")
    if missing_or_failed_shots:
        reasons.append("not_all_shots_approved:" + ",".join(missing_or_failed_shots))
    if metadata_mismatch:
        reasons.append("metadata_mismatch")
    if face_needs_review:
        reasons.extend(face_reasons)
    if looks_needs_review:
        reasons.extend(looks_reasons)
    if looks_bucket == "4.4-5.0" or target_looks == "4.4-5.0":
        reasons.append("over_level_4.4-5.0")

    complete_approved = not reasons
    asset_ids = {
        shot: str(asset_rows_by_shot.get(shot, {}).get("assetId") or _asset_id_for(profile_id, shot))
        for shot in SHOT_ORDER
    }
    final_paths = {
        shot: str(asset_rows_by_shot.get(shot, {}).get("finalPath") or asset_rows_by_shot.get(shot, {}).get("expectedFinalPath") or "")
        for shot in SHOT_ORDER
    }
    return {
        "profileId": profile_id,
        "gender": str(anchor.get("gender") or "unknown"),
        "numericId": str(anchor.get("numericId") or ""),
        "targetFaceType": target_face,
        "observedFaceType": face_bucket or "unclear",
        "countedFaceType": face_bucket,
        "targetLooksLevel": anchor.get("targetLooksLevel", ""),
        "targetLooksLevelBand": target_looks,
        "observedLooksLevelBand": looks_bucket or "unclear",
        "faceType": face_bucket,
        "looksLevelBand": looks_bucket,
        "countedLooksLevelBand": looks_bucket,
        "assetIds": asset_ids,
        "finalPaths": final_paths,
        "identityScope": str(anchor.get("identityScope") or "production"),
        "isReserve": _as_bool(anchor.get("isReserve")),
        "reserveStatus": str(anchor.get("reserveStatus") or ""),
        "completeIdentityDecision": identity_decision or "missing",
        "sameIdentity": same_identity,
        "countsTowardDistribution": counts_toward_distribution,
        "completeApproved": complete_approved,
        "approvedShotCount": sum(1 for decision in asset_decisions.values() if decision == "approved"),
        "assetDecisions": asset_decisions,
        "missingShotTypes": missing_or_failed_shots,
        "metadataMismatch": metadata_mismatch,
        "overLevel": "over_level_4.4-5.0" in reasons,
        "needsReview": face_needs_review or looks_needs_review or any("needs_review" in reason for reason in reasons),
        "rejected": identity_decision == "rejected",
        "reasons": sorted(set(reasons)),
        "updatedAt": now_utc(),
    }


def evaluate_identity(profile_id: str, profile_rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    by_shot = {str(row.get("shotType") or ""): dict(row) for row in profile_rows}
    anchor = by_shot.get("face_card") or (profile_rows[0] if profile_rows else {})
    identity_row = {
        "profileId": profile_id,
        "gender": anchor.get("gender", ""),
        "targetFaceType": target_face_type(anchor),
        "targetLooksLevel": target_looks_level(anchor) or "",
        "targetLooksLevelBand": target_looks_level_band(anchor),
        "completeIdentityDecision": anchor.get("identityDecision") or "",
        "countsTowardDistribution": False,
    }
    asset_rows = [
        {
            "profileId": profile_id,
            "shotType": shot,
            "decision": "approved" if shot in by_shot and _asset_approved(by_shot[shot]) and _path_exists(by_shot[shot].get("finalPath")) else "missing",
            "metadataMismatch": by_shot.get(shot, {}).get("metadataMismatch", False),
        }
        for shot in SHOT_ORDER
    ]
    return evaluate_identity_from_visual_manifests(profile_id, identity_row=identity_row, approved_row={}, asset_rows=asset_rows)


def _bucket_rows(scope: str, dimension: str, targets: Mapping[str, int], counts: Mapping[str, int], order: tuple[str, ...]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for bucket in order:
        target = int(targets.get(bucket, 0))
        current = int(counts.get(bucket, 0))
        rows.append(
            {
                "scope": scope,
                "dimension": dimension,
                "bucket": bucket,
                "target": target,
                "current": current,
                "deficit": max(0, target - current),
                "surplus": max(0, current - target),
                "exactMatch": current == target,
                "updatedAt": now_utc(),
            }
        )
    return rows


def _deficit_map(targets: Mapping[str, int], counts: Mapping[str, int], order: tuple[str, ...]) -> dict[str, int]:
    return {bucket: max(0, int(targets.get(bucket, 0)) - int(counts.get(bucket, 0))) for bucket in order}


def _surplus_map(targets: Mapping[str, int], counts: Mapping[str, int], order: tuple[str, ...]) -> dict[str, int]:
    return {bucket: max(0, int(counts.get(bucket, 0)) - int(targets.get(bucket, 0))) for bucket in order}


def _count_map(counts: Mapping[str, int], order: tuple[str, ...]) -> dict[str, int]:
    return {bucket: int(counts.get(bucket, 0)) for bucket in order}


def _forbidden_buckets(
    *,
    targets: Mapping[str, Any],
    gender_face_deficits: Mapping[str, Mapping[str, int]],
    gender_face_surpluses: Mapping[str, Mapping[str, int]],
    gender_looks_deficits: Mapping[str, Mapping[str, int]],
    gender_looks_surpluses: Mapping[str, Mapping[str, int]],
) -> list[dict[str, Any]]:
    forbidden: list[dict[str, Any]] = []
    for gender in ("female", "male"):
        for face_type in FACE_TYPES:
            if int(gender_face_surpluses[gender].get(face_type, 0)) > 0:
                reason = "surplus"
            elif int(gender_face_deficits[gender].get(face_type, 0)) == 0:
                reason = "quota_full"
            else:
                continue
            forbidden.append({"gender": gender, "faceType": face_type, "looksLevelBand": "any", "reason": reason})
        for band in LOOKS_LEVEL_BANDS:
            if band == "4.4-5.0":
                forbidden.append({"gender": gender, "faceType": "any", "looksLevelBand": band, "reason": "over_level_risk"})
                continue
            if int(gender_looks_surpluses[gender].get(band, 0)) > 0:
                reason = "surplus"
            elif int(gender_looks_deficits[gender].get(band, 0)) == 0:
                reason = "quota_full"
            else:
                continue
            forbidden.append({"gender": gender, "faceType": "any", "looksLevelBand": band, "reason": reason})
    return forbidden


def _next_target_buckets(
    *,
    gender_identity_deficits: Mapping[str, int],
    global_face_deficits: Mapping[str, int],
    gender_face_deficits: Mapping[str, Mapping[str, int]],
    global_looks_deficits: Mapping[str, int],
    gender_looks_deficits: Mapping[str, Mapping[str, int]],
) -> list[dict[str, Any]]:
    buckets: list[dict[str, Any]] = []
    for gender in ("female", "male"):
        gender_deficit = int(gender_identity_deficits.get(gender, 0))
        if gender_deficit <= 0:
            continue
        for face_type in FACE_TYPES:
            face_needed = min(gender_deficit, int(global_face_deficits.get(face_type, 0)), int(gender_face_deficits[gender].get(face_type, 0)))
            if face_needed <= 0:
                continue
            for band in COUNTABLE_LOOKS_BANDS:
                needed = min(face_needed, int(global_looks_deficits.get(band, 0)), int(gender_looks_deficits[gender].get(band, 0)))
                if needed <= 0:
                    continue
                combined = (
                    gender_deficit
                    + int(global_face_deficits.get(face_type, 0))
                    + int(gender_face_deficits[gender].get(face_type, 0))
                    + int(global_looks_deficits.get(band, 0))
                    + int(gender_looks_deficits[gender].get(band, 0))
                )
                priority = "high" if combined >= 20 else ("medium" if combined >= 8 else "low")
                buckets.append(
                    {
                        "gender": gender,
                        "faceType": face_type,
                        "looksLevelBand": band,
                        "neededIdentities": needed,
                        "combinedDeficit": combined,
                        "priority": priority,
                    }
                )
    return sorted(buckets, key=lambda row: (-int(row["combinedDeficit"]), str(row["gender"]), str(row["faceType"]), str(row["looksLevelBand"])))


def _visual_distribution_audit(paths: Any) -> tuple[dict[str, Any] | None, list[str], str]:
    for relative in VISUAL_DISTRIBUTION_AUDIT_CANDIDATES:
        path = paths.reports / relative
        if not path.exists():
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            return None, [f"{relative}:invalid_json:{exc.msg}:line{exc.lineno}:col{exc.colno}"], relative
        if isinstance(value, Mapping) and isinstance(value.get("visualAudit"), Mapping):
            return dict(value["visualAudit"]), [], relative
        if isinstance(value, Mapping):
            return dict(value), [], relative
        return None, [f"{relative}:not_object"], relative
    return None, [], ""


def _dicts_disagree(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    keys = set(left) | set(right)
    for key in keys:
        if _as_int(left.get(key)) != _as_int(right.get(key)):
            return True
    return False


def _visual_disagreements(audit: Mapping[str, Any], visual: Mapping[str, Any] | None) -> list[str]:
    if not visual:
        return []
    checks = (
        ("approvedCompleteIdentityCount", "approvedCompleteIdentityCount"),
        ("approvedCompleteIdentities", "approvedCompleteIdentityCount"),
        ("approvedImageCount", "approvedImageCount"),
        ("approvedImages", "approvedImageCount"),
        ("femaleApprovedIdentityCount", "femaleApprovedIdentityCount"),
        ("femaleApprovedCompleteIdentities", "femaleApprovedIdentityCount"),
        ("maleApprovedIdentityCount", "maleApprovedIdentityCount"),
        ("maleApprovedCompleteIdentities", "maleApprovedIdentityCount"),
    )
    disagreements: list[str] = []
    for visual_key, audit_key in checks:
        if visual_key in visual and _as_int(visual.get(visual_key)) != _as_int(audit.get(audit_key)):
            disagreements.append(visual_key)
    dict_checks = (
        "globalFaceTypeCounts",
        "globalFaceTypeDeficits",
        "globalFaceTypeSurpluses",
        "globalLooksLevelBandCounts",
        "globalLooksLevelBandDeficits",
        "globalLooksLevelBandSurpluses",
    )
    for key in dict_checks:
        if isinstance(visual.get(key), Mapping) and _dicts_disagree(visual[key], audit.get(key, {})):
            disagreements.append(key)
    nested_checks = (
        "genderFaceTypeCounts",
        "genderFaceTypeDeficits",
        "genderFaceTypeSurpluses",
        "genderLooksLevelBandCounts",
        "genderLooksLevelBandDeficits",
        "genderLooksLevelBandSurpluses",
    )
    for key in nested_checks:
        visual_value = visual.get(key)
        audit_value = audit.get(key, {})
        if not isinstance(visual_value, Mapping):
            continue
        for gender in ("female", "male"):
            if isinstance(visual_value.get(gender), Mapping) and _dicts_disagree(visual_value[gender], audit_value.get(gender, {})):
                disagreements.append(f"{key}.{gender}")
    return disagreements


def _manual_flag_is_visual_distribution_only(flag: Path) -> bool:
    if not flag.exists():
        return False
    try:
        payload = json.loads(flag.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - do not clear unknown manual-review prose.
        return False
    if not isinstance(payload, Mapping):
        return False
    fail_conditions = payload.get("failConditions")
    if isinstance(fail_conditions, list) and fail_conditions and all(str(item) == "python_visual_distribution_audit_disagree" for item in fail_conditions):
        return True
    if payload.get("schemaVersion") == "seolleyeon_visual_distribution_audit_apply_v3":
        disagreements = payload.get("disagreements")
        return payload.get("needsManualReview") is True and isinstance(disagreements, list) and bool(disagreements)
    return False


def audit_distribution(*, root: Path | str | None = None, write_outputs: bool = True) -> dict[str, Any]:
    paths = pipeline_paths(root)
    ensure_base_dirs(paths)
    targets = load_distribution_targets(root)
    validate_distribution_targets(targets)

    approved_manifest_rows, approved_errors = _read_json_records(paths.manifests / "approved_identity_manifest.jsonl")
    identity_rows, identity_errors = _read_json_records(paths.manifests / "identity_qa_manifest.jsonl", visual_key="identities")
    asset_rows, asset_errors = _read_json_records(paths.manifests / "asset_qa_manifest.jsonl", visual_key="assets")
    visual_distribution, visual_distribution_errors, visual_distribution_path = _visual_distribution_audit(paths)
    visual_distribution_ignored_reasons: list[str] = []
    if not visual_distribution_path and (paths.reports / "visual_verdict/distribution_audit_apply.json").exists():
        visual_distribution_ignored_reasons.append("visual_distribution_audit_stale_after_identity_reapply")
    visual_json_errors = [*approved_errors, *identity_errors, *asset_errors, *visual_distribution_errors]

    evidence = evaluate_approved_identity_evidence(root)
    approved_by_profile = _latest_by_key(approved_manifest_rows, "profileId")
    identity_by_profile = _latest_by_key(identity_rows, "profileId")
    assets_by_profile = group_by_profile(asset_rows)
    profile_ids = sorted(set(approved_by_profile) | set(identity_by_profile) | set(assets_by_profile))
    visual_identity_evaluations = [
        evaluate_identity_from_visual_manifests(
            profile_id,
            identity_row=identity_by_profile.get(profile_id, {}),
            approved_row=approved_by_profile.get(profile_id, {}),
            asset_rows=assets_by_profile.get(profile_id, []),
        )
        for profile_id in profile_ids
    ]
    identity_evaluations = evidence["evaluatedIdentities"] or visual_identity_evaluations
    approved = [row for row in evidence["validIdentities"] if not row.get("isReserve")]

    gender_counts = Counter(str(row["gender"]) for row in approved)
    face_counts_global = Counter(str(row["countedFaceType"]) for row in approved)
    looks_counts_global = Counter(str(row["countedLooksLevelBand"]) for row in approved)
    eyewear_counts_global = Counter(str(row.get("eyewearBucket") or "without_eyewear") for row in approved)
    season_counts_global = Counter(str(row.get("season") or "") for row in approved)
    face_counts_by_gender = {
        gender: Counter(str(row["countedFaceType"]) for row in approved if row["gender"] == gender)
        for gender in ("female", "male")
    }
    looks_counts_by_gender = {
        gender: Counter(str(row["countedLooksLevelBand"]) for row in approved if row["gender"] == gender)
        for gender in ("female", "male")
    }
    eyewear_counts_by_gender = {
        gender: Counter(str(row.get("eyewearBucket") or "without_eyewear") for row in approved if row["gender"] == gender)
        for gender in ("female", "male")
    }

    report_rows: list[dict[str, Any]] = []
    report_rows.extend(_bucket_rows("global", "faceType", targets["faceTypeTargets"]["global"], face_counts_global, FACE_TYPES))
    report_rows.extend(_bucket_rows("global", "looksLevelBand", targets["looksLevelBandTargets"]["global"], looks_counts_global, LOOKS_LEVEL_BANDS))
    if isinstance(targets.get("eyewearTargets"), Mapping):
        report_rows.extend(_bucket_rows("global", "eyewear", targets["eyewearTargets"]["global"], eyewear_counts_global, EYEWEAR_BUCKETS))
    if isinstance(targets.get("seasonTargets"), Mapping):
        season_targets = targets["seasonTargets"].get("global", targets["seasonTargets"])
        report_rows.extend(_bucket_rows("global", "season", season_targets, season_counts_global, SEASONS))
    for gender in ("female", "male"):
        report_rows.extend(_bucket_rows(gender, "faceType", targets["faceTypeTargets"][gender], face_counts_by_gender[gender], FACE_TYPES))
        report_rows.extend(_bucket_rows(gender, "looksLevelBand", targets["looksLevelBandTargets"][gender], looks_counts_by_gender[gender], LOOKS_LEVEL_BANDS))
        if isinstance(targets.get("eyewearTargets"), Mapping):
            report_rows.extend(_bucket_rows(gender, "eyewear", targets["eyewearTargets"][gender], eyewear_counts_by_gender[gender], EYEWEAR_BUCKETS))

    final_target = targets["finalTarget"]
    approved_complete_count = len(approved)
    approved_image_count = approved_complete_count * int(final_target["shotsPerIdentity"])
    count_checks = {
        "approvedCompleteIdentities": {
            "target": int(final_target["approvedCompleteIdentities"]),
            "current": approved_complete_count,
        },
        "approvedImages": {
            "target": int(final_target["approvedImages"]),
            "current": approved_image_count,
        },
        "femaleApprovedIdentities": {
            "target": int(final_target["femaleApprovedIdentities"]),
            "current": int(gender_counts.get("female", 0)),
        },
        "maleApprovedIdentities": {
            "target": int(final_target["maleApprovedIdentities"]),
            "current": int(gender_counts.get("male", 0)),
        },
    }
    for check in count_checks.values():
        check["deficit"] = max(0, int(check["target"]) - int(check["current"]))
        check["surplus"] = max(0, int(check["current"]) - int(check["target"]))
        check["exactMatch"] = int(check["target"]) == int(check["current"])

    global_face_counts = _count_map(face_counts_global, FACE_TYPES)
    global_face_deficits = _deficit_map(targets["faceTypeTargets"]["global"], face_counts_global, FACE_TYPES)
    global_face_surpluses = _surplus_map(targets["faceTypeTargets"]["global"], face_counts_global, FACE_TYPES)
    gender_face_counts = {gender: _count_map(face_counts_by_gender[gender], FACE_TYPES) for gender in ("female", "male")}
    gender_face_deficits = {
        gender: _deficit_map(targets["faceTypeTargets"][gender], face_counts_by_gender[gender], FACE_TYPES)
        for gender in ("female", "male")
    }
    gender_face_surpluses = {
        gender: _surplus_map(targets["faceTypeTargets"][gender], face_counts_by_gender[gender], FACE_TYPES)
        for gender in ("female", "male")
    }
    global_looks_counts = _count_map(looks_counts_global, LOOKS_LEVEL_BANDS)
    global_looks_deficits = _deficit_map(targets["looksLevelBandTargets"]["global"], looks_counts_global, LOOKS_LEVEL_BANDS)
    global_looks_surpluses = _surplus_map(targets["looksLevelBandTargets"]["global"], looks_counts_global, LOOKS_LEVEL_BANDS)
    gender_looks_counts = {gender: _count_map(looks_counts_by_gender[gender], LOOKS_LEVEL_BANDS) for gender in ("female", "male")}
    gender_looks_deficits = {
        gender: _deficit_map(targets["looksLevelBandTargets"][gender], looks_counts_by_gender[gender], LOOKS_LEVEL_BANDS)
        for gender in ("female", "male")
    }
    gender_looks_surpluses = {
        gender: _surplus_map(targets["looksLevelBandTargets"][gender], looks_counts_by_gender[gender], LOOKS_LEVEL_BANDS)
        for gender in ("female", "male")
    }
    if isinstance(targets.get("eyewearTargets"), Mapping):
        global_eyewear_counts = _count_map(eyewear_counts_global, EYEWEAR_BUCKETS)
        global_eyewear_deficits = _deficit_map(targets["eyewearTargets"]["global"], eyewear_counts_global, EYEWEAR_BUCKETS)
        global_eyewear_surpluses = _surplus_map(targets["eyewearTargets"]["global"], eyewear_counts_global, EYEWEAR_BUCKETS)
        gender_eyewear_counts = {gender: _count_map(eyewear_counts_by_gender[gender], EYEWEAR_BUCKETS) for gender in ("female", "male")}
        gender_eyewear_deficits = {
            gender: _deficit_map(targets["eyewearTargets"][gender], eyewear_counts_by_gender[gender], EYEWEAR_BUCKETS)
            for gender in ("female", "male")
        }
        gender_eyewear_surpluses = {
            gender: _surplus_map(targets["eyewearTargets"][gender], eyewear_counts_by_gender[gender], EYEWEAR_BUCKETS)
            for gender in ("female", "male")
        }
    else:
        global_eyewear_counts = {}
        global_eyewear_deficits = {}
        global_eyewear_surpluses = {}
        gender_eyewear_counts = {}
        gender_eyewear_deficits = {}
        gender_eyewear_surpluses = {}
    if isinstance(targets.get("seasonTargets"), Mapping):
        season_targets = targets["seasonTargets"].get("global", targets["seasonTargets"])
        global_season_counts = _count_map(season_counts_global, SEASONS)
        global_season_deficits = _deficit_map(season_targets, season_counts_global, SEASONS)
        global_season_surpluses = _surplus_map(season_targets, season_counts_global, SEASONS)
    else:
        global_season_counts = {}
        global_season_deficits = {}
        global_season_surpluses = {}

    gender_identity_deficits = {
        "female": max(0, int(final_target["femaleApprovedIdentities"]) - int(gender_counts.get("female", 0))),
        "male": max(0, int(final_target["maleApprovedIdentities"]) - int(gender_counts.get("male", 0))),
    }
    forbidden_buckets = _forbidden_buckets(
        targets=targets,
        gender_face_deficits=gender_face_deficits,
        gender_face_surpluses=gender_face_surpluses,
        gender_looks_deficits=gender_looks_deficits,
        gender_looks_surpluses=gender_looks_surpluses,
    )
    next_target_buckets = _next_target_buckets(
        gender_identity_deficits=gender_identity_deficits,
        global_face_deficits=global_face_deficits,
        gender_face_deficits=gender_face_deficits,
        global_looks_deficits=global_looks_deficits,
        gender_looks_deficits=gender_looks_deficits,
    )

    over_level_identities = [
        row
        for row in identity_evaluations
        if row["completeIdentityDecision"] == "approved"
        and row["countsTowardDistribution"]
        and row["approvedShotCount"] == len(SHOT_ORDER)
        and (row["observedLooksLevelBand"] == "4.4-5.0" or row["targetLooksLevelBand"] == "4.4-5.0")
    ]
    counted_without_three_shots = [row for row in approved if row["approvedShotCount"] != len(SHOT_ORDER)]
    exact_distribution = all(bool(row["exactMatch"]) for row in report_rows)
    exact_counts = all(bool(check["exactMatch"]) for check in count_checks.values())

    preliminary_audit = {
        "approvedCompleteIdentityCount": approved_complete_count,
        "approvedImageCount": approved_image_count,
        "femaleApprovedIdentityCount": int(gender_counts.get("female", 0)),
        "maleApprovedIdentityCount": int(gender_counts.get("male", 0)),
        "globalFaceTypeCounts": global_face_counts,
        "globalFaceTypeDeficits": global_face_deficits,
        "globalFaceTypeSurpluses": global_face_surpluses,
        "genderFaceTypeCounts": gender_face_counts,
        "genderFaceTypeDeficits": gender_face_deficits,
        "genderFaceTypeSurpluses": gender_face_surpluses,
        "globalLooksLevelBandCounts": global_looks_counts,
        "globalLooksLevelBandDeficits": global_looks_deficits,
        "globalLooksLevelBandSurpluses": global_looks_surpluses,
        "genderLooksLevelBandCounts": gender_looks_counts,
        "genderLooksLevelBandDeficits": gender_looks_deficits,
        "genderLooksLevelBandSurpluses": gender_looks_surpluses,
        "globalEyewearCounts": global_eyewear_counts,
        "globalEyewearDeficits": global_eyewear_deficits,
        "globalEyewearSurpluses": global_eyewear_surpluses,
        "genderEyewearCounts": gender_eyewear_counts,
        "genderEyewearDeficits": gender_eyewear_deficits,
        "genderEyewearSurpluses": gender_eyewear_surpluses,
        "globalSeasonCounts": global_season_counts,
        "globalSeasonDeficits": global_season_deficits,
        "globalSeasonSurpluses": global_season_surpluses,
    }
    visual_disagreements = _visual_disagreements(preliminary_audit, visual_distribution)

    fail_conditions: list[str] = []
    if any(int(row["surplus"]) > 0 for row in report_rows):
        fail_conditions.append("bucket_surplus")
    if over_level_identities:
        fail_conditions.append("approved_4.4-5.0_identity")
    if approved_complete_count > int(final_target["approvedCompleteIdentities"]):
        fail_conditions.append("approvedCompleteIdentityCount_over_target")
    if int(gender_counts.get("female", 0)) > int(final_target["femaleApprovedIdentities"]):
        fail_conditions.append("femaleApprovedIdentityCount_over_target")
    if int(gender_counts.get("male", 0)) > int(final_target["maleApprovedIdentities"]):
        fail_conditions.append("maleApprovedIdentityCount_over_target")
    if counted_without_three_shots:
        fail_conditions.append("identity_counted_without_3_approved_shots")
    if evidence["invalidApprovedIdentities"] or evidence["invalidApprovedAssets"]:
        fail_conditions.append("approved_manifest_missing_file_backing")
    if visual_json_errors:
        fail_conditions.append("visual_verdict_json_invalid")
    if visual_disagreements:
        fail_conditions.append("python_visual_distribution_audit_disagree")

    passed = exact_distribution and exact_counts and not fail_conditions
    if passed:
        final_decision = "approved"
    elif visual_json_errors or visual_disagreements or any(condition in fail_conditions for condition in ("bucket_surplus", "approved_4.4-5.0_identity", "approved_manifest_missing_file_backing")):
        final_decision = "needs_manual_review"
    elif any(int(row["deficit"]) > 0 for row in report_rows) or any(int(check["deficit"]) > 0 for check in count_checks.values()):
        final_decision = "needs_more_generation"
    else:
        final_decision = "rejected"

    audit = {
        "schemaVersion": "seolleyeon_ai_image_distribution_audit_v3",
        "targetsPath": to_portable_path(paths.ai_image / "config" / "AI_IMAGE_DISTRIBUTION_TARGETS_V3.json"),
        "countingUnit": "identity",
        **preliminary_audit,
        "approvedCompleteIdentities": approved_complete_count,
        "approvedImages": approved_image_count,
        "femaleApprovedCompleteIdentities": int(gender_counts.get("female", 0)),
        "maleApprovedCompleteIdentities": int(gender_counts.get("male", 0)),
        "countChecks": count_checks,
        "bucketChecks": report_rows,
        "forbiddenBuckets": forbidden_buckets,
        "nextTargetBuckets": next_target_buckets,
        "overLevelApprovedIdentities": over_level_identities,
        "needsReviewIdentities": [row for row in identity_evaluations if row["needsReview"] or "countsTowardDistribution_not_true" in row["reasons"]],
        "metadataMismatchIdentities": [row for row in identity_evaluations if row["metadataMismatch"]],
        "rejectedIdentities": [row for row in identity_evaluations if row["rejected"]],
        "countedWithoutThreeApprovedShots": counted_without_three_shots,
        "approvedIdentities": approved,
        "evaluatedIdentities": identity_evaluations,
        "visualEvaluatedIdentities": visual_identity_evaluations,
        "invalidApprovedIdentities": evidence["invalidApprovedIdentities"],
        "invalidApprovedAssets": evidence["invalidApprovedAssets"],
        "approvedManifestRows": evidence["approvedManifestRows"],
        "approvedManifestRowsExcluded": len(evidence["invalidApprovedIdentities"]),
        "visualDistributionAuditPath": visual_distribution_path,
        "visualDistributionAuditDisagreements": visual_disagreements,
        "visualDistributionAuditIgnoredReasons": visual_distribution_ignored_reasons,
        "visualJsonErrors": visual_json_errors,
        "failConditions": sorted(set(fail_conditions)),
        "exactDistributionMatch": exact_distribution,
        "exactFinalCountMatch": exact_counts,
        "finalDecision": final_decision,
        "passed": passed,
        "updatedAt": now_utc(),
    }
    if write_outputs:
        (paths.reports / "distribution_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
        (paths.reports / "latest_distribution_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
        write_csv(paths.reports / "distribution_report.csv", report_rows, DISTRIBUTION_REPORT_FIELDS)
        destructive_approved_wipe_blocked = bool(approved_manifest_rows) and not approved
        if destructive_approved_wipe_blocked:
            audit["manifestWriteGuards"] = {
                "approvedIdentityManifestPreserved": True,
                "reason": "computed_zero_approved_from_nonempty_manifest",
                "previousApprovedIdentityRows": len(approved_manifest_rows),
            }
            (paths.reports / "distribution_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
            (paths.reports / "latest_distribution_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            write_jsonl(paths.manifests / "approved_identity_manifest.jsonl", approved)
        rejected_by_profile = _latest_by_key(read_jsonl(paths.manifests / "rejected_identity_manifest.jsonl"), "profileId")
        for row in identity_evaluations:
            if row["rejected"]:
                profile_id = str(row.get("profileId") or "")
                if profile_id:
                    rejected_by_profile[profile_id] = row
        write_jsonl(paths.manifests / "rejected_identity_manifest.jsonl", [rejected_by_profile[key] for key in sorted(rejected_by_profile)])
        write_jsonl(paths.manifests / "reserve_identity_manifest.jsonl", [row for row in identity_evaluations if row["isReserve"]])
    flag = paths.manifests / "manual_review_required.flag"
    if write_outputs and (visual_json_errors or visual_disagreements):
        flag.write_text(json.dumps({"failConditions": audit["failConditions"], "visualJsonErrors": visual_json_errors, "visualDistributionAuditDisagreements": visual_disagreements}, ensure_ascii=False, indent=2), encoding="utf-8")
    elif write_outputs and flag.exists():
        try:
            payload = json.loads(flag.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {}
        stale_reasons = set(payload.get("failConditions") or []) | set(payload.get("failureReasons") or [])
        if stale_reasons and stale_reasons <= {"python_visual_distribution_audit_disagree", "visual_verdict_json_invalid"}:
            flag.unlink()
    return audit


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit Seolleyeon AI profile distribution against exact v3 targets.")
    parser.add_argument("--root", default=None)
    parser.add_argument("--targets_json", default=None, help="Compatibility option; targets are loaded from ai_image/config.")
    parser.add_argument("--identity_manifest", default=None, help="Compatibility option; identity QA manifest path remains standardized.")
    parser.add_argument("--asset_qa_manifest", default=None, help="Compatibility option; asset QA manifest path remains standardized.")
    parser.add_argument("--out_dir", default=None, help="Compatibility option; reports are written under ai_image/reports.")
    parser.add_argument("--read-only", "--read_only", dest="read_only", action="store_true", help="Compute without writing reports or manifest updates.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    audit = audit_distribution(root=args.root, write_outputs=not args.read_only)
    print(
        json.dumps(
            {
                "passed": audit["passed"],
                "finalDecision": audit["finalDecision"],
                "approvedCompleteIdentityCount": audit["approvedCompleteIdentityCount"],
                "failConditions": audit["failConditions"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0
