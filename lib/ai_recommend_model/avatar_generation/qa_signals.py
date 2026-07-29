from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Callable, Mapping, Optional, Protocol, Sequence, Tuple

from PIL import Image

from .analysis.image_quality import analyze_image_quality
from .analysis.schema import FaceDetection, FaceDetectorResult
from .analysis.visual_risk import (
    ACTION_NEUTRALIZE_BACKGROUND_PERSON,
    ACTION_NEUTRALIZE_TEXT_LOGO,
    STATUS_CRITICAL_UNAVAILABLE,
    TEXT_LOGO_KINDS,
    VisualRiskAnalysis,
)

MIN_CONFIDENCE = 0.75
ADULT_LIKE_MINIMUM = 0.55
BRAND_FIT_MINIMUM = 0.55
SEVERE_RISK_THRESHOLD = 0.85

SENSITIVE_EXACT_KEYS = {
    "bbox",
    "bbox_xyxy",
    "box",
    "boxes",
    "embedding",
    "embeddings",
    "gender",
    "image",
    "image_bytes",
    "image_ref",
    "label",
    "labels",
    "ocr",
    "ocr_text",
    "ocrtext",
    "path",
    "pixels",
    "primary_face_bbox",
    "primaryfacebbox",
    "prompt",
    "quad_boxes",
    "raw_prompt",
    "rawprompt",
    "reference_ref",
    "referenceref",
    "ref",
    "source_ref",
    "sourceref",
    "text",
    "url",
    "uri",
}
SENSITIVE_SUFFIXES = ("_bbox", "_embedding", "_image", "_label", "_ocr", "_prompt", "_ref")
UNCERTAIN_VALUES = {"", "unknown", "uncertain", "unsure", "n/a", "none_detected"}


class FaceDetector(Protocol):
    def detect(self, image: Image.Image) -> FaceDetectorResult:
        ...


class VisualRiskAdapter(Protocol):
    def analyze(
        self,
        image: Image.Image,
        *,
        primary_face_bbox_xyxy: Optional[Sequence[float]] = None,
    ) -> VisualRiskAnalysis:
        ...


class LocalSafetyRiskAdapter(Protocol):
    def analyze(self, image: Image.Image) -> Any:
        ...


class SimilarityAdapter(Protocol):
    def compare(
        self,
        source_crop: Image.Image,
        candidate_crop: Image.Image,
        *,
        calibration_policy: Any = None,
    ) -> Any:
        ...


@dataclass(frozen=True)
class LocalSafetyRiskResult:
    provider: str
    available: bool
    calibrated: bool
    childlike_score: float | None = None
    sexualized_score: float | None = None
    beautification_score: float | None = None
    brand_mismatch_score: float | None = None
    artifact_score: float | None = None
    severe_artifact_score: float | None = None
    adult_like: bool | None = None
    brand_fit: bool | None = None
    adult_like_score: float | None = None
    brand_fit_score: float | None = None
    calibration_version: str | None = None
    availability_reason: str | None = None
    needs_review: bool = False

    def to_document(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "available": bool(self.available),
            "calibrated": bool(self.calibrated),
            "calibrationVersion": self.calibration_version,
            "availabilityReason": _safe_status(self.availability_reason),
            "needsReview": bool(self.needs_review),
        }


@dataclass(frozen=True, repr=False)
class CandidateQASignalResult:
    signals: Mapping[str, Any]
    model_availability: Mapping[str, str]
    stage: str = "candidate_qa_signals"
    cascade: Tuple[str, ...] = field(default_factory=tuple)
    models_unavailable: Tuple[str, ...] = field(default_factory=tuple)
    needs_review: bool = False
    skipped_heavy_reason: str | None = None
    trait_matches: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "signals", MappingProxyType(dict(self.signals)))
        object.__setattr__(self, "model_availability", MappingProxyType(dict(self.model_availability)))
        object.__setattr__(self, "cascade", tuple(self.cascade))
        object.__setattr__(self, "models_unavailable", tuple(self.models_unavailable))
        object.__setattr__(self, "trait_matches", MappingProxyType(dict(self.trait_matches)))

    @property
    def modelsUnavailable(self) -> bool:
        return bool(self.models_unavailable)

    def to_document(self) -> dict[str, object]:
        document: dict[str, object] = {
            "stage": self.stage,
            "cascade": list(self.cascade),
            "signals": _sanitize_document(self.signals),
            "modelAvailability": _sanitize_document(self.model_availability),
            "modelsUnavailable": self.modelsUnavailable,
            "modelsUnavailableKeys": list(self.models_unavailable),
            "needsReview": bool(self.needs_review),
            "skippedHeavyReason": self.skipped_heavy_reason,
        }
        if self.trait_matches:
            document["traitMatches"] = _sanitize_document(self.trait_matches)
        return document

    def __repr__(self) -> str:
        return f"CandidateQASignalResult({self.to_document()!r})"


def build_candidate_qa_signals(
    *,
    source_image: Image.Image,
    candidate_image: Image.Image,
    source_analysis: Mapping[str, Any],
    reference_preprocess: Mapping[str, Any],
    source_traits: Mapping[str, Any] | None = None,
    candidate_traits: Mapping[str, Any] | None = None,
    source_primary_bbox: Sequence[float] | None = None,
    face_detector: FaceDetector,
    visual_risk_adapter: VisualRiskAdapter,
    local_risk_adapter: LocalSafetyRiskAdapter | Callable[..., Any],
    similarity_adapter: SimilarityAdapter | Callable[..., Any] | None = None,
    similarity_policy: Any = None,
    allow_similarity: bool = True,
) -> CandidateQASignalResult:
    signals: dict[str, Any] = {}
    availability: dict[str, str] = {}
    unavailable: list[str] = []
    cascade: list[str] = []
    needs_review = False
    skipped_heavy_reason: str | None = None
    primary_face: FaceDetection | None = None
    face_count: int | None = None

    quality = analyze_image_quality(candidate_image)
    cascade.append("image_quality")
    _add_quality_signals(signals, quality)

    try:
        candidate_faces = face_detector.detect(candidate_image)
        cascade.append("candidate_face_detection")
        face_unavailable = _face_detector_unavailable(candidate_faces)
        availability.update(_availability_from_face_detector(candidate_faces, unavailable=face_unavailable))
        if face_unavailable:
            unavailable.append("faceDetector")
            needs_review = True
        primary_face = _primary_face(candidate_faces.faces)
        face_count = len(candidate_faces.faces)
        signals["primaryFaceConfidence"] = _rounded(primary_face.confidence if primary_face else None)
        if face_unavailable:
            # An unavailable detector cannot support a hard no-face or multi-face decision.
            signals["cropConsistent"] = None
            if signals.get("cropIsolationQuality") != "fail":
                signals["cropIsolationQuality"] = "needs_review"
        else:
            signals["cropConsistent"] = face_count == 1
            if signals.get("cropIsolationQuality") != "fail":
                signals["cropIsolationQuality"] = "pass" if face_count == 1 else "fail"
            if face_count == 0:
                signals["noFaceDetected"] = True
            elif face_count > 1:
                signals["multipleFacesGenerated"] = True
                signals["secondaryFaceLeakageRisk"] = "high"
    except Exception as exc:
        cascade.append("candidate_face_detection")
        availability["faceDetector"] = "unavailable"
        availability["faceDetector.error"] = _exception_code(exc)
        unavailable.append("faceDetector")
        needs_review = True
        signals["primaryFaceConfidence"] = None
        signals["cropConsistent"] = None
        signals["cropIsolationQuality"] = "needs_review"

    try:
        visual = visual_risk_adapter.analyze(
            candidate_image,
            primary_face_bbox_xyxy=_bbox_to_xyxy(primary_face.bbox, candidate_image.size) if primary_face else None,
        )
        cascade.append("visual_risk")
        availability["visualRisk"] = _availability_status(
            getattr(visual, "provider_available", False), getattr(visual, "status", None)
        )
        availability.update(
            {
                f"visualRisk.{key}": _safe_status(value)
                for key, value in getattr(visual, "detector_availability", {}).items()
            }
        )
        if _critical_unavailable(visual):
            unavailable.append("visualRisk")
            needs_review = True
        _add_visual_signals(signals, visual)
    except Exception as exc:
        cascade.append("visual_risk")
        availability["visualRisk"] = "unavailable"
        availability["visualRisk.error"] = _exception_code(exc)
        unavailable.append("visualRisk")
        needs_review = True
        signals.setdefault("textLogoWatermarkRisk", "medium")
        signals.setdefault("backgroundLeakageRisk", "medium")
        signals.setdefault("secondaryFaceLeakageRisk", "medium")

    try:
        local_risk = _normalize_local_risk(_run_local_risk(local_risk_adapter, candidate_image))
        cascade.append("local_safety_risk")
    except Exception as exc:
        local_risk = _unavailable_local_risk(_exception_code(exc))
        cascade.append("local_safety_risk")
    availability["localSafetyRisk"] = _local_risk_status(local_risk)
    availability["localSafetyRisk.calibrationVersion"] = _safe_status(local_risk.calibration_version)
    availability["localSafetyRisk.needsReview"] = "true" if local_risk.needs_review else "false"
    if not local_risk.available:
        unavailable.append("localSafetyRisk")
        needs_review = True
        signals["adultLike"] = None
        signals["brandFit"] = None
    elif not local_risk.calibrated:
        availability["localSafetyRisk"] = "uncalibrated"
        unavailable.append("localSafetyRisk")
        needs_review = True
        signals["adultLike"] = None
        signals["brandFit"] = None
    else:
        _add_local_risk_signals(signals, availability, local_risk)
        if local_risk.needs_review:
            needs_review = True

    trait_matches = _compare_traits(source_traits or {}, candidate_traits or {})
    if any(value == "review" for value in trait_matches.values()):
        needs_review = True
    if any(value == "mismatch" for value in trait_matches.values()):
        needs_review = True
        signals["hardTraitContradiction"] = True

    hard_lightweight_issue = _has_hard_lightweight_issue(signals)
    if unavailable:
        skipped_heavy_reason = "critical_model_unavailable"
    elif hard_lightweight_issue:
        skipped_heavy_reason = "hard_lightweight_issue"
    elif not allow_similarity:
        skipped_heavy_reason = "similarity_not_allowed"
    elif similarity_adapter is None:
        skipped_heavy_reason = "similarity_unavailable"
        availability["faceSimilarity"] = "unavailable"
        unavailable.append("faceSimilarity")
        needs_review = True
    else:
        try:
            source_crop = _crop_face(source_image, source_primary_bbox)
            candidate_crop = _crop_face(candidate_image, primary_face.bbox if primary_face else None)
            similarity = _run_similarity(
                similarity_adapter,
                source_crop,
                candidate_crop,
                similarity_policy=similarity_policy,
            )
            cascade.append("face_similarity")
            _add_similarity_signals(signals, availability, similarity)
            if not bool(_attr(similarity, "available", False)):
                unavailable.append("faceSimilarity")
                needs_review = True
            elif not bool(_attr(similarity, "identity_reliable", False)):
                needs_review = True
        except Exception as exc:
            cascade.append("face_similarity")
            availability["faceSimilarity"] = "unavailable"
            availability["faceSimilarity.error"] = _exception_code(exc)
            signals["faceSimilarityReliable"] = False
            unavailable.append("faceSimilarity")
            needs_review = True

    return CandidateQASignalResult(
        signals=signals,
        model_availability={**_metadata_availability(source_analysis, reference_preprocess), **availability},
        cascade=tuple(cascade),
        models_unavailable=tuple(dict.fromkeys(unavailable)),
        needs_review=bool(needs_review),
        skipped_heavy_reason=skipped_heavy_reason,
        trait_matches=trait_matches,
    )


def _add_quality_signals(signals: dict[str, Any], quality: Any) -> None:
    blur_band = getattr(quality, "blur_band", None)
    overexposure_band = getattr(quality, "overexposure_band", None)
    crop_border_band = getattr(quality, "crop_border_band", None)
    if getattr(quality, "lighting_band", None) == "invalid" or blur_band == "blurred" or overexposure_band == "severe":
        signals["severeArtifactDetected"] = True
        signals["cropIsolationQuality"] = "fail"
    elif blur_band == "soft" or crop_border_band == "heavy_border":
        signals["artifactNeedsReview"] = True


def _add_visual_signals(signals: dict[str, Any], visual: VisualRiskAnalysis) -> None:
    region_kinds = [getattr(region, "kind", "") for region in getattr(visual, "regions", ())]
    actions = tuple(getattr(visual, "actions_required", ()))
    has_text_logo = ACTION_NEUTRALIZE_TEXT_LOGO in actions or any(kind in TEXT_LOGO_KINDS for kind in region_kinds)
    has_background_person = ACTION_NEUTRALIZE_BACKGROUND_PERSON in actions or "background-person" in region_kinds
    complexity = str(getattr(visual, "background_complexity", "unknown") or "unknown")
    counts: dict[str, int] = {}
    for kind in region_kinds:
        counts[kind] = counts.get(kind, 0) + 1
    signals["visualRegionCounts"] = counts
    signals["visualActionsRequired"] = list(actions)
    signals["logoTextWatermarkDetected"] = bool(has_text_logo)
    signals["textLogoWatermarkRisk"] = "high" if has_text_logo else "low"
    signals["secondaryPersonGenerated"] = bool(has_background_person)
    if has_background_person:
        signals["backgroundLeakageRisk"] = "high"
    elif complexity == "high":
        signals["backgroundLeakageRisk"] = "medium"
        signals["backgroundComplexityNeedsReview"] = True
    elif complexity == "medium":
        signals["backgroundLeakageRisk"] = "medium"
    else:
        signals["backgroundLeakageRisk"] = "low"
    signals.setdefault("secondaryFaceLeakageRisk", "high" if has_background_person else "low")


def _add_local_risk_signals(signals: dict[str, Any], availability: dict[str, str], risk: LocalSafetyRiskResult) -> None:
    adult_like = risk.adult_like
    if adult_like is None and risk.adult_like_score is not None:
        adult_like = float(risk.adult_like_score) >= ADULT_LIKE_MINIMUM
    brand_fit = risk.brand_fit
    if brand_fit is None and risk.brand_fit_score is not None:
        brand_fit = float(risk.brand_fit_score) >= BRAND_FIT_MINIMUM
    artifact_score = risk.severe_artifact_score if risk.severe_artifact_score is not None else risk.artifact_score
    signals["adultLike"] = adult_like
    signals["brandFit"] = brand_fit
    signals["childlikeScore"] = _rounded(risk.childlike_score)
    signals["sexualizedScore"] = _rounded(risk.sexualized_score)
    signals["beautificationScore"] = _rounded(risk.beautification_score)
    signals["severeArtifactScore"] = _rounded(artifact_score)
    signals["brandMismatchScore"] = _rounded(risk.brand_mismatch_score)
    if _score_high(risk.childlike_score):
        signals["childlikeOrTeenager"] = True
    if _score_high(risk.sexualized_score):
        signals["sexualizedOrNightlife"] = True
        signals["brandFit"] = False
    if _score_high(artifact_score):
        signals["severeArtifactDetected"] = True
        signals["cropIsolationQuality"] = "fail"


def _add_similarity_signals(signals: dict[str, Any], availability: dict[str, str], similarity: Any) -> None:
    if not bool(_attr(similarity, "available", False)):
        availability["faceSimilarity"] = "unavailable"
        signals["faceSimilarityReliable"] = False
        return
    if not bool(_attr(similarity, "identity_reliable", False)):
        availability["faceSimilarity"] = "uncalibrated"
        signals["faceSimilarityReliable"] = False
        signals["faceSimilarityNeedsReview"] = True
        return
    availability["faceSimilarity"] = "available"
    signals["faceSimilarityReliable"] = True
    signals["faceSimilarityScore"] = _rounded(_attr(similarity, "score", None))
    signals["faceSimilarityNeedsReview"] = bool(_attr(similarity, "needs_review", False))


def _compare_traits(source_traits: Mapping[str, Any], candidate_traits: Mapping[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    _compare_value(result, "hair_color_range", source_traits, candidate_traits, "hair_color_range")
    _compare_presence_and_style(result, "eyewear", source_traits, candidate_traits, "eyewear_present", "eyewear_style")
    _compare_presence_and_style(result, "facial_hair", source_traits, candidate_traits, "facial_hair_present", "facial_hair_style")
    _compare_value(result, "clothing_category", source_traits, candidate_traits, "clothing_category")
    _compare_value(result, "clothing_color", source_traits, candidate_traits, "clothing_color")
    if "gender" in source_traits or "gender" in candidate_traits:
        result["onboardingGenderContract"] = "not_image_inferred"
    return result


def _compare_value(result: dict[str, str], result_key: str, source: Mapping[str, Any], candidate: Mapping[str, Any], key: str) -> None:
    left = _concrete_trait(source, key)
    right = _concrete_trait(candidate, key)
    if left is None or right is None:
        result[result_key] = "review"
    elif left == right:
        result[result_key] = "match"
    else:
        result[result_key] = "mismatch"


def _compare_presence_and_style(result: dict[str, str], prefix: str, source: Mapping[str, Any], candidate: Mapping[str, Any], presence_key: str, style_key: str) -> None:
    left_present = _concrete_bool(source, presence_key)
    right_present = _concrete_bool(candidate, presence_key)
    presence_result_key = f"{prefix}_present"
    style_result_key = f"{prefix}_style"
    if left_present is None or right_present is None:
        result[presence_result_key] = "review"
        result[style_result_key] = "review"
        return
    if left_present != right_present:
        result[presence_result_key] = "mismatch"
        result[style_result_key] = "mismatch"
        return
    result[presence_result_key] = "match"
    if not left_present:
        result[style_result_key] = "match"
        return
    _compare_value(result, style_result_key, source, candidate, style_key)


def _concrete_trait(values: Mapping[str, Any], key: str) -> str | None:
    if not _high_confidence(values, key):
        return None
    raw = values.get(key)
    if isinstance(raw, Mapping):
        raw = raw.get("value") or raw.get("label")
    if raw is None:
        return None
    value = str(raw).strip().lower()
    return None if value in UNCERTAIN_VALUES else value


def _concrete_bool(values: Mapping[str, Any], key: str) -> bool | None:
    if not _high_confidence(values, key):
        return None
    raw = values.get(key)
    if isinstance(raw, Mapping):
        raw = raw.get("value")
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        lowered = raw.strip().lower()
        if lowered in {"true", "yes", "present"}:
            return True
        if lowered in {"false", "no", "absent", "none"}:
            return False
    return None


def _high_confidence(values: Mapping[str, Any], key: str) -> bool:
    raw = values.get(key)
    if isinstance(raw, Mapping):
        confidence = raw.get("confidence")
    else:
        confidence = values.get(f"{key}_confidence") or values.get("confidence")
    try:
        return confidence is not None and float(confidence) >= MIN_CONFIDENCE
    except (TypeError, ValueError):
        return False


def _has_hard_lightweight_issue(signals: Mapping[str, Any]) -> bool:
    return any(
        signals.get(key) is True
        for key in (
            "noFaceDetected",
            "multipleFacesGenerated",
            "secondaryPersonGenerated",
            "logoTextWatermarkDetected",
            "sexualizedOrNightlife",
            "childlikeOrTeenager",
            "severeArtifactDetected",
            "hardTraitContradiction",
        )
    )


def _availability_from_face_detector(result: FaceDetectorResult, *, unavailable: bool) -> dict[str, str]:
    availability = {"faceDetector": "unavailable" if unavailable else "available"}
    for key, value in result.model_availability.items():
        key_text = str(key)
        if key_text == "faceDetector":
            continue
        availability[key_text] = _safe_status(value)
    return availability


def _face_detector_unavailable(result: FaceDetectorResult) -> bool:
    provider = str(getattr(result, "provider", "") or "").lower()
    if "deterministic_fallback" in provider or provider == "fallback":
        return True
    statuses = [str(value).lower() for value in getattr(result, "model_availability", {}).values()]
    return any(status in {"unavailable", "critical_unavailable"} for status in statuses)


def _metadata_availability(source_analysis: Mapping[str, Any], reference_preprocess: Mapping[str, Any]) -> dict[str, str]:
    availability: dict[str, str] = {}
    for prefix, document in (("source", source_analysis), ("reference", reference_preprocess)):
        raw = document.get("modelAvailability")
        if isinstance(raw, Mapping):
            availability.update({f"{prefix}.{key}": _safe_status(value) for key, value in raw.items()})
        stage = document.get("stage") or document.get("status")
        if stage is not None:
            availability[f"{prefix}.stage"] = _safe_status(stage)
    return availability


def _primary_face(faces: Sequence[FaceDetection]) -> FaceDetection | None:
    if not faces:
        return None
    return max(faces, key=lambda face: (face.confidence or 0.0, face.area_ratio))


def _crop_face(image: Image.Image, bbox: Sequence[float] | None) -> Image.Image:
    if bbox is None:
        return image.copy()
    left, top, right, bottom = _bbox_to_xyxy(bbox, image.size)
    if right <= left or bottom <= top:
        return image.copy()
    return image.crop((left, top, right, bottom))


def _bbox_to_xyxy(bbox: Sequence[float], size: tuple[int, int]) -> tuple[int, int, int, int]:
    values = [float(value) for value in bbox[:4]]
    width, height = size
    if len(values) < 4:
        return (0, 0, width, height)
    x, y, third, fourth = values
    if all(0.0 <= value <= 1.0 for value in values):
        left, top, right, bottom = x * width, y * height, (x + third) * width, (y + fourth) * height
    elif third > x and fourth > y:
        left, top, right, bottom = x, y, third, fourth
    else:
        left, top, right, bottom = x, y, x + third, y + fourth
    return (
        max(0, min(width, int(round(left)))),
        max(0, min(height, int(round(top)))),
        max(0, min(width, int(round(right)))),
        max(0, min(height, int(round(bottom)))),
    )


def _run_local_risk(adapter: LocalSafetyRiskAdapter | Callable[..., Any], image: Image.Image) -> Any:
    analyze = getattr(adapter, "analyze", None)
    if analyze is not None:
        return analyze(image)
    return adapter(image)


def _normalize_local_risk(value: Any) -> LocalSafetyRiskResult:
    if isinstance(value, LocalSafetyRiskResult):
        severe_artifact_score = value.severe_artifact_score if value.severe_artifact_score is not None else value.artifact_score
        return LocalSafetyRiskResult(
            provider=value.provider,
            available=value.available,
            calibrated=value.calibrated,
            childlike_score=value.childlike_score,
            sexualized_score=value.sexualized_score,
            beautification_score=value.beautification_score,
            brand_mismatch_score=value.brand_mismatch_score,
            artifact_score=value.artifact_score,
            severe_artifact_score=severe_artifact_score,
            adult_like=value.adult_like,
            brand_fit=value.brand_fit,
            adult_like_score=value.adult_like_score,
            brand_fit_score=value.brand_fit_score,
            calibration_version=value.calibration_version,
            availability_reason=value.availability_reason,
            needs_review=value.needs_review,
        )
    return LocalSafetyRiskResult(
        provider=str(_attr(value, "provider", "clip")),
        available=bool(_attr(value, "available", False)),
        calibrated=bool(_attr(value, "calibrated", False)),
        childlike_score=_rounded(_attr(value, "childlike_score", None)),
        sexualized_score=_rounded(_attr(value, "sexualized_score", None)),
        beautification_score=_rounded(_attr(value, "beautification_score", None)),
        brand_mismatch_score=_rounded(_attr(value, "brand_mismatch_score", None)),
        severe_artifact_score=_rounded(_attr(value, "severe_artifact_score", None)),
        adult_like_score=_rounded(_attr(value, "adult_like_score", None)),
        brand_fit_score=_rounded(_attr(value, "brand_fit_score", None)),
        calibration_version=_attr(value, "calibration_version", None),
        availability_reason=_attr(value, "availability_reason", None),
        needs_review=bool(_attr(value, "needs_review", False)),
    )


def _unavailable_local_risk(reason: str) -> LocalSafetyRiskResult:
    return LocalSafetyRiskResult(
        provider="clip",
        available=False,
        calibrated=False,
        availability_reason=reason,
        needs_review=True,
    )


def _run_similarity(adapter: SimilarityAdapter | Callable[..., Any], source_crop: Image.Image, candidate_crop: Image.Image, *, similarity_policy: Any) -> Any:
    compare = getattr(adapter, "compare", None)
    if compare is not None:
        return compare(source_crop, candidate_crop, calibration_policy=similarity_policy)
    return adapter(source_crop, candidate_crop, calibration_policy=similarity_policy)


def _critical_unavailable(visual: VisualRiskAnalysis) -> bool:
    if getattr(visual, "status", None) == STATUS_CRITICAL_UNAVAILABLE:
        return True
    return getattr(visual, "provider_available", True) is False and getattr(visual, "risk", None) == "block"


def _availability_status(available: bool, status: Any) -> str:
    if available:
        return "available" if status in {None, "available"} else _safe_status(status)
    if status == STATUS_CRITICAL_UNAVAILABLE:
        return STATUS_CRITICAL_UNAVAILABLE
    return "unavailable"


def _local_risk_status(risk: LocalSafetyRiskResult) -> str:
    if not risk.available:
        return "unavailable"
    return "available" if risk.calibrated else "uncalibrated"


def _score_high(value: float | None, threshold: float = SEVERE_RISK_THRESHOLD) -> bool:
    return value is not None and float(value) >= threshold


def _rounded(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), 6)
    except (TypeError, ValueError):
        return None


def _attr(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(key, default)
    return getattr(value, key, default)


def _exception_code(exc: Exception) -> str:
    name = exc.__class__.__name__
    return name if name else "Exception"


def _safe_status(value: Any) -> str:
    if value is None:
        return "unknown"
    text = str(value).strip()
    if not text:
        return "unknown"
    return text if text.replace("_", "").replace("-", "").isalnum() else value.__class__.__name__


def _sanitize_document(value: Any) -> Any:
    if isinstance(value, Mapping):
        sanitized = {}
        for key, item in value.items():
            key_text = str(key)
            if _is_sensitive_key(key_text):
                continue
            sanitized[key_text] = _sanitize_document(item)
        return sanitized
    if isinstance(value, (list, tuple)):
        return [_sanitize_document(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return _safe_status(value)


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    normalized = lowered.replace("-", "_")
    if normalized in SENSITIVE_EXACT_KEYS:
        return True
    return any(normalized.endswith(suffix) for suffix in SENSITIVE_SUFFIXES)


__all__ = [
    "CandidateQASignalResult",
    "FaceDetector",
    "LocalSafetyRiskAdapter",
    "LocalSafetyRiskResult",
    "SimilarityAdapter",
    "VisualRiskAdapter",
    "build_candidate_qa_signals",
]
