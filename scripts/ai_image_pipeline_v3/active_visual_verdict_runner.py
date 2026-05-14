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
from .contact_sheet import generate_chunk_contact_sheets, generate_grouped_contact_sheets, generate_identity_contact_sheets
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


def _summary_counts(items: Sequence[Mapping[str, Any]], decision_key: str) -> dict[str, int]:
    approved = sum(1 for item in items if item.get(decision_key) == "approved")
    needs_review = sum(1 for item in items if item.get(decision_key) == "needs_review")
    rejected = sum(1 for item in items if item.get(decision_key) == "rejected")
    return {"approved": approved, "needs_review": needs_review, "rejected": rejected}


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


def ensure_contact_sheets(root: Path | str | None = None, *, chunk_id: str | None = None) -> list[ContactSheetEntry]:
    if not generated_image_rows(root):
        write_manual_review_flag(root, "no_generated_images_for_visual_qa")
        raise ActiveVisualVerdictError("No generated/recovered images exist for active visual QA.")
    paths = pipeline_paths(root)
    ensure_base_dirs(paths)
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


def _asset_metadata(root: Path | str | None, entry: ContactSheetEntry) -> list[dict[str, Any]]:
    rows = load_generation_manifest(pipeline_paths(root))
    if entry.asset_ids:
        wanted = set(entry.asset_ids)
        return [dict(row) for row in rows if str(row.get("assetId") or "") in wanted]
    lowered = entry.sheet_path.as_posix().lower()
    selected = []
    for row in rows:
        if str(row.get("gender") or "").lower() in lowered and str(row.get("shotType") or "").lower() in lowered:
            selected.append(dict(row))
    return selected[:100]


def _identity_metadata(root: Path | str | None, entry: ContactSheetEntry) -> list[dict[str, Any]]:
    rows = load_generation_manifest(pipeline_paths(root))
    if entry.profile_ids:
        wanted = set(entry.profile_ids)
        return [dict(row) for row in rows if str(row.get("profileId") or "") in wanted]
    if re.fullmatch(r"(female|male)_\d{3}", entry.sheet_path.stem):
        return [dict(row) for row in rows if str(row.get("profileId") or "") == entry.sheet_path.stem]
    return []


def build_asset_prompt(root: Path | str | None, entry: ContactSheetEntry) -> str:
    base = _prompt_file(root, "VISUAL_VERDICT_ASSET_QA_PROMPT.md")
    metadata = _asset_metadata(root, entry)
    return (
        f"{base}\n\n"
        "ACTIVE CODEX IMAGE-INPUT INSTRUCTIONS:\n"
        "Inspect the attached contact sheet image. Return strict JSON only. Do not infer approval from metadata.\n"
        f"sheetId: {entry.sheet_id}\n"
        f"sheetPath: {entry.sheet_path}\n"
        f"visibleMetadata: {json.dumps(metadata, ensure_ascii=False)[:20000]}\n"
        f"Required qaType: {ASSET_QA_TYPE}. Every visible assetId label must appear exactly once in assets[]."
    )


def build_identity_prompt(root: Path | str | None, entry: ContactSheetEntry) -> str:
    base = _prompt_file(root, "VISUAL_VERDICT_IDENTITY_QA_PROMPT.md")
    metadata = _identity_metadata(root, entry)
    asset_qa = read_jsonl(pipeline_paths(root).manifests / "asset_qa_manifest.jsonl")
    wanted_asset_ids = {str(row.get("assetId") or "") for row in metadata}
    decisions = [row for row in asset_qa if str(row.get("assetId") or "") in wanted_asset_ids]
    return (
        f"{base}\n\n"
        "ACTIVE CODEX IMAGE-INPUT INSTRUCTIONS:\n"
        "Inspect the attached identity contact sheet. Return strict JSON only. Do not infer identity approval from metadata.\n"
        f"sheetId: {entry.sheet_id}\n"
        f"sheetPath: {entry.sheet_path}\n"
        f"visibleMetadata: {json.dumps(metadata, ensure_ascii=False)[:20000]}\n"
        f"assetQaDecisions: {json.dumps(decisions, ensure_ascii=False)[:20000]}\n"
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


def run_active_visual_asset_qa(
    *,
    root: Path | str | None = None,
    chunk_id: str | None = None,
    config: ActiveVisualConfig | None = None,
    run_func: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    apply_after: bool = True,
) -> dict[str, Any]:
    config = config or ActiveVisualConfig.from_env()
    entries = _filter_chunk_entries(ensure_contact_sheets(root, chunk_id=chunk_id), chunk_id)
    sheets = _selected_sheets(entries, "asset", config)
    if not sheets:
        write_manual_review_flag(root, "asset_contact_sheets_missing")
        raise ActiveVisualVerdictError("No asset contact sheets found.")
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
        _save_part(root, "asset_qa", index, payload)
        parts.append(payload)
    merged = merge_asset_parts(parts)
    validate_asset_qa_json(merged)
    latest = _save_latest_and_history(root, "asset_qa", "asset_qa_latest.json", merged)
    result = {
        "checked": len(merged["assets"]),
        "outputJson": to_portable_path(latest),
        "parts": len(parts),
        "applied": False,
    }
    if apply_after:
        result["applyResult"] = apply_asset_qa(root=root, input_path=str(latest))
        result["applied"] = True
    return result


def run_active_visual_identity_qa(
    *,
    root: Path | str | None = None,
    chunk_id: str | None = None,
    config: ActiveVisualConfig | None = None,
    run_func: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    apply_after: bool = True,
) -> dict[str, Any]:
    config = config or ActiveVisualConfig.from_env()
    paths = pipeline_paths(root)
    if not (paths.manifests / "asset_qa_manifest.jsonl").exists():
        write_manual_review_flag(root, "asset_qa_manifest_missing_for_identity_visual_qa")
        raise ActiveVisualVerdictError("asset_qa_manifest.jsonl is required before identity visual QA.")
    entries = _filter_chunk_entries(ensure_contact_sheets(root, chunk_id=chunk_id), chunk_id)
    sheets = _selected_sheets(entries, "identity", config)
    if not sheets:
        write_manual_review_flag(root, "identity_contact_sheets_missing")
        raise ActiveVisualVerdictError("No identity contact sheets found.")
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
        _save_part(root, "identity_qa", index, payload)
        parts.append(payload)
    merged = merge_identity_parts(parts)
    validate_identity_qa_json(merged)
    latest = _save_latest_and_history(root, "identity_qa", "identity_qa_latest.json", merged)
    result = {
        "checked": len(merged["identities"]),
        "outputJson": to_portable_path(latest),
        "parts": len(parts),
        "applied": False,
    }
    if apply_after:
        result["applyResult"] = apply_identity_qa(root=root, input_path=str(latest))
        result["applied"] = True
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
) -> dict[str, Any]:
    config = config or ActiveVisualConfig.from_env()
    paths = pipeline_paths(root)
    for manifest_name in ("asset_qa_manifest.jsonl", "identity_qa_manifest.jsonl"):
        if not (paths.manifests / manifest_name).exists():
            write_manual_review_flag(root, f"{manifest_name}_missing_for_distribution_visual_qa")
            raise ActiveVisualVerdictError(f"{manifest_name} is required before distribution visual QA.")
    audit_distribution(root=root)
    entries = _filter_chunk_entries(build_contact_sheet_index(root=root, chunk_id=chunk_id), chunk_id)
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


def coverage_check(root: Path | str | None = None) -> dict[str, Any]:
    paths = pipeline_paths(root)
    asset_rows = {str(row.get("assetId") or ""): row for row in read_jsonl(paths.manifests / "asset_qa_manifest.jsonl")}
    identity_rows = {str(row.get("profileId") or ""): row for row in read_jsonl(paths.manifests / "identity_qa_manifest.jsonl")}
    approved_rows = read_jsonl(paths.manifests / "approved_identity_manifest.jsonl")
    generated_rows = generated_image_rows(root)
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


def run_active_visual_qa_all(
    *,
    root: Path | str | None = None,
    chunk_id: str | None = None,
    config: ActiveVisualConfig | None = None,
    run_func: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, Any]:
    config = config or ActiveVisualConfig.from_env()
    result: dict[str, Any] = {}
    try:
        ensure_contact_sheets(root, chunk_id=chunk_id)
        result["assetQA"] = run_active_visual_asset_qa(root=root, chunk_id=chunk_id, config=config, run_func=run_func, apply_after=True)
        result["identityQA"] = run_active_visual_identity_qa(root=root, chunk_id=chunk_id, config=config, run_func=run_func, apply_after=True)
        result["distributionAuditBefore"] = {
            key: audit_distribution(root=root)[key]
            for key in ("passed", "finalDecision", "approvedCompleteIdentityCount", "approvedImageCount")
        }
        result["distributionQA"] = run_active_visual_distribution_qa(root=root, chunk_id=chunk_id, config=config, run_func=run_func, apply_after=True)
        coverage = coverage_check(root=root)
        result["coverage"] = coverage
        if not coverage["passed"]:
            raise ActiveVisualVerdictError("Visual QA coverage check failed.")
        final_audit = audit_distribution(root=root)
        result["distributionAuditAfter"] = {
            key: final_audit[key]
            for key in ("passed", "finalDecision", "approvedCompleteIdentityCount", "approvedImageCount")
        }
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
    args = parser.parse_args(argv)
    runners = {
        "asset": run_active_visual_asset_qa,
        "identity": run_active_visual_identity_qa,
        "distribution": run_active_visual_distribution_qa,
        "all": run_active_visual_qa_all,
    }
    try:
        if kind == "all":
            result = runners[kind](root=args.root, chunk_id=args.chunk_id)
        else:
            result = runners[kind](root=args.root, chunk_id=args.chunk_id, apply_after=not args.no_apply)
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
