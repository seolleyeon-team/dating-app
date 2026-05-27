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
    broad_traits: Mapping[str, str] = field(default_factory=dict)
    blendshape_categories: Mapping[str, str] = field(default_factory=dict)

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
    model_availability: Mapping[str, str] = field(default_factory=dict)
    metadata: Mapping[str, object] = field(default_factory=dict)

    def to_document(self) -> Dict[str, object]:
        document: Dict[str, object] = {
            "provider": self.provider,
            "providerVersion": self.provider_version,
            "faceCount": len(self.faces),
            "modelAvailability": dict(self.model_availability),
        }
        if self.metadata:
            document["metadata"] = dict(self.metadata)
        return document


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
    model_availability: Mapping[str, str] = field(default_factory=dict)
    detector_metadata: Mapping[str, object] = field(default_factory=dict)
    broad_trait_hints: Mapping[str, str] = field(default_factory=dict)
    face_count: int = 0
    primary_face: Optional[FaceDetection] = None
    primary_face_bbox: Optional[BBox] = None
    primary_face_confidence: Optional[float] = None
    primary_face_score: Optional[float] = None
    primary_face_score_margin: Optional[float] = None
    secondary_face_count: int = 0
    large_secondary_face_count: int = 0
    background_face_risk: str = "none"
    background_neutralization_required: bool = False
    analysis_version: str = DEFAULT_SOURCE_ANALYSIS_VERSION
    completed_at: Optional[str] = None

    def to_document(self) -> Dict[str, object]:
        detector: Dict[str, object] = {
            "provider": self.detector_provider,
            "providerVersion": self.detector_version,
        }
        if self.detector_metadata:
            detector["metadata"] = dict(self.detector_metadata)
        document: Dict[str, object] = {
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
            "detector": detector,
            "modelAvailability": (
                dict(self.model_availability)
            ),
            "broadTraitHints": dict(self.broad_trait_hints),
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
            "secondaryFaceCount": int(self.secondary_face_count),
            "largeSecondaryFaceCount": int(self.large_secondary_face_count),
            "backgroundFaceRisk": self.background_face_risk,
            "primaryFaceConfidence": (
                None
                if self.primary_face_confidence is None
                else round(float(self.primary_face_confidence), 6)
            ),
            "primaryFaceScore": (
                None
                if self.primary_face_score is None
                else round(float(self.primary_face_score), 6)
            ),
            "primaryFaceScoreMargin": (
                None
                if self.primary_face_score_margin is None
                else round(float(self.primary_face_score_margin), 6)
            ),
            "backgroundNeutralizationRequired": bool(
                self.background_neutralization_required
            ),
        }
        if self.primary_face_bbox is not None:
            document["primaryFaceBbox"] = [
                round(float(value), 3) for value in self.primary_face_bbox
            ]
        return document


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
        broad_traits=value.get("broadTraitHints", value.get("broad_traits", {}))
        if isinstance(value.get("broadTraitHints", value.get("broad_traits", {})), Mapping)
        else {},
        blendshape_categories=value.get(
            "blendshapeCategories",
            value.get("blendshape_categories", {}),
        )
        if isinstance(
            value.get("blendshapeCategories", value.get("blendshape_categories", {})),
            Mapping,
        )
        else {},
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
