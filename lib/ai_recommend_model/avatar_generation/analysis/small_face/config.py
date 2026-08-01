from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Tuple


def _env_bool(name: str, fallback: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return fallback
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return fallback


def _env_float(name: str, fallback: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return fallback
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"Invalid float for {name}: {raw!r}") from exc


def _env_int(name: str, fallback: int, *, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return fallback
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"Invalid int for {name}: {raw!r}") from exc
    if value < minimum or value > maximum:
        raise ValueError(f"{name}={value} out of range [{minimum}, {maximum}]")
    return value


def _env_text(name: str, fallback: str) -> str:
    return os.environ.get(name, "").strip() or fallback


def _parse_grids(raw: str) -> Tuple[int, ...]:
    parts = [part.strip() for part in raw.split(",") if part.strip()]
    grids = tuple(int(part) for part in parts)
    if not grids:
        raise ValueError("AVATAR_FACE_TILE_GRIDS must not be empty")
    for grid in grids:
        if grid < 2 or grid > 4:
            raise ValueError(f"Unsupported tile grid size: {grid}")
    return grids


@dataclass(frozen=True)
class PrimaryScoreWeights:
    confidence: float = 0.35
    face_area: float = 0.25
    center_proximity: float = 0.20
    border_clearance: float = 0.10
    sharpness: float = 0.10


@dataclass(frozen=True)
class SmallFacePipelineConfig:
    enabled: bool = False
    blur_shadow_enabled: bool = False
    full_range_enabled: bool = True
    face_detect_model_path: str = ""
    primary_min_confidence: float = 0.45
    fallback_min_confidence: float = 0.35
    nms_iou_threshold: float = 0.35
    cross_pass_nms_iou: float = 0.35
    tile_fallback_enabled: bool = True
    tile_grids: Tuple[int, ...] = (2, 3)
    tile_overlap: float = 0.25
    tile_max_count: int = 13
    min_short_side_detect_px: int = 48
    min_short_side_trait_px: int = 64
    primary_score_gap_min: float = 0.12
    secondary_primary_area_ratio_max: float = 0.55
    primary_crop_target_size: int = 512
    primary_crop_max_size: int = 768
    crop_expand_horizontal: float = 0.55
    crop_expand_top: float = 0.80
    crop_expand_bottom: float = 1.05
    secondary_mask_expand: float = 0.25
    secondary_blur_radius: float = 18.0
    score_weights: PrimaryScoreWeights = PrimaryScoreWeights()
    fail_closed_without_model: bool = True

    @classmethod
    def from_env(cls) -> "SmallFacePipelineConfig":
        grids = _parse_grids(_env_text("AVATAR_FACE_TILE_GRIDS", "2,3"))
        cfg = cls(
            enabled=_env_bool("AVATAR_SMALL_FACE_PIPELINE_ENABLED", False),
            blur_shadow_enabled=_env_bool("AVATAR_BLUR_SHADOW_ENABLED", False),
            full_range_enabled=_env_bool("AVATAR_FACE_FULL_RANGE_ENABLED", True),
            face_detect_model_path=_env_text("AVATAR_FACE_DETECT_MODEL_PATH", ""),
            primary_min_confidence=_env_float(
                "AVATAR_FACE_DETECT_PRIMARY_MIN_CONFIDENCE", 0.45
            ),
            fallback_min_confidence=_env_float(
                "AVATAR_FACE_DETECT_FALLBACK_MIN_CONFIDENCE", 0.35
            ),
            nms_iou_threshold=_env_float(
                "AVATAR_FACE_DETECT_NMS_IOU_THRESHOLD", 0.35
            ),
            cross_pass_nms_iou=_env_float("AVATAR_FACE_CROSS_PASS_NMS_IOU", 0.35),
            tile_fallback_enabled=_env_bool("AVATAR_FACE_TILE_FALLBACK_ENABLED", True),
            tile_grids=grids,
            tile_overlap=_env_float("AVATAR_FACE_TILE_OVERLAP", 0.25),
            tile_max_count=_env_int(
                "AVATAR_FACE_TILE_MAX_COUNT", 13, minimum=4, maximum=25
            ),
            min_short_side_detect_px=_env_int(
                "AVATAR_FACE_MIN_SHORT_SIDE_DETECT_PX", 48, minimum=16, maximum=512
            ),
            min_short_side_trait_px=_env_int(
                "AVATAR_FACE_MIN_SHORT_SIDE_TRAIT_PX", 64, minimum=24, maximum=1024
            ),
            primary_score_gap_min=_env_float("AVATAR_PRIMARY_FACE_SCORE_GAP_MIN", 0.12),
            secondary_primary_area_ratio_max=_env_float(
                "AVATAR_SECONDARY_PRIMARY_AREA_RATIO_MAX", 0.55
            ),
            primary_crop_target_size=_env_int(
                "AVATAR_PRIMARY_CROP_TARGET_SIZE", 512, minimum=256, maximum=1024
            ),
            primary_crop_max_size=_env_int(
                "AVATAR_PRIMARY_CROP_MAX_SIZE", 768, minimum=256, maximum=1536
            ),
        )
        if cfg.primary_crop_max_size < cfg.primary_crop_target_size:
            raise ValueError(
                "AVATAR_PRIMARY_CROP_MAX_SIZE must be >= AVATAR_PRIMARY_CROP_TARGET_SIZE"
            )
        if not (0.0 < cfg.tile_overlap < 0.9):
            raise ValueError("AVATAR_FACE_TILE_OVERLAP must be in (0, 0.9)")
        return cfg


__all__ = ["PrimaryScoreWeights", "SmallFacePipelineConfig"]
