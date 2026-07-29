from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Protocol, Sequence, Tuple

BBoxXYXY = Tuple[float, float, float, float]

TASK_OCR_WITH_REGION = "<OCR_WITH_REGION>"
TASK_OD = "<OD>"
TASK_MORE_DETAILED_CAPTION = "<MORE_DETAILED_CAPTION>"

STATUS_AVAILABLE = "available"
STATUS_CRITICAL_UNAVAILABLE = "critical_unavailable"
STATUS_NEEDS_REVIEW = "needs_review"

RISK_PASS = "pass"
RISK_REVIEW = "review"
RISK_BLOCK = "block"

ACTION_MANUAL_REVIEW = "manual_review"
ACTION_NEEDS_REVIEW = "needs_review"
ACTION_NEUTRALIZE_TEXT_LOGO = "neutralize_text_logo"
ACTION_NEUTRALIZE_BACKGROUND_PERSON = "neutralize_background_person"
ACTION_REVIEW_BACKGROUND_COMPLEXITY = "review_background_complexity"

KIND_TEXT = "text"
KIND_LOGO = "logo"
KIND_SIGN = "sign"
KIND_PERSON = "person"
KIND_BACKGROUND_PERSON = "background-person"

TEXT_LOGO_KINDS = {KIND_TEXT, KIND_LOGO, KIND_SIGN}
REVIEW_KINDS = {*TEXT_LOGO_KINDS, KIND_BACKGROUND_PERSON}


@dataclass(frozen=True)
class VisualRiskRegion:
    kind: str
    bbox_xyxy: BBoxXYXY = field(repr=False)
    confidence: Optional[float] = None
    status: str = STATUS_NEEDS_REVIEW

    @property
    def bbox(self) -> BBoxXYXY:
        return self.bbox_xyxy


@dataclass(frozen=True)
class VisualRiskAnalysis:
    provider: str
    provider_available: bool
    regions: Tuple[VisualRiskRegion, ...] = field(default_factory=tuple, repr=False)
    status: str = STATUS_AVAILABLE
    risk: str = RISK_PASS
    actions_required: Tuple[str, ...] = field(default_factory=tuple)
    detector_availability: Mapping[str, str] = field(default_factory=dict)
    background_complexity: str = "unknown"
    background_complexity_risk_count: int = 0
    error_code: Optional[str] = None

    def to_document(self) -> Dict[str, object]:
        counts: Dict[str, int] = {}
        for region in self.regions:
            counts[region.kind] = counts.get(region.kind, 0) + 1
        document: Dict[str, object] = {
            "provider": self.provider,
            "providerAvailable": self.provider_available,
            "detectorAvailability": dict(self.detector_availability),
            "status": self.status,
            "risk": self.risk,
            "actionsRequired": list(self.actions_required),
            "regionCounts": counts,
            "backgroundComplexity": self.background_complexity,
            "backgroundComplexityRiskCount": self.background_complexity_risk_count,
        }
        if self.error_code:
            document["errorCode"] = self.error_code
        return document

    @property
    def sanitized_metadata(self) -> Dict[str, object]:
        return self.to_document()


class VisualRiskAdapter(Protocol):
    provider: str

    def analyze(
        self,
        image: Any,
        *,
        primary_face_bbox_xyxy: Optional[Sequence[float]] = None,
    ) -> VisualRiskAnalysis:
        ...


def unavailable_visual_risk_analysis(
    provider: str,
    *,
    error_code: str,
    status: str = STATUS_CRITICAL_UNAVAILABLE,
) -> VisualRiskAnalysis:
    return VisualRiskAnalysis(
        provider=provider,
        provider_available=False,
        status=status,
        risk=RISK_BLOCK,
        actions_required=(ACTION_MANUAL_REVIEW, ACTION_NEEDS_REVIEW),
        detector_availability={
            TASK_OCR_WITH_REGION: status,
            TASK_OD: status,
        },
        error_code=error_code,
    )


def analyze_florence_visual_risk_outputs(
    outputs: Mapping[str, Any],
    *,
    provider: str = "florence2",
    image_size: Optional[Tuple[int, int]] = None,
    primary_face_bbox_xyxy: Optional[Sequence[float]] = None,
) -> VisualRiskAnalysis:
    try:
        regions = _parse_florence_regions(
            outputs,
            image_size=image_size,
            primary_face_bbox_xyxy=primary_face_bbox_xyxy,
        )
    except (TypeError, ValueError, KeyError, IndexError):
        return unavailable_visual_risk_analysis(
            provider,
            error_code="malformed_florence_output",
            status=STATUS_NEEDS_REVIEW,
        )

    complexity = _classify_background_complexity(outputs.get(TASK_MORE_DETAILED_CAPTION), regions)
    complexity_risk_count = 1 if complexity == "high" else 0
    actions = _actions_for(regions, complexity)
    risk = RISK_REVIEW if actions else RISK_PASS
    return VisualRiskAnalysis(
        provider=provider,
        provider_available=True,
        regions=regions,
        status=STATUS_NEEDS_REVIEW if risk == RISK_REVIEW else STATUS_AVAILABLE,
        risk=risk,
        actions_required=actions,
        detector_availability={
            TASK_OCR_WITH_REGION: STATUS_AVAILABLE,
            TASK_OD: STATUS_AVAILABLE,
            TASK_MORE_DETAILED_CAPTION: (
                STATUS_AVAILABLE
                if TASK_MORE_DETAILED_CAPTION in outputs
                else "not_requested"
            ),
        },
        background_complexity=complexity,
        background_complexity_risk_count=complexity_risk_count,
    )


def _parse_florence_regions(
    outputs: Mapping[str, Any],
    *,
    image_size: Optional[Tuple[int, int]],
    primary_face_bbox_xyxy: Optional[Sequence[float]],
) -> Tuple[VisualRiskRegion, ...]:
    if TASK_OCR_WITH_REGION not in outputs or TASK_OD not in outputs:
        raise KeyError("required Florence task output missing")

    regions = []
    ocr = _task_payload(outputs, TASK_OCR_WITH_REGION)
    quad_boxes = ocr.get("quad_boxes", [])
    ocr_labels = ocr.get("labels", [])
    if len(quad_boxes) != len(ocr_labels):
        raise ValueError("OCR quad_boxes/labels length mismatch")
    for quad, label in zip(quad_boxes, ocr_labels):
        if _has_visible_label(label):
            regions.append(
                VisualRiskRegion(_classify_ocr_label(label), _quad_to_xyxy(quad, image_size))
            )

    od = _task_payload(outputs, TASK_OD)
    bboxes = od.get("bboxes", [])
    labels = od.get("labels", [])
    if len(bboxes) != len(labels):
        raise ValueError("OD bboxes/labels length mismatch")
    primary_bbox = _normalize_bbox(primary_face_bbox_xyxy, image_size) if primary_face_bbox_xyxy else None
    for bbox, label in zip(bboxes, labels):
        bbox_xyxy = _normalize_bbox(bbox, image_size)
        kind = _classify_od_label(label)
        if kind is None:
            continue
        if kind == KIND_PERSON and not _is_primary_person(bbox_xyxy, primary_bbox):
            kind = KIND_BACKGROUND_PERSON
        regions.append(VisualRiskRegion(kind, bbox_xyxy))

    return tuple(regions)


def _task_payload(outputs: Mapping[str, Any], task: str) -> Mapping[str, Any]:
    payload = outputs[task]
    if isinstance(payload, Mapping) and task in payload and isinstance(payload[task], Mapping):
        payload = payload[task]
    if not isinstance(payload, Mapping):
        raise TypeError(f"{task} output must be a mapping")
    return payload


def _classify_ocr_label(label: object) -> str:
    lowered = str(label).lower()
    if any(token in lowered for token in ("logo", "brand", "trademark")):
        return KIND_LOGO
    if any(token in lowered for token in ("sign", "poster", "banner", "billboard")):
        return KIND_SIGN
    return KIND_TEXT


def _classify_od_label(label: object) -> Optional[str]:
    lowered = str(label).lower()
    if "person" in lowered or "human" in lowered:
        return KIND_PERSON
    if any(token in lowered for token in ("logo", "brand", "trademark")):
        return KIND_LOGO
    if any(token in lowered for token in ("sign", "poster", "banner", "billboard")):
        return KIND_SIGN
    return None


def _classify_background_complexity(
    caption_payload: object,
    regions: Sequence[VisualRiskRegion],
) -> str:
    background_count = sum(1 for region in regions if region.kind == KIND_BACKGROUND_PERSON)
    sign_count = sum(1 for region in regions if region.kind in TEXT_LOGO_KINDS)
    caption = _caption_text(caption_payload).lower()
    busy_tokens = ("crowd", "busy", "market", "street", "text", "sign", "poster", "many people")
    if background_count >= 2 or sign_count >= 3 or any(token in caption for token in busy_tokens):
        return "high"
    if background_count == 1 or sign_count > 0:
        return "medium"
    return "low" if caption_payload is not None or regions else "unknown"


def _actions_for(regions: Sequence[VisualRiskRegion], complexity: str) -> Tuple[str, ...]:
    actions = []
    if any(region.kind in TEXT_LOGO_KINDS for region in regions):
        actions.append(ACTION_NEUTRALIZE_TEXT_LOGO)
    if any(region.kind == KIND_BACKGROUND_PERSON for region in regions):
        actions.append(ACTION_NEUTRALIZE_BACKGROUND_PERSON)
    if complexity == "high":
        actions.append(ACTION_REVIEW_BACKGROUND_COMPLEXITY)
    return tuple(actions)


def _caption_text(caption_payload: object) -> str:
    if isinstance(caption_payload, Mapping):
        nested = caption_payload.get(TASK_MORE_DETAILED_CAPTION, caption_payload.get("caption", ""))
        return str(nested)
    return "" if caption_payload is None else str(caption_payload)


def _has_visible_label(label: object) -> bool:
    return bool(str(label).strip())


def _quad_to_xyxy(quad: Sequence[float], image_size: Optional[Tuple[int, int]]) -> BBoxXYXY:
    values = [float(value) for value in quad]
    if len(values) != 8:
        raise ValueError("quad must contain 8 coordinates")
    xs = values[0::2]
    ys = values[1::2]
    return _normalize_bbox((min(xs), min(ys), max(xs), max(ys)), image_size)


def _normalize_bbox(
    bbox: Optional[Sequence[float]],
    image_size: Optional[Tuple[int, int]],
) -> BBoxXYXY:
    if bbox is None:
        raise ValueError("bbox is required")
    values = [float(value) for value in bbox]
    if len(values) != 4:
        raise ValueError("bbox must contain 4 coordinates")
    left, top, right, bottom = values
    if right < left or bottom < top:
        raise ValueError("bbox must be xyxy")
    if image_size is not None:
        width, height = image_size
        left = min(max(left, 0.0), float(width))
        right = min(max(right, 0.0), float(width))
        top = min(max(top, 0.0), float(height))
        bottom = min(max(bottom, 0.0), float(height))
    return (left, top, right, bottom)


def _is_primary_person(
    person_bbox: BBoxXYXY,
    primary_face_bbox: Optional[BBoxXYXY],
) -> bool:
    if primary_face_bbox is None:
        return False
    face_left, face_top, face_right, face_bottom = primary_face_bbox
    face_center_x = (face_left + face_right) / 2.0
    face_center_y = (face_top + face_bottom) / 2.0
    left, top, right, bottom = person_bbox
    if not (left <= face_center_x <= right and top <= face_center_y <= bottom):
        return False
    face_area = max(0.0, face_right - face_left) * max(0.0, face_bottom - face_top)
    if face_area <= 0.0:
        return False
    return _intersection_area(person_bbox, primary_face_bbox) / face_area >= 0.5


def _intersection_area(a: BBoxXYXY, b: BBoxXYXY) -> float:
    left = max(a[0], b[0])
    top = max(a[1], b[1])
    right = min(a[2], b[2])
    bottom = min(a[3], b[3])
    return max(0.0, right - left) * max(0.0, bottom - top)
