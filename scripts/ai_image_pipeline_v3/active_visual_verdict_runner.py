from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .completion import completion_check
from .config import SHOT_ORDER, ensure_base_dirs, now_utc, pipeline_paths, read_jsonl, to_portable_path
from .contact_sheet import (
    build_current_chunk_whitelist,
    generate_chunk_contact_sheets,
    generate_grouped_contact_sheets,
    generate_identity_contact_sheets,
    generate_strict_chunk_contact_sheets,
    write_current_chunk_whitelists,
)
from .distribution_audit import audit_distribution
from .manifest import load_generation_manifest
from .visual_verdict import (
    ASSET_QA_TYPE,
    DISTRIBUTION_QA_TYPE,
    IDENTITY_QA_TYPE,
    apply_asset_qa,
    apply_distribution_audit,
    apply_identity_qa,
)


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
VALID_EXEC_MODES = {"auto", "direct", "exec"}
VALID_IMAGE_ARG_MODES = {"auto", "image", "short_i"}
COMPACT_METADATA_PROMPT_BUDGET = 20000
UNKNOWN_TARGET_VALUES = {"", "unknown", "null", "none"}
COMPACT_METADATA_FIELDS = (
    "assetId",
    "profileId",
    "gender",
    "numericId",
    "shotType",
    "targetFaceType",
    "targetLooksLevelBand",
    "targetLooksLevel",
    "eyewearGroup",
    "hasEyewear",
    "targetHasEyewear",
    "targetEyewearGroup",
    "targetEyewear",
    "targetCanonicalEyewear",
    "targetShotEyewearExpected",
    "temporaryEyewearAllowed",
    "temporaryEyewearApplied",
    "season",
    "fashionCategory",
    "locationType",
    "promptHash",
    "finalPath",
    "fileQaStatus",
)


def default_codex_bin(env: Mapping[str, str] | None = None) -> str:
    """Return a Codex executable name that works from Python subprocesses.

    On this Windows/MSYS setup, Python subprocess timeouts can leave orphaned
    children when they launch the npm/cmd shim. Prefer the native Codex
    executable when it is available, then fall back to the explicit override or
    command shim.
    """
    values = env or os.environ
    if os.name == "nt":
        native = Path.home() / "AppData" / "Local" / "OpenAI" / "Codex" / "bin" / "codex.exe"
        if native.exists():
            return str(native)
    explicit = str(values.get("CODEX_BIN") or "").strip()
    if explicit:
        return explicit
    if os.name == "nt":
        if shutil.which("codex.exe"):
            return "codex.exe"
        if shutil.which("codex.cmd"):
            return "codex.cmd"
        npm_prefix = Path.home() / "AppData" / "Roaming" / "npm" / "codex.cmd"
        if npm_prefix.exists():
            return str(npm_prefix)
    return "codex"


class ActiveVisualVerdictError(RuntimeError):
    pass


@dataclass(frozen=True)
class CodexCommandForm:
    exec_mode: str
    image_arg_mode: str


@dataclass(frozen=True)
class ActiveVisualConfig:
    codex_bin: str
    image_arg_mode: str
    exec_mode: str
    timeout_sec: int
    max_images_per_call: int
    max_sheets_per_run: int
    strict: bool

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "ActiveVisualConfig":
        values = env or os.environ
        image_arg_mode = str(values.get("CODEX_IMAGE_ARG_MODE") or "auto").strip()
        exec_mode = str(values.get("CODEX_EXEC_MODE") or "auto").strip()
        if image_arg_mode not in VALID_IMAGE_ARG_MODES:
            raise ValueError(f"Unsupported CODEX_IMAGE_ARG_MODE: {image_arg_mode}")
        if exec_mode not in VALID_EXEC_MODES:
            raise ValueError(f"Unsupported CODEX_EXEC_MODE: {exec_mode}")
        return cls(
            codex_bin=default_codex_bin(values),
            image_arg_mode=image_arg_mode,
            exec_mode=exec_mode,
            timeout_sec=int(values.get("CODEX_VISUAL_QA_TIMEOUT_SEC") or "900"),
            max_images_per_call=max(1, int(values.get("CODEX_VISUAL_QA_MAX_IMAGES_PER_CALL") or "1")),
            max_sheets_per_run=max(1, int(values.get("CODEX_VISUAL_QA_MAX_SHEETS_PER_RUN") or "999")),
            strict=str(values.get("CODEX_VISUAL_QA_STRICT") or "1") != "0",
        )


@dataclass(frozen=True)
class ContactSheetEntry:
    sheet_id: str
    sheet_path: Path
    sheet_type: str
    asset_ids: tuple[str, ...] = ()
    profile_ids: tuple[str, ...] = ()


def _timestamp() -> str:
    return re.sub(r"[^0-9A-Za-z]", "", now_utc())


def visual_dir(root: Path | str | None = None) -> Path:
    return pipeline_paths(root).reports / "visual_verdict"


def write_manual_review_flag(root: Path | str | None, reason: str, details: Mapping[str, Any] | None = None) -> Path:
    paths = pipeline_paths(root)
    ensure_base_dirs(paths)
    path = paths.manifests / "manual_review_required.flag"
    payload = {
        "schemaVersion": "seolleyeon_active_visual_manual_review_v3",
        "reason": reason,
        "details": dict(details or {}),
        "updatedAt": now_utc(),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _load_asset_whitelist_payload(
    root: Path | str | None,
    *,
    chunk_id: str,
    asset_whitelist: Path | str | None = None,
) -> dict[str, Any]:
    if asset_whitelist:
        payload = json.loads(Path(asset_whitelist).read_text(encoding="utf-8-sig"))
    else:
        payload = build_current_chunk_whitelist(root, chunk_id)
    if str(payload.get("chunkId") or "") != str(chunk_id):
        raise ValueError(f"asset whitelist chunkId mismatch: expected {chunk_id}, got {payload.get('chunkId') or '<missing>'}")
    return payload


def _scope_from_whitelist(payload: Mapping[str, Any]) -> tuple[set[str], set[str], dict[str, dict[str, Any]]]:
    assets = [dict(row) for row in payload.get("assets", []) if isinstance(row, Mapping)]
    allowed_asset_ids = {str(row.get("assetId") or "") for row in assets if str(row.get("assetId") or "")}
    allowed_profile_ids = {str(row.get("profileId") or "") for row in assets if str(row.get("profileId") or "")}
    expected_by_asset = {str(row.get("assetId") or ""): row for row in assets if str(row.get("assetId") or "")}
    return allowed_asset_ids, allowed_profile_ids, expected_by_asset


def _unknown_target(value: Any) -> bool:
    return str(value or "").strip().lower() in UNKNOWN_TARGET_VALUES


def _save_invalid_payload(root: Path | str | None, qa_slug: str, payload: Mapping[str, Any], reason: str, details: Mapping[str, Any]) -> tuple[Path, Path]:
    invalid_dir = visual_dir(root) / "invalid"
    invalid_dir.mkdir(parents=True, exist_ok=True)
    timestamp = _timestamp()
    payload_path = invalid_dir / f"{qa_slug}_out_of_scope_{timestamp}.json"
    reason_path = invalid_dir / f"{qa_slug}_out_of_scope_{timestamp}.reason.json"
    payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    reason_path.write_text(
        json.dumps(
            {
                "schemaVersion": "seolleyeon_visual_qa_invalid_payload_v3",
                "reason": reason,
                "details": dict(details),
                "invalidPayloadPath": to_portable_path(payload_path),
                "createdAt": now_utc(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return payload_path, reason_path


def mark_latest_asset_qa_invalid_if_out_of_scope(
    root: Path | str | None,
    *,
    chunk_id: str,
    asset_whitelist: Path | str | None = None,
) -> dict[str, Any]:
    latest = visual_dir(root) / "asset_qa_latest.json"
    if not latest.exists():
        return {"checked": False, "invalidated": False, "reason": "asset_qa_latest_missing"}
    try:
        payload = json.loads(latest.read_text(encoding="utf-8-sig"))
    except Exception as exc:  # noqa: BLE001 - keep bad payload untouched; strict apply will reject it.
        return {"checked": True, "invalidated": False, "reason": f"asset_qa_latest_unreadable:{exc}"}
    whitelist = _load_asset_whitelist_payload(root, chunk_id=chunk_id, asset_whitelist=asset_whitelist)
    allowed_asset_ids, _, _ = _scope_from_whitelist(whitelist)
    rows = payload.get("assets") if isinstance(payload, Mapping) else []
    if not isinstance(rows, list):
        return {"checked": True, "invalidated": False, "reason": "asset_qa_latest_has_no_assets_array"}
    offending = [str(row.get("assetId") or "") for row in rows if isinstance(row, Mapping) and str(row.get("assetId") or "") not in allowed_asset_ids]
    if not offending:
        return {"checked": True, "invalidated": False, "payloadAssetCount": len(rows)}
    payload_path, reason_path = _save_invalid_payload(
        root,
        "asset_qa",
        payload,
        "out_of_scope_asset_in_chunk_visual_qa",
        {
            "firstOffendingAssetId": offending[0],
            "offendingAssetIds": sorted(set(offending)),
            "chunkId": chunk_id,
            "expectedWhitelistSize": len(allowed_asset_ids),
            "payloadAssetCount": len(rows),
        },
    )
    latest.write_text(
        json.dumps(
            {
                "qaType": f"{ASSET_QA_TYPE}_invalid",
                "invalid": True,
                "reason": "out_of_scope_asset_in_chunk_visual_qa",
                "chunkId": chunk_id,
                "invalidPayloadPath": to_portable_path(payload_path),
                "reasonPath": to_portable_path(reason_path),
                "updatedAt": now_utc(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return {
        "checked": True,
        "invalidated": True,
        "firstOffendingAssetId": offending[0],
        "invalidPayloadPath": to_portable_path(payload_path),
        "reasonPath": to_portable_path(reason_path),
    }


def strip_code_fences(text: str) -> str:
    stripped = text.strip()
    fence = re.fullmatch(r"```(?:json|JSON)?\s*(.*?)\s*```", stripped, flags=re.DOTALL)
    return fence.group(1).strip() if fence else stripped


def strip_codex_cli_noise(text: str) -> str:
    lines = text.splitlines()
    noise = re.compile(r"^SUCCESS: The process with PID \d+ \(child process of PID \d+\) has been terminated\.$")
    while lines and (not lines[0].strip() or noise.fullmatch(lines[0].strip())):
        lines.pop(0)
    return "\n".join(lines).strip()


def extract_json_object(text: str) -> dict[str, Any]:
    candidate = strip_code_fences(strip_codex_cli_noise(text))
    decoder = json.JSONDecoder()
    index = candidate.find("{")
    if index < 0:
        raise ValueError("No JSON object found in Codex output.")
    payload, end = decoder.raw_decode(candidate[index:])
    remainder = candidate[index + end :].strip()
    if remainder:
        if remainder.startswith("{"):
            raise ValueError("Multiple top-level JSON objects found in Codex output.")
        raise ValueError("Non-JSON text found after JSON object.")
    if candidate[:index].strip():
        raise ValueError("Non-JSON text found before JSON object.")
    if not isinstance(payload, dict):
        raise ValueError("Top-level JSON value must be an object.")
    return payload


def validate_asset_qa_json(payload: Mapping[str, Any], *, allow_empty: bool = False) -> None:
    if payload.get("qaType") != ASSET_QA_TYPE:
        raise ValueError(f"Unexpected qaType: {payload.get('qaType') or '<missing>'}")
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    if not allow_empty and int(payload.get("checked") or summary.get("checked") or 1) <= 0:
        raise ValueError("Asset visual QA checked:0 is invalid.")
    assets = payload.get("assets")
    if not isinstance(assets, list):
        raise ValueError("Asset visual QA requires assets[].")
    if not assets and not allow_empty:
        raise ValueError("Asset visual QA assets[] is empty.")
    for index, asset in enumerate(assets):
        if not isinstance(asset, Mapping):
            raise ValueError(f"assets[{index}] must be an object.")
        for key in ("assetId", "profileId", "gender", "shotType", "observedFaceType", "observedLooksLevelBand", "decision"):
            if key not in asset:
                raise ValueError(f"assets[{index}] missing {key}.")


def validate_identity_qa_json(payload: Mapping[str, Any], *, allow_empty: bool = False) -> None:
    if payload.get("qaType") != IDENTITY_QA_TYPE:
        raise ValueError(f"Unexpected qaType: {payload.get('qaType') or '<missing>'}")
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    if not allow_empty and int(payload.get("checked") or summary.get("checked") or 1) <= 0:
        raise ValueError("Identity visual QA checked:0 is invalid.")
    identities = payload.get("identities")
    if not isinstance(identities, list):
        raise ValueError("Identity visual QA requires identities[].")
    if not identities and not allow_empty:
        raise ValueError("Identity visual QA identities[] is empty.")
    for index, identity in enumerate(identities):
        if not isinstance(identity, Mapping):
            raise ValueError(f"identities[{index}] must be an object.")
        for key in ("profileId", "gender", "assetIds", "assetDecisions", "sameIdentity", "completeIdentityDecision"):
            if key not in identity:
                raise ValueError(f"identities[{index}] missing {key}.")


def validate_distribution_qa_json(payload: Mapping[str, Any]) -> None:
    if payload.get("qaType") != DISTRIBUTION_QA_TYPE:
        raise ValueError(f"Unexpected qaType: {payload.get('qaType') or '<missing>'}")
    for key in (
        "finalDecision",
        "approvedCompleteIdentityCount",
        "approvedImageCount",
        "femaleApprovedIdentityCount",
        "maleApprovedIdentityCount",
        "globalFaceTypeCounts",
        "globalLooksLevelBandCounts",
        "invalidIdentities",
        "nextGenerationDirective",
    ):
        if key not in payload:
            raise ValueError(f"Distribution visual QA missing {key}.")


def _raise_scope_failure(
    root: Path | str | None,
    qa_slug: str,
    payload: Mapping[str, Any],
    reason: str,
    details: Mapping[str, Any],
) -> None:
    payload_path, reason_path = _save_invalid_payload(root, qa_slug, payload, reason, details)
    write_manual_review_flag(
        root,
        reason,
        {
            **dict(details),
            "invalidPayloadPath": to_portable_path(payload_path),
            "reasonPath": to_portable_path(reason_path),
        },
    )
    raise ActiveVisualVerdictError(f"{reason}: {details.get('firstOffendingAssetId') or details.get('firstOffendingProfileId') or details.get('message') or ''}".rstrip())


def validate_asset_payload_scope(
    payload: Mapping[str, Any],
    *,
    root: Path | str | None,
    chunk_id: str,
    allowed_asset_ids: set[str],
    allowed_profile_ids: set[str],
    expected_by_asset: Mapping[str, Mapping[str, Any]],
) -> None:
    assets = payload.get("assets")
    if not isinstance(assets, list):
        return
    seen: set[str] = set()
    duplicate_asset_ids: list[str] = []
    out_of_scope_asset_ids: list[str] = []
    out_of_scope_profile_ids: list[str] = []
    mismatches: list[dict[str, str]] = []
    target_unknowns: list[dict[str, str]] = []
    target_mismatches: list[dict[str, str]] = []
    for row in assets:
        if not isinstance(row, Mapping):
            continue
        asset_id = str(row.get("assetId") or "")
        profile_id = str(row.get("profileId") or "")
        if asset_id in seen:
            duplicate_asset_ids.append(asset_id)
        seen.add(asset_id)
        if asset_id not in allowed_asset_ids:
            out_of_scope_asset_ids.append(asset_id)
            continue
        if profile_id not in allowed_profile_ids:
            out_of_scope_profile_ids.append(profile_id)
        expected = expected_by_asset.get(asset_id, {})
        for key in ("profileId", "gender", "shotType"):
            expected_value = str(expected.get(key) or "")
            observed_value = str(row.get(key) or "")
            if expected_value and observed_value and expected_value != observed_value:
                mismatches.append({"assetId": asset_id, "field": key, "expected": expected_value, "observed": observed_value})
        for key in ("targetFaceType", "targetLooksLevelBand"):
            expected_value = str(expected.get(key) or "").strip()
            if _unknown_target(expected_value):
                continue
            observed_value = str(row.get(key) or "").strip()
            if _unknown_target(observed_value):
                target_unknowns.append({"assetId": asset_id, "field": key, "expected": expected_value, "observed": observed_value or "unknown"})
            elif observed_value != expected_value:
                target_mismatches.append({"assetId": asset_id, "field": key, "expected": expected_value, "observed": observed_value})
    if len(assets) > len(allowed_asset_ids):
        _raise_scope_failure(
            root,
            "asset_qa",
            payload,
            "asset_visual_qa_payload_exceeds_chunk_scope",
            {
                "chunkId": chunk_id,
                "payloadAssetCount": len(assets),
                "allowedAssetCount": len(allowed_asset_ids),
                "message": "payload contains more rows than current chunk whitelist",
            },
        )
    if out_of_scope_asset_ids:
        _raise_scope_failure(
            root,
            "asset_qa",
            payload,
            "asset_visual_qa_out_of_scope_payload",
            {
                "chunkId": chunk_id,
                "firstOffendingAssetId": out_of_scope_asset_ids[0],
                "outOfScopeAssetIds": sorted(set(out_of_scope_asset_ids)),
                "allowedAssetCount": len(allowed_asset_ids),
                "payloadAssetCount": len(assets),
            },
        )
    if duplicate_asset_ids:
        _raise_scope_failure(root, "asset_qa", payload, "asset_visual_qa_duplicate_asset_id", {"chunkId": chunk_id, "duplicateAssetIds": sorted(set(duplicate_asset_ids))})
    if out_of_scope_profile_ids:
        _raise_scope_failure(root, "asset_qa", payload, "asset_visual_qa_out_of_scope_profile", {"chunkId": chunk_id, "firstOffendingProfileId": out_of_scope_profile_ids[0], "outOfScopeProfileIds": sorted(set(out_of_scope_profile_ids))})
    if mismatches:
        _raise_scope_failure(root, "asset_qa", payload, "asset_visual_qa_plan_mismatch", {"chunkId": chunk_id, "mismatches": mismatches[:20]})
    if target_unknowns:
        _raise_scope_failure(
            root,
            "asset_qa",
            payload,
            "visual_qa_target_metadata_unknown",
            {
                "chunkId": chunk_id,
                "firstOffendingAssetId": target_unknowns[0]["assetId"],
                "targetUnknowns": target_unknowns[:20],
            },
        )
    if target_mismatches:
        _raise_scope_failure(
            root,
            "asset_qa",
            payload,
            "visual_qa_target_metadata_mismatch",
            {
                "chunkId": chunk_id,
                "firstOffendingAssetId": target_mismatches[0]["assetId"],
                "targetMismatches": target_mismatches[:20],
            },
        )
    missing = sorted(allowed_asset_ids - seen)
    if missing:
        _raise_scope_failure(
            root,
            "asset_qa",
            payload,
            "asset_visual_qa_missing_whitelisted_assets",
            {"chunkId": chunk_id, "missingAssetIds": missing, "allowedAssetCount": len(allowed_asset_ids), "payloadAssetCount": len(assets)},
        )


def validate_identity_payload_scope(
    payload: Mapping[str, Any],
    *,
    root: Path | str | None,
    chunk_id: str,
    allowed_asset_ids: set[str],
    allowed_profile_ids: set[str],
) -> None:
    identities = payload.get("identities")
    if not isinstance(identities, list):
        return
    seen: set[str] = set()
    out_of_scope_profiles: list[str] = []
    out_of_scope_assets: list[str] = []
    duplicates: list[str] = []
    for row in identities:
        if not isinstance(row, Mapping):
            continue
        profile_id = str(row.get("profileId") or "")
        if profile_id in seen:
            duplicates.append(profile_id)
        seen.add(profile_id)
        if profile_id not in allowed_profile_ids:
            out_of_scope_profiles.append(profile_id)
        asset_ids = row.get("assetIds")
        values: list[str] = []
        if isinstance(asset_ids, Mapping):
            values.extend(str(value) for value in asset_ids.values())
        elif isinstance(asset_ids, list):
            values.extend(str(value) for value in asset_ids)
        out_of_scope_assets.extend(asset_id for asset_id in values if asset_id and asset_id not in allowed_asset_ids)
    if out_of_scope_profiles:
        _raise_scope_failure(root, "identity_qa", payload, "identity_visual_qa_out_of_scope_payload", {"chunkId": chunk_id, "firstOffendingProfileId": out_of_scope_profiles[0], "outOfScopeProfileIds": sorted(set(out_of_scope_profiles))})
    if out_of_scope_assets:
        _raise_scope_failure(root, "identity_qa", payload, "identity_visual_qa_out_of_scope_asset", {"chunkId": chunk_id, "firstOffendingAssetId": out_of_scope_assets[0], "outOfScopeAssetIds": sorted(set(out_of_scope_assets))})
    if duplicates:
        _raise_scope_failure(root, "identity_qa", payload, "identity_visual_qa_duplicate_profile_id", {"chunkId": chunk_id, "duplicateProfileIds": sorted(set(duplicates))})
    missing = sorted(allowed_profile_ids - seen)
    if missing:
        _raise_scope_failure(root, "identity_qa", payload, "identity_visual_qa_missing_whitelisted_profiles", {"chunkId": chunk_id, "missingProfileIds": missing})


def _summary_counts(items: Sequence[Mapping[str, Any]], decision_key: str) -> dict[str, int]:
    approved = sum(1 for item in items if item.get(decision_key) == "approved")
    needs_review = sum(1 for item in items if item.get(decision_key) == "needs_review")
    rejected = sum(1 for item in items if item.get(decision_key) == "rejected")
    return {"approved": approved, "needs_review": needs_review, "rejected": rejected}


def _asset_downgrade_summary(raw_assets: Sequence[Mapping[str, Any]], applied: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(applied, Mapping):
        return {"rawApprovedButAppliedDowngraded": 0, "topReasons": []}
    output_manifest = str(applied.get("output_manifest") or "")
    applied_rows = read_jsonl(Path(output_manifest)) if output_manifest else []
    applied_by_asset = {str(row.get("assetId") or ""): row for row in applied_rows if str(row.get("assetId") or "")}
    reasons: dict[str, int] = {}
    downgraded = 0
    for raw in raw_assets:
        asset_id = str(raw.get("assetId") or "")
        if raw.get("decision") != "approved" or asset_id not in applied_by_asset:
            continue
        final_decision = str(applied_by_asset[asset_id].get("finalDecision") or "")
        if final_decision == "approved":
            continue
        downgraded += 1
        applied_row = applied_by_asset[asset_id]
        for reason in applied_row.get("needsReviewReasons") or []:
            key = f"needsReview:{reason}"
            reasons[key] = reasons.get(key, 0) + 1
        for reason in applied_row.get("hardRejectReasons") or []:
            key = f"hardReject:{reason}"
            reasons[key] = reasons.get(key, 0) + 1
        mismatch_fields = applied_row.get("mismatchFields") or []
        if mismatch_fields:
            key = "metadata_mismatch:" + ",".join(str(item) for item in mismatch_fields)
            reasons[key] = reasons.get(key, 0) + 1
    return {
        "rawApprovedButAppliedDowngraded": downgraded,
        "topReasons": sorted(reasons.items(), key=lambda item: (-item[1], item[0]))[:10],
    }


def _same_payload(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    return json.dumps(left, ensure_ascii=False, sort_keys=True) == json.dumps(right, ensure_ascii=False, sort_keys=True)


def merge_asset_parts(parts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_asset: dict[str, dict[str, Any]] = {}
    for part in parts:
        validate_asset_qa_json(part)
        for row in part["assets"]:
            asset = dict(row)
            asset_id = str(asset.get("assetId") or "")
            if not asset_id:
                raise ValueError("Asset QA part contains blank assetId.")
            existing = by_asset.get(asset_id)
            if existing and not _same_payload(existing, asset):
                raise ValueError(f"Conflicting duplicate assetId in visual QA parts: {asset_id}")
            by_asset[asset_id] = asset
    assets = list(by_asset.values())
    counts = _summary_counts(assets, "decision")
    return {
        "qaType": ASSET_QA_TYPE,
        "sheetId": "active_visual_asset_qa_merged",
        "assets": assets,
        "summary": {
            "approvedCount": counts["approved"],
            "needsReviewCount": counts["needs_review"],
            "rejectedCount": counts["rejected"],
            "hardRejectCount": sum(1 for row in assets if row.get("hardReject") is True),
            "metadataMismatchCount": sum(1 for row in assets if row.get("metadataMismatch") is True),
        },
    }


def merge_identity_parts(parts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_profile: dict[str, dict[str, Any]] = {}
    for part in parts:
        validate_identity_qa_json(part)
        for row in part["identities"]:
            identity = dict(row)
            profile_id = str(identity.get("profileId") or "")
            if not profile_id:
                raise ValueError("Identity QA part contains blank profileId.")
            existing = by_profile.get(profile_id)
            if existing and not _same_payload(existing, identity):
                raise ValueError(f"Conflicting duplicate profileId in visual QA parts: {profile_id}")
            by_profile[profile_id] = identity
    identities = list(by_profile.values())
    counts = _summary_counts(identities, "completeIdentityDecision")
    return {
        "qaType": IDENTITY_QA_TYPE,
        "sheetId": "active_visual_identity_qa_merged",
        "identities": identities,
        "summary": {
            "approvedCompleteIdentities": counts["approved"],
            "needsReviewIdentities": counts["needs_review"],
            "rejectedIdentities": counts["rejected"],
            "missingShotIdentities": sum(1 for row in identities if "missing" in str(row.get("assetDecisions") or "")),
            "identityMismatchCount": sum(1 for row in identities if row.get("sameIdentity") is False),
        },
    }


def build_codex_args(
    prompt: str,
    image_paths: Sequence[Path | str],
    *,
    config: ActiveVisualConfig,
    form: CodexCommandForm,
    root: Path | str | None = None,
    prompt_via_stdin: bool = False,
) -> list[str]:
    args = [config.codex_bin]
    if form.exec_mode == "exec":
        args.append("exec")
    if image_paths:
        image_arg = "--image" if form.image_arg_mode == "image" else "-i"
        args.extend([image_arg, ",".join(str(Path(path).resolve()) for path in image_paths)])
    if root is not None:
        args.extend(["-C", str(Path(root).resolve())])
    if not prompt_via_stdin:
        args.append(prompt)
    return args


def _run_help(args: list[str], *, run_func: Callable[..., subprocess.CompletedProcess[str]]) -> tuple[int, str]:
    try:
        result = run_func(args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30, shell=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, str(exc)
    return int(result.returncode), f"{result.stdout or ''}\n{result.stderr or ''}"


def discover_command_forms(
    *,
    root: Path | str | None = None,
    config: ActiveVisualConfig | None = None,
    run_func: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> list[CodexCommandForm]:
    del root
    config = config or ActiveVisualConfig.from_env()
    forms: list[CodexCommandForm] = []
    direct_rc, direct_help = _run_help([config.codex_bin, "--help"], run_func=run_func)
    exec_rc, exec_help = _run_help([config.codex_bin, "exec", "--help"], run_func=run_func)

    def allowed_exec(value: str) -> bool:
        return config.exec_mode in {"auto", value}

    def allowed_image(value: str) -> bool:
        return config.image_arg_mode in {"auto", value}

    def add_if_supported(exec_mode: str, image_mode: str, help_text: str, rc: int) -> None:
        if rc != 0 or not allowed_exec(exec_mode) or not allowed_image(image_mode):
            return
        needle = "--image" if image_mode == "image" else "-i"
        if needle in help_text or config.image_arg_mode == image_mode:
            form = CodexCommandForm(exec_mode=exec_mode, image_arg_mode=image_mode)
            if form not in forms:
                forms.append(form)

    add_if_supported("exec", "image", exec_help, exec_rc)
    add_if_supported("exec", "short_i", exec_help, exec_rc)
    add_if_supported("direct", "image", direct_help, direct_rc)
    add_if_supported("direct", "short_i", direct_help, direct_rc)
    return forms


def probe_codex_image_input(
    *,
    root: Path | str | None = None,
    config: ActiveVisualConfig | None = None,
    run_func: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, Any]:
    config = config or ActiveVisualConfig.from_env()
    forms = discover_command_forms(root=root, config=config, run_func=run_func)
    result = {
        "available": bool(forms),
        "forms": [form.__dict__ for form in forms],
        "codexBin": config.codex_bin,
        "manualCommands": manual_visual_commands(root=root, codex_bin=config.codex_bin),
    }
    if not forms:
        result["manualReviewFlag"] = to_portable_path(write_manual_review_flag(root, "codex_image_input_unavailable", result))
    return result


def manual_visual_commands(root: Path | str | None = None, codex_bin: str | None = None) -> dict[str, str]:
    base = pipeline_paths(root).root
    bin_name = codex_bin or default_codex_bin()
    return {
        "assetQA": (
            f'{bin_name} --image "<asset_contact_sheet.png>" "Use '
            f'{base / "ai_image/prompts/VISUAL_VERDICT_ASSET_QA_PROMPT.md"} and return strict '
            f'JSON qaType={ASSET_QA_TYPE}. Save to ai_image/reports/visual_verdict/asset_qa_latest.json."'
        ),
        "identityQA": (
            f'{bin_name} --image "<identity_contact_sheet.png>" "Use '
            f'{base / "ai_image/prompts/VISUAL_VERDICT_IDENTITY_QA_PROMPT.md"} and return strict '
            f'JSON qaType={IDENTITY_QA_TYPE}. Save to ai_image/reports/visual_verdict/identity_qa_latest.json."'
        ),
        "distributionQA": (
            f'{bin_name} "Use ai_image/prompts/VISUAL_VERDICT_DISTRIBUTION_AUDIT_PROMPT.md, the visual QA manifests, '
            f'and latest_distribution_audit.json. Return strict JSON qaType={DISTRIBUTION_QA_TYPE}."'
        ),
    }


def generated_image_rows(root: Path | str | None = None) -> list[dict[str, Any]]:
    paths = pipeline_paths(root)
    rows: list[dict[str, Any]] = []
    for row in load_generation_manifest(paths):
        status = str(row.get("status") or "")
        if status in {"obsolete", "replaced"}:
            continue
        for key in ("finalPath", "localPath", "approvedPath"):
            value = row.get(key)
            if value and Path(str(value)).exists():
                enriched = dict(row)
                enriched["_visualImagePath"] = str(value)
                rows.append(enriched)
                break
    return rows


def ensure_contact_sheets(
    root: Path | str | None = None,
    *,
    chunk_id: str | None = None,
    strict_chunk_scope: bool = False,
    asset_whitelist: Path | str | None = None,
    contact_sheet_index: Path | str | None = None,
) -> list[ContactSheetEntry]:
    if not generated_image_rows(root):
        write_manual_review_flag(root, "no_generated_images_for_visual_qa")
        raise ActiveVisualVerdictError("No generated/recovered images exist for active visual QA.")
    paths = pipeline_paths(root)
    ensure_base_dirs(paths)
    if strict_chunk_scope:
        if not chunk_id:
            raise ActiveVisualVerdictError("--chunk_id is required with strict chunk visual QA scope.")
        if contact_sheet_index:
            entries = _entries_from_contact_sheet_index(contact_sheet_index, chunk_id=chunk_id)
        else:
            generate_strict_chunk_contact_sheets(root=root, chunk_id=chunk_id, asset_whitelist=asset_whitelist)
            entries = build_contact_sheet_index(root=root, chunk_id=chunk_id)
        if not entries:
            write_manual_review_flag(root, "strict_chunk_contact_sheets_missing", {"chunkId": chunk_id})
            raise ActiveVisualVerdictError("No strict chunk contact sheets found.")
        return entries
    sheet_dir = paths.reports / "contact_sheets"
    existing = [path for path in sheet_dir.rglob("*") if path.suffix.lower() in IMAGE_SUFFIXES] if sheet_dir.exists() else []
    if not existing:
        try:
            generate_grouped_contact_sheets(root=root, stage=chunk_id or "pilot")
            generate_identity_contact_sheets(root=root)
            generate_chunk_contact_sheets(root=root)
        except Exception as exc:  # noqa: BLE001 - convert contact-sheet failures into manual review state.
            write_manual_review_flag(root, "contact_sheets_missing", {"error": str(exc)})
            raise ActiveVisualVerdictError(f"Contact sheet generation failed: {exc}") from exc
    entries = build_contact_sheet_index(root=root, chunk_id=chunk_id)
    if chunk_id and not _filter_chunk_entries(entries, chunk_id):
        try:
            generate_grouped_contact_sheets(root=root, stage=chunk_id)
            generate_identity_contact_sheets(root=root)
            generate_chunk_contact_sheets(root=root)
        except Exception as exc:  # noqa: BLE001 - convert contact-sheet failures into manual review state.
            write_manual_review_flag(root, "contact_sheets_missing", {"error": str(exc)})
            raise ActiveVisualVerdictError(f"Contact sheet generation failed: {exc}") from exc
        entries = build_contact_sheet_index(root=root, chunk_id=chunk_id)
    if not entries:
        write_manual_review_flag(root, "contact_sheets_missing")
        raise ActiveVisualVerdictError("No contact sheets found after generation attempt.")
    return entries


def _classify_sheet(path: Path) -> str:
    name = path.name.lower()
    stem = path.stem.lower()
    lowered_parts = [part.lower() for part in path.parts]
    in_identities_dir = "identities" in lowered_parts
    in_chunks_dir = "chunks" in lowered_parts

    if in_identities_dir or re.fullmatch(r"(female|male)_\d{3}", stem):
        return "identity"
    if "face_card" in name or "silhouette_card" in name or "vibe_card" in name or "contact_sheet" in name:
        return "asset"
    if "distribution" in name or name.startswith("final_") or "_final_" in name:
        return "distribution"
    if "overview" in name or in_chunks_dir or "chunk_" in name:
        return "overview"
    return "overview"


def _ids_from_sheet_name(path: Path, rows: Sequence[Mapping[str, Any]]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    stem = path.stem
    profile_ids = sorted({str(row.get("profileId") or "") for row in rows if str(row.get("profileId") or "") and str(row.get("profileId") or "") in stem})
    asset_ids = sorted({str(row.get("assetId") or "") for row in rows if str(row.get("assetId") or "") and str(row.get("assetId") or "") in stem})
    return tuple(asset_ids), tuple(profile_ids)


def build_contact_sheet_index(root: Path | str | None = None, *, chunk_id: str | None = None) -> list[ContactSheetEntry]:
    paths = pipeline_paths(root)
    sheet_dir = paths.reports / "contact_sheets"
    chunk_sheet_dir = paths.reports / "chunks" / str(chunk_id) / "contact_sheets" if chunk_id else None
    strict_index = chunk_sheet_dir / "contact_sheet_index.json" if chunk_sheet_dir else None
    if strict_index and strict_index.exists():
        try:
            payload = json.loads(strict_index.read_text(encoding="utf-8-sig"))
        except Exception:
            payload = {}
        if payload.get("sheetScope") == "current_chunk_only" and str(payload.get("chunkId") or "") == str(chunk_id):
            entries: list[ContactSheetEntry] = []
            for sheet in payload.get("sheets", []):
                if not isinstance(sheet, Mapping):
                    continue
                raw_sheet_id = str(sheet.get("sheetId") or "")
                sheet_id = raw_sheet_id if raw_sheet_id.startswith(f"{chunk_id}__") else f"{chunk_id}__{raw_sheet_id}"
                entries.append(
                    ContactSheetEntry(
                        sheet_id=sheet_id,
                        sheet_path=Path(str(sheet.get("sheetPath") or "")).resolve(),
                        sheet_type=str(sheet.get("sheetType") or "overview"),
                        asset_ids=tuple(str(asset_id) for asset_id in sheet.get("assetIds", []) if str(asset_id)),
                        profile_ids=tuple(str(profile_id) for profile_id in sheet.get("profileIds", []) if str(profile_id)),
                    )
                )
            return entries
    if not sheet_dir.exists() and not (chunk_sheet_dir and chunk_sheet_dir.exists()):
        return []
    manifest_rows = load_generation_manifest(paths)
    chunk_profile_ids: set[str] = set()
    if chunk_id:
        current_plan = paths.manifests / "current_chunk_plan.json"
        if current_plan.exists():
            try:
                payload = json.loads(current_plan.read_text(encoding="utf-8-sig"))
                if str(payload.get("chunkId") or "") == str(chunk_id):
                    chunk_profile_ids = {
                        str(identity.get("profileId") or "")
                        for identity in payload.get("identities", [])
                        if str(identity.get("profileId") or "")
                    }
            except Exception:
                chunk_profile_ids = set()
    entries: list[ContactSheetEntry] = []
    source_dirs = [sheet_dir]
    if chunk_sheet_dir and chunk_sheet_dir.exists():
        source_dirs.insert(0, chunk_sheet_dir)

    seen_paths: set[Path] = set()
    for base_dir in source_dirs:
        if not base_dir.exists():
            continue
        for path in sorted(path for path in base_dir.rglob("*") if path.suffix.lower() in IMAGE_SUFFIXES):
            resolved = path.resolve()
            if resolved in seen_paths:
                continue
            seen_paths.add(resolved)
            sheet_type = _classify_sheet(path)
            asset_ids, profile_ids = _ids_from_sheet_name(path, manifest_rows)
            if sheet_type == "identity" and not profile_ids:
                profile_ids = (path.stem,)
            try:
                relative = path.relative_to(base_dir)
            except ValueError:
                relative = path.name
            prefix = ""
            if chunk_id:
                is_chunk_dir_entry = base_dir == chunk_sheet_dir
                is_chunk_stage_asset = sheet_type == "asset" and path.stem.startswith(f"{chunk_id}_")
                is_chunk_identity = sheet_type == "identity" and bool(chunk_profile_ids.intersection(profile_ids))
                if is_chunk_dir_entry or is_chunk_stage_asset or is_chunk_identity:
                    prefix = f"{chunk_id}__"
            entry = ContactSheetEntry(
                sheet_id=prefix + Path(relative).with_suffix("").as_posix().replace("/", "__"),
                sheet_path=path.resolve(),
                sheet_type=sheet_type,
                asset_ids=asset_ids,
                profile_ids=profile_ids,
            )
            entries.append(entry)

    if not entries:
        return []
    sheet_dir.mkdir(parents=True, exist_ok=True)
    index_entries = [
        {
            "sheetId": entry.sheet_id,
            "sheetPath": to_portable_path(entry.sheet_path),
            "sheetType": entry.sheet_type,
            "assetIds": list(entry.asset_ids),
            "profileIds": list(entry.profile_ids),
        }
        for entry in entries
    ]
    index_path = sheet_dir / "contact_sheet_index.json"
    index_path.write_text(
        json.dumps(
            {
                "schemaVersion": "seolleyeon_contact_sheet_index_v3",
                "chunkId": chunk_id or "",
                "generatedAt": now_utc(),
                "entries": index_entries,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    if chunk_sheet_dir and chunk_sheet_dir.exists():
        chunk_index = chunk_sheet_dir / "contact_sheet_index.json"
        chunk_index.write_text(
            json.dumps(
                {
                    "schemaVersion": "seolleyeon_contact_sheet_index_v3",
                    "chunkId": chunk_id or "",
                    "generatedAt": now_utc(),
                    "entries": index_entries,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    return entries


def _prompt_file(root: Path | str | None, filename: str) -> str:
    return (pipeline_paths(root).root / "ai_image" / "prompts" / filename).read_text(encoding="utf-8")


def _latest_by_asset(rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        asset_id = str(row.get("assetId") or "")
        if asset_id:
            latest[asset_id] = dict(row)
    return latest


def _current_chunk_plan_assets(root: Path | str | None) -> dict[str, dict[str, Any]]:
    plan_path = pipeline_paths(root).manifests / "current_chunk_plan.json"
    if not plan_path.exists():
        return {}
    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        return {}
    assets: dict[str, dict[str, Any]] = {}
    for identity in plan.get("identities", []):
        if not isinstance(identity, Mapping):
            continue
        identity_defaults = {
            "profileId": identity.get("profileId"),
            "gender": identity.get("gender"),
            "numericId": identity.get("numericId"),
            "targetFaceType": identity.get("targetFaceType"),
            "targetLooksLevelBand": identity.get("targetLooksLevelBand"),
            "targetLooksLevel": identity.get("targetLooksLevel"),
            "eyewearGroup": identity.get("eyewearGroup"),
            "hasEyewear": identity.get("hasEyewear"),
            "targetHasEyewear": identity.get("targetHasEyewear"),
            "targetEyewearGroup": identity.get("targetEyewearGroup"),
            "targetEyewear": identity.get("targetEyewear"),
            "targetCanonicalEyewear": identity.get("targetCanonicalEyewear"),
            "targetShotEyewearExpected": identity.get("targetShotEyewearExpected"),
            "temporaryEyewearAllowed": identity.get("temporaryEyewearAllowed"),
            "temporaryEyewearApplied": identity.get("temporaryEyewearApplied"),
            "season": identity.get("season"),
        }
        for asset in identity.get("assets", []):
            if not isinstance(asset, Mapping):
                continue
            asset_id = str(asset.get("assetId") or "")
            if not asset_id:
                continue
            row = {key: value for key, value in identity_defaults.items() if value not in (None, "")}
            row.update(dict(asset))
            assets[asset_id] = row
    return assets


def _known_whitelist_assets(root: Path | str | None) -> dict[str, dict[str, Any]]:
    paths = pipeline_paths(root)
    chunk_root = paths.reports / "chunks"
    rows: dict[str, dict[str, Any]] = {}
    if not chunk_root.exists():
        return rows
    for name in ("file_complete_identity_whitelist.json", "current_chunk_asset_whitelist.json"):
        for path in chunk_root.glob(f"*/{name}"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8-sig"))
            except (json.JSONDecodeError, OSError):
                continue
            for row in payload.get("assets", []):
                if isinstance(row, Mapping) and str(row.get("assetId") or ""):
                    rows[str(row.get("assetId"))] = dict(row)
    return rows


def _file_qa_by_asset(root: Path | str | None) -> dict[str, dict[str, Any]]:
    paths = pipeline_paths(root)
    rows = list(read_jsonl(paths.manifests / "file_qa_manifest.jsonl"))
    chunk_root = paths.reports / "chunks"
    if chunk_root.exists():
        for path in chunk_root.glob("*/file_qa.jsonl"):
            rows.extend(read_jsonl(path))
    latest = _latest_by_asset(rows)
    state_path = paths.manifests / "current_chunk_state.json"
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError):
            state = {}
        asset_states = state.get("assetStates") if isinstance(state.get("assetStates"), Mapping) else {}
        for asset_id, status in asset_states.items():
            normalized_status = str(status or "").strip()
            if not normalized_status:
                continue
            # current_chunk_state is the controller's latest post-reconcile file-QA authority.
            # It must override stale per-chunk file_qa.jsonl rows such as qaStatus=file_needs_review
            # that were written before recovery/reconcile marked the same file as file_qa_passed.
            current = dict(latest.get(str(asset_id), {}))
            current["assetId"] = str(asset_id)
            current["fileQaStatus"] = normalized_status
            current["status"] = normalized_status
            current["source"] = "current_chunk_state"
            latest[str(asset_id)] = current
    return latest


def _file_qa_status_for(asset_id: str, file_qa_by_asset: Mapping[str, Mapping[str, Any]], fallback: Any = None) -> str:
    row = file_qa_by_asset.get(asset_id, {})
    for key in ("fileQaStatus", "fileQAStatus", "decision", "status", "qaStatus"):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return str(fallback or "unknown")


def _asset_manifest_by_asset(root: Path | str | None) -> dict[str, dict[str, Any]]:
    paths = pipeline_paths(root)
    rows = read_jsonl(paths.manifests / "asset_manifest.jsonl")
    if not rows:
        rows = read_jsonl(paths.manifests / "ai_profile_assets_v3.jsonl")
    return _latest_by_asset(rows)


def _first_non_empty(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _compact_metadata_by_asset(root: Path | str | None, asset_ids: set[str]) -> dict[str, dict[str, Any]]:
    paths = pipeline_paths(root)
    generation_by_asset = _latest_by_asset(load_generation_manifest(paths))
    asset_manifest = _asset_manifest_by_asset(root)
    plan_assets = _current_chunk_plan_assets(root)
    whitelist_assets = _known_whitelist_assets(root)
    file_qa = _file_qa_by_asset(root)
    compact: dict[str, dict[str, Any]] = {}
    for asset_id in sorted(asset_ids):
        source = {
            "inCurrentChunkPlan": asset_id in plan_assets,
            "inAssetManifest": asset_id in asset_manifest,
            "inGenerationManifest": asset_id in generation_by_asset,
            "inFileCompleteWhitelist": asset_id in whitelist_assets and "fileQaStatus" in whitelist_assets.get(asset_id, {}),
        }
        whitelist_row = whitelist_assets.get(asset_id, {})
        plan_row = plan_assets.get(asset_id, {})
        manifest_row = asset_manifest.get(asset_id, {})
        generation_row = generation_by_asset.get(asset_id, {})
        merged = {
            key: _first_non_empty(
                whitelist_row.get(key),
                plan_row.get(key),
                generation_row.get(key),
                manifest_row.get(key),
            )
            for key in COMPACT_METADATA_FIELDS
            if key != "fileQaStatus"
        }
        merged["assetId"] = asset_id
        merged["fileQaStatus"] = _file_qa_status_for(asset_id, file_qa, whitelist_row.get("fileQaStatus"))
        merged["source"] = source
        compact[asset_id] = {
            key: value
            for key, value in merged.items()
            if key == "source" or value not in (None, "")
        }
    return compact


def _compact_asset_metadata(root: Path | str | None, entry: ContactSheetEntry) -> list[dict[str, Any]]:
    if entry.asset_ids:
        metadata_by_asset = _compact_metadata_by_asset(root, set(entry.asset_ids))
        return [metadata_by_asset[asset_id] for asset_id in entry.asset_ids if asset_id in metadata_by_asset]
    rows = load_generation_manifest(pipeline_paths(root))
    lowered = entry.sheet_path.as_posix().lower()
    selected_ids = {
        str(row.get("assetId") or "")
        for row in rows
        if str(row.get("assetId") or "")
        and str(row.get("gender") or "").lower() in lowered
        and str(row.get("shotType") or "").lower() in lowered
    }
    metadata_by_asset = _compact_metadata_by_asset(root, selected_ids)
    return list(metadata_by_asset.values())[:100]


def _compact_identity_metadata(root: Path | str | None, entry: ContactSheetEntry) -> list[dict[str, Any]]:
    rows = load_generation_manifest(pipeline_paths(root))
    if entry.profile_ids:
        wanted_profiles = set(entry.profile_ids)
    elif re.fullmatch(r"(female|male)_\d{3}", entry.sheet_path.stem):
        wanted_profiles = {entry.sheet_path.stem}
    else:
        wanted_profiles = set()
    wanted_asset_ids = {
        str(row.get("assetId") or "")
        for row in rows
        if str(row.get("assetId") or "") and str(row.get("profileId") or "") in wanted_profiles
    }
    metadata_by_asset = _compact_metadata_by_asset(root, wanted_asset_ids)
    return [metadata_by_asset[asset_id] for asset_id in sorted(wanted_asset_ids) if asset_id in metadata_by_asset]


def _validate_source_targets(root: Path | str | None, metadata: Sequence[Mapping[str, Any]], *, qa_slug: str, sheet_id: str) -> None:
    missing: list[dict[str, str]] = []
    for row in metadata:
        asset_id = str(row.get("assetId") or "")
        for key in ("targetFaceType", "targetLooksLevelBand"):
            if _unknown_target(row.get(key)):
                missing.append({"assetId": asset_id, "field": key})
    if missing:
        reason = "source_metadata_missing"
        write_manual_review_flag(root, reason, {"sheetId": sheet_id, "missingTargetFields": missing[:20]})
        raise ActiveVisualVerdictError(f"{reason}: {sheet_id} missing target metadata for {missing[0]['assetId']} {missing[0]['field']}")


def _metadata_json_for_prompt(root: Path | str | None, metadata: Sequence[Mapping[str, Any]], *, qa_slug: str, sheet_id: str) -> str:
    _validate_source_targets(root, metadata, qa_slug=qa_slug, sheet_id=sheet_id)
    text = json.dumps(list(metadata), ensure_ascii=False, separators=(",", ":"))
    if len(text) > COMPACT_METADATA_PROMPT_BUDGET:
        write_manual_review_flag(
            root,
            "compact_visual_metadata_exceeds_prompt_budget",
            {
                "qaSlug": qa_slug,
                "sheetId": sheet_id,
                "metadataChars": len(text),
                "budgetChars": COMPACT_METADATA_PROMPT_BUDGET,
            },
        )
        raise ActiveVisualVerdictError(
            f"compact_visual_metadata_exceeds_prompt_budget: {sheet_id} has {len(text)} chars; split the sheet before QA"
        )
    return text


def _compact_asset_decisions(decisions: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for row in decisions:
        compact.append(
            {
                key: row.get(key)
                for key in (
                    "assetId",
                    "profileId",
                    "gender",
                    "numericId",
                    "shotType",
                    "targetFaceType",
                    "observedFaceType",
                    "targetLooksLevelBand",
                    "observedLooksLevelBand",
                    "targetHasEyewear",
                    "targetEyewearGroup",
                    "targetEyewear",
                    "targetCanonicalEyewear",
                    "targetShotEyewearExpected",
                    "observedHasEyewear",
                    "observedEyewearGroup",
                    "observedEyewear",
                    "eyewearReadable",
                    "eyewearMismatch",
                    "eyewearMismatchReason",
                    "temporaryEyewearAllowed",
                    "temporaryEyewearApplied",
                    "finalDecision",
                    "decision",
                    "metadataMismatch",
                    "mismatchFields",
                    "hardReject",
                    "hardRejectReasons",
                    "needsReviewReasons",
                    "rejectReasons",
                )
                if row.get(key) not in (None, "")
            }
        )
    return compact


def _asset_metadata(root: Path | str | None, entry: ContactSheetEntry) -> list[dict[str, Any]]:
    return _compact_asset_metadata(root, entry)


def _identity_metadata(root: Path | str | None, entry: ContactSheetEntry) -> list[dict[str, Any]]:
    return _compact_identity_metadata(root, entry)


def build_asset_prompt(root: Path | str | None, entry: ContactSheetEntry) -> str:
    base = _prompt_file(root, "VISUAL_VERDICT_ASSET_QA_PROMPT.md")
    metadata = _asset_metadata(root, entry)
    metadata_json = _metadata_json_for_prompt(root, metadata, qa_slug="asset_qa", sheet_id=entry.sheet_id)
    allowed_asset_ids = list(entry.asset_ids)
    allowed_profile_ids = list(entry.profile_ids) or sorted({str(row.get("profileId") or "") for row in metadata if str(row.get("profileId") or "")})
    scope_text = ""
    if allowed_asset_ids:
        scope_text = (
            "\nSTRICT CURRENT-CHUNK SCOPE:\n"
            f"allowedAssetIds: {json.dumps(allowed_asset_ids, ensure_ascii=False)}\n"
            f"allowedProfileIds: {json.dumps(allowed_profile_ids, ensure_ascii=False)}\n"
            "Return rows only for allowedAssetIds. Ignore any visible asset not in this list. "
            "Do not invent assetIds. Do not include global, reserve, or extra generation assets.\n"
        )
    target_instruction = (
        "TARGET METADATA RULES:\n"
        "You are given exact source-of-truth target metadata for each asset. "
        "Copy targetFaceType and targetLooksLevelBand exactly from compactVisibleMetadata. "
        "Also copy targetHasEyewear, targetEyewearGroup, targetEyewear, targetCanonicalEyewear, "
        "targetShotEyewearExpected, temporaryEyewearAllowed, and temporaryEyewearApplied exactly when present. "
        "Do not infer targetFaceType or targetLooksLevelBand from the image. "
        "Only judge observedFaceType, observedLooksLevelBand, observedHasEyewear, observedEyewearGroup, observedEyewear, and eyewearReadable from the image. "
        "If targetHasEyewear=true, missing eyewear or a different visible frame type is metadataMismatch. "
        "If targetHasEyewear=false, visible glasses are metadataMismatch unless temporaryEyewearAllowed=true for that shot. "
        "Sunglasses, tinted lenses, or a face-covering mask are hard reject. "
        "If the image does not visually match the target, set metadataMismatch=true. "
        "Never set provided target metadata to unknown; use unclear only for observed fields.\n"
    )
    return (
        f"{base}\n\n"
        "ACTIVE CODEX IMAGE-INPUT INSTRUCTIONS:\n"
        "Inspect the attached contact sheet image. Return strict JSON only. Do not infer approval from metadata.\n"
        f"sheetId: {entry.sheet_id}\n"
        f"sheetPath: {entry.sheet_path}\n"
        f"{scope_text}"
        f"{target_instruction}"
        f"compactVisibleMetadata: {metadata_json}\n"
        f"Required qaType: {ASSET_QA_TYPE}. Every visible assetId label must appear exactly once in assets[]."
    )


def build_identity_prompt(root: Path | str | None, entry: ContactSheetEntry) -> str:
    base = _prompt_file(root, "VISUAL_VERDICT_IDENTITY_QA_PROMPT.md")
    metadata = _identity_metadata(root, entry)
    metadata_json = _metadata_json_for_prompt(root, metadata, qa_slug="identity_qa", sheet_id=entry.sheet_id)
    asset_qa = read_jsonl(pipeline_paths(root).manifests / "asset_qa_manifest.jsonl")
    wanted_asset_ids = {str(row.get("assetId") or "") for row in metadata}
    decisions = _compact_asset_decisions([row for row in asset_qa if str(row.get("assetId") or "") in wanted_asset_ids])
    decisions_json = json.dumps(decisions, ensure_ascii=False, separators=(",", ":"))
    if len(decisions_json) > COMPACT_METADATA_PROMPT_BUDGET:
        write_manual_review_flag(
            root,
            "compact_asset_qa_decisions_exceed_prompt_budget",
            {
                "sheetId": entry.sheet_id,
                "metadataChars": len(decisions_json),
                "budgetChars": COMPACT_METADATA_PROMPT_BUDGET,
            },
        )
        raise ActiveVisualVerdictError(f"compact_asset_qa_decisions_exceed_prompt_budget: {entry.sheet_id}")
    allowed_profile_ids = list(entry.profile_ids)
    allowed_asset_ids = sorted(wanted_asset_ids)
    scope_text = ""
    if allowed_profile_ids:
        scope_text = (
            "\nSTRICT CURRENT-CHUNK SCOPE:\n"
            f"allowedProfileIds: {json.dumps(allowed_profile_ids, ensure_ascii=False)}\n"
            f"allowedAssetIds: {json.dumps(allowed_asset_ids, ensure_ascii=False)}\n"
            "Return rows only for allowedProfileIds and their allowedAssetIds. "
            "Do not invent profileIds or assetIds. Do not include global, reserve, or extra generation assets.\n"
        )
    identity_instruction = (
        "IDENTITY QA DECISION RULES:\n"
        "Use applied assetQaDecisions finalDecision values, not raw asset_qa_latest decisions. "
        "Identity approval requires all three applied asset finalDecisions to be approved. "
        "Do not approve identity if any asset is needs_review, rejected, metadataMismatch, missing, or file-QA failed. "
        "Copy targetFaceType, targetLooksLevelBand, and eyewear target fields exactly from compactVisibleMetadata; only judge observed fields from the image. "
        "Do not approve identity if canonical eyewear changes across approved-looking shots, if required eyewear disappears, "
        "or if glasses appear on a no-eyewear identity without explicit temporaryEyewearAllowed metadata.\n"
    )
    return (
        f"{base}\n\n"
        "ACTIVE CODEX IMAGE-INPUT INSTRUCTIONS:\n"
        "Inspect the attached identity contact sheet. Return strict JSON only. Do not infer identity approval from metadata.\n"
        f"sheetId: {entry.sheet_id}\n"
        f"sheetPath: {entry.sheet_path}\n"
        f"{scope_text}"
        f"{identity_instruction}"
        f"compactVisibleMetadata: {metadata_json}\n"
        f"assetQaDecisions: {decisions_json}\n"
        f"Required qaType: {IDENTITY_QA_TYPE}. Every visible profileId must appear exactly once in identities[]."
    )


def build_distribution_prompt(
    root: Path | str | None,
    entry: ContactSheetEntry | None = None,
    *,
    text_only_reason: str | None = None,
) -> str:
    base = _prompt_file(root, "VISUAL_VERDICT_DISTRIBUTION_AUDIT_PROMPT.md")
    audit = audit_distribution(root=root)
    paths = pipeline_paths(root)
    summary = {
        "numericAudit": audit,
        "assetQaCount": len(read_jsonl(paths.manifests / "asset_qa_manifest.jsonl")),
        "identityQaCount": len(read_jsonl(paths.manifests / "identity_qa_manifest.jsonl")),
        "approvedIdentityCount": len(read_jsonl(paths.manifests / "approved_identity_manifest.jsonl")),
        "rejectedIdentityCount": len(read_jsonl(paths.manifests / "rejected_identity_manifest.jsonl")),
    }
    if entry and not text_only_reason:
        sheet_text = f"\nsheetId: {entry.sheet_id}\nsheetPath: {entry.sheet_path}\n"
    elif entry and text_only_reason:
        sheet_text = (
            f"\nsheetId: {entry.sheet_id}\nsheetPath: {entry.sheet_path}\n"
            f"No distribution contact sheet image is attached because {text_only_reason}; "
            "perform text+manifest audit only and use needs_manual_review if visual evidence is required.\n"
        )
    else:
        sheet_text = "\nNo distribution contact sheet is attached; perform text+manifest audit only.\n"
    return (
        f"{base}\n\n"
        "ACTIVE CODEX DISTRIBUTION AUDIT INSTRUCTIONS:\n"
        "Return strict JSON only. Numeric distribution audit is the final numeric authority. "
        "If visual evidence is insufficient, use finalDecision=needs_manual_review. "
        "If the dataset is incomplete, use finalDecision=needs_more_generation.\n"
        f"{sheet_text}"
        f"distributionSummary: {json.dumps(summary, ensure_ascii=False)[:30000]}\n"
        f"Required qaType: {DISTRIBUTION_QA_TYPE}."
    )


def _log_paths(root: Path | str | None, qa_slug: str, timestamp: str) -> tuple[Path, Path, Path]:
    base = visual_dir(root) / "logs"
    base.mkdir(parents=True, exist_ok=True)
    return (
        base / f"{qa_slug}_{timestamp}.stdout.txt",
        base / f"{qa_slug}_{timestamp}.stderr.txt",
        base / f"{qa_slug}_{timestamp}.command.json",
    )


def _save_invalid(root: Path | str | None, qa_slug: str, text: str) -> Path:
    path = visual_dir(root) / "invalid" / f"{qa_slug}_{_timestamp()}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _save_part(root: Path | str | None, qa_slug: str, index: int, payload: Mapping[str, Any]) -> Path:
    path = visual_dir(root) / "parts" / f"{qa_slug}_part_{index}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _save_latest_and_history(root: Path | str | None, qa_slug: str, latest_name: str, payload: Mapping[str, Any]) -> Path:
    base = visual_dir(root)
    history = base / "history" / f"{qa_slug}_{_timestamp()}.json"
    latest = base / latest_name
    history.parent.mkdir(parents=True, exist_ok=True)
    latest.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    history.write_text(text, encoding="utf-8")
    tmp = latest.with_suffix(latest.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(latest)
    return latest


def _choose_form(root: Path | str | None, config: ActiveVisualConfig, run_func: Callable[..., subprocess.CompletedProcess[str]]) -> CodexCommandForm:
    forms = discover_command_forms(root=root, config=config, run_func=run_func)
    if not forms:
        write_manual_review_flag(root, "codex_image_input_unavailable", {"manualCommands": manual_visual_commands(root)})
        raise ActiveVisualVerdictError("No supported Codex CLI image-input form was detected.")
    return forms[0]


def run_codex_visual_call(
    *,
    root: Path | str | None,
    qa_slug: str,
    prompt: str,
    image_paths: Sequence[Path | str],
    config: ActiveVisualConfig | None = None,
    form: CodexCommandForm | None = None,
    run_func: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, Any]:
    config = config or ActiveVisualConfig.from_env()
    if not image_paths and qa_slug in {"asset_qa", "identity_qa"}:
        write_manual_review_flag(root, f"{qa_slug}_requires_image_path")
        raise ActiveVisualVerdictError(f"{qa_slug} requires at least one attached image path.")
    if form is None:
        form = _choose_form(root, config, run_func) if image_paths else CodexCommandForm(exec_mode="exec" if config.exec_mode in {"auto", "exec"} else "direct", image_arg_mode="image")
    # Windows command lines are easy to exceed with sheet metadata and safety prompts.
    # Keep image paths in argv, but send the review prompt through stdin.
    prompt_via_stdin = True
    args = build_codex_args(prompt, image_paths, config=config, form=form, root=pipeline_paths(root).root, prompt_via_stdin=prompt_via_stdin)
    timestamp = _timestamp()
    stdout_path, stderr_path, command_path = _log_paths(root, qa_slug, timestamp)
    command_path.write_text(
        json.dumps(
            {
                "args": args,
                "imagePaths": [str(Path(path).resolve()) for path in image_paths],
                "promptViaStdin": prompt_via_stdin,
                "promptChars": len(prompt),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    try:
        result = run_func(
            args,
            cwd=str(pipeline_paths(root).root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            input=prompt if prompt_via_stdin else None,
            timeout=config.timeout_sec,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        _save_invalid(root, qa_slug, str(exc))
        write_manual_review_flag(root, f"{qa_slug}_codex_subprocess_failed", {"error": str(exc)})
        raise ActiveVisualVerdictError(f"Codex visual QA subprocess failed: {exc}") from exc
    stdout_path.write_text(result.stdout or "", encoding="utf-8")
    stderr_path.write_text(result.stderr or "", encoding="utf-8")
    if result.returncode != 0:
        _save_invalid(root, qa_slug, f"STDOUT:\n{result.stdout or ''}\nSTDERR:\n{result.stderr or ''}")
        write_manual_review_flag(root, f"{qa_slug}_codex_subprocess_failed", {"returncode": result.returncode})
        raise ActiveVisualVerdictError(f"Codex visual QA returned nonzero exit code: {result.returncode}")
    try:
        return extract_json_object(result.stdout or "")
    except Exception as exc:  # noqa: BLE001 - save raw model output before failing.
        _save_invalid(root, qa_slug, result.stdout or "")
        write_manual_review_flag(root, f"{qa_slug}_invalid_json", {"error": str(exc)})
        raise


def _selected_sheets(entries: Sequence[ContactSheetEntry], sheet_type: str, config: ActiveVisualConfig) -> list[ContactSheetEntry]:
    if sheet_type == "distribution":
        selected = [entry for entry in entries if entry.sheet_type in {"distribution", "overview"}]
    else:
        selected = [entry for entry in entries if entry.sheet_type == sheet_type]
    return selected[: config.max_sheets_per_run]


def _filter_chunk_entries(entries: Sequence[ContactSheetEntry], chunk_id: str | None) -> list[ContactSheetEntry]:
    if not chunk_id:
        return list(entries)
    prefix = f"{chunk_id}__"
    return [entry for entry in entries if entry.sheet_id.startswith(prefix)]


def _entries_from_contact_sheet_index(index_path: Path | str, *, chunk_id: str | None = None) -> list[ContactSheetEntry]:
    payload = json.loads(Path(index_path).read_text(encoding="utf-8-sig"))
    if chunk_id and str(payload.get("chunkId") or "") != str(chunk_id):
        raise ActiveVisualVerdictError(
            f"contact sheet index chunkId mismatch: expected {chunk_id}, got {payload.get('chunkId') or '<missing>'}"
        )
    raw_sheets = payload.get("sheets") if isinstance(payload.get("sheets"), list) else payload.get("entries")
    if not isinstance(raw_sheets, list):
        raise ActiveVisualVerdictError("contact sheet index requires sheets[] or entries[].")
    entries: list[ContactSheetEntry] = []
    for sheet in raw_sheets:
        if not isinstance(sheet, Mapping):
            continue
        out_of_scope = [str(item) for item in sheet.get("outOfScopeAssetIds", []) if str(item)]
        if out_of_scope:
            raise ActiveVisualVerdictError(f"contact sheet index contains out-of-scope assets: {out_of_scope[:5]}")
        raw_sheet_id = str(sheet.get("sheetId") or "")
        sheet_id = raw_sheet_id
        if chunk_id and not sheet_id.startswith(f"{chunk_id}__"):
            sheet_id = f"{chunk_id}__{sheet_id}"
        entries.append(
            ContactSheetEntry(
                sheet_id=sheet_id,
                sheet_path=Path(str(sheet.get("sheetPath") or "")).resolve(),
                sheet_type=str(sheet.get("sheetType") or "overview"),
                asset_ids=tuple(str(asset_id) for asset_id in sheet.get("assetIds", []) if str(asset_id)),
                profile_ids=tuple(str(profile_id) for profile_id in sheet.get("profileIds", []) if str(profile_id)),
            )
        )
    return entries


def run_active_visual_asset_qa(
    *,
    root: Path | str | None = None,
    chunk_id: str | None = None,
    config: ActiveVisualConfig | None = None,
    run_func: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    apply_after: bool = True,
    strict_chunk_scope: bool = False,
    asset_whitelist: Path | str | None = None,
    contact_sheet_index: Path | str | None = None,
) -> dict[str, Any]:
    config = config or ActiveVisualConfig.from_env()
    scope_payload: dict[str, Any] | None = None
    allowed_asset_ids: set[str] = set()
    allowed_profile_ids: set[str] = set()
    expected_by_asset: dict[str, dict[str, Any]] = {}
    latestInvalidation: dict[str, Any] | None = None
    if strict_chunk_scope:
        if not chunk_id:
            raise ActiveVisualVerdictError("--chunk_id is required with strict asset visual QA scope.")
        if not asset_whitelist:
            write_current_chunk_whitelists(root, chunk_id)
        scope_payload = _load_asset_whitelist_payload(root, chunk_id=chunk_id, asset_whitelist=asset_whitelist)
        allowed_asset_ids, allowed_profile_ids, expected_by_asset = _scope_from_whitelist(scope_payload)
        compact_expected = _compact_metadata_by_asset(root, allowed_asset_ids)
        for asset_id, compact_row in compact_expected.items():
            expected_by_asset.setdefault(asset_id, {}).update(compact_row)
        latestInvalidation = mark_latest_asset_qa_invalid_if_out_of_scope(root, chunk_id=chunk_id, asset_whitelist=asset_whitelist)
    entries = _filter_chunk_entries(
        ensure_contact_sheets(
            root,
            chunk_id=chunk_id,
            strict_chunk_scope=strict_chunk_scope,
            asset_whitelist=asset_whitelist,
            contact_sheet_index=contact_sheet_index,
        ),
        chunk_id,
    )
    sheets = _selected_sheets(entries, "asset", config)
    if not sheets:
        write_manual_review_flag(root, "asset_contact_sheets_missing")
        raise ActiveVisualVerdictError("No asset contact sheets found.")
    if strict_chunk_scope:
        sheet_asset_ids = {asset_id for sheet in sheets for asset_id in sheet.asset_ids}
        allowed_asset_ids = sheet_asset_ids
        compact_expected = _compact_metadata_by_asset(root, sheet_asset_ids)
        expected_by_asset = {
            asset_id: {**expected_by_asset.get(asset_id, {}), **compact_expected.get(asset_id, {})}
            for asset_id in sheet_asset_ids
            if asset_id in expected_by_asset or asset_id in compact_expected
        }
        allowed_profile_ids = {profile_id for sheet in sheets for profile_id in sheet.profile_ids}
    form = _choose_form(root, config, run_func)
    parts: list[dict[str, Any]] = []
    for index, sheet in enumerate(sheets, start=1):
        payload = run_codex_visual_call(
            root=root,
            qa_slug="asset_qa",
            prompt=build_asset_prompt(root, sheet),
            image_paths=[sheet.sheet_path],
            config=config,
            form=form,
            run_func=run_func,
        )
        validate_asset_qa_json(payload)
        if strict_chunk_scope:
            part_allowed_asset_ids = set(sheet.asset_ids)
            part_allowed_profile_ids = set(sheet.profile_ids)
            part_expected_by_asset = {
                asset_id: expected_by_asset[asset_id]
                for asset_id in part_allowed_asset_ids
                if asset_id in expected_by_asset
            }
            validate_asset_payload_scope(
                payload,
                root=root,
                chunk_id=str(chunk_id),
                allowed_asset_ids=part_allowed_asset_ids,
                allowed_profile_ids=part_allowed_profile_ids,
                expected_by_asset=part_expected_by_asset,
            )
        _save_part(root, "asset_qa", index, payload)
        parts.append(payload)
    merged = merge_asset_parts(parts)
    validate_asset_qa_json(merged)
    if strict_chunk_scope:
        validate_asset_payload_scope(
            merged,
            root=root,
            chunk_id=str(chunk_id),
            allowed_asset_ids=allowed_asset_ids,
            allowed_profile_ids=allowed_profile_ids,
            expected_by_asset=expected_by_asset,
        )
    latest = _save_latest_and_history(root, "asset_qa", "asset_qa_latest.json", merged)
    raw_counts = _summary_counts(merged["assets"], "decision")
    target_unknown_count = sum(
        1
        for row in merged["assets"]
        if _unknown_target(row.get("targetFaceType")) or _unknown_target(row.get("targetLooksLevelBand"))
    )
    result = {
        "checked": len(merged["assets"]),
        "outputJson": to_portable_path(latest),
        "parts": len(parts),
        "applied": False,
        "strictChunkScope": bool(strict_chunk_scope),
        "allowedAssetCount": len(allowed_asset_ids) if strict_chunk_scope else 0,
        "latestInvalidation": latestInvalidation,
        "rawAssetQaCounts": raw_counts,
        "targetUnknownCount": target_unknown_count,
    }
    if apply_after:
        result["applyResult"] = apply_asset_qa(root=root, input_path=str(latest))
        result["applied"] = True
        result["appliedAssetQaCounts"] = {
            key: int(result["applyResult"].get(key) or 0)
            for key in ("approved", "needs_review", "rejected")
        }
        result["downgradeSummary"] = _asset_downgrade_summary(merged["assets"], result["applyResult"])
    return result


def run_active_visual_identity_qa(
    *,
    root: Path | str | None = None,
    chunk_id: str | None = None,
    config: ActiveVisualConfig | None = None,
    run_func: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    apply_after: bool = True,
    strict_chunk_scope: bool = False,
    asset_whitelist: Path | str | None = None,
    contact_sheet_index: Path | str | None = None,
) -> dict[str, Any]:
    config = config or ActiveVisualConfig.from_env()
    paths = pipeline_paths(root)
    if not (paths.manifests / "asset_qa_manifest.jsonl").exists():
        write_manual_review_flag(root, "asset_qa_manifest_missing_for_identity_visual_qa")
        raise ActiveVisualVerdictError("asset_qa_manifest.jsonl is required before identity visual QA.")
    allowed_asset_ids: set[str] = set()
    allowed_profile_ids: set[str] = set()
    if strict_chunk_scope:
        if not chunk_id:
            raise ActiveVisualVerdictError("--chunk_id is required with strict identity visual QA scope.")
        if not asset_whitelist:
            write_current_chunk_whitelists(root, chunk_id)
        scope_payload = _load_asset_whitelist_payload(root, chunk_id=chunk_id, asset_whitelist=asset_whitelist)
        allowed_asset_ids, allowed_profile_ids, _ = _scope_from_whitelist(scope_payload)
    entries = _filter_chunk_entries(
        ensure_contact_sheets(
            root,
            chunk_id=chunk_id,
            strict_chunk_scope=strict_chunk_scope,
            asset_whitelist=asset_whitelist,
            contact_sheet_index=contact_sheet_index,
        ),
        chunk_id,
    )
    sheets = _selected_sheets(entries, "identity", config)
    if not sheets:
        write_manual_review_flag(root, "identity_contact_sheets_missing")
        raise ActiveVisualVerdictError("No identity contact sheets found.")
    if strict_chunk_scope:
        allowed_profile_ids = {profile_id for sheet in sheets for profile_id in sheet.profile_ids}
    form = _choose_form(root, config, run_func)
    parts: list[dict[str, Any]] = []
    for index, sheet in enumerate(sheets, start=1):
        payload = run_codex_visual_call(
            root=root,
            qa_slug="identity_qa",
            prompt=build_identity_prompt(root, sheet),
            image_paths=[sheet.sheet_path],
            config=config,
            form=form,
            run_func=run_func,
        )
        validate_identity_qa_json(payload)
        if strict_chunk_scope:
            validate_identity_payload_scope(
                payload,
                root=root,
                chunk_id=str(chunk_id),
                allowed_asset_ids=allowed_asset_ids,
                allowed_profile_ids=set(sheet.profile_ids),
            )
        _save_part(root, "identity_qa", index, payload)
        parts.append(payload)
    merged = merge_identity_parts(parts)
    validate_identity_qa_json(merged)
    if strict_chunk_scope:
        validate_identity_payload_scope(
            merged,
            root=root,
            chunk_id=str(chunk_id),
            allowed_asset_ids=allowed_asset_ids,
            allowed_profile_ids=allowed_profile_ids,
        )
    latest = _save_latest_and_history(root, "identity_qa", "identity_qa_latest.json", merged)
    raw_counts = _summary_counts(merged["identities"], "completeIdentityDecision")
    result = {
        "checked": len(merged["identities"]),
        "outputJson": to_portable_path(latest),
        "parts": len(parts),
        "applied": False,
        "strictChunkScope": bool(strict_chunk_scope),
        "allowedProfileCount": len(allowed_profile_ids) if strict_chunk_scope else 0,
        "rawIdentityQaCounts": raw_counts,
    }
    if apply_after:
        result["applyResult"] = apply_identity_qa(root=root, input_path=str(latest))
        result["applied"] = True
        result["appliedIdentityQaCounts"] = {
            key: int(result["applyResult"].get(key) or 0)
            for key in ("approved", "needs_review", "rejected")
        }
    return result


def _distribution_sheet(entries: Sequence[ContactSheetEntry]) -> ContactSheetEntry | None:
    selected = [entry for entry in entries if entry.sheet_type in {"distribution", "overview"}]
    return selected[0] if selected else None


def run_active_visual_distribution_qa(
    *,
    root: Path | str | None = None,
    chunk_id: str | None = None,
    config: ActiveVisualConfig | None = None,
    run_func: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    apply_after: bool = True,
    strict_chunk_scope: bool = False,
    asset_whitelist: Path | str | None = None,
    contact_sheet_index: Path | str | None = None,
) -> dict[str, Any]:
    config = config or ActiveVisualConfig.from_env()
    if strict_chunk_scope:
        if not chunk_id:
            raise ActiveVisualVerdictError("--chunk_id is required with strict distribution visual QA scope.")
        if not asset_whitelist:
            write_current_chunk_whitelists(root, chunk_id)
        _load_asset_whitelist_payload(root, chunk_id=chunk_id, asset_whitelist=asset_whitelist)
    paths = pipeline_paths(root)
    for manifest_name in ("asset_qa_manifest.jsonl", "identity_qa_manifest.jsonl"):
        if not (paths.manifests / manifest_name).exists():
            write_manual_review_flag(root, f"{manifest_name}_missing_for_distribution_visual_qa")
            raise ActiveVisualVerdictError(f"{manifest_name} is required before distribution visual QA.")
    audit_distribution(root=root)
    entries = _filter_chunk_entries(
        ensure_contact_sheets(
            root,
            chunk_id=chunk_id,
            strict_chunk_scope=strict_chunk_scope,
            asset_whitelist=asset_whitelist,
            contact_sheet_index=contact_sheet_index,
        )
        if strict_chunk_scope
        else build_contact_sheet_index(root=root, chunk_id=chunk_id),
        chunk_id,
    )
    sheet = _distribution_sheet(entries)
    image_paths = [sheet.sheet_path] if sheet else []
    form = None
    text_only_reason = None
    if image_paths:
        forms = discover_command_forms(root=root, config=config, run_func=run_func)
        if forms:
            form = forms[0]
        else:
            # Distribution QA is allowed to fall back to a manifest/numeric audit.
            # Asset and identity QA still require actual image inspection.
            image_paths = []
            text_only_reason = "Codex CLI image input is unavailable"
    payload = run_codex_visual_call(
        root=root,
        qa_slug="distribution_audit",
        prompt=build_distribution_prompt(root, sheet, text_only_reason=text_only_reason),
        image_paths=image_paths,
        config=config,
        form=form,
        run_func=run_func,
    )
    validate_distribution_qa_json(payload)
    latest = _save_latest_and_history(root, "distribution_audit", "distribution_audit_latest.json", payload)
    result = {"outputJson": to_portable_path(latest), "applied": False}
    if apply_after:
        apply_result = apply_distribution_audit(root=root, input_path=str(latest), numeric_audit=paths.reports / "latest_distribution_audit.json")
        result["applyResult"] = apply_result
        result["applied"] = True
        audit_distribution(root=root)
        result["completion"] = completion_check(root=root)
        if apply_result.get("needsManualReview"):
            raise ActiveVisualVerdictError("Visual distribution audit disagrees with numeric audit.")
    return result


def coverage_check(
    root: Path | str | None = None,
    *,
    chunk_id: str | None = None,
    asset_whitelist: Path | str | None = None,
) -> dict[str, Any]:
    paths = pipeline_paths(root)
    asset_rows = {str(row.get("assetId") or ""): row for row in read_jsonl(paths.manifests / "asset_qa_manifest.jsonl")}
    identity_rows = {str(row.get("profileId") or ""): row for row in read_jsonl(paths.manifests / "identity_qa_manifest.jsonl")}
    approved_rows = read_jsonl(paths.manifests / "approved_identity_manifest.jsonl")
    generated_rows = generated_image_rows(root)
    allowed_asset_ids: set[str] = set()
    allowed_profile_ids: set[str] = set()
    if chunk_id:
        payload = _load_asset_whitelist_payload(root, chunk_id=chunk_id, asset_whitelist=asset_whitelist)
        allowed_asset_ids, allowed_profile_ids, _ = _scope_from_whitelist(payload)
        generated_rows = [
            row
            for row in generated_rows
            if str(row.get("assetId") or "") in allowed_asset_ids
            and str(row.get("profileId") or "") in allowed_profile_ids
        ]
        asset_rows = {asset_id: row for asset_id, row in asset_rows.items() if asset_id in allowed_asset_ids}
        identity_rows = {profile_id: row for profile_id, row in identity_rows.items() if profile_id in allowed_profile_ids}
        approved_rows = [row for row in approved_rows if str(row.get("profileId") or "") in allowed_profile_ids]
    missing_asset_ids = sorted(str(row.get("assetId") or "") for row in generated_rows if str(row.get("assetId") or "") not in asset_rows)
    invalid_approved_assets = sorted(
        asset_id
        for asset_id, row in asset_rows.items()
        if row.get("finalDecision") == "approved"
        and (
            row.get("metadataMismatch") is True
            or row.get("observedLooksLevelBand") == "4.4-5.0"
            or row.get("hardReject") is True
            or row.get("shotTypeReadable") is False
            or row.get("observedFaceType") == "unclear"
            or row.get("observedLooksLevelBand") == "unclear"
        )
    )
    by_profile: dict[str, set[str]] = {}
    for row in generated_rows:
        by_profile.setdefault(str(row.get("profileId") or ""), set()).add(str(row.get("shotType") or ""))
    complete_profiles = sorted(profile for profile, shots in by_profile.items() if set(SHOT_ORDER).issubset(shots))
    missing_identity_profiles = sorted(profile for profile in complete_profiles if profile not in identity_rows)
    invalid_approved_profiles: list[str] = []
    for row in approved_rows:
        profile_id = str(row.get("profileId") or "")
        identity = identity_rows.get(profile_id, {})
        asset_ids = row.get("assetIds") if isinstance(row.get("assetIds"), Mapping) else {}
        if (
            not identity
            or identity.get("finalCompleteIdentityDecision") != "approved"
            or identity.get("countsTowardDistribution") is not True
            or identity.get("sameIdentity") is not True
            or identity.get("metadataMismatch") is True
            or identity.get("observedLooksLevelBand") == "4.4-5.0"
            or any(asset_rows.get(str(asset_ids.get(shot) or ""), {}).get("finalDecision") != "approved" for shot in SHOT_ORDER)
        ):
            invalid_approved_profiles.append(profile_id)
    result = {
        "passed": not (missing_asset_ids or invalid_approved_assets or missing_identity_profiles or invalid_approved_profiles),
        "missingAssetIds": missing_asset_ids,
        "invalidApprovedAssetIds": invalid_approved_assets,
        "missingIdentityProfileIds": missing_identity_profiles,
        "invalidApprovedProfileIds": sorted(invalid_approved_profiles),
    }
    if not result["passed"]:
        write_manual_review_flag(root, "visual_qa_coverage_gap", result)
    return result


def mark_current_chunk_visual_qa_complete(
    root: Path | str | None = None,
    *,
    chunk_id: str | None,
    distribution_audit_complete: bool,
) -> dict[str, Any]:
    if not chunk_id:
        return {"updated": False, "reason": "chunk_id_missing"}
    paths = pipeline_paths(root)
    state_path = paths.manifests / "current_chunk_state.json"
    if not state_path.exists():
        return {"updated": False, "reason": "current_chunk_state_missing"}
    try:
        state = json.loads(state_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        return {"updated": False, "reason": f"current_chunk_state_invalid:{exc}"}
    if str(state.get("chunkId") or "") != str(chunk_id):
        return {
            "updated": False,
            "reason": "current_chunk_state_chunk_id_mismatch",
            "stateChunkId": str(state.get("chunkId") or ""),
        }
    timestamp = now_utc()
    state["activeVisualQaComplete"] = True
    state["activeVisualQaCompletedAt"] = timestamp
    if distribution_audit_complete:
        state["distributionAuditComplete"] = True
        state["distributionAuditCompletedAt"] = timestamp
    state["updatedAt"] = timestamp
    tmp = state_path.with_suffix(state_path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(state_path)
    return {
        "updated": True,
        "chunkId": chunk_id,
        "activeVisualQaComplete": True,
        "distributionAuditComplete": bool(state.get("distributionAuditComplete")),
    }


def run_active_visual_qa_all(
    *,
    root: Path | str | None = None,
    chunk_id: str | None = None,
    config: ActiveVisualConfig | None = None,
    run_func: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    strict_chunk_scope: bool = False,
    asset_whitelist: Path | str | None = None,
    contact_sheet_index: Path | str | None = None,
) -> dict[str, Any]:
    config = config or ActiveVisualConfig.from_env()
    result: dict[str, Any] = {}
    try:
        ensure_contact_sheets(
            root,
            chunk_id=chunk_id,
            strict_chunk_scope=strict_chunk_scope,
            asset_whitelist=asset_whitelist,
            contact_sheet_index=contact_sheet_index,
        )
        result["assetQA"] = run_active_visual_asset_qa(
            root=root,
            chunk_id=chunk_id,
            config=config,
            run_func=run_func,
            apply_after=True,
            strict_chunk_scope=strict_chunk_scope,
            asset_whitelist=asset_whitelist,
            contact_sheet_index=contact_sheet_index,
        )
        result["identityQA"] = run_active_visual_identity_qa(
            root=root,
            chunk_id=chunk_id,
            config=config,
            run_func=run_func,
            apply_after=True,
            strict_chunk_scope=strict_chunk_scope,
            asset_whitelist=asset_whitelist,
            contact_sheet_index=contact_sheet_index,
        )
        result["distributionAuditBefore"] = {
            key: audit_distribution(root=root)[key]
            for key in ("passed", "finalDecision", "approvedCompleteIdentityCount", "approvedImageCount")
        }
        result["distributionQA"] = run_active_visual_distribution_qa(
            root=root,
            chunk_id=chunk_id,
            config=config,
            run_func=run_func,
            apply_after=True,
            strict_chunk_scope=strict_chunk_scope,
            asset_whitelist=asset_whitelist,
            contact_sheet_index=contact_sheet_index,
        )
        coverage = coverage_check(root=root, chunk_id=chunk_id if strict_chunk_scope else None, asset_whitelist=asset_whitelist)
        result["coverage"] = coverage
        if not coverage["passed"]:
            raise ActiveVisualVerdictError("Visual QA coverage check failed.")
        final_audit = audit_distribution(root=root)
        result["distributionAuditAfter"] = {
            key: final_audit[key]
            for key in ("passed", "finalDecision", "approvedCompleteIdentityCount", "approvedImageCount")
        }
        result["chunkStateUpdate"] = mark_current_chunk_visual_qa_complete(
            root=root,
            chunk_id=chunk_id,
            distribution_audit_complete=bool(result.get("distributionQA", {}).get("applied")),
        )
        result["completion"] = completion_check(root=root)
        return result
    except Exception as exc:
        if not (pipeline_paths(root).manifests / "manual_review_required.flag").exists():
            write_manual_review_flag(root, "active_visual_qa_all_failed", {"error": str(exc)})
        raise


def active_visual_probe_main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Probe Codex CLI image-input support for active Seolleyeon visual QA.")
    parser.add_argument("--root", default=None)
    args = parser.parse_args(argv)
    result = probe_codex_image_input(root=args.root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["available"] else 2


def _runner_main(kind: str, argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=f"Run active Codex image-input visual {kind} QA.")
    parser.add_argument("--root", default=None)
    parser.add_argument("--chunk_id", default=None)
    parser.add_argument("--no_apply", action="store_true")
    parser.add_argument("--strict-chunk-scope", "--strict_chunk_scope", dest="strict_chunk_scope", action="store_true", default=False)
    parser.add_argument("--asset-whitelist", "--asset_whitelist", dest="asset_whitelist", default=None)
    parser.add_argument("--contact-sheet-index", "--contact_sheet_index", dest="contact_sheet_index", default=None)
    args = parser.parse_args(argv)
    runners = {
        "asset": run_active_visual_asset_qa,
        "identity": run_active_visual_identity_qa,
        "distribution": run_active_visual_distribution_qa,
        "all": run_active_visual_qa_all,
    }
    try:
        if kind == "all":
            result = runners[kind](
                root=args.root,
                chunk_id=args.chunk_id,
                strict_chunk_scope=args.strict_chunk_scope,
                asset_whitelist=args.asset_whitelist,
                contact_sheet_index=args.contact_sheet_index,
            )
        else:
            result = runners[kind](
                root=args.root,
                chunk_id=args.chunk_id,
                apply_after=not args.no_apply,
                strict_chunk_scope=args.strict_chunk_scope,
                asset_whitelist=args.asset_whitelist,
                contact_sheet_index=args.contact_sheet_index,
            )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:  # noqa: BLE001 - CLI should print a concise JSON failure.
        print(json.dumps({"passed": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2


def asset_main(argv: list[str] | None = None) -> int:
    return _runner_main("asset", argv)


def identity_main(argv: list[str] | None = None) -> int:
    return _runner_main("identity", argv)


def distribution_main(argv: list[str] | None = None) -> int:
    return _runner_main("distribution", argv)


def all_main(argv: list[str] | None = None) -> int:
    return _runner_main("all", argv)
