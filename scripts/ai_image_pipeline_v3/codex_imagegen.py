from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from .config import (
    CODEX_GENERATED_IMAGES_DIR_ENV,
    DEFAULT_CODEX_GENERATED_IMAGES_DIR,
    MAX_ATTEMPTS,
    SHOT_ORDER,
    approved_asset_path,
    ensure_base_dirs,
    now_utc,
    pipeline_paths,
    profile_number,
    prompt_hash,
    raw_attempt_path,
    read_jsonl,
    rejected_attempt_path,
    shot_sort_key,
    to_portable_path,
    write_jsonl,
)
from .manifest import load_generation_manifest, public_final_path, write_generation_outputs
from .pending_state import pending_is_resolved, pending_is_unresolved, pending_requires_recovery as pending_requires_recovery_state, resolved_pending_payload
from .retry_plan import APPROVED_STATUSES, attempt_count
from .targeting import apply_reserve_policy, approved_identity_report


PENDING_FILENAME = "pending-imagegen.json"
IMAGEGEN_QUEUE_FILENAME = "imagegen_queue.jsonl"
IDENTITY_MANIFEST_FILENAME = "identity_manifest.jsonl"
COMPLETED_PENDING_FILENAME = "completed_pending_imagegen.jsonl"
RESERVE_ACTIVATION_FILENAME = "reserve_activation_manifest.jsonl"
RETRY_MANIFEST_FILENAME = "retry_manifest.jsonl"

ELIGIBLE_STATUSES = {
    "prepared",
    "queued",
    "retry_queued",
    "missing",
    "qa_rejected",
    "vision_rejected",
    "failed",
}
PENDING_STATUSES = {"pending_imagegen"}
RECOVERED_PENDING_STATUSES = {"recovered_pending_qa", "needs_manual_review"}
GENERATED_IMAGE_TIMESTAMP_GRACE_SECONDS = 5


@dataclass(frozen=True)
class NextPromptResult:
    asset_id: str
    profile_id: str
    shot_type: str
    attempt: int
    pending_path: Path
    imagegen_command: str


@dataclass(frozen=True)
class RecoverResult:
    asset_id: str
    source_path: Path
    raw_path: Path
    final_path: Path
    pending_path: Path


def identity_manifest_path(root: Path | str | None = None) -> Path:
    return pipeline_paths(root).manifests / IDENTITY_MANIFEST_FILENAME


def queue_path(root: Path | str | None = None) -> Path:
    return pipeline_paths(root).manifests / IMAGEGEN_QUEUE_FILENAME


def pending_path(root: Path | str | None = None) -> Path:
    return pipeline_paths(root).manifests / PENDING_FILENAME


def completed_pending_path(root: Path | str | None = None) -> Path:
    return pipeline_paths(root).manifests / COMPLETED_PENDING_FILENAME


def retry_manifest_path(root: Path | str | None = None) -> Path:
    return pipeline_paths(root).manifests / RETRY_MANIFEST_FILENAME


def reserve_activation_path(root: Path | str | None = None) -> Path:
    return pipeline_paths(root).manifests / RESERVE_ACTIVATION_FILENAME


def write_identity_manifest(root: Path | str | None, specs: Iterable[Mapping[str, Any]]) -> Path:
    rows: list[dict[str, Any]] = []
    for spec in specs:
        profile_id = str(spec["profileId"])
        is_reserve = bool(spec.get("isReserve")) or str(spec.get("identityScope") or "") == "reserve"
        rows.append(
            {
                "profileId": profile_id,
                "gender": str(spec["gender"]),
                "numericId": profile_number(profile_id),
                "identityScope": "reserve" if is_reserve else "primary",
                "isReserve": is_reserve,
                "reserveStatus": "standby" if is_reserve else "",
                "activeForTarget": not is_reserve,
                "identityDecision": "",
                "shotTypes": list(SHOT_ORDER),
                "updatedAt": now_utc(),
            }
        )
    path = identity_manifest_path(root)
    write_jsonl(path, rows)
    return path


def write_imagegen_queue(root: Path | str | None, rows: Iterable[Mapping[str, Any]]) -> Path:
    queue_rows: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        is_reserve = bool(item.get("isReserve"))
        active = bool(item.get("activeForTarget") if "activeForTarget" in item else not is_reserve)
        item["queueStatus"] = "standby" if is_reserve and not active else "queued"
        item["queueReason"] = "reserve_standby" if item["queueStatus"] == "standby" else "ready"
        item["updatedAt"] = now_utc()
        queue_rows.append(item)
    path = queue_path(root)
    write_jsonl(path, sorted(queue_rows, key=shot_sort_key))
    return path


def read_pending(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8-sig").strip()
    if not text:
        return None
    return json.loads(text)


def write_pending(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), ensure_ascii=False, indent=2), encoding="utf-8")


def _pending_requires_recovery(pending: Mapping[str, Any] | None) -> bool:
    return pending_requires_recovery_state(pending)


def _json_command(prompt: str) -> str:
    return "$imagegen " + json.dumps(prompt, ensure_ascii=False)


def face_card_imagegen_prompt(row: Mapping[str, Any], prompt: str) -> str:
    return f"""Generate exactly one vertical realistic smartphone profile photo.

Asset metadata:
assetId: {row["assetId"]}
profileId: {row["profileId"]}
shotType: {row["shotType"]}

Use this prompt:
{prompt}

Rules:
- one image only
- no text in image
- no watermark
- no logo
- adult Korean university student
- realistic, calm, trustworthy
- not influencer-like
- not school uniform
- not childlike
"""


def silhouette_card_imagegen_prompt(row: Mapping[str, Any], prompt: str) -> str:
    return f"""Using the attached face_card image as the same person reference, generate exactly one silhouette_card image.

Asset metadata:
assetId: {row["assetId"]}
profileId: {row["profileId"]}
shotType: {row["shotType"]}

Goal:
Same person as the reference face_card.
Generate a realistic 3/4 body or full-body smartphone profile photo.
The body frame and proportions should be readable.
Campus-appropriate modest clothing.
No oversized padding.
No revealing outfit.
No school uniform.
No text, no logo, no watermark.

Use this prompt:
{prompt}
"""


def vibe_card_imagegen_prompt(row: Mapping[str, Any], prompt: str) -> str:
    return f"""Using the attached face_card image as the same person reference, generate exactly one vibe_card image.

Asset metadata:
assetId: {row["assetId"]}
profileId: {row["profileId"]}
shotType: {row["shotType"]}

Goal:
Same person as the reference face_card.
Generate a realistic campus/cafe/library/exhibition lifestyle profile photo.
The mood should be calm, sincere, and trustworthy.
Not nightlife.
Not influencer content.
No readable logo, school name, text, or watermark.

Use this prompt:
{prompt}
"""


def _image_exists(path_value: Any) -> bool:
    if not path_value:
        return False
    path = Path(str(path_value))
    return path.exists() and path.stat().st_size > 0


def _is_approved(row: Mapping[str, Any]) -> bool:
    return str(row.get("status") or "") in APPROVED_STATUSES and _image_exists(row.get("finalPath"))


def _face_approved(rows_by_asset: Mapping[str, Mapping[str, Any]], row: Mapping[str, Any]) -> bool:
    face_asset_id = f"{row['profileId']}__face_card__v001"
    face = rows_by_asset.get(face_asset_id)
    return bool(face and _is_approved(face))


def _dependent_reference_path(rows_by_asset: Mapping[str, Mapping[str, Any]], row: Mapping[str, Any]) -> str:
    face_asset_id = f"{row['profileId']}__face_card__v001"
    face = rows_by_asset.get(face_asset_id, {})
    return str(face.get("finalPath") or face.get("localPath") or "")


def _eligible_attempt(row: Mapping[str, Any], *, max_attempts: int, force: bool) -> int | None:
    if not bool(row.get("activeForTarget", True)):
        return None
    status = str(row.get("status") or "")
    if _is_approved(row) and not force:
        return None
    if status in PENDING_STATUSES:
        return None
    if status in RECOVERED_PENDING_STATUSES and not force:
        return None
    if status not in ELIGIBLE_STATUSES and not force:
        return None
    next_attempt = attempt_count(row) + 1
    if next_attempt > max_attempts and not force:
        return None
    return next_attempt


def _candidate_sort_key(row: Mapping[str, Any]) -> tuple[int, str, int]:
    shot_type = str(row.get("shotType") or "")
    try:
        shot_index = SHOT_ORDER.index(shot_type)
    except ValueError:
        shot_index = len(SHOT_ORDER)
    reserve_rank = 1 if bool(row.get("isReserve")) and str(row.get("reserveStatus") or "") != "activated" else 0
    return shot_index, str(row.get("profileId") or ""), reserve_rank


def select_next_asset(
    rows: list[Mapping[str, Any]],
    *,
    max_attempts: int = MAX_ATTEMPTS,
    force: bool = False,
    stop_when_target_reached: bool = False,
    target_approved_identities: int = 240,
    target_approved_assets: int = 720,
) -> tuple[dict[str, Any] | None, int | None, str]:
    if stop_when_target_reached:
        report = approved_identity_report(rows)
        if (
            int(report.get("approvedIdentities") or 0) >= target_approved_identities
            and int(report.get("approvedAssets") or 0) >= target_approved_assets
        ):
            return None, None, "target_reached"

    rows_by_asset = {str(row.get("assetId")): row for row in rows}
    candidates: list[tuple[dict[str, Any], int]] = []
    waiting_reference = 0
    for source in sorted(rows, key=_candidate_sort_key):
        row = dict(source)
        attempt = _eligible_attempt(row, max_attempts=max_attempts, force=force)
        if attempt is None:
            continue
        if str(row.get("shotType")) != "face_card" and not _face_approved(rows_by_asset, row):
            waiting_reference += 1
            continue
        candidates.append((row, attempt))
    if candidates:
        return candidates[0][0], candidates[0][1], "selected"
    if waiting_reference:
        return None, None, "waiting_reference"
    return None, None, "no_eligible_asset"


def build_pending_payload(
    *,
    paths_root: Path | str | None,
    row: Mapping[str, Any],
    attempt: int,
    queue_file: Path,
    manifest_file: Path,
    out_pending: Path,
    generated_root: Path | str | None = None,
) -> dict[str, Any]:
    paths = pipeline_paths(paths_root)
    rows_by_asset = {str(item.get("assetId")): item for item in load_generation_manifest(paths)}
    asset_id = str(row["assetId"])
    raw_path = raw_attempt_path(paths, asset_id, attempt)
    final_path = public_final_path(paths, row)
    approved_path = approved_asset_path(paths, row)
    rejected_path = rejected_attempt_path(paths, asset_id, attempt)
    generated_dir = str(generated_root or os.environ.get(CODEX_GENERATED_IMAGES_DIR_ENV) or DEFAULT_CODEX_GENERATED_IMAGES_DIR)
    reference_asset_id = str(row.get("referenceAssetId") or "")
    reference_path = ""
    if str(row.get("shotType")) != "face_card":
        reference_asset_id = reference_asset_id or f"{row['profileId']}__face_card__v001"
        reference_path = _dependent_reference_path(rows_by_asset, row)
    source_prompt = str(row.get("prompt") or "")
    prompt = source_prompt
    if str(row.get("shotType")) == "face_card":
        prompt = face_card_imagegen_prompt(row, source_prompt)
    elif str(row.get("shotType")) == "silhouette_card" and reference_path:
        prompt = silhouette_card_imagegen_prompt(row, source_prompt)
    elif str(row.get("shotType")) == "vibe_card" and reference_path:
        prompt = vibe_card_imagegen_prompt(row, source_prompt)
    elif reference_path:
        prompt = (
            f"{prompt}\n\nReference image for same-person identity consistency: {reference_path}\n"
            "Use this approved face_card as the identity anchor. If the current Codex $imagegen surface "
            "cannot use this reference image, stop and report reference_blocked; do not generate an "
            "independent text-only dependent shot."
        )
    return {
        "assetId": asset_id,
        "profileId": str(row["profileId"]),
        "gender": str(row["gender"]),
        "numericId": profile_number(str(row["profileId"])),
        "shotType": str(row["shotType"]),
        "attempt": int(attempt),
        "prompt": prompt,
        "promptHash": prompt_hash(prompt),
        "queuePath": to_portable_path(queue_file),
        "manifestPath": to_portable_path(manifest_file),
        "pendingPath": to_portable_path(out_pending),
        "expectedRawPath": to_portable_path(raw_path),
        "expectedFinalPath": to_portable_path(final_path),
        "expectedApprovedPath": to_portable_path(approved_path),
        "expectedRejectedPath": to_portable_path(rejected_path),
        "referenceAssetId": reference_asset_id,
        "referenceImagePath": reference_path,
        "codexGeneratedImagesDir": generated_dir,
        "status": "pending_imagegen",
        "createdAt": now_utc(),
        "recoveryInstructions": [
            "After the $imagegen result, do not continue to the next queued asset.",
            "First run mingw32-make ai-image-recover or scripts/recover_pending_imagegen_v3.py.",
            "Map identity from this pending-imagegen.json only; do not infer identity visually.",
            "Copy raw output to expectedRawPath and final candidate to expectedFinalPath.",
            "Run QA before preparing another $imagegen prompt.",
        ],
    }


def next_prompt(
    *,
    root: Path | str | None = None,
    queue: Path | str | None = None,
    manifest: Path | str | None = None,
    out_pending: Path | str | None = None,
    max_attempts: int = MAX_ATTEMPTS,
    force: bool = False,
    stop_when_target_reached: bool = False,
    target_approved_identities: int = 240,
    target_approved_assets: int = 720,
) -> NextPromptResult | None:
    paths = pipeline_paths(root)
    ensure_base_dirs(paths)
    queue_file = Path(queue).resolve() if queue else queue_path(root)
    manifest_file = Path(manifest).resolve() if manifest else paths.manifests / "generation_manifest.jsonl"
    out_pending_file = Path(out_pending).resolve() if out_pending else pending_path(root)

    pending = read_pending(out_pending_file)
    if _pending_requires_recovery(pending):
        raise RuntimeError(
            f"pending imagegen checkpoint requires recovery first: {out_pending_file}. "
            "Run mingw32-make ai-image-recover before creating a new prompt."
        )
    if pending_is_unresolved(pending):
        raise RuntimeError(
            f"unresolved pending-imagegen checkpoint blocks new prompt: {out_pending_file}. "
            "Resolve, clear, or manually review this checkpoint before creating another prompt."
        )

    apply_reserve_policy(root=root, max_attempts=max_attempts)
    rows = load_generation_manifest(paths)
    row, attempt, reason = select_next_asset(
        rows,
        max_attempts=max_attempts,
        force=force,
        stop_when_target_reached=stop_when_target_reached,
        target_approved_identities=target_approved_identities,
        target_approved_assets=target_approved_assets,
    )
    if row is None or attempt is None:
        print(f"No eligible Codex imagegen asset: {reason}")
        return None

    payload = build_pending_payload(
        paths_root=root,
        row=row,
        attempt=attempt,
        queue_file=queue_file,
        manifest_file=manifest_file,
        out_pending=out_pending_file,
    )
    write_pending(out_pending_file, payload)

    by_asset = {str(item["assetId"]): dict(item) for item in rows}
    selected = by_asset[payload["assetId"]]
    selected.update(
        {
            "status": "pending_imagegen",
            "attempt": int(attempt),
            "attemptCount": int(attempt),
            "pendingPath": to_portable_path(out_pending_file),
            "expectedRawPath": payload["expectedRawPath"],
            "expectedFinalPath": payload["expectedFinalPath"],
            "expectedApprovedPath": payload["expectedApprovedPath"],
            "expectedRejectedPath": payload["expectedRejectedPath"],
            "finalPath": payload["expectedFinalPath"],
            "approvedPath": payload["expectedApprovedPath"],
            "rejectedPath": payload["expectedRejectedPath"],
            "resolvedReferencePath": payload["referenceImagePath"],
            "updatedAt": now_utc(),
            "error": "",
        }
    )
    by_asset[payload["assetId"]] = selected
    write_generation_outputs(paths, list(by_asset.values()))

    command = _json_command(payload["prompt"])
    return NextPromptResult(
        asset_id=payload["assetId"],
        profile_id=payload["profileId"],
        shot_type=payload["shotType"],
        attempt=int(attempt),
        pending_path=out_pending_file,
        imagegen_command=command,
    )


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        text = value.replace("Z", "+00:00")
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _candidate_generated_files(generated_root: Path) -> list[Path]:
    if not generated_root.exists():
        return []
    exts = {".png", ".jpg", ".jpeg", ".webp"}
    return sorted(
        [path for path in generated_root.rglob("*") if path.is_file() and path.suffix.lower() in exts],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )


def latest_generated_image(generated_root: Path, *, created_at: str | None = None) -> Path:
    files = _candidate_generated_files(generated_root)
    if not files:
        raise FileNotFoundError(f"No generated images found under {generated_root}")
    created = _parse_timestamp(created_at)
    if created is not None:
        created_ts = created.timestamp()
        after_created = [path for path in files if path.stat().st_mtime >= created_ts - GENERATED_IMAGE_TIMESTAMP_GRACE_SECONDS]
        if len(after_created) > 1:
            candidates = ", ".join(str(path) for path in after_created[:5])
            raise RuntimeError(
                "Ambiguous Codex generated image recovery candidates after pending timestamp. "
                f"Pass --source explicitly. candidates={candidates}"
            )
        if after_created:
            return after_created[0]
        newest = files[0]
        newest_mtime = datetime.fromtimestamp(newest.stat().st_mtime, timezone.utc).isoformat()
        raise FileNotFoundError(
            "No Codex generated image was created at or after the pending checkpoint timestamp. "
            f"pendingCreatedAt={created.isoformat()} newestCandidate={newest} newestMtime={newest_mtime}"
        )
    return files[0]


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _path_key(path: Path | str) -> str:
    try:
        return str(Path(path).resolve()).replace("\\", "/").casefold()
    except OSError:
        return str(path).replace("\\", "/").casefold()


def _source_reuse_conflict(root: Path | str | None, source_path: Path, asset_id: str) -> str | None:
    source_key = _path_key(source_path)
    for row in read_jsonl(completed_pending_path(root)):
        other_asset_id = str(row.get("assetId") or "")
        if not other_asset_id or other_asset_id == asset_id:
            continue
        for key in ("sourcePath", "codexGeneratedSourcePath", "sourceGeneratedImagePath"):
            used = str(row.get(key) or "")
            if used and _path_key(used) == source_key:
                return other_asset_id
    return None


def _exact_duplicate_existing_asset(rows: Iterable[Mapping[str, Any]], source_path: Path, asset_id: str) -> str | None:
    if not source_path.exists() or not source_path.is_file():
        return None
    try:
        source_hash = _file_sha256(source_path)
    except OSError:
        return None
    for row in rows:
        other_asset_id = str(row.get("assetId") or "")
        if not other_asset_id or other_asset_id == asset_id:
            continue
        for key in ("finalPath", "approvedPath", "localPath", "rawPath"):
            value = str(row.get(key) or "")
            if not value:
                continue
            path = Path(value)
            if not path.exists() or not path.is_file():
                continue
            try:
                if _file_sha256(path) == source_hash:
                    return other_asset_id
            except OSError:
                continue
    return None


def _copy_as_png(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.suffix.lower() == ".png":
        shutil.copy2(source, target)
        return
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("Pillow is required to import non-PNG Codex generated images as PNG.") from exc
    with Image.open(source) as image:
        image.convert("RGB").save(target, format="PNG")


def _append_jsonl(path: Path, row: Mapping[str, Any]) -> None:
    rows = read_jsonl(path)
    rows.append(dict(row))
    write_jsonl(path, rows)


def recover_pending_imagegen(
    *,
    root: Path | str | None = None,
    pending: Path | str | None = None,
    generated_root: Path | str | None = None,
    out_dir: Path | str | None = None,
    source: Path | str | None = None,
    force: bool = False,
    run_qa: bool = True,
    wait_seconds: float = 0.0,
    poll_interval: float = 1.0,
) -> RecoverResult:
    root_path: Path | str | None = root
    if out_dir:
        out_path = Path(out_dir).resolve()
        root_path = out_path.parent if out_path.name == "ai_image" else out_path
    paths = pipeline_paths(root_path)
    ensure_base_dirs(paths)
    pending_file = Path(pending).resolve() if pending else pending_path(root_path)
    payload = read_pending(pending_file)
    if not payload:
        raise FileNotFoundError(f"No pending imagegen checkpoint found: {pending_file}")
    if pending_is_resolved(payload) and not force:
        raise RuntimeError(f"Pending checkpoint is already resolved: {pending_file}")

    generated_dir = Path(
        generated_root
        or payload.get("codexGeneratedImagesDir")
        or os.environ.get(CODEX_GENERATED_IMAGES_DIR_ENV)
        or DEFAULT_CODEX_GENERATED_IMAGES_DIR
    ).resolve()
    if source:
        source_path = Path(source).resolve()
    else:
        deadline = time.monotonic() + max(0.0, float(wait_seconds))
        while True:
            try:
                source_path = latest_generated_image(generated_dir, created_at=payload.get("createdAt"))
                break
            except FileNotFoundError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(max(0.1, float(poll_interval)))
    if not source_path.exists():
        raise FileNotFoundError(f"Generated image source does not exist: {source_path}")

    raw_path = Path(str(payload["expectedRawPath"])).resolve()
    final_path = Path(str(payload["expectedFinalPath"])).resolve()
    approved_path_value = str(payload.get("expectedApprovedPath") or "")
    rejected_path_value = str(payload.get("expectedRejectedPath") or "")
    approved_path = Path(approved_path_value).resolve() if approved_path_value else None
    rejected_path = Path(rejected_path_value).resolve() if rejected_path_value else None
    rows = load_generation_manifest(paths)
    row = next((item for item in rows if str(item.get("assetId")) == str(payload["assetId"])), None)
    asset_id = str(payload["assetId"])
    if not force:
        source_conflict = _source_reuse_conflict(root_path, source_path, asset_id)
        if source_conflict:
            raise RuntimeError(
                "Refusing to recover a Codex generated image source that was already assigned "
                f"to another asset: source={source_path} existingAssetId={source_conflict} assetId={asset_id}"
            )
        duplicate_asset = _exact_duplicate_existing_asset(rows, source_path, asset_id)
        if duplicate_asset:
            raise RuntimeError(
                "Refusing to recover an exact duplicate image for another asset. "
                f"source={source_path} existingAssetId={duplicate_asset} assetId={asset_id}"
            )
    if row and str(row.get("status") or "") in APPROVED_STATUSES and final_path.exists() and not force:
        raise RuntimeError(f"Refusing to overwrite approved asset without --force: {final_path}")

    _copy_as_png(source_path, raw_path)
    if final_path.exists() and row and str(row.get("status") or "") in APPROVED_STATUSES and not force:
        raise RuntimeError(f"Refusing to overwrite approved final image without --force: {final_path}")
    _copy_as_png(raw_path, final_path)

    updated_rows: list[dict[str, Any]] = []
    found = False
    for item in rows:
        out = dict(item)
        if str(out.get("assetId")) == str(payload["assetId"]):
            found = True
            out.update(
                {
                    "status": "recovered_pending_qa",
                    "attempt": int(payload.get("attempt") or out.get("attempt") or 1),
                    "attemptCount": int(payload.get("attempt") or out.get("attemptCount") or 1),
                    "localPath": to_portable_path(raw_path),
                    "rawPath": to_portable_path(raw_path),
                    "finalPath": to_portable_path(final_path),
                    "approvedPath": to_portable_path(approved_path) if approved_path else str(out.get("approvedPath") or ""),
                    "rejectedPath": to_portable_path(rejected_path) if rejected_path else str(out.get("rejectedPath") or ""),
                    "expectedRawPath": to_portable_path(raw_path),
                    "expectedFinalPath": to_portable_path(final_path),
                    "expectedApprovedPath": to_portable_path(approved_path) if approved_path else str(out.get("expectedApprovedPath") or ""),
                    "expectedRejectedPath": to_portable_path(rejected_path) if rejected_path else str(out.get("expectedRejectedPath") or ""),
                    "codexGeneratedSourcePath": to_portable_path(source_path),
                    "recoveredAt": now_utc(),
                    "updatedAt": now_utc(),
                    "error": "",
                }
            )
        updated_rows.append(out)
    if not found:
        raise RuntimeError(f"Pending assetId was not found in generation manifest: {payload['assetId']}")
    write_generation_outputs(paths, updated_rows)

    completed = resolved_pending_payload(
        payload,
        recoveryStatus="recovered",
        sourcePath=to_portable_path(source_path),
        rawPath=to_portable_path(raw_path),
        finalPath=to_portable_path(final_path),
        recoveredAt=now_utc(),
    )
    _append_jsonl(completed_pending_path(root_path), completed)
    write_pending(pending_file, completed)

    if run_qa:
        from .qa import qa_images

        qa_images(root=root_path, shot_type=str(payload["shotType"]), force=force)

    return RecoverResult(
        asset_id=str(payload["assetId"]),
        source_path=source_path,
        raw_path=raw_path,
        final_path=final_path,
        pending_path=pending_file,
    )


def build_next_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Write the next Codex $imagegen pending checkpoint and print the exact prompt.")
    parser.add_argument("--root", default=None)
    parser.add_argument("--queue", default=None)
    parser.add_argument("--manifest", default=None)
    parser.add_argument("--out_pending", default=None)
    parser.add_argument("--max_attempts", type=int, default=MAX_ATTEMPTS)
    parser.add_argument("--target_approved_identities", type=int, default=240)
    parser.add_argument("--target_approved_assets", type=int, default=720)
    parser.add_argument("--stop_when_target_reached", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser


def next_main(argv: list[str] | None = None) -> int:
    args = build_next_parser().parse_args(argv)
    result = next_prompt(
        root=args.root,
        queue=args.queue,
        manifest=args.manifest,
        out_pending=args.out_pending,
        max_attempts=args.max_attempts,
        target_approved_identities=args.target_approved_identities,
        target_approved_assets=args.target_approved_assets,
        stop_when_target_reached=args.stop_when_target_reached,
        force=args.force,
    )
    if result is None:
        return 0
    print(f"pending={result.pending_path}")
    print(f"assetId={result.asset_id} profileId={result.profile_id} shotType={result.shot_type} attempt={result.attempt}")
    print(result.imagegen_command)
    return 0


def build_recover_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Recover/import the latest Codex built-in $imagegen output from pending-imagegen.json.")
    parser.add_argument("--root", default=None)
    parser.add_argument("--pending", default=None)
    parser.add_argument("--generated_root", default=None)
    parser.add_argument("--out_dir", default=None)
    parser.add_argument("--source", default=None, help="Explicit generated image file to import; otherwise newest file is used.")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--no_qa", action="store_true", help="Recover without running file QA. Normal workflow keeps QA enabled.")
    return parser


def recover_main(argv: list[str] | None = None) -> int:
    args = build_recover_parser().parse_args(argv)
    result = recover_pending_imagegen(
        root=args.root,
        pending=args.pending,
        generated_root=args.generated_root,
        out_dir=args.out_dir,
        source=args.source,
        force=args.force,
        run_qa=not args.no_qa,
    )
    print(
        json.dumps(
            {
                "assetId": result.asset_id,
                "sourcePath": str(result.source_path),
                "rawPath": str(result.raw_path),
                "finalPath": str(result.final_path),
                "pendingPath": str(result.pending_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0
