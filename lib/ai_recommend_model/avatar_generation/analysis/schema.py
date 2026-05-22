from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .config import DEFAULT_SOURCE_ANALYSIS_VERSION

BBox = Tuple[float, float, float, float]


@dataclass(frozen=True)
class FaceDetection:
    bbox: BBox
    confidence: Optional[float] = None
    occlusion_score: Optional[float] = None
    landmarks: Any = field(default=None, repr=False, compare=False)

    @property
    def area_ratio(self) -> float:
        width = max(0.0, float(self.bbox[2]))
        height = max(0.0, float(self.bbox[3]))
        return round(width * height, 6)

    def to_document(self) -> Dict[str, object]:
        return {
            "bbox": [round(float(value), 6) for value in self.bbox],
            "confidence": (
                None if self.confidence is None else round(float(self.confidence), 6)
            ),
            "areaRatio": self.area_ratio,
            "occlusionScore": (
                None
                if self.occlusion_score is None
                else round(float(self.occlusion_score), 6)
            ),
        }


@dataclass(frozen=True)
class FaceDetectorResult:
    provider: str
    image_width: Optional[int]
    image_height: Optional[int]
    faces: Sequence[FaceDetection] = field(default_factory=list)
    provider_version: Optional[str] = None

    def to_document(self) -> Dict[str, object]:
        return {
            "provider": self.provider,
            "providerVersion": self.provider_version,
            "faceCount": len(self.faces),
        }


@dataclass(frozen=True)
class SourceAnalysisResult:
    status: str
    hard_reject: bool
    reject_reasons: Sequence[str]
    source_ref: str
    image_width: Optional[int]
    image_height: Optional[int]
    detector_provider: str
    detector_version: Optional[str] = None
    face_count: int = 0
    primary_face: Optional[FaceDetection] = None
    analysis_version: str = DEFAULT_SOURCE_ANALYSIS_VERSION
    completed_at: Optional[str] = None

    def to_document(self) -> Dict[str, object]:
        return {
            "analysisVersion": self.analysis_version,
            "completedAt": self.completed_at
            or datetime.now(tz=timezone.utc).isoformat(),
            "status": self.status,
            "hardReject": bool(self.hard_reject),
            "rejectReasons": list(self.reject_reasons),
            "sourceRef": self.source_ref,
            "image": {
                "width": self.image_width,
                "height": self.image_height,
            },
            "detector": {
                "provider": self.detector_provider,
                "providerVersion": self.detector_version,
            },
            "face": {
                "count": self.face_count,
                "areaRatio": (
                    None if self.primary_face is None else self.primary_face.area_ratio
                ),
                "confidence": (
                    None
                    if self.primary_face is None
                    else self.primary_face.to_document()["confidence"]
                ),
                "occlusionScore": (
                    None
                    if self.primary_face is None
                    else self.primary_face.to_document()["occlusionScore"]
                ),
            },
        }


def face_detection_from_mapping(value: Mapping[str, Any]) -> FaceDetection:
    bbox_value = value.get("bbox")
    if not isinstance(bbox_value, (list, tuple)) or len(bbox_value) != 4:
        raise ValueError("Face detection bbox must contain x, y, width, height.")
    return FaceDetection(
        bbox=tuple(float(item) for item in bbox_value),  # type: ignore[arg-type]
        confidence=_optional_float(value.get("confidence")),
        occlusion_score=_optional_float(
            value.get("occlusionScore", value.get("occlusion_score"))
        ),
        landmarks=value.get("landmarks"),
    )


def _optional_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    return float(value)


__all__ = [
    "FaceDetection",
    "FaceDetectorResult",
    "SourceAnalysisResult",
    "face_detection_from_mapping",
]
