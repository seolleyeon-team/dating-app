from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

from .config import pipeline_paths


CONFIG_FILENAME = "AI_IMAGE_DISTRIBUTION_TARGETS_V3.json"
FACE_TYPES = (
    "cat_like",
    "dog_like",
    "hamster_like",
    "bear_like",
    "fox_like",
    "deer_like",
    "horse_like",
    "mixed_neutral",
)
LOOKS_LEVEL_BANDS = ("1.5-2.4", "2.5-3.2", "3.3-3.8", "3.9-4.3", "4.4-5.0")
EYEWEAR_BUCKETS = ("with_eyewear", "without_eyewear")
SEASONS = ("spring", "summer", "autumn", "winter")
FACE_TYPE_ALIASES = {
    "neutral_mixed": "mixed_neutral",
    "mixed_neutral": "mixed_neutral",
}

DEFAULT_DISTRIBUTION_TARGETS: dict[str, Any] = {
    "schemaVersion": "seolleyeon_ai_image_distribution_v3",
    "countingUnit": "identity",
    "finalTarget": {
        "approvedCompleteIdentities": 240,
        "approvedImages": 720,
        "femaleApprovedIdentities": 120,
        "maleApprovedIdentities": 120,
        "shotsPerIdentity": 3,
        "requiredShotTypes": ["face_card", "silhouette_card", "vibe_card"],
    },
    "faceTypeTargets": {
        "global": {
            "cat_like": 34,
            "dog_like": 38,
            "hamster_like": 24,
            "bear_like": 29,
            "fox_like": 29,
            "deer_like": 43,
            "horse_like": 19,
            "mixed_neutral": 24,
        },
        "female": {
            "cat_like": 17,
            "dog_like": 19,
            "hamster_like": 12,
            "bear_like": 15,
            "fox_like": 14,
            "deer_like": 22,
            "horse_like": 9,
            "mixed_neutral": 12,
        },
        "male": {
            "cat_like": 17,
            "dog_like": 19,
            "hamster_like": 12,
            "bear_like": 14,
            "fox_like": 15,
            "deer_like": 21,
            "horse_like": 10,
            "mixed_neutral": 12,
        },
    },
    "looksLevelBandTargets": {
        "global": {"1.5-2.4": 36, "2.5-3.2": 108, "3.3-3.8": 72, "3.9-4.3": 24, "4.4-5.0": 0},
        "female": {"1.5-2.4": 18, "2.5-3.2": 54, "3.3-3.8": 36, "3.9-4.3": 12, "4.4-5.0": 0},
        "male": {"1.5-2.4": 18, "2.5-3.2": 54, "3.3-3.8": 36, "3.9-4.3": 12, "4.4-5.0": 0},
    },
    "eyewearTargets": {
        "global": {"with_eyewear": 36, "without_eyewear": 204},
        "female": {"with_eyewear": 12, "without_eyewear": 108},
        "male": {"with_eyewear": 24, "without_eyewear": 96},
        "reserve": {
            "female": {"with_eyewear": 2, "without_eyewear": 18},
            "male": {"with_eyewear": 4, "without_eyewear": 16},
        },
    },
    "seasonTargets": {
        "global": {"spring": 60, "summer": 53, "autumn": 79, "winter": 48},
    },
    "rules": {
        "countOnlyApprovedCompleteIdentities": True,
        "doNotCountNeedsReview": True,
        "doNotCountRejected": True,
        "doNotCountMetadataMismatch": True,
        "doNotCountOverLevel44To50": True,
        "finalDatasetRequiresExactCounts": True,
    },
}


def distribution_config_path(root: Path | str | None = None) -> Path:
    return pipeline_paths(root).ai_image / "config" / CONFIG_FILENAME


def load_distribution_targets(root: Path | str | None = None) -> dict[str, Any]:
    path = distribution_config_path(root)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return deepcopy(DEFAULT_DISTRIBUTION_TARGETS)


def write_default_distribution_targets(root: Path | str | None = None, *, force: bool = False) -> Path:
    path = distribution_config_path(root)
    if path.exists() and not force:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(DEFAULT_DISTRIBUTION_TARGETS, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def normalize_face_type(value: Any) -> str:
    raw = str(value or "").strip()
    return FACE_TYPE_ALIASES.get(raw, raw)


def looks_level_band(value: Any) -> str:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return ""
    if score <= 2.4:
        return "1.5-2.4"
    if score <= 3.2:
        return "2.5-3.2"
    if score <= 3.8:
        return "3.3-3.8"
    if score <= 4.3:
        return "3.9-4.3"
    if score <= 5.0:
        return "4.4-5.0"
    return "over_5.0"


def metadata_mapping(row: Mapping[str, Any]) -> Mapping[str, Any]:
    metadata = row.get("metadata")
    return metadata if isinstance(metadata, Mapping) else {}


def target_face_type(row: Mapping[str, Any]) -> str:
    if row.get("targetFaceType"):
        return normalize_face_type(row.get("targetFaceType"))
    metadata = metadata_mapping(row)
    face = metadata.get("face") if isinstance(metadata.get("face"), Mapping) else {}
    if isinstance(face, Mapping):
        return normalize_face_type(face.get("faceType"))
    return normalize_face_type(row.get("faceType"))


def target_looks_level(row: Mapping[str, Any]) -> float | None:
    for value in (row.get("targetLooksLevel"), row.get("looksLevel")):
        if value not in (None, ""):
            try:
                return float(value)
            except (TypeError, ValueError):
                pass
    metadata = metadata_mapping(row)
    face = metadata.get("face") if isinstance(metadata.get("face"), Mapping) else {}
    if isinstance(face, Mapping):
        try:
            return float(face.get("looksLevel"))
        except (TypeError, ValueError):
            return None
    return None


def target_looks_level_band(row: Mapping[str, Any]) -> str:
    if row.get("targetLooksLevelBand"):
        return str(row.get("targetLooksLevelBand"))
    level = target_looks_level(row)
    return looks_level_band(level)


def validate_distribution_targets(targets: Mapping[str, Any]) -> None:
    if targets.get("schemaVersion") != "seolleyeon_ai_image_distribution_v3":
        raise ValueError("Unexpected AI image distribution target schemaVersion.")
    for section in ("faceTypeTargets", "looksLevelBandTargets"):
        if section not in targets:
            raise ValueError(f"Distribution targets missing {section}.")
        for group in ("global", "female", "male"):
            if group not in targets[section]:
                raise ValueError(f"Distribution targets missing {section}.{group}.")
    if "eyewearTargets" in targets:
        for group in ("global", "female", "male"):
            if group not in targets["eyewearTargets"]:
                raise ValueError(f"Distribution targets missing eyewearTargets.{group}.")
            for bucket in EYEWEAR_BUCKETS:
                if bucket not in targets["eyewearTargets"][group]:
                    raise ValueError(f"Distribution targets missing eyewearTargets.{group}.{bucket}.")
    if "seasonTargets" in targets:
        season_targets = targets["seasonTargets"].get("global", targets["seasonTargets"])
        for season in SEASONS:
            if season not in season_targets:
                raise ValueError(f"Distribution targets missing seasonTargets.global.{season}.")
