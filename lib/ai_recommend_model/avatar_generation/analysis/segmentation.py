from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence

from PIL import Image, ImageChops

try:  # AV3-B may provide this shape; keep it optional for parallel work.
    from avatar_generation.analysis import FaceDetection as _AV3BFaceDetection
except Exception:  # pragma: no cover - depends on another worker's availability.
    _AV3BFaceDetection = None


@dataclass(frozen=True)
class FaceRegion:
    bbox: tuple[int, int, int, int]
    confidence: float | None = None
    source: str = "source_analysis"

    def clamped(self, image_size: tuple[int, int]) -> "FaceRegion | None":
        width, height = image_size
        left, top, right, bottom = self.bbox
        left = max(0, min(width, int(round(left))))
        top = max(0, min(height, int(round(top))))
        right = max(0, min(width, int(round(right))))
        bottom = max(0, min(height, int(round(bottom))))
        if right <= left or bottom <= top:
            return None
        return FaceRegion(
            bbox=(left, top, right, bottom),
            confidence=self.confidence,
            source=self.source,
        )


@dataclass(frozen=True)
class SegmentationResult:
    provider: str
    face_mask: Image.Image
    style_mask: Image.Image
    faces: tuple[FaceRegion, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_metadata(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "faceCount": len(self.faces),
            **_safe_segmentation_metadata(self.metadata),
        }


class ReferenceSegmenter(Protocol):
    def segment(
        self,
        image: Image.Image,
        *,
        face_hints: Sequence[FaceRegion] = (),
    ) -> SegmentationResult:
        ...


def face_regions_from_source_analysis(
    source_analysis: Any,
    image_size: tuple[int, int],
) -> tuple[FaceRegion, ...]:
    """Extract AV3-B-like face boxes without importing AV3-B as a hard dependency."""
    if source_analysis is None:
        return ()
    if isinstance(source_analysis, FaceRegion):
        clamped = source_analysis.clamped(image_size)
        return (clamped,) if clamped is not None else ()

    candidates: list[Any] = [source_analysis]
    to_document = getattr(source_analysis, "to_document", None)
    if callable(to_document):
        try:
            candidates.append(to_document())
        except Exception:
            pass

    faces: list[FaceRegion] = []
    for candidate in candidates:
        faces.extend(_extract_faces(candidate, image_size))

    deduped: list[FaceRegion] = []
    seen: set[tuple[int, int, int, int]] = set()
    for face in faces:
        clamped = face.clamped(image_size)
        if clamped is None or clamped.bbox in seen:
            continue
        seen.add(clamped.bbox)
        deduped.append(clamped)
    return tuple(deduped)


def fallback_segment_reference_regions(
    image: Image.Image,
    *,
    source_analysis: Any = None,
    face_regions: Sequence[FaceRegion] | None = None,
    provider: str | None = None,
    extra_metadata: Mapping[str, Any] | None = None,
) -> SegmentationResult:
    image_size = image.size
    faces = tuple(face_regions) if face_regions is not None else face_regions_from_source_analysis(source_analysis, image_size)
    clamped_faces = tuple(face for face in (face.clamped(image_size) for face in faces) if face is not None)

    face_mask = Image.new("L", image_size, 0)
    for face in clamped_faces:
        face_mask.paste(255, face.bbox)
    style_mask = ImageChops.invert(face_mask)

    mask_stat = face_mask.histogram()
    coverage = sum(index * count for index, count in enumerate(mask_stat)) / (255.0 * image_size[0] * image_size[1])
    metadata = {
        "maskCoverage": round(coverage, 6),
        **dict(extra_metadata or {}),
    }
    return SegmentationResult(
        provider=provider or ("source_analysis" if clamped_faces else "full_style"),
        face_mask=face_mask,
        style_mask=style_mask,
        faces=clamped_faces,
        metadata=metadata,
    )

_UNSAFE_METADATA_KEYS = {
    "bbox",
    "boundingbox",
    "box",
    "confidence",
    "face",
    "faces",
    "landmark",
    "landmarks",
}


def _is_unsafe_segmentation_metadata_key(key: object) -> bool:
    normalized_key = str(key).replace("_", "").lower()
    return (
        normalized_key in _UNSAFE_METADATA_KEYS
        or "bbox" in normalized_key
        or "confidence" in normalized_key
        or "landmark" in normalized_key
    )


def _safe_segmentation_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in metadata.items():
        if _is_unsafe_segmentation_metadata_key(key):
            continue
        if isinstance(value, Mapping):
            nested = _safe_segmentation_metadata(value)
            if nested:
                safe[str(key)] = nested
            continue
        if isinstance(value, (list, tuple, set)):
            continue
        safe[str(key)] = value
    return safe


def _extract_faces(value: Any, image_size: tuple[int, int]) -> list[FaceRegion]:
    if value is None:
        return []
    if isinstance(value, FaceRegion):
        return [value]

    faces_value = _field(value, "faces")
    if faces_value is not None and not isinstance(faces_value, (str, bytes, Mapping)):
        faces: list[FaceRegion] = []
        for item in faces_value:
            faces.extend(_extract_faces(item, image_size))
        return faces

    direct_face = _field(value, "face")
    primary_face = _field(value, "primaryFace") or _field(value, "primary_face")
    face_like = primary_face or direct_face or value
    bbox_value = (
        _field(face_like, "bbox")
        or _field(face_like, "boundingBox")
        or _field(face_like, "box")
        or _field(value, "primaryFaceBbox")
        or _field(value, "primary_face_bbox")
    )
    if bbox_value is None and face_like is not value:
        bbox_value = _field(value, "bbox") or _field(value, "boundingBox") or _field(value, "box")

    bbox = _bbox_to_pixels(bbox_value or face_like, image_size)
    if bbox is None:
        return []
    confidence = _field(face_like, "confidence")
    try:
        confidence = float(confidence) if confidence is not None else None
    except (TypeError, ValueError):
        confidence = None
    return [FaceRegion(bbox=bbox, confidence=confidence)]


def _field(value: Any, name: str) -> Any:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


def _bbox_to_pixels(value: Any, image_size: tuple[int, int]) -> tuple[int, int, int, int] | None:
    if value is None:
        return None
    width, height = image_size

    if isinstance(value, Mapping):
        if {"left", "top", "right", "bottom"}.issubset(value.keys()):
            coords = (value["left"], value["top"], value["right"], value["bottom"])
            return _xyxy_to_pixels(coords, image_size)
        if {"x", "y", "width", "height"}.issubset(value.keys()):
            coords = (value["x"], value["y"], value["width"], value["height"])
            return _xywh_to_pixels(coords, image_size)
        nested = value.get("bbox") or value.get("boundingBox") or value.get("box")
        if nested is not None:
            return _bbox_to_pixels(nested, image_size)
        return None

    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) < 4:
        return None
    coords = tuple(float(value[index]) for index in range(4))
    if all(0.0 <= coordinate <= 1.0 for coordinate in coords):
        return _xywh_to_pixels(coords, image_size)
    return _xywh_to_pixels(coords, image_size)


def _xywh_to_pixels(coords: Sequence[float], image_size: tuple[int, int]) -> tuple[int, int, int, int]:
    width, height = image_size
    x, y, box_width, box_height = coords
    if all(0.0 <= coordinate <= 1.0 for coordinate in coords):
        left = x * width
        top = y * height
        right = (x + box_width) * width
        bottom = (y + box_height) * height
    else:
        left = x
        top = y
        right = x + box_width
        bottom = y + box_height
    return (int(round(left)), int(round(top)), int(round(right)), int(round(bottom)))


def _xyxy_to_pixels(coords: Sequence[float], image_size: tuple[int, int]) -> tuple[int, int, int, int]:
    width, height = image_size
    left, top, right, bottom = coords
    if all(0.0 <= coordinate <= 1.0 for coordinate in coords):
        left *= width
        right *= width
        top *= height
        bottom *= height
    return (int(round(left)), int(round(top)), int(round(right)), int(round(bottom)))
