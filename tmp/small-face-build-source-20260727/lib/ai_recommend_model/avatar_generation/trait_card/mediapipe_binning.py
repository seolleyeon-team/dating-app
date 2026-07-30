from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping, Sequence

from .schema import UNCLEAR, AvatarTraitCard, TraitCardValidationResult


BROAD_HINT_FIELDS = {
    "face_shape_category",
    "facial_feature_balance",
    "eye_size_category",
    "eye_shape_mood",
    "brow_shape",
    "nose_prominence",
    "nose_bridge_impression",
    "mouth_expression",
    "mouth_fullness_category",
}


def build_broad_trait_hints(
    *,
    face_bbox: Sequence[float] | None = None,
    landmarks: Sequence[Any] | None = None,
    blendshapes: Mapping[str, float] | None = None,
) -> dict[str, str]:
    """Convert MediaPipe outputs into broad enum hints only.

    Raw landmark coordinates and raw blendshape vectors are intentionally not
    returned. This helper is for coarse source analysis, not identity
    conditioning.
    """
    hints: dict[str, str] = {}
    bbox = _bbox_tuple(face_bbox)
    if bbox is not None:
        _, _, width, height = bbox
        ratio = width / max(height, 1e-6)
        if ratio >= 0.88:
            hints["face_shape_category"] = "round"
        elif ratio <= 0.62:
            hints["face_shape_category"] = "long"
        else:
            hints["face_shape_category"] = "oval"

        area = max(0.0, width) * max(0.0, height)
        if area >= 0.18:
            hints["facial_feature_balance"] = "balanced"
        elif area >= 0.08:
            hints["facial_feature_balance"] = "soft"

    landmarks_list = list(landmarks or [])
    if len(landmarks_list) >= 468:
        hints.update(_landmark_shape_hints(landmarks_list))

    blendshape_hints = _blendshape_hints(blendshapes or {})
    hints.update({key: value for key, value in blendshape_hints.items() if value != UNCLEAR})

    return {key: value for key, value in hints.items() if key in BROAD_HINT_FIELDS and value != UNCLEAR}


def merge_trait_card_with_broad_hints(
    validation: TraitCardValidationResult,
    hints: Mapping[str, Any] | None,
) -> TraitCardValidationResult:
    """Merge broad MediaPipe hints into a validated card without raw geometry."""
    if not hints:
        return validation

    current = validation.trait_card.to_dict()
    merged = dict(current)
    for key, value in hints.items():
        if key not in BROAD_HINT_FIELDS:
            continue
        text = str(value or "").strip()
        if not text or text == UNCLEAR:
            continue
        if key == "mouth_expression":
            merged[key] = text
            continue
        if current.get(key, UNCLEAR) == UNCLEAR:
            merged[key] = text

    return replace(
        validation,
        trait_card=AvatarTraitCard(**{
            key: merged.get(key, value)
            for key, value in current.items()
        }),
    )


def _bbox_tuple(face_bbox: Sequence[float] | None) -> tuple[float, float, float, float] | None:
    if face_bbox is None or len(face_bbox) != 4:
        return None
    try:
        return tuple(float(value) for value in face_bbox)  # type: ignore[return-value]
    except (TypeError, ValueError):
        return None


def _landmark_shape_hints(landmarks: Sequence[Any]) -> dict[str, str]:
    hints: dict[str, str] = {}
    left_eye = _distance(landmarks, 33, 133)
    right_eye = _distance(landmarks, 362, 263)
    face_width = _distance(landmarks, 234, 454)
    if face_width and left_eye and right_eye:
        eye_ratio = ((left_eye + right_eye) / 2.0) / face_width
        if eye_ratio < 0.115:
            hints["eye_size_category"] = "small"
        elif eye_ratio > 0.155:
            hints["eye_size_category"] = "medium_large"
        else:
            hints["eye_size_category"] = "medium"

    left_brow_span = _distance(landmarks, 70, 107)
    right_brow_span = _distance(landmarks, 336, 300)
    if face_width and left_brow_span and right_brow_span:
        brow_ratio = ((left_brow_span + right_brow_span) / 2.0) / face_width
        if brow_ratio < 0.13:
            hints["brow_shape"] = "straight"
        elif brow_ratio > 0.20:
            hints["brow_shape"] = "arched"
        else:
            hints["brow_shape"] = "soft_arch"

    mouth_width = _distance(landmarks, 61, 291)
    mouth_height = _distance(landmarks, 13, 14)
    if face_width and mouth_width:
        fullness_ratio = (mouth_height or 0.0) / max(mouth_width, 1e-6)
        if fullness_ratio < 0.10:
            hints["mouth_fullness_category"] = "thin"
        elif fullness_ratio > 0.22:
            hints["mouth_fullness_category"] = "full"
        else:
            hints["mouth_fullness_category"] = "medium"
    return hints


def _blendshape_hints(blendshapes: Mapping[str, float]) -> dict[str, str]:
    smile = max(
        _score(blendshapes, "mouthSmileLeft"),
        _score(blendshapes, "mouthSmileRight"),
    )
    jaw_open = _score(blendshapes, "jawOpen")
    if smile >= 0.30:
        expression = "subtle_smile"
    elif jaw_open <= 0.08:
        expression = "calm_closed"
    else:
        expression = "neutral"
    return {"mouth_expression": expression}


def _score(values: Mapping[str, float], key: str) -> float:
    try:
        return float(values.get(key, 0.0))
    except (TypeError, ValueError):
        return 0.0


def _distance(landmarks: Sequence[Any], first: int, second: int) -> float | None:
    try:
        a = landmarks[first]
        b = landmarks[second]
        ax, ay = float(a.x), float(a.y)
        bx, by = float(b.x), float(b.y)
    except (AttributeError, IndexError, TypeError, ValueError):
        return None
    return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5


__all__ = [
    "BROAD_HINT_FIELDS",
    "build_broad_trait_hints",
    "merge_trait_card_with_broad_hints",
]
