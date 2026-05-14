from __future__ import annotations

import csv
import hashlib
import json
import shutil
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


DEFAULT_MODEL = "codex-built-in-imagegen"
FALLBACK_MODEL = "codex-built-in-imagegen"
DEFAULT_SIZE = "1024x1536"
DEFAULT_QUALITY = "high"
DEFAULT_OUTPUT_FORMAT = "png"
DEFAULT_CONCURRENCY = 2
PRIMARY_FEMALE_COUNT = 120
PRIMARY_MALE_COUNT = 120
RESERVE_FEMALE_COUNT = 20
RESERVE_MALE_COUNT = 20
TARGET_APPROVED_IDENTITIES = 240
TARGET_APPROVED_ASSETS = 720
MAX_ATTEMPTS = 3

SHOT_ORDER = ("face_card", "silhouette_card", "vibe_card")
CODEX_GENERATED_IMAGES_DIR_ENV = "CODEX_GENERATED_IMAGES_DIR"
DEFAULT_CODEX_GENERATED_IMAGES_DIR = str(Path.home() / ".codex" / "generated_images")
STATUS_FIELDS = (
    "assetId",
    "profileId",
    "gender",
    "numericId",
    "identityScope",
    "isReserve",
    "reserveStatus",
    "activeForTarget",
    "identityDecision",
    "shotType",
    "targetFaceType",
    "targetLooksLevel",
    "targetLooksLevelBand",
    "status",
    "localPath",
    "finalPath",
    "approvedPath",
    "rejectedPath",
    "expectedRawPath",
    "expectedFinalPath",
    "expectedApprovedPath",
    "expectedRejectedPath",
    "storagePath",
    "legacyStoragePath",
    "model",
    "size",
    "quality",
    "outputFormat",
    "promptHash",
    "referenceAssetId",
    "referenceLocalPath",
    "resolvedReferencePath",
    "attempt",
    "attemptCount",
    "dryRun",
    "updatedAt",
    "error",
)


@dataclass(frozen=True)
class PipelinePaths:
    root: Path
    ai_image: Path
    manifests: Path
    raw: Path
    approved: Path
    rejected: Path
    final: Path
    reports: Path
    logs: Path


def repo_root_from_here() -> Path:
    return Path(__file__).resolve().parents[2]


def pipeline_paths(root: Path | str | None = None) -> PipelinePaths:
    base = Path(root).resolve() if root is not None else repo_root_from_here()
    ai_image = base / "ai_image"
    return PipelinePaths(
        root=base,
        ai_image=ai_image,
        manifests=ai_image / "manifests",
        raw=ai_image / "raw",
        approved=ai_image / "approved",
        rejected=ai_image / "rejected",
        final=ai_image,
        reports=ai_image / "reports",
        logs=ai_image / "logs",
    )


def ensure_base_dirs(paths: PipelinePaths) -> None:
    for folder in (
        paths.ai_image,
        paths.manifests,
        paths.raw,
        paths.approved,
        paths.rejected,
        paths.final,
        paths.final / "female",
        paths.final / "male",
        paths.reports,
        paths.logs,
    ):
        folder.mkdir(parents=True, exist_ok=True)


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def prompt_hash(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:24]


def profile_number(profile_id: str) -> str:
    parts = str(profile_id).split("_", 1)
    if len(parts) != 2 or not parts[1]:
        raise ValueError(f"Invalid profileId: {profile_id}")
    return parts[1]


def raw_attempt_path(paths: PipelinePaths, asset_id: str, attempt: int) -> Path:
    return paths.raw / f"{asset_id}__attempt{int(attempt):02d}.png"


def approved_asset_path(paths: PipelinePaths, asset: Mapping[str, Any]) -> Path:
    return paths.approved / f"{asset['assetId']}.png"


def approved_asset_mirror_path(paths: PipelinePaths, asset: Mapping[str, Any]) -> Path:
    return paths.approved / str(asset["gender"]) / profile_number(str(asset["profileId"])) / f"{asset['shotType']}.png"


def rejected_attempt_path(paths: PipelinePaths, asset_id: str, attempt: int) -> Path:
    return paths.rejected / f"{asset_id}__attempt{int(attempt):02d}.png"


def local_image_path(paths: PipelinePaths, asset: Mapping[str, Any], *, root_key: str = "raw") -> Path:
    if root_key == "final":
        return paths.final / str(asset["gender"]) / profile_number(str(asset["profileId"])) / f"{asset['shotType']}.png"
    if root_key == "approved":
        return approved_asset_path(paths, asset)
    if root_key == "rejected":
        return rejected_attempt_path(paths, str(asset["assetId"]), int(asset.get("attemptCount") or 1))
    if root_key == "raw":
        return raw_attempt_path(paths, str(asset["assetId"]), int(asset.get("attemptCount") or 1))
    root = getattr(paths, root_key)
    return root / str(asset["gender"]) / profile_number(str(asset["profileId"])) / f"{asset['shotType']}.png"


def to_portable_path(path: Path) -> str:
    return path.resolve().as_posix()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(dict(row), ensure_ascii=False, sort_keys=False) + "\n")
    replace_with_retry(tmp, path)


def replace_with_retry(tmp: Path, path: Path, *, attempts: int = 8, delay_sec: float = 0.25) -> None:
    last_error: OSError | None = None
    for _ in range(attempts):
        try:
            tmp.replace(path)
            return
        except OSError as exc:
            last_error = exc
            time.sleep(delay_sec)
    if last_error is not None:
        for _ in range(attempts):
            try:
                with tmp.open("rb") as src, path.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
                tmp.unlink(missing_ok=True)
                return
            except OSError as exc:
                last_error = exc
                time.sleep(delay_sec)
        raise last_error
    tmp.replace(path)


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(fieldnames), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})
    replace_with_retry(tmp, path)


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_status_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    write_csv(path, rows, STATUS_FIELDS)


def shot_sort_key(asset: Mapping[str, Any]) -> tuple[str, int]:
    shot_type = str(asset.get("shotType", ""))
    try:
        shot_idx = SHOT_ORDER.index(shot_type)
    except ValueError:
        shot_idx = len(SHOT_ORDER)
    return str(asset.get("profileId", "")), shot_idx
