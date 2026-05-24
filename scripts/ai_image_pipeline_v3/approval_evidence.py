from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .config import SHOT_ORDER, pipeline_paths, profile_number, read_jsonl
from .distribution_targets import normalize_face_type, target_face_type, target_looks_level, target_looks_level_band
from .qa import inspect_image_detail


APPROVED_DECISIONS = {"approved", "vision_approved", "identity_approved", "qa_approved"}
NEEDS_REVIEW_DECISIONS = {"needs_review", "vision_needs_review", "identity_needs_review", "file_needs_review"}
REJECTED_DECISIONS = {"rejected", "vision_rejected", "identity_rejected", "file_rejected", "qa_rejected"}
FILE_QA_PASSED = {"file_qa_passed", "file_passed", "passed"}


def _as_bool(value: Any, *, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "y", "approved", "passed"}


def _normalize_decision(value: Any) -> str:
    raw = str(value or "").strip()
    if raw in APPROVED_DECISIONS:
        return "approved"
    if raw in NEEDS_REVIEW_DECISIONS:
        return "needs_review"
    if raw in REJECTED_DECISIONS:
        return "rejected"
    if raw in FILE_QA_PASSED:
        return "file_qa_passed"
    return raw


def _latest_by_key(rows: list[Mapping[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        row_key = str(row.get(key) or "")
        if row_key:
            latest[row_key] = dict(row)
    return latest


def _manifest_rows(root: Path | str | None) -> list[dict[str, Any]]:
    paths = pipeline_paths(root)
    rows: list[dict[str, Any]] = []
    for name in ("ai_profile_assets_v3.jsonl", "asset_manifest.jsonl"):
        rows.extend(read_jsonl(paths.manifests / name))
    return rows


def _resolve_path(root: Path | str | None, value: Any) -> Path | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    path = Path(raw)
    if path.is_absolute():
        return path
    return pipeline_paths(root).root / path


def _expected_final_owner(root: Path | str | None, row: Mapping[str, Any], final_path: Path | None) -> bool:
    if final_path is None:
        return False
    gender = str(row.get("gender") or "")
    numeric = str(row.get("numericId") or "")
    if not numeric:
        try:
            numeric = profile_number(str(row.get("profileId") or ""))
        except ValueError:
            numeric = ""
    shot = str(row.get("shotType") or "")
    expected = pipeline_paths(root).ai_image / gender / numeric / f"{shot}.png"
    try:
        return final_path.resolve() == expected.resolve()
    except OSError:
        return False


def _row_value(*rows: Mapping[str, Any], key: str, default: Any = "") -> Any:
    for row in rows:
        if row.get(key) not in (None, ""):
            return row.get(key)
    return default


def _file_qa_passed(row: Mapping[str, Any]) -> bool:
    status = _normalize_decision(row.get("status") or row.get("decision") or row.get("qaStatus"))
    return status in {"file_qa_passed", "file_passed"}


def _prompt_targeting_version(row: Mapping[str, Any]) -> str:
    value = str(row.get("promptTargetingVersion") or "").strip()
    if value:
        return value
    metadata = row.get("metadata")
    if isinstance(metadata, Mapping):
        return str(metadata.get("promptTargetingVersion") or "").strip()
    return ""


def _prompt_evidence_mismatches(active_row: Mapping[str, Any], evidence_row: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    active_version = _prompt_targeting_version(active_row)
    evidence_version = _prompt_targeting_version(evidence_row)
    if active_version and evidence_version and evidence_version != active_version:
        reasons.append("prompt_targeting_version_mismatch")
    active_hash = str(active_row.get("promptHash") or "").strip()
    evidence_hash = str(evidence_row.get("promptHash") or "").strip()
    if active_hash and evidence_hash and evidence_hash != active_hash:
        reasons.append("prompt_hash_mismatch")
    return reasons


def _load_current_chunk_state(root: Path | str | None) -> dict[str, Any]:
    path = pipeline_paths(root).manifests / "current_chunk_state.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        return {}
    return dict(payload) if isinstance(payload, Mapping) else {}


def _transaction_receipts(root: Path | str | None) -> list[dict[str, Any]]:
    reports = pipeline_paths(root).ai_image / "reports" / "chunks"
    if not reports.exists():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(reports.glob("*/transactions/*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(payload, Mapping):
            row = dict(payload)
            row["receiptPath"] = str(path)
            rows.append(row)
    return rows


def _latest_transaction_by_asset(root: Path | str | None) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in _transaction_receipts(root):
        asset_id = str(row.get("assetId") or row.get("asset_id") or "")
        if asset_id:
            latest[asset_id] = row
    return latest


def _state_file_qa_status(root: Path | str | None, asset_id: str) -> str:
    state = _load_current_chunk_state(root)
    asset_states = state.get("assetStates") if isinstance(state.get("assetStates"), Mapping) else {}
    return str(asset_states.get(asset_id) or "")


def resolve_file_qa_evidence(
    root: Path | str | None,
    asset_id: str,
    *,
    active_asset: Mapping[str, Any] | None = None,
    generation_row: Mapping[str, Any] | None = None,
    file_qa_row: Mapping[str, Any] | None = None,
    transaction_receipt: Mapping[str, Any] | None = None,
    expected_profile_id: str = "",
    expected_shot_type: str = "",
) -> dict[str, Any]:
    """Resolve strict file-QA evidence for an asset without trusting file existence alone.

    The global file QA manifest is primary.  A current chunk state fallback is
    accepted only when active asset ownership, generation evidence,
    prompt version/hash, and the final image file all validate.
    """
    active_asset = dict(active_asset or {})
    generation_row = dict(generation_row or {})
    file_qa_row = dict(file_qa_row or {})
    transaction_receipt = dict(transaction_receipt or _latest_transaction_by_asset(root).get(asset_id, {}))
    reasons: set[str] = set()
    status = ""
    source = "none"

    if not active_asset:
        reasons.add("file_qa_asset_not_in_active_manifest")
    if not generation_row:
        reasons.add("file_qa_missing_generation_evidence")

    row_for_metadata = generation_row or active_asset
    if expected_profile_id and str(row_for_metadata.get("profileId") or "") != expected_profile_id:
        reasons.add("metadata_mismatch")
    if expected_shot_type and str(row_for_metadata.get("shotType") or "") != expected_shot_type:
        reasons.add("metadata_mismatch")
    if str(row_for_metadata.get("assetId") or asset_id) != asset_id:
        reasons.add("metadata_mismatch")

    if active_asset and generation_row:
        reasons.update(_prompt_evidence_mismatches(active_asset, generation_row))
    if active_asset and file_qa_row:
        reasons.update(_prompt_evidence_mismatches(active_asset, file_qa_row))

    final_path = _resolve_path(root, _row_value(generation_row, active_asset, file_qa_row, transaction_receipt, key="finalPath"))
    if not final_path and file_qa_row:
        final_path = _resolve_path(root, _row_value(file_qa_row, key="imagePath"))
    if final_path is None:
        reasons.add("final_file_missing")
    else:
        if not _expected_final_owner(root, row_for_metadata or active_asset, final_path):
            reasons.add("final_path_mismatch")
        if not final_path.exists():
            reasons.add("final_file_missing")
        else:
            detail = inspect_image_detail(final_path)
            if not detail.get("ok"):
                reasons.add("final_file_not_decodable")

    receipt_accepts_file_qa = False
    if transaction_receipt:
        receipt_status = str(transaction_receipt.get("status") or transaction_receipt.get("finalStatus") or "")
        receipt_file_qa_status = ""
        receipt_file_qa = transaction_receipt.get("fileQa")
        if isinstance(receipt_file_qa, Mapping):
            receipt_file_qa_status = str(receipt_file_qa.get("decision") or receipt_file_qa.get("status") or "")
        if str(transaction_receipt.get("assetId") or asset_id) != asset_id:
            reasons.add("transaction_receipt_metadata_mismatch")
        if expected_profile_id and str(transaction_receipt.get("profileId") or "") != expected_profile_id:
            reasons.add("transaction_receipt_metadata_mismatch")
        if expected_shot_type and str(transaction_receipt.get("shotType") or "") != expected_shot_type:
            reasons.add("transaction_receipt_metadata_mismatch")
        raw_path = _resolve_path(root, transaction_receipt.get("rawPath"))
        if raw_path is not None and not raw_path.exists():
            reasons.add("transaction_receipt_raw_missing")
        receipt_accepts_file_qa = (
            _as_bool(transaction_receipt.get("fileQaPassed"))
            and receipt_status not in {"failed", "error", "rejected"}
            and _normalize_decision(receipt_file_qa_status or "file_qa_passed") in {"file_qa_passed", "file_passed"}
        )

    generation_status = str(generation_row.get("status") or generation_row.get("decision") or generation_row.get("qaStatus") or "")
    generation_accepts_file_qa = bool(generation_row) and _normalize_decision(generation_status) in FILE_QA_PASSED

    state_status = _state_file_qa_status(root, asset_id)
    normalized_state_status = _normalize_decision(state_status)
    state_accepts_file_qa = state_status in {"file_qa_passed", "visual_qa_pending"}
    state_blocks_file_qa = state_status in {
        "failed",
        "file_qa_failed",
        "retry_needed",
        "missing",
        "pending_imagegen",
        "pending_file_qa",
    }

    if file_qa_row:
        status = str(
            file_qa_row.get("status")
            or file_qa_row.get("decision")
            or file_qa_row.get("qaStatus")
            or file_qa_row.get("fileQaStatus")
            or ""
        )
        normalized_manifest_status = _normalize_decision(status)
        source = "file_qa_manifest"
        if _file_qa_passed(file_qa_row):
            if state_blocks_file_qa:
                reasons.add("file_qa_evidence_conflict")
        elif normalized_manifest_status in {"rejected"} or "failed" in status or "rejected" in status:
            reasons.add("file_qa_status_mismatch")
            if state_accepts_file_qa or receipt_accepts_file_qa or generation_accepts_file_qa:
                reasons.add("file_qa_evidence_conflict")
        elif receipt_accepts_file_qa:
            status = "file_qa_passed"
            source = "transaction_receipt"
        elif generation_accepts_file_qa:
            status = "file_qa_passed"
            source = "generation_manifest"
        elif state_accepts_file_qa:
            status = "file_qa_passed"
            source = "current_chunk_state"
            reasons.add("file_qa_found_in_state_only")
        else:
            reasons.add("file_qa_status_mismatch")
    else:
        if receipt_accepts_file_qa:
            status = "file_qa_passed"
            source = "transaction_receipt"
        elif generation_accepts_file_qa:
            status = "file_qa_passed"
            source = "generation_manifest"
        elif state_accepts_file_qa:
            status = "file_qa_passed"
            source = "current_chunk_state"
            reasons.add("file_qa_found_in_state_only")
        else:
            status = state_status or "missing"
            reasons.add("file_qa_missing_in_manifest")
            if state_blocks_file_qa:
                reasons.add("file_qa_status_mismatch")

    if source in {"transaction_receipt", "generation_manifest", "current_chunk_state"} and "file_qa_missing_in_manifest" in reasons:
        reasons.discard("file_qa_missing_in_manifest")
    if source == "current_chunk_state" and "file_qa_missing_generation_evidence" in reasons:
        reasons.discard("file_qa_missing_generation_evidence")

    blocking_reasons = {
        reason
        for reason in reasons
        if reason not in {"file_qa_found_in_state_only", "file_qa_evidence_valid"}
    }
    ok = not blocking_reasons and (status in FILE_QA_PASSED or (source == "current_chunk_state" and normalized_state_status in {"file_qa_passed", "visual_qa_pending"}))
    if ok:
        reasons.add("file_qa_evidence_valid")
    return {
        "assetId": asset_id,
        "ok": ok,
        "source": source,
        "status": status,
        "reasons": sorted(reasons),
        "finalPath": str(final_path) if final_path else "",
        "promptHashMatches": "prompt_hash_mismatch" not in reasons,
        "promptTargetingVersionMatches": "prompt_targeting_version_mismatch" not in reasons,
        "durableAfterChunkReplacement": source in {"file_qa_manifest", "transaction_receipt", "generation_manifest"},
    }


def _asset_visual_decision(row: Mapping[str, Any]) -> str:
    return _normalize_decision(row.get("finalDecision") or row.get("decision") or row.get("visualDecision") or row.get("status"))


def _identity_decision(row: Mapping[str, Any]) -> str:
    return _normalize_decision(row.get("finalCompleteIdentityDecision") or row.get("completeIdentityDecision") or row.get("decision") or row.get("status"))


def _asset_id_from_approved(approved_row: Mapping[str, Any], profile_id: str, shot: str) -> str:
    asset_ids = approved_row.get("assetIds") if isinstance(approved_row.get("assetIds"), Mapping) else {}
    return str(asset_ids.get(shot) or f"{profile_id}__{shot}__v001")


def _latest_jsonl_by_key(path: Path, key: str, target_values: set[str] | None = None) -> dict[str, Mapping[str, Any]]:
    latest: dict[str, Mapping[str, Any]] = {}
    if not path.exists():
        return latest
    target_bytes = [value.encode("utf-8") for value in sorted(target_values or set())]
    with path.open("rb") as f:
        for raw_line in f:
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            if target_bytes and not any(value in raw_line for value in target_bytes):
                continue
            row = json.loads(raw_line.decode("utf-8"))
            if not isinstance(row, Mapping):
                continue
            value = row.get(key)
            if value is not None and value != "":
                value_str = str(value)
                if target_values is None or value_str in target_values:
                    latest[value_str] = row
    return latest


def _approved_asset_ids(approved_rows: list[dict[str, Any]]) -> set[str]:
    asset_ids: set[str] = set()
    for approved_row in approved_rows:
        profile_id = str(approved_row.get("profileId") or "")
        if not profile_id:
            continue
        for shot in SHOT_ORDER:
            asset_ids.add(_asset_id_from_approved(approved_row, profile_id, shot))
    return asset_ids


def load_approval_evidence_inputs(root: Path | str | None = None) -> dict[str, Any]:
    paths = pipeline_paths(root)
    asset_manifest_rows = _manifest_rows(root)
    file_qa_rows = read_jsonl(paths.manifests / "file_qa_manifest.jsonl")
    asset_qa_rows = read_jsonl(paths.manifests / "asset_qa_manifest.jsonl")
    identity_qa_rows = read_jsonl(paths.manifests / "identity_qa_manifest.jsonl")
    approved_rows = read_jsonl(paths.manifests / "approved_identity_manifest.jsonl")
    generation_by_asset_id = _latest_jsonl_by_key(
        paths.manifests / "generation_manifest.jsonl",
        "assetId",
        _approved_asset_ids(approved_rows),
    )
    return {
        "assetManifestRows": asset_manifest_rows,
        "generationRows": [],
        "fileQaRows": file_qa_rows,
        "assetQaRows": asset_qa_rows,
        "identityQaRows": identity_qa_rows,
        "approvedIdentityRows": approved_rows,
        "assetById": _latest_by_key(asset_manifest_rows, "assetId"),
        "generationByAssetId": generation_by_asset_id,
        "fileQaByAssetId": _latest_by_key(file_qa_rows, "assetId"),
        "assetQaByAssetId": _latest_by_key(asset_qa_rows, "assetId"),
        "identityQaByProfileId": _latest_by_key(identity_qa_rows, "profileId"),
        "approvedByProfileId": _latest_by_key(approved_rows, "profileId"),
        "transactionByAssetId": _latest_transaction_by_asset(root),
    }


def evaluate_approved_identity_evidence(root: Path | str | None = None) -> dict[str, Any]:
    inputs = load_approval_evidence_inputs(root)
    evaluated: list[dict[str, Any]] = []
    valid: list[dict[str, Any]] = []
    invalid_identities: list[dict[str, Any]] = []
    invalid_assets: list[dict[str, Any]] = []

    for approved_row in inputs["approvedIdentityRows"]:
        if not isinstance(approved_row, Mapping):
            continue
        profile_id = str(approved_row.get("profileId") or "")
        if not profile_id:
            invalid_identities.append({"profileId": "", "reasons": ["approved_identity_missing_identity_qa"]})
            continue
        identity_qa = inputs["identityQaByProfileId"].get(profile_id, {})
        identity_reasons: set[str] = set()
        asset_decisions: dict[str, str] = {}
        asset_ids: dict[str, str] = {}
        final_paths: dict[str, str] = {}
        asset_rows_for_identity: list[Mapping[str, Any]] = []

        if not identity_qa:
            identity_reasons.add("approved_identity_missing_identity_qa")
        else:
            decision = _identity_decision(identity_qa)
            if decision == "needs_review":
                identity_reasons.add("needs_review_counted")
            elif decision == "rejected":
                identity_reasons.add("rejected_counted")
            elif decision != "approved":
                identity_reasons.add("approved_identity_missing_identity_qa")
            if not _as_bool(identity_qa.get("countsTowardDistribution")):
                identity_reasons.add("needs_review_counted")
            if _as_bool(identity_qa.get("metadataMismatch")):
                identity_reasons.add("metadata_mismatch")
            if str(identity_qa.get("observedLooksLevelBand") or identity_qa.get("targetLooksLevelBand") or "") == "4.4-5.0":
                identity_reasons.add("over_level_4_4_to_5_0_counted")

        for shot in SHOT_ORDER:
            asset_id = _asset_id_from_approved(approved_row, profile_id, shot)
            asset_ids[shot] = asset_id
            asset_manifest = inputs["assetById"].get(asset_id, {})
            generation = inputs["generationByAssetId"].get(asset_id, {})
            file_qa = inputs["fileQaByAssetId"].get(asset_id, {})
            asset_qa = inputs["assetQaByAssetId"].get(asset_id, {})
            asset_reasons: set[str] = set()
            if not asset_manifest:
                asset_reasons.add("approved_asset_not_in_asset_manifest")
            if not generation:
                final_candidate = _resolve_path(root, _row_value(asset_manifest, approved_row, key="finalPath"))
                if not _expected_final_owner(root, asset_manifest or approved_row, final_candidate):
                    asset_reasons.add("approved_asset_not_in_generation_manifest")
            file_evidence = resolve_file_qa_evidence(
                root,
                asset_id,
                active_asset=asset_manifest,
                generation_row=generation,
                file_qa_row=file_qa,
                transaction_receipt=inputs["transactionByAssetId"].get(asset_id, {}),
                expected_profile_id=profile_id,
                expected_shot_type=shot,
            )
            if not file_evidence["ok"]:
                asset_reasons.add("approved_asset_missing_file_qa")
                for reason in file_evidence.get("reasons", []):
                    if reason not in {"file_qa_found_in_state_only"}:
                        asset_reasons.add(reason)
            if not asset_qa:
                asset_reasons.add("approved_asset_missing_visual_qa")
            else:
                visual_decision = _asset_visual_decision(asset_qa)
                if visual_decision == "needs_review":
                    asset_reasons.add("needs_review_counted")
                elif visual_decision == "rejected":
                    asset_reasons.add("rejected_counted")
                elif visual_decision != "approved":
                    asset_reasons.add("approved_asset_missing_visual_qa")
                if _as_bool(asset_qa.get("metadataMismatch")):
                    asset_reasons.add("metadata_mismatch")
                if str(asset_qa.get("observedLooksLevelBand") or asset_qa.get("targetLooksLevelBand") or "") == "4.4-5.0":
                    asset_reasons.add("over_level_4_4_to_5_0_counted")

            row_for_match = generation or asset_manifest or asset_qa or {}
            if row_for_match:
                for key, expected in (("profileId", profile_id), ("shotType", shot)):
                    if str(row_for_match.get(key) or "") and str(row_for_match.get(key) or "") != expected:
                        asset_reasons.add("metadata_mismatch")
                if str(row_for_match.get("assetId") or asset_id) != asset_id:
                    asset_reasons.add("metadata_mismatch")

            final_path = _resolve_path(root, _row_value(generation, asset_manifest, approved_row, key="finalPath"))
            final_paths[shot] = str(final_path) if final_path else ""
            if final_path is None or not final_path.exists():
                asset_reasons.add("approved_identity_missing_final_file")
            else:
                detail = inspect_image_detail(final_path)
                if not detail.get("ok"):
                    asset_reasons.add("approved_identity_missing_final_file")
            if asset_reasons:
                invalid_assets.append(
                    {
                        "profileId": profile_id,
                        "assetId": asset_id,
                        "shotType": shot,
                        "reasons": sorted(asset_reasons),
                    }
                )
                identity_reasons.update(asset_reasons)
                asset_decisions[shot] = "invalid"
            else:
                asset_decisions[shot] = "approved"
                asset_rows_for_identity.append(generation or asset_manifest or asset_qa)

        if set(asset_ids) != set(SHOT_ORDER) or any(asset_decisions.get(shot) != "approved" for shot in SHOT_ORDER):
            identity_reasons.add("less_than_3_approved_shots")

        anchor = identity_qa or approved_row or (asset_rows_for_identity[0] if asset_rows_for_identity else {})
        face_type = normalize_face_type(
            str(
                _row_value(
                    identity_qa,
                    approved_row,
                    *(asset_rows_for_identity or []),
                    key="observedFaceType",
                    default="",
                )
                or _row_value(identity_qa, approved_row, *(asset_rows_for_identity or []), key="faceType", default="")
                or target_face_type(anchor)
            )
        )
        looks_band = str(
            _row_value(
                identity_qa,
                approved_row,
                *(asset_rows_for_identity or []),
                key="observedLooksLevelBand",
                default="",
            )
            or _row_value(identity_qa, approved_row, *(asset_rows_for_identity or []), key="looksLevelBand", default="")
            or target_looks_level_band(anchor)
        )
        first_asset = asset_rows_for_identity[0] if asset_rows_for_identity else {}
        has_eyewear = _as_bool(_row_value(first_asset, approved_row, identity_qa, key="hasEyewear"), default=False)
        eyewear_group = str(_row_value(first_asset, approved_row, identity_qa, key="eyewearGroup", default="glasses" if has_eyewear else "none"))
        season = str(_row_value(first_asset, approved_row, identity_qa, key="season", default=""))
        evaluated_identity = {
            "profileId": profile_id,
            "gender": str(_row_value(anchor, approved_row, key="gender", default=profile_id.split("_", 1)[0] if "_" in profile_id else "")),
            "numericId": str(_row_value(anchor, approved_row, key="numericId", default="")),
            "targetFaceType": normalize_face_type(str(_row_value(anchor, key="targetFaceType", default=target_face_type(anchor)))),
            "targetLooksLevel": target_looks_level(anchor) or _row_value(anchor, key="targetLooksLevel", default=""),
            "targetLooksLevelBand": str(_row_value(anchor, key="targetLooksLevelBand", default=target_looks_level_band(anchor))),
            "observedFaceType": face_type,
            "countedFaceType": face_type,
            "faceType": face_type,
            "observedLooksLevelBand": looks_band,
            "countedLooksLevelBand": looks_band,
            "looksLevelBand": looks_band,
            "assetIds": asset_ids,
            "finalPaths": final_paths,
            "identityScope": str(_row_value(anchor, approved_row, key="identityScope", default="production")),
            "isReserve": _as_bool(_row_value(anchor, approved_row, key="isReserve")),
            "reserveStatus": str(_row_value(anchor, approved_row, key="reserveStatus", default="")),
            "completeIdentityDecision": _identity_decision(identity_qa) or "missing",
            "sameIdentity": _as_bool(identity_qa.get("sameIdentity"), default=True),
            "countsTowardDistribution": not identity_reasons,
            "completeApproved": not identity_reasons,
            "approvedShotCount": sum(1 for decision in asset_decisions.values() if decision == "approved"),
            "assetDecisions": asset_decisions,
            "missingShotTypes": [shot for shot in SHOT_ORDER if asset_decisions.get(shot) != "approved"],
            "metadataMismatch": "metadata_mismatch" in identity_reasons,
            "overLevel": "over_level_4_4_to_5_0_counted" in identity_reasons,
            "needsReview": "needs_review_counted" in identity_reasons,
            "rejected": "rejected_counted" in identity_reasons,
            "hasEyewear": has_eyewear,
            "eyewearGroup": eyewear_group,
            "eyewearBucket": "with_eyewear" if has_eyewear or eyewear_group == "glasses" else "without_eyewear",
            "season": season,
            "reasons": sorted(identity_reasons),
        }
        evaluated.append(evaluated_identity)
        if identity_reasons:
            invalid_identities.append({"profileId": profile_id, "reasons": sorted(identity_reasons)})
        else:
            valid.append(evaluated_identity)

    return {
        "inputs": inputs,
        "approvedManifestRows": len(inputs["approvedIdentityRows"]),
        "validIdentities": valid,
        "evaluatedIdentities": evaluated,
        "invalidApprovedIdentities": invalid_identities,
        "invalidApprovedAssets": invalid_assets,
    }
