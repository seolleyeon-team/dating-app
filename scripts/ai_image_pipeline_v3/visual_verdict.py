from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from .config import SHOT_ORDER, ensure_base_dirs, now_utc, pipeline_paths, profile_number, read_jsonl, to_portable_path, write_jsonl
from .approval_evidence import resolve_file_qa_evidence
from .distribution_audit import audit_distribution
from .distribution_targets import normalize_face_type, target_face_type, target_looks_level_band
from .manifest import load_generation_manifest, write_generation_outputs


ASSET_QA_TYPE = "seolleyeon_visual_verdict_asset_v3"
IDENTITY_QA_TYPE = "seolleyeon_visual_verdict_identity_v3"
DISTRIBUTION_QA_TYPE = "seolleyeon_visual_verdict_distribution_v3"
CONFIDENCE_THRESHOLD = 0.70

ASSET_REQUIRED_KEYS = {
    "assetId",
    "profileId",
    "gender",
    "shotType",
    "targetFaceType",
    "observedFaceType",
    "targetLooksLevelBand",
    "observedLooksLevelBand",
    "adultVisual",
    "photoRealism",
    "brandFit",
    "shotTypeReadable",
    "metadataMismatch",
    "decision",
}
IDENTITY_REQUIRED_KEYS = {
    "profileId",
    "gender",
    "targetFaceType",
    "observedFaceType",
    "targetLooksLevelBand",
    "observedLooksLevelBand",
    "assetIds",
    "assetDecisions",
    "faceToSilhouetteConsistency",
    "faceToVibeConsistency",
    "sameIdentity",
    "completeIdentityDecision",
    "countsTowardDistribution",
}
VALID_DECISIONS = {"approved", "needs_review", "rejected"}


def asset_qa_manifest_path(root: Path | str | None = None, out_manifest: Path | str | None = None) -> Path:
    return Path(out_manifest).resolve() if out_manifest else pipeline_paths(root).manifests / "asset_qa_manifest.jsonl"


def identity_qa_manifest_path(root: Path | str | None = None, out_manifest: Path | str | None = None) -> Path:
    return Path(out_manifest).resolve() if out_manifest else pipeline_paths(root).manifests / "identity_qa_manifest.jsonl"


def _json_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if value in (None, ""):
        return []
    return [str(value)]


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


def _normalize_decision(value: Any) -> str:
    decision = str(value or "").strip()
    if decision in {"vision_approved", "identity_approved", "qa_approved", "file_passed"}:
        return "approved"
    if decision in {"vision_rejected", "identity_rejected", "qa_rejected", "file_rejected"}:
        return "rejected"
    if decision in {"", "missing", "file_needs_review"}:
        return "needs_review"
    if decision not in VALID_DECISIONS:
        return "needs_review"
    return decision


def _status_from_decision(decision: str, *, identity: bool = False) -> str:
    prefix = "identity" if identity else "vision"
    return f"{prefix}_{_normalize_decision(decision)}"


def _safe_numeric_id(profile_id: Any) -> str | None:
    try:
        return profile_number(str(profile_id))
    except ValueError:
        return None


def _read_json_payload(path: Path) -> Any:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        if text[:1] in {"[", "{"}:
            raise
        rows: list[dict[str, Any]] = []
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as line_exc:
                raise ValueError(f"invalid JSONL line {line_number}: {line_exc.msg}") from line_exc
            if not isinstance(row, Mapping):
                raise ValueError(f"invalid JSONL line {line_number}: object expected")
            rows.append(dict(row))
        return rows


def _load_visual_items(
    input_path: str | None,
    *,
    expected_qa_type: str,
    item_key: str | None,
    allow_empty: bool = False,
    legacy_jsonl: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None, Path]:
    if not input_path:
        raise ValueError("Visual verdict input path is required.")
    path = Path(input_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Visual verdict input does not exist: {path}")
    payload = _read_json_payload(path)

    if isinstance(payload, Mapping):
        top_level = dict(payload)
        qa_type = str(top_level.get("qaType") or "")
        if qa_type != expected_qa_type:
            raise ValueError(f"Unexpected qaType: {qa_type or '<missing>'}")
        checked_value = top_level.get("checked")
        summary = top_level.get("summary") if isinstance(top_level.get("summary"), Mapping) else {}
        if checked_value is None:
            checked_value = summary.get("checked")
        if checked_value is not None and not allow_empty:
            try:
                if int(checked_value) <= 0:
                    raise ValueError("visual-verdict input has checked:0")
            except (TypeError, ValueError) as exc:
                if isinstance(exc, ValueError) and str(exc) == "visual-verdict input has checked:0":
                    raise
        if item_key is None:
            return [top_level], top_level, path
        items = top_level.get(item_key)
        if not isinstance(items, list):
            raise ValueError(f"{expected_qa_type} requires {item_key}[]")
        rows = [dict(item) for item in items if isinstance(item, Mapping)]
        if len(rows) != len(items):
            raise ValueError(f"{item_key}[] must contain only objects")
        if not rows and not allow_empty:
            raise ValueError(f"{item_key}[] is empty")
        return rows, top_level, path

    if isinstance(payload, list) and legacy_jsonl:
        rows = [dict(item) for item in payload if isinstance(item, Mapping)]
        if len(rows) != len(payload):
            raise ValueError("legacy visual-verdict input must contain only objects")
        if not rows and not allow_empty:
            raise ValueError("legacy visual-verdict input is empty")
        return rows, None, path

    if isinstance(payload, list):
        raise ValueError("legacy JSONL/list input requires --legacy_jsonl")
    raise ValueError("visual-verdict input must be a JSON object")


def _require_keys(row: Mapping[str, Any], required: set[str], label: str) -> None:
    missing = sorted(key for key in required if key not in row)
    if missing:
        raise ValueError(f"{label} missing required fields: {', '.join(missing)}")


def _history_path(root: Path | str | None, filename: str) -> Path:
    return pipeline_paths(root).reports / "visual_verdict" / filename


def _append_history(root: Path | str | None, filename: str, rows: list[Mapping[str, Any]]) -> None:
    if not rows:
        return
    path = _history_path(root, filename)
    history = read_jsonl(path)
    history.extend(dict(row) for row in rows)
    write_jsonl(path, history)


def _latest_by_key(rows: list[Mapping[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        row_key = str(row.get(key) or "")
        if row_key:
            out[row_key] = dict(row)
    return out


def _asset_hard_reject_reasons(review: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    if review.get("adultVisual") is False:
        reasons.append("adultVisual_false")
    for key, threshold in (
        ("childlikeRisk", 2.0),
        ("schoolUniformRisk", 1.0),
        ("sexualizationRisk", 1.0),
        ("artifactRisk", 3.0),
    ):
        value = _as_float(review.get(key))
        if value is not None and value >= threshold:
            reasons.append(f"{key}_gte_{threshold:g}")
    for key, threshold in (("photoRealism", 4.0), ("brandFit", 4.0)):
        value = _as_float(review.get(key))
        if value is not None and value < threshold:
            reasons.append(f"{key}_lt_{threshold:g}")
    if review.get("shotTypeReadable") is False:
        reasons.append("shotTypeReadable_false")
    if str(review.get("observedLooksLevelBand") or "") == "4.4-5.0":
        reasons.append("over_level_4.4-5.0")
    reasons.extend(_eyewear_hard_reject_reasons(review))
    return reasons


def _normalized_mismatch_fields(fields: Any) -> set[str]:
    mapping = {
        "targetFaceType": "faceType",
        "observedFaceType": "faceType",
        "targetLooksLevelBand": "looksLevelBand",
        "observedLooksLevelBand": "looksLevelBand",
        "targetHasEyewear": "eyewear",
        "observedHasEyewear": "eyewear",
        "targetEyewearGroup": "eyewear",
        "observedEyewearGroup": "eyewear",
        "targetEyewear": "eyewear",
        "observedEyewear": "eyewear",
        "targetShotEyewearExpected": "eyewear",
        "eyewearMismatch": "eyewear",
    }
    return {mapping.get(field, field) for field in _json_list(fields)}


def _target_eyewear_expected(asset: Mapping[str, Any]) -> str:
    expected = str(asset.get("targetShotEyewearExpected") or asset.get("shotEyewearExpected") or asset.get("canonicalEyewear") or asset.get("eyewear") or "none").strip()
    return expected or "none"


def _target_has_eyewear(asset: Mapping[str, Any]) -> bool:
    if "targetHasEyewear" in asset:
        return _as_bool(asset.get("targetHasEyewear"))
    expected = _target_eyewear_expected(asset)
    if expected != "none":
        return True
    return _as_bool(asset.get("hasEyewear")) or str(asset.get("eyewearGroup") or "") == "glasses"


def _target_eyewear_group(asset: Mapping[str, Any]) -> str:
    group = str(asset.get("targetEyewearGroup") or asset.get("eyewearGroup") or "").strip()
    if group:
        return group
    return "glasses" if _target_has_eyewear(asset) else "none"


def _temporary_eyewear_allowed(asset: Mapping[str, Any]) -> bool:
    return _as_bool(asset.get("temporaryEyewearAllowed")) or _as_bool(asset.get("temporaryEyewearApplied"))


def _observed_has_eyewear(review: Mapping[str, Any]) -> bool | None:
    if "observedHasEyewear" not in review:
        return None
    if review.get("observedHasEyewear") in (None, ""):
        return None
    return _as_bool(review.get("observedHasEyewear"))


def _observed_eyewear_group(review: Mapping[str, Any]) -> str:
    return str(review.get("observedEyewearGroup") or "").strip()


def _eyewear_hard_reject_reasons(review: Mapping[str, Any]) -> list[str]:
    observed_values = " ".join(
        str(review.get(key) or "")
        for key in ("observedEyewearGroup", "observedEyewear", "eyewearMismatchReason")
    ).lower()
    reasons: list[str] = []
    if "sunglasses" in observed_values:
        reasons.append("eyewear_sunglasses")
    if "tinted" in observed_values:
        reasons.append("eyewear_tinted_lenses")
    if "face-covering mask" in observed_values or "face covering mask" in observed_values:
        reasons.append("face_covering_mask")
    return sorted(set(reasons))


def _eyewear_mismatch(
    *,
    review: Mapping[str, Any],
    generation_asset: Mapping[str, Any],
) -> tuple[bool, list[str], list[str]]:
    fields: set[str] = set()
    reasons: list[str] = []
    observed_has = _observed_has_eyewear(review)
    observed_group = _observed_eyewear_group(review)
    target_has = _target_has_eyewear(generation_asset)
    target_group = _target_eyewear_group(generation_asset)
    target_expected = _target_eyewear_expected(generation_asset)
    temporary_allowed = _temporary_eyewear_allowed(generation_asset)
    mismatch = _as_bool(review.get("eyewearMismatch"))

    if _as_bool(review.get("eyewearReadable"), default=True) is False:
        reasons.append("eyewear_not_readable")
    if observed_has is None:
        return mismatch, sorted(fields), sorted(set(reasons))
    if target_has and not observed_has:
        mismatch = True
        fields.add("eyewear")
        reasons.append("required_eyewear_missing")
    if target_has and observed_has:
        if observed_group and observed_group not in {"glasses", "unclear"}:
            mismatch = True
            fields.add("eyewear")
            reasons.append(f"unexpected_eyewear_group:{observed_group}")
        observed_eyewear = str(review.get("observedEyewear") or "").strip()
        if observed_eyewear and observed_eyewear not in {"unclear", "other", target_expected}:
            mismatch = True
            fields.add("eyewear")
            reasons.append("different_eyewear_frame")
    if not target_has and observed_has and not temporary_allowed:
        mismatch = True
        fields.add("eyewear")
        reasons.append("unexpected_eyewear_present")
    if target_group == "none" and observed_group == "glasses" and not temporary_allowed:
        mismatch = True
        fields.add("eyewear")
        reasons.append("unexpected_eyewear_group:glasses")
    if review.get("eyewearMismatchReason"):
        reasons.append(str(review.get("eyewearMismatchReason")))
    return mismatch, sorted(fields), sorted(set(reasons))


def _asset_mismatch(
    *,
    review: Mapping[str, Any],
    generation_asset: Mapping[str, Any],
    target_face: str,
    observed_face: str,
    target_looks: str,
    observed_looks: str,
) -> tuple[bool, list[str]]:
    fields = _normalized_mismatch_fields(review.get("mismatchFields"))
    mismatch = _as_bool(review.get("metadataMismatch")) or bool(fields)
    face_confidence = _as_float(review.get("faceTypeConfidence"))
    if observed_face != "unclear" and face_confidence is not None and face_confidence >= CONFIDENCE_THRESHOLD and target_face and target_face != observed_face:
        mismatch = True
        fields.add("faceType")
    looks_confidence = _as_float(review.get("looksLevelConfidence"))
    if observed_looks != "unclear" and looks_confidence is not None and looks_confidence >= CONFIDENCE_THRESHOLD and target_looks and target_looks != observed_looks:
        mismatch = True
        fields.add("looksLevelBand")
    if str(review.get("gender") or "") == "unknown":
        fields.add("gender")
    elif generation_asset.get("gender") and str(review.get("gender") or "") != str(generation_asset.get("gender") or ""):
        mismatch = True
        fields.add("gender")
    if str(review.get("shotType") or "") == "unknown":
        fields.add("shotType")
    elif generation_asset.get("shotType") and str(review.get("shotType") or "") != str(generation_asset.get("shotType") or ""):
        mismatch = True
        fields.add("shotType")
    eyewear_mismatch, eyewear_fields, _eyewear_reasons = _eyewear_mismatch(review=review, generation_asset=generation_asset)
    if eyewear_mismatch:
        mismatch = True
        fields.update(eyewear_fields or ["eyewear"])
    shot_type = str(generation_asset.get("shotType") or review.get("shotType") or "")
    if shot_type != "vibe_card" and fields == {"locationType"}:
        # The identity-level manifest stores the vibe_card locationType for distribution/audit.
        # face_card and silhouette_card may intentionally use neutral fallback scenes, so a
        # visual-QA locationType-only note must not reject otherwise valid non-vibe assets.
        fields.discard("locationType")
        mismatch = False
    return mismatch, sorted(fields)


def _asset_record(
    review: Mapping[str, Any],
    *,
    generation_asset: Mapping[str, Any],
    sheet_id: str,
    source_json: Path,
    applied_at: str,
) -> dict[str, Any]:
    _require_keys(review, ASSET_REQUIRED_KEYS, "asset")
    asset_id = str(review.get("assetId") or "")
    if not generation_asset:
        raise ValueError(f"Unknown assetId in asset QA payload: {asset_id}")
    for key in ("assetId", "profileId", "gender", "shotType"):
        expected = str(generation_asset.get(key) or "")
        observed = str(review.get(key) or "")
        if expected and observed and observed != "unknown" and expected != observed:
            raise ValueError(f"Asset QA {asset_id} {key} mismatch: expected {expected}, got {observed}")

    source_target_face = normalize_face_type(generation_asset.get("targetFaceType") or target_face_type(generation_asset))
    returned_target_face = normalize_face_type(review.get("targetFaceType") or "")
    if source_target_face and source_target_face != "unknown":
        if not returned_target_face or returned_target_face == "unknown":
            raise ValueError(f"visual_qa_target_metadata_unknown: {asset_id} targetFaceType expected {source_target_face}")
        if returned_target_face != source_target_face:
            raise ValueError(f"visual_qa_target_metadata_mismatch: {asset_id} targetFaceType expected {source_target_face}, got {returned_target_face}")
    source_target_looks = str(generation_asset.get("targetLooksLevelBand") or target_looks_level_band(generation_asset) or "").strip()
    returned_target_looks = str(review.get("targetLooksLevelBand") or "").strip()
    if source_target_looks and source_target_looks != "unknown":
        if not returned_target_looks or returned_target_looks == "unknown":
            raise ValueError(f"visual_qa_target_metadata_unknown: {asset_id} targetLooksLevelBand expected {source_target_looks}")
        if returned_target_looks != source_target_looks:
            raise ValueError(f"visual_qa_target_metadata_mismatch: {asset_id} targetLooksLevelBand expected {source_target_looks}, got {returned_target_looks}")
    profile_id = str(review.get("profileId") or generation_asset.get("profileId") or "")
    numeric_id = _safe_numeric_id(profile_id)
    target_face = normalize_face_type(review.get("targetFaceType") or generation_asset.get("targetFaceType") or target_face_type(generation_asset))
    observed_face = normalize_face_type(review.get("observedFaceType") or "unclear")
    target_looks = str(review.get("targetLooksLevelBand") or generation_asset.get("targetLooksLevelBand") or target_looks_level_band(generation_asset) or "unknown")
    observed_looks = str(review.get("observedLooksLevelBand") or "unclear")
    original_decision = _normalize_decision(review.get("decision"))
    hard_reject_reasons = _asset_hard_reject_reasons(review)
    eyewear_mismatch, eyewear_mismatch_fields, eyewear_reasons = _eyewear_mismatch(review=review, generation_asset=generation_asset)
    metadata_mismatch, mismatch_fields = _asset_mismatch(
        review=review,
        generation_asset=generation_asset,
        target_face=target_face,
        observed_face=observed_face,
        target_looks=target_looks,
        observed_looks=observed_looks,
    )
    if eyewear_mismatch:
        metadata_mismatch = True
        mismatch_fields = sorted(set([*mismatch_fields, *(eyewear_mismatch_fields or ["eyewear"])]))

    needs_review_reasons: list[str] = []
    if observed_face == "unclear":
        needs_review_reasons.append("observedFaceType_unclear")
    if observed_looks == "unclear":
        needs_review_reasons.append("observedLooksLevelBand_unclear")
    if str(review.get("gender") or "") == "unknown":
        needs_review_reasons.append("gender_unknown")
    if str(review.get("shotType") or "") == "unknown":
        needs_review_reasons.append("shotType_unknown")
    if numeric_id is None:
        needs_review_reasons.append("numericId_unparseable")
    if metadata_mismatch:
        needs_review_reasons.append("metadata_mismatch")
    needs_review_reasons.extend(eyewear_reasons)

    if hard_reject_reasons:
        final_decision = "rejected"
    elif original_decision == "rejected":
        final_decision = "rejected"
    elif original_decision == "needs_review" or needs_review_reasons:
        final_decision = "needs_review"
    else:
        final_decision = "approved"

    reject_reasons = sorted(set([*_json_list(review.get("rejectReasons")), *hard_reject_reasons]))
    return {
        "schemaVersion": "seolleyeon_asset_qa_manifest_v3",
        "assetId": asset_id,
        "profileId": profile_id,
        "gender": str(review.get("gender") or generation_asset.get("gender") or "unknown"),
        "numericId": numeric_id,
        "shotType": str(review.get("shotType") or generation_asset.get("shotType") or "unknown"),
        "targetFaceType": target_face or "unknown",
        "observedFaceType": observed_face or "unclear",
        "faceTypeConfidence": _as_float(review.get("faceTypeConfidence")) if _as_float(review.get("faceTypeConfidence")) is not None else 0.0,
        "targetLooksLevelBand": target_looks,
        "observedLooksLevelBand": observed_looks,
        "looksLevelConfidence": _as_float(review.get("looksLevelConfidence")) if _as_float(review.get("looksLevelConfidence")) is not None else 0.0,
        "targetHasEyewear": _target_has_eyewear(generation_asset),
        "targetEyewearGroup": _target_eyewear_group(generation_asset),
        "targetEyewear": str(generation_asset.get("targetEyewear") or generation_asset.get("eyewear") or _target_eyewear_expected(generation_asset)),
        "targetCanonicalEyewear": str(generation_asset.get("targetCanonicalEyewear") or generation_asset.get("canonicalEyewear") or _target_eyewear_expected(generation_asset)),
        "targetShotEyewearExpected": _target_eyewear_expected(generation_asset),
        "observedHasEyewear": _observed_has_eyewear(review),
        "observedEyewearGroup": _observed_eyewear_group(review) or ("unclear" if _observed_has_eyewear(review) is None else "none"),
        "observedEyewear": str(review.get("observedEyewear") or ("unclear" if _observed_has_eyewear(review) is None else "none")),
        "eyewearReadable": _as_bool(review.get("eyewearReadable"), default=True),
        "eyewearMismatch": eyewear_mismatch,
        "eyewearMismatchReason": "; ".join(eyewear_reasons),
        "temporaryEyewearAllowed": _temporary_eyewear_allowed(generation_asset),
        "temporaryEyewearApplied": _as_bool(generation_asset.get("temporaryEyewearApplied")),
        "adultVisual": _as_bool(review.get("adultVisual")),
        "photoRealism": _as_float(review.get("photoRealism")) if _as_float(review.get("photoRealism")) is not None else 0.0,
        "campusRealism": _as_float(review.get("campusRealism")) if _as_float(review.get("campusRealism")) is not None else 0.0,
        "brandFit": _as_float(review.get("brandFit")) if _as_float(review.get("brandFit")) is not None else 0.0,
        "shotTypeReadable": _as_bool(review.get("shotTypeReadable")),
        "influencerRisk": _as_float(review.get("influencerRisk")) if _as_float(review.get("influencerRisk")) is not None else 0.0,
        "childlikeRisk": _as_float(review.get("childlikeRisk")) if _as_float(review.get("childlikeRisk")) is not None else 0.0,
        "schoolUniformRisk": _as_float(review.get("schoolUniformRisk")) if _as_float(review.get("schoolUniformRisk")) is not None else 0.0,
        "sexualizationRisk": _as_float(review.get("sexualizationRisk")) if _as_float(review.get("sexualizationRisk")) is not None else 0.0,
        "artifactRisk": _as_float(review.get("artifactRisk")) if _as_float(review.get("artifactRisk")) is not None else 0.0,
        "metadataMismatch": metadata_mismatch,
        "mismatchFields": mismatch_fields,
        "originalDecision": original_decision,
        "finalDecision": final_decision,
        "decision": final_decision,
        "status": _status_from_decision(final_decision),
        "hardReject": bool(hard_reject_reasons),
        "hardRejectReasons": hard_reject_reasons,
        "rejectReasons": reject_reasons,
        "needsReviewReasons": sorted(set(needs_review_reasons)),
        "notes": str(review.get("notes") or ""),
        "sheetId": sheet_id,
        "visualVerdictQaType": ASSET_QA_TYPE,
        "sourceVisualJson": to_portable_path(source_json),
        "appliedAt": applied_at,
        "updatedAt": applied_at,
        "countsTowardIdentityQa": final_decision == "approved",
    }


def apply_asset_qa(
    *,
    root: Path | str | None = None,
    input_path: str | None = None,
    out_manifest: Path | str | None = None,
    force: bool = False,
    allow_empty: bool = False,
    legacy_jsonl: bool = False,
) -> dict[str, Any]:
    paths = pipeline_paths(root)
    ensure_base_dirs(paths)
    reviews, payload, source_path = _load_visual_items(
        input_path,
        expected_qa_type=ASSET_QA_TYPE,
        item_key="assets",
        allow_empty=allow_empty,
        legacy_jsonl=legacy_jsonl,
    )
    applied_at = now_utc()
    sheet_id = str((payload or {}).get("sheetId") or "")
    generation_by_asset = {str(row.get("assetId") or ""): dict(row) for row in load_generation_manifest(paths)}
    output_manifest = asset_qa_manifest_path(root, out_manifest)
    manifest_by_asset = _latest_by_key(read_jsonl(output_manifest), "assetId")
    applied_records: list[dict[str, Any]] = []

    for review in reviews:
        record = _asset_record(
            review,
            generation_asset=generation_by_asset.get(str(review.get("assetId") or ""), {}),
            sheet_id=sheet_id,
            source_json=source_path,
            applied_at=applied_at,
        )
        manifest_by_asset[record["assetId"]] = record
        applied_records.append(record)

    if reviews and not applied_records:
        raise RuntimeError("visual-verdict asset QA payload produced checked=0")

    for record in applied_records:
        generation_row = generation_by_asset.get(record["assetId"])
        if not generation_row:
            continue
        generation_row.update(
            {
                "status": record["status"],
                "visualDecision": record["finalDecision"],
                "metadataMismatch": record["metadataMismatch"],
                "mismatchFields": record["mismatchFields"],
                "observedFaceType": record["observedFaceType"],
                "observedLooksLevelBand": record["observedLooksLevelBand"],
                "faceTypeConfidence": record["faceTypeConfidence"],
                "looksLevelConfidence": record["looksLevelConfidence"],
                "updatedAt": applied_at,
                "error": "; ".join(record["hardRejectReasons"] or record["needsReviewReasons"] or record["rejectReasons"]),
            }
        )
    if generation_by_asset:
        write_generation_outputs(paths, list(generation_by_asset.values()))

    ordered = sorted(manifest_by_asset.values(), key=lambda row: (str(row.get("profileId") or ""), str(row.get("shotType") or ""), str(row.get("assetId") or "")))
    write_jsonl(output_manifest, ordered)
    _append_history(root, "asset_qa_apply_history.jsonl", applied_records)

    counts = {
        "checked": len(reviews),
        "approved": sum(1 for row in applied_records if row["finalDecision"] == "approved"),
        "needs_review": sum(1 for row in applied_records if row["finalDecision"] == "needs_review"),
        "rejected": sum(1 for row in applied_records if row["finalDecision"] == "rejected"),
        "hard_rejected": sum(1 for row in applied_records if row["hardReject"]),
        "metadata_mismatch": sum(1 for row in applied_records if row["metadataMismatch"]),
        "output_manifest": to_portable_path(output_manifest),
    }
    return counts


def _asset_ids_from_review(review: Mapping[str, Any]) -> dict[str, str]:
    source = review.get("assetIds") if isinstance(review.get("assetIds"), Mapping) else {}
    return {shot: str(source.get(shot) or "") for shot in SHOT_ORDER}


def _identity_metadata_mismatch(review: Mapping[str, Any], asset_records: list[Mapping[str, Any]]) -> tuple[bool, list[str]]:
    fields = _normalized_mismatch_fields(review.get("mismatchFields"))
    mismatch = _as_bool(review.get("metadataMismatch")) or bool(fields)
    target_face = normalize_face_type(review.get("targetFaceType") or "")
    observed_face = normalize_face_type(review.get("observedFaceType") or "")
    target_looks = str(review.get("targetLooksLevelBand") or "")
    observed_looks = str(review.get("observedLooksLevelBand") or "")
    if observed_face and observed_face != "unclear" and target_face and target_face != observed_face:
        mismatch = True
        fields.add("faceType")
    if observed_looks and observed_looks != "unclear" and target_looks and target_looks != observed_looks:
        mismatch = True
        fields.add("looksLevelBand")
    for asset in asset_records:
        if _as_bool(asset.get("metadataMismatch")):
            mismatch = True
            fields.update(_normalized_mismatch_fields(asset.get("mismatchFields")))
        target_has = _target_has_eyewear(asset)
        observed_has = _observed_has_eyewear(asset)
        if observed_has is None:
            continue
        if target_has and not observed_has:
            mismatch = True
            fields.add("eyewear")
        if not target_has and observed_has and not _as_bool(asset.get("temporaryEyewearAllowed")):
            mismatch = True
            fields.add("eyewear")
        target_expected = str(asset.get("targetShotEyewearExpected") or "none")
        observed_eyewear = str(asset.get("observedEyewear") or "")
        if target_has and observed_eyewear and observed_eyewear not in {"unclear", "other", target_expected}:
            mismatch = True
            fields.add("eyewear")
    return mismatch, sorted(fields)


def _identity_record(
    review: Mapping[str, Any],
    *,
    active_asset_by_id: Mapping[str, Mapping[str, Any]],
    asset_by_id: Mapping[str, Mapping[str, Any]],
    generation_by_asset: Mapping[str, Mapping[str, Any]],
    file_qa_by_asset: Mapping[str, Mapping[str, Any]],
    root: Path | str | None,
    source_json: Path,
    applied_at: str,
) -> dict[str, Any]:
    _require_keys(review, IDENTITY_REQUIRED_KEYS, "identity")
    profile_id = str(review.get("profileId") or "")
    numeric_id = _safe_numeric_id(profile_id)
    asset_ids = _asset_ids_from_review(review)
    if not any(str(row.get("profileId") or "") == profile_id for row in generation_by_asset.values()):
        raise ValueError(f"Unknown identity in identity QA payload: {profile_id}")
    asset_records = [asset_by_id[asset_id] for asset_id in asset_ids.values() if asset_id in asset_by_id]
    missing_asset_qa = [shot for shot, asset_id in asset_ids.items() if not asset_id or asset_id not in asset_by_id]
    asset_final_decisions = {
        shot: _normalize_decision(asset_by_id.get(asset_id, {}).get("finalDecision") or "missing")
        for shot, asset_id in asset_ids.items()
    }
    visual_asset_decisions = review.get("assetDecisions") if isinstance(review.get("assetDecisions"), Mapping) else {}
    original_decision = _normalize_decision(review.get("completeIdentityDecision"))
    metadata_mismatch, mismatch_fields = _identity_metadata_mismatch(review, asset_records)
    same_identity = _as_bool(review.get("sameIdentity"), default=False)
    face_to_silhouette = _as_float(review.get("faceToSilhouetteConsistency"))
    face_to_vibe = _as_float(review.get("faceToVibeConsistency"))

    reject_reasons = set(_json_list(review.get("rejectReasons")))
    needs_review_reasons: set[str] = set()
    file_qa_evidence: dict[str, dict[str, Any]] = {}
    propagated_hard_reject = any(_as_bool(asset.get("hardReject")) for asset in asset_records)

    if any(not asset_ids.get(shot) for shot in SHOT_ORDER):
        needs_review_reasons.add("missing_required_asset_id")
    for shot in missing_asset_qa:
        needs_review_reasons.add(f"asset_qa_missing:{shot}")
    for shot in SHOT_ORDER:
        asset_id = asset_ids.get(shot, "")
        generation_asset = generation_by_asset.get(asset_id, {})
        if asset_id and generation_asset:
            if str(generation_asset.get("profileId") or "") != profile_id:
                raise ValueError(f"Identity QA {profile_id} references asset from another profile: {asset_id}")
            if str(generation_asset.get("shotType") or "") != shot:
                raise ValueError(f"Identity QA {profile_id} references wrong shot for {shot}: {asset_id}")
        final_path_value = str(generation_asset.get("finalPath") or generation_asset.get("expectedFinalPath") or "")
        final_path = Path(final_path_value)
        if final_path_value and not final_path.is_absolute():
            final_path = pipeline_paths(root).root / final_path
        if not final_path_value or not final_path.exists():
            needs_review_reasons.add(f"final_file_missing:{shot}")
        file_qa = file_qa_by_asset.get(asset_id, {})
        evidence = resolve_file_qa_evidence(
            root,
            asset_id,
            active_asset=active_asset_by_id.get(asset_id, {}),
            generation_row=generation_asset,
            file_qa_row=file_qa,
            expected_profile_id=profile_id,
            expected_shot_type=shot,
        )
        file_qa_evidence[shot] = evidence
        if not evidence["ok"]:
            needs_review_reasons.add(f"file_qa_missing:{shot}")
            for reason in evidence.get("reasons", []):
                if reason == "prompt_hash_mismatch":
                    needs_review_reasons.add(f"prompt_hash_mismatch:{shot}")
                elif reason == "prompt_targeting_version_mismatch":
                    needs_review_reasons.add(f"prompt_targeting_version_mismatch:{shot}")
                elif reason in {"file_qa_missing_in_manifest", "file_qa_status_mismatch", "final_path_mismatch"}:
                    needs_review_reasons.add(f"{reason}:{shot}")
        visual_decision = _normalize_decision(visual_asset_decisions.get(shot) or "missing")
        if visual_decision != "approved":
            needs_review_reasons.add(f"visual_asset_decision_not_approved:{shot}")
        asset_decision = asset_final_decisions.get(shot, "missing")
        if asset_decision == "needs_review":
            needs_review_reasons.add(f"asset_needs_review:{shot}")
        if asset_decision == "missing":
            needs_review_reasons.add(f"asset_missing:{shot}")
        if asset_decision == "rejected":
            reject_reasons.add(f"asset_rejected:{shot}")
    if not same_identity:
        reject_reasons.add("sameIdentity_false")
    if face_to_silhouette is None or face_to_vibe is None:
        needs_review_reasons.add("identity_consistency_uncertain")
    if face_to_silhouette is not None and face_to_silhouette < 3.8:
        reject_reasons.add("faceToSilhouetteConsistency_below_3.8")
    if face_to_vibe is not None and face_to_vibe < 3.8:
        reject_reasons.add("faceToVibeConsistency_below_3.8")
    if propagated_hard_reject:
        reject_reasons.add("asset_hard_reject")
    if str(review.get("observedLooksLevelBand") or "") == "4.4-5.0":
        reject_reasons.add("over_level_4.4-5.0")
    if str(review.get("observedFaceType") or "") == "unclear":
        needs_review_reasons.add("observedFaceType_unclear")
    if str(review.get("observedLooksLevelBand") or "") == "unclear":
        needs_review_reasons.add("observedLooksLevelBand_unclear")
    if metadata_mismatch:
        needs_review_reasons.add("metadata_mismatch")
    if "eyewear" in mismatch_fields:
        needs_review_reasons.add("eyewear_inconsistent")
    if original_decision == "needs_review":
        needs_review_reasons.add("visual_verdict_needs_review")
    if not _as_bool(review.get("countsTowardDistribution")):
        needs_review_reasons.add("visual_countsTowardDistribution_false")
    if numeric_id is None:
        needs_review_reasons.add("numericId_unparseable")
    if set(asset_ids) != set(SHOT_ORDER):
        needs_review_reasons.add("required_shot_types_not_exact")

    if original_decision == "rejected":
        reject_reasons.add("visual_verdict_rejected")
    if reject_reasons:
        final_decision = "rejected"
    elif needs_review_reasons:
        final_decision = "needs_review"
    else:
        final_decision = "approved"

    final_paths = {
        shot: str(generation_by_asset.get(asset_id, {}).get("finalPath") or generation_by_asset.get(asset_id, {}).get("expectedFinalPath") or "")
        for shot, asset_id in asset_ids.items()
    }
    counts_toward = final_decision == "approved"
    first_generation_asset = next((generation_by_asset.get(str(asset_ids.get(shot) or ""), {}) for shot in SHOT_ORDER if generation_by_asset.get(str(asset_ids.get(shot) or ""), {})), {})
    observed_eyewear_values = {
        shot: asset_by_id.get(str(asset_ids.get(shot) or ""), {}).get("observedEyewear")
        for shot in SHOT_ORDER
    }
    return {
        "schemaVersion": "seolleyeon_identity_qa_manifest_v3",
        "profileId": profile_id,
        "gender": str(review.get("gender") or "unknown"),
        "numericId": numeric_id,
        "targetFaceType": normalize_face_type(review.get("targetFaceType") or "unknown"),
        "observedFaceType": normalize_face_type(review.get("observedFaceType") or "unclear"),
        "targetLooksLevelBand": str(review.get("targetLooksLevelBand") or "unknown"),
        "observedLooksLevelBand": str(review.get("observedLooksLevelBand") or "unclear"),
        "targetHasEyewear": _target_has_eyewear(first_generation_asset),
        "targetEyewearGroup": _target_eyewear_group(first_generation_asset),
        "targetEyewear": str(first_generation_asset.get("targetEyewear") or first_generation_asset.get("eyewear") or _target_eyewear_expected(first_generation_asset)),
        "targetCanonicalEyewear": str(first_generation_asset.get("targetCanonicalEyewear") or first_generation_asset.get("canonicalEyewear") or _target_eyewear_expected(first_generation_asset)),
        "targetShotEyewearExpected": {
            shot: _target_eyewear_expected(generation_by_asset.get(str(asset_ids.get(shot) or ""), {}))
            for shot in SHOT_ORDER
        },
        "observedEyewearConsistency": "inconsistent" if "eyewear" in mismatch_fields else str(review.get("observedEyewearConsistency") or "consistent"),
        "observedEyewearByShot": observed_eyewear_values,
        "eyewearMismatchReason": "; ".join(sorted(reason for reason in needs_review_reasons if "eyewear" in reason)),
        "assetIds": asset_ids,
        "assetDecisions": asset_final_decisions,
        "assetFinalDecisions": asset_final_decisions,
        "fileQaEvidence": file_qa_evidence,
        "finalPaths": final_paths,
        "faceToSilhouetteConsistency": face_to_silhouette if face_to_silhouette is not None else 0.0,
        "faceToVibeConsistency": face_to_vibe if face_to_vibe is not None else 0.0,
        "sameIdentity": same_identity,
        "originalCompleteIdentityDecision": original_decision,
        "finalCompleteIdentityDecision": final_decision,
        "completeIdentityDecision": final_decision,
        "decision": final_decision,
        "status": _status_from_decision(final_decision, identity=True),
        "countsTowardDistribution": counts_toward,
        "metadataMismatch": metadata_mismatch,
        "mismatchFields": mismatch_fields,
        "failedShotTypes": sorted({shot for shot, decision in asset_final_decisions.items() if decision != "approved"}),
        "retryShotTypes": sorted({shot for shot in SHOT_ORDER if shot in missing_asset_qa or asset_final_decisions.get(shot) == "needs_review"}),
        "rejectReasons": sorted(reject_reasons),
        "needsReviewReasons": sorted(needs_review_reasons),
        "sourceVisualJson": to_portable_path(source_json),
        "visualVerdictQaType": IDENTITY_QA_TYPE,
        "appliedAt": applied_at,
        "updatedAt": applied_at,
        "notes": str(review.get("notes") or ""),
    }


def _approved_identity_record(identity: Mapping[str, Any], *, generation_by_asset: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    asset_ids = identity.get("assetIds") if isinstance(identity.get("assetIds"), Mapping) else {}
    final_paths = {
        shot: str(generation_by_asset.get(str(asset_ids.get(shot) or ""), {}).get("finalPath") or "")
        for shot in SHOT_ORDER
    }
    return {
        "schemaVersion": "seolleyeon_approved_identity_manifest_v3",
        "profileId": identity.get("profileId", ""),
        "gender": identity.get("gender", ""),
        "numericId": identity.get("numericId"),
        "faceType": identity.get("observedFaceType", ""),
        "looksLevelBand": identity.get("observedLooksLevelBand", ""),
        "observedFaceType": identity.get("observedFaceType", ""),
        "observedLooksLevelBand": identity.get("observedLooksLevelBand", ""),
        "hasEyewear": identity.get("targetHasEyewear", False),
        "eyewearGroup": identity.get("targetEyewearGroup", "none"),
        "eyewear": identity.get("targetEyewear", "none"),
        "canonicalEyewear": identity.get("targetCanonicalEyewear", "none"),
        "observedEyewearConsistency": identity.get("observedEyewearConsistency", ""),
        "assetIds": {shot: str(asset_ids.get(shot) or "") for shot in SHOT_ORDER},
        "fileQaEvidence": identity.get("fileQaEvidence", {}),
        "finalPaths": final_paths,
        "finalCompleteIdentityDecision": identity.get("finalCompleteIdentityDecision", ""),
        "countsTowardDistribution": True,
        "metadataMismatch": False,
        "appliedAt": identity.get("appliedAt", now_utc()),
    }


def _identity_has_strict_approval_backing(
    identity: Mapping[str, Any],
    *,
    active_asset_by_id: Mapping[str, Mapping[str, Any]],
    asset_by_id: Mapping[str, Mapping[str, Any]],
    generation_by_asset: Mapping[str, Mapping[str, Any]],
    file_qa_by_asset: Mapping[str, Mapping[str, Any]],
    root: Path | str | None,
) -> bool:
    if identity.get("finalCompleteIdentityDecision") != "approved":
        return False
    if identity.get("countsTowardDistribution") is not True:
        return False
    if _as_bool(identity.get("metadataMismatch")):
        return False
    if identity.get("observedLooksLevelBand") == "4.4-5.0":
        return False
    profile_id = str(identity.get("profileId") or "")
    asset_ids = identity.get("assetIds") if isinstance(identity.get("assetIds"), Mapping) else {}
    if set(asset_ids) != set(SHOT_ORDER):
        return False
    for shot in SHOT_ORDER:
        asset_id = str(asset_ids.get(shot) or "")
        if not asset_id:
            return False
        asset_qa = asset_by_id.get(asset_id, {})
        if _normalize_decision(asset_qa.get("finalDecision") or "missing") != "approved":
            return False
        if _as_bool(asset_qa.get("metadataMismatch")):
            return False
        evidence = resolve_file_qa_evidence(
            root,
            asset_id,
            active_asset=active_asset_by_id.get(asset_id, {}),
            generation_row=generation_by_asset.get(asset_id, {}),
            file_qa_row=file_qa_by_asset.get(asset_id, {}),
            expected_profile_id=profile_id,
            expected_shot_type=shot,
        )
        if not evidence["ok"]:
            return False
    return True


def apply_identity_qa(
    *,
    root: Path | str | None = None,
    input_path: str | None = None,
    asset_qa_manifest: Path | str | None = None,
    out_manifest: Path | str | None = None,
    max_attempts: int = 3,
    allow_empty: bool = False,
    legacy_jsonl: bool = False,
) -> dict[str, Any]:
    del max_attempts
    paths = pipeline_paths(root)
    ensure_base_dirs(paths)
    reviews, _payload, source_path = _load_visual_items(
        input_path,
        expected_qa_type=IDENTITY_QA_TYPE,
        item_key="identities",
        allow_empty=allow_empty,
        legacy_jsonl=legacy_jsonl,
    )
    applied_at = now_utc()
    asset_manifest_path = Path(asset_qa_manifest).resolve() if asset_qa_manifest else asset_qa_manifest_path(root)
    asset_by_id = _latest_by_key(read_jsonl(asset_manifest_path), "assetId")
    active_asset_by_id = _latest_by_key(
        read_jsonl(paths.manifests / "ai_profile_assets_v3.jsonl") + read_jsonl(paths.manifests / "asset_manifest.jsonl"),
        "assetId",
    )
    generation_by_asset = {str(row.get("assetId") or ""): dict(row) for row in load_generation_manifest(paths)}
    file_qa_by_asset = _latest_by_key(read_jsonl(paths.manifests / "file_qa_manifest.jsonl"), "assetId")
    output_manifest = identity_qa_manifest_path(root, out_manifest)
    manifest_by_profile = _latest_by_key(read_jsonl(output_manifest), "profileId")
    existing_approved_by_profile = _latest_by_key(read_jsonl(paths.manifests / "approved_identity_manifest.jsonl"), "profileId")
    existing_rejected_by_profile = _latest_by_key(read_jsonl(paths.manifests / "rejected_identity_manifest.jsonl"), "profileId")
    existing_needs_review_by_profile = _latest_by_key(read_jsonl(paths.manifests / "needs_review_identity_manifest.jsonl"), "profileId")
    applied_records: list[dict[str, Any]] = []

    for review in reviews:
        record = _identity_record(
            review,
            active_asset_by_id=active_asset_by_id,
            asset_by_id=asset_by_id,
            generation_by_asset=generation_by_asset,
            file_qa_by_asset=file_qa_by_asset,
            root=root,
            source_json=source_path,
            applied_at=applied_at,
        )
        manifest_by_profile[record["profileId"]] = record
        applied_records.append(record)

    if reviews and not applied_records:
        raise RuntimeError("visual-verdict identity QA payload produced checked=0")

    for record in applied_records:
        for asset_id in record.get("assetIds", {}).values():
            if asset_id in generation_by_asset:
                generation_by_asset[asset_id]["identityDecision"] = record["finalCompleteIdentityDecision"]
                generation_by_asset[asset_id]["countsTowardDistribution"] = record["countsTowardDistribution"]
                generation_by_asset[asset_id]["sameIdentity"] = record["sameIdentity"]
                generation_by_asset[asset_id]["metadataMismatch"] = record["metadataMismatch"] or _as_bool(generation_by_asset[asset_id].get("metadataMismatch"))
                generation_by_asset[asset_id]["updatedAt"] = applied_at
    if generation_by_asset:
        write_generation_outputs(paths, list(generation_by_asset.values()))

    ordered = sorted(manifest_by_profile.values(), key=lambda row: str(row.get("profileId") or ""))
    write_jsonl(output_manifest, ordered)
    _append_history(root, "identity_qa_apply_history.jsonl", applied_records)

    applied_profile_ids = {str(row.get("profileId") or "") for row in applied_records if row.get("profileId")}
    current_approved_records = [
        _approved_identity_record(row, generation_by_asset=generation_by_asset)
        for row in ordered
        if _identity_has_strict_approval_backing(
            row,
            active_asset_by_id=active_asset_by_id,
            asset_by_id=asset_by_id,
            generation_by_asset=generation_by_asset,
            file_qa_by_asset=file_qa_by_asset,
            root=root,
        )
    ]
    approved_by_profile = dict(existing_approved_by_profile)
    rejected_by_profile = dict(existing_rejected_by_profile)
    needs_review_by_profile = dict(existing_needs_review_by_profile)
    for profile_id in applied_profile_ids:
        approved_by_profile.pop(profile_id, None)
        rejected_by_profile.pop(profile_id, None)
        needs_review_by_profile.pop(profile_id, None)
    for row in current_approved_records:
        profile_id = str(row.get("profileId") or "")
        if profile_id:
            approved_by_profile[profile_id] = row
    for row in ordered:
        profile_id = str(row.get("profileId") or "")
        if not profile_id or profile_id not in applied_profile_ids:
            continue
        if row.get("finalCompleteIdentityDecision") == "rejected":
            rejected_by_profile[profile_id] = row
        elif row.get("finalCompleteIdentityDecision") == "needs_review":
            needs_review_by_profile[profile_id] = row
    approved_records = [approved_by_profile[key] for key in sorted(approved_by_profile)]
    rejected_records = [rejected_by_profile[key] for key in sorted(rejected_by_profile)]
    needs_review_records = [needs_review_by_profile[key] for key in sorted(needs_review_by_profile)]
    write_jsonl(paths.manifests / "approved_identity_manifest.jsonl", approved_records)
    write_jsonl(paths.manifests / "rejected_identity_manifest.jsonl", rejected_records)
    write_jsonl(paths.manifests / "needs_review_identity_manifest.jsonl", needs_review_records)
    audit_distribution(root=root)

    return {
        "checked": len(reviews),
        "approved": sum(1 for row in applied_records if row["finalCompleteIdentityDecision"] == "approved"),
        "needs_review": sum(1 for row in applied_records if row["finalCompleteIdentityDecision"] == "needs_review"),
        "rejected": sum(1 for row in applied_records if row["finalCompleteIdentityDecision"] == "rejected"),
        "hard_rejected": sum(1 for row in applied_records if "asset_hard_reject" in row.get("rejectReasons", [])),
        "metadata_mismatch": sum(1 for row in applied_records if row["metadataMismatch"]),
        "output_manifest": to_portable_path(output_manifest),
    }


def _dicts_disagree(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    for key in set(left) | set(right):
        try:
            left_value = int(left.get(key) or 0)
            right_value = int(right.get(key) or 0)
        except (TypeError, ValueError):
            return True
        if left_value != right_value:
            return True
    return False


def _visual_numeric_disagreements(visual: Mapping[str, Any], numeric: Mapping[str, Any]) -> list[str]:
    disagreements: list[str] = []
    for visual_key, numeric_key in (
        ("approvedCompleteIdentityCount", "approvedCompleteIdentityCount"),
        ("approvedImageCount", "approvedImageCount"),
        ("femaleApprovedIdentityCount", "femaleApprovedIdentityCount"),
        ("maleApprovedIdentityCount", "maleApprovedIdentityCount"),
    ):
        if visual_key in visual and int(visual.get(visual_key) or 0) != int(numeric.get(numeric_key) or 0):
            disagreements.append(visual_key)
    for key in (
        "globalFaceTypeCounts",
        "globalFaceTypeDeficits",
        "globalFaceTypeSurpluses",
        "globalLooksLevelBandCounts",
        "globalLooksLevelBandDeficits",
        "globalLooksLevelBandSurpluses",
    ):
        if isinstance(visual.get(key), Mapping) and _dicts_disagree(visual[key], numeric.get(key, {})):
            disagreements.append(key)
    for key in (
        "genderFaceTypeCounts",
        "genderFaceTypeDeficits",
        "genderFaceTypeSurpluses",
        "genderLooksLevelBandCounts",
        "genderLooksLevelBandDeficits",
        "genderLooksLevelBandSurpluses",
    ):
        visual_value = visual.get(key)
        numeric_value = numeric.get(key, {})
        if not isinstance(visual_value, Mapping):
            continue
        for gender in ("female", "male"):
            if isinstance(visual_value.get(gender), Mapping) and _dicts_disagree(visual_value[gender], numeric_value.get(gender, {})):
                disagreements.append(f"{key}.{gender}")
    return disagreements


def apply_distribution_audit(
    *,
    root: Path | str | None = None,
    input_path: str | None = None,
    numeric_audit: Path | str | None = None,
    allow_empty: bool = False,
    legacy_jsonl: bool = False,
) -> dict[str, Any]:
    paths = pipeline_paths(root)
    ensure_base_dirs(paths)
    visual_rows, _payload, _source_path = _load_visual_items(
        input_path,
        expected_qa_type=DISTRIBUTION_QA_TYPE,
        item_key=None,
        allow_empty=allow_empty,
        legacy_jsonl=legacy_jsonl,
    )
    visual = visual_rows[0] if visual_rows else {}
    if numeric_audit and Path(numeric_audit).exists():
        python_audit = json.loads(Path(numeric_audit).read_text(encoding="utf-8"))
    else:
        python_audit = audit_distribution(root=root)
    disagreements = _visual_numeric_disagreements(visual, python_audit)
    result = {
        "schemaVersion": "seolleyeon_visual_distribution_audit_apply_v3",
        "visualAudit": visual,
        "pythonAuditSummary": {
            "approvedCompleteIdentityCount": python_audit["approvedCompleteIdentityCount"],
            "approvedImageCount": python_audit["approvedImageCount"],
            "femaleApprovedIdentityCount": python_audit["femaleApprovedIdentityCount"],
            "maleApprovedIdentityCount": python_audit["maleApprovedIdentityCount"],
            "exactDistributionMatch": python_audit["exactDistributionMatch"],
            "passed": python_audit["passed"],
        },
        "disagreements": disagreements,
        "needsManualReview": bool(disagreements),
        "updatedAt": now_utc(),
    }
    out_dir = paths.reports / "visual_verdict"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "distribution_audit_apply.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if disagreements:
        (paths.manifests / "manual_review_required.flag").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def _parser(kind: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=f"Apply visual-verdict {kind} JSON to Seolleyeon AI image manifests.")
    parser.add_argument("--root", default=None)
    parser.add_argument("--input", "--visual_json", dest="input", required=True)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--max_attempts", type=int, default=3)
    parser.add_argument("--allow_empty", action="store_true")
    parser.add_argument("--legacy_jsonl", action="store_true")
    parser.add_argument("--out_manifest", default=None)
    parser.add_argument("--asset_qa_manifest", default=None)
    parser.add_argument("--numeric_audit", default=None)
    return parser


def asset_main(argv: list[str] | None = None) -> int:
    args = _parser("asset QA").parse_args(argv)
    counts = apply_asset_qa(
        root=args.root,
        input_path=args.input,
        out_manifest=args.out_manifest,
        force=args.force,
        allow_empty=args.allow_empty,
        legacy_jsonl=args.legacy_jsonl,
    )
    print(json.dumps(counts, ensure_ascii=False, indent=2))
    return 0


def identity_main(argv: list[str] | None = None) -> int:
    args = _parser("identity QA").parse_args(argv)
    counts = apply_identity_qa(
        root=args.root,
        input_path=args.input,
        asset_qa_manifest=args.asset_qa_manifest,
        out_manifest=args.out_manifest,
        max_attempts=args.max_attempts,
        allow_empty=args.allow_empty,
        legacy_jsonl=args.legacy_jsonl,
    )
    print(json.dumps(counts, ensure_ascii=False, indent=2))
    return 0


def distribution_main(argv: list[str] | None = None) -> int:
    args = _parser("distribution audit").parse_args(argv)
    result = apply_distribution_audit(
        root=args.root,
        input_path=args.input,
        numeric_audit=args.numeric_audit,
        allow_empty=args.allow_empty,
        legacy_jsonl=args.legacy_jsonl,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 2 if result["needsManualReview"] else 0
